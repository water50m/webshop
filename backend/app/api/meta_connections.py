"""Owner-only Facebook Page onboarding via Meta OAuth."""

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from secrets import token_urlsafe
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import accessible_channel_ids, get_active_shop_membership, get_current_user, require_channel_access, require_role
from app.models import Channel, ChannelAuditLog, ChannelMembership, ChannelMembershipRole, ChannelType, DataDeletionRequest, FacebookIdentity, MetaOAuthAttempt, Shop, ShopMembership, ShopMembershipRole, User, UserRole
from app.services.page_data_deletion import delete_page_data
from app.services.meta_tokens import MetaTokenConfigurationError, decrypt_access_token, encrypt_access_token

router = APIRouter(prefix="/api/meta/facebook", tags=["meta-facebook"])

_GRAPH_API = "https://graph.facebook.com/v22.0"
_OAUTH_SCOPES = ("pages_show_list", "pages_read_engagement", "pages_manage_metadata", "pages_messaging")
_ATTEMPT_TTL = timedelta(minutes=15)


class ConnectionStartOut(BaseModel):
    authorization_url: str


class PageOut(BaseModel):
    id: str
    name: str
    category: str = ""
    tasks: list[str] = []


class PendingConnectionOut(BaseModel):
    id: str
    expires_at: str
    pages: list[PageOut]


class SelectPageIn(BaseModel):
    page_id: str


class ConnectionOut(BaseModel):
    id: int
    page_id: str
    name: str
    shop_id: int
    connected_at: str


class ConnectionStatusOut(BaseModel):
    channel_id: int
    connected: bool
    token_valid: bool
    detail: str


class DeletePageDataIn(BaseModel):
    confirmation: bool = False


class PublicDeletionRequestIn(BaseModel):
    page_id: str
    requester_email: str = ""
    requester_name: str = ""


class DeletionRequestOut(BaseModel):
    confirmation_code: str
    status: str
    detail: str


def _new_deletion_request(
    db: Session, *, page_id: str, source: str, status: str, requester_email: str = "", requester_name: str = "", detail: dict | None = None
) -> DataDeletionRequest:
    request = DataDeletionRequest(
        confirmation_code=token_urlsafe(24),
        page_external_id=page_id,
        request_source=source,
        status=status,
        requester_email=requester_email[:255],
        requester_name=requester_name[:255],
        detail=detail or {},
        completed_at=datetime.utcnow() if status == "completed" else None,
    )
    db.add(request)
    return request


def _deletion_url(code: str) -> str:
    return f"{settings.meta_public_web_url.rstrip('/')}/data-deletion?code={code}"


def _decode_signed_request(signed_request: str) -> dict:
    """Verify Meta's Data Deletion Callback payload without logging its contents."""
    try:
        encoded_signature, encoded_payload = signed_request.split(".", 1)
        signature = base64.urlsafe_b64decode(encoded_signature + "=" * (-len(encoded_signature) % 4))
        expected = hmac.new(settings.meta_app_secret.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4)))
        if not isinstance(payload, dict) or not payload.get("user_id"):
            raise ValueError("payload")
        return payload
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="signed_request ไม่ถูกต้อง") from exc


def _require_oauth_config() -> None:
    missing = [
        name
        for name, value in (
            ("META_APP_ID", settings.meta_app_id),
            ("META_APP_SECRET", settings.meta_app_secret),
            ("META_OAUTH_REDIRECT_URI", settings.meta_oauth_redirect_uri),
            ("META_OAUTH_FRONTEND_URL", settings.meta_oauth_frontend_url),
            ("META_TOKEN_ENCRYPTION_KEY", settings.meta_token_encryption_key),
        )
        if not value
    ]
    if missing:
        raise HTTPException(status_code=503, detail=f"ยังตั้งค่า Meta OAuth ไม่ครบ: {', '.join(missing)}")


def _active_attempt(db: Session, attempt_id: str, user: User) -> MetaOAuthAttempt:
    attempt = db.get(MetaOAuthAttempt, attempt_id)
    if attempt is None or attempt.initiated_by_user_id != user.id:
        raise HTTPException(status_code=404, detail="ไม่พบรายการเชื่อมเพจ")
    if attempt.completed_at is not None:
        raise HTTPException(status_code=409, detail="รายการเชื่อมเพจนี้ถูกใช้ไปแล้ว")
    if attempt.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=410, detail="รายการเชื่อมเพจหมดอายุ กรุณาเริ่มใหม่")
    return attempt


def _connection_out(channel: Channel) -> ConnectionOut:
    if channel.shop_id is None:
        raise HTTPException(status_code=409, detail="Facebook Page นี้ยังไม่มีร้านที่ผูกไว้")
    return ConnectionOut(id=channel.id, page_id=channel.external_id, name=channel.name, shop_id=channel.shop_id, connected_at=channel.created_at.isoformat())


@router.post("/connections/start", response_model=ConnectionStartOut, dependencies=[Depends(require_role(UserRole.owner))])
def start_connection(db: Session = Depends(get_db), user: User = Depends(get_current_user), membership: ShopMembership = Depends(get_active_shop_membership)):
    _require_oauth_config()
    attempt = MetaOAuthAttempt(
        id=token_urlsafe(32),
        initiated_by_user_id=user.id,
        shop_id=membership.shop_id,
        expires_at=datetime.utcnow() + _ATTEMPT_TTL,
    )
    db.add(attempt)
    db.commit()
    params = {
        "client_id": settings.meta_app_id,
        "redirect_uri": settings.meta_oauth_redirect_uri,
        "state": attempt.id,
        "response_type": "code",
        "scope": ",".join(_OAUTH_SCOPES),
    }
    return ConnectionStartOut(authorization_url=f"https://www.facebook.com/v22.0/dialog/oauth?{urlencode(params)}")


@router.get("/callback", include_in_schema=False)
def oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    _require_oauth_config()
    if not state:
        raise HTTPException(status_code=400, detail="Meta OAuth ไม่ส่ง state กลับมา")
    attempt = db.get(MetaOAuthAttempt, state)
    if attempt is None or attempt.completed_at is not None or attempt.callback_completed_at is not None or attempt.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="ลิงก์เชื่อม Facebook ไม่ถูกต้องหรือหมดอายุ")
    if error or not code:
        return RedirectResponse(f"{settings.meta_oauth_frontend_url}?facebook_error=cancelled")
    try:
        token_response = httpx.get(
            f"{_GRAPH_API}/oauth/access_token",
            params={
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret,
                "redirect_uri": settings.meta_oauth_redirect_uri,
                "code": code,
                **({"code_verifier": attempt.code_verifier} if attempt.code_verifier else {}),
            },
            timeout=15.0,
        )
        token_response.raise_for_status()
        user_token = str(token_response.json().get("access_token") or "")
        if not user_token:
            raise ValueError("missing access token")
        profile_response = httpx.get(
            f"{_GRAPH_API}/me",
            params={"fields": "id,name,picture.type(large)", "access_token": user_token},
            timeout=15.0,
        )
        profile_response.raise_for_status()
        profile = profile_response.json()
        facebook_user_id = str(profile.get("id") or "")
        if not facebook_user_id:
            raise ValueError("missing Facebook user id")
        facebook_name = str(profile.get("name") or "").strip()
        picture = profile.get("picture")
        profile_picture_url = str(picture.get("data", {}).get("url") or "") if isinstance(picture, dict) else ""
        pages_response = httpx.get(
            f"{_GRAPH_API}/me/accounts",
            params={"fields": "id,name,category,tasks,access_token", "access_token": user_token},
            timeout=15.0,
        )
        pages_response.raise_for_status()
        raw_pages = pages_response.json().get("data", [])
    except httpx.HTTPStatusError as exc:
        # Do not log the request URL: it contains OAuth secrets and codes.
        logging.warning("Facebook OAuth token exchange failed with HTTP %s", exc.response.status_code)
        return RedirectResponse(f"{settings.meta_oauth_frontend_url}?facebook_error=token_exchange")
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        # Preserve credentials by recording only the exception class, never
        # the request URL, authorization code, access token, or secret.
        logging.warning("Facebook OAuth token exchange failed before a valid response (%s)", type(exc).__name__)
        return RedirectResponse(f"{settings.meta_oauth_frontend_url}?facebook_error=token_exchange")
    try:
        # Only encrypted Page tokens are retained between callback and the
        # owner's page-selection click. The user token is not needed after
        # this response and is deliberately discarded.
        pages = [
            {
                "id": str(page.get("id") or ""),
                "name": str(page.get("name") or ""),
                "category": str(page.get("category") or ""),
                "tasks": [str(task) for task in page.get("tasks", [])],
                "access_token": encrypt_access_token(str(page.get("access_token") or "")),
            }
            for page in raw_pages
            if page.get("id") and page.get("access_token")
        ]
    except MetaTokenConfigurationError:
        return RedirectResponse(f"{settings.meta_oauth_frontend_url}?facebook_error=token_encryption")
    attempt.facebook_user_id = facebook_user_id
    attempt.available_pages = pages
    attempt.callback_completed_at = datetime.utcnow()
    if attempt.purpose == "facebook_login":
        # The public login flow creates its session only after the callback has
        # verified the app-scoped identity and the current Page list.
        from app.api.auth import complete_facebook_login
        user = complete_facebook_login(db, attempt, facebook_name, profile_picture_url)
        attempt.initiated_by_user_id = user.id
        db.commit()
        from app.api.auth import facebook_onboarding_url
        response = RedirectResponse(f"{facebook_onboarding_url()}?facebook_login={attempt.id}")
        from app.deps import SESSION_COOKIE_NAME
        from app.services.auth import create_session
        session = create_session(db, user)
        db.commit()
        response.set_cookie(SESSION_COOKIE_NAME, session.token, httponly=True, samesite="lax", max_age=7 * 24 * 60 * 60)
        return response
    if attempt.purpose == "account_pages":
        user = db.get(User, attempt.initiated_by_user_id)
        identity = db.query(FacebookIdentity).filter_by(user_id=user.id if user else None).first()
        if identity is None or identity.facebook_user_id != facebook_user_id:
            # The page list must be tied to the same Facebook account that
            # created this SStore session; never let an account switch here.
            attempt.completed_at = datetime.utcnow()
            db.commit()
            return RedirectResponse(f"{settings.meta_oauth_frontend_url.rstrip('/')}/my-pages?facebook_error=identity_mismatch")
        identity.facebook_name = facebook_name[:255] or identity.facebook_name
        identity.profile_picture_url = profile_picture_url[:2000] or identity.profile_picture_url
        identity.last_verified_at = datetime.utcnow()
        db.commit()
        return RedirectResponse(f"{settings.meta_oauth_frontend_url.rstrip('/')}/my-pages?facebook_pages={attempt.id}")
    db.commit()
    return RedirectResponse(f"{settings.meta_oauth_frontend_url}?facebook_connection={attempt.id}")


@router.get("/connections/pending/{attempt_id}", response_model=PendingConnectionOut, dependencies=[Depends(require_role(UserRole.owner))])
def get_pending_connection(attempt_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attempt = _active_attempt(db, attempt_id, user)
    pages = [PageOut(id=page["id"], name=page["name"], category=page.get("category", ""), tasks=page.get("tasks", [])) for page in attempt.available_pages]
    return PendingConnectionOut(id=attempt.id, expires_at=attempt.expires_at.isoformat(), pages=pages)


@router.post("/connections/pending/{attempt_id}/select", response_model=ConnectionOut, dependencies=[Depends(require_role(UserRole.owner))])
def select_page(attempt_id: str, payload: SelectPageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attempt = _active_attempt(db, attempt_id, user)
    page = next((page for page in attempt.available_pages if page.get("id") == payload.page_id), None)
    if page is None:
        raise HTTPException(status_code=422, detail="เพจที่เลือกไม่อยู่ในรายการสิทธิ์ Facebook")
    try:
        page_token = decrypt_access_token(str(page["access_token"]))
        subscribed = httpx.post(
            f"{_GRAPH_API}/{page['id']}/subscribed_apps",
            params={"subscribed_fields": "messages,messaging_postbacks", "access_token": page_token},
            timeout=15.0,
        )
        subscribed.raise_for_status()
        encrypted_token = encrypt_access_token(page_token)
    except (httpx.HTTPError, KeyError, MetaTokenConfigurationError):
        raise HTTPException(status_code=502, detail="ไม่สามารถผูก Webhook กับ Facebook Page นี้ได้") from None
    channel = db.query(Channel).filter_by(type=ChannelType.facebook_page, external_id=str(page["id"])).first()
    if channel is None:
        # A Page is an operationally independent store.  It owns its own
        # catalog, stock, POS bills, settings and staff membership boundary.
        # Do not attach a second Page to the Shop that happened to be active
        # when the owner started the OAuth flow.
        shop = Shop(name=str(page.get("name") or "Facebook Shop")[:255])
        db.add(shop)
        db.flush()
        db.add(ShopMembership(shop_id=shop.id, user_id=user.id, role=ShopMembershipRole.owner))
        channel = Channel(shop_id=shop.id, type=ChannelType.facebook_page, external_id=str(page["id"]), name=str(page.get("name") or ""))
        db.add(channel)
        db.flush()
    elif channel.shop_id is None:
        raise HTTPException(status_code=409, detail="Facebook Page นี้ยังไม่มีร้านที่ผูกไว้")
    channel.name = str(page.get("name") or "")[:255]
    channel.access_token = encrypted_token
    channel.connected_facebook_user_id = attempt.facebook_user_id
    # The person verified by Facebook as a Page administrator also needs the
    # matching Shop membership; every catalog/POS endpoint is scoped by Shop.
    if not db.query(ShopMembership).filter_by(shop_id=channel.shop_id, user_id=user.id).first():
        db.add(ShopMembership(shop_id=channel.shop_id, user_id=user.id, role=ShopMembershipRole.manager))
    membership = db.query(ChannelMembership).filter_by(channel_id=channel.id, user_id=user.id).first()
    if membership is None:
        db.add(ChannelMembership(channel_id=channel.id, user_id=user.id, role=ChannelMembershipRole.page_owner, granted_by_user_id=user.id))
    else:
        membership.is_active = True
    db.add(ChannelAuditLog(channel_id=channel.id, actor_user_id=user.id, action="facebook_connected", detail={"page_id": channel.external_id}))
    attempt.available_pages = []
    attempt.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(channel)
    return _connection_out(channel)


@router.get("/connections", response_model=list[ConnectionOut])
def list_connections(db: Session = Depends(get_db), user: User = Depends(get_current_user), membership: ShopMembership = Depends(get_active_shop_membership)):
    channels = (
        db.query(Channel)
        .filter(Channel.type == ChannelType.facebook_page, Channel.shop_id == membership.shop_id, Channel.access_token != "", Channel.id.in_(accessible_channel_ids(user, db)))
        .order_by(Channel.name, Channel.id)
        .all()
    )
    return [_connection_out(channel) for channel in channels]


@router.get("/connections/{channel_id}/status", response_model=ConnectionStatusOut)
def connection_status(channel_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel = db.get(Channel, channel_id)
    if channel is None or channel.type != ChannelType.facebook_page:
        raise HTTPException(status_code=404, detail="ไม่พบ Facebook Page ที่เชื่อมต่อ")
    require_channel_access(channel_id, user, db)
    if not channel.access_token:
        return ConnectionStatusOut(channel_id=channel_id, connected=False, token_valid=False, detail="เพจถูกยกเลิกการเชื่อมต่อแล้ว")
    try:
        token = decrypt_access_token(channel.access_token)
        response = httpx.get(f"{_GRAPH_API}/{channel.external_id}", params={"fields": "id,name", "access_token": token}, timeout=10.0)
        response.raise_for_status()
    except (httpx.HTTPError, MetaTokenConfigurationError):
        return ConnectionStatusOut(channel_id=channel_id, connected=True, token_valid=False, detail="ตรวจสอบ token ไม่ผ่าน กรุณาเชื่อม Facebook ใหม่")
    return ConnectionStatusOut(channel_id=channel_id, connected=True, token_valid=True, detail="token พร้อมใช้งาน")


@router.delete("/connections/{channel_id}")
def disconnect_page(channel_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel = db.get(Channel, channel_id)
    if channel is None or channel.type != ChannelType.facebook_page:
        raise HTTPException(status_code=404, detail="ไม่พบ Facebook Page ที่เชื่อมต่อ")
    require_channel_access(channel_id, user, db, ChannelMembershipRole.page_owner)
    try:
        token = decrypt_access_token(channel.access_token)
        if token:
            httpx.delete(f"{_GRAPH_API}/{channel.external_id}/subscribed_apps", params={"access_token": token}, timeout=10.0)
    except (httpx.HTTPError, MetaTokenConfigurationError):
        # Local disconnection must still remove the token if Meta is unavailable.
        pass
    channel.access_token = ""
    db.add(ChannelAuditLog(channel_id=channel.id, actor_user_id=user.id, action="facebook_disconnected", detail={}))
    db.commit()
    return {"ok": True}


@router.delete("/connections/{channel_id}/data", response_model=DeletionRequestOut)
def delete_connected_page_data(channel_id: int, payload: DeletePageDataIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Owner-confirmed irreversible deletion, precisely scoped to one Page."""
    if not payload.confirmation:
        raise HTTPException(status_code=422, detail="ต้องยืนยันการลบข้อมูลก่อน")
    channel = db.get(Channel, channel_id)
    if channel is None or channel.type != ChannelType.facebook_page:
        raise HTTPException(status_code=404, detail="ไม่พบ Facebook Page ที่เชื่อมต่อ")
    require_channel_access(channel_id, user, db, ChannelMembershipRole.page_owner)
    page_id = channel.external_id
    try:
        token = decrypt_access_token(channel.access_token)
        if token:
            httpx.delete(f"{_GRAPH_API}/{page_id}/subscribed_apps", params={"access_token": token}, timeout=10.0)
    except (httpx.HTTPError, MetaTokenConfigurationError):
        pass
    request = _new_deletion_request(db, page_id=page_id, source="owner_portal", status="completed")
    counts = delete_page_data(db, channel)
    request.detail = counts
    db.commit()
    return DeletionRequestOut(confirmation_code=request.confirmation_code, status=request.status, detail="ลบข้อมูลของ Facebook Page นี้แล้ว")


@router.post("/data-deletion-requests", response_model=DeletionRequestOut)
def create_public_deletion_request(payload: PublicDeletionRequestIn, db: Session = Depends(get_db)):
    """Public, non-destructive request. Identity is verified before action."""
    page_id = payload.page_id.strip()
    if not page_id or len(page_id) > 255:
        raise HTTPException(status_code=422, detail="กรุณาระบุ Page ID ที่ถูกต้อง")
    request = _new_deletion_request(
        db,
        page_id=page_id,
        source="public_form",
        status="pending_verification",
        requester_email=payload.requester_email.strip(),
        requester_name=payload.requester_name.strip(),
    )
    db.commit()
    return DeletionRequestOut(confirmation_code=request.confirmation_code, status=request.status, detail="รับคำขอแล้ว ต้องยืนยันสิทธิ์จัดการเพจก่อนลบข้อมูล")


@router.get("/data-deletion-requests/{confirmation_code}", response_model=DeletionRequestOut)
def get_deletion_request(confirmation_code: str, db: Session = Depends(get_db)):
    request = db.query(DataDeletionRequest).filter_by(confirmation_code=confirmation_code).first()
    if request is None:
        raise HTTPException(status_code=404, detail="ไม่พบรหัสติดตามคำขอ")
    detail = "ลบข้อมูลของเพจตามคำขอเสร็จแล้ว" if request.status == "completed" else "กำลังรอยืนยันสิทธิ์จัดการเพจ"
    return DeletionRequestOut(confirmation_code=request.confirmation_code, status=request.status, detail=detail)


@router.post("/data-deletion-callback", response_model=None)
def meta_data_deletion_callback(signed_request: str = Form(...), db: Session = Depends(get_db)):
    """Endpoint configured in Meta's Data Deletion Callback URL setting."""
    if not settings.meta_app_secret or not settings.meta_public_web_url:
        raise HTTPException(status_code=503, detail="ยังตั้งค่า Meta Data Deletion Callback ไม่ครบ")
    facebook_user_id = str(_decode_signed_request(signed_request)["user_id"])
    channels = (
        db.query(Channel)
        .filter(Channel.type == ChannelType.facebook_page, Channel.connected_facebook_user_id == facebook_user_id)
        .all()
    )
    last_request: DataDeletionRequest | None = None
    for channel in channels:
        page_id = channel.external_id
        last_request = _new_deletion_request(db, page_id=page_id, source="meta_callback", status="completed")
        delete_page_data(db, channel)
    if last_request is None:
        last_request = _new_deletion_request(db, page_id="", source="meta_callback", status="completed")
    db.commit()
    return {"url": _deletion_url(last_request.confirmation_code), "confirmation_code": last_request.confirmation_code}
