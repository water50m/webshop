from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_active_shop_membership, get_current_user, require_role
from app.models import Product, PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus, ShopMembership, Supplier, User, UserRole
from app.services.purchasing import receive_purchase_order

router = APIRouter(
    prefix="/api/suppliers",
    tags=["suppliers"],
    dependencies=[Depends(get_current_user)],
)
manage_only = Depends(require_role(UserRole.owner, UserRole.manager))


class SupplierOut(BaseModel):
    id: int
    name: str
    phone: str
    address: str
    note: str


class SupplierIn(BaseModel):
    name: str
    phone: str = ""
    address: str = ""
    note: str = ""


def _serialize_supplier(s: Supplier) -> SupplierOut:
    return SupplierOut(id=s.id, name=s.name, phone=s.phone, address=s.address, note=s.note)


@router.get("", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    return [_serialize_supplier(s) for s in db.query(Supplier).filter_by(shop_id=membership.shop_id).order_by(Supplier.name).all()]


@router.post("", response_model=SupplierOut, dependencies=[manage_only])
def create_supplier(payload: SupplierIn, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    supplier = Supplier(shop_id=membership.shop_id, **payload.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return _serialize_supplier(supplier)


@router.put("/{supplier_id}", response_model=SupplierOut, dependencies=[manage_only])
def update_supplier(supplier_id: int, payload: SupplierIn, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    supplier = db.query(Supplier).filter_by(id=supplier_id, shop_id=membership.shop_id).first()
    if supplier is None:
        raise HTTPException(status_code=404, detail="ไม่พบซัพพลายเออร์นี้")
    for key, value in payload.model_dump().items():
        setattr(supplier, key, value)
    db.commit()
    db.refresh(supplier)
    return _serialize_supplier(supplier)


po_router = APIRouter(
    prefix="/api/purchase-orders",
    tags=["purchase-orders"],
    dependencies=[Depends(get_current_user)],
)


class PurchaseOrderItemOut(BaseModel):
    id: int
    product_id: int | None
    product_name: str
    quantity: int
    unit_cost: float


class PurchaseOrderItemIn(BaseModel):
    product_id: int
    quantity: int
    unit_cost: float


class PurchaseOrderOut(BaseModel):
    id: int
    supplier_id: int
    supplier_name: str
    status: str
    note: str
    created_at: str
    received_at: str | None
    items: list[PurchaseOrderItemOut]
    total_cost: float


class PurchaseOrderIn(BaseModel):
    supplier_id: int
    note: str = ""
    items: list[PurchaseOrderItemIn]


def _serialize_po(po: PurchaseOrder) -> PurchaseOrderOut:
    items = [
        PurchaseOrderItemOut(
            id=i.id, product_id=i.product_id, product_name=i.product_name, quantity=i.quantity, unit_cost=float(i.unit_cost)
        )
        for i in po.items
    ]
    return PurchaseOrderOut(
        id=po.id,
        supplier_id=po.supplier_id,
        supplier_name=po.supplier.name if po.supplier else "",
        status=po.status.value,
        note=po.note,
        created_at=po.created_at.isoformat(),
        received_at=po.received_at.isoformat() if po.received_at else None,
        items=items,
        total_cost=sum(float(i.unit_cost) * i.quantity for i in po.items),
    )


@po_router.get("", response_model=list[PurchaseOrderOut])
def list_purchase_orders(status: str | None = None, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    query = db.query(PurchaseOrder).filter(PurchaseOrder.shop_id == membership.shop_id)
    if status:
        query = query.filter(PurchaseOrder.status == PurchaseOrderStatus(status))
    return [_serialize_po(po) for po in query.order_by(PurchaseOrder.created_at.desc()).all()]


@po_router.post("", response_model=PurchaseOrderOut, dependencies=[manage_only])
def create_purchase_order(payload: PurchaseOrderIn, db: Session = Depends(get_db), user: User = Depends(get_current_user), membership: ShopMembership = Depends(get_active_shop_membership)):
    supplier = db.query(Supplier).filter_by(id=payload.supplier_id, shop_id=membership.shop_id).first()
    if supplier is None:
        raise HTTPException(status_code=404, detail="ไม่พบซัพพลายเออร์นี้")
    po = PurchaseOrder(shop_id=membership.shop_id, supplier_id=supplier.id, note=payload.note, created_by_user_id=user.id)
    db.add(po)
    db.flush()
    for item in payload.items:
        product = db.query(Product).filter_by(id=item.product_id, shop_id=membership.shop_id).first()
        if product is None:
            raise HTTPException(status_code=404, detail="ไม่พบสินค้านี้")
        db.add(
            PurchaseOrderItem(
                purchase_order_id=po.id,
                product_id=product.id,
                product_name=product.name,
                quantity=item.quantity,
                unit_cost=item.unit_cost,
            )
        )
    db.commit()
    db.refresh(po)
    return _serialize_po(po)


@po_router.post("/{po_id}/receive", response_model=PurchaseOrderOut, dependencies=[manage_only])
def receive_purchase_order_endpoint(po_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user), membership: ShopMembership = Depends(get_active_shop_membership)):
    po = db.query(PurchaseOrder).filter_by(id=po_id, shop_id=membership.shop_id).first()
    if po is None:
        raise HTTPException(status_code=404, detail="ไม่พบใบสั่งซื้อนี้")
    try:
        receive_purchase_order(db, po, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(po)
    return _serialize_po(po)


@po_router.post("/{po_id}/cancel", response_model=PurchaseOrderOut, dependencies=[manage_only])
def cancel_purchase_order(po_id: int, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    po = db.query(PurchaseOrder).filter_by(id=po_id, shop_id=membership.shop_id).first()
    if po is None:
        raise HTTPException(status_code=404, detail="ไม่พบใบสั่งซื้อนี้")
    if po.status == PurchaseOrderStatus.received:
        raise HTTPException(status_code=400, detail="ใบสั่งซื้อนี้รับสินค้าไปแล้ว ยกเลิกไม่ได้")
    po.status = PurchaseOrderStatus.cancelled
    db.commit()
    db.refresh(po)
    return _serialize_po(po)
