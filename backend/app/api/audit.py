from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import SaleAuditLog, UserRole

router = APIRouter(
    prefix="/api/audit",
    tags=["audit"],
    dependencies=[Depends(require_role(UserRole.owner, UserRole.manager))],
)


class AuditLogOut(BaseModel):
    id: int
    sale_id: int
    receipt_no: int | None
    action: str
    user_name: str | None
    note: str
    created_at: str


@router.get("/sales", response_model=list[AuditLogOut])
def list_sale_audit_logs(
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(SaleAuditLog)
    if start is not None:
        query = query.filter(SaleAuditLog.created_at >= start)
    if end is not None:
        query = query.filter(SaleAuditLog.created_at < end)
    rows = query.order_by(SaleAuditLog.created_at.desc()).all()
    return [
        AuditLogOut(
            id=row.id,
            sale_id=row.sale_id,
            receipt_no=row.sale.receipt_no,
            action=row.action.value,
            user_name=(row.user.display_name or row.user.username) if row.user else None,
            note=row.note,
            created_at=row.created_at.isoformat(),
        )
        for row in rows
    ]
