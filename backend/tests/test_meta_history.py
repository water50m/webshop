import os
from datetime import datetime

os.environ["DATABASE_URL"] = "sqlite:///./test_meta_history.db"

import pytest

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import HistoryConversation, HistoryMessage
from app.services import meta_history


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "meta_history_access_token", "history-token")
    monkeypatch.setattr(settings, "meta_history_page_id", "")
    monkeypatch.setattr(settings, "meta_history_lookback_days", 60)
    yield
    Base.metadata.drop_all(bind=engine)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_history_import_stores_text_locally_and_skips_media(monkeypatch):
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    calls = []

    def fake_get(url, *, params=None, timeout=None):
        calls.append((url, params))
        if url.endswith("/me"):
            return FakeResponse({"id": "page-1", "name": "ร้านทดสอบ"})
        if url.endswith("/page-1/conversations"):
            return FakeResponse(
                {
                    "data": [
                        {
                            "id": "conversation-1",
                            "updated_time": now,
                            "participants": {"data": [{"id": "page-1", "name": "ร้านทดสอบ"}, {"id": "user-1", "name": "Ada"}]},
                        }
                    ]
                }
            )
        if url.endswith("/conversation-1/messages"):
            return FakeResponse(
                {
                    "data": [
                        {"id": "message-in", "message": "ข้าวหมกมีไหม", "from": {"id": "user-1"}, "created_time": now},
                        {"id": "message-out", "message": "มีค่ะ", "from": {"id": "page-1"}, "created_time": now},
                        {"id": "media-only", "from": {"id": "user-1"}, "created_time": now},
                    ]
                }
            )
        raise AssertionError(f"Unexpected GET: {url}")

    monkeypatch.setattr(meta_history.httpx, "get", fake_get)
    db = SessionLocal()
    try:
        run = meta_history.run_history_import(db)
        assert run.status == "completed"
        assert run.conversation_count == 1
        assert run.message_count == 2
        assert run.skipped_non_text_count == 1
        assert db.query(HistoryConversation).count() == 1
        messages = db.query(HistoryMessage).order_by(HistoryMessage.external_id).all()
        assert [(message.external_id, message.direction, message.text) for message in messages] == [
            ("message-in", "in", "ข้าวหมกมีไหม"),
            ("message-out", "out", "มีค่ะ"),
        ]
        assert len(calls) == 3
    finally:
        db.close()
