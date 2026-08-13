import os

os.environ["DATABASE_URL"] = "sqlite:///./test_line_notify.db"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User, UserRole
from app.services import line_notify
from app.services.auth import hash_password

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(User(username="owner", password_hash=hash_password("ownerpass"), display_name="Owner", role=UserRole.owner))
    db.commit()
    db.close()
    login = client.post("/api/auth/login", json={"username": "owner", "password": "ownerpass"})
    assert login.status_code == 200, login.text
    yield
    Base.metadata.drop_all(bind=engine)


def test_test_line_notify_fails_without_token_configured():
    res = client.post("/api/settings/test-line-notify")
    assert res.status_code == 400
    assert "LINE" in res.json()["detail"]


def test_test_line_notify_succeeds_when_configured(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "ok"

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(line_notify.httpx, "post", fake_post)

    client.put(
        "/api/settings",
        json={
            "shop_type": "individual",
            "shop_name": "ร้านทดสอบ",
            "low_stock_line_token": "fake-token",
            "low_stock_line_target_id": "Uxxxxxx",
        },
    )
    res = client.post("/api/settings/test-line-notify")
    assert res.status_code == 200, res.text
    assert res.json()["ok"] is True
    assert captured["headers"]["Authorization"] == "Bearer fake-token"
    assert captured["json"]["to"] == "Uxxxxxx"


def test_build_low_stock_message_lists_products():
    from app.models import Product

    db = SessionLocal()
    Base.metadata.create_all(bind=engine)
    product = Product(sku="SKU1", name="สินค้า A", price=10, stock_quantity=1, low_stock_threshold=5)
    db.add(product)
    db.commit()
    message = line_notify.build_low_stock_message([product])
    assert "สินค้า A" in message
    assert "เหลือ 1" in message
    db.close()
