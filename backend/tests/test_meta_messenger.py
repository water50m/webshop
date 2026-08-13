import os

os.environ["DATABASE_URL"] = "sqlite:///./test_meta_messenger.db"

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Product, ShopSettings, User, UserRole
from app.services import message_ingest, meta_messenger
from app.services.auth import hash_password

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(User(username="owner", password_hash=hash_password("ownerpass"), role=UserRole.owner))
    db.commit()
    db.close()
    login = client.post("/api/auth/login", json={"username": "owner", "password": "ownerpass"})
    assert login.status_code == 200, login.text
    monkeypatch.setattr(settings, "meta_app_secret", "")
    monkeypatch.setattr(settings, "meta_page_access_token", "page-token")
    monkeypatch.setattr(message_ingest, "populate_messenger_display_name", lambda customer: None)
    yield
    Base.metadata.drop_all(bind=engine)


def create_product(sku, name, price=50, image_url=None, stock_quantity=10):
    response = client.post(
        "/api/products",
        json={"sku": sku, "name": name, "price": price, "image_url": image_url},
    )
    assert response.status_code == 200, response.text
    product = response.json()
    if stock_quantity:
        adjustment = client.post(
            f"/api/products/{product['id']}/stock-adjustment",
            json={"change": stock_quantity, "note": "test stock"},
        )
        assert adjustment.status_code == 200, adjustment.text
        product = adjustment.json()
    return product


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"recipient_id": "customer-1", "message_id": "mid.1"}


def test_greeting_sends_plain_text_without_order_buttons(monkeypatch):
    create_product("KHAO-MOK", "ข้าวหมก", 20)
    requests = []

    def fake_post(url, *, params, json, timeout):
        requests.append({"url": url, "params": params, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(meta_messenger.httpx, "post", fake_post)
    webhook = {
        "object": "page",
        "entry": [
            {
                "id": "page-1",
                "messaging": [{"sender": {"id": "customer-1"}, "message": {"text": "สวัสดีค่ะ"}}],
            }
        ],
    }

    response = client.post("/webhooks/meta", json=webhook)
    assert response.status_code == 200, response.text
    assert [request["json"]["message"] for request in requests] == [{"text": "สวัสดีครับ รับอะไรดีครับ"}]
    assert client.get("/api/draft-orders").json() == []


def test_menu_question_uses_only_selected_in_stock_products(monkeypatch):
    visible = create_product("VISIBLE", "ข้าวหมกไก่ทอด", 45)
    hidden = create_product("HIDDEN", "น้ำอัดลม", 25)
    db = SessionLocal()
    db.get(Product, hidden["id"]).show_in_menu_answer = False
    db.commit()
    db.close()
    sent_messages = []

    def fake_post(url, *, params, json, timeout):
        sent_messages.append(json["message"])
        return FakeResponse()

    monkeypatch.setattr(meta_messenger.httpx, "post", fake_post)
    webhook = {"object": "page", "entry": [{"id": "page-1", "messaging": [{"sender": {"id": "customer-1"}, "message": {"text": "มีเมนูอะไรบ้าง"}}]}]}
    assert client.post("/webhooks/meta", json=webhook).status_code == 200
    assert sent_messages == [{"text": f"ขณะนี้มี: {visible['name']}"}]


def test_remaining_menu_question_is_answered_from_the_selected_catalog(monkeypatch):
    visible = create_product("REMAINING", "ข้าวหมกไก่ต้ม", 45)
    sent_messages = []

    def fake_post(url, *, params, json, timeout):
        sent_messages.append(json["message"])
        return FakeResponse()

    monkeypatch.setattr(meta_messenger.httpx, "post", fake_post)
    webhook = {"object": "page", "entry": [{"id": "page-1", "messaging": [{"sender": {"id": "customer-1"}, "message": {"text": "เหลืออะไรบ้าง"}}]}]}
    assert client.post("/webhooks/meta", json=webhook).status_code == 200
    assert sent_messages == [{"text": f"ขณะนี้มี: {visible['name']}"}]


def test_menu_question_can_send_a_generated_menu_image(monkeypatch):
    create_product("MENU-IMAGE", "ข้าวหมกไก่ทอด", 45)
    db = SessionLocal()
    db.add(ShopSettings(id=1, shop_name="ร้านทดสอบ", menu_answer_format="image"))
    db.commit()
    db.close()
    sent_images = []

    def fake_send_image(page_id, recipient_id, image, filename):
        sent_images.append((page_id, recipient_id, image, filename))
        return {"message_id": "image.1"}

    monkeypatch.setattr(meta_messenger, "_send_image", fake_send_image)
    webhook = {"object": "page", "entry": [{"id": "page-1", "messaging": [{"sender": {"id": "customer-1"}, "message": {"text": "มีเมนูอะไรบ้าง"}}]}]}
    assert client.post("/webhooks/meta", json=webhook).status_code == 200
    assert len(sent_images) == 1
    assert sent_images[0][2].startswith(b"\x89PNG")
    assert sent_images[0][3] == "menu-answer.png"


def test_product_postback_adds_draft_order_and_confirms_to_customer(monkeypatch):
    product = create_product("TEA1", "ชาไทยเย็น", 35)
    sent_messages = []

    def fake_post(url, *, params, json, timeout):
        sent_messages.append(json["message"])
        return FakeResponse()

    monkeypatch.setattr(meta_messenger.httpx, "post", fake_post)
    webhook = {
        "object": "page",
        "entry": [
            {
                "id": "page-1",
                "messaging": [
                    {
                        "sender": {"id": "customer-1"},
                        "postback": {"payload": f"ORDER_PRODUCT:{product['id']}"},
                    }
                ],
            }
        ],
    }

    response = client.post("/webhooks/meta", json=webhook)
    assert response.status_code == 200, response.text
    assert sent_messages == [{"text": "รับรายการ: ชาไทยเย็น ราคา ฿35.00 แล้วค่ะ"}]

    drafts = client.get("/api/draft-orders").json()
    assert len(drafts) == 1
    assert drafts[0]["items"][0]["product_id"] == product["id"]
    assert drafts[0]["items"][0]["quantity"] == 1


def test_staff_confirmation_sends_order_summary_to_messenger(monkeypatch):
    product = create_product("TEA2", "ชาไทยเย็น", 35)
    sent_messages = []

    def fake_post(url, *, params, json, timeout):
        sent_messages.append(json["message"])
        return FakeResponse()

    monkeypatch.setattr(meta_messenger.httpx, "post", fake_post)
    webhook = {
        "object": "page",
        "entry": [
            {
                "id": "page-1",
                "messaging": [
                    {
                        "sender": {"id": "customer-1"},
                        "message": {"text": "ขอชาไทยเย็น"},
                    }
                ],
            }
        ],
    }
    assert client.post("/webhooks/meta", json=webhook).status_code == 200

    draft = client.get("/api/draft-orders").json()[0]
    response = client.post(f"/api/draft-orders/{draft['id']}/confirm")
    assert response.status_code == 200, response.text
    assert sent_messages == [
        {"text": "ได้รับรายการแล้ว กำลังตรวจสอบก่อนยืนยันครับ"},
        {
            "text": (
                "รับออเดอร์เรียบร้อยครับ\n"
                "รายการ:\n"
                "• ชาไทยเย็น x 1 — ฿35.00\n"
                "รวมทั้งหมด ฿35.00\n"
                "ขอบคุณค่ะ"
            )
        }
    ]


def test_repeated_order_message_does_not_increase_the_pending_draft(monkeypatch):
    product = create_product("NO-DOUBLE", "ข้าวหมกไก่ทอด", 45)
    sent_messages = []

    def fake_post(url, *, params, json, timeout):
        sent_messages.append(json["message"])
        return FakeResponse()

    monkeypatch.setattr(meta_messenger.httpx, "post", fake_post)
    webhook = {
        "object": "page",
        "entry": [{"id": "page-1", "messaging": [{"sender": {"id": "customer-1"}, "message": {"text": "เอาข้าวหมกไก่ทอด 1"}}]}],
    }
    assert client.post("/webhooks/meta", json=webhook).status_code == 200
    assert client.post("/webhooks/meta", json=webhook).status_code == 200

    drafts = client.get("/api/draft-orders").json()
    assert len(drafts) == 1
    assert len(drafts[0]["items"]) == 1
    assert drafts[0]["items"][0]["product_id"] == product["id"]
    assert drafts[0]["items"][0]["quantity"] == 1
    assert sent_messages == [{"text": "ได้รับรายการแล้ว กำลังตรวจสอบก่อนยืนยันครับ"}]


def test_verified_stock_answer_is_sent_at_most_twice_and_never_creates_a_draft(monkeypatch):
    create_product("FRIED-SET", "ข้าวหมกไก่ทอด", 45)
    sent_messages = []

    def fake_post(url, *, params, json, timeout):
        sent_messages.append(json["message"])
        return FakeResponse()

    monkeypatch.setattr(meta_messenger.httpx, "post", fake_post)
    webhook = {
        "object": "page",
        "entry": [{"id": "page-1", "messaging": [{"sender": {"id": "customer-1"}, "message": {"text": "ข้าวหมกไก่ทอดยังมีไหม"}}]}],
    }

    assert client.post("/webhooks/meta", json=webhook).status_code == 200
    assert client.post("/webhooks/meta", json=webhook).status_code == 200
    assert client.post("/webhooks/meta", json=webhook).status_code == 200

    assert sent_messages == [
        {"text": "ขณะนี้มีข้าวหมกไก่ทอดครับ"},
        {"text": "ขณะนี้มีข้าวหมกไก่ทอดครับ"},
    ]
    assert client.get("/api/draft-orders").json() == []


def test_question_that_requires_an_admin_gets_a_receipt_but_not_a_made_up_answer(monkeypatch):
    sent_messages = []

    def fake_post(url, *, params, json, timeout):
        sent_messages.append(json["message"])
        return FakeResponse()

    monkeypatch.setattr(meta_messenger.httpx, "post", fake_post)
    webhook = {
        "object": "page",
        "entry": [{"id": "page-1", "messaging": [{"sender": {"id": "customer-1"}, "message": {"text": "ร้านเปิดกี่โมงหรอ"}}]}],
    }

    assert client.post("/webhooks/meta", json=webhook).status_code == 200
    assert sent_messages == [{"text": "ได้รับข้อความแล้ว แอดมินกำลังตรวจสอบให้ครับ"}]
    conversation = client.get("/api/conversations").json()[0]
    assert conversation["primary_label"] == "รอแอดมิน"
