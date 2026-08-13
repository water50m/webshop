import os
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_history_analysis_preparation.db"

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import HistoryConversation, HistoryMessage, User, UserRole
from app.services.auth import hash_password

client = TestClient(app)


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(User(username="owner", password_hash=hash_password("ownerpass"), role=UserRole.owner))
    conversation = HistoryConversation(
        external_id="facebook-conversation-should-not-leak",
        customer_external_id="facebook-user-should-not-leak",
        customer_display_name="Ada Lovelace",
    )
    db.add(conversation)
    db.flush()
    now = datetime.utcnow()
    db.add_all(
        [
            HistoryMessage(
                history_conversation_id=conversation.id,
                external_id="message-1",
                direction="in",
                text="ชื่อ: Ada โทร 081-234-5678 ที่อยู่: 99 ถนนตัวอย่าง กรุงเทพ 10110",
                sent_at=now,
            ),
            HistoryMessage(
                history_conversation_id=conversation.id,
                external_id="message-2",
                direction="out",
                text="สั่งชา 2 แก้วได้ค่ะ ดูเมนู https://facebook.com/example",
                sent_at=now + timedelta(minutes=1),
            ),
        ]
    )
    db.commit()
    db.close()
    response = client.post("/api/auth/login", json={"username": "owner", "password": "ownerpass"})
    assert response.status_code == 200


def teardown_function():
    Base.metadata.drop_all(bind=engine)


def test_prepare_review_and_approve_redacted_local_history():
    response = client.post("/api/history-preparation/analysis-preparations", json={"max_conversations_per_batch": 1})

    assert response.status_code == 200
    preparation = response.json()
    assert preparation["conversation_count"] == 1
    assert preparation["message_count"] == 2
    assert preparation["batch_count"] == 1
    assert preparation["redaction_counts"] == {"address": 1, "name": 1, "phone": 1, "url": 1}
    batch_id = preparation["batches"][0]["id"]

    batch = client.get(f"/api/history-preparation/analysis-batches/{batch_id}")
    assert batch.status_code == 200
    messages = batch.json()["content"]["conversations"][0]["messages"]
    assert messages == [
        {"speaker": "customer", "text": "[NAME] โทร [PHONE] [ADDRESS]"},
        {"speaker": "shop", "text": "สั่งชา 2 แก้วได้ค่ะ ดูเมนู [URL]"},
    ]
    assert "Ada Lovelace" not in str(batch.json())
    assert "facebook-user-should-not-leak" not in str(batch.json())

    approved = client.post(f"/api/history-preparation/analysis-batches/{batch_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_at"] is not None


def test_keeps_rough_delivery_context_but_masks_precise_location_data():
    from app.services.history_analysis_preparation import redact_text

    redacted, counts = redact_text(
        "ส่งหอในโซน A หน้าห้อง 208 เลขที่ 99/12 หมู่ 7 โทร 081-234-5678 https://maps.example/a"
    )

    assert redacted == "ส่งหอในโซน A [UNIT] [ADDRESS_NUMBER] [VILLAGE] โทร [PHONE] [URL]"
    assert counts == {"address": 2, "phone": 1, "unit_number": 1, "url": 1}
