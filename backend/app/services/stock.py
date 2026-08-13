from sqlalchemy.orm import Session

from app.models import Ingredient, IngredientMovement, Product, StockMovement, StockMovementReason, User


def adjust_stock(
    db: Session,
    product: Product,
    change: int,
    reason: StockMovementReason,
    note: str = "",
    allow_negative: bool = False,
    created_by: User | None = None,
) -> StockMovement:
    new_quantity = product.stock_quantity + change
    if new_quantity < 0:
        if not allow_negative:
            raise ValueError(f"สต๊อกไม่พอ: {product.name} เหลือ {product.stock_quantity}")
        new_quantity = 0
        change = -product.stock_quantity

    product.stock_quantity = new_quantity
    movement = StockMovement(
        product_id=product.id,
        change=change,
        reason=reason,
        note=note,
        created_by_user_id=created_by.id if created_by else None,
    )
    db.add(movement)
    return movement


def adjust_ingredient_stock(
    db: Session,
    ingredient: Ingredient,
    change: float,
    reason: StockMovementReason,
    note: str = "",
    allow_negative: bool = False,
    created_by: User | None = None,
) -> IngredientMovement:
    new_quantity = float(ingredient.stock_quantity) + change
    if new_quantity < 0:
        if not allow_negative:
            raise ValueError(f"วัตถุดิบไม่พอ: {ingredient.name} เหลือ {ingredient.stock_quantity}")
        new_quantity = 0
        change = -float(ingredient.stock_quantity)

    ingredient.stock_quantity = new_quantity
    movement = IngredientMovement(
        ingredient_id=ingredient.id,
        change=change,
        reason=reason,
        note=note,
        created_by_user_id=created_by.id if created_by else None,
    )
    db.add(movement)
    return movement
