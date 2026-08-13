import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import (
    Channel,
    ChannelType,
    Conversation,
    Customer,
    DraftOrder,
    DraftOrderItem,
    DraftOrderStatus,
    Message,
    OrderParserMode,
    Product,
    ShopSettings,
)
from app.services.ai_order_parser import AiOrderParserError, parse_order_with_ai
from app.services.conversation_labels import label_slots, set_label_slot
from app.services.meta_profile import populate_messenger_display_name
from app.services.order_parser import CatalogTerm, ParsedMatch, classify_sentence, parse_order_text
from app.services.rule_based_parser_v2 import ParserV2Result, advance_conversation_state, record_handoff

logger = logging.getLogger(__name__)


def get_or_create_channel(db: Session, channel_type: ChannelType, external_id: str) -> Channel:
    channel = db.query(Channel).filter_by(type=channel_type, external_id=external_id).first()
    if channel is None:
        channel = Channel(type=channel_type, external_id=external_id)
        db.add(channel)
        db.flush()
    return channel


def get_or_create_customer(db: Session, channel: Channel, external_user_id: str) -> Customer:
    customer = (
        db.query(Customer)
        .filter_by(channel_id=channel.id, external_user_id=external_user_id)
        .first()
    )
    if customer is None:
        customer = Customer(channel_id=channel.id, external_user_id=external_user_id)
        db.add(customer)
        db.flush()
    return customer


def get_or_create_conversation(db: Session, channel: Channel, customer: Customer) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter_by(channel_id=channel.id, customer_id=customer.id)
        .first()
    )
    if conversation is None:
        conversation = Conversation(channel_id=channel.id, customer_id=customer.id)
        db.add(conversation)
        db.flush()
    return conversation


def _append_note(existing: str, addition: str) -> str:
    return f"{existing}, {addition}" if existing else addition


def upsert_draft_order_from_matches(
    db: Session, conversation: Conversation, matches: list[ParsedMatch]
) -> DraftOrder | None:
    """Build/extend a pending draft order from parsed matches.

    Matched menu items become draft order items (a negated menu item, e.g.
    "ไม่เอาส้มตำ", is dropped instead of added). Matched modifiers/ingredients
    become a special_request note on whichever menu item most recently
    appeared earlier in the same message (e.g. "ผัดไทยกุ้ง ไม่ใส่ถั่ว" attaches
    "ไม่ใส่ถั่ว" to the ผัดไทยกุ้ง item); if none has appeared yet in this
    message, the note is attached to the draft order itself instead.
    """
    if not matches:
        return None

    draft_order: DraftOrder | None = None

    def get_or_create_draft_order() -> DraftOrder:
        nonlocal draft_order
        if draft_order is not None:
            return draft_order
        draft_order = (
            db.query(DraftOrder)
            .filter_by(conversation_id=conversation.id, status=DraftOrderStatus.pending)
            .first()
        )
        if draft_order is None:
            draft_order = DraftOrder(conversation_id=conversation.id)
            db.add(draft_order)
            db.flush()
        return draft_order

    current_item: DraftOrderItem | None = None
    pending_notes: list[str] = []

    for match in sorted(matches, key=lambda m: m.start):
        term = match.term
        if term.kind == "product":
            if match.negated:
                # Customer explicitly excluded this menu item -- don't add it.
                continue
            draft_order = get_or_create_draft_order()
            product = db.get(Product, term.id)
            existing_item = next(
                (item for item in draft_order.items if item.product_id == product.id), None
            )
            if existing_item:
                existing_item.quantity += 1
                current_item = existing_item
            else:
                new_item = DraftOrderItem(
                    product_id=product.id,
                    matched_text=term.name,
                    quantity=1,
                    unit_price=product.price,
                )
                new_item.draft_order = draft_order
                db.add(new_item)
                db.flush()
                current_item = new_item
        else:
            note = f"ไม่ใส่{term.name}" if match.negated else f"เพิ่ม{term.name}"
            if current_item is not None:
                current_item.special_request = _append_note(current_item.special_request, note)
            else:
                pending_notes.append(note)

    if pending_notes:
        # A modifier/ingredient mentioned with no menu item earlier in this
        # message -- only worth recording if there's already an open draft
        # order to attach the note to (e.g. a follow-up "ไม่ใส่ถั่วนะคะ").
        # Don't spin up a brand new, item-less draft order just for a note.
        target = draft_order or (
            db.query(DraftOrder)
            .filter_by(conversation_id=conversation.id, status=DraftOrderStatus.pending)
            .first()
        )
        if target is not None:
            target.note = _append_note(target.note, ", ".join(pending_notes))
            draft_order = target

    db.flush()
    return draft_order


def upsert_draft_order_from_parser_v2(db: Session, conversation: Conversation, items) -> DraftOrder | None:
    """Append only stock-checked Parser v2 items to the current staff-review draft.

    A draft is deliberately not a confirmed sale: staff still see and can edit
    it in Inbox before stock is reduced or a confirmation is sent.
    """
    if not items:
        return None
    draft_order = (
        db.query(DraftOrder)
        .filter_by(conversation_id=conversation.id, status=DraftOrderStatus.pending)
        .first()
    )
    if draft_order is None:
        draft_order = DraftOrder(conversation_id=conversation.id)
        db.add(draft_order)
        db.flush()

    for parsed_item in items:
        product = db.get(Product, parsed_item.product_id)
        if product is None:
            continue
        existing_item = next((item for item in draft_order.items if item.product_id == product.id), None)
        if existing_item:
            existing_item.quantity += parsed_item.quantity
        else:
            db.add(
                DraftOrderItem(
                    draft_order_id=draft_order.id,
                    product_id=product.id,
                    matched_text=parsed_item.matched_text,
                    quantity=parsed_item.quantity,
                    unit_price=product.price,
                )
            )
    db.flush()
    return draft_order


def resolve_order_matches(db: Session, text: str, classification: str | None = None) -> list[ParsedMatch]:
    """Classify+parse a single incoming message using whichever parser the
    shop has selected in settings ("algorithm" or "ai"). If AI mode is on but
    the call fails for any reason (no key, network error, bad response), this
    falls back to the algorithmic parser instead of silently dropping the
    message.
    """
    classification = classification or classify_sentence(text)
    # Questions and greetings go to the inbox for a person to handle.  Do not
    # call the AI parser for these messages, even when AI mode is enabled.
    if classification != "order":
        return []

    settings = db.get(ShopSettings, 1)
    mode = settings.order_parser_mode if settings else OrderParserMode.algorithm

    if mode == OrderParserMode.ai and settings and settings.ai_api_key:
        try:
            classification, matches = parse_order_with_ai(db, text, settings.ai_api_key)
            return matches if classification == "order" else []
        except AiOrderParserError as exc:
            logger.warning("AI order parsing failed, falling back to algorithm parser: %s", exc)

    return parse_order_text(db, text)


def ingest_incoming_message(
    db: Session,
    channel_type: ChannelType,
    channel_external_id: str,
    sender_external_id: str,
    text: str,
    raw_payload: dict,
) -> tuple[Message, Conversation, str, ParserV2Result]:
    channel = get_or_create_channel(db, channel_type, channel_external_id)
    customer = get_or_create_customer(db, channel, sender_external_id)
    if channel_type == ChannelType.facebook_page:
        populate_messenger_display_name(customer)
    conversation = get_or_create_conversation(db, channel, customer)
    reactivated_from_hidden = conversation.is_hidden
    if reactivated_from_hidden:
        # A new customer message always re-opens a hidden/finished chat.  Keep
        # the customer and operational records, but do not carry a completed
        # label into the new work cycle.
        conversation.is_hidden = False
        conversation.status = "open"
        primary_label, _ = label_slots(conversation)
        if primary_label == "เสร็จสิ้น":
            set_label_slot(db, conversation, "primary", None)

    # A customer commonly repeats the same order when no acknowledgement has
    # appeared yet.  Do not silently turn that into a larger order.  Deliberate
    # additions stay explicit (for example "เพิ่มไก่ทอด 1").
    previous_same_message = (
        db.query(Message)
        .filter_by(conversation_id=conversation.id, direction="in", text=text)
        .order_by(Message.created_at.desc())
        .first()
    )
    is_recent_repeat = (
        previous_same_message is not None
        and previous_same_message.created_at >= datetime.utcnow() - timedelta(minutes=2)
    )

    message = Message(
        conversation_id=conversation.id,
        direction="in",
        text=text,
        raw_payload=raw_payload,
    )
    db.add(message)

    conversation.last_message_at = datetime.utcnow()
    conversation.unread_count += 1

    classification = classify_sentence(text)
    # Parser v2 is the only text path that prepares Inbox draft orders.  It
    # preserves per-item quantities, stock safety and conversation references;
    # the legacy parser remains available for Messenger product buttons.
    parser_v2_result, _ = advance_conversation_state(db, conversation.id, text)
    is_duplicate_order = bool(parser_v2_result.items and is_recent_repeat)
    if is_duplicate_order:
        message.raw_payload = {**raw_payload, "_duplicate_order": True}
    elif parser_v2_result.items and parser_v2_result.handoff_reason is None:
        upsert_draft_order_from_parser_v2(db, conversation, parser_v2_result.items)
    record_handoff(db, text, parser_v2_result)
    if parser_v2_result.handoff_reason:
        set_label_slot(db, conversation, "primary", "รอแอดมิน")
    elif parser_v2_result.items and not is_duplicate_order:
        # A parsed order still needs the staff's final confirmation (and the
        # Inbox draft card), so it remains an admin task.
        set_label_slot(db, conversation, "primary", "รอแอดมิน")
    elif parser_v2_result.answer_text:
        # The deterministic reply can be handled without a handoff.  Leave a
        # visible operational trace rather than falsely flagging the chat as
        # waiting for an admin.
        set_label_slot(db, conversation, "primary", "ดำเนินการ")
        conversation.status = "in_progress"
    if parser_v2_result.intent == "greeting":
        classification = "greeting"
    elif parser_v2_result.intent == "payment":
        classification = "payment"
    elif parser_v2_result.intent.startswith("ask_"):
        classification = "question"
    if classification == "question" and parser_v2_result.answer_text is None and not reactivated_from_hidden:
        conversation.status = "waiting_reply"

    db.commit()
    db.refresh(message)
    return message, conversation, classification, parser_v2_result


def ingest_product_selection(
    db: Session,
    channel_type: ChannelType,
    channel_external_id: str,
    sender_external_id: str,
    product_id: int,
    raw_payload: dict,
) -> tuple[Conversation, Product, Message] | None:
    """Add a Messenger postback product choice to the customer's pending draft order."""
    product = db.get(Product, product_id)
    if product is None:
        logger.warning("Ignoring Messenger selection for missing product %s", product_id)
        return None

    channel = get_or_create_channel(db, channel_type, channel_external_id)
    customer = get_or_create_customer(db, channel, sender_external_id)
    if channel_type == ChannelType.facebook_page:
        populate_messenger_display_name(customer)
    conversation = get_or_create_conversation(db, channel, customer)
    message = Message(
        conversation_id=conversation.id,
        direction="in",
        text=f"[เลือกเมนู] {product.name}",
        raw_payload=raw_payload,
    )
    db.add(message)
    conversation.last_message_at = datetime.utcnow()
    upsert_draft_order_from_matches(
        db,
        conversation,
        [
            ParsedMatch(
                term=CatalogTerm(kind="product", id=product.id, name=product.name),
                matched_text=product.name,
                negated=False,
                start=0,
            )
        ],
    )
    db.flush()
    return conversation, product, message
