import os

os.environ["DATABASE_URL"] = "sqlite:///./test_db_config.db"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.db_config import CONFIG_PATH
from app.main import app
from app.models import User, UserRole
from app.services.auth import hash_password

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    CONFIG_PATH.unlink(missing_ok=True)
    db = SessionLocal()
    db.add(User(username="owner", password_hash=hash_password("ownerpass"), display_name="Owner", role=UserRole.owner))
    db.add(
        User(username="manager", password_hash=hash_password("managerpass"), display_name="Manager", role=UserRole.manager)
    )
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)
    CONFIG_PATH.unlink(missing_ok=True)


def _login(username: str, password: str):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text


def test_get_db_config_requires_owner():
    _login("manager", "managerpass")
    res = client.get("/api/system/db-config")
    assert res.status_code == 403


def test_get_db_config_defaults_when_no_file():
    _login("owner", "ownerpass")
    res = client.get("/api/system/db-config")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["engine"] == "sqlite"
    assert body["env_override"] is True  # test process always has DATABASE_URL set


def test_update_db_config_requires_postgres_url_when_engine_is_postgres():
    _login("owner", "ownerpass")
    res = client.put("/api/system/db-config", json={"engine": "postgres", "sqlite_path": "./dev.db", "postgres_url": ""})
    assert res.status_code == 400
    assert "PostgreSQL" in res.json()["detail"]


def test_update_db_config_rejects_unknown_engine():
    _login("owner", "ownerpass")
    res = client.put("/api/system/db-config", json={"engine": "mysql", "sqlite_path": "", "postgres_url": ""})
    assert res.status_code == 400


def test_update_db_config_writes_and_persists_sqlite_choice():
    _login("owner", "ownerpass")
    res = client.put(
        "/api/system/db-config", json={"engine": "sqlite", "sqlite_path": "./other.db", "postgres_url": ""}
    )
    assert res.status_code == 200, res.text
    assert res.json()["sqlite_path"] == "./other.db"

    res2 = client.get("/api/system/db-config")
    assert res2.json()["sqlite_path"] == "./other.db"
    assert CONFIG_PATH.exists()


def test_test_db_config_succeeds_for_reachable_sqlite_file():
    _login("owner", "ownerpass")
    res = client.post(
        "/api/system/db-config/test", json={"engine": "sqlite", "sqlite_path": "./test_db_config_probe.db", "postgres_url": ""}
    )
    assert res.status_code == 200, res.text
    assert res.json()["ok"] is True
    if os.path.exists("./test_db_config_probe.db"):
        os.remove("./test_db_config_probe.db")


def test_test_db_config_fails_for_unreachable_postgres():
    _login("owner", "ownerpass")
    res = client.post(
        "/api/system/db-config/test",
        json={"engine": "postgres", "sqlite_path": "", "postgres_url": "postgresql+psycopg2://baduser:badpass@127.0.0.1:1/nope"},
    )
    assert res.status_code == 400
    assert "เชื่อมต่อไม่สำเร็จ" in res.json()["detail"]
