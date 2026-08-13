from datetime import datetime

from sqlalchemy.orm import Session

from app.models import PurchaseOrder, PurchaseOrderStatus, StockMovementReason, User
from app.services.stock import adjust_stock


def receive_purchase_order(db: Session, po: PurchaseOrder, user: User) -> PurchaseOrder:
    if po.status == PurchaseOrderStatus.received:
        raise ValueError("ใบสั่งซื้อนี้รับสินค้าไปแล้ว")
    if po.status == PurchaseOrderStatus.cancelled:
        raise ValueError("ใบสั่งซื้อนี้ถูกยกเลิกแล้ว")
    for item in po.items:
        if item.product is not None:
            adjust_stock(
                db,
                item.product,
                item.quantity,
                StockMovementReason.restock,
                note=f"รับสินค้าตามใบสั่งซื้อ #{po.id}",
                created_by=user,
            )
            item.product.cost_price = item.unit_cost
    po.status = PurchaseOrderStatus.received
    po.received_at = datetime.utcnow()
    return po
