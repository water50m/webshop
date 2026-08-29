"""Redis-backed Inbox events with an in-process fallback for local development."""

import json
import logging
from queue import Empty, Full, Queue
from threading import Lock
from typing import Callable, Iterator

try:
    import redis
except ImportError:  # pragma: no cover - lets existing local installs fall back safely
    redis = None

from app.config import settings

logger = logging.getLogger(__name__)

_REDIS_CHANNEL = "sstore:inbox-events"


class InboxEventBroker:
    def __init__(self, redis_url: str = "") -> None:
        self._subscribers: set[Queue[dict]] = set()
        self._lock = Lock()
        self._redis = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=25,
        ) if redis_url and redis is not None else None
        self._redis_failed = False

    def _publish_local(self, payload: dict) -> None:
        """Deliver to streams served by this process when Redis is unavailable."""
        with self._lock:
            subscribers = tuple(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(payload)
            except Full:
                # A stale browser must not block Facebook's webhook.  Dropping
                # its oldest event is safe because a manual page refresh still
                # reloads the complete state from the database.
                try:
                    subscriber.get_nowait()
                    subscriber.put_nowait(payload)
                except (Empty, Full):
                    pass

    def publish(self, payload: dict) -> None:
        if self._redis is not None and not self._redis_failed:
            try:
                self._redis.publish(_REDIS_CHANNEL, json.dumps(payload, ensure_ascii=False))
                return
            except redis.RedisError:
                self._redis_failed = True
                logger.warning("Redis Inbox event publishing failed; using this process only", exc_info=True)
        self._publish_local(payload)

    def stream(self, can_receive: Callable[[dict], bool] | None = None) -> Iterator[str]:
        if self._redis is not None and not self._redis_failed:
            pubsub = None
            try:
                pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(_REDIS_CHANNEL)
                while True:
                    event = pubsub.get_message(timeout=20)
                    if event is None:
                        yield ": keep-alive\n\n"
                        continue
                    try:
                        payload = json.loads(event["data"])
                    except (TypeError, json.JSONDecodeError):
                        logger.warning("Ignoring malformed Redis Inbox event")
                        continue
                    if can_receive is not None and not can_receive(payload):
                        continue
                    yield f"event: inbox.message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except redis.RedisError:
                self._redis_failed = True
                logger.warning("Redis Inbox event subscription failed; using this process only", exc_info=True)
            finally:
                if pubsub is not None:
                    pubsub.close()

        subscriber: Queue[dict] = Queue(maxsize=100)
        with self._lock:
            self._subscribers.add(subscriber)
        try:
            while True:
                try:
                    payload = subscriber.get(timeout=20)
                    if can_receive is not None and not can_receive(payload):
                        continue
                    yield f"event: inbox.message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                except Empty:
                    # Keep proxies and browser connections alive while there
                    # are no incoming Facebook messages.
                    yield ": keep-alive\n\n"
        finally:
            with self._lock:
                self._subscribers.discard(subscriber)


inbox_event_broker = InboxEventBroker(settings.redis_url)
