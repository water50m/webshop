from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_active_shop_membership, get_current_user, require_role
from app.models import Ingredient, RecipeItem, ShopMembership, StockMovementReason, User, UserRole
from app.services.stock import adjust_ingredient_stock

router = APIRouter(
    prefix="/api/ingredients",
    tags=["ingredients"],
    dependencies=[Depends(get_current_user)],
)
manage_only = Depends(require_role(UserRole.owner, UserRole.manager))


class IngredientOut(BaseModel):
    id: int
    name: str
    unit: str
    stock_quantity: float
    low_stock_threshold: float


class IngredientIn(BaseModel):
    name: str
    unit: str = ""
    low_stock_threshold: float = 0


class StockAdjustmentIn(BaseModel):
    change: float
    note: str = ""


def _serialize(ingredient: Ingredient) -> IngredientOut:
    return IngredientOut(
        id=ingredient.id,
        name=ingredient.name,
        unit=ingredient.unit,
        stock_quantity=float(ingredient.stock_quantity),
        low_stock_threshold=float(ingredient.low_stock_threshold),
    )


@router.get("", response_model=list[IngredientOut])
def list_ingredients(db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    return [_serialize(i) for i in db.query(Ingredient).filter_by(shop_id=membership.shop_id).order_by(Ingredient.name).all()]


@router.post("", response_model=IngredientOut, dependencies=[manage_only])
def create_ingredient(payload: IngredientIn, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    ingredient = Ingredient(shop_id=membership.shop_id, name=payload.name, unit=payload.unit, low_stock_threshold=payload.low_stock_threshold)
    db.add(ingredient)
    db.commit()
    db.refresh(ingredient)
    return _serialize(ingredient)


@router.put("/{ingredient_id}", response_model=IngredientOut, dependencies=[manage_only])
def update_ingredient(ingredient_id: int, payload: IngredientIn, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    ingredient = db.query(Ingredient).filter_by(id=ingredient_id, shop_id=membership.shop_id).first()
    if ingredient is None:
        raise HTTPException(status_code=404, detail="ไม่พบวัตถุดิบนี้")
    ingredient.name = payload.name
    ingredient.unit = payload.unit
    ingredient.low_stock_threshold = payload.low_stock_threshold
    db.commit()
    db.refresh(ingredient)
    return _serialize(ingredient)


@router.delete("/{ingredient_id}", dependencies=[manage_only])
def delete_ingredient(ingredient_id: int, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    ingredient = db.query(Ingredient).filter_by(id=ingredient_id, shop_id=membership.shop_id).first()
    if ingredient is None:
        raise HTTPException(status_code=404, detail="ไม่พบวัตถุดิบนี้")
    used = db.query(RecipeItem).filter(RecipeItem.ingredient_id == ingredient_id).first()
    if used is not None:
        raise HTTPException(status_code=400, detail="วัตถุดิบนี้ถูกใช้ในสูตรสินค้าอยู่ ลบไม่ได้")
    db.delete(ingredient)
    db.commit()
    return {"ok": True}


@router.post("/{ingredient_id}/stock-adjustment", response_model=IngredientOut, dependencies=[manage_only])
def adjust_ingredient_stock_endpoint(
    ingredient_id: int,
    payload: StockAdjustmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    membership: ShopMembership = Depends(get_active_shop_membership),
):
    ingredient = db.query(Ingredient).filter_by(id=ingredient_id, shop_id=membership.shop_id).first()
    if ingredient is None:
        raise HTTPException(status_code=404, detail="ไม่พบวัตถุดิบนี้")
    reason = StockMovementReason.restock if payload.change > 0 else StockMovementReason.adjustment
    try:
        adjust_ingredient_stock(db, ingredient, payload.change, reason, note=payload.note, created_by=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(ingredient)
    return _serialize(ingredient)
