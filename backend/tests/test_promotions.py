import os
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_promotions.db"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User, UserRole
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


def create_product(sku, name, price, stock=100):
    res = client.post("/api/products", json={"sku": sku, "name": name, "price": price, "low_stock_threshold": 1})
    assert res.status_code == 200, res.text
    product = res.json()
    client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": stock, "note": "initial"})
    return product


def iso(dt):
    return dt.isoformat()


def test_time_discount_applies_within_window_and_shows_on_product():
    product = create_product("A1", "สินค้า A", 100)
    now = datetime.utcnow()
    promo = client.post(
        "/api/promotions",
        json={
            "name": "ลด 20%",
            "type": "time_discount",
            "discount_type": "percent",
            "discount_value": 20,
            "start_at": iso(now - timedelta(hours=1)),
            "end_at": iso(now + timedelta(hours=1)),
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert promo.status_code == 200, promo.text
    assert promo.json()["is_active_now"] is True

    after = client.get("/api/products/lookup?code=A1").json()
    assert after["discounted_price"] == 80.0

    sale = client.post("/api/pos/sales").json()
    add = client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "A1", "quantity": 2}).json()
    assert add["items"][0]["unit_price"] == 80.0
    assert add["subtotal"] == 160.0


def test_time_discount_outside_window_not_applied():
    product = create_product("A2", "สินค้า A2", 50)
    now = datetime.utcnow()
    client.post(
        "/api/promotions",
        json={
            "name": "โปรหมดอายุ",
            "type": "time_discount",
            "discount_type": "amount",
            "discount_value": 10,
            "start_at": iso(now - timedelta(days=2)),
            "end_at": iso(now - timedelta(days=1)),
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    after = client.get("/api/products/lookup?code=A2").json()
    assert after["discounted_price"] is None


def test_inactive_promotion_not_applied():
    product = create_product("A3", "สินค้า A3", 50)
    promo = client.post(
        "/api/promotions",
        json={
            "name": "โปรปิดใช้งาน",
            "type": "time_discount",
            "is_active": False,
            "discount_type": "amount",
            "discount_value": 5,
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    ).json()
    assert promo["is_active_now"] is False
    after = client.get("/api/products/lookup?code=A3").json()
    assert after["discounted_price"] is None


def test_bundle_discount_applied_when_set_complete():
    product_a = create_product("B1", "สินค้า B1", 100)
    product_b = create_product("B2", "สินค้า B2", 50)

    promo = client.post(
        "/api/promotions",
        json={
            "name": "ซื้อคู่กัน",
            "type": "bundle",
            "bundle_price": 120,
            "items": [
                {"product_id": product_a["id"], "quantity": 1},
                {"product_id": product_b["id"], "quantity": 1},
            ],
        },
    )
    assert promo.status_code == 200, promo.text

    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "B1", "quantity": 1})
    cart = client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "B2", "quantity": 1}).json()

    assert cart["subtotal"] == 150.0
    assert cart["promotion_discount"] == 30.0
    assert cart["total"] == 120.0


def test_bundle_discount_scales_with_multiple_sets():
    product_a = create_product("C1", "สินค้า C1", 100)
    product_b = create_product("C2", "สินค้า C2", 50)

    client.post(
        "/api/promotions",
        json={
            "name": "ซื้อคู่กัน 2",
            "type": "bundle",
            "bundle_price": 120,
            "items": [
                {"product_id": product_a["id"], "quantity": 1},
                {"product_id": product_b["id"], "quantity": 1},
            ],
        },
    )

    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "C1", "quantity": 2})
    cart = client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "C2", "quantity": 2}).json()

    assert cart["subtotal"] == 300.0
    assert cart["promotion_discount"] == 60.0
    assert cart["total"] == 240.0


def test_toggle_promotion_disables_it():
    product = create_product("D1", "สินค้า D1", 50)
    promo = client.post(
        "/api/promotions",
        json={
            "name": "โปรทดสอบ toggle",
            "type": "time_discount",
            "discount_type": "amount",
            "discount_value": 5,
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    ).json()

    before = client.get("/api/products/lookup?code=D1").json()
    assert before["discounted_price"] == 45.0

    toggled = client.post(f"/api/promotions/{promo['id']}/toggle").json()
    assert toggled["is_active"] is False

    after = client.get("/api/products/lookup?code=D1").json()
    assert after["discounted_price"] is None
