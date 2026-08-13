import os

os.environ["DATABASE_URL"] = "sqlite:///./test_thermal_printer.db"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User, UserRole
from app.services import thermal_printer
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


def _make_completed_sale() -> int:
    client.put("/api/settings", json={"shop_type": "individual", "shop_name": "ร้านทดสอบ"})
    client.post("/api/shifts/open", json={"opening_cash": 0})
    res = client.post("/api/products", json={"sku": "SKU1", "name": "สินค้าทดสอบ", "price": 100, "low_stock_threshold": 1})
    product = res.json()
    client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": 5, "note": "initial"})
    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU1", "quantity": 1})
    checkout = client.post(f"/api/pos/sales/{sale['id']}/checkout", json={"payments": [{"method": "cash", "amount": 100}]})
    assert checkout.status_code == 200, checkout.text
    return sale["id"]


def test_print_thermal_fails_without_printer_configured():
    sale_id = _make_completed_sale()
    res = client.post(f"/api/pos/sales/{sale_id}/print-thermal")
    assert res.status_code == 400
    assert "เครื่องพิมพ์" in res.json()["detail"]


def test_print_thermal_sends_escpos_bytes_when_configured(monkeypatch):
    sale_id = _make_completed_sale()
    client.put(
        "/api/settings",
        json={"shop_type": "individual", "shop_name": "ร้านทดสอบ", "receipt_printer_ip": "192.168.1.50", "receipt_printer_port": 9100},
    )

    captured = {}

    def fake_send(ip, port, data, timeout=5):
        captured["ip"] = ip
        captured["port"] = port
        captured["data"] = data

    monkeypatch.setattr(thermal_printer, "send_to_printer", fake_send)
    monkeypatch.setattr("app.api.pos.send_to_printer", fake_send)

    res = client.post(f"/api/pos/sales/{sale_id}/print-thermal")
    assert res.status_code == 200, res.text
    assert res.json()["ok"] is True
    assert captured["ip"] == "192.168.1.50"
    assert captured["port"] == 9100
    assert b"\x1b@" in captured["data"]  # ESC/POS init command present


def test_print_thermal_reports_connection_error(monkeypatch):
    sale_id = _make_completed_sale()
    client.put(
        "/api/settings",
        json={"shop_type": "individual", "shop_name": "ร้านทดสอบ", "receipt_printer_ip": "192.168.1.50", "receipt_printer_port": 9100},
    )

    def fake_send(ip, port, data, timeout=5):
        raise ValueError(f"เชื่อมต่อเครื่องพิมพ์ไม่สำเร็จ ({ip}:{port}): mock error")

    monkeypatch.setattr("app.api.pos.send_to_printer", fake_send)

    res = client.post(f"/api/pos/sales/{sale_id}/print-thermal")
    assert res.status_code == 400
    assert "เชื่อมต่อเครื่องพิมพ์ไม่สำเร็จ" in res.json()["detail"]


def test_build_escpos_receipt_encodes_thai_text():
    from app.models import Sale
    from app.services import pos as pos_service

    db = SessionLocal()
    res = client.post("/api/products", json={"sku": "SKU2", "name": "กาแฟเย็น", "price": 50, "low_stock_threshold": 1})
    product_id = res.json()["id"]
    client.post(f"/api/products/{product_id}/stock-adjustment", json={"change": 5, "note": "initial"})
    client.post("/api/shifts/open", json={"opening_cash": 0})
    sale_res = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale_res['id']}/items", json={"code": "SKU2", "quantity": 1})
    client.post(f"/api/pos/sales/{sale_res['id']}/checkout", json={"payments": [{"method": "cash", "amount": 50}]})

    sale = db.get(Sale, sale_res["id"])
    from app.api.settings import get_or_create_settings

    settings = get_or_create_settings(db)
    totals = pos_service.compute_totals(db, sale)
    data = thermal_printer.build_escpos_receipt(sale, settings, totals)
    assert "กาแฟเย็น".encode("cp874") in data
    db.close()
