import os

os.environ["DATABASE_URL"] = "sqlite:///./test_print_bridges.db"

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
    assert client.post("/api/auth/login", json={"username": "owner", "password": "ownerpass"}).status_code == 200
    yield
    Base.metadata.drop_all(bind=engine)


def test_bridge_heartbeat_command_and_result_flow():
    created = client.post("/api/bridges", json={"name": "เคาน์เตอร์หน้า"})
    assert created.status_code == 200, created.text
    bridge = created.json()
    token = bridge["device_token"]
    headers = {"X-Bridge-Token": token}

    heartbeat = client.post(
        "/api/bridge-device/heartbeat",
        headers=headers,
        json={"wifi_ssid": "SHOP-WIFI", "wifi_rssi": -48, "printer_connected": True, "printer_name": "Receipt-01", "printer_address": "AA:BB"},
    )
    assert heartbeat.status_code == 200
    listed = client.get("/api/bridges").json()[0]
    assert listed["is_online"] is True
    assert listed["printer_connected"] is True

    queued = client.post(f"/api/bridges/{bridge['id']}/commands", json={"command": "scan_bluetooth"})
    assert queued.status_code == 200
    command = client.get("/api/bridge-device/commands", headers=headers).json()["command"]
    assert command["command"] == "scan_bluetooth"

    result = client.post(
        f"/api/bridge-device/commands/{command['id']}/result",
        headers=headers,
        json={"ok": True, "result": {"devices": [{"name": "Printer", "address": "AA:BB", "rssi": -40}]}},
    )
    assert result.status_code == 200
    history = client.get(f"/api/bridges/{bridge['id']}/commands").json()
    assert history[0]["status"] == "succeeded"
    assert history[0]["result"]["devices"][0]["address"] == "AA:BB"


def test_wifi_password_is_removed_after_bridge_reports_result():
    bridge = client.post("/api/bridges", json={"name": "Bridge 1"}).json()
    headers = {"X-Bridge-Token": bridge["device_token"]}
    queued = client.post(
        f"/api/bridges/{bridge['id']}/commands",
        json={"command": "configure_wifi", "payload": {"ssid": "SHOP", "password": "secret-password"}},
    )
    command = client.get("/api/bridge-device/commands", headers=headers).json()["command"]
    assert command["payload"]["password"] == "secret-password"
    assert client.post(f"/api/bridge-device/commands/{command['id']}/result", headers=headers, json={"ok": True}).status_code == 200
    db = SessionLocal()
    from app.models import PrintBridgeCommand
    stored = db.get(PrintBridgeCommand, queued.json()["id"])
    assert stored.payload["password"] == "[removed]"
    db.close()
