import os

os.environ["DATABASE_URL"] = "sqlite:///./test_auth.db"

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
    yield
    Base.metadata.drop_all(bind=engine)


def create_user(username, password, role, display_name=""):
    db = SessionLocal()
    db.add(User(username=username, password_hash=hash_password(password), display_name=display_name, role=role))
    db.commit()
    db.close()


def test_login_success_sets_cookie_and_me_works():
    create_user("owner1", "pass1234", UserRole.owner, "Owner One")
    res = client.post("/api/auth/login", json={"username": "owner1", "password": "pass1234"})
    assert res.status_code == 200, res.text
    assert res.cookies.get("session_token") is not None

    me = client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["username"] == "owner1"
    assert body["role"] == "owner"


def test_login_wrong_password_fails():
    create_user("owner1", "pass1234", UserRole.owner)
    res = client.post("/api/auth/login", json={"username": "owner1", "password": "wrongpass"})
    assert res.status_code == 401


def test_login_unknown_user_fails():
    res = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert res.status_code == 401


def test_logout_clears_session():
    create_user("owner1", "pass1234", UserRole.owner)
    client.post("/api/auth/login", json={"username": "owner1", "password": "pass1234"})
    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200

    me = client.get("/api/auth/me")
    assert me.status_code == 401


def test_protected_endpoint_without_login_returns_401():
    res = client.get("/api/products")
    assert res.status_code == 401


def test_cashier_cannot_access_owner_manager_endpoint():
    create_user("cashier1", "pass1234", UserRole.cashier)
    login = client.post("/api/auth/login", json={"username": "cashier1", "password": "pass1234"})
    assert login.status_code == 200

    res = client.get("/api/expenses")
    assert res.status_code == 403


def test_cashier_can_use_pos_and_view_products():
    create_user("cashier1", "pass1234", UserRole.cashier)
    client.post("/api/auth/login", json={"username": "cashier1", "password": "pass1234"})

    assert client.get("/api/products").status_code == 200
    assert client.post("/api/pos/sales").status_code == 200


def test_cashier_cannot_create_product():
    create_user("cashier1", "pass1234", UserRole.cashier)
    client.post("/api/auth/login", json={"username": "cashier1", "password": "pass1234"})

    res = client.post("/api/products", json={"sku": "X1", "name": "ของ", "price": 10})
    assert res.status_code == 403


def test_manager_can_create_product_but_not_manage_users():
    create_user("manager1", "pass1234", UserRole.manager)
    client.post("/api/auth/login", json={"username": "manager1", "password": "pass1234"})

    res = client.post("/api/products", json={"sku": "X1", "name": "ของ", "price": 10})
    assert res.status_code == 200, res.text

    users_res = client.get("/api/users")
    assert users_res.status_code == 403


def test_owner_can_manage_users():
    create_user("owner1", "pass1234", UserRole.owner)
    client.post("/api/auth/login", json={"username": "owner1", "password": "pass1234"})

    create = client.post(
        "/api/users",
        json={"username": "newcashier", "password": "abcd1234", "display_name": "New Cashier", "role": "cashier"},
    )
    assert create.status_code == 200, create.text
    user_id = create.json()["id"]

    listed = client.get("/api/users")
    assert listed.status_code == 200
    assert any(u["username"] == "newcashier" for u in listed.json())

    updated = client.put(f"/api/users/{user_id}", json={"display_name": "Updated", "role": "manager"})
    assert updated.status_code == 200
    assert updated.json()["role"] == "manager"

    deleted = client.delete(f"/api/users/{user_id}")
    assert deleted.status_code == 200


def test_set_pin_then_unlock_succeeds():
    create_user("cashier1", "pass1234", UserRole.cashier)
    client.post("/api/auth/login", json={"username": "cashier1", "password": "pass1234"})

    me_before = client.get("/api/auth/me").json()
    assert me_before["has_pin"] is False

    set_pin = client.post("/api/auth/set-pin", json={"pin": "1234"})
    assert set_pin.status_code == 200, set_pin.text

    me_after = client.get("/api/auth/me").json()
    assert me_after["has_pin"] is True

    client.post("/api/auth/logout")
    unlock = client.post("/api/auth/unlock", json={"username": "cashier1", "pin": "1234"})
    assert unlock.status_code == 200, unlock.text
    assert unlock.json()["username"] == "cashier1"

    me = client.get("/api/auth/me")
    assert me.status_code == 200


def test_unlock_with_wrong_pin_fails():
    create_user("cashier1", "pass1234", UserRole.cashier)
    client.post("/api/auth/login", json={"username": "cashier1", "password": "pass1234"})
    client.post("/api/auth/set-pin", json={"pin": "1234"})
    client.post("/api/auth/logout")

    res = client.post("/api/auth/unlock", json={"username": "cashier1", "pin": "9999"})
    assert res.status_code == 401


def test_unlock_without_pin_set_fails():
    create_user("cashier1", "pass1234", UserRole.cashier)
    res = client.post("/api/auth/unlock", json={"username": "cashier1", "pin": "1234"})
    assert res.status_code == 401


def test_set_pin_rejects_short_or_nondigit():
    create_user("cashier1", "pass1234", UserRole.cashier)
    client.post("/api/auth/login", json={"username": "cashier1", "password": "pass1234"})

    assert client.post("/api/auth/set-pin", json={"pin": "12"}).status_code == 400
    assert client.post("/api/auth/set-pin", json={"pin": "abcd"}).status_code == 400


def test_set_pin_requires_login():
    res = client.post("/api/auth/set-pin", json={"pin": "1234"})
    assert res.status_code == 401
