from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_role
from app.models import InventoryMode, OrderParserMode, Product, ShopSettings, ShopType, UserRole
from app.services.line_notify import build_low_stock_message, send_line_message
from app.services.promptpay import generate_promptpay_payload

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(get_current_user)])
manage_only = Depends(require_role(UserRole.owner, UserRole.manager))


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
    inventory_mode: InventoryMode = InventoryMode.simple
    order_parser_mode: OrderParserMode = OrderParserMode.algorithm
    ai_api_key: str = ""
    menu_answer_format: str = "text"


def get_or_create_settings(db: Session) -> ShopSettings:
    settings = db.get(ShopSettings, 1)
    if settings is None:
        settings = ShopSettings(id=1, shop_type=ShopType.individual)
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
        inventory_mode=settings.inventory_mode.value,
        order_parser_mode=settings.order_parser_mode.value,
        ai_api_key=settings.ai_api_key,
        menu_answer_format=settings.menu_answer_format,
    )


@router.get("", response_model=ShopSettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return _serialize(get_or_create_settings(db))


@router.put("", response_model=ShopSettingsOut, dependencies=[manage_only])
def update_settings(payload: ShopSettingsIn, db: Session = Depends(get_db)):
    if payload.menu_answer_format not in {"text", "image"}:
        raise HTTPException(status_code=422, detail="รูปแบบคำตอบเมนูไม่ถูกต้อง")
    settings = get_or_create_settings(db)
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
    settings.inventory_mode = payload.inventory_mode
    settings.order_parser_mode = payload.order_parser_mode
    settings.ai_api_key = payload.ai_api_key
    settings.menu_answer_format = payload.menu_answer_format
    db.commit()
    db.refresh(settings)
    return _serialize(settings)


class PromptPayQrOut(BaseModel):
    payload: str


@router.get("/promptpay-qr", response_model=PromptPayQrOut)
def get_promptpay_qr(amount: float | None = None, db: Session = Depends(get_db)):
    settings = get_or_create_settings(db)
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
def test_line_notify(db: Session = Depends(get_db)):
    settings = get_or_create_settings(db)
    low_stock = db.query(Product).filter(Product.stock_quantity <= Product.low_stock_threshold).all()
    message = build_low_stock_message(low_stock) if low_stock else "ทดสอบการแจ้งเตือนสต๊อกใกล้หมดจากระบบ POS"
    try:
        send_line_message(settings.low_stock_line_token, settings.low_stock_line_target_id, message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LineNotifyTestOut(ok=True, detail="ส่งข้อความแจ้งเตือนผ่าน LINE สำเร็จ")
