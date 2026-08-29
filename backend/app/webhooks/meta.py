import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import ChannelType, Message
from app.services.message_ingest import ingest_incoming_message, ingest_product_selection
from app.services.inbox_events import inbox_event_broker
from app.services.conversation_labels import label_slots
from app.services.meta_messenger import send_menu_answer, send_promptpay_qr, send_selection_confirmation, send_verified_answer

router = APIRouter(prefix="/webhooks/meta", tags=["meta-webhook"])
logger = logging.getLogger(__name__)


def _is_sticker_message(message: dict) -> bool:
    """Recognize Messenger stickers without treating ordinary photos as greetings."""
    if message.get("sticker_id"):
        return True
    for attachment in message.get("attachments", []):
        if attachment.get("type") == "sticker" or attachment.get("sticker_id"):
            return True
        if (attachment.get("payload") or {}).get("sticker_id"):
            return True
    return False


def _inbox_message_event(conversation, message) -> dict:
    """Build the exact persisted state that the Inbox needs; no follow-up read is required in the browser."""
    primary_label, payment_label = label_slots(conversation)
    pending_draft = next((draft for draft in conversation.draft_orders if draft.status.value == "pending"), None)
    return {
        "conversation": {
            "id": conversation.id,
            "channel_id": conversation.channel_id,
            "customer_id": conversation.customer_id,
            "customer_display_name": conversation.customer.display_name,
            "customer_profile_image_url": conversation.customer.profile_image_url,
            "last_message_at": conversation.last_message_at.isoformat(),
            "status": conversation.status,
            "is_hidden": conversation.is_hidden,
            "is_pinned": conversation.is_pinned,
            "unread_count": conversation.unread_count,
            "bill_count": conversation.bill_count,
            "primary_label": primary_label,
            "payment_label": payment_label,
            "delivery_note": conversation.delivery_note,
            "order_confirmed_at": None,
        },
        "message": {
            "id": message.id,
            "direction": message.direction,
            "text": message.text,
            "created_at": message.created_at.isoformat(),
            "sent_by_display_name": None,
        },
        "draft_order": (
            {
                "id": pending_draft.id,
                "conversation_id": pending_draft.conversation_id,
                "status": pending_draft.status.value,
                "note": pending_draft.note,
                "total": float(sum(item.unit_price * item.quantity for item in pending_draft.items)),
                "confirmed_at": None,
                "confirmed_by_display_name": None,
                "items": [
                    {
                        "id": item.id,
                        "product_id": item.product_id,
                        "product_name": item.product.name if item.product else None,
                        "matched_text": item.matched_text,
                        "quantity": item.quantity,
                        "unit_price": float(item.unit_price),
                        "special_request": item.special_request,
                    }
                    for item in pending_draft.items
                ],
            }
            if pending_draft
            else None
        ),
    }


@router.get("")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.meta_verify_token:
        return Response(content=challenge or "", media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


def _verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not settings.meta_app_secret:
        # No secret configured (local/dev) -- skip verification.
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.meta_app_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    provided = signature_header.split("sha256=", 1)[1]
    return hmac.compare_digest(expected, provided)


@router.post("")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not _verify_signature(raw_body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    object_type = payload.get("object")

    channel_type = {
        "page": ChannelType.facebook_page,
        "instagram": ChannelType.instagram,
    }.get(object_type)

    if channel_type is None:
        logger.warning("Unhandled webhook object type: %s", object_type)
        return {"status": "ignored"}

    for entry in payload.get("entry", []):
        channel_external_id = str(entry.get("id"))
        for messaging_event in entry.get("messaging", []):
            sender_id = messaging_event.get("sender", {}).get("id")
            if messaging_event.get("message", {}).get("is_echo"):
                continue

            postback = messaging_event.get("postback")
            if sender_id and postback and channel_type == ChannelType.facebook_page:
                payload_text = str(postback.get("payload") or "")
                if payload_text.startswith("ORDER_PRODUCT:"):
                    try:
                        product_id = int(payload_text.removeprefix("ORDER_PRODUCT:"))
                    except ValueError:
                        logger.warning("Ignoring malformed Messenger product postback")
                        continue
                    selection = ingest_product_selection(
                        db=db,
                        channel_type=channel_type,
                        channel_external_id=channel_external_id,
                        sender_external_id=sender_id,
                        product_id=product_id,
                        raw_payload=messaging_event,
                    )
                    if selection is not None and channel_type == ChannelType.facebook_page:
                        conversation, product, incoming_message = selection
                        send_selection_confirmation(db, conversation, channel_external_id, sender_id, product)
                    db.commit()
                    if selection is not None:
                        inbox_event_broker.publish(_inbox_message_event(conversation, incoming_message))
                        for outgoing_message in (
                            db.query(Message)
                            .filter(
                                Message.conversation_id == conversation.id,
                                Message.direction == "out",
                                Message.id > incoming_message.id,
                            )
                            .order_by(Message.id)
                            .all()
                        ):
                            inbox_event_broker.publish(_inbox_message_event(conversation, outgoing_message))
                continue

            message = messaging_event.get("message")
            if not sender_id or not message:
                continue
            is_sticker = _is_sticker_message(message)
            text = "[สติกเกอร์]" if is_sticker else message.get("text", "")
            incoming_message, conversation, classification, parser_result = ingest_incoming_message(
                db=db,
                channel_type=channel_type,
                channel_external_id=channel_external_id,
                sender_external_id=sender_id,
                text=text,
                raw_payload=messaging_event,
                parser_text="สวัสดี" if is_sticker else None,
            )
            # ingest_incoming_message commits before returning.  Publish only
            # this committed payload so Inbox never receives data that is not
            # already durable in the database.
            inbox_event_broker.publish(_inbox_message_event(conversation, incoming_message))
            if channel_type == ChannelType.facebook_page and classification == "greeting":
                if parser_result.answer_text and send_verified_answer(db, conversation, channel_external_id, sender_id, parser_result.answer_text):
                    db.commit()
            elif channel_type == ChannelType.facebook_page and classification == "payment":
                if send_promptpay_qr(db, conversation, channel_external_id, sender_id):
                    db.commit()
            elif channel_type == ChannelType.facebook_page and parser_result.intent == "ask_menu" and parser_result.answer_text:
                if send_menu_answer(db, conversation, channel_external_id, sender_id, parser_result.answer_text):
                    db.commit()
            elif (
                channel_type == ChannelType.facebook_page
                and parser_result.intent == "start_order"
                and parser_result.items
                and parser_result.handoff_reason is None
                and not (incoming_message.raw_payload or {}).get("_duplicate_order")
            ):
                # This only acknowledges receipt.  It does not confirm an order,
                # reduce stock, or replace the staff confirmation in Inbox.
                if send_verified_answer(
                    db,
                    conversation,
                    channel_external_id,
                    sender_id,
                    "ได้รับรายการแล้ว กำลังตรวจสอบก่อนยืนยันครับ",
                ):
                    db.commit()
            elif channel_type == ChannelType.facebook_page and parser_result.handoff_reason:
                # A handoff is not a made-up answer.  It only tells the customer
                # that a person has been notified, so the chat never appears dead.
                if send_verified_answer(
                    db,
                    conversation,
                    channel_external_id,
                    sender_id,
                    "ได้รับข้อความแล้ว แอดมินกำลังตรวจสอบให้ครับ",
                ):
                    db.commit()
            elif (
                channel_type == ChannelType.facebook_page
                and parser_result.answer_text
                and parser_result.handoff_reason is None
            ):
                if send_verified_answer(db, conversation, channel_external_id, sender_id, parser_result.answer_text):
                    db.commit()

            # The automatic reply is persisted after the incoming message.
            # Send every new outgoing record to SSE only after that commit, so
            # Inbox displays the exact message the customer received.
            for outgoing_message in (
                db.query(Message)
                .filter(
                    Message.conversation_id == conversation.id,
                    Message.direction == "out",
                    Message.id > incoming_message.id,
                )
                .order_by(Message.id)
                .all()
            ):
                inbox_event_broker.publish(_inbox_message_event(conversation, outgoing_message))

    return {"status": "ok"}
