import os
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_daily_report.db"

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
    db.add(User(username="owner", password_hash=hash_password("ownerpass"), role=UserRole.owner))
    db.commit()
    db.close()
    assert client.post("/api/auth/login", json={"username": "owner", "password": "ownerpass"}).status_code == 200
    assert client.post("/api/shifts/open", json={"opening_cash": 0}).status_code == 200
    yield
    Base.metadata.drop_all(bind=engine)


def test_daily_report_returns_income_expense_top_products_and_orders():
    product = client.post("/api/products", json={"sku": "DAILY1", "name": "Daily product", "price": 75}).json()
    client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": 10, "note": "initial"})
    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"product_id": product["id"], "quantity": 2})
    assert client.post(f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "cash", "amount": 150}]}).status_code == 200
    assert client.post("/api/expenses", json={"category": "marketing", "amount": 40, "description": "ads", "expense_date": datetime.utcnow().date().isoformat()}).status_code == 200

    start = (datetime.utcnow() - timedelta(days=1)).isoformat()
    end = (datetime.utcnow() + timedelta(days=1)).isoformat()
    response = client.get(f"/api/reports/daily?start={start}&end={end}")

    assert response.status_code == 200, response.text
    body = response.json()
    today = next(day for day in body["days"] if day["date"] == datetime.utcnow().date().isoformat())
    assert today["income"] == 150
    assert today["expense"] == 40
    assert today["top_product_quantities"]["0"] == 2
    assert body["top_products"][0]["sku"] == "DAILY1"
    assert body["orders"][0]["revenue"] == 150
