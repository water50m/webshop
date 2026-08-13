import os

os.environ["DATABASE_URL"] = "sqlite:///./test_role_permission_gaps.db"

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
    login_as("owner", "ownerpass")
    yield
    Base.metadata.drop_all(bind=engine)


def login_as(username: str, password: str):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


def create_user(username: str, password: str, role: str):
    res = client.post("/api/users", json={"username": username, "password": password, "role": role})
    assert res.status_code == 200, res.text


def create_product(sku="SKU1", price=100, stock=10):
    res = client.post("/api/products", json={"sku": sku, "name": "สินค้าทดสอบ", "price": price, "low_stock_threshold": 1})
    assert res.status_code == 200, res.text
    product = res.json()
    client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": stock, "note": "initial"})
    return product


def complete_a_sale(product: dict, payments=None) -> dict:
    """Creates a sale and checks it out as whichever user is currently logged in."""
    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"product_id": product["id"], "quantity": 1})
    checkout = client.post(
        f"/api/pos/sales/{sale['id']}/checkout",
        json={"payments": payments or [{"method": "cash", "amount": 100}]},
    )
    assert checkout.status_code == 200, checkout.text
    return checkout.json()


def test_cashier_cannot_void_completed_sale_but_owner_can():
    create_user("cashier1", "pass1234", "cashier")
    product = create_product()
    login_as("cashier1", "pass1234")
    client.post("/api/shifts/open", json={"opening_cash": 0})
    sale = complete_a_sale(product)

    void = client.post(f"/api/pos/sales/{sale['id']}/void")
    assert void.status_code == 403

    login_as("owner", "ownerpass")
    void = client.post(f"/api/pos/sales/{sale['id']}/void")
    assert void.status_code == 200, void.text
    assert void.json()["status"] == "voided"


def test_cashier_cannot_void_held_sale_self_correction_still_allowed():
    create_user("cashier1", "pass1234", "cashier")
    login_as("cashier1", "pass1234")
    sale = client.post("/api/pos/sales").json()
    void = client.post(f"/api/pos/sales/{sale['id']}/void")
    assert void.status_code == 200, void.text


def test_cashier_cannot_refund_but_manager_can():
    create_user("cashier1", "pass1234", "cashier")
    create_user("manager1", "pass1234", "manager")
    product = create_product()

    login_as("cashier1", "pass1234")
    client.post("/api/shifts/open", json={"opening_cash": 0})
    sale = complete_a_sale(product)
    item_id = sale["items"][0]["id"]

    refund = client.post(f"/api/pos/sales/{sale['id']}/refund", json={"items": [{"item_id": item_id, "quantity": 1}]})
    assert refund.status_code == 403

    login_as("manager1", "pass1234")
    refund = client.post(f"/api/pos/sales/{sale['id']}/refund", json={"items": [{"item_id": item_id, "quantity": 1}]})
    assert refund.status_code == 200, refund.text
    assert refund.json()["status"] == "voided"


def test_cashier_can_close_own_shift_but_not_others():
    create_user("cashier1", "pass1234", "cashier")
    create_user("cashier2", "pass1234", "cashier")

    login_as("cashier1", "pass1234")
    shift1 = client.post("/api/shifts/open", json={"opening_cash": 0}).json()

    login_as("cashier2", "pass1234")
    shift2 = client.post("/api/shifts/open", json={"opening_cash": 0}).json()

    close_other = client.post(f"/api/shifts/{shift1['id']}/close", json={"closing_cash_counted": 0})
    assert close_other.status_code == 403

    close_own = client.post(f"/api/shifts/{shift2['id']}/close", json={"closing_cash_counted": 0})
    assert close_own.status_code == 200, close_own.text


def test_cashier_cannot_view_others_shift_summary_but_owner_can():
    create_user("cashier1", "pass1234", "cashier")
    create_user("cashier2", "pass1234", "cashier")

    login_as("cashier1", "pass1234")
    shift1 = client.post("/api/shifts/open", json={"opening_cash": 0}).json()

    login_as("cashier2", "pass1234")
    summary = client.get(f"/api/shifts/{shift1['id']}/summary")
    assert summary.status_code == 403

    login_as("owner", "ownerpass")
    summary = client.get(f"/api/shifts/{shift1['id']}/summary")
    assert summary.status_code == 200, summary.text


def test_manager_can_close_any_cashiers_shift():
    create_user("cashier1", "pass1234", "cashier")
    create_user("manager1", "pass1234", "manager")

    login_as("cashier1", "pass1234")
    shift1 = client.post("/api/shifts/open", json={"opening_cash": 0}).json()

    login_as("manager1", "pass1234")
    close = client.post(f"/api/shifts/{shift1['id']}/close", json={"closing_cash_counted": 0})
    assert close.status_code == 200, close.text
