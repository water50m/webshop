import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_active_shop_membership, get_current_user, require_role
from app.models import InventoryMode, OrderParserMode, Product, ShopMembership, ShopSettings, ShopType, UserRole
from app.services.line_notify import build_low_stock_message, send_line_message
from app.services.promptpay import generate_promptpay_payload

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(get_current_user)])
manage_only = Depends(require_role(UserRole.owner, UserRole.manager))
LOGO_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "shop-logos"
ALLOWED_LOGO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_LOGO_SIZE = 5 * 1024 * 1024


class ShopSettingsOut(BaseModel):
    shop_type: str
    shop_name: str
    address: str
    tax_id: str
    promptpay_id: str
    loyalty_baht_per_point: float
    low_stock_line_token: str
    low_stock_line_target_id: str
    receipt_printer_ip: str
    receipt_printer_port: int
    receipt_paper_width: int
    receipt_logo_url: str
    receipt_show_logo: bool
    receipt_footer_text: str
    receipt_show_cashier: bool
    receipt_show_member: bool
    inventory_mode: str
    order_parser_mode: str
    ai_api_key: str
    menu_answer_format: str


class ShopSettingsIn(BaseModel):
    shop_type: ShopType
    shop_name: str = ""
    address: str = ""
    tax_id: str = ""
    promptpay_id: str = ""
    loyalty_baht_per_point: float = 0
    low_stock_line_token: str = ""
    low_stock_line_target_id: str = ""
    receipt_printer_ip: str = ""
    receipt_printer_port: int = 9100
    receipt_paper_width: int = 80
    receipt_logo_url: str = ""
    receipt_show_logo: bool = True
    receipt_footer_text: str = "ขอบคุณที่ใช้บริการ"
    receipt_show_cashier: bool = True
    receipt_show_member: bool = True
    inventory_mode: InventoryMode = InventoryMode.simple
    order_parser_mode: OrderParserMode = OrderParserMode.algorithm
    ai_api_key: str = ""
    menu_answer_format: str = "text"


def get_or_create_settings(db: Session, shop_id: int) -> ShopSettings:
    settings = db.query(ShopSettings).filter_by(shop_id=shop_id).first()
    if settings is None:
        settings = ShopSettings(shop_id=shop_id, shop_type=ShopType.individual)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _serialize(settings: ShopSettings) -> ShopSettingsOut:
    return ShopSettingsOut(
        shop_type=settings.shop_type.value,
        shop_name=settings.shop_name,
        address=settings.address,
        tax_id=settings.tax_id,
        promptpay_id=settings.promptpay_id,
        loyalty_baht_per_point=float(settings.loyalty_baht_per_point),
        low_stock_line_token=settings.low_stock_line_token,
        low_stock_line_target_id=settings.low_stock_line_target_id,
        receipt_printer_ip=settings.receipt_printer_ip,
        receipt_printer_port=settings.receipt_printer_port,
        receipt_paper_width=settings.receipt_paper_width,
        receipt_logo_url=settings.receipt_logo_url,
        receipt_show_logo=settings.receipt_show_logo,
        receipt_footer_text=settings.receipt_footer_text,
        receipt_show_cashier=settings.receipt_show_cashier,
        receipt_show_member=settings.receipt_show_member,
        inventory_mode=settings.inventory_mode.value,
        order_parser_mode=settings.order_parser_mode.value,
        ai_api_key=settings.ai_api_key,
        menu_answer_format=settings.menu_answer_format,
    )


@router.get("", response_model=ShopSettingsOut)
def get_settings(db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    return _serialize(get_or_create_settings(db, membership.shop_id))


@router.put("", response_model=ShopSettingsOut, dependencies=[manage_only])
def update_settings(payload: ShopSettingsIn, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    if payload.menu_answer_format not in {"text", "image"}:
        raise HTTPException(status_code=422, detail="รูปแบบคำตอบเมนูไม่ถูกต้อง")
    if payload.receipt_paper_width not in {58, 80}:
        raise HTTPException(status_code=422, detail="ขนาดกระดาษใบเสร็จต้องเป็น 58 หรือ 80 มม.")
    settings = get_or_create_settings(db, membership.shop_id)
    settings.shop_type = payload.shop_type
    settings.shop_name = payload.shop_name
    settings.address = payload.address
    settings.tax_id = payload.tax_id
    settings.promptpay_id = payload.promptpay_id
    settings.loyalty_baht_per_point = payload.loyalty_baht_per_point
    settings.low_stock_line_token = payload.low_stock_line_token
    settings.low_stock_line_target_id = payload.low_stock_line_target_id
    settings.receipt_printer_ip = payload.receipt_printer_ip
    settings.receipt_printer_port = payload.receipt_printer_port
    settings.receipt_paper_width = payload.receipt_paper_width
    settings.receipt_logo_url = payload.receipt_logo_url
    settings.receipt_show_logo = payload.receipt_show_logo
    settings.receipt_footer_text = payload.receipt_footer_text.strip()[:255]
    settings.receipt_show_cashier = payload.receipt_show_cashier
    settings.receipt_show_member = payload.receipt_show_member
    settings.inventory_mode = payload.inventory_mode
    settings.order_parser_mode = payload.order_parser_mode
    settings.ai_api_key = payload.ai_api_key
    settings.menu_answer_format = payload.menu_answer_format
    db.commit()
    db.refresh(settings)
    return _serialize(settings)


@router.post("/receipt-logo", response_model=ShopSettingsOut, dependencies=[manage_only])
def upload_receipt_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    membership: ShopMembership = Depends(get_active_shop_membership),
):
    ext = ALLOWED_LOGO_TYPES.get(file.content_type)
    if ext is None:
        raise HTTPException(status_code=400, detail="รองรับเฉพาะไฟล์ภาพ JPEG, PNG หรือ WEBP")
    contents = file.file.read()
    if len(contents) > MAX_LOGO_SIZE:
        raise HTTPException(status_code=400, detail="ไฟล์โลโก้ต้องมีขนาดไม่เกิน 5MB")

    LOGO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings = get_or_create_settings(db, membership.shop_id)
    old_url = settings.receipt_logo_url
    filename = f"{uuid.uuid4().hex}{ext}"
    (LOGO_UPLOAD_DIR / filename).write_bytes(contents)
    settings.receipt_logo_url = f"/uploads/shop-logos/{filename}"
    db.commit()
    db.refresh(settings)

    if old_url.startswith("/uploads/shop-logos/"):
        (LOGO_UPLOAD_DIR / Path(old_url).name).unlink(missing_ok=True)
    return _serialize(settings)


class PromptPayQrOut(BaseModel):
    payload: str


@router.get("/promptpay-qr", response_model=PromptPayQrOut)
def get_promptpay_qr(amount: float | None = None, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    settings = get_or_create_settings(db, membership.shop_id)
    if not settings.promptpay_id:
        raise HTTPException(status_code=400, detail="ร้านยังไม่ได้ตั้งค่าหมายเลขพร้อมเพย์ในหน้าตั้งค่า")
    try:
        payload = generate_promptpay_payload(settings.promptpay_id, amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PromptPayQrOut(payload=payload)


class LineNotifyTestOut(BaseModel):
    ok: bool
    detail: str


@router.post("/test-line-notify", response_model=LineNotifyTestOut, dependencies=[manage_only])
def test_line_notify(db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    settings = get_or_create_settings(db, membership.shop_id)
    low_stock = db.query(Product).filter(Product.shop_id == membership.shop_id, Product.stock_quantity <= Product.low_stock_threshold).all()
    message = build_low_stock_message(low_stock) if low_stock else "ทดสอบการแจ้งเตือนสต๊อกใกล้หมดจากระบบ POS"
    try:
        send_line_message(settings.low_stock_line_token, settings.low_stock_line_target_id, message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LineNotifyTestOut(ok=True, detail="ส่งข้อความแจ้งเตือนผ่าน LINE สำเร็จ")
