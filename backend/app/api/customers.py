from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_active_shop_membership, get_current_user
from app.models import LoyaltyCustomer, ShopMembership

router = APIRouter(
    prefix="/api/customers",
    tags=["customers"],
    dependencies=[Depends(get_current_user)],
)


class CustomerOut(BaseModel):
    id: int
    phone: str
    name: str
    points: int


class CustomerIn(BaseModel):
    phone: str
    name: str = ""


def _serialize(customer: LoyaltyCustomer) -> CustomerOut:
    return CustomerOut(id=customer.id, phone=customer.phone, name=customer.name, points=customer.points)


@router.get("", response_model=list[CustomerOut])
def list_customers(search: str | None = None, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    query = db.query(LoyaltyCustomer).filter(LoyaltyCustomer.shop_id == membership.shop_id)
    if search:
        query = query.filter(
            (LoyaltyCustomer.phone.contains(search)) | (LoyaltyCustomer.name.contains(search))
        )
    return [_serialize(c) for c in query.order_by(LoyaltyCustomer.name).all()]


@router.get("/lookup", response_model=CustomerOut)
def lookup_customer(phone: str, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    customer = db.query(LoyaltyCustomer).filter(LoyaltyCustomer.shop_id == membership.shop_id, LoyaltyCustomer.phone == phone.strip()).first()
    if customer is None:
        raise HTTPException(status_code=404, detail="ไม่พบลูกค้าเบอร์นี้")
    return _serialize(customer)


@router.post("", response_model=CustomerOut)
def create_customer(payload: CustomerIn, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    existing = db.query(LoyaltyCustomer).filter(LoyaltyCustomer.shop_id == membership.shop_id, LoyaltyCustomer.phone == payload.phone.strip()).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="มีลูกค้าเบอร์นี้อยู่แล้ว")
    customer = LoyaltyCustomer(shop_id=membership.shop_id, phone=payload.phone.strip(), name=payload.name)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return _serialize(customer)


@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, payload: CustomerIn, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    customer = db.query(LoyaltyCustomer).filter_by(id=customer_id, shop_id=membership.shop_id).first()
    if customer is None:
        raise HTTPException(status_code=404, detail="ไม่พบลูกค้านี้")
    customer.phone = payload.phone.strip()
    customer.name = payload.name
    db.commit()
    db.refresh(customer)
    return _serialize(customer)
