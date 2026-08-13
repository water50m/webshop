from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.settings import get_or_create_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import PaymentMethod, Product, Sale, SaleItem, SaleStatus, User, UserRole
from app.services import loyalty as loyalty_service
from app.services import pos as pos_service
from app.services import shifts as shift_service
from app.services.thermal_printer import build_escpos_receipt, send_to_printer

router = APIRouter(
    prefix="/api/pos",
    tags=["pos"],
    dependencies=[Depends(get_current_user)],
)


class SaleItemModifierOut(BaseModel):
    name: str
    price_delta: float


class SaleItemOut(BaseModel):
    id: int
    product_id: int | None
    product_name: str
    sku: str
    quantity: int
    unit_price: float
    discount_amount: float
    refunded_quantity: int
    modifiers: list[SaleItemModifierOut]
    line_total: float


class SalePaymentOut(BaseModel):
    method: str
    amount: float


class SaleOut(BaseModel):
    id: int
    receipt_no: int | None
    status: str
    payment_method: str | None
    discount_amount: float
    paid_amount: float | None
    change_amount: float | None
    note: str
    created_by_name: str | None
    completed_at: str | None
    items: list[SaleItemOut]
    payments: list[SalePaymentOut]
    subtotal: float
    total_discount: float
    promotion_discount: float
    total: float
    customer_phone: str | None
    customer_name: str | None
    points_earned: int
    points_redeemed: int
    customer_points_balance: int | None


class AddItemIn(BaseModel):
    code: str | None = None
    product_id: int | None = None
    quantity: int = 1
    modifier_ids: list[int] = []


class UpdateItemIn(BaseModel):
    quantity: int | None = None
    discount_amount: float | None = None


class UpdateSaleIn(BaseModel):
    discount_amount: float | None = None
    note: str | None = None


class PaymentIn(BaseModel):
    method: PaymentMethod
    amount: float


class CheckoutIn(BaseModel):
    payments: list[PaymentIn]
    customer_phone: str | None = None
    customer_name: str = ""
    redeem_points: int = 0


class RefundItemIn(BaseModel):
    item_id: int
    quantity: int


class RefundIn(BaseModel):
    items: list[RefundItemIn]
    note: str = ""


class VoidIn(BaseModel):
    note: str = ""


def _serialize(db: Session, sale: Sale) -> SaleOut:
    totals = pos_service.compute_totals(db, sale)
    return SaleOut(
        id=sale.id,
        receipt_no=sale.receipt_no,
        status=sale.status.value,
        payment_method=sale.payment_method.value if sale.payment_method else None,
        discount_amount=float(sale.discount_amount),
        paid_amount=float(sale.paid_amount) if sale.paid_amount is not None else None,
        change_amount=float(sale.change_amount) if sale.change_amount is not None else None,
        note=sale.note,
        created_by_name=sale.created_by.display_name or sale.created_by.username if sale.created_by else None,
        completed_at=sale.completed_at.isoformat() if sale.completed_at else None,
        items=[
            SaleItemOut(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                sku=item.sku,
                quantity=item.quantity,
                unit_price=float(item.unit_price),
                discount_amount=float(item.discount_amount),
                refunded_quantity=item.refunded_quantity,
                modifiers=[SaleItemModifierOut(name=m.name, price_delta=float(m.price_delta)) for m in item.modifiers],
                line_total=pos_service.line_total(item),
            )
            for item in sale.items
        ],
        payments=[SalePaymentOut(method=p.method.value, amount=float(p.amount)) for p in sale.payments],
        subtotal=totals["subtotal"],
        total_discount=totals["discount"],
        promotion_discount=totals["promotion_discount"],
        total=totals["total"],
        customer_phone=sale.customer.phone if sale.customer else None,
        customer_name=sale.customer.name if sale.customer else None,
        points_earned=sale.points_earned,
        points_redeemed=sale.points_redeemed,
        customer_points_balance=sale.customer.points if sale.customer else None,
    )


def _get_sale(db: Session, sale_id: int) -> Sale:
    sale = db.get(Sale, sale_id)
    if sale is None:
        raise HTTPException(status_code=404, detail="ไม่พบบิลนี้")
    return sale


@router.get("/sales", response_model=list[SaleOut])
def list_sales(
    status: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    receipt_no: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Sale)
    if status:
        query = query.filter(Sale.status == SaleStatus(status))
    if start is not None:
        query = query.filter(Sale.created_at >= start)
    if end is not None:
        query = query.filter(Sale.created_at < end)
    if receipt_no is not None:
        query = query.filter(Sale.receipt_no == receipt_no)
    return [_serialize(db, s) for s in query.order_by(Sale.created_at.desc()).all()]


@router.post("/sales", response_model=SaleOut)
def create_sale(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sale = pos_service.create_held_sale(db, user)
    db.commit()
    db.refresh(sale)
    return _serialize(db, sale)


@router.get("/sales/{sale_id}", response_model=SaleOut)
def get_sale(sale_id: int, db: Session = Depends(get_db)):
    sale = _get_sale(db, sale_id)
    return _serialize(db, sale)


@router.put("/sales/{sale_id}", response_model=SaleOut)
def update_sale(sale_id: int, payload: UpdateSaleIn, db: Session = Depends(get_db)):
    sale = _get_sale(db, sale_id)
    if sale.status != SaleStatus.held:
        raise HTTPException(status_code=400, detail="แก้ไขได้เฉพาะบิลที่ยังพักอยู่")
    if payload.discount_amount is not None:
        sale.discount_amount = payload.discount_amount
    if payload.note is not None:
        sale.note = payload.note
    db.commit()
    db.refresh(sale)
    return _serialize(db, sale)


@router.post("/sales/{sale_id}/items", response_model=SaleOut)
def add_sale_item(sale_id: int, payload: AddItemIn, db: Session = Depends(get_db)):
    sale = _get_sale(db, sale_id)
    if sale.status != SaleStatus.held:
        raise HTTPException(status_code=400, detail="แก้ไขได้เฉพาะบิลที่ยังพักอยู่")

    product = None
    if payload.product_id is not None:
        product = db.get(Product, payload.product_id)
    elif payload.code is not None:
        product = db.query(Product).filter(Product.sku == payload.code).first()
    if product is None:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า")

    try:
        pos_service.add_item(db, sale, product, payload.quantity, modifier_ids=payload.modifier_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(sale)
    return _serialize(db, sale)


@router.put("/sales/{sale_id}/items/{item_id}", response_model=SaleOut)
def update_sale_item(sale_id: int, item_id: int, payload: UpdateItemIn, db: Session = Depends(get_db)):
    sale = _get_sale(db, sale_id)
    if sale.status != SaleStatus.held:
        raise HTTPException(status_code=400, detail="แก้ไขได้เฉพาะบิลที่ยังพักอยู่")
    item = db.get(SaleItem, item_id)
    if item is None or item.sale_id != sale.id:
        raise HTTPException(status_code=404, detail="ไม่พบรายการนี้")
    pos_service.update_item(db, item, quantity=payload.quantity, discount_amount=payload.discount_amount)
    db.commit()
    db.refresh(sale)
    return _serialize(db, sale)


@router.delete("/sales/{sale_id}/items/{item_id}", response_model=SaleOut)
def remove_sale_item(sale_id: int, item_id: int, db: Session = Depends(get_db)):
    sale = _get_sale(db, sale_id)
    if sale.status != SaleStatus.held:
        raise HTTPException(status_code=400, detail="แก้ไขได้เฉพาะบิลที่ยังพักอยู่")
    item = db.get(SaleItem, item_id)
    if item is None or item.sale_id != sale.id:
        raise HTTPException(status_code=404, detail="ไม่พบรายการนี้")
    pos_service.remove_item(db, item)
    db.commit()
    db.refresh(sale)
    return _serialize(db, sale)


@router.post("/sales/{sale_id}/checkout", response_model=SaleOut)
def checkout_sale(
    sale_id: int,
    payload: CheckoutIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sale = _get_sale(db, sale_id)
    shift = shift_service.get_open_shift(db, user)
    if shift is None:
        raise HTTPException(status_code=400, detail="กรุณาเปิดกะก่อนทำการขาย")
    customer = None
    if payload.customer_phone:
        customer = loyalty_service.find_or_create_customer(db, payload.customer_phone, payload.customer_name)
    try:
        pos_service.checkout_sale(
            db,
            sale,
            [(p.method, p.amount) for p in payload.payments],
            user,
            shift,
            customer=customer,
            redeem_points=payload.redeem_points,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(sale)
    return _serialize(db, sale)


@router.post("/sales/{sale_id}/void", response_model=SaleOut)
def void_sale(sale_id: int, payload: VoidIn = VoidIn(), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sale = _get_sale(db, sale_id)
    if sale.status == SaleStatus.completed and user.role == UserRole.cashier:
        raise HTTPException(status_code=403, detail="การยกเลิกบิลที่ชำระเงินแล้วต้องให้ผู้จัดการหรือเจ้าของร้านทำรายการ")
    try:
        pos_service.void_sale(db, sale, user, note=payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(sale)
    return _serialize(db, sale)


class PrintThermalOut(BaseModel):
    ok: bool
    detail: str


@router.post("/sales/{sale_id}/print-thermal", response_model=PrintThermalOut)
def print_sale_thermal(sale_id: int, db: Session = Depends(get_db)):
    sale = _get_sale(db, sale_id)
    settings = get_or_create_settings(db)
    totals = pos_service.compute_totals(db, sale)
    data = build_escpos_receipt(sale, settings, totals)
    try:
        send_to_printer(settings.receipt_printer_ip, settings.receipt_printer_port, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PrintThermalOut(ok=True, detail="ส่งใบเสร็จไปที่เครื่องพิมพ์แล้ว")


@router.post("/sales/{sale_id}/refund", response_model=SaleOut)
def refund_sale(
    sale_id: int,
    payload: RefundIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role == UserRole.cashier:
        raise HTTPException(status_code=403, detail="การคืนเงินต้องให้ผู้จัดการหรือเจ้าของร้านทำรายการ")
    sale = _get_sale(db, sale_id)
    try:
        pos_service.refund_items(
            db, sale, [(i.item_id, i.quantity) for i in payload.items], user, note=payload.note
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(sale)
    return _serialize(db, sale)
