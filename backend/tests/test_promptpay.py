import os

os.environ["DATABASE_URL"] = "sqlite:///./test_promptpay.db"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User, UserRole
from app.services.auth import hash_password
from app.services.promptpay import _crc16_ccitt, generate_promptpay_payload

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


def test_payload_crc_is_self_consistent():
    payload = generate_promptpay_payload("0812345678", 100.5)
    body, crc = payload[:-4], payload[-4:]
    assert _crc16_ccitt(body) == crc


def test_payload_contains_expected_fields_for_phone_number():
    payload = generate_promptpay_payload("0812345678", 50)
    assert payload.startswith("000201")
    assert "5802TH" in payload
    assert "5303764" in payload
    assert "0066812345678" in payload
    assert "540550.00" in payload  # tag 54 len 05 value "50.00"


def test_payload_for_national_id():
    payload = generate_promptpay_payload("1234567890123", 20)
    assert "02131234567890123" in payload


def test_static_qr_without_amount_uses_point_of_initiation_11():
    payload = generate_promptpay_payload("0812345678")
    assert "010211" in payload


def test_invalid_target_raises():
    with pytest.raises(ValueError):
        generate_promptpay_payload("12345")


def test_settings_promptpay_qr_endpoint():
    update = client.put(
        "/api/settings",
        json={"shop_type": "individual", "shop_name": "ร้านทดสอบ", "address": "", "tax_id": "", "promptpay_id": "0812345678"},
    )
    assert update.status_code == 200, update.text
    assert update.json()["promptpay_id"] == "0812345678"

    qr = client.get("/api/settings/promptpay-qr?amount=99.50")
    assert qr.status_code == 200, qr.text
    assert qr.json()["payload"].startswith("000201")


def test_promptpay_qr_fails_without_configured_id():
    res = client.get("/api/settings/promptpay-qr?amount=10")
    assert res.status_code == 400
