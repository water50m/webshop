from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.settings import get_or_create_settings
from app.db import get_db
from app.deps import require_role
from app.models import Product, Sale, SaleStatus, Shift, UserRole
from app.services.accounting import build_summary, get_daily_report, get_pos_income, get_product_performance

router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
    dependencies=[Depends(require_role(UserRole.owner, UserRole.manager))],
)


class SummaryOut(BaseModel):
    year: int
    month: int | None
    income: float
    cogs: float
    gross_profit: float
    expense_breakdown: dict[str, float]
    total_expense: float
    net_profit: float
    shop_type: str
    tax_estimate: float
    tax_disclaimer: str


@router.get("/summary", response_model=SummaryOut)
def get_summary(year: int, month: int | None = None, db: Session = Depends(get_db)):
    settings = get_or_create_settings(db)
    summary = build_summary(db, settings.shop_type, year, month)
    return SummaryOut(
        year=summary["year"],
        month=summary["month"],
        income=float(summary["income"]),
        cogs=float(summary["cogs"]),
        gross_profit=float(summary["gross_profit"]),
        expense_breakdown={k: float(v) for k, v in summary["expense_breakdown"].items()},
        total_expense=float(summary["total_expense"]),
        net_profit=float(summary["net_profit"]),
        shop_type=summary["shop_type"],
        tax_estimate=float(summary["tax_estimate"]),
        tax_disclaimer=summary["tax_disclaimer"],
    )


class ProductPerformanceOut(BaseModel):
    product_id: int | None
    name: str
    sku: str
    quantity_sold: int
    revenue: float


class DailyReportDayOut(BaseModel):
    date: str
    income: float
    expense: float
    order_count: int
    top_product_quantities: dict[str, int]


class AllTimeTopProductOut(BaseModel):
    name: str
    sku: str
    quantity_sold: int


class ReportOrderOut(BaseModel):
    id: int
    receipt_no: int | None
    completed_at: str
    revenue: float
    source: str
    reference: str


class DailyReportOut(BaseModel):
    days: list[DailyReportDayOut]
    top_products: list[AllTimeTopProductOut]
    orders: list[ReportOrderOut]


@router.get("/products", response_model=list[ProductPerformanceOut])
def get_product_performance_report(start: datetime, end: datetime, db: Session = Depends(get_db)):
    rows = get_product_performance(db, start, end)
    return [
        ProductPerformanceOut(
            product_id=r["product_id"], name=r["name"], sku=r["sku"], quantity_sold=r["quantity_sold"], revenue=float(r["revenue"])
        )
        for r in rows
    ]


@router.get("/daily", response_model=DailyReportOut)
def get_daily_report_data(start: datetime, end: datetime, db: Session = Depends(get_db)):
    return get_daily_report(db, start, end)


class LowStockProductOut(BaseModel):
    id: int
    name: str
    sku: str
    stock_quantity: int
    low_stock_threshold: int


class OpenShiftOut(BaseModel):
    id: int
    opened_by_name: str
    opening_cash: float
    opened_at: str


class TodaySummaryOut(BaseModel):
    sale_count: int
    total_revenue: float
    low_stock_products: list[LowStockProductOut]
    open_shifts: list[OpenShiftOut]


@router.get("/today", response_model=TodaySummaryOut)
def get_today_summary(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    start = datetime(now.year, now.month, now.day)
    end = start + timedelta(days=1)

    sale_count = (
        db.query(Sale)
        .filter(Sale.status == SaleStatus.completed, Sale.completed_at >= start, Sale.completed_at < end)
        .count()
    )
    total_revenue = float(get_pos_income(db, start, end))

    low_stock = (
        db.query(Product)
        .filter(Product.stock_quantity <= Product.low_stock_threshold)
        .order_by(Product.stock_quantity)
        .all()
    )
    open_shifts = db.query(Shift).filter(Shift.closed_at.is_(None)).all()

    return TodaySummaryOut(
        sale_count=sale_count,
        total_revenue=total_revenue,
        low_stock_products=[
            LowStockProductOut(
                id=p.id, name=p.name, sku=p.sku, stock_quantity=p.stock_quantity, low_stock_threshold=p.low_stock_threshold
            )
            for p in low_stock
        ],
        open_shifts=[
            OpenShiftOut(
                id=s.id,
                opened_by_name=s.opened_by.display_name or s.opened_by.username,
                opening_cash=float(s.opening_cash),
                opened_at=s.opened_at.isoformat(),
            )
            for s in open_shifts
        ],
    )
