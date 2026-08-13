import os
from datetime import datetime

os.environ["DATABASE_URL"] = "sqlite:///./test_cost_price_gross_margin.db"

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


def create_product(sku="SKU1", price=100, cost_price=40, stock=10):
    res = client.post("/api/products", json={"sku": sku, "name": "สินค้าทดสอบ", "price": price, "cost_price": cost_price})
    assert res.status_code == 200, res.text
    product = res.json()
    adj = client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": stock, "note": "initial"})
    assert adj.status_code == 200, adj.text
    return adj.json()


def test_owner_sees_cost_price_cashier_does_not():
    create_product(cost_price=40)
    client.post("/api/users", json={"username": "cashier1", "password": "pass1234", "role": "cashier"})

    owner_view = client.get("/api/products/lookup?code=SKU1").json()
    assert owner_view["cost_price"] == 40

    login_as("cashier1", "pass1234")
    cashier_view = client.get("/api/products/lookup?code=SKU1").json()
    assert cashier_view["cost_price"] == 0


def test_gross_profit_excludes_cogs_of_sold_items():
    product = create_product(price=100, cost_price=40)
    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"product_id": product["id"], "quantity": 3})
    checkout = client.post(f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "cash", "amount": 300}]})
    assert checkout.status_code == 200, checkout.text

    now = datetime.utcnow()
    summary = client.get(f"/api/reports/summary?year={now.year}&month={now.month}").json()
    assert summary["income"] == 300
    assert summary["cogs"] == 120
    assert summary["gross_profit"] == 180


def test_gross_profit_excludes_refunded_quantity():
    product = create_product(price=100, cost_price=40)
    sale = client.post("/api/pos/sales").json()
    add = client.post(f"/api/pos/sales/{sale['id']}/items", json={"product_id": product["id"], "quantity": 3}).json()
    item_id = add["items"][0]["id"]
    client.post(f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "cash", "amount": 300}]})
    client.post(f"/api/pos/sales/{sale['id']}/refund", json={"items": [{"item_id": item_id, "quantity": 1}]})

    now = datetime.utcnow()
    summary = client.get(f"/api/reports/summary?year={now.year}&month={now.month}").json()
    assert summary["income"] == 200
    assert summary["cogs"] == 80
    assert summary["gross_profit"] == 120
