import base64
import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import ChannelType
from app.services.message_ingest import ingest_incoming_message

router = APIRouter(prefix="/webhooks/line", tags=["line-webhook"])
logger = logging.getLogger(__name__)


def _verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not settings.line_channel_secret:
        # No secret configured (local/dev) -- skip verification.
        return True
    if not signature_header:
        return False
    expected = base64.b64encode(
        hmac.new(settings.line_channel_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode("utf-8")
    return hmac.compare_digest(expected, signature_header)


@router.post("")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("X-Line-Signature")
    if not _verify_signature(raw_body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    destination = payload.get("destination", "")

    for event in payload.get("events", []):
        if event.get("type") != "message":
            continue
        message = event.get("message", {})
        if message.get("type") != "text":
            continue
        sender_id = event.get("source", {}).get("userId")
        if not sender_id:
            continue
        ingest_incoming_message(
            db=db,
            channel_type=ChannelType.line,
            channel_external_id=destination,
            sender_external_id=sender_id,
            text=message.get("text", ""),
            raw_payload=event,
        )

    return {"status": "ok"}
