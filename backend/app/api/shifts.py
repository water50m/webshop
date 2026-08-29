from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_active_shop_membership, get_current_user
from app.models import Shift, ShopMembership, User, UserRole
from app.services import shifts as shift_service

router = APIRouter(prefix="/api/shifts", tags=["shifts"], dependencies=[Depends(get_current_user)])


def _ensure_can_manage_shift(shift: Shift, user: User) -> None:
    if user.role == UserRole.cashier and shift.opened_by_user_id != user.id:
        raise HTTPException(status_code=403, detail="ดู/ปิดกะของผู้อื่นได้เฉพาะผู้จัดการหรือเจ้าของร้าน")


class ShiftOut(BaseModel):
    id: int
    opened_by_name: str
    opening_cash: float
    opened_at: str
    closed_by_name: str | None
    closing_cash_counted: float | None
    closed_at: str | None
    note: str


class OpenShiftIn(BaseModel):
    opening_cash: float = 0
    note: str = ""


class CloseShiftIn(BaseModel):
    closing_cash_counted: float
    note: str = ""


class ShiftSummaryOut(BaseModel):
    sale_count: int
    total_revenue: float
    totals_by_method: dict[str, float]
    opening_cash: float
    expected_cash: float
    closing_cash_counted: float | None
    cash_difference: float | None


def _serialize(shift: Shift) -> ShiftOut:
    return ShiftOut(
        id=shift.id,
        opened_by_name=shift.opened_by.display_name or shift.opened_by.username,
        opening_cash=float(shift.opening_cash),
        opened_at=shift.opened_at.isoformat(),
        closed_by_name=(shift.closed_by.display_name or shift.closed_by.username) if shift.closed_by else None,
        closing_cash_counted=float(shift.closing_cash_counted) if shift.closing_cash_counted is not None else None,
        closed_at=shift.closed_at.isoformat() if shift.closed_at else None,
        note=shift.note,
    )


@router.get("/current", response_model=ShiftOut | None)
def get_current_shift(db: Session = Depends(get_db), user: User = Depends(get_current_user), membership: ShopMembership = Depends(get_active_shop_membership)):
    shift = shift_service.get_open_shift(db, user, membership.shop_id)
    return _serialize(shift) if shift else None


@router.post("/open", response_model=ShiftOut)
def open_shift(payload: OpenShiftIn, db: Session = Depends(get_db), user: User = Depends(get_current_user), membership: ShopMembership = Depends(get_active_shop_membership)):
    try:
        shift = shift_service.open_shift(db, user, payload.opening_cash, payload.note, membership.shop_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(shift)
    return _serialize(shift)


@router.post("/{shift_id}/close", response_model=ShiftOut)
def close_shift(
    shift_id: int,
    payload: CloseShiftIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    membership: ShopMembership = Depends(get_active_shop_membership),
):
    shift = db.query(Shift).filter_by(id=shift_id, shop_id=membership.shop_id).first()
    if shift is None:
        raise HTTPException(status_code=404, detail="ไม่พบกะนี้")
    _ensure_can_manage_shift(shift, user)
    try:
        shift_service.close_shift(db, shift, user, payload.closing_cash_counted, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(shift)
    return _serialize(shift)


@router.get("/{shift_id}/summary", response_model=ShiftSummaryOut)
def get_shift_summary(shift_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user), membership: ShopMembership = Depends(get_active_shop_membership)):
    shift = db.query(Shift).filter_by(id=shift_id, shop_id=membership.shop_id).first()
    if shift is None:
        raise HTTPException(status_code=404, detail="ไม่พบกะนี้")
    _ensure_can_manage_shift(shift, user)
    return ShiftSummaryOut(**shift_service.shift_summary(db, shift))
