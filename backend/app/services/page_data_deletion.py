"""Deletion of Messenger data scoped to exactly one Facebook Page channel."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    Channel,
    ChannelAuditLog,
    ChannelMembership,
    Conversation,
    ConversationLabel,
    Customer,
    DraftOrder,
    DraftOrderItem,
    HistoryConversation,
    HistoryImportRun,
    HistoryMessage,
    Message,
    ParserV2ConversationState,
)


def delete_page_data(db: Session, channel: Channel) -> dict[str, int]:
    """Permanently remove data for one Page and no other Page.

    The caller is responsible for authorizing the deletion and creating its
    confirmation record.  Channel is removed too, so a later reconnection is a
    clean, new Page connection.
    """
    page_id = channel.external_id
    conversation_ids = [row[0] for row in db.query(Conversation.id).filter_by(channel_id=channel.id).all()]
    customer_ids = [row[0] for row in db.query(Customer.id).filter_by(channel_id=channel.id).all()]
    draft_ids = (
        [row[0] for row in db.query(DraftOrder.id).filter(DraftOrder.conversation_id.in_(conversation_ids)).all()]
        if conversation_ids else []
    )
    history_ids = [row[0] for row in db.query(HistoryConversation.id).filter_by(page_id=page_id).all()]
    counts = {"conversations": len(conversation_ids), "customers": len(customer_ids), "draft_orders": len(draft_ids), "history_conversations": len(history_ids)}

    if draft_ids:
        db.query(DraftOrderItem).filter(DraftOrderItem.draft_order_id.in_(draft_ids)).delete(synchronize_session=False)
    if conversation_ids:
        db.query(ParserV2ConversationState).filter(ParserV2ConversationState.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
        db.query(ConversationLabel).filter(ConversationLabel.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
        db.query(Message).filter(Message.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
        db.query(DraftOrder).filter(DraftOrder.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
        db.query(Conversation).filter(Conversation.id.in_(conversation_ids)).delete(synchronize_session=False)
    if customer_ids:
        db.query(Customer).filter(Customer.id.in_(customer_ids)).delete(synchronize_session=False)
    if history_ids:
        db.query(HistoryMessage).filter(HistoryMessage.history_conversation_id.in_(history_ids)).delete(synchronize_session=False)
        db.query(HistoryConversation).filter(HistoryConversation.id.in_(history_ids)).delete(synchronize_session=False)
    db.query(HistoryImportRun).filter_by(page_id=page_id).delete(synchronize_session=False)
    db.query(ChannelAuditLog).filter_by(channel_id=channel.id).delete(synchronize_session=False)
    db.query(ChannelMembership).filter_by(channel_id=channel.id).delete(synchronize_session=False)
    db.delete(channel)
    return counts
