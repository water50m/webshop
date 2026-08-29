from collections import OrderedDict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import accessible_channel_ids, get_current_user
from app.models import Conversation, DraftOrder, DraftOrderStatus, User

router = APIRouter(
    prefix="/api/order-history",
    tags=["order-history"],
    dependencies=[Depends(get_current_user)],
)


class OrderHistoryItemOut(BaseModel):
    product_name: str
    quantity: int
    unit_price: float


class OrderHistoryOrderOut(BaseModel):
    id: int
    confirmed_at: str
    total: float
    items: list[OrderHistoryItemOut]


class OrderHistoryCustomerOut(BaseModel):
    customer_id: int
    customer_display_name: str
    order_count: int
    total_spent: float
    last_order_at: str
    orders: list[OrderHistoryOrderOut]


@router.get("", response_model=list[OrderHistoryCustomerOut])
def list_chat_order_history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Confirmed chat orders grouped by customer; independent of Inbox messages."""
    confirmed_orders = (
        db.query(DraftOrder).join(Conversation)
        .filter(DraftOrder.status == DraftOrderStatus.confirmed)
        .filter(Conversation.channel_id.in_(accessible_channel_ids(user, db)))
        .order_by(DraftOrder.confirmed_at.desc(), DraftOrder.id.desc())
        .all()
    )
    customers: OrderedDict[int, dict] = OrderedDict()
    for order in confirmed_orders:
        conversation = order.conversation
        customer = conversation.customer
        total = sum(float(item.unit_price) * item.quantity for item in order.items)
        if customer.id not in customers:
            customers[customer.id] = {
                "customer_id": customer.id,
                "customer_display_name": customer.display_name or f"ลูกค้า #{customer.id}",
                "order_count": 0,
                "total_spent": 0.0,
                "last_order_at": order.confirmed_at.isoformat() if order.confirmed_at else order.created_at.isoformat(),
                "orders": [],
            }
        group = customers[customer.id]
        group["order_count"] += 1
        group["total_spent"] += total
        group["orders"].append(
            {
                "id": order.id,
                "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else order.created_at.isoformat(),
                "total": total,
                "items": [
                    {
                        "product_name": item.product.name if item.product else item.matched_text,
                        "quantity": item.quantity,
                        "unit_price": float(item.unit_price),
                    }
                    for item in order.items
                ],
            }
        )
    return list(customers.values())
