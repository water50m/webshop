import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_active_shop_membership, get_current_user, require_role
from app.models import BridgeCommandStatus, PrintBridge, PrintBridgeCommand, ShopMembership, UserRole

router = APIRouter(prefix="/api/bridges", tags=["print-bridges"], dependencies=[Depends(get_current_user)])
manage_only = Depends(require_role(UserRole.owner, UserRole.manager))
device_router = APIRouter(prefix="/api/bridge-device", tags=["print-bridge-device"])


class BridgeOut(BaseModel):
    id: int
    name: str
    is_online: bool
    last_seen_at: datetime | None
    wifi_ssid: str
    wifi_rssi: int | None
    printer_connected: bool
    printer_name: str
    printer_address: str
    printer_error: str
    firmware_version: str


class CreateBridgeIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CreatedBridgeOut(BridgeOut):
    device_token: str


class CommandOut(BaseModel):
    id: int
    command: str
    status: str
    result: dict
    created_at: datetime


class QueueCommandIn(BaseModel):
    command: str
    payload: dict = Field(default_factory=dict)


class HeartbeatIn(BaseModel):
    wifi_ssid: str = ""
    wifi_rssi: int | None = None
    printer_connected: bool = False
    printer_name: str = ""
    printer_address: str = ""
    printer_error: str = ""
    firmware_version: str = ""


class CommandResultIn(BaseModel):
    ok: bool
    result: dict = Field(default_factory=dict)


def _serialize(bridge: PrintBridge) -> BridgeOut:
    online = bool(bridge.last_seen_at and bridge.last_seen_at >= datetime.utcnow() - timedelta(seconds=45))
    return BridgeOut(
        id=bridge.id, name=bridge.name, is_online=online, last_seen_at=bridge.last_seen_at,
        wifi_ssid=bridge.wifi_ssid, wifi_rssi=bridge.wifi_rssi, printer_connected=bridge.printer_connected,
        printer_name=bridge.printer_name, printer_address=bridge.printer_address,
        printer_error=bridge.printer_error, firmware_version=bridge.firmware_version,
    )


@router.get("", response_model=list[BridgeOut], dependencies=[manage_only])
def list_bridges(db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    return [_serialize(row) for row in db.query(PrintBridge).filter_by(shop_id=membership.shop_id).order_by(PrintBridge.name).all()]


@router.post("", response_model=CreatedBridgeOut, dependencies=[manage_only])
def create_bridge(payload: CreateBridgeIn, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    if db.query(PrintBridge).filter_by(shop_id=membership.shop_id, name=payload.name).first():
        raise HTTPException(status_code=400, detail="มีชื่อ Bridge นี้แล้ว")
    bridge = PrintBridge(shop_id=membership.shop_id, name=payload.name, device_token=secrets.token_urlsafe(32))
    db.add(bridge)
    db.commit()
    db.refresh(bridge)
    return CreatedBridgeOut(**_serialize(bridge).model_dump(), device_token=bridge.device_token)


@router.get("/{bridge_id}/commands", response_model=list[CommandOut], dependencies=[manage_only])
def list_commands(bridge_id: int, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    if not db.query(PrintBridge).filter_by(id=bridge_id, shop_id=membership.shop_id).first():
        raise HTTPException(status_code=404, detail="ไม่พบ Print Bridge")
    return [CommandOut(id=row.id, command=row.command, status=row.status.value, result=row.result, created_at=row.created_at)
            for row in db.query(PrintBridgeCommand).filter(PrintBridgeCommand.bridge_id == bridge_id)
            .order_by(PrintBridgeCommand.created_at.desc()).limit(12).all()]


@router.post("/{bridge_id}/commands", response_model=CommandOut, dependencies=[manage_only])
def queue_command(bridge_id: int, payload: QueueCommandIn, db: Session = Depends(get_db), membership: ShopMembership = Depends(get_active_shop_membership)):
    if not db.query(PrintBridge).filter_by(id=bridge_id, shop_id=membership.shop_id).first():
        raise HTTPException(status_code=404, detail="ไม่พบ Print Bridge")
    allowed = {"scan_bluetooth", "connect_printer", "reconnect_printer", "test_printer", "test_bridge", "configure_wifi"}
    if payload.command not in allowed:
        raise HTTPException(status_code=400, detail="คำสั่ง Bridge ไม่ถูกต้อง")
    if payload.command == "connect_printer" and not payload.payload.get("address"):
        raise HTTPException(status_code=400, detail="กรุณาระบุ Bluetooth address ของเครื่องพิมพ์")
    if payload.command == "configure_wifi" and (not payload.payload.get("ssid") or not payload.payload.get("password")):
        raise HTTPException(status_code=400, detail="กรุณาระบุชื่อและรหัสผ่าน Wi-Fi")
    command = PrintBridgeCommand(bridge_id=bridge_id, command=payload.command, payload=payload.payload)
    db.add(command)
    db.commit()
    db.refresh(command)
    return CommandOut(id=command.id, command=command.command, status=command.status.value, result=command.result, created_at=command.created_at)


def _device(token: str | None, db: Session) -> PrintBridge:
    if not token:
        raise HTTPException(status_code=401, detail="ต้องส่ง X-Bridge-Token")
    bridge = db.query(PrintBridge).filter(PrintBridge.device_token == token).first()
    if bridge is None:
        raise HTTPException(status_code=401, detail="Bridge token ไม่ถูกต้อง")
    return bridge


@device_router.post("/heartbeat")
def heartbeat(payload: HeartbeatIn, x_bridge_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    bridge = _device(x_bridge_token, db)
    bridge.last_seen_at = datetime.utcnow()
    bridge.is_online = True
    for field in ("wifi_ssid", "wifi_rssi", "printer_connected", "printer_name", "printer_address", "printer_error", "firmware_version"):
        setattr(bridge, field, getattr(payload, field))
    db.commit()
    return {"ok": True}


@device_router.get("/commands")
def next_command(x_bridge_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    bridge = _device(x_bridge_token, db)
    bridge.last_seen_at = datetime.utcnow()
    command = db.query(PrintBridgeCommand).filter(
        PrintBridgeCommand.bridge_id == bridge.id, PrintBridgeCommand.status == BridgeCommandStatus.pending
    ).order_by(PrintBridgeCommand.created_at).first()
    if command is None:
        db.commit()
        return {"command": None}
    command.status = BridgeCommandStatus.delivered
    command.delivered_at = datetime.utcnow()
    db.commit()
    return {"command": {"id": command.id, "command": command.command, "payload": command.payload}}


@device_router.post("/commands/{command_id}/result")
def command_result(command_id: int, payload: CommandResultIn, x_bridge_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    bridge = _device(x_bridge_token, db)
    command = db.get(PrintBridgeCommand, command_id)
    if command is None or command.bridge_id != bridge.id:
        raise HTTPException(status_code=404, detail="ไม่พบคำสั่ง")
    command.status = BridgeCommandStatus.succeeded if payload.ok else BridgeCommandStatus.failed
    command.result = payload.result
    command.completed_at = datetime.utcnow()
    # Never retain a Wi-Fi password after the bridge has fetched this command.
    if command.command == "configure_wifi":
        command.payload = {"ssid": command.payload.get("ssid", ""), "password": "[removed]"}
    db.commit()
    return {"ok": True}
