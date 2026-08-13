import os

os.environ["DATABASE_URL"] = "sqlite:///./test_history_preparation.db"

from fastapi.testclient import TestClient

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User, UserRole
from app.services.auth import hash_password

client = TestClient(app)


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(User(username="owner", password_hash=hash_password("ownerpass"), role=UserRole.owner))
    db.commit()
    db.close()
    response = client.post("/api/auth/login", json={"username": "owner", "password": "ownerpass"})
    assert response.status_code == 200


def teardown_function():
    Base.metadata.drop_all(bind=engine)


def test_status_waits_for_dedicated_history_token(monkeypatch):
    monkeypatch.setattr(settings, "meta_history_access_token", "")
    monkeypatch.setattr(settings, "meta_history_page_id", "")

    response = client.get("/api/history-preparation/status")

    assert response.status_code == 200
    assert response.json() == {
        "state": "waiting_for_token",
        "token_ready": False,
        "page_id_ready": False,
        "lookback_days": 60,
        "source": "facebook",
        "analysis_only": True,
        "sending_enabled": False,
        "next_action": "เพิ่ม META_HISTORY_ACCESS_TOKEN ใน backend/.env แล้วรีสตาร์ต backend",
    }
