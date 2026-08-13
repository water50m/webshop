from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.deps import get_current_user
from app.services.inbox_events import inbox_event_broker

router = APIRouter(
    prefix="/api/events",
    tags=["events"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/inbox")
def stream_inbox_events():
    return StreamingResponse(
        inbox_event_broker.stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
