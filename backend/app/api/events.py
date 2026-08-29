from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.db import SessionLocal
from app.deps import accessible_channel_ids, get_current_user
from app.models import User
from app.services.inbox_events import inbox_event_broker

router = APIRouter(
    prefix="/api/events",
    tags=["events"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/inbox")
def stream_inbox_events(user: User = Depends(get_current_user)):
    def can_receive(payload: dict) -> bool:
        channel_id = payload.get("conversation", {}).get("channel_id")
        if not isinstance(channel_id, int):
            return False
        # Re-check on every event so revoking a page membership also stops an
        # already-open SSE connection without waiting for a browser reload.
        db = SessionLocal()
        try:
            return channel_id in accessible_channel_ids(user, db)
        finally:
            db.close()

    return StreamingResponse(
        inbox_event_broker.stream(can_receive),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
