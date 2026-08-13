import os

os.environ["DATABASE_URL"] = "sqlite:///./test_inventory_recipe_stocktake.db"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Product, User, UserRole
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
    client.post("/api/shifts/open", json={"opening_cash": 0})
    yield
    Base.metadata.drop_all(bind=engine)


def _set_inventory_mode(mode: str):
    res = client.put("/api/settings", json={"shop_type": "individual", "inventory_mode": mode})
    assert res.status_code == 200, res.text


def _create_product(sku: str, name: str, price: float = 100, stock: int = 0) -> dict:
    res = client.post("/api/products", json={"sku": sku, "name": name, "price": price, "low_stock_threshold": 1})
    assert res.status_code == 200, res.text
    product = res.json()
    if stock:
        client.post(f"/api/products/{product['id']}/stock-adjustment", json={"change": stock, "note": "initial"})
    return product


def _create_ingredient(name: str, unit: str = "กรัม", stock: float = 0) -> dict:
    res = client.post("/api/ingredients", json={"name": name, "unit": unit})
    assert res.status_code == 200, res.text
    ingredient = res.json()
    if stock:
        client.post(f"/api/ingredients/{ingredient['id']}/stock-adjustment", json={"change": stock, "note": "initial"})
    return ingredient


def _checkout(sale_id: int, amount: float):
    res = client.post(f"/api/pos/sales/{sale_id}/checkout", json={"payments": [{"method": "cash", "amount": amount}]})
    assert res.status_code == 200, res.text
    return res.json()


def test_simple_mode_deducts_product_stock_by_default():
    product = _create_product("SKU-S1", "น้ำเปล่า", price=10, stock=5)
    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU-S1", "quantity": 2})
    _checkout(sale["id"], 20)

    db = SessionLocal()
    refreshed = db.get(Product, product["id"])
    assert refreshed.stock_quantity == 3
    db.close()


def test_recipe_mode_deducts_ingredient_stock_and_leaves_product_stock_alone():
    _set_inventory_mode("recipe")
    coffee = _create_ingredient("เมล็ดกาแฟ", unit="กรัม", stock=1000)
    milk = _create_ingredient("นมสด", unit="มล.", stock=2000)
    product = _create_product("SKU-R1", "ลาเต้", price=60, stock=0)

    recipe = client.put(
        f"/api/products/{product['id']}/recipe",
        json=[
            {"ingredient_id": coffee["id"], "quantity_per_unit": 18},
            {"ingredient_id": milk["id"], "quantity_per_unit": 150},
        ],
    )
    assert recipe.status_code == 200, recipe.text

    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU-R1", "quantity": 2})
    _checkout(sale["id"], 120)

    ingredients = {i["id"]: i for i in client.get("/api/ingredients").json()}
    assert ingredients[coffee["id"]]["stock_quantity"] == 1000 - 18 * 2
    assert ingredients[milk["id"]]["stock_quantity"] == 2000 - 150 * 2

    db = SessionLocal()
    refreshed = db.get(Product, product["id"])
    assert refreshed.stock_quantity == 0  # untouched, product had no own stock check
    db.close()


def test_recipe_mode_falls_back_to_product_stock_when_no_recipe_defined():
    _set_inventory_mode("recipe")
    product = _create_product("SKU-R2", "น้ำขวด", price=15, stock=10)

    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU-R2", "quantity": 3})
    _checkout(sale["id"], 45)

    db = SessionLocal()
    refreshed = db.get(Product, product["id"])
    assert refreshed.stock_quantity == 7
    db.close()


def test_recipe_mode_void_restores_ingredient_stock():
    _set_inventory_mode("recipe")
    sugar = _create_ingredient("น้ำตาล", unit="กรัม", stock=500)
    product = _create_product("SKU-R3", "ชาเย็น", price=30, stock=0)
    client.put(f"/api/products/{product['id']}/recipe", json=[{"ingredient_id": sugar["id"], "quantity_per_unit": 20}])

    sale = client.post("/api/pos/sales").json()
    client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU-R3", "quantity": 2})
    _checkout(sale["id"], 60)

    after_sale = next(i for i in client.get("/api/ingredients").json() if i["id"] == sugar["id"])
    assert after_sale["stock_quantity"] == 460

    void = client.post(f"/api/pos/sales/{sale['id']}/void")
    assert void.status_code == 200, void.text

    after_void = next(i for i in client.get("/api/ingredients").json() if i["id"] == sugar["id"])
    assert after_void["stock_quantity"] == 500


def test_recipe_mode_refund_restores_ingredient_stock_partially():
    _set_inventory_mode("recipe")
    cup = _create_ingredient("แก้ว", unit="ชิ้น", stock=50)
    product = _create_product("SKU-R4", "โซดา", price=25, stock=0)
    client.put(f"/api/products/{product['id']}/recipe", json=[{"ingredient_id": cup["id"], "quantity_per_unit": 1}])

    sale = client.post("/api/pos/sales").json()
    add = client.post(f"/api/pos/sales/{sale['id']}/items", json={"code": "SKU-R4", "quantity": 4})
    item_id = add.json()["items"][0]["id"]
    checked_out = _checkout(sale["id"], 100)
    assert checked_out["items"][0]["id"] == item_id

    after_sale = next(i for i in client.get("/api/ingredients").json() if i["id"] == cup["id"])
    assert after_sale["stock_quantity"] == 46

    refund = client.post(f"/api/pos/sales/{sale['id']}/refund", json={"items": [{"item_id": item_id, "quantity": 1}]})
    assert refund.status_code == 200, refund.text

    after_refund = next(i for i in client.get("/api/ingredients").json() if i["id"] == cup["id"])
    assert after_refund["stock_quantity"] == 47


def test_stocktake_simple_mode_counts_products_and_skips_uncounted_lines():
    product_a = _create_product("SKU-T1", "ขนมปัง", price=20, stock=10)
    product_b = _create_product("SKU-T2", "นมกล่อง", price=18, stock=5)

    opened = client.post("/api/stocktake/sessions", json={"note": "นับประจำเดือน"})
    assert opened.status_code == 200, opened.text
    session = opened.json()
    assert session["entity_type"] == "product"
    assert {line["product_id"] for line in session["lines"]} == {product_a["id"], product_b["id"]}

    line_a = next(line for line in session["lines"] if line["product_id"] == product_a["id"])
    res = client.put(f"/api/stocktake/sessions/{session['id']}/lines/{line_a['id']}", json={"counted_quantity": 8})
    assert res.status_code == 200, res.text

    closed = client.post(f"/api/stocktake/sessions/{session['id']}/close")
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["adjusted_count"] == 1
    assert body["skipped_count"] == 1

    db = SessionLocal()
    refreshed_a = db.get(Product, product_a["id"])
    refreshed_b = db.get(Product, product_b["id"])
    assert refreshed_a.stock_quantity == 8
    assert refreshed_b.stock_quantity == 5  # uncounted line left untouched
    db.close()


def test_stocktake_recipe_mode_counts_ingredients():
    _set_inventory_mode("recipe")
    flour = _create_ingredient("แป้ง", unit="กรัม", stock=300)

    opened = client.post("/api/stocktake/sessions")
    assert opened.status_code == 200, opened.text
    session = opened.json()
    assert session["entity_type"] == "ingredient"
    assert {line["ingredient_id"] for line in session["lines"]} == {flour["id"]}

    line = session["lines"][0]
    client.put(f"/api/stocktake/sessions/{session['id']}/lines/{line['id']}", json={"counted_quantity": 280})
    closed = client.post(f"/api/stocktake/sessions/{session['id']}/close")
    assert closed.status_code == 200, closed.text

    ingredient = next(i for i in client.get("/api/ingredients").json() if i["id"] == flour["id"])
    assert ingredient["stock_quantity"] == 280


def test_stocktake_cannot_open_second_session_while_one_is_open():
    client.post("/api/stocktake/sessions")
    second = client.post("/api/stocktake/sessions")
    assert second.status_code == 400
    assert "เปิดอยู่แล้ว" in second.json()["detail"]


def test_ingredient_delete_blocked_while_used_in_recipe_then_allowed_after_removal():
    ingredient = _create_ingredient("เกลือ", unit="กรัม")
    product = _create_product("SKU-T3", "ไข่เจียว", price=40, stock=0)
    client.put(f"/api/products/{product['id']}/recipe", json=[{"ingredient_id": ingredient["id"], "quantity_per_unit": 2}])

    blocked = client.delete(f"/api/ingredients/{ingredient['id']}")
    assert blocked.status_code == 400

    client.put(f"/api/products/{product['id']}/recipe", json=[])
    allowed = client.delete(f"/api/ingredients/{ingredient['id']}")
    assert allowed.status_code == 200, allowed.text
