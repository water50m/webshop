import os

os.environ["DATABASE_URL"] = "sqlite:///./test_product_modifiers.db"

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


def create_product(sku="SAL1", name="สลัดผัก", price=50, stock=10):
    res = client.post("/api/products", json={"sku": sku, "name": name, "price": price})
    assert res.status_code == 200, res.text
    product = res.json()
    adj = client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": stock, "note": "initial"})
    assert adj.status_code == 200, adj.text
    return adj.json()


def add_modifier(product_id, name, price_delta=0):
    res = client.post(f"/api/products/{product_id}/modifiers", json={"name": name, "price_delta": price_delta})
    assert res.status_code == 200, res.text
    return next(m for m in res.json()["modifiers"] if m["name"] == name)


def test_create_modifier_appears_on_product():
    product = create_product()
    modifier = add_modifier(product["id"], "ไข่ต้ม", 10)
    assert modifier["price_delta"] == 10

    fetched = client.get(f"/api/products/lookup?code=SAL1").json()
    assert len(fetched["modifiers"]) == 1


def test_update_and_delete_modifier():
    product = create_product()
    modifier = add_modifier(product["id"], "ไข่ต้ม", 10)

    updated = client.put(
        f"/api/products/{product['id']}/modifiers/{modifier['id']}", json={"name": "ไข่ต้ม", "price_delta": 15}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["modifiers"][0]["price_delta"] == 15

    deleted = client.delete(f"/api/products/{product['id']}/modifiers/{modifier['id']}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["modifiers"] == []


def test_add_item_with_modifier_adds_to_unit_price():
    product = create_product(price=50)
    modifier = add_modifier(product["id"], "ไข่ต้ม", 10)

    sale = client.post("/api/pos/sales").json()
    added = client.post(
        f"/api/pos/sales/{sale['id']}/items",
        json={"product_id": product["id"], "quantity": 2, "modifier_ids": [modifier["id"]]},
    )
    assert added.status_code == 200, added.text
    body = added.json()
    item = body["items"][0]
    assert item["modifiers"] == [{"name": "ไข่ต้ม", "price_delta": 10}]
    assert item["line_total"] == (50 + 10) * 2
    assert body["subtotal"] == (50 + 10) * 2


def test_same_product_different_modifiers_are_separate_lines():
    product = create_product(price=50)
    modifier = add_modifier(product["id"], "ไข่ต้ม", 10)

    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"product_id": product["id"], "quantity": 1})
    second = client.post(
        f"/api/pos/sales/{sale['id']}/items",
        json={"product_id": product["id"], "quantity": 1, "modifier_ids": [modifier["id"]]},
    )
    assert second.status_code == 200, second.text
    assert len(second.json()["items"]) == 2


def test_same_product_same_modifiers_merge_into_one_line():
    product = create_product(price=50)
    modifier = add_modifier(product["id"], "ไข่ต้ม", 10)

    sale = client.post("/api/pos/sales").json()
    client.post(
        f"/api/pos/sales/{sale['id']}/items",
        json={"product_id": product["id"], "quantity": 1, "modifier_ids": [modifier["id"]]},
    )
    second = client.post(
        f"/api/pos/sales/{sale['id']}/items",
        json={"product_id": product["id"], "quantity": 2, "modifier_ids": [modifier["id"]]},
    )
    assert second.status_code == 200, second.text
    items = second.json()["items"]
    assert len(items) == 1
    assert items[0]["quantity"] == 3


def test_modifier_from_other_product_rejected():
    product_a = create_product(sku="A1", name="สลัด A")
    product_b = create_product(sku="B1", name="สลัด B")
    modifier_b = add_modifier(product_b["id"], "ซอสงา", 5)

    sale = client.post("/api/pos/sales").json()
    res = client.post(
        f"/api/pos/sales/{sale['id']}/items",
        json={"product_id": product_a["id"], "quantity": 1, "modifier_ids": [modifier_b["id"]]},
    )
    assert res.status_code == 400


def test_checkout_total_includes_modifier_price():
    product = create_product(price=50)
    modifier = add_modifier(product["id"], "ไข่ต้ม", 10)

    sale = client.post("/api/pos/sales").json()
    client.post(
        f"/api/pos/sales/{sale['id']}/items",
        json={"product_id": product["id"], "quantity": 2, "modifier_ids": [modifier["id"]]},
    )
    checkout = client.post(f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "cash", "amount": 120}]})
    assert checkout.status_code == 200, checkout.text
    assert checkout.json()["total"] == 120


def test_only_owner_or_manager_can_manage_modifiers():
    product = create_product()
    client.post("/api/users", json={"username": "cashier1", "password": "pass1234", "role": "cashier"})
    cashier_login = client.post("/api/auth/login", json={"username": "cashier1", "password": "pass1234"})
    assert cashier_login.status_code == 200

    res = client.post(f"/api/products/{product['id']}/modifiers", json={"name": "ไข่ต้ม", "price_delta": 10})
    assert res.status_code == 403
