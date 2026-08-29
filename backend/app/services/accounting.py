from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    DraftOrder,
    DraftOrderItem,
    DraftOrderStatus,
    Channel,
    Conversation,
    Expense,
    ExpenseCategory,
    Sale,
    SaleStatus,
    ShopType,
)

PERSONAL_ALLOWANCE = Decimal("60000")

# อัตราภาษีเงินได้บุคคลธรรมดาแบบขั้นบันได (ปีภาษี 2567)
INDIVIDUAL_BRACKETS: list[tuple[Decimal, Decimal]] = [
    (Decimal("150000"), Decimal("0")),
    (Decimal("300000"), Decimal("0.05")),
    (Decimal("500000"), Decimal("0.10")),
    (Decimal("750000"), Decimal("0.15")),
    (Decimal("1000000"), Decimal("0.20")),
    (Decimal("2000000"), Decimal("0.25")),
    (Decimal("5000000"), Decimal("0.30")),
    (None, Decimal("0.35")),
]

# อัตราภาษีนิติบุคคล SME แบบง่าย
JURISTIC_BRACKETS: list[tuple[Decimal, Decimal]] = [
    (Decimal("300000"), Decimal("0")),
    (Decimal("3000000"), Decimal("0.15")),
    (None, Decimal("0.20")),
]

TAX_DISCLAIMER = "ประมาณการอย่างง่าย ไม่ใช่คำแนะนำทางภาษีที่แม่นยำ 100% โปรดตรวจสอบกับผู้เชี่ยวชาญด้านภาษี"


def _period_bounds(year: int, month: int | None) -> tuple[datetime, datetime]:
    if month is not None:
        start = datetime(year, month, 1)
        end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    else:
        start = datetime(year, 1, 1)
        end = datetime(year + 1, 1, 1)
    return start, end


def get_channel_order_income(db: Session, start: datetime, end: datetime, shop_id: int | None = None) -> Decimal:
    rows = (
        db.query(DraftOrderItem)
        .join(DraftOrder, DraftOrderItem.draft_order_id == DraftOrder.id)
        .join(Conversation, DraftOrder.conversation_id == Conversation.id)
        .join(Channel, Conversation.channel_id == Channel.id)
        .filter(
            DraftOrder.status == DraftOrderStatus.confirmed,
            DraftOrder.confirmed_at >= start,
            DraftOrder.confirmed_at < end,
            Channel.shop_id == shop_id,
        )
        .all()
    )
    return sum((Decimal(str(item.unit_price)) * item.quantity for item in rows), Decimal("0"))


def get_pos_income(db: Session, start: datetime, end: datetime, shop_id: int | None = None) -> Decimal:
    rows = (
        db.query(Sale)
        .filter(
            Sale.status == SaleStatus.completed,
            Sale.completed_at >= start,
            Sale.completed_at < end,
            Sale.shop_id == shop_id,
        )
        .all()
    )
    return sum((get_sale_revenue(sale) for sale in rows), Decimal("0"))


def get_sale_revenue(sale: Sale) -> Decimal:
    """Calculate the current net revenue for one completed POS sale."""
    subtotal = sum(
        (
            (Decimal(str(item.unit_price)) + sum((Decimal(str(m.price_delta)) for m in item.modifiers), Decimal("0")))
            * (item.quantity - item.refunded_quantity)
            - Decimal(str(item.discount_amount))
            for item in sale.items
        ),
        Decimal("0"),
    )
    return subtotal - Decimal(str(sale.discount_amount))


def get_income(db: Session, start: datetime, end: datetime, shop_id: int | None = None) -> Decimal:
    return get_channel_order_income(db, start, end, shop_id) + get_pos_income(db, start, end, shop_id)


def get_product_performance(db: Session, start: datetime, end: datetime, shop_id: int | None = None) -> list[dict]:
    sales = (
        db.query(Sale)
        .filter(
            Sale.status == SaleStatus.completed,
            Sale.completed_at >= start,
            Sale.completed_at < end,
            Sale.shop_id == shop_id,
        )
        .all()
    )
    stats: dict[object, dict] = {}
    for sale in sales:
        for item in sale.items:
            net_qty = item.quantity - item.refunded_quantity
            if net_qty <= 0:
                continue
            modifiers_total = sum((Decimal(str(m.price_delta)) for m in item.modifiers), Decimal("0"))
            revenue = (Decimal(str(item.unit_price)) + modifiers_total) * net_qty - Decimal(str(item.discount_amount))
            key = item.product_id if item.product_id is not None else f"deleted:{item.sku}"
            entry = stats.setdefault(
                key,
                {"product_id": item.product_id, "name": item.product_name, "sku": item.sku, "quantity_sold": 0, "revenue": Decimal("0")},
            )
            entry["quantity_sold"] += net_qty
            entry["revenue"] += revenue
    return sorted(stats.values(), key=lambda e: e["quantity_sold"], reverse=True)


def get_daily_report(db: Session, start: datetime, end: datetime, shop_id: int | None = None) -> dict:
    """Return daily sales/expense series, the all-time POS top five, and POS order revenue."""
    sales = (
        db.query(Sale)
        .filter(Sale.status == SaleStatus.completed, Sale.completed_at >= start, Sale.completed_at < end, Sale.shop_id == shop_id)
        .order_by(Sale.completed_at.desc())
        .all()
    )
    channel_orders = (
        db.query(DraftOrder)
        .join(Conversation, DraftOrder.conversation_id == Conversation.id)
        .join(Channel, Conversation.channel_id == Channel.id)
        .filter(
            DraftOrder.status == DraftOrderStatus.confirmed,
            DraftOrder.confirmed_at >= start,
            DraftOrder.confirmed_at < end,
            Channel.shop_id == shop_id,
        )
        .all()
    )
    expenses = db.query(Expense).filter(Expense.shop_id == shop_id, Expense.expense_date >= start.date(), Expense.expense_date < end.date()).all()

    daily: dict[date, dict] = {}
    cursor = start.date()
    while cursor < end.date():
        daily[cursor] = {"date": cursor.isoformat(), "income": Decimal("0"), "expense": Decimal("0"), "order_count": 0, "products": {}}
        cursor += timedelta(days=1)

    for sale in sales:
        if sale.completed_at is None:
            continue
        entry = daily[sale.completed_at.date()]
        entry["income"] += get_sale_revenue(sale)
        entry["order_count"] += 1
        for item in sale.items:
            quantity = item.quantity - item.refunded_quantity
            if quantity <= 0:
                continue
            key = item.product_id if item.product_id is not None else f"deleted:{item.sku}"
            entry["products"][key] = entry["products"].get(key, 0) + quantity

    for order in channel_orders:
        if order.confirmed_at is None:
            continue
        entry = daily[order.confirmed_at.date()]
        entry["income"] += sum((Decimal(str(item.unit_price)) * item.quantity for item in order.items), Decimal("0"))
        entry["order_count"] += 1
    for expense in expenses:
        daily[expense.expense_date]["expense"] += Decimal(str(expense.amount))

    all_time_sales = db.query(Sale).filter(Sale.shop_id == shop_id, Sale.status == SaleStatus.completed).all()
    top_stats: dict[object, dict] = {}
    for sale in all_time_sales:
        for item in sale.items:
            quantity = item.quantity - item.refunded_quantity
            if quantity <= 0:
                continue
            key = item.product_id if item.product_id is not None else f"deleted:{item.sku}"
            item_stat = top_stats.setdefault(key, {"key": key, "name": item.product_name, "sku": item.sku, "quantity_sold": 0})
            item_stat["quantity_sold"] += quantity
    top_products = sorted(top_stats.values(), key=lambda item: item["quantity_sold"], reverse=True)[:5]

    return {
        "days": [
            {
                "date": item["date"], "income": float(item["income"]), "expense": float(item["expense"]),
                "order_count": item["order_count"],
                "top_product_quantities": {str(index): item["products"].get(product["key"], 0) for index, product in enumerate(top_products)},
            }
            for item in daily.values()
        ],
        "top_products": [{key: value for key, value in product.items() if key != "key"} for product in top_products],
        "orders": sorted([
            {
                "id": sale.id, "receipt_no": sale.receipt_no, "completed_at": sale.completed_at.isoformat() if sale.completed_at else "",
                "revenue": float(get_sale_revenue(sale)), "source": "pos", "reference": f"POS #{sale.receipt_no or sale.id}",
            }
            for sale in sales
        ] + [
            {
                "id": order.id, "receipt_no": None, "completed_at": order.confirmed_at.isoformat() if order.confirmed_at else "",
                "revenue": float(sum((Decimal(str(item.unit_price)) * item.quantity for item in order.items), Decimal("0"))),
                "source": "chat", "reference": f"แชต #{order.id}",
            }
            for order in channel_orders
        ], key=lambda order: order["completed_at"], reverse=True),
    }


def get_pos_cogs(db: Session, start: datetime, end: datetime, shop_id: int | None = None) -> Decimal:
    rows = (
        db.query(Sale)
        .filter(
            Sale.status == SaleStatus.completed,
            Sale.completed_at >= start,
            Sale.completed_at < end,
            Sale.shop_id == shop_id,
        )
        .all()
    )
    total = Decimal("0")
    for sale in rows:
        for item in sale.items:
            if item.product is not None:
                net_qty = item.quantity - item.refunded_quantity
                total += Decimal(str(item.product.cost_price)) * net_qty
    return total


def get_expense_breakdown(db: Session, start: date, end: date, shop_id: int | None = None) -> dict[str, Decimal]:
    breakdown = {category.value: Decimal("0") for category in ExpenseCategory}
    rows = (
        db.query(Expense)
        .filter(Expense.shop_id == shop_id, Expense.expense_date >= start, Expense.expense_date < end)
        .all()
    )
    for expense in rows:
        breakdown[expense.category.value] += Decimal(str(expense.amount))
    return breakdown


def _apply_brackets(taxable: Decimal, brackets: list[tuple[Decimal | None, Decimal]]) -> Decimal:
    if taxable <= 0:
        return Decimal("0")
    tax = Decimal("0")
    lower = Decimal("0")
    for upper, rate in brackets:
        if upper is None:
            tax += (taxable - lower) * rate
            break
        if taxable > upper:
            tax += (upper - lower) * rate
        else:
            tax += (taxable - lower) * rate
            break
        lower = upper
    return tax


def calculate_tax(shop_type: ShopType, net_profit: Decimal) -> Decimal:
    if net_profit <= 0:
        return Decimal("0")
    if shop_type == ShopType.individual:
        taxable = net_profit - PERSONAL_ALLOWANCE
        return _apply_brackets(taxable, INDIVIDUAL_BRACKETS)
    return _apply_brackets(net_profit, JURISTIC_BRACKETS)


def build_summary(db: Session, shop_type: ShopType, year: int, month: int | None, shop_id: int | None = None) -> dict:
    start, end = _period_bounds(year, month)
    income = get_income(db, start, end, shop_id)
    cogs = get_pos_cogs(db, start, end, shop_id)
    gross_profit = income - cogs
    expense_breakdown = get_expense_breakdown(db, start.date(), end.date(), shop_id)
    total_expense = sum(expense_breakdown.values(), Decimal("0"))
    net_profit = income - total_expense
    tax_estimate = calculate_tax(shop_type, net_profit)
    return {
        "year": year,
        "month": month,
        "income": income,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "expense_breakdown": expense_breakdown,
        "total_expense": total_expense,
        "net_profit": net_profit,
        "shop_type": shop_type.value,
        "tax_estimate": tax_estimate,
        "tax_disclaimer": TAX_DISCLAIMER,
    }
