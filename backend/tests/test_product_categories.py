import os

os.environ["DATABASE_URL"] = "sqlite:///./test_product_categories.db"

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


def create_product(sku, name, category, price=50):
    res = client.post("/api/products", json={"sku": sku, "name": name, "category": category, "price": price})
    assert res.status_code == 200, res.text
    return res.json()


def test_create_product_with_category():
    product = create_product("SAL1", "สลัดผัก", "สลัด")
    assert product["category"] == "สลัด"


def test_list_categories_returns_distinct_used_categories():
    create_product("SAL1", "สลัดผัก", "สลัด")
    create_product("SAL2", "สลัดไก่", "สลัด")
    create_product("DRK1", "น้ำส้ม", "เครื่องดื่ม")
    create_product("NOCAT1", "ของอื่น", "")

    res = client.get("/api/products/categories")
    assert res.status_code == 200, res.text
    assert set(res.json()) == {"เครื่องดื่ม", "สลัด"}


def test_filter_products_by_category():
    create_product("SAL1", "สลัดผัก", "สลัด")
    create_product("DRK1", "น้ำส้ม", "เครื่องดื่ม")

    res = client.get("/api/products?category=สลัด")
    assert res.status_code == 200, res.text
    names = [p["name"] for p in res.json()]
    assert names == ["สลัดผัก"]


def test_update_product_category():
    product = create_product("SAL1", "สลัดผัก", "สลัด")
    updated = client.put(
        f"/api/products/{product['id']}",
        json={"sku": "SAL1", "name": "สลัดผัก", "category": "เมนูแนะนำ", "price": 50},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["category"] == "เมนูแนะนำ"
