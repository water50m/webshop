import os
from datetime import date

os.environ["DATABASE_URL"] = "sqlite:///./test_pos.db"

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


def create_product(sku="SKU1", name="สินค้าทดสอบ", price=100, stock=10, low_stock_threshold=2):
    res = client.post(
        "/api/products",
        json={"sku": sku, "name": name, "price": price, "low_stock_threshold": low_stock_threshold},
    )
    assert res.status_code == 200, res.text
    product = res.json()
    adj = client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": stock, "note": "initial"})
    assert adj.status_code == 200, adj.text
    return adj.json()


def test_pos_checkout_deducts_stock_and_records_movement():
    product = create_product(stock=10)

    sale = client.post("/api/pos/sales").json()
    add = client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 3})
    assert add.status_code == 200, add.text
    cart = add.json()
    assert cart["subtotal"] == 300
    assert cart["total"] == 300

    checkout = client.post(
        f"/api/pos/sales/{sale['id']}/checkout",
        json={"payments": [{"method": "cash", "amount": 500}]},
    )
    assert checkout.status_code == 200, checkout.text
    completed = checkout.json()
    assert completed["status"] == "completed"
    assert completed["change_amount"] == 200
    assert completed["receipt_no"] == 1

    after = client.get(f"/api/products/lookup?code=SKU1").json()
    assert after["stock_quantity"] == 7


def test_pos_checkout_blocks_when_stock_insufficient():
    create_product(stock=2)
    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 5})
    checkout = client.post(
        f"/api/pos/sales/{sale['id']}/checkout",
        json={"payments": [{"method": "cash", "amount": 1000}]},
    )
    assert checkout.status_code == 400


def test_pos_void_restocks_items():
    create_product(stock=10)
    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 4})
    client.post(f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "transfer", "amount": 400}]})

    after_sale = client.get(f"/api/products/lookup?code=SKU1").json()
    assert after_sale["stock_quantity"] == 6

    void = client.post(f"/api/pos/sales/{sale['id']}/void")
    assert void.status_code == 200, void.text
    assert void.json()["status"] == "voided"

    after_void = client.get(f"/api/products/lookup?code=SKU1").json()
    assert after_void["stock_quantity"] == 10


def test_multiple_held_sales_independent():
    create_product(stock=20)
    sale_a = client.post("/api/pos/sales").json()
    sale_b = client.post("/api/pos/sales").json()

    client.post(f"/api/pos/sales/{sale_a['id']}/items", json={"code": "SKU1", "quantity": 1})
    client.post(f"/api/pos/sales/{sale_b['id']}/items", json={"code": "SKU1", "quantity": 2})

    held = client.get("/api/pos/sales?status=held").json()
    assert len(held) == 2

    a = client.get(f"/api/pos/sales/{sale_a['id']}").json()
    b = client.get(f"/api/pos/sales/{sale_b['id']}").json()
    assert a["items"][0]["quantity"] == 1
    assert b["items"][0]["quantity"] == 2


def test_draft_order_confirm_deducts_same_stock_pool():
    from app.db import SessionLocal
    from app.models import Channel, ChannelType, Conversation, Customer, DraftOrder, DraftOrderItem, Product

    product = create_product(stock=5)

    db = SessionLocal()
    try:
        channel = Channel(type=ChannelType.facebook_page, external_id="page1")
        db.add(channel)
        db.flush()
        customer = Customer(channel_id=channel.id, external_user_id="user1")
        db.add(customer)
        db.flush()
        conversation = Conversation(channel_id=channel.id, customer_id=customer.id)
        db.add(conversation)
        db.flush()
        db_product = db.get(Product, product["id"])
        draft_order = DraftOrder(conversation_id=conversation.id)
        db.add(draft_order)
        db.flush()
        db.add(
            DraftOrderItem(
                draft_order_id=draft_order.id,
                product_id=db_product.id,
                matched_text=db_product.name,
                quantity=2,
                unit_price=db_product.price,
            )
        )
        db.commit()
        draft_order_id = draft_order.id
    finally:
        db.close()

    confirm = client.post(f"/api/draft-orders/{draft_order_id}/confirm")
    assert confirm.status_code == 200, confirm.text

    after = client.get("/api/products/lookup?code=SKU1").json()
    assert after["stock_quantity"] == 3


def test_bill_and_item_discount_applied():
    create_product(stock=10, price=100)
    sale = client.post("/api/pos/sales").json()
    add = client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 2}).json()
    item_id = add["items"][0]["id"]

    client.put(f"/api/pos/sales/{sale['id']}/items/{item_id}", json={"discount_amount": 20})
    updated = client.put(f"/api/pos/sales/{sale['id']}", json={"discount_amount": 10}).json()

    assert updated["subtotal"] == 200
    assert updated["total_discount"] == 30
    assert updated["total"] == 170
