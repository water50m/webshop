from datetime import datetime

from sqlalchemy.orm import Session

from app.models import PaymentMethod, Sale, SaleStatus, Shift, User


def get_open_shift(db: Session, user: User) -> Shift | None:
    return (
        db.query(Shift)
        .filter(Shift.opened_by_user_id == user.id, Shift.closed_at.is_(None))
        .order_by(Shift.opened_at.desc())
        .first()
    )


def open_shift(db: Session, user: User, opening_cash: float, note: str = "") -> Shift:
    if get_open_shift(db, user) is not None:
        raise ValueError("คุณมีกะที่เปิดอยู่แล้ว กรุณาปิดกะเดิมก่อน")
    shift = Shift(opened_by_user_id=user.id, opening_cash=opening_cash, note=note)
    db.add(shift)
    db.flush()
    return shift


def shift_summary(db: Session, shift: Shift) -> dict:
    sales = db.query(Sale).filter(Sale.shift_id == shift.id, Sale.status != SaleStatus.held).all()
    totals_by_method: dict[str, float] = {method.value: 0.0 for method in PaymentMethod}
    revenue = 0.0
    cash_net = 0.0
    for sale in sales:
        if sale.status == SaleStatus.voided:
            continue
        for payment in sale.payments:
            totals_by_method[payment.method.value] = totals_by_method.get(payment.method.value, 0.0) + float(
                payment.amount
            )
        cash_paid = sum(float(p.amount) for p in sale.payments if p.method == PaymentMethod.cash)
        cash_net += cash_paid - float(sale.change_amount or 0)
        revenue += sum(float(p.amount) for p in sale.payments)

    expected_cash = float(shift.opening_cash) + cash_net
    closing_cash_counted = float(shift.closing_cash_counted) if shift.closing_cash_counted is not None else None
    return {
        "sale_count": len([s for s in sales if s.status == SaleStatus.completed]),
        "total_revenue": revenue,
        "totals_by_method": totals_by_method,
        "opening_cash": float(shift.opening_cash),
        "expected_cash": expected_cash,
        "closing_cash_counted": closing_cash_counted,
        "cash_difference": (closing_cash_counted - expected_cash) if closing_cash_counted is not None else None,
    }


def close_shift(db: Session, shift: Shift, user: User, closing_cash_counted: float, note: str = "") -> Shift:
    if shift.closed_at is not None:
        raise ValueError("กะนี้ปิดไปแล้ว")
    shift.closed_by_user_id = user.id
    shift.closing_cash_counted = closing_cash_counted
    shift.closed_at = datetime.utcnow()
    if note:
        shift.note = f"{shift.note} {note}".strip()
    return shift
