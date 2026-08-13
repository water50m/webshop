import os

os.environ["DATABASE_URL"] = "sqlite:///./test_suppliers_po.db"

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
    db.add(User(username="cashier", password_hash=hash_password("cashierpass"), display_name="Cashier", role=UserRole.cashier))
    db.commit()
    db.close()
    login = client.post("/api/auth/login", json={"username": "owner", "password": "ownerpass"})
    assert login.status_code == 200, login.text
    yield
    Base.metadata.drop_all(bind=engine)


def create_product(sku="SKU1", price=100, stock=0, cost_price=0):
    res = client.post(
        "/api/products",
        json={"sku": sku, "name": "สินค้าทดสอบ", "price": price, "cost_price": cost_price, "low_stock_threshold": 1},
    )
    product = res.json()
    if stock:
        client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": stock, "note": "initial"})
    return product


def test_create_supplier_and_purchase_order():
    supplier = client.post("/api/suppliers", json={"name": "ซัพพลายเออร์ A", "phone": "021234567"}).json()
    product = create_product(cost_price=5)

    po = client.post(
        "/api/purchase-orders",
        json={"supplier_id": supplier["id"], "items": [{"product_id": product["id"], "quantity": 20, "unit_cost": 8}]},
    )
    assert po.status_code == 200, po.text
    assert po.json()["status"] == "draft"
    assert po.json()["total_cost"] == 160


def test_receiving_po_increases_stock_and_updates_cost_price():
    supplier = client.post("/api/suppliers", json={"name": "ซัพพลายเออร์ B"}).json()
    product = create_product(cost_price=5)

    po = client.post(
        "/api/purchase-orders",
        json={"supplier_id": supplier["id"], "items": [{"product_id": product["id"], "quantity": 30, "unit_cost": 9.5}]},
    ).json()

    receive = client.post(f"/api/purchase-orders/{po['id']}/receive")
    assert receive.status_code == 200, receive.text
    assert receive.json()["status"] == "received"

    updated_product = client.get(f"/api/products/lookup?code=SKU1").json()
    assert updated_product["stock_quantity"] == 30
    assert updated_product["cost_price"] == 9.5

    again = client.post(f"/api/purchase-orders/{po['id']}/receive")
    assert again.status_code == 400


def test_cancel_po_blocked_after_received():
    supplier = client.post("/api/suppliers", json={"name": "ซัพพลายเออร์ C"}).json()
    product = create_product()
    po = client.post(
        "/api/purchase-orders",
        json={"supplier_id": supplier["id"], "items": [{"product_id": product["id"], "quantity": 5, "unit_cost": 1}]},
    ).json()
    client.post(f"/api/purchase-orders/{po['id']}/receive")
    cancel = client.post(f"/api/purchase-orders/{po['id']}/cancel")
    assert cancel.status_code == 400


def test_cashier_cannot_create_supplier_or_po():
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "cashier", "password": "cashierpass"})
    res = client.post("/api/suppliers", json={"name": "ไม่มีสิทธิ์"})
    assert res.status_code == 403
