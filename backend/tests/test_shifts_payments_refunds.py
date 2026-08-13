import os
from datetime import datetime

os.environ["DATABASE_URL"] = "sqlite:///./test_shifts_payments_refunds.db"

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


def create_product(sku="SKU1", name="สินค้าทดสอบ", price=100, stock=10):
    res = client.post("/api/products", json={"sku": sku, "name": name, "price": price, "low_stock_threshold": 1})
    assert res.status_code == 200, res.text
    product = res.json()
    client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": stock, "note": "initial"})
    return product


def test_checkout_blocked_without_open_shift():
    create_product(stock=10)
    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 1})
    checkout = client.post(f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "cash", "amount": 100}]})
    assert checkout.status_code == 400
    assert "เปิดกะ" in checkout.json()["detail"]


def test_open_shift_then_checkout_succeeds_and_receipt_no_increments():
    open_res = client.post("/api/shifts/open", json={"opening_cash": 1000})
    assert open_res.status_code == 200, open_res.text
    shift_id = open_res.json()["id"]

    create_product(stock=10)
    sale1 = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale1['id']}/items", json={"code": "SKU1", "quantity": 1})
    checkout1 = client.post(f"/api/pos/sales/{sale1['id']}/checkout", json={"payments": [{"method": "cash", "amount": 100}]})
    assert checkout1.status_code == 200, checkout1.text
    assert checkout1.json()["receipt_no"] == 1

    sale2 = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale2['id']}/items", json={"code": "SKU1", "quantity": 1})
    checkout2 = client.post(f"/api/pos/sales/{sale2['id']}/checkout", json={"payments": [{"method": "cash", "amount": 100}]})
    assert checkout2.status_code == 200, checkout2.text
    assert checkout2.json()["receipt_no"] == 2

    assert client.get("/api/shifts/current").json()["id"] == shift_id


def test_cannot_open_second_shift_while_one_open():
    client.post("/api/shifts/open", json={"opening_cash": 0})
    second = client.post("/api/shifts/open", json={"opening_cash": 0})
    assert second.status_code == 400


def test_split_payment_checkout_and_shift_summary():
    open_res = client.post("/api/shifts/open", json={"opening_cash": 100})
    shift_id = open_res.json()["id"]

    create_product(stock=10, price=100)
    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 2})  # total 200

    checkout = client.post(
        f"/api/pos/sales/{sale['id']}/checkout",
        json={"payments": [{"method": "cash", "amount": 50}, {"method": "transfer", "amount": 150}]},
    )
    assert checkout.status_code == 200, checkout.text
    body = checkout.json()
    assert body["change_amount"] == 0
    assert sorted(p["method"] for p in body["payments"]) == ["cash", "transfer"]

    close_res = client.post(f"/api/shifts/{shift_id}/close", json={"closing_cash_counted": 150})
    assert close_res.status_code == 200, close_res.text

    summary = client.get(f"/api/shifts/{shift_id}/summary").json()
    assert summary["totals_by_method"]["cash"] == 50
    assert summary["totals_by_method"]["transfer"] == 150
    assert summary["expected_cash"] == 150  # opening 100 + cash 50
    assert summary["cash_difference"] == 0


def test_split_payment_with_cash_change():
    client.post("/api/shifts/open", json={"opening_cash": 0})
    create_product(stock=10, price=100)
    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 1})  # total 100

    checkout = client.post(
        f"/api/pos/sales/{sale['id']}/checkout",
        json={"payments": [{"method": "transfer", "amount": 50}, {"method": "cash", "amount": 100}]},
    )
    assert checkout.status_code == 200, checkout.text
    assert checkout.json()["change_amount"] == 50


def test_partial_refund_restocks_and_adjusts_total():
    client.post("/api/shifts/open", json={"opening_cash": 0})
    create_product(stock=10, price=100)
    sale = client.post("/api/pos/sales").json()
    add = client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 3}).json()
    item_id = add["items"][0]["id"]

    checkout = client.post(f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "cash", "amount": 300}]})
    assert checkout.status_code == 200, checkout.text

    after_sale = client.get("/api/products/lookup?code=SKU1").json()
    assert after_sale["stock_quantity"] == 7

    refund = client.post(
        f"/api/pos/sales/{sale['id']}/refund",
        json={"items": [{"item_id": item_id, "quantity": 1}], "note": "ลูกค้าคืน 1 ชิ้น"},
    )
    assert refund.status_code == 200, refund.text
    refunded = refund.json()
    assert refunded["status"] == "completed"
    assert refunded["items"][0]["refunded_quantity"] == 1
    assert refunded["total"] == 200

    after_refund = client.get("/api/products/lookup?code=SKU1").json()
    assert after_refund["stock_quantity"] == 8


def test_partial_refund_excluded_from_income_report():
    client.post("/api/shifts/open", json={"opening_cash": 0})
    create_product(stock=10, price=100)
    sale = client.post("/api/pos/sales").json()
    add = client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 3}).json()
    item_id = add["items"][0]["id"]
    client.post(f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "cash", "amount": 300}]})

    now = datetime.utcnow()
    before_refund = client.get(f"/api/reports/summary?year={now.year}&month={now.month}").json()
    assert before_refund["income"] == 300

    client.post(f"/api/pos/sales/{sale['id']}/refund", json={"items": [{"item_id": item_id, "quantity": 1}]})

    after_refund = client.get(f"/api/reports/summary?year={now.year}&month={now.month}").json()
    assert after_refund["income"] == 200


def test_refund_all_quantity_voids_sale():
    client.post("/api/shifts/open", json={"opening_cash": 0})
    create_product(stock=10, price=100)
    sale = client.post("/api/pos/sales").json()
    add = client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 2}).json()
    item_id = add["items"][0]["id"]
    client.post(f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "cash", "amount": 200}]})

    refund = client.post(f"/api/pos/sales/{sale['id']}/refund", json={"items": [{"item_id": item_id, "quantity": 2}]})
    assert refund.status_code == 200, refund.text
    assert refund.json()["status"] == "voided"


def test_refund_more_than_purchased_fails():
    client.post("/api/shifts/open", json={"opening_cash": 0})
    create_product(stock=10, price=100)
    sale = client.post("/api/pos/sales").json()
    add = client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 1}).json()
    item_id = add["items"][0]["id"]
    client.post(f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "cash", "amount": 100}]})

    refund = client.post(f"/api/pos/sales/{sale['id']}/refund", json={"items": [{"item_id": item_id, "quantity": 5}]})
    assert refund.status_code == 400


def test_sales_history_date_filter():
    client.post("/api/shifts/open", json={"opening_cash": 0})
    create_product(stock=10, price=100)
    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 1})
    client.post(f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "cash", "amount": 100}]})

    far_future = client.get("/api/pos/sales?status=completed&start=2999-01-01T00:00:00")
    assert far_future.status_code == 200
    assert far_future.json() == []

    all_completed = client.get("/api/pos/sales?status=completed")
    assert len(all_completed.json()) == 1
