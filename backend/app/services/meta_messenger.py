"""Send Messenger menu cards and safely record the messages we send."""

import logging
from io import BytesIO
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ChannelType, Conversation, DraftOrder, DraftOrderStatus, Message, Product, ShopSettings, User
from app.services.promptpay import generate_promptpay_payload
from app.services.meta_tokens import MetaTokenConfigurationError, channel_access_token

logger = logging.getLogger(__name__)

_GRAPH_API_BASE_URL = "https://graph.facebook.com/v22.0"
_AUTOMATED_REPLY_WINDOW = timedelta(minutes=3)


@dataclass(frozen=True)
class MenuOption:
    product: Product
    special_product: Product | None = None


def list_menu_options(db: Session) -> list[MenuOption]:
    """Pair products named '<menu>พิเศษ' with their normal menu where possible."""
    products = db.query(Product).order_by(Product.name, Product.id).all()
    product_by_name = {product.name: product for product in products}
    paired_special_ids = {
        special.id
        for special in products
        if special.name.endswith("พิเศษ") and product_by_name.get(special.name.removesuffix("พิเศษ"))
    }
    return [
        MenuOption(
            product=product,
            special_product=product_by_name.get(f"{product.name}พิเศษ"),
        )
        for product in products
        if product.id not in paired_special_ids
    ]


def _order_button_title(product: Product) -> str:
    """Use the product name in the visible postback label (Messenger max 20 chars)."""
    price = f"฿{float(product.price):,.0f}"
    prefix = "สั่ง"
    remaining_name_length = 20 - len(prefix) - len(price) - 1
    if remaining_name_length <= 0:
        return f"สั่งสินค้า {price}"[:20]
    return f"{prefix}{product.name[:remaining_name_length]} {price}"


def _channel_token(conversation: Conversation) -> str:
    try:
        return channel_access_token(conversation.channel) or settings.meta_page_access_token
    except MetaTokenConfigurationError:
        logger.warning("Messenger response skipped because the Page token cannot be decrypted")
        return ""


def _send(page_id: str, recipient_id: str, message: dict, access_token: str | None = None) -> dict | None:
    """Send one Messenger message without allowing Meta errors to fail a webhook."""
    token = access_token or settings.meta_page_access_token
    if not token:
        logger.info("Messenger response skipped because META_PAGE_ACCESS_TOKEN is not configured")
        return None
    try:
        response = httpx.post(
            f"{_GRAPH_API_BASE_URL}/{page_id}/messages",
            params={"access_token": token},
            json={"recipient": {"id": recipient_id}, "message": message},
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except (httpx.HTTPError, ValueError):
        logger.warning("Unable to send Messenger response", exc_info=True)
        return None


def _record_outgoing_message(
    db: Session,
    conversation: Conversation,
    text: str,
    payload: dict,
    automation_key: str | None = None,
    sent_by: User | None = None,
) -> None:
    recorded_payload = dict(payload)
    if automation_key:
        recorded_payload["_automation_key"] = automation_key
    db.add(
        Message(
            conversation_id=conversation.id,
            direction="out",
            text=text,
            raw_payload=recorded_payload,
            sent_by_user_id=sent_by.id if sent_by is not None else None,
        )
    )
    conversation.last_message_at = datetime.utcnow()


def _automated_reply_sent_twice(db: Session, conversation: Conversation, key: str) -> bool:
    """Limit a repeated automatic reply without permanently silencing a chat.

    Only messages tagged by this service are counted, so staff replies never
    suppress a needed automatic response.  The current reply is allowed at
    most twice in a short rolling window; a customer who returns later can
    still receive a normal greeting or answer.
    """
    window_start = datetime.utcnow() - _AUTOMATED_REPLY_WINDOW
    messages = db.query(Message).filter_by(conversation_id=conversation.id, direction="out").all()
    return sum(
        1
        for message in messages
        if message.created_at >= window_start and (message.raw_payload or {}).get("_automation_key") == key
    ) >= 2


def send_verified_answer(
    db: Session, conversation: Conversation, page_id: str, recipient_id: str, text: str
) -> bool:
    """Send a stock-verified Parser v2 answer at most twice per short window.

    The answer text is produced only by deterministic rules (and never from a
    free-form model).  Its digest is used as the automation key so repeating
    the same customer question cannot flood the conversation, while a changed
    answer such as a stock update may still be sent.
    """
    answer = text.strip()
    if not answer or conversation.channel.type != ChannelType.facebook_page:
        return False
    automation_key = f"verified_answer:{sha256(answer.encode('utf-8')).hexdigest()}"
    if _automated_reply_sent_twice(db, conversation, automation_key):
        return False
    response = _send(page_id, recipient_id, {"text": answer}, _channel_token(conversation))
    if response is None:
        return False
    _record_outgoing_message(db, conversation, answer, response, automation_key)
    return True


def _menu_answer_products(db: Session) -> list[Product]:
    return [
        product
        for product in db.query(Product).order_by(Product.name, Product.id).all()
        if product.show_in_menu_answer
        and product.category != "ตัวเลือกออเดอร์"
        and product.is_available
        and (product.stock_mode == "unlimited" or product.stock_quantity > 0)
    ]


def _menu_answer_text(products: list[Product]) -> str:
    return "ขณะนี้มี: " + ", ".join(product.name for product in products)


def _build_menu_answer_image(shop_name: str, products: list[Product]) -> bytes:
    """Build a temporary Thai menu card; it is sent from memory and not stored."""
    from PIL import Image, ImageDraw, ImageFont

    font_path = next(
        (path for path in (Path("C:/Windows/Fonts/tahoma.ttf"), Path("C:/Windows/Fonts/LeelawUI.ttf")) if path.exists()),
        None,
    )
    if font_path is None:
        raise RuntimeError("Thai menu font is unavailable")
    title_font = ImageFont.truetype(str(font_path), 44)
    item_font = ImageFont.truetype(str(font_path), 30)
    width, row_height = 1000, 58
    image = Image.new("RGB", (width, 160 + max(1, len(products)) * row_height), "#fffdf7")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 120), fill="#b45309")
    draw.text((48, 30), shop_name.strip() or "เมนูร้าน", font=title_font, fill="white")
    draw.text((48, 132), "เมนูที่พร้อมรับออเดอร์", font=item_font, fill="#334155")
    for index, product in enumerate(products):
        y = 180 + index * row_height
        if index % 2 == 0:
            draw.rectangle((32, y - 6, width - 32, y + 42), fill="#fef3c7")
        draw.text((52, y), product.name, font=item_font, fill="#1f2937")
        price = f"{float(product.price):,.0f} บาท"
        price_box = draw.textbbox((0, 0), price, font=item_font)
        draw.text((width - 52 - (price_box[2] - price_box[0]), y), price, font=item_font, fill="#92400e")
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def send_menu_answer(
    db: Session, conversation: Conversation, page_id: str, recipient_id: str, text: str
) -> bool:
    """Reply to a generic menu question using selected in-stock products.

    A narrower query (for example drinks) stays textual.  The image mode is
    used only when the parser's answer exactly equals the configured menu list.
    """
    products = _menu_answer_products(db)
    expected_text = _menu_answer_text(products) if products else ""
    settings = db.get(ShopSettings, 1)
    if not products or settings is None or settings.menu_answer_format != "image" or text != expected_text:
        return send_verified_answer(db, conversation, page_id, recipient_id, text)
    signature = ",".join(f"{product.id}:{product.price}" for product in products)
    automation_key = f"menu_image:{sha256(signature.encode('utf-8')).hexdigest()}"
    if _automated_reply_sent_twice(db, conversation, automation_key):
        return False
    try:
        image = _build_menu_answer_image(settings.shop_name, products)
    except (ImportError, OSError, RuntimeError):
        logger.warning("Unable to render menu response image", exc_info=True)
        return send_verified_answer(db, conversation, page_id, recipient_id, text)
    response = _send_image(page_id, recipient_id, image, "menu-answer.png", _channel_token(conversation))
    if response is None:
        return False
    _record_outgoing_message(db, conversation, "[รูปเมนูที่พร้อมรับออเดอร์]", response, automation_key)
    return True


def send_menu(
    db: Session, conversation: Conversation, page_id: str, recipient_id: str
) -> bool:
    """Send one vertical Messenger button-template message per menu option."""
    if _automated_reply_sent_twice(db, conversation, "menu"):
        return False
    options = list_menu_options(db)
    if not options:
        response = _send(page_id, recipient_id, {"text": "ขออภัย ขณะนี้ยังไม่มีเมนูให้เลือกค่ะ"}, _channel_token(conversation))
        if response is None:
            return False
        _record_outgoing_message(db, conversation, "ขออภัย ขณะนี้ยังไม่มีเมนูให้เลือกค่ะ", response, "menu")
        return True

    sent_any = False
    for option_index, option in enumerate(options):
        product = option.product
        buttons = [
            {
                "type": "postback",
                "title": _order_button_title(product),
                "payload": f"ORDER_PRODUCT:{product.id}",
            }
        ]
        if option.special_product:
            special = option.special_product
            buttons = [
                {
                    "type": "postback",
                    "title": _order_button_title(product),
                    "payload": f"ORDER_PRODUCT:{product.id}",
                },
                {
                    "type": "postback",
                    "title": _order_button_title(special),
                    "payload": f"ORDER_PRODUCT:{special.id}",
                },
            ]
        message = {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": f"{product.name}\nราคา ฿{float(product.price):,.2f}",
                    "buttons": buttons,
                },
            }
        }
        response = _send(page_id, recipient_id, message, _channel_token(conversation))
        if response is None:
            continue
        # One greeting can result in several Messenger cards.  Tag only the
        # first card so the guard counts reply events, not card count.
        _record_outgoing_message(db, conversation, f"เมนู: {product.name}", response, "menu" if option_index == 0 else None)
        sent_any = True
    return sent_any


def send_selection_confirmation(
    db: Session, conversation: Conversation, page_id: str, recipient_id: str, product: Product
) -> bool:
    text = f"รับรายการ: {product.name} ราคา ฿{float(product.price):,.2f} แล้วค่ะ"
    response = _send(page_id, recipient_id, {"text": text}, _channel_token(conversation))
    if response is None:
        return False
    _record_outgoing_message(db, conversation, text, response)
    return True


def send_saved_delivery_note(db: Session, conversation: Conversation, sent_by: User) -> bool:
    """Send the staff-saved delivery message only when the staff presses the button."""
    text = conversation.delivery_note.strip()
    if not text:
        return False
    if conversation.channel.type != ChannelType.facebook_page:
        return False
    response = _send(
        conversation.channel.external_id,
        conversation.customer.external_user_id,
        {"text": text},
        _channel_token(conversation),
    )
    if response is None:
        return False
    _record_outgoing_message(db, conversation, text, response, sent_by=sent_by)
    return True


def send_manual_text(db: Session, conversation: Conversation, text: str, sent_by: User) -> bool:
    """Send a staff-composed Inbox reply and retain it as an outgoing message."""
    reply = text.strip()
    if not reply or conversation.channel.type != ChannelType.facebook_page:
        return False
    response = _send(
        conversation.channel.external_id,
        conversation.customer.external_user_id,
        {"text": reply},
        _channel_token(conversation),
    )
    if response is None:
        return False
    _record_outgoing_message(db, conversation, reply, response, sent_by=sent_by)
    return True


def send_manual_photo(db: Session, conversation: Conversation, image: bytes, filename: str, sent_by: User) -> bool:
    """Forward a staff-captured photo without writing the image to local storage."""
    if conversation.channel.type != ChannelType.facebook_page:
        return False
    response = _send_image(
        conversation.channel.external_id,
        conversation.customer.external_user_id,
        image,
        filename,
        _channel_token(conversation),
    )
    if response is None:
        return False
    # The database records delivery metadata only. The image bytes remain in
    # request memory and are discarded as soon as this request completes.
    _record_outgoing_message(db, conversation, "[ส่งรูปภาพจากร้าน]", response, sent_by=sent_by)
    return True


def _send_image(
    page_id: str, recipient_id: str, image: bytes, filename: str = "promptpay-qr.png", access_token: str | None = None
) -> dict | None:
    """Send a generated PNG through the Messenger Send API as an image."""
    token = access_token or settings.meta_page_access_token
    if not token:
        logger.info("Messenger QR response skipped because META_PAGE_ACCESS_TOKEN is not configured")
        return None
    try:
        response = httpx.post(
            f"{_GRAPH_API_BASE_URL}/{page_id}/messages",
            params={"access_token": token},
            data={
                "recipient": json.dumps({"id": recipient_id}),
                "message": json.dumps({"attachment": {"type": "image", "payload": {}}}),
            },
            files={"filedata": (filename, image, "image/png")},
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except (httpx.HTTPError, ValueError):
        logger.warning("Unable to send Messenger QR image", exc_info=True)
        return None


def _promptpay_qr_png(payload: str) -> bytes:
    """Render a standard PromptPay payload locally; no customer data leaves the app."""
    import qrcode

    image = qrcode.make(payload)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def send_promptpay_qr(db: Session, conversation: Conversation, page_id: str, recipient_id: str) -> bool:
    """Send a PromptPay QR for the pending order total when one is available.

    A payment question before an order has been read still gets a normal static
    QR.  No amount is guessed from free text.
    """
    automation_key = "promptpay_qr"
    if _automated_reply_sent_twice(db, conversation, automation_key):
        return False
    shop_settings = db.get(ShopSettings, 1)
    if shop_settings is None or not shop_settings.promptpay_id:
        logger.warning("PromptPay QR requested but PromptPay has not been configured")
        return False
    draft_order = (
        db.query(DraftOrder)
        .filter_by(conversation_id=conversation.id, status=DraftOrderStatus.pending)
        .order_by(DraftOrder.updated_at.desc())
        .first()
    )
    amount = sum(float(item.unit_price) * item.quantity for item in draft_order.items) if draft_order and draft_order.items else None
    try:
        image = _promptpay_qr_png(generate_promptpay_payload(shop_settings.promptpay_id, amount))
    except (ImportError, ValueError):
        logger.warning("Unable to render PromptPay QR", exc_info=True)
        return False

    image_response = _send_image(page_id, recipient_id, image, access_token=_channel_token(conversation))
    if image_response is None:
        return False
    _record_outgoing_message(db, conversation, "[QR code สำหรับสแกนจ่าย]", image_response, automation_key)

    text = (
        f"QR code สำหรับสแกนจ่าย {amount:,.2f} บาท"
        if amount is not None
        else "QR code สำหรับสแกนจ่ายแบบปกติ"
    )
    text += "\nสำหรับการจ่ายด้วยวิธีอื่นกรุณารอสักครู่ครับ"
    text_response = _send(page_id, recipient_id, {"text": text}, _channel_token(conversation))
    if text_response is not None:
        _record_outgoing_message(db, conversation, text, text_response)
    return True


def _build_order_confirmation_text(draft_order: DraftOrder) -> str:
    lines = ["รับออเดอร์เรียบร้อยครับ", "รายการ:"]
    total = 0.0
    for item in draft_order.items:
        product_name = item.product.name if item.product else item.matched_text
        line_total = float(item.unit_price) * item.quantity
        total += line_total
        line = f"• {product_name} x {item.quantity} — ฿{line_total:,.2f}"
        if item.special_request:
            line += f" ({item.special_request})"
        lines.append(line)
    if draft_order.note:
        lines.append(f"หมายเหตุ: {draft_order.note}")
    lines.extend((f"รวมทั้งหมด ฿{total:,.2f}", "ขอบคุณค่ะ"))
    return "\n".join(lines)


def send_order_confirmation(db: Session, draft_order: DraftOrder, sent_by: User | None = None) -> bool:
    """Send a receipt-style confirmation after a staff member confirms an order.

    Only Facebook Page conversations can use the Messenger Send API here. A
    failed delivery is intentionally non-fatal: the confirmed order and stock
    movement must remain valid even when Meta rejects a message.
    """
    conversation = draft_order.conversation
    if conversation.channel.type != ChannelType.facebook_page:
        return False

    text = _build_order_confirmation_text(draft_order)
    response = _send(
        conversation.channel.external_id,
        conversation.customer.external_user_id,
        {"text": text},
        _channel_token(conversation),
    )
    if response is None:
        return False
    _record_outgoing_message(db, conversation, text, response, sent_by=sent_by)
    return True
