"""Two fixed Inbox label slots: operational progress and payment progress."""

from sqlalchemy.orm import Session

from app.models import Conversation, ConversationLabel

PRIMARY_LABELS = ("รอแอดมิน", "ดำเนินการ", "รับออเดอร์แล้ว", "รอส่ง", "ส่งแล้ว", "เสร็จสิ้น", "แก้ไข")
PAYMENT_LABELS = ("รอจ่ายเงิน", "จ่ายเงินแล้ว")


def label_slots(conversation: Conversation) -> tuple[str | None, str | None]:
    names = {label.name for label in conversation.labels}
    primary = next((name for name in PRIMARY_LABELS if name in names), None)
    payment = next((name for name in PAYMENT_LABELS if name in names), None)
    return primary, payment


def set_label_slot(db: Session, conversation: Conversation, slot: str, value: str | None) -> None:
    allowed = PRIMARY_LABELS if slot == "primary" else PAYMENT_LABELS
    if value is not None and value not in allowed:
        raise ValueError("ป้ายไม่ถูกต้อง")
    # Re-applying the current label is a normal outcome when the same unsafe
    # customer message is delivered again by a channel.  Do nothing so the
    # unique database constraint cannot be hit by a delete-and-reinsert.
    if value and any(label.name == value for label in conversation.labels):
        return
    for label in list(conversation.labels):
        if label.name in allowed:
            db.delete(label)
    if value:
        db.add(ConversationLabel(conversation_id=conversation.id, name=value))
