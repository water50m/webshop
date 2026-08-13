from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import DraftOrder, DraftOrderItem, DraftOrderStatus, Message, Product, StockMovementReason, User
from app.services.conversation_labels import set_label_slot
from app.services.meta_messenger import send_order_confirmation
from app.services.stock import adjust_stock

router = APIRouter(
    prefix="/api/draft-orders",
    tags=["draft-orders"],
    dependencies=[Depends(get_current_user)],
)


class DraftOrderItemOut(BaseModel):
    id: int
    product_id: int | None
    product_name: str | None
    matched_text: str
    quantity: int
    unit_price: float
    special_request: str


class DraftOrderOut(BaseModel):
    id: int
    conversation_id: int
    status: str
    note: str
    total: float
    items: list[DraftOrderItemOut]


class DraftOrderItemIn(BaseModel):
    product_id: int
    quantity: int = 1


class UpdateDraftOrderIn(BaseModel):
    note: str | None = None
    items: list[DraftOrderItemIn] | None = None


def _has_retained_order_source(db: Session, draft_order: DraftOrder) -> bool:
    """A staff-review draft is only valid while its originating order remains.

    Chat content is intentionally removed when a conversation is hidden or
    completed.  Older installations could leave the accompanying pending
    draft behind, which made it look like a new greeting already had an order.
    The source message is created just before the draft; a short grace period
    accommodates database timestamp precision without accepting a later,
    unrelated greeting as the source.
    """
    grace = timedelta(seconds=10)
    return (
        db.query(Message.id)
        .filter(
            Message.conversation_id == draft_order.conversation_id,
            Message.direction == "in",
            Message.created_at >= draft_order.created_at - grace,
            Message.created_at <= draft_order.updated_at + grace,
        )
        .first()
        is not None
    )


def _reject_stale_drafts(db: Session, draft_orders: list[DraftOrder]) -> list[DraftOrder]:
    """Dismiss orphaned pending drafts left after chat retention cleanup."""
    active: list[DraftOrder] = []
    changed = False
    for draft_order in draft_orders:
        if _has_retained_order_source(db, draft_order):
            active.append(draft_order)
        else:
            draft_order.status = DraftOrderStatus.rejected
            changed = True
    if changed:
        db.commit()
    return active


def _serialize(draft_order: DraftOrder) -> DraftOrderOut:
    return DraftOrderOut(
        id=draft_order.id,
        conversation_id=draft_order.conversation_id,
        status=draft_order.status.value,
        note=draft_order.note,
        total=sum(float(item.unit_price) * item.quantity for item in draft_order.items),
        items=[
            DraftOrderItemOut(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name if item.product else None,
                matched_text=item.matched_text,
                quantity=item.quantity,
                unit_price=float(item.unit_price),
                special_request=item.special_request,
            )
            for item in draft_order.items
        ],
    )


@router.get("", response_model=list[DraftOrderOut])
def list_draft_orders(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(DraftOrder)
    if status:
        query = query.filter(DraftOrder.status == DraftOrderStatus(status))
    drafts = query.order_by(DraftOrder.created_at.desc()).all()
    if status == DraftOrderStatus.pending.value:
        drafts = _reject_stale_drafts(db, drafts)
    return [_serialize(d) for d in drafts]


@router.get("/{draft_order_id}", response_model=DraftOrderOut)
def get_draft_order(draft_order_id: int, db: Session = Depends(get_db)):
    draft_order = db.get(DraftOrder, draft_order_id)
    if draft_order is None:
        raise HTTPException(status_code=404, detail="Draft order not found")
    return _serialize(draft_order)


@router.put("/{draft_order_id}", response_model=DraftOrderOut)
def update_draft_order(draft_order_id: int, payload: UpdateDraftOrderIn, db: Session = Depends(get_db)):
    draft_order = db.get(DraftOrder, draft_order_id)
    if draft_order is None:
        raise HTTPException(status_code=404, detail="Draft order not found")
    if draft_order.status != DraftOrderStatus.pending:
        raise HTTPException(status_code=400, detail="Only pending draft orders can be edited")
    if not _has_retained_order_source(db, draft_order):
        draft_order.status = DraftOrderStatus.rejected
        db.commit()
        raise HTTPException(status_code=409, detail="ร่างออเดอร์เก่าไม่มีข้อความสั่งซื้อที่อ้างอิงแล้ว")

    if payload.note is not None:
        draft_order.note = payload.note

    if payload.items is not None:
        for item in list(draft_order.items):
            db.delete(item)
        db.flush()
        for item_in in payload.items:
            product = db.get(Product, item_in.product_id)
            if product is None:
                raise HTTPException(status_code=400, detail=f"Product {item_in.product_id} not found")
            db.add(
                DraftOrderItem(
                    draft_order_id=draft_order.id,
                    product_id=product.id,
                    matched_text=product.name,
                    quantity=item_in.quantity,
                    unit_price=product.price,
                )
            )

    db.commit()
    db.refresh(draft_order)
    return _serialize(draft_order)


@router.post("/{draft_order_id}/confirm", response_model=DraftOrderOut)
def confirm_draft_order(
    draft_order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    draft_order = db.get(DraftOrder, draft_order_id)
    if draft_order is None:
        raise HTTPException(status_code=404, detail="Draft order not found")
    if draft_order.status != DraftOrderStatus.pending:
        raise HTTPException(status_code=400, detail="Only pending draft orders can be confirmed")
    if not _has_retained_order_source(db, draft_order):
        draft_order.status = DraftOrderStatus.rejected
        db.commit()
        raise HTTPException(status_code=409, detail="ร่างออเดอร์เก่าไม่มีข้อความสั่งซื้อที่อ้างอิงแล้ว")
    if not draft_order.items:
        raise HTTPException(status_code=400, detail="Cannot confirm an empty draft order")

    unavailable = []
    for item in draft_order.items:
        product = item.product
        if product is None:
            unavailable.append(item.matched_text)
        elif not product.is_available or (
            product.stock_mode != "unlimited" and product.stock_quantity < item.quantity
        ):
            unavailable.append(product.name)
    if unavailable:
        raise HTTPException(
            status_code=409,
            detail=f"สต็อกไม่พอหรือปิดขาย: {', '.join(unavailable)} กรุณาแก้ไขร่างออเดอร์ก่อนยืนยัน",
        )

    draft_order.status = DraftOrderStatus.confirmed
    draft_order.confirmed_at = datetime.utcnow()
    set_label_slot(db, draft_order.conversation, "primary", "รับออเดอร์แล้ว")
    draft_order.conversation.bill_count += 1
    for item in draft_order.items:
        if item.product is not None:
            adjust_stock(
                db,
                item.product,
                -item.quantity,
                StockMovementReason.channel_order_confirm,
                note=f"Confirm draft order #{draft_order.id}",
                created_by=user,
                allow_negative=False,
            )
    db.commit()
    db.refresh(draft_order)
    if send_order_confirmation(db, draft_order):
        db.commit()
    return _serialize(draft_order)


@router.post("/{draft_order_id}/reject", response_model=DraftOrderOut)
def reject_draft_order(draft_order_id: int, db: Session = Depends(get_db)):
    draft_order = db.get(DraftOrder, draft_order_id)
    if draft_order is None:
        raise HTTPException(status_code=404, detail="Draft order not found")
    if draft_order.status != DraftOrderStatus.pending:
        raise HTTPException(status_code=400, detail="Only pending draft orders can be rejected")

    draft_order.status = DraftOrderStatus.rejected
    db.commit()
    db.refresh(draft_order)
    return _serialize(draft_order)
