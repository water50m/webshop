import socket
from pathlib import Path

from PIL import Image

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
LOGO_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "shop-logos"


def _encode(text: str) -> bytes:
    return text.encode("cp874", errors="replace")


def _logo_as_escpos(logo_url: str, max_width: int) -> bytes:
    """Render an uploaded colour logo as a high-contrast monochrome raster image."""
    if not logo_url.startswith("/uploads/shop-logos/"):
        return b""
    path = LOGO_UPLOAD_DIR / Path(logo_url).name
    if not path.is_file():
        return b""
    try:
        with Image.open(path) as source:
            image = source.convert("RGBA")
            background = Image.new("RGBA", image.size, "white")
            background.alpha_composite(image)
            image = background.convert("L")
            image.thumbnail((max_width, 200), Image.Resampling.LANCZOS)
            image = image.convert("1")  # Floyd-Steinberg dithering preserves detail on thermal paper.
            width, height = image.size
            byte_width = (width + 7) // 8
            pixels = image.load()
            raster = bytearray()
            for y in range(height):
                for x_byte in range(byte_width):
                    value = 0
                    for bit in range(8):
                        x = x_byte * 8 + bit
                        if x < width and pixels[x, y] == 0:
                            value |= 0x80 >> bit
                    raster.append(value)
            return GS + b"v0" + bytes((0, byte_width & 0xFF, byte_width >> 8, height & 0xFF, height >> 8)) + bytes(raster) + LINE_FEED
    except (OSError, ValueError):
        return b""


def build_escpos_receipt(sale: Sale, settings: ShopSettings, totals: dict) -> bytes:
    line_width = 48 if settings.receipt_paper_width == 80 else 32
    amount_width = 10
    item_width = line_width - amount_width
    lines = bytearray()
    lines += INIT
    lines += ALIGN_CENTER
    if settings.receipt_show_logo:
        lines += _logo_as_escpos(settings.receipt_logo_url, 576 if settings.receipt_paper_width == 80 else 384)
    if settings.shop_name:
        lines += BOLD_ON + _encode(settings.shop_name) + LINE_FEED + BOLD_OFF
    if settings.address:
        lines += _encode(settings.address) + LINE_FEED
    if settings.tax_id:
        lines += _encode(f"เลขประจำตัวผู้เสียภาษี: {settings.tax_id}") + LINE_FEED
    lines += _encode("ใบเสร็จรับเงิน") + LINE_FEED
    receipt_no = sale.receipt_no if sale.receipt_no is not None else sale.id
    when = sale.completed_at.strftime("%d/%m/%Y %H:%M") if sale.completed_at else ""
    lines += _encode(f"เลขที่ {receipt_no}  {when}") + LINE_FEED
    lines += ALIGN_LEFT
    lines += _encode("-" * line_width) + LINE_FEED

    for item in sale.items:
        line_total = pos_service.line_total(item)
        name_qty = f"{item.product_name} x{item.quantity}"
        lines += _encode(f"{name_qty:<{item_width}}{line_total:>{amount_width},.2f}") + LINE_FEED
        for modifier in item.modifiers:
            lines += _encode(f"  + {modifier.name}") + LINE_FEED
        if item.refunded_quantity > 0:
            lines += _encode(f"  (คืน {item.refunded_quantity})") + LINE_FEED

    lines += _encode("-" * line_width) + LINE_FEED
    lines += _encode(f"{'ยอดรวม':<{item_width}}{totals['subtotal']:>{amount_width},.2f}") + LINE_FEED
    if totals["discount"] > 0:
        lines += _encode(f"{'ส่วนลด':<{item_width}}{totals['discount']:>{amount_width},.2f}") + LINE_FEED
    lines += BOLD_ON
    lines += _encode(f"{'ยอดสุทธิ':<{item_width}}{totals['total']:>{amount_width},.2f}") + LINE_FEED
    lines += BOLD_OFF

    for payment in sale.payments:
        label = METHOD_LABEL.get(payment.method.value, payment.method.value)
        lines += _encode(f"ชำระโดย{label:<{item_width - 8}}{float(payment.amount):>{amount_width},.2f}") + LINE_FEED
    if sale.change_amount and float(sale.change_amount) > 0:
        lines += _encode(f"{'เงินทอน':<{item_width}}{float(sale.change_amount):>{amount_width},.2f}") + LINE_FEED

    if settings.receipt_show_member and sale.customer is not None:
        lines += _encode(f"สมาชิก: {sale.customer.name or sale.customer.phone}") + LINE_FEED
        if sale.points_redeemed:
            lines += _encode(f"ใช้แต้มสะสม -{sale.points_redeemed}") + LINE_FEED
        if sale.points_earned:
            lines += _encode(f"ได้รับแต้มสะสม +{sale.points_earned}") + LINE_FEED

    if settings.receipt_footer_text:
        lines += ALIGN_CENTER + _encode(settings.receipt_footer_text) + LINE_FEED + ALIGN_LEFT
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
