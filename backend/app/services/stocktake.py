from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    Ingredient,
    InventoryMode,
    Product,
    ShopSettings,
    StockMovementReason,
    StocktakeLine,
    StocktakeSession,
    StocktakeStatus,
    User,
)
from app.services.stock import adjust_ingredient_stock, adjust_stock


def get_open_session(db: Session, shop_id: int) -> StocktakeSession | None:
    return db.query(StocktakeSession).filter(StocktakeSession.shop_id == shop_id, StocktakeSession.status == StocktakeStatus.open).first()


def open_session(db: Session, user: User, shop_id: int, note: str = "") -> StocktakeSession:
    if get_open_session(db, shop_id) is not None:
        raise ValueError("มีรอบนับสต๊อกที่เปิดอยู่แล้ว ต้องปิดรอบเดิมก่อน")

    settings = db.query(ShopSettings).filter_by(shop_id=shop_id).first()
    mode = settings.inventory_mode if settings else InventoryMode.simple
    entity_type = "ingredient" if mode == InventoryMode.recipe else "product"

    session = StocktakeSession(shop_id=shop_id, opened_by_user_id=user.id, note=note, entity_type=entity_type)
    db.add(session)
    db.flush()

    if entity_type == "ingredient":
        for ingredient in db.query(Ingredient).filter_by(shop_id=shop_id).order_by(Ingredient.name).all():
            db.add(
                StocktakeLine(
                    session_id=session.id,
                    ingredient_id=ingredient.id,
                    expected_quantity=float(ingredient.stock_quantity),
                )
            )
    else:
        for product in db.query(Product).filter_by(shop_id=shop_id).order_by(Product.name).all():
            db.add(
                StocktakeLine(
                    session_id=session.id,
                    product_id=product.id,
                    expected_quantity=float(product.stock_quantity),
                )
            )
    db.flush()
    return session


def submit_count(line: StocktakeLine, counted_quantity: float | None) -> StocktakeLine:
    line.counted_quantity = counted_quantity
    return line


def close_session(db: Session, session: StocktakeSession, user: User) -> dict:
    if session.status == StocktakeStatus.closed:
        raise ValueError("รอบนับสต๊อกนี้ปิดไปแล้ว")

    adjusted = 0
    skipped = 0
    for line in session.lines:
        if line.counted_quantity is None:
            skipped += 1
            continue
        diff = float(line.counted_quantity) - float(line.expected_quantity)
        if diff == 0:
            continue
        if line.product is not None:
            adjust_stock(
                db,
                line.product,
                int(round(diff)),
                StockMovementReason.stocktake,
                note=f"Stocktake #{session.id}",
                allow_negative=True,
                created_by=user,
            )
        elif line.ingredient is not None:
            adjust_ingredient_stock(
                db,
                line.ingredient,
                diff,
                StockMovementReason.stocktake,
                note=f"Stocktake #{session.id}",
                allow_negative=True,
                created_by=user,
            )
        adjusted += 1

    session.status = StocktakeStatus.closed
    session.closed_by_user_id = user.id
    session.closed_at = datetime.utcnow()
    return {"adjusted_count": adjusted, "skipped_count": skipped}
