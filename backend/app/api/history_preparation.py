"""Local-only preparation and review for the Facebook history-analysis workflow."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user, require_role
from app.models import HistoryAnalysisBatch, HistoryAnalysisPreparation, User, UserRole
from app.services.history_analysis_preparation import approve_batch, create_preparation
from app.services.meta_history import MetaHistoryError, run_history_import

router = APIRouter(
    prefix="/api/history-preparation",
    tags=["history-preparation"],
    dependencies=[Depends(require_role(UserRole.owner, UserRole.manager))],
)


class HistoryPreparationStatus(BaseModel):
    state: str
    token_ready: bool
    page_id_ready: bool
    lookback_days: int
    source: str
    analysis_only: bool
    sending_enabled: bool
    next_action: str


@router.get("/status", response_model=HistoryPreparationStatus)
def get_status():
    token_ready = bool(settings.meta_history_access_token)
    return HistoryPreparationStatus(
        state="ready" if token_ready else "waiting_for_token",
        token_ready=token_ready,
        page_id_ready=bool(settings.meta_history_page_id),
        lookback_days=settings.meta_history_lookback_days,
        source="facebook",
        analysis_only=True,
        sending_enabled=False,
        next_action=(
            "พร้อมให้เริ่มนำเข้าประวัติ Facebook เพื่อวิเคราะห์"
            if token_ready
            else "เพิ่ม META_HISTORY_ACCESS_TOKEN ใน backend/.env แล้วรีสตาร์ต backend"
        ),
    )


class HistoryImportOut(BaseModel):
    id: int
    status: str
    page_id: str
    lookback_days: int
    conversation_count: int
    message_count: int
    skipped_non_text_count: int
    error_detail: str


@router.post("/import", response_model=HistoryImportOut)
def import_history(db: Session = Depends(get_db)):
    """Start only phase 1: local text import. No AI or outbound messaging."""
    try:
        run = run_history_import(db)
    except MetaHistoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HistoryImportOut(
        id=run.id,
        status=run.status,
        page_id=run.page_id,
        lookback_days=run.lookback_days,
        conversation_count=run.conversation_count,
        message_count=run.message_count,
        skipped_non_text_count=run.skipped_non_text_count,
        error_detail=run.error_detail,
    )


class PrepareAnalysisIn(BaseModel):
    max_conversations_per_batch: int = Field(default=20, ge=1, le=100)
    max_characters_per_batch: int = Field(default=9000, ge=1000, le=30000)


class AnalysisBatchSummary(BaseModel):
    id: int
    batch_number: int
    status: str
    conversation_count: int
    message_count: int
    approved_at: datetime | None


class AnalysisPreparationOut(BaseModel):
    id: int
    status: str
    conversation_count: int
    message_count: int
    batch_count: int
    redaction_counts: dict[str, int]
    created_at: datetime
    batches: list[AnalysisBatchSummary]


class AnalysisBatchOut(AnalysisBatchSummary):
    preparation_id: int
    content: dict


def _preparation_out(preparation: HistoryAnalysisPreparation) -> AnalysisPreparationOut:
    return AnalysisPreparationOut(
        id=preparation.id,
        status=preparation.status,
        conversation_count=preparation.conversation_count,
        message_count=preparation.message_count,
        batch_count=preparation.batch_count,
        redaction_counts=preparation.redaction_counts,
        created_at=preparation.created_at,
        batches=[
            AnalysisBatchSummary(
                id=batch.id,
                batch_number=batch.batch_number,
                status=batch.status,
                conversation_count=batch.conversation_count,
                message_count=batch.message_count,
                approved_at=batch.approved_at,
            )
            for batch in preparation.batches
        ],
    )


@router.post("/analysis-preparations", response_model=AnalysisPreparationOut)
def prepare_analysis_data(payload: PrepareAnalysisIn, db: Session = Depends(get_db)):
    """Create a new redacted local snapshot. No AI provider is called."""
    preparation = create_preparation(
        db,
        max_conversations_per_batch=payload.max_conversations_per_batch,
        max_characters_per_batch=payload.max_characters_per_batch,
    )
    return _preparation_out(preparation)


@router.get("/analysis-preparations", response_model=list[AnalysisPreparationOut])
def list_analysis_preparations(db: Session = Depends(get_db)):
    preparations = db.query(HistoryAnalysisPreparation).order_by(HistoryAnalysisPreparation.id.desc()).all()
    return [_preparation_out(preparation) for preparation in preparations]


@router.get("/analysis-batches/{batch_id}", response_model=AnalysisBatchOut)
def get_analysis_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(HistoryAnalysisBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="ไม่พบชุดข้อมูล")
    return AnalysisBatchOut(
        id=batch.id,
        preparation_id=batch.preparation_id,
        batch_number=batch.batch_number,
        status=batch.status,
        conversation_count=batch.conversation_count,
        message_count=batch.message_count,
        approved_at=batch.approved_at,
        content=batch.content,
    )


@router.post("/analysis-batches/{batch_id}/approve", response_model=AnalysisBatchOut)
def approve_analysis_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    batch = db.get(HistoryAnalysisBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="ไม่พบชุดข้อมูล")
    approve_batch(batch, user.id)
    db.commit()
    db.refresh(batch)
    return AnalysisBatchOut(
        id=batch.id,
        preparation_id=batch.preparation_id,
        batch_number=batch.batch_number,
        status=batch.status,
        conversation_count=batch.conversation_count,
        message_count=batch.message_count,
        approved_at=batch.approved_at,
        content=batch.content,
    )
