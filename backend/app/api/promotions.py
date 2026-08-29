from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_active_shop_membership, get_current_user, require_role
from app.models import DiscountType, Product, Promotion, PromotionItem, PromotionType, ShopMembership, User, UserRole
from app.services.promotions import is_promotion_active

router = APIRouter(
    prefix="/api/promotions",
    tags=["promotions"],
    dependencies=[Depends(require_role(UserRole.owner, UserRole.manager))],
)


class PromotionItemIn(BaseModel):
    product_id: int
    quantity: int = 1


class PromotionItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int


class PromotionIn(BaseModel):
    name: str
    type: PromotionType
    is_active: bool = True
    discount_type: DiscountType | None = None
    discount_value: float | None = None
    bundle_price: float | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    items: list[PromotionItemIn]


class PromotionOut(BaseModel):
    id: int
    name: str
    type: str
    is_active: bool
    is_active_now: bool
    discount_type: str | None
    discount_value: float | None
    bundle_price: float | None
    start_at: datetime | None
    end_at: datetime | None
    items: list[PromotionItemOut]


def _serialize(promotion: Promotion) -> PromotionOut:
    return PromotionOut(
        id=promotion.id,
        name=promotion.name,
        type=promotion.type.value,
        is_active=promotion.is_active,
        is_active_now=is_promotion_active(promotion),
        discount_type=promotion.discount_type.value if promotion.discount_type else None,
        discount_value=float(promotion.discount_value) if promotion.discount_value is not None else None,
        bundle_price=float(promotion.bundle_price) if promotion.bundle_price is not None else None,
        start_at=promotion.start_at,
        end_at=promotion.end_at,
        items=[
            PromotionItemOut(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name,
                quantity=item.quantity,
            )
            for item in promotion.items
        ],
    )


def _validate_payload(payload: PromotionIn, db: Session, shop_id: int) -> None:
    if not payload.items:
        raise HTTPException(status_code=400, detail="ต้องมีสินค้าอย่างน้อย 1 รายการ")
    if payload.type == PromotionType.time_discount:
        if len(payload.items) != 1:
            raise HTTPException(status_code=400, detail="ลดราคาชั่วคราวต้องเลือกสินค้าแค่ 1 รายการ")
        if payload.discount_type is None or payload.discount_value is None:
            raise HTTPException(status_code=400, detail="ต้องระบุประเภทและจำนวนส่วนลด")
    if payload.type == PromotionType.bundle and payload.bundle_price is None:
        raise HTTPException(status_code=400, detail="ต้องระบุราคาเซ็ต")
    for item_in in payload.items:
        if db.query(Product).filter_by(id=item_in.product_id, shop_id=shop_id).first() is None:
            raise HTTPException(status_code=400, detail=f"Product {item_in.product_id} not found")


@router.get("", response_model=list[PromotionOut])
def list_promotions(db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    return [_serialize(p) for p in db.query(Promotion).filter_by(shop_id=membership.shop_id).order_by(Promotion.created_at.desc()).all()]


@router.post("", response_model=PromotionOut)
def create_promotion(payload: PromotionIn, db: Session = Depends(get_db), user: User = Depends(get_current_user), membership: ShopMembership = Depends(get_active_shop_membership)):
    _validate_payload(payload, db, membership.shop_id)
    promotion = Promotion(
        shop_id=membership.shop_id,
        name=payload.name,
        type=payload.type,
        is_active=payload.is_active,
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
        bundle_price=payload.bundle_price,
        start_at=payload.start_at,
        end_at=payload.end_at,
        created_by_user_id=user.id,
    )
    db.add(promotion)
    db.flush()
    for item_in in payload.items:
        db.add(PromotionItem(promotion_id=promotion.id, product_id=item_in.product_id, quantity=item_in.quantity))
    db.commit()
    db.refresh(promotion)
    return _serialize(promotion)


@router.put("/{promotion_id}", response_model=PromotionOut)
def update_promotion(promotion_id: int, payload: PromotionIn, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    promotion = db.query(Promotion).filter_by(id=promotion_id, shop_id=membership.shop_id).first()
    if promotion is None:
        raise HTTPException(status_code=404, detail="Promotion not found")
    _validate_payload(payload, db, membership.shop_id)

    promotion.name = payload.name
    promotion.type = payload.type
    promotion.is_active = payload.is_active
    promotion.discount_type = payload.discount_type
    promotion.discount_value = payload.discount_value
    promotion.bundle_price = payload.bundle_price
    promotion.start_at = payload.start_at
    promotion.end_at = payload.end_at

    for item in list(promotion.items):
        db.delete(item)
    db.flush()
    for item_in in payload.items:
        db.add(PromotionItem(promotion_id=promotion.id, product_id=item_in.product_id, quantity=item_in.quantity))

    db.commit()
    db.refresh(promotion)
    return _serialize(promotion)


@router.post("/{promotion_id}/toggle", response_model=PromotionOut)
def toggle_promotion(promotion_id: int, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    promotion = db.query(Promotion).filter_by(id=promotion_id, shop_id=membership.shop_id).first()
    if promotion is None:
        raise HTTPException(status_code=404, detail="Promotion not found")
    promotion.is_active = not promotion.is_active
    db.commit()
    db.refresh(promotion)
    return _serialize(promotion)
