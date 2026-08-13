import os
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_product_performance_report.db"

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


def create_product(sku, price, stock=20):
    res = client.post("/api/products", json={"sku": sku, "name": f"สินค้า {sku}", "price": price})
    assert res.status_code == 200, res.text
    product = res.json()
    adj = client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": stock, "note": "initial"})
    assert adj.status_code == 200, adj.text
    return adj.json()


def sell(product, quantity):
    sale = client.post("/api/pos/sales").json()
    add = client.post(f"/api/pos/sales/{sale['id']}/items", json={"product_id": product["id"], "quantity": quantity}).json()
    item_id = add["items"][0]["id"]
    checkout = client.post(
        f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "cash", "amount": quantity * float(product["price"])}]}
    )
    assert checkout.status_code == 200, checkout.text
    return checkout.json(), item_id


def date_range():
    start = (datetime.utcnow() - timedelta(days=1)).isoformat()
    end = (datetime.utcnow() + timedelta(days=1)).isoformat()
    return start, end


def test_best_seller_sorted_by_quantity_desc():
    best = create_product("BEST1", 50)
    worst = create_product("WORST1", 50)
    sell(best, 10)
    sell(worst, 1)

    start, end = date_range()
    res = client.get(f"/api/reports/products?start={start}&end={end}")
    assert res.status_code == 200, res.text
    rows = res.json()
    assert rows[0]["sku"] == "BEST1"
    assert rows[0]["quantity_sold"] == 10
    assert rows[-1]["sku"] == "WORST1"
    assert rows[-1]["quantity_sold"] == 1


def test_performance_excludes_refunded_quantity():
    product = create_product("REF1", 100)
    _, item_id = sell(product, 5)
    sale = client.get("/api/pos/sales?status=completed").json()[0]
    refund = client.post(f"/api/pos/sales/{sale['id']}/refund", json={"items": [{"item_id": item_id, "quantity": 2}]})
    assert refund.status_code == 200, refund.text

    start, end = date_range()
    res = client.get(f"/api/reports/products?start={start}&end={end}")
    rows = res.json()
    row = next(r for r in rows if r["sku"] == "REF1")
    assert row["quantity_sold"] == 3
    assert row["revenue"] == 300


def test_cashier_cannot_view_product_performance_report():
    client.post("/api/users", json={"username": "cashier1", "password": "pass1234", "role": "cashier"})
    client.post("/api/auth/login", json={"username": "cashier1", "password": "pass1234"})

    start, end = date_range()
    res = client.get(f"/api/reports/products?start={start}&end={end}")
    assert res.status_code == 403
