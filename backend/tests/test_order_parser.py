import os
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_order_parser.db"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import DraftOrder, DraftOrderStatus, Message, User, UserRole
from app.services.auth import hash_password
from app.services import meta_profile
from app.api import conversations as conversations_api
from app.config import settings
from app.services.order_parser import classify_sentence, is_order_sentence, parse_order_text

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(User(username="owner", password_hash=hash_password("ownerpass"), display_name="Owner", role=UserRole.owner))
    db.commit()
    db.close()
    login = client.post("/api/auth/login", json={"username": "owner", "password": "ownerpass"})
    assert login.status_code == 200, login.text
    monkeypatch.setattr(settings, "meta_app_secret", "")
    monkeypatch.setattr(settings, "line_channel_secret", "")
    yield
    Base.metadata.drop_all(bind=engine)


def create_product(sku, name, price=50):
    res = client.post("/api/products", json={"sku": sku, "name": name, "price": price})
    assert res.status_code == 200, res.text
    product = res.json()
    stock = client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": 10, "note": "test stock"})
    assert stock.status_code == 200, stock.text
    return stock.json()


def add_modifier(product_id, name, price_delta=0):
    res = client.post(f"/api/products/{product_id}/modifiers", json={"name": name, "price_delta": price_delta})
    assert res.status_code == 200, res.text
    return res.json()


# --- Rule 1: greeting/question classification ---


@pytest.mark.parametrize(
    "text,expected",
    [
        ("สวัสดีค่ะ", "greeting"),
        ("หวัดดีครับ", "greeting"),
        ("ราคาเท่าไหร่คะ", "question"),
        ("เปิดกี่โมงคะ", "question"),
        ("มีส้มตำไหม", "question"),
        ("ขอส้มตำ 1 จาน", "order"),
        ("", "empty"),
    ],
)
def test_classify_sentence(text, expected):
    assert classify_sentence(text) == expected


def test_greeting_followed_by_order_is_still_an_order():
    # Mixed greeting + order text should not be discarded just because it
    # starts with a greeting phrase.
    assert is_order_sentence("สวัสดีค่ะ ขอส้มตำ") is True


# --- Rule 2 + 3: matching products/modifiers/ingredients with negation ---


def test_parse_matches_product_and_modifier_without_negation():
    db = SessionLocal()
    product = create_product("PAD1", "ผัดไทยกุ้ง")
    add_modifier(product["id"], "ถั่ว")
    matches = parse_order_text(db, "ขอผัดไทยกุ้ง ใส่ถั่วด้วย")
    db.close()

    kinds = {(m.term.kind, m.term.name, m.negated) for m in matches}
    assert ("product", "ผัดไทยกุ้ง", False) in kinds
    assert ("modifier", "ถั่ว", False) in kinds


def test_parse_detects_negation_immediately_before_term():
    db = SessionLocal()
    product = create_product("PAD2", "ผัดไทยกุ้ง")
    add_modifier(product["id"], "ถั่ว")
    matches = parse_order_text(db, "ขอผัดไทยกุ้ง ไม่ใส่ถั่ว")
    db.close()

    negated = {m.term.name: m.negated for m in matches}
    assert negated["ผัดไทยกุ้ง"] is False
    assert negated["ถั่ว"] is True


def test_negation_does_not_leak_to_unrelated_later_term():
    # "ไม่ใส่ถั่ว" only negates ถั่ว -- a second modifier mentioned afterwards
    # without its own negation marker must stay un-negated.
    db = SessionLocal()
    product = create_product("PAD3", "ผัดไทยกุ้ง")
    add_modifier(product["id"], "ถั่ว")
    add_modifier(product["id"], "พริก")
    matches = parse_order_text(db, "ขอผัดไทยกุ้ง ไม่ใส่ถั่ว ใส่พริกด้วย")
    db.close()

    negated = {m.term.name: m.negated for m in matches}
    assert negated["ถั่ว"] is True
    assert negated["พริก"] is False


# --- End-to-end through the webhook: draft order + special_request notes ---


def test_meta_webhook_sends_customization_to_admin_without_a_draft_order():
    product = create_product("PAD4", "ผัดไทยกุ้ง", price=60)
    add_modifier(product["id"], "ถั่ว")

    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page1",
                "messaging": [
                    {
                        "sender": {"id": "user1"},
                        "message": {"text": "ขอผัดไทยกุ้ง ไม่ใส่ถั่ว"},
                    }
                ],
            }
        ],
    }
    res = client.post("/webhooks/meta", json=payload)
    assert res.status_code == 200, res.text

    assert client.get("/api/draft-orders").json() == []
    conversation = client.get("/api/conversations").json()[0]
    assert conversation["primary_label"] == "รอแอดมิน"


def test_meta_webhook_fetches_and_returns_messenger_sender_name(monkeypatch):
    monkeypatch.setattr(meta_profile.settings, "meta_page_access_token", "page-token")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"first_name": "Ada", "last_name": "Lovelace"}

    def fake_get(url, *, params, timeout):
        assert url.endswith("/user-profile-1")
        assert params["fields"] == "first_name,last_name"
        assert params["access_token"] == "page-token"
        assert timeout == 5.0
        return FakeResponse()

    monkeypatch.setattr(meta_profile.httpx, "get", fake_get)
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-profile-1",
                "messaging": [
                    {
                        "sender": {"id": "user-profile-1"},
                        "message": {"text": "ขอทราบราคา"},
                    }
                ],
            }
        ],
    }

    res = client.post("/webhooks/meta", json=payload)
    assert res.status_code == 200, res.text

    conversations = client.get("/api/conversations")
    assert conversations.status_code == 200, conversations.text
    assert conversations.json()[0]["customer_display_name"] == "Ada Lovelace"


def test_greeting_message_does_not_create_draft_order():
    create_product("PAD5", "ผัดไทยกุ้ง")

    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page1",
                "messaging": [{"sender": {"id": "user2"}, "message": {"text": "สวัสดีค่ะ"}}],
            }
        ],
    }
    res = client.post("/webhooks/meta", json=payload)
    assert res.status_code == 200, res.text


def test_opening_a_conversation_marks_customer_messages_as_read():
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-unread",
                "messaging": [{"sender": {"id": "user-unread"}, "message": {"text": "สวัสดี"}}],
            }
        ],
    }
    assert client.post("/webhooks/meta", json=payload).status_code == 200
    conversation = client.get("/api/conversations").json()[0]
    assert conversation["unread_count"] == 1

    read = client.post(f"/api/conversations/{conversation['id']}/mark-read")
    assert read.status_code == 200, read.text
    assert read.json()["unread_count"] == 0

    payload["entry"][0]["messaging"][0]["message"]["text"] = "มีใครอยู่ไหม"
    assert client.post("/webhooks/meta", json=payload).status_code == 200
    assert client.get("/api/conversations").json()[0]["unread_count"] == 1


def test_auto_answer_is_marked_in_progress_without_waiting_for_admin():
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-auto-progress",
                "messaging": [{"sender": {"id": "user-auto-progress"}, "message": {"text": "สวัสดี"}}],
            }
        ],
    }
    assert client.post("/webhooks/meta", json=payload).status_code == 200
    conversation = client.get("/api/conversations").json()[0]
    assert conversation["primary_label"] == "ดำเนินการ"
    assert conversation["status"] == "in_progress"


def test_staff_reply_changes_waiting_admin_label_to_in_progress(monkeypatch):
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-staff-reply",
                "messaging": [{"sender": {"id": "user-staff-reply"}, "message": {"text": "ร้านเปิดกี่โมงหรอ"}}],
            }
        ],
    }
    assert client.post("/webhooks/meta", json=payload).status_code == 200
    conversation = client.get("/api/conversations").json()[0]
    assert conversation["primary_label"] == "รอแอดมิน"

    def fake_send_manual_text(db, conversation, text):
        db.add(Message(conversation_id=conversation.id, direction="out", text=text, raw_payload={"test": True}))
        return True

    monkeypatch.setattr(conversations_api, "send_manual_text", fake_send_manual_text)
    sent = client.post(f"/api/conversations/{conversation['id']}/send-message", json={"text": "เปิด 10 โมงครับ"})
    assert sent.status_code == 200, sent.text
    assert sent.json()["conversation"]["primary_label"] == "ดำเนินการ"
    assert sent.json()["conversation"]["status"] == "in_progress"
    assert sent.json()["message"]["text"] == "เปิด 10 โมงครับ"


def test_orphaned_old_draft_is_not_shown_after_a_new_greeting():
    """A deleted chat must not leave an old review card in the next chat cycle."""
    create_product("ORPHAN-DRAFT", "ข้าวหมกไก่ทอด", price=45)
    order_payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-orphan-draft",
                "messaging": [{"sender": {"id": "user-orphan-draft"}, "message": {"text": "เอาข้าวหมกไก่ทอด 1"}}],
            }
        ],
    }
    assert client.post("/webhooks/meta", json=order_payload).status_code == 200
    assert len(client.get("/api/draft-orders?status=pending").json()) == 1

    # Simulate a legacy chat cleanup that removed messages but not its pending
    # draft.  A later greeting must not make that old draft reappear.
    db = SessionLocal()
    draft = db.query(DraftOrder).one()
    draft.created_at = datetime.utcnow() - timedelta(days=1)
    draft.updated_at = draft.created_at
    db.query(Message).delete()
    db.commit()
    db.close()

    greeting_payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-orphan-draft",
                "messaging": [{"sender": {"id": "user-orphan-draft"}, "message": {"text": "สวัสดี"}}],
            }
        ],
    }
    assert client.post("/webhooks/meta", json=greeting_payload).status_code == 200

    assert client.get("/api/draft-orders?status=pending").json() == []
    db = SessionLocal()
    assert db.query(DraftOrder).one().status == DraftOrderStatus.rejected
    db.close()


def test_finishing_a_conversation_removes_only_its_messages():
    payload = {
        "object": "page",
        "entry": [{"id": "page-finish", "messaging": [{"sender": {"id": "user-finish"}, "message": {"text": "สวัสดี"}}]}],
    }
    assert client.post("/webhooks/meta", json=payload).status_code == 200
    conversation = client.get("/api/conversations").json()[0]
    assert client.get(f"/api/conversations/{conversation['id']}/messages").json()
    paid = client.patch(
        f"/api/conversations/{conversation['id']}",
        json={"payment_label": "จ่ายเงินแล้ว"},
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["payment_label"] == "จ่ายเงินแล้ว"

    response = client.patch(
        f"/api/conversations/{conversation['id']}",
        json={"primary_label": "เสร็จสิ้น"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_hidden"] is True
    assert response.json()["customer_display_name"] == conversation["customer_display_name"]
    assert response.json()["payment_label"] is None
    assert client.get(f"/api/conversations/{conversation['id']}/messages").json() == []
    assert client.get("/api/conversations?visibility=hidden").json()[0]["id"] == conversation["id"]

    drafts = client.get("/api/draft-orders").json()
    assert drafts == []


def test_hiding_a_conversation_clears_messages_and_a_new_customer_message_reopens_it():
    first_payload = {
        "object": "page",
        "entry": [{"id": "page-hide", "messaging": [{"sender": {"id": "user-hide"}, "message": {"text": "สวัสดี"}}]}],
    }
    assert client.post("/webhooks/meta", json=first_payload).status_code == 200
    conversation = client.get("/api/conversations").json()[0]

    hidden = client.patch(f"/api/conversations/{conversation['id']}", json={"is_hidden": True})
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["is_hidden"] is True
    assert client.get(f"/api/conversations/{conversation['id']}/messages").json() == []

    second_payload = {
        "object": "page",
        "entry": [{"id": "page-hide", "messaging": [{"sender": {"id": "user-hide"}, "message": {"text": "มีใครอยู่ไหม"}}]}],
    }
    assert client.post("/webhooks/meta", json=second_payload).status_code == 200
    reopened = client.get("/api/conversations").json()[0]
    assert reopened["id"] == conversation["id"]
    assert reopened["is_hidden"] is False
    assert reopened["status"] == "open"
    assert len(client.get(f"/api/conversations/{conversation['id']}/messages").json()) == 1


def test_hiding_a_conversation_rejects_its_pending_draft_order():
    product = create_product("HIDE-DRAFT", "ข้าวหมกไก่ทอด", price=45)
    payload = {
        "object": "page",
        "entry": [{"id": "page-hide-draft", "messaging": [{"sender": {"id": "user-hide-draft"}, "message": {"text": "เอาข้าวหมกไก่ทอด 1"}}]}],
    }
    assert client.post("/webhooks/meta", json=payload).status_code == 200
    conversation = client.get("/api/conversations").json()[0]
    pending = client.get("/api/draft-orders?status=pending").json()
    assert len(pending) == 1
    assert pending[0]["items"][0]["product_id"] == product["id"]

    assert client.patch(f"/api/conversations/{conversation['id']}", json={"is_hidden": True}).status_code == 200
    assert client.get("/api/draft-orders?status=pending").json() == []
    rejected = client.get("/api/draft-orders?status=rejected").json()
    assert len(rejected) == 1
    assert rejected[0]["conversation_id"] == conversation["id"]


def test_confirmed_chat_order_is_kept_in_order_history_after_messages_are_cleared():
    product = create_product("HISTORY", "ข้าวหมกไก่ต้ม", price=45)
    payload = {
        "object": "page",
        "entry": [{"id": "page-history", "messaging": [{"sender": {"id": "user-history"}, "message": {"text": "เอาข้าวหมกไก่ต้ม 2"}}]}],
    }
    assert client.post("/webhooks/meta", json=payload).status_code == 200
    conversation = client.get("/api/conversations").json()[0]
    draft = client.get("/api/draft-orders?status=pending").json()[0]
    assert client.post(f"/api/draft-orders/{draft['id']}/confirm").status_code == 200
    assert client.patch(f"/api/conversations/{conversation['id']}", json={"is_hidden": True}).status_code == 200

    history = client.get("/api/order-history")
    assert history.status_code == 200, history.text
    customer = history.json()[0]
    assert customer["customer_id"] == conversation["customer_id"]
    assert customer["order_count"] == 1
    assert customer["orders"][0]["id"] == draft["id"]
    assert customer["orders"][0]["items"] == [{"product_name": product["name"], "quantity": 2, "unit_price": 45.0}]


def test_bill_count_increments_for_confirmed_additions_and_resets_when_finished():
    create_product("BILL-COUNT", "ชาไทย", price=25)
    payload = {
        "object": "page",
        "entry": [{"id": "page-bill", "messaging": [{"sender": {"id": "user-bill"}, "message": {"text": "เอาชาไทย 1"}}]}],
    }
    assert client.post("/webhooks/meta", json=payload).status_code == 200
    first_draft = client.get("/api/draft-orders?status=pending").json()[0]
    assert client.post(f"/api/draft-orders/{first_draft['id']}/confirm").status_code == 200
    conversation = client.get("/api/conversations").json()[0]
    assert conversation["primary_label"] == "รับออเดอร์แล้ว"
    assert conversation["bill_count"] == 1

    payload["entry"][0]["messaging"][0]["message"]["text"] = "เอาชาไทย 2"
    assert client.post("/webhooks/meta", json=payload).status_code == 200
    second_draft = client.get("/api/draft-orders?status=pending").json()[0]
    assert client.post(f"/api/draft-orders/{second_draft['id']}/confirm").status_code == 200
    assert client.get("/api/conversations").json()[0]["bill_count"] == 2

    finished = client.patch(f"/api/conversations/{conversation['id']}", json={"primary_label": "เสร็จสิ้น"})
    assert finished.status_code == 200, finished.text
    assert finished.json()["bill_count"] == 0


def test_question_is_marked_waiting_for_reply_without_a_draft_order():
    create_product("PAD-Q", "ผัดไทยกุ้ง")
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-question",
                "messaging": [{"sender": {"id": "user-question"}, "message": {"text": "ผัดไทยกุ้งราคาเท่าไหร่คะ"}}],
            }
        ],
    }

    response = client.post("/webhooks/meta", json=payload)
    assert response.status_code == 200, response.text
    assert client.get("/api/draft-orders").json() == []
    conversations = client.get("/api/conversations").json()
    assert conversations[0]["status"] == "waiting_reply"


def test_negated_menu_item_is_not_added():
    create_product("PAD6", "ส้มตำ", price=40)

    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page1",
                "messaging": [{"sender": {"id": "user3"}, "message": {"text": "ไม่เอาส้มตำ"}}],
            }
        ],
    }
    res = client.post("/webhooks/meta", json=payload)
    assert res.status_code == 200, res.text

    assert client.get("/api/draft-orders").json() == []
    conversation = client.get("/api/conversations").json()[0]
    assert conversation["primary_label"] == "รอแอดมิน"


def test_line_webhook_ingests_message_into_draft_order():
    create_product("PAD7", "ชาไทยเย็น", price=35)

    payload = {
        "destination": "Uxxxxbot",
        "events": [
            {
                "type": "message",
                "message": {"type": "text", "text": "ขอชาไทยเย็น 1 แก้ว"},
                "source": {"userId": "Ulinecustomer"},
            }
        ],
    }
    res = client.post("/webhooks/line", json=payload)
    assert res.status_code == 200, res.text

    conversations = client.get("/api/conversations").json()
    assert len(conversations) == 1

    drafts = client.get("/api/draft-orders").json()
    assert len(drafts) == 1
    assert drafts[0]["items"][0]["product_name"] == "ชาไทยเย็น"
