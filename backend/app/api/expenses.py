from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import Expense, ExpenseCategory, UserRole

router = APIRouter(
    prefix="/api/expenses",
    tags=["expenses"],
    dependencies=[Depends(require_role(UserRole.owner, UserRole.manager))],
)


class ExpenseOut(BaseModel):
    id: int
    category: str
    amount: float
    description: str
    expense_date: date


class ExpenseIn(BaseModel):
    category: ExpenseCategory
    amount: float
    description: str = ""
    expense_date: date


def _serialize(expense: Expense) -> ExpenseOut:
    return ExpenseOut(
        id=expense.id,
        category=expense.category.value,
        amount=float(expense.amount),
        description=expense.description,
        expense_date=expense.expense_date,
    )


@router.get("", response_model=list[ExpenseOut])
def list_expenses(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Expense)
    if start is not None:
        query = query.filter(Expense.expense_date >= start)
    if end is not None:
        query = query.filter(Expense.expense_date < end)
    return [_serialize(e) for e in query.order_by(Expense.expense_date.desc()).all()]


@router.post("", response_model=ExpenseOut)
def create_expense(payload: ExpenseIn, db: Session = Depends(get_db)):
    expense = Expense(
        category=payload.category,
        amount=payload.amount,
        description=payload.description,
        expense_date=payload.expense_date,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return _serialize(expense)


@router.put("/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: int, payload: ExpenseIn, db: Session = Depends(get_db)):
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    expense.category = payload.category
    expense.amount = payload.amount
    expense.description = payload.description
    expense.expense_date = payload.expense_date
    db.commit()
    db.refresh(expense)
    return _serialize(expense)


@router.delete("/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    db.delete(expense)
    db.commit()
    return {"ok": True}
