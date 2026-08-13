"""Test-only API for the isolated Parser v2 workflow."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_role
from app.models import AdminHandoffLog, OrderOption, ParserV2ConversationState, Product, ProductAlias, User, UserRole
from app.services.rule_based_parser_v2 import (
    advance_conversation_state,
    get_or_create_conversation_state,
    parse_message,
    record_handoff,
    resolve_handoff,
    serialize_result,
)
from app.services.parser_v2_history_corpus import summarize_latest_approved_history

router = APIRouter(
    prefix="/api/parser-v2",
    tags=["parser-v2-test"],
    dependencies=[Depends(require_role(UserRole.owner, UserRole.manager))],
)


class ParserV2TestIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class ParserV2ConversationTurnIn(ParserV2TestIn):
    conversation_id: int


class HandoffResolveIn(BaseModel):
    resolution: str = Field(min_length=1, max_length=4000)


class ProductAliasIn(BaseModel):
    product_id: int
    alias_text: str = Field(min_length=1, max_length=255)


class ProductAliasOut(BaseModel):
    id: int
    product_id: int
    alias_text: str
    status: str


class OrderOptionAvailabilityIn(BaseModel):
    is_available: bool


class OrderOptionOut(BaseModel):
    id: int
    name: str
    stock_mode: str
    stock_quantity: int
    is_available: bool


class HandoffOut(BaseModel):
    id: int
    redacted_text: str
    intent: str
    reason: str
    candidates: dict
    status: str
    resolution: str
    resolved_at: datetime | None
    created_at: datetime


class ParserV2TestOut(BaseModel):
    normalized_text: str
    tokens: list[str]
    intent: str
    next_state: str
    items: list[dict]
    handoff_reason: str | None
    candidates: list[dict]
    order_options: list[str]
    answer_text: str | None
    handoff_id: int | None


class ParserV2ConversationStateOut(BaseModel):
    conversation_id: int
    state: str
    last_items: list[dict]
    delivery_context_confirmed: bool
    updated_at: datetime


class ParserV2ConversationTurnOut(ParserV2TestOut):
    conversation_state: ParserV2ConversationStateOut


class HistoryCorpusSummaryOut(BaseModel):
    preparation_id: int
    approved_batch_count: int
    customer_message_count: int
    intent_counts: dict[str, int]
    next_state_counts: dict[str, int]
    handoff_reason_counts: dict[str, int]
    matched_product_quantity: dict[str, int]
    match_source_counts: dict[str, int]


def _handoff_out(handoff: AdminHandoffLog) -> HandoffOut:
    return HandoffOut(
        id=handoff.id,
        redacted_text=handoff.redacted_text,
        intent=handoff.intent,
        reason=handoff.reason,
        candidates=handoff.candidates,
        status=handoff.status,
        resolution=handoff.resolution,
        resolved_at=handoff.resolved_at,
        created_at=handoff.created_at,
    )


def _alias_out(alias: ProductAlias) -> ProductAliasOut:
    return ProductAliasOut(
        id=alias.id,
        product_id=alias.product_id,
        alias_text=alias.alias_text,
        status=alias.status,
    )


def _option_out(option: OrderOption) -> OrderOptionOut:
    return OrderOptionOut(
        id=option.id,
        name=option.name,
        stock_mode=option.stock_mode,
        stock_quantity=option.stock_quantity,
        is_available=option.is_available,
    )


def _state_out(state: ParserV2ConversationState) -> ParserV2ConversationStateOut:
    return ParserV2ConversationStateOut(
        conversation_id=state.conversation_id,
        state=state.state,
        last_items=state.last_items,
        delivery_context_confirmed=state.delivery_context_confirmed,
        updated_at=state.updated_at,
    )


@router.get("/options", response_model=list[OrderOptionOut])
def list_order_options(db: Session = Depends(get_db)):
    return [_option_out(option) for option in db.query(OrderOption).order_by(OrderOption.name).all()]


@router.patch("/options/{option_id}", response_model=OrderOptionOut)
def set_order_option_availability(
    option_id: int, payload: OrderOptionAvailabilityIn, db: Session = Depends(get_db)
):
    option = db.get(OrderOption, option_id)
    if option is None:
        raise HTTPException(status_code=404, detail="ไม่พบตัวเลือก")
    option.is_available = payload.is_available
    db.commit()
    db.refresh(option)
    return _option_out(option)


@router.get("/aliases", response_model=list[ProductAliasOut])
def list_product_aliases(db: Session = Depends(get_db)):
    aliases = db.query(ProductAlias).order_by(ProductAlias.product_id, ProductAlias.alias_text).all()
    return [_alias_out(alias) for alias in aliases]


@router.post("/aliases", response_model=ProductAliasOut)
def approve_product_alias(payload: ProductAliasIn, db: Session = Depends(get_db)):
    """Create an owner-approved alias; no discovered spelling is enabled automatically."""
    product = db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า")
    alias_text = payload.alias_text.strip().lower()
    existing = db.query(ProductAlias).filter(
        ProductAlias.product_id == product.id,
        ProductAlias.alias_text == alias_text,
    ).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="มีชื่อเรียกนี้แล้ว")
    alias = ProductAlias(product_id=product.id, alias_text=alias_text, status="approved")
    db.add(alias)
    db.commit()
    db.refresh(alias)
    return _alias_out(alias)


@router.post("/test", response_model=ParserV2TestOut)
def test_parser(payload: ParserV2TestIn, db: Session = Depends(get_db)):
    result = parse_message(db, payload.text)
    handoff = record_handoff(db, payload.text, result)
    return ParserV2TestOut(**serialize_result(result), handoff_id=handoff.id if handoff else None)


@router.post("/conversation-turn", response_model=ParserV2ConversationTurnOut)
def test_conversation_turn(payload: ParserV2ConversationTurnIn, db: Session = Depends(get_db)):
    """Stateful Parser v2 simulation for one existing conversation.

    This endpoint stores Parser state only.  It does not append an Inbox
    message, create a draft order, or send a channel reply.
    """
    try:
        result, state = advance_conversation_state(db, payload.conversation_id, payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    handoff = record_handoff(db, payload.text, result)
    if handoff is None:
        db.commit()
    db.refresh(state)
    return ParserV2ConversationTurnOut(
        **serialize_result(result),
        handoff_id=handoff.id if handoff else None,
        conversation_state=_state_out(state),
    )


@router.post("/conversations/{conversation_id}/confirm-delivery-context", response_model=ParserV2ConversationStateOut)
def confirm_delivery_context(conversation_id: int, db: Session = Depends(get_db)):
    """Mark that an admin has verified the conversation's existing delivery point."""
    try:
        state = get_or_create_conversation_state(db, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    state.delivery_context_confirmed = True
    db.commit()
    db.refresh(state)
    return _state_out(state)


@router.post("/conversations/{conversation_id}/reset-state", response_model=ParserV2ConversationStateOut)
def reset_conversation_state(conversation_id: int, db: Session = Depends(get_db)):
    """Clear only Parser v2's derived memory; Inbox messages and orders remain untouched."""
    try:
        state = get_or_create_conversation_state(db, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    state.state = "idle"
    state.last_items = []
    state.delivery_context_confirmed = False
    db.commit()
    db.refresh(state)
    return _state_out(state)


@router.get("/history-summary", response_model=HistoryCorpusSummaryOut)
def history_summary(db: Session = Depends(get_db)):
    try:
        return HistoryCorpusSummaryOut(**summarize_latest_approved_history(db))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/handoffs", response_model=list[HandoffOut])
def list_handoffs(db: Session = Depends(get_db)):
    rows = db.query(AdminHandoffLog).order_by(AdminHandoffLog.id.desc()).all()
    return [_handoff_out(row) for row in rows]


@router.post("/handoffs/{handoff_id}/resolve", response_model=HandoffOut)
def resolve_parser_handoff(
    handoff_id: int,
    payload: HandoffResolveIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    handoff = db.get(AdminHandoffLog, handoff_id)
    if handoff is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายการส่งต่อแอดมิน")
    return _handoff_out(resolve_handoff(db, handoff, payload.resolution, user.id))
