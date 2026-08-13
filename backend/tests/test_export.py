import os

os.environ["DATABASE_URL"] = "sqlite:///./test_export.db"

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


def test_export_products_csv():
    client.post("/api/products", json={"sku": "SKU1", "name": "สินค้าทดสอบ", "price": 100, "low_stock_threshold": 1})
    res = client.get("/api/export/products")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "SKU1" in res.text


def test_export_sales_csv_includes_completed_sale():
    client.post("/api/products", json={"sku": "SKU1", "name": "สินค้าทดสอบ", "price": 100, "low_stock_threshold": 1})
    product = client.get("/api/products/lookup?code=SKU1").json()
    client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": 5, "note": "initial"})
    client.post("/api/shifts/open", json={"opening_cash": 0})
    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 1})
    client.post(f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "cash", "amount": 100}]})

    res = client.get("/api/export/sales")
    assert res.status_code == 200
    assert "SKU1" in res.text


def test_export_blocked_for_cashier():
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "cashier", "password": "cashierpass"})
    res = client.get("/api/export/products")
    assert res.status_code == 403
