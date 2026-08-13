"""Read-only importer for text history from a Facebook Page.

This module deliberately uses only GET requests. It does not import or call
the Messenger sending service, and writes only to the history_* staging tables.
"""

import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import HistoryConversation, HistoryImportRun, HistoryMessage

logger = logging.getLogger(__name__)
_GRAPH_API_BASE_URL = "https://graph.facebook.com/v22.0"


class MetaHistoryError(Exception):
    pass


def _parse_graph_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _get(url: str, params: dict | None = None) -> dict:
    try:
        response = httpx.get(url, params=params, timeout=20.0)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        # Do not preserve the HTTP exception as its request URL can contain an
        # access token in query parameters. Keep the user-facing error safe.
        logger.warning("Meta history request failed with HTTP %s", exc.response.status_code)
        raise MetaHistoryError("Meta ปฏิเสธคำขออ่านประวัติแชต กรุณาตรวจ token และสิทธิ์ของเพจ") from None
    except (httpx.HTTPError, ValueError):
        raise MetaHistoryError("ไม่สามารถอ่านประวัติแชตจาก Meta ได้") from None
    if not isinstance(payload, dict):
        raise MetaHistoryError("Meta ส่งข้อมูลประวัติแชตในรูปแบบที่ไม่ถูกต้อง")
    return payload


def _pages(url: str, params: dict):
    next_url: str | None = url
    next_params: dict | None = params
    while next_url:
        payload = _get(next_url, next_params)
        yield payload.get("data") or []
        next_url = (payload.get("paging") or {}).get("next")
        next_params = None


def _participant(conversation: dict, page_id: str) -> tuple[str, str]:
    participants = (conversation.get("participants") or {}).get("data") or []
    for participant in participants:
        participant_id = str(participant.get("id") or "")
        if participant_id and participant_id != page_id:
            return participant_id, str(participant.get("name") or "")
    return "", ""


def run_history_import(db: Session) -> HistoryImportRun:
    """Import the configured lookback window into local staging tables only."""
    token = settings.meta_history_access_token
    if not token:
        raise MetaHistoryError("ยังไม่ได้ตั้งค่า META_HISTORY_ACCESS_TOKEN")

    page_id = settings.meta_history_page_id
    if not page_id:
        page_profile = _get(
            f"{_GRAPH_API_BASE_URL}/me",
            {"fields": "id,name", "access_token": token},
        )
        page_id = str(page_profile.get("id") or "")
    if not page_id:
        raise MetaHistoryError("ไม่พบ Page ID จาก token")

    now = datetime.utcnow()
    start = now - timedelta(days=settings.meta_history_lookback_days)
    run = HistoryImportRun(page_id=page_id, lookback_days=settings.meta_history_lookback_days)
    db.add(run)
    # Do not hold a SQLite write transaction while making Graph API requests.
    # The live web app can keep serving requests while this offline job runs.
    db.commit()
    db.refresh(run)
    run_id = run.id
    conversation_count = 0
    message_count = 0
    skipped_non_text_count = 0

    try:
        conversations_url = f"{_GRAPH_API_BASE_URL}/{page_id}/conversations"
        conversation_params = {
            "fields": "id,updated_time,participants{id,name}",
            "limit": 100,
            "access_token": token,
        }
        for conversations in _pages(conversations_url, conversation_params):
            # Meta returns this connection newest-first.  Once an entire page
            # is older than the requested window, later pages cannot contain
            # a message from the window, so avoid fetching their threads.
            page_is_before_window = bool(conversations) and all(
                (updated_at := _parse_graph_time(item.get("updated_time"))) is not None
                and updated_at < start
                for item in conversations
            )
            if page_is_before_window:
                break
            for external_conversation in conversations:
                external_id = str(external_conversation.get("id") or "")
                if not external_id:
                    continue
                updated_at = _parse_graph_time(external_conversation.get("updated_time"))
                if updated_at and updated_at < start:
                    continue
                customer_id, customer_name = _participant(external_conversation, page_id)
                existing_conversation = (
                    db.query(HistoryConversation).filter_by(external_id=external_id).first()
                )
                # A previously committed conversation whose last update has
                # not changed is already complete, so a resumed import need
                # not download its messages again.
                if existing_conversation and existing_conversation.updated_at == updated_at:
                    conversation_count += 1
                    continue
                messages_url = f"{_GRAPH_API_BASE_URL}/{external_id}/messages"
                message_params = {
                    "fields": "id,message,from{id,name},created_time",
                    "limit": 100,
                    "access_token": token,
                }
                # Fetch first, then open a short local write transaction.
                external_messages: list[dict] = []
                for messages in _pages(messages_url, message_params):
                    external_messages.extend(messages)

                conversation = existing_conversation
                if conversation is None:
                    conversation = HistoryConversation(external_id=external_id)
                    db.add(conversation)
                conversation.page_id = page_id
                conversation.customer_external_id = customer_id
                conversation.customer_display_name = customer_name
                conversation.updated_at = updated_at
                conversation.imported_at = now
                db.flush()
                conversation_count += 1
                for external_message in external_messages:
                        sent_at = _parse_graph_time(external_message.get("created_time"))
                        if sent_at is None or sent_at < start:
                            continue
                        text = str(external_message.get("message") or "").strip()
                        if not text:
                            skipped_non_text_count += 1
                            continue
                        message_id = str(external_message.get("id") or "")
                        if not message_id or db.query(HistoryMessage.id).filter_by(external_id=message_id).first():
                            continue
                        sender_id = str((external_message.get("from") or {}).get("id") or "")
                        db.add(
                            HistoryMessage(
                                history_conversation_id=conversation.id,
                                external_id=message_id,
                                direction="out" if sender_id == page_id else "in",
                                text=text,
                                sent_at=sent_at,
                                raw_payload=external_message,
                            )
                        )
                        message_count += 1
                db.commit()
        run = db.get(HistoryImportRun, run_id)
        run.status = "completed"
    except MetaHistoryError as exc:
        db.rollback()
        run = db.get(HistoryImportRun, run_id)
        run.status = "failed"
        run.error_detail = str(exc)
    finally:
        run = db.get(HistoryImportRun, run_id)
        run.conversation_count = conversation_count
        run.message_count = message_count
        run.skipped_non_text_count = skipped_non_text_count
        run.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(run)
    return run
