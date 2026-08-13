import socket

from app.models import Sale, ShopSettings
from app.services import pos as pos_service

ESC = b"\x1b"
GS = b"\x1d"
INIT = ESC + b"@"
ALIGN_CENTER = ESC + b"a\x01"
ALIGN_LEFT = ESC + b"a\x00"
BOLD_ON = ESC + b"E\x01"
BOLD_OFF = ESC + b"E\x00"
CUT_PAPER = GS + b"V\x01"
LINE_FEED = b"\n"

METHOD_LABEL = {"cash": "เงินสด", "transfer": "โอน/พร้อมเพย์"}


def _encode(text: str) -> bytes:
    return text.encode("cp874", errors="replace")


def build_escpos_receipt(sale: Sale, settings: ShopSettings, totals: dict) -> bytes:
    lines = bytearray()
    lines += INIT
    lines += ALIGN_CENTER
    if settings.shop_name:
        lines += BOLD_ON + _encode(settings.shop_name) + LINE_FEED + BOLD_OFF
    if settings.address:
        lines += _encode(settings.address) + LINE_FEED
    if settings.tax_id:
        lines += _encode(f"เลขประจำตัวผู้เสียภาษี: {settings.tax_id}") + LINE_FEED
    lines += _encode("ใบเสร็จ") + LINE_FEED
    receipt_no = sale.receipt_no if sale.receipt_no is not None else sale.id
    when = sale.completed_at.strftime("%d/%m/%Y %H:%M") if sale.completed_at else ""
    lines += _encode(f"เลขที่ {receipt_no}  {when}") + LINE_FEED
    lines += ALIGN_LEFT
    lines += _encode("-" * 32) + LINE_FEED

    for item in sale.items:
        line_total = pos_service.line_total(item)
        name_qty = f"{item.product_name} x{item.quantity}"
        lines += _encode(f"{name_qty:<22}{line_total:>10,.2f}") + LINE_FEED
        for modifier in item.modifiers:
            lines += _encode(f"  + {modifier.name}") + LINE_FEED
        if item.refunded_quantity > 0:
            lines += _encode(f"  (คืน {item.refunded_quantity})") + LINE_FEED

    lines += _encode("-" * 32) + LINE_FEED
    lines += _encode(f"{'ยอดรวม':<22}{totals['subtotal']:>10,.2f}") + LINE_FEED
    if totals["discount"] > 0:
        lines += _encode(f"{'ส่วนลด':<22}{totals['discount']:>10,.2f}") + LINE_FEED
    lines += BOLD_ON
    lines += _encode(f"{'ยอดสุทธิ':<22}{totals['total']:>10,.2f}") + LINE_FEED
    lines += BOLD_OFF

    for payment in sale.payments:
        label = METHOD_LABEL.get(payment.method.value, payment.method.value)
        lines += _encode(f"ชำระโดย{label:<14}{float(payment.amount):>10,.2f}") + LINE_FEED
    if sale.change_amount and float(sale.change_amount) > 0:
        lines += _encode(f"{'เงินทอน':<22}{float(sale.change_amount):>10,.2f}") + LINE_FEED

    if sale.customer is not None:
        lines += _encode(f"สมาชิก: {sale.customer.name or sale.customer.phone}") + LINE_FEED
        if sale.points_redeemed:
            lines += _encode(f"ใช้แต้มสะสม -{sale.points_redeemed}") + LINE_FEED
        if sale.points_earned:
            lines += _encode(f"ได้รับแต้มสะสม +{sale.points_earned}") + LINE_FEED

    lines += LINE_FEED + LINE_FEED + LINE_FEED
    lines += CUT_PAPER
    return bytes(lines)


def send_to_printer(ip: str, port: int, data: bytes, timeout: float = 5) -> None:
    if not ip:
        raise ValueError("ยังไม่ได้ตั้งค่า IP เครื่องพิมพ์ใบเสร็จในหน้าตั้งค่า")
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock.sendall(data)
    except OSError as exc:
        raise ValueError(f"เชื่อมต่อเครื่องพิมพ์ไม่สำเร็จ ({ip}:{port}): {exc}") from exc
