from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import accessible_channel_ids, get_active_shop_membership, get_current_user, require_conversation_access
from app.models import Channel, ChannelAuditLog, ChannelMembershipRole, Conversation, DraftOrder, DraftOrderStatus, Message, User
from app.services.conversation_labels import PAYMENT_LABELS, PRIMARY_LABELS, label_slots, set_label_slot
from app.services.meta_messenger import send_manual_photo, send_manual_text, send_saved_delivery_note

router = APIRouter(
    prefix="/api/conversations",
    tags=["conversations"],
    dependencies=[Depends(get_current_user)],
)


class MessageOut(BaseModel):
    id: int
    direction: str
    text: str
    created_at: str
    sent_by_display_name: str | None = None

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    id: int
    channel_id: int
    customer_id: int
    customer_display_name: str
    customer_profile_image_url: str
    last_message_at: str
    status: str
    is_hidden: bool
    is_pinned: bool
    unread_count: int
    bill_count: int
    primary_label: str | None
    payment_label: str | None
    delivery_note: str
    order_confirmed_at: str | None

    class Config:
        from_attributes = True


class ConversationUpdate(BaseModel):
    status: str | None = None
    is_hidden: bool | None = None
    is_pinned: bool | None = None
    primary_label: str | None = None
    payment_label: str | None = None
    delivery_note: str | None = None


class ManualReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class ManualReplyOut(BaseModel):
    conversation: ConversationOut
    message: MessageOut


def _serialize_message(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        direction=message.direction,
        text=message.text,
        created_at=message.created_at.isoformat(),
        sent_by_display_name=(
            (message.sent_by.facebook_identity.facebook_name if message.sent_by.facebook_identity else "")
            or message.sent_by.display_name
            or message.sent_by.username
        ) if message.sent_by else None,
    )


def _clear_chat_content(db: Session, conversation: Conversation) -> None:
    """Remove disposable chat content while retaining customer/order history."""
    db.query(Message).filter(Message.conversation_id == conversation.id).delete(synchronize_session=False)
    db.query(DraftOrder).filter(
        DraftOrder.conversation_id == conversation.id,
        DraftOrder.status == DraftOrderStatus.pending,
    ).update({DraftOrder.status: DraftOrderStatus.rejected}, synchronize_session=False)


def _serialize(conversation: Conversation) -> ConversationOut:
    primary_label, payment_label = label_slots(conversation)
    confirmed_at = max(
        (draft.confirmed_at for draft in conversation.draft_orders if draft.confirmed_at is not None),
        default=None,
    )
    return ConversationOut(
        id=conversation.id,
        channel_id=conversation.channel_id,
        customer_id=conversation.customer_id,
        customer_display_name=conversation.customer.display_name,
        customer_profile_image_url=conversation.customer.profile_image_url,
        last_message_at=conversation.last_message_at.isoformat(),
        status=conversation.status,
        is_hidden=conversation.is_hidden,
        is_pinned=conversation.is_pinned,
        unread_count=conversation.unread_count,
        bill_count=conversation.bill_count,
        primary_label=primary_label,
        payment_label=payment_label,
        delivery_note=conversation.delivery_note,
        order_confirmed_at=confirmed_at.isoformat() if confirmed_at else None,
    )


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    status: str | None = None,
    visibility: str = "active",
    channel_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    membership=Depends(get_active_shop_membership),
):
    channel_ids = accessible_channel_ids(user, db)
    query = (
        db.query(Conversation)
        .join(Channel, Conversation.channel_id == Channel.id)
        .filter(Conversation.channel_id.in_(channel_ids), Channel.shop_id == membership.shop_id)
    )
    if channel_id is not None:
        if channel_id not in channel_ids:
            raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เข้าถึงเพจนี้")
        query = query.filter(Conversation.channel_id == channel_id)
    if status:
        query = query.filter(Conversation.status == status)
    if visibility == "active":
        query = query.filter(Conversation.is_hidden.is_(False))
    elif visibility == "hidden":
        query = query.filter(Conversation.is_hidden.is_(True))
    elif visibility != "all":
        raise HTTPException(status_code=422, detail="visibility must be active, hidden, or all")

    conversations = query.order_by(Conversation.is_pinned.desc(), Conversation.last_message_at.desc()).all()
    return [
        _serialize(c)
        for c in conversations
    ]


@router.patch("/{conversation_id}", response_model=ConversationOut)
def update_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = require_conversation_access(conversation_id, user, db, ChannelMembershipRole.page_staff)
    if payload.status is not None:
        if payload.status not in {"open", "waiting_reply", "in_progress", "done", "spam"}:
            raise HTTPException(status_code=422, detail="Invalid conversation status")
        conversation.status = payload.status
        if payload.status == "done":
            conversation.bill_count = 0
    if payload.is_hidden is not None:
        conversation.is_hidden = payload.is_hidden
        if payload.is_hidden:
            # Hiding is a storage cleanup action: retain the customer and
            # conversation metadata, but remove disposable chat content.
            _clear_chat_content(db, conversation)
    if payload.is_pinned is not None:
        conversation.is_pinned = payload.is_pinned
    if "primary_label" in payload.model_fields_set:
        if payload.primary_label not in PRIMARY_LABELS:
            raise HTTPException(status_code=422, detail="ป้ายงานไม่ถูกต้อง")
        set_label_slot(db, conversation, "primary", payload.primary_label)
        if payload.primary_label == "เสร็จสิ้น":
            # Closing a chat also dismisses an unconfirmed draft.  Confirmed
            # orders remain part of the customer/order history.  Payment is
            # specific to that completed order, so never carry its label into
            # the next customer contact.
            _clear_chat_content(db, conversation)
            set_label_slot(db, conversation, "payment", None)
            conversation.bill_count = 0
            conversation.is_hidden = True
            conversation.customer.profile_image_url = ""
    if "payment_label" in payload.model_fields_set:
        if payload.payment_label and payload.payment_label not in PAYMENT_LABELS:
            raise HTTPException(status_code=422, detail="ป้ายการจ่ายเงินไม่ถูกต้อง")
        set_label_slot(db, conversation, "payment", payload.payment_label or None)
    if payload.delivery_note is not None:
        conversation.delivery_note = payload.delivery_note.strip()
    if payload.model_fields_set:
        db.add(ChannelAuditLog(channel_id=conversation.channel_id, actor_user_id=user.id, action="conversation_updated", detail={"conversation_id": conversation.id, "fields": sorted(payload.model_fields_set)}))
    db.commit()
    db.refresh(conversation)
    return _serialize(conversation)


@router.post("/{conversation_id}/send-delivery", response_model=ConversationOut)
def send_delivery(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = require_conversation_access(conversation_id, user, db, ChannelMembershipRole.page_staff)
    if not conversation.delivery_note.strip():
        raise HTTPException(status_code=422, detail="กรุณาบันทึกข้อความที่จัดส่งก่อน")
    if not send_saved_delivery_note(db, conversation, user):
        raise HTTPException(status_code=409, detail="ส่งข้อความจัดส่งไม่สำเร็จ: ต้องเป็นแชท Facebook ที่เชื่อมต่อและพร้อมส่งข้อความ")

    db.add(ChannelAuditLog(channel_id=conversation.channel_id, actor_user_id=user.id, action="delivery_note_sent", detail={"conversation_id": conversation.id}))

    db.commit()
    db.refresh(conversation)
    return _serialize(conversation)


@router.post("/{conversation_id}/send-message", response_model=ManualReplyOut)
def send_message(
    conversation_id: int,
    payload: ManualReplyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Send an Inbox-composed Facebook reply and move the task into progress."""
    conversation = require_conversation_access(conversation_id, user, db, ChannelMembershipRole.page_staff)
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="กรุณาพิมพ์ข้อความก่อนส่ง")
    if not send_manual_text(db, conversation, text, user):
        raise HTTPException(status_code=409, detail="ส่งข้อความไม่สำเร็จ: ต้องเป็นแชท Facebook ที่เชื่อมต่อและพร้อมส่งข้อความ")
    set_label_slot(db, conversation, "primary", "ดำเนินการ")
    conversation.status = "in_progress"
    db.add(ChannelAuditLog(channel_id=conversation.channel_id, actor_user_id=user.id, action="message_sent", detail={"conversation_id": conversation.id, "message_type": "text"}))
    db.commit()
    db.refresh(conversation)
    message = (
        db.query(Message)
        .filter_by(conversation_id=conversation.id, direction="out")
        .order_by(Message.created_at.desc(), Message.id.desc())
        .first()
    )
    if message is None:  # Defensive guard for a sender implementation change.
        raise HTTPException(status_code=500, detail="ไม่พบบันทึกข้อความที่ส่ง")
    return ManualReplyOut(conversation=_serialize(conversation), message=_serialize_message(message))


@router.post("/{conversation_id}/send-photo", response_model=ConversationOut)
async def send_photo(
    conversation_id: int,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Forward one staff-captured image to Messenger without persisting it locally."""
    conversation = require_conversation_access(conversation_id, user, db, ChannelMembershipRole.page_staff)
    if photo.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=422, detail="รองรับเฉพาะรูป JPG, PNG หรือ WEBP")
    image = await photo.read()
    if not image or len(image) > 5 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="รูปต้องมีขนาดไม่เกิน 5 MB")
    if not send_manual_photo(db, conversation, image, photo.filename or "shop-photo.jpg", user):
        raise HTTPException(status_code=409, detail="ส่งรูปไม่สำเร็จ: ต้องเป็นแชท Facebook ที่เชื่อมต่อและพร้อมส่งข้อความ")
    db.add(ChannelAuditLog(channel_id=conversation.channel_id, actor_user_id=user.id, action="message_sent", detail={"conversation_id": conversation.id, "message_type": "photo"}))
    db.commit()
    db.refresh(conversation)
    return _serialize(conversation)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = require_conversation_access(conversation_id, user, db)
    return [
        _serialize_message(m)
        for m in conversation.messages
    ]


@router.post("/{conversation_id}/mark-read", response_model=ConversationOut)
def mark_conversation_read(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Clear the inbox alert once staff have opened this conversation."""
    conversation = require_conversation_access(conversation_id, user, db)
    if conversation.unread_count:
        conversation.unread_count = 0
        db.commit()
        db.refresh(conversation)
    return _serialize(conversation)
