import os

os.environ["DATABASE_URL"] = "sqlite:///./test_loyalty.db"

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
    client.put(
        "/api/settings",
        json={"shop_type": "individual", "shop_name": "ร้านทดสอบ", "loyalty_baht_per_point": 100},
    )
    client.post("/api/shifts/open", json={"opening_cash": 0})
    yield
    Base.metadata.drop_all(bind=engine)


def create_product(sku="SKU1", price=100, stock=10):
    res = client.post("/api/products", json={"sku": sku, "name": "สินค้าทดสอบ", "price": price, "low_stock_threshold": 1})
    product = res.json()
    client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": stock, "note": "initial"})
    return product


def test_checkout_with_new_customer_creates_customer_and_earns_points():
    create_product(price=250)
    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 1})

    checkout = client.post(
        f"/api/pos/sales/{sale['id']}/checkout",
        json={"payments": [{"method": "cash", "amount": 250}], "customer_phone": "0811111111", "customer_name": "สมชาย"},
    )
    assert checkout.status_code == 200, checkout.text
    body = checkout.json()
    assert body["customer_phone"] == "0811111111"
    assert body["points_earned"] == 2  # floor(250 / 100)
    assert body["customer_points_balance"] == 2

    customer = client.get("/api/customers/lookup?phone=0811111111").json()
    assert customer["points"] == 2
    assert customer["name"] == "สมชาย"


def test_redeem_points_discounts_total_and_requires_sufficient_balance():
    create_product(price=300)
    client.post("/api/customers", json={"phone": "0822222222", "name": "สมหญิง"})

    db = SessionLocal()
    from app.models import LoyaltyCustomer

    customer = db.query(LoyaltyCustomer).filter(LoyaltyCustomer.phone == "0822222222").first()
    customer.points = 50
    db.commit()
    db.close()

    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 1})

    too_much = client.post(
        f"/api/pos/sales/{sale['id']}/checkout",
        json={"payments": [{"method": "cash", "amount": 300}], "customer_phone": "0822222222", "redeem_points": 999},
    )
    assert too_much.status_code == 400

    checkout = client.post(
        f"/api/pos/sales/{sale['id']}/checkout",
        json={"payments": [{"method": "cash", "amount": 250}], "customer_phone": "0822222222", "redeem_points": 50},
    )
    assert checkout.status_code == 200, checkout.text
    body = checkout.json()
    assert body["points_redeemed"] == 50
    assert body["change_amount"] == 0

    customer_after = client.get("/api/customers/lookup?phone=0822222222").json()
    # 50 (initial) - 50 (redeemed) + floor(250 baht due / 100) earned = 2
    assert customer_after["points"] == 2
