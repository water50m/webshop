import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_active_shop_membership, get_current_user, require_role
from app.models import Expense, Product, Sale, SaleStatus, ShopMembership, UserRole

router = APIRouter(
    prefix="/api/export",
    tags=["export"],
    dependencies=[Depends(require_role(UserRole.owner, UserRole.manager))],
)


def _csv_response(filename: str, header: list[str], rows: list[list]) -> StreamingResponse:
    buffer = io.StringIO()
    buffer.write("﻿")  # BOM so Excel opens UTF-8 (Thai text) correctly
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/products")
def export_products(db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    products = db.query(Product).filter_by(shop_id=membership.shop_id).order_by(Product.name).all()
    rows = [
        [p.sku, p.name, p.category, float(p.price), float(p.cost_price), p.stock_quantity, p.low_stock_threshold]
        for p in products
    ]
    return _csv_response(
        "products.csv",
        ["SKU", "ชื่อสินค้า", "หมวดหมู่", "ราคาขาย", "ต้นทุน", "คงเหลือ", "จุดสั่งซื้อขั้นต่ำ"],
        rows,
    )


@router.get("/sales")
def export_sales(start: datetime | None = None, end: datetime | None = None, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    query = db.query(Sale).filter(Sale.shop_id == membership.shop_id, Sale.status == SaleStatus.completed)
    if start is not None:
        query = query.filter(Sale.completed_at >= start)
    if end is not None:
        query = query.filter(Sale.completed_at < end)
    rows = []
    for sale in query.order_by(Sale.completed_at).all():
        for item in sale.items:
            net_qty = item.quantity - item.refunded_quantity
            rows.append(
                [
                    sale.receipt_no,
                    sale.completed_at.isoformat() if sale.completed_at else "",
                    item.product_name,
                    item.sku,
                    net_qty,
                    float(item.unit_price),
                    sale.created_by.display_name or sale.created_by.username if sale.created_by else "",
                ]
            )
    return _csv_response(
        "sales.csv",
        ["เลขใบเสร็จ", "วันที่/เวลา", "สินค้า", "SKU", "จำนวนสุทธิ", "ราคาต่อหน่วย", "แคชเชียร์"],
        rows,
    )


@router.get("/expenses")
def export_expenses(start: datetime | None = None, end: datetime | None = None, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    query = db.query(Expense).filter(Expense.shop_id == membership.shop_id)
    if start is not None:
        query = query.filter(Expense.expense_date >= start.date())
    if end is not None:
        query = query.filter(Expense.expense_date < end.date())
    rows = [
        [e.expense_date.isoformat(), e.category.value, float(e.amount), e.description]
        for e in query.order_by(Expense.expense_date).all()
    ]
    return _csv_response("expenses.csv", ["วันที่", "หมวด", "จำนวนเงิน", "รายละเอียด"], rows)
