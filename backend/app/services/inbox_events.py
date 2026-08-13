"""In-process events for delivering newly persisted Inbox data to staff clients."""

import json
from queue import Empty, Full, Queue
from threading import Lock
from typing import Iterator


class InboxEventBroker:
    def __init__(self) -> None:
        self._subscribers: set[Queue[dict]] = set()
        self._lock = Lock()

    def publish(self, payload: dict) -> None:
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

    def stream(self) -> Iterator[str]:
        subscriber: Queue[dict] = Queue(maxsize=100)
        with self._lock:
            self._subscribers.add(subscriber)
        try:
            while True:
                try:
                    payload = subscriber.get(timeout=20)
                    yield f"event: inbox.message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                except Empty:
                    # Keep proxies and browser connections alive while there
                    # are no incoming Facebook messages.
                    yield ": keep-alive\n\n"
        finally:
            with self._lock:
                self._subscribers.discard(subscriber)


inbox_event_broker = InboxEventBroker()
