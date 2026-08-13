import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_role
from app.models import Ingredient, Product, ProductModifier, RecipeItem, StockMovementReason, User, UserRole
from app.services.promotions import get_discounted_price
from app.services.stock import adjust_stock

router = APIRouter(
    prefix="/api/products",
    tags=["products"],
    dependencies=[Depends(get_current_user)],
)
manage_only = Depends(require_role(UserRole.owner, UserRole.manager))

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "products"
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024


class ProductModifierOut(BaseModel):
    id: int
    name: str
    price_delta: float


class ProductModifierIn(BaseModel):
    name: str
    price_delta: float = 0


class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    category: str
    price: float
    cost_price: float
    stock_quantity: int
    stock_mode: str
    is_available: bool
    low_stock_threshold: int
    image_url: str | None
    show_in_menu_answer: bool
    discounted_price: float | None
    modifiers: list[ProductModifierOut]


class ProductIn(BaseModel):
    sku: str
    name: str
    category: str = ""
    price: float
    cost_price: float = 0
    stock_mode: Literal["tracked", "unlimited"] = "tracked"
    is_available: bool = True
    low_stock_threshold: int = 5
    image_url: str | None = None
    show_in_menu_answer: bool = True


class StockAdjustmentIn(BaseModel):
    change: int
    note: str = ""


class BulkRestockOut(BaseModel):
    adjusted_count: int
    change_per_product: int


def _serialize(db: Session, product: Product, user: User | None = None) -> ProductOut:
    can_see_cost = user is not None and user.role in (UserRole.owner, UserRole.manager)
    return ProductOut(
        id=product.id,
        sku=product.sku,
        name=product.name,
        category=product.category,
        price=float(product.price),
        cost_price=float(product.cost_price) if can_see_cost else 0,
        stock_quantity=product.stock_quantity,
        stock_mode=product.stock_mode,
        is_available=product.is_available,
        low_stock_threshold=product.low_stock_threshold,
        image_url=product.image_url,
        show_in_menu_answer=product.show_in_menu_answer,
        discounted_price=get_discounted_price(db, product),
        modifiers=[ProductModifierOut(id=m.id, name=m.name, price_delta=float(m.price_delta)) for m in product.modifiers],
    )


@router.get("", response_model=list[ProductOut])
def list_products(
    search: str | None = None,
    category: str | None = None,
    low_stock: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Product)
    if search:
        query = query.filter(or_(Product.sku.ilike(f"%{search}%"), Product.name.ilike(f"%{search}%")))
    if category:
        query = query.filter(Product.category == category)
    products = query.order_by(Product.name).all()
    if low_stock:
        products = [p for p in products if p.stock_mode == "tracked" and p.stock_quantity <= p.low_stock_threshold]
    return [_serialize(db, p, user) for p in products]


@router.get("/categories", response_model=list[str])
def list_categories(db: Session = Depends(get_db)):
    rows = db.query(Product.category).filter(Product.category != "").distinct().order_by(Product.category).all()
    return [r[0] for r in rows]


@router.get("/lookup", response_model=ProductOut)
def lookup_product(code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.sku == code).first()
    if product is None:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้าตามรหัสนี้")
    return _serialize(db, product, user)


@router.post("", response_model=ProductOut, dependencies=[manage_only])
def create_product(payload: ProductIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.query(Product).filter(Product.sku == payload.sku).first() is not None:
        raise HTTPException(status_code=400, detail="SKU นี้ถูกใช้ไปแล้ว")
    product = Product(
        sku=payload.sku,
        name=payload.name,
        category=payload.category,
        price=payload.price,
        cost_price=payload.cost_price,
        stock_mode=payload.stock_mode,
        is_available=payload.is_available,
        low_stock_threshold=payload.low_stock_threshold,
        image_url=payload.image_url,
        show_in_menu_answer=payload.show_in_menu_answer,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return _serialize(db, product, user)


@router.put("/{product_id}", response_model=ProductOut, dependencies=[manage_only])
def update_product(product_id: int, payload: ProductIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    existing = db.query(Product).filter(Product.sku == payload.sku, Product.id != product_id).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="SKU นี้ถูกใช้ไปแล้ว")
    product.sku = payload.sku
    product.name = payload.name
    product.category = payload.category
    product.price = payload.price
    product.cost_price = payload.cost_price
    product.stock_mode = payload.stock_mode
    product.is_available = payload.is_available
    product.low_stock_threshold = payload.low_stock_threshold
    product.image_url = payload.image_url
    product.show_in_menu_answer = payload.show_in_menu_answer
    db.commit()
    db.refresh(product)
    return _serialize(db, product, user)


@router.post("/{product_id}/image", response_model=ProductOut, dependencies=[manage_only])
def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    ext = ALLOWED_IMAGE_TYPES.get(file.content_type)
    if ext is None:
        raise HTTPException(status_code=400, detail="รองรับเฉพาะไฟล์ภาพ JPEG, PNG, WEBP หรือ GIF")
    contents = file.file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="ไฟล์ภาพต้องมีขนาดไม่เกิน 5MB")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    old_url = product.image_url
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / filename).write_bytes(contents)
    product.image_url = f"/uploads/products/{filename}"
    db.commit()
    db.refresh(product)

    if old_url and old_url.startswith("/uploads/products/"):
        old_path = UPLOAD_DIR / Path(old_url).name
        old_path.unlink(missing_ok=True)

    return _serialize(db, product, user)


@router.post("/{product_id}/stock-adjustment", response_model=ProductOut, dependencies=[manage_only])
def adjust_product_stock(
    product_id: int,
    payload: StockAdjustmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.stock_mode == "unlimited":
        raise HTTPException(status_code=400, detail="สินค้านี้ตั้งเป็นสต็อกไม่จำกัด จึงไม่ต้องปรับจำนวน")
    reason = StockMovementReason.restock if payload.change > 0 else StockMovementReason.adjustment
    try:
        adjust_stock(db, product, payload.change, reason, note=payload.note, created_by=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(product)
    return _serialize(db, product, user)


@router.post("/restock-all", response_model=BulkRestockOut, dependencies=[manage_only])
def restock_all_products(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Add ten units to every tracked product and keep an audit movement per product."""
    products = db.query(Product).filter(Product.stock_mode != "unlimited").all()
    for product in products:
        adjust_stock(
            db,
            product,
            10,
            StockMovementReason.restock,
            note="เติมสต็อกทั้งหมด +10",
            created_by=user,
        )
    db.commit()
    return BulkRestockOut(adjusted_count=len(products), change_per_product=10)


class RecipeItemOut(BaseModel):
    id: int
    ingredient_id: int
    ingredient_name: str
    unit: str
    quantity_per_unit: float


class RecipeItemIn(BaseModel):
    ingredient_id: int
    quantity_per_unit: float


def _serialize_recipe(product: Product) -> list[RecipeItemOut]:
    return [
        RecipeItemOut(
            id=r.id,
            ingredient_id=r.ingredient_id,
            ingredient_name=r.ingredient.name,
            unit=r.ingredient.unit,
            quantity_per_unit=float(r.quantity_per_unit),
        )
        for r in product.recipe_items
    ]


@router.get("/{product_id}/recipe", response_model=list[RecipeItemOut])
def get_recipe(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _serialize_recipe(product)


@router.put("/{product_id}/recipe", response_model=list[RecipeItemOut], dependencies=[manage_only])
def update_recipe(product_id: int, payload: list[RecipeItemIn], db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    for ri in payload:
        if db.get(Ingredient, ri.ingredient_id) is None:
            raise HTTPException(status_code=400, detail=f"Ingredient {ri.ingredient_id} not found")
    for existing in list(product.recipe_items):
        db.delete(existing)
    db.flush()
    for ri in payload:
        db.add(RecipeItem(product_id=product.id, ingredient_id=ri.ingredient_id, quantity_per_unit=ri.quantity_per_unit))
    db.commit()
    db.refresh(product)
    return _serialize_recipe(product)


@router.post("/{product_id}/modifiers", response_model=ProductOut, dependencies=[manage_only])
def create_modifier(
    product_id: int, payload: ProductModifierIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    db.add(ProductModifier(product_id=product.id, name=payload.name, price_delta=payload.price_delta))
    db.commit()
    db.refresh(product)
    return _serialize(db, product, user)


@router.put("/{product_id}/modifiers/{modifier_id}", response_model=ProductOut, dependencies=[manage_only])
def update_modifier(
    product_id: int,
    modifier_id: int,
    payload: ProductModifierIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    modifier = db.get(ProductModifier, modifier_id)
    if modifier is None or modifier.product_id != product_id:
        raise HTTPException(status_code=404, detail="ไม่พบตัวเลือกเสริมนี้")
    modifier.name = payload.name
    modifier.price_delta = payload.price_delta
    db.commit()
    db.refresh(product)
    return _serialize(db, product, user)


@router.delete("/{product_id}/modifiers/{modifier_id}", response_model=ProductOut, dependencies=[manage_only])
def delete_modifier(
    product_id: int, modifier_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    modifier = db.get(ProductModifier, modifier_id)
    if modifier is None or modifier.product_id != product_id:
        raise HTTPException(status_code=404, detail="ไม่พบตัวเลือกเสริมนี้")
    db.delete(modifier)
    db.commit()
    db.refresh(product)
    return _serialize(db, product, user)
