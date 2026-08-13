from sqlalchemy.orm import Session

from app.models import LoyaltyCustomer


def find_or_create_customer(db: Session, phone: str, name: str = "") -> LoyaltyCustomer:
    phone = phone.strip()
    customer = db.query(LoyaltyCustomer).filter(LoyaltyCustomer.phone == phone).first()
    if customer is None:
        customer = LoyaltyCustomer(phone=phone, name=name)
        db.add(customer)
        db.flush()
    elif name and not customer.name:
        customer.name = name
    return customer
