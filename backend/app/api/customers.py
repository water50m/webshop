from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import LoyaltyCustomer

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
def list_customers(search: str | None = None, db: Session = Depends(get_db)):
    query = db.query(LoyaltyCustomer)
    if search:
        query = query.filter(
            (LoyaltyCustomer.phone.contains(search)) | (LoyaltyCustomer.name.contains(search))
        )
    return [_serialize(c) for c in query.order_by(LoyaltyCustomer.name).all()]


@router.get("/lookup", response_model=CustomerOut)
def lookup_customer(phone: str, db: Session = Depends(get_db)):
    customer = db.query(LoyaltyCustomer).filter(LoyaltyCustomer.phone == phone.strip()).first()
    if customer is None:
        raise HTTPException(status_code=404, detail="ไม่พบลูกค้าเบอร์นี้")
    return _serialize(customer)


@router.post("", response_model=CustomerOut)
def create_customer(payload: CustomerIn, db: Session = Depends(get_db)):
    existing = db.query(LoyaltyCustomer).filter(LoyaltyCustomer.phone == payload.phone.strip()).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="มีลูกค้าเบอร์นี้อยู่แล้ว")
    customer = LoyaltyCustomer(phone=payload.phone.strip(), name=payload.name)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return _serialize(customer)


@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, payload: CustomerIn, db: Session = Depends(get_db)):
    customer = db.get(LoyaltyCustomer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="ไม่พบลูกค้านี้")
    customer.phone = payload.phone.strip()
    customer.name = payload.name
    db.commit()
    db.refresh(customer)
    return _serialize(customer)
