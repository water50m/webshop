from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_active_shop_membership, get_current_user, require_role
from app.models import ShopMembership, StocktakeLine, StocktakeSession, StocktakeStatus, User, UserRole
from app.services import stocktake as stocktake_service

router = APIRouter(
    prefix="/api/stocktake",
    tags=["stocktake"],
    dependencies=[Depends(get_current_user)],
)
manage_only = Depends(require_role(UserRole.owner, UserRole.manager))


class StocktakeLineOut(BaseModel):
    id: int
    product_id: int | None
    ingredient_id: int | None
    name: str
    unit: str
    expected_quantity: float
    counted_quantity: float | None


class StocktakeSessionOut(BaseModel):
    id: int
    status: str
    entity_type: str
    opened_by_name: str
    opened_at: str
    closed_by_name: str | None
    closed_at: str | None
    note: str
    lines: list[StocktakeLineOut]


class OpenSessionIn(BaseModel):
    note: str = ""


class CountIn(BaseModel):
    counted_quantity: float | None = None


class CloseSessionOut(BaseModel):
    session: StocktakeSessionOut
    adjusted_count: int
    skipped_count: int


def _line_name_unit(line: StocktakeLine) -> tuple[str, str]:
    if line.product is not None:
        return line.product.name, ""
    if line.ingredient is not None:
        return line.ingredient.name, line.ingredient.unit
    return "", ""


def _serialize_line(line: StocktakeLine) -> StocktakeLineOut:
    name, unit = _line_name_unit(line)
    return StocktakeLineOut(
        id=line.id,
        product_id=line.product_id,
        ingredient_id=line.ingredient_id,
        name=name,
        unit=unit,
        expected_quantity=float(line.expected_quantity),
        counted_quantity=float(line.counted_quantity) if line.counted_quantity is not None else None,
    )


def _serialize_session(session: StocktakeSession) -> StocktakeSessionOut:
    return StocktakeSessionOut(
        id=session.id,
        status=session.status.value,
        entity_type=session.entity_type,
        opened_by_name=session.opened_by.display_name or session.opened_by.username,
        opened_at=session.opened_at.isoformat(),
        closed_by_name=(session.closed_by.display_name or session.closed_by.username) if session.closed_by else None,
        closed_at=session.closed_at.isoformat() if session.closed_at else None,
        note=session.note,
        lines=[_serialize_line(line) for line in session.lines],
    )


@router.get("/sessions", response_model=list[StocktakeSessionOut])
def list_sessions(db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    return [_serialize_session(s) for s in db.query(StocktakeSession).filter_by(shop_id=membership.shop_id).order_by(StocktakeSession.opened_at.desc()).all()]


@router.get("/sessions/current", response_model=StocktakeSessionOut | None)
def current_session(db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    session = stocktake_service.get_open_session(db, membership.shop_id)
    return _serialize_session(session) if session else None


@router.get("/sessions/{session_id}", response_model=StocktakeSessionOut)
def get_session(session_id: int, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    session = db.query(StocktakeSession).filter_by(id=session_id, shop_id=membership.shop_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="ไม่พบรอบนับสต๊อกนี้")
    return _serialize_session(session)


@router.post("/sessions", response_model=StocktakeSessionOut, dependencies=[manage_only])
def open_session(
    payload: OpenSessionIn = OpenSessionIn(), db: Session = Depends(get_db), user: User = Depends(get_current_user), membership: ShopMembership = Depends(get_active_shop_membership)
):
    try:
        session = stocktake_service.open_session(db, user, membership.shop_id, note=payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(session)
    return _serialize_session(session)


@router.put("/sessions/{session_id}/lines/{line_id}", response_model=StocktakeLineOut)
def submit_line_count(session_id: int, line_id: int, payload: CountIn, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    line = db.get(StocktakeLine, line_id)
    if line is None or line.session_id != session_id:
        raise HTTPException(status_code=404, detail="ไม่พบรายการนี้")
    session = db.query(StocktakeSession).filter_by(id=session_id, shop_id=membership.shop_id).first()
    if session is None or session.status != StocktakeStatus.open:
        raise HTTPException(status_code=400, detail="รอบนับสต๊อกนี้ปิดไปแล้ว")
    stocktake_service.submit_count(line, payload.counted_quantity)
    db.commit()
    db.refresh(line)
    return _serialize_line(line)


@router.post("/sessions/{session_id}/close", response_model=CloseSessionOut, dependencies=[manage_only])
def close_session_endpoint(session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user), membership: ShopMembership = Depends(get_active_shop_membership)):
    session = db.query(StocktakeSession).filter_by(id=session_id, shop_id=membership.shop_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="ไม่พบรอบนับสต๊อกนี้")
    try:
        result = stocktake_service.close_session(db, session, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(session)
    return CloseSessionOut(session=_serialize_session(session), **result)
