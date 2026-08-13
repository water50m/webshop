import os

os.environ["DATABASE_URL"] = "sqlite:///./test_product_image_upload.db"

import pytest
from fastapi.testclient import TestClient

from app.api.products import UPLOAD_DIR
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User, UserRole
from app.services.auth import hash_password

client = TestClient(app)

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(User(username="owner", password_hash=hash_password("ownerpass"), display_name="Owner", role=UserRole.owner))
    db.add(User(username="cashier1", password_hash=hash_password("pass1234"), display_name="Cashier", role=UserRole.cashier))
    db.commit()
    db.close()
    login = client.post("/api/auth/login", json={"username": "owner", "password": "ownerpass"})
    assert login.status_code == 200, login.text
    yield
    Base.metadata.drop_all(bind=engine)
    for f in UPLOAD_DIR.glob("*"):
        f.unlink()


def create_product(sku="SAL1", name="สลัดผัก", price=50):
    res = client.post("/api/products", json={"sku": sku, "name": name, "price": price})
    assert res.status_code == 200, res.text
    return res.json()


def test_upload_image_sets_image_url():
    product = create_product()
    res = client.post(
        f"/api/products/{product['id']}/image",
        files={"file": ("test.png", PNG_BYTES, "image/png")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["image_url"].startswith("/uploads/products/")
    assert body["image_url"].endswith(".png")

    fetched = client.get(f"/api/products/lookup?code=SAL1").json()
    assert fetched["image_url"] == body["image_url"]


def test_upload_replaces_previous_file():
    product = create_product()
    first = client.post(
        f"/api/products/{product['id']}/image",
        files={"file": ("a.png", PNG_BYTES, "image/png")},
    ).json()
    first_path = UPLOAD_DIR / first["image_url"].split("/")[-1]
    assert first_path.exists()

    second = client.post(
        f"/api/products/{product['id']}/image",
        files={"file": ("b.png", PNG_BYTES, "image/png")},
    ).json()
    assert second["image_url"] != first["image_url"]
    assert not first_path.exists()


def test_upload_rejects_non_image_content_type():
    product = create_product()
    res = client.post(
        f"/api/products/{product['id']}/image",
        files={"file": ("a.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 400


def test_upload_rejects_oversized_file():
    product = create_product()
    big = b"\x00" * (5 * 1024 * 1024 + 1)
    res = client.post(
        f"/api/products/{product['id']}/image",
        files={"file": ("a.png", big, "image/png")},
    )
    assert res.status_code == 400


def test_only_owner_or_manager_can_upload_image():
    product = create_product()
    cashier_login = client.post("/api/auth/login", json={"username": "cashier1", "password": "pass1234"})
    assert cashier_login.status_code == 200

    res = client.post(
        f"/api/products/{product['id']}/image",
        files={"file": ("a.png", PNG_BYTES, "image/png")},
    )
    assert res.status_code == 403
