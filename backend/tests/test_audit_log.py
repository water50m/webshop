import os

os.environ["DATABASE_URL"] = "sqlite:///./test_audit_log.db"

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
    shift = client.post("/api/shifts/open", json={"opening_cash": 0})
    assert shift.status_code == 200, shift.text
    yield
    Base.metadata.drop_all(bind=engine)


def login_as(username, password):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text


def create_product(sku="SKU1", price=100, stock=10):
    res = client.post("/api/products", json={"sku": sku, "name": "สินค้าทดสอบ", "price": price})
    assert res.status_code == 200, res.text
    product = res.json()
    adj = client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": stock, "note": "initial"})
    assert adj.status_code == 200, adj.text
    return adj.json()


def complete_a_sale(product, quantity=2):
    sale = client.post("/api/pos/sales").json()
    add = client.post(f"/api/pos/sales/{sale['id']}/items", json={"product_id": product["id"], "quantity": quantity}).json()
    item_id = add["items"][0]["id"]
    checkout = client.post(
        f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "cash", "amount": quantity * float(product["price"])}]}
    )
    assert checkout.status_code == 200, checkout.text
    return checkout.json(), item_id


def test_void_completed_sale_creates_audit_log():
    product = create_product()
    sale, _ = complete_a_sale(product)
    void = client.post(f"/api/pos/sales/{sale['id']}/void", json={"note": "ลูกค้าเปลี่ยนใจ"})
    assert void.status_code == 200, void.text

    logs = client.get("/api/audit/sales").json()
    assert len(logs) == 1
    assert logs[0]["action"] == "void"
    assert logs[0]["sale_id"] == sale["id"]
    assert logs[0]["user_name"] == "Owner"
    assert logs[0]["note"] == "ลูกค้าเปลี่ยนใจ"


def test_refund_creates_audit_log():
    product = create_product()
    sale, item_id = complete_a_sale(product)
    refund = client.post(
        f"/api/pos/sales/{sale['id']}/refund", json={"items": [{"item_id": item_id, "quantity": 1}], "note": "สินค้าชำรุด"}
    )
    assert refund.status_code == 200, refund.text

    logs = client.get("/api/audit/sales").json()
    assert len(logs) == 1
    assert logs[0]["action"] == "refund"
    assert logs[0]["note"] == "สินค้าชำรุด"


def test_voiding_held_bill_does_not_create_audit_log():
    product = create_product()
    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"product_id": product["id"], "quantity": 1})
    void = client.post(f"/api/pos/sales/{sale['id']}/void")
    assert void.status_code == 200, void.text

    logs = client.get("/api/audit/sales").json()
    assert logs == []


def test_cashier_cannot_view_audit_log():
    client.post("/api/users", json={"username": "cashier1", "password": "pass1234", "role": "cashier"})
    login_as("cashier1", "pass1234")
    res = client.get("/api/audit/sales")
    assert res.status_code == 403


def test_audit_log_date_filter():
    product = create_product()
    sale, _ = complete_a_sale(product)
    client.post(f"/api/pos/sales/{sale['id']}/void")

    from datetime import datetime, timedelta

    future_start = (datetime.utcnow() + timedelta(days=1)).isoformat()
    logs = client.get(f"/api/audit/sales?start={future_start}").json()
    assert logs == []
