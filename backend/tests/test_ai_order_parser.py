import json
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_ai_order_parser.db"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User, UserRole
from app.services import ai_order_parser, message_ingest
from app.services.auth import hash_password
from app.config import settings

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
    monkeypatch.setattr(settings, "meta_page_access_token", "")
    yield
    Base.metadata.drop_all(bind=engine)


def create_product(sku, name, price=50):
    res = client.post("/api/products", json={"sku": sku, "name": name, "price": price})
    assert res.status_code == 200, res.text
    product = res.json()
    stock = client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": 10, "note": "test stock"})
    assert stock.status_code == 200, stock.text
    return stock.json()


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


def _claude_response(classification, items):
    return FakeResponse(
        200,
        {"content": [{"text": json.dumps({"classification": classification, "items": items})}]},
    )


def test_settings_persist_order_parser_mode_and_api_key():
    res = client.put(
        "/api/settings",
        json={"shop_type": "individual", "order_parser_mode": "ai", "ai_api_key": "sk-ant-test"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["order_parser_mode"] == "ai"
    assert body["ai_api_key"] == "sk-ant-test"

    res2 = client.get("/api/settings")
    assert res2.json()["order_parser_mode"] == "ai"


def test_parse_order_with_ai_maps_catalog_names_to_matches(monkeypatch):
    product = create_product("PAD1", "ผัดไทยกุ้ง", price=60)
    client.post(f"/api/products/{product['id']}/modifiers", json={"name": "ถั่ว", "price_delta": 0})

    def fake_post(url, headers=None, json=None, timeout=None):
        return _claude_response(
            "order",
            [
                {"name": "ผัดไทยกุ้ง", "quantity": 2, "negated": False},
                {"name": "ถั่ว", "quantity": 1, "negated": True},
            ],
        )

    monkeypatch.setattr(ai_order_parser.httpx, "post", fake_post)

    db = SessionLocal()
    classification, matches = ai_order_parser.parse_order_with_ai(db, "ขอผัดไทยกุ้ง 2 จาน ไม่ใส่ถั่ว", "sk-ant-test")
    db.close()

    assert classification == "order"
    product_matches = [m for m in matches if m.term.kind == "product"]
    modifier_matches = [m for m in matches if m.term.kind == "modifier"]
    assert len(product_matches) == 2  # quantity 2 -> repeated match
    assert all(m.term.name == "ผัดไทยกุ้ง" and not m.negated for m in product_matches)
    assert len(modifier_matches) == 1
    assert modifier_matches[0].negated is True


def test_parse_order_with_ai_skips_hallucinated_names(monkeypatch):
    create_product("PAD2", "ผัดไทยกุ้ง", price=60)

    def fake_post(url, headers=None, json=None, timeout=None):
        return _claude_response("order", [{"name": "เมนูที่ไม่มีอยู่จริง", "quantity": 1, "negated": False}])

    monkeypatch.setattr(ai_order_parser.httpx, "post", fake_post)

    db = SessionLocal()
    classification, matches = ai_order_parser.parse_order_with_ai(db, "ขอเมนูที่ไม่มีอยู่จริง", "sk-ant-test")
    db.close()

    assert classification == "order"
    assert matches == []


def test_parse_order_with_ai_raises_without_api_key():
    db = SessionLocal()
    with pytest.raises(ai_order_parser.AiOrderParserError):
        ai_order_parser.parse_order_with_ai(db, "ขอส้มตำ", "")
    db.close()


def test_parse_order_with_ai_raises_on_http_error(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(500, {"error": "boom"})

    monkeypatch.setattr(ai_order_parser.httpx, "post", fake_post)

    db = SessionLocal()
    with pytest.raises(ai_order_parser.AiOrderParserError):
        ai_order_parser.parse_order_with_ai(db, "ขอส้มตำ", "sk-ant-test")
    db.close()


# --- ingest-level: mode selection + fallback ---


def test_ingest_uses_ai_parser_when_mode_is_ai(monkeypatch):
    create_product("PAD3", "ผัดไทยกุ้ง", price=60)
    client.put("/api/settings", json={"shop_type": "individual", "order_parser_mode": "ai", "ai_api_key": "sk-ant-test"})

    def fake_post(url, headers=None, json=None, timeout=None):
        return _claude_response("order", [{"name": "ผัดไทยกุ้ง", "quantity": 1, "negated": False}])

    monkeypatch.setattr(ai_order_parser.httpx, "post", fake_post)

    payload = {
        "object": "page",
        "entry": [{"id": "page1", "messaging": [{"sender": {"id": "u1"}, "message": {"text": "ขอผัดไทยกุ้ง"}}]}],
    }
    res = client.post("/webhooks/meta", json=payload)
    assert res.status_code == 200, res.text

    drafts = client.get("/api/draft-orders").json()
    assert len(drafts) == 1
    assert drafts[0]["items"][0]["product_name"] == "ผัดไทยกุ้ง"


def test_ingest_falls_back_to_algorithm_when_ai_call_fails(monkeypatch):
    create_product("PAD4", "ส้มตำ", price=40)
    client.put("/api/settings", json={"shop_type": "individual", "order_parser_mode": "ai", "ai_api_key": "sk-ant-test"})

    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(500, {"error": "boom"})

    monkeypatch.setattr(ai_order_parser.httpx, "post", fake_post)

    payload = {
        "object": "page",
        "entry": [{"id": "page1", "messaging": [{"sender": {"id": "u2"}, "message": {"text": "ขอส้มตำ"}}]}],
    }
    res = client.post("/webhooks/meta", json=payload)
    assert res.status_code == 200, res.text

    # AI call failed -> message_ingest should have fallen back to the
    # algorithmic parser, which can still match "ส้มตำ" by substring.
    drafts = client.get("/api/draft-orders").json()
    assert len(drafts) == 1
    assert drafts[0]["items"][0]["product_name"] == "ส้มตำ"


def test_ingest_uses_algorithm_directly_when_mode_is_algorithm():
    create_product("PAD5", "ส้มตำ", price=40)
    # default mode is "algorithm" -- no settings change needed.
    payload = {
        "object": "page",
        "entry": [{"id": "page1", "messaging": [{"sender": {"id": "u3"}, "message": {"text": "ขอส้มตำ"}}]}],
    }
    res = client.post("/webhooks/meta", json=payload)
    assert res.status_code == 200, res.text

    drafts = client.get("/api/draft-orders").json()
    assert len(drafts) == 1


def test_resolve_order_matches_used_directly():
    create_product("PAD6", "ส้มตำ", price=40)
    db = SessionLocal()
    matches = message_ingest.resolve_order_matches(db, "สวัสดีค่ะ")
    db.close()
    assert matches == []


def test_question_does_not_call_ai_and_is_marked_waiting_for_reply(monkeypatch):
    client.put("/api/settings", json={"shop_type": "individual", "order_parser_mode": "ai", "ai_api_key": "sk-ant-test"})

    def fail_if_called(*args, **kwargs):
        raise AssertionError("AI must not be called for a customer question")

    monkeypatch.setattr(ai_order_parser.httpx, "post", fail_if_called)
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-question",
                "messaging": [{"sender": {"id": "u-question"}, "message": {"text": "เปิดกี่โมงคะ"}}],
            }
        ],
    }

    response = client.post("/webhooks/meta", json=payload)
    assert response.status_code == 200, response.text
    assert client.get("/api/draft-orders").json() == []
    assert client.get("/api/conversations").json()[0]["status"] == "waiting_reply"
