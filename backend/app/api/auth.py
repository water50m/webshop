from datetime import datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from urllib.parse import urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
import httpx
import logging
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.config import settings
from app.deps import SESSION_COOKIE_NAME, get_current_user
from app.models import Channel, ChannelAuditLog, ChannelMembership, ChannelMembershipRole, ChannelType, FacebookIdentity, MetaOAuthAttempt, Shop, ShopMembership, ShopMembershipRole, User, UserRole
from app.services.auth import create_session, delete_session, hash_password, hash_pin, verify_password, verify_pin
from app.services.meta_tokens import MetaTokenConfigurationError, decrypt_access_token, encrypt_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

_GRAPH_API = "https://graph.facebook.com/v22.0"
_FACEBOOK_SCOPES = ("public_profile", "pages_show_list", "pages_read_engagement", "pages_manage_metadata", "pages_messaging")
_ATTEMPT_TTL = timedelta(minutes=15)


class LoginIn(BaseModel):
    username: str
    password: str


class UnlockIn(BaseModel):
    username: str
    pin: str


class SetPinIn(BaseModel):
    pin: str


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    has_pin: bool


class FacebookStartOut(BaseModel):
    authorization_url: str


class FacebookPageOut(BaseModel):
    id: str
    name: str
    registered: bool
    channel_id: int | None = None
    shop_id: int | None = None


class FacebookPendingOut(BaseModel):
    id: str
    pages: list[FacebookPageOut]


class FacebookPageIn(BaseModel):
    page_id: str


def _serialize(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role.value,
        has_pin=user.pin_hash is not None,
    )


def _facebook_frontend_url() -> str:
    return (settings.meta_oauth_login_frontend_url or settings.meta_oauth_frontend_url).rstrip("/")


def facebook_onboarding_url() -> str:
    """Return the frontend root onboarding route, not the legacy /facebook page."""
    configured = _facebook_frontend_url()
    parts = urlsplit(configured)
    return urlunsplit((parts.scheme, parts.netloc, "/onboarding", "", ""))


def _require_facebook_oauth() -> None:
    if not all((settings.meta_app_id, settings.meta_app_secret, settings.meta_oauth_redirect_uri, _facebook_frontend_url(), settings.meta_token_encryption_key)):
        raise HTTPException(status_code=503, detail="ยังตั้งค่า Meta OAuth ไม่ครบ")


def _set_session(response: Response, db: Session, user: User) -> None:
    session = create_session(db, user)
    db.commit()
    response.set_cookie(SESSION_COOKIE_NAME, session.token, httponly=True, samesite="lax", max_age=7 * 24 * 60 * 60)


def complete_facebook_login(
    db: Session,
    attempt: MetaOAuthAttempt,
    facebook_name: str = "",
    profile_picture_url: str = "",
) -> User:
    """Create/retrieve an identity and grant only currently verified Page access."""
    identity = db.query(FacebookIdentity).filter_by(facebook_user_id=attempt.facebook_user_id).first()
    if identity is None:
        # Facebook IDs are opaque; this local username is never presented as a Facebook identity.
        username = f"facebook_{attempt.facebook_user_id[-20:]}"
        while db.query(User).filter_by(username=username).first():
            username = f"facebook_{token_urlsafe(12).lower().replace('-', '')[:20]}"
        user = User(username=username, password_hash=hash_password(token_urlsafe(32)), display_name="Facebook user", role=UserRole.cashier)
        db.add(user)
        db.flush()
        identity = FacebookIdentity(
            user_id=user.id,
            facebook_user_id=attempt.facebook_user_id,
            facebook_name=facebook_name[:255],
            profile_picture_url=profile_picture_url[:2000],
        )
        db.add(identity)
    else:
        user = identity.user
        identity.last_verified_at = datetime.utcnow()

    if facebook_name:
        identity.facebook_name = facebook_name[:255]
    if profile_picture_url:
        identity.profile_picture_url = profile_picture_url[:2000]

    facebook_page_ids = {str(page.get("id")) for page in attempt.available_pages}
    channels = db.query(Channel).filter(Channel.type == ChannelType.facebook_page, Channel.external_id.in_(facebook_page_ids)).all() if facebook_page_ids else []
    for channel in channels:
        membership = db.query(ChannelMembership).filter_by(channel_id=channel.id, user_id=user.id).first()
        if membership is None:
            db.add(ChannelMembership(channel_id=channel.id, user_id=user.id, role=ChannelMembershipRole.page_manager, granted_by_user_id=None))
            db.add(ChannelAuditLog(channel_id=channel.id, actor_user_id=user.id, target_user_id=user.id, action="facebook_admin_access_granted", detail={"page_id": channel.external_id}))
        # A revoked membership intentionally remains revoked until page_owner approves it.
        if channel.shop_id and not db.query(ShopMembership).filter_by(shop_id=channel.shop_id, user_id=user.id).first():
            db.add(ShopMembership(shop_id=channel.shop_id, user_id=user.id, role=ShopMembershipRole.manager, is_active=True))
    identity.last_verified_at = datetime.utcnow()
    db.flush()
    return user


@router.post("/facebook/start", response_model=FacebookStartOut)
def facebook_start(db: Session = Depends(get_db)):
    _require_facebook_oauth()
    verifier = token_urlsafe(64)
    challenge = sha256(verifier.encode()).digest()
    import base64
    code_challenge = base64.urlsafe_b64encode(challenge).decode().rstrip("=")
    attempt = MetaOAuthAttempt(id=token_urlsafe(32), purpose="facebook_login", code_verifier=verifier, expires_at=datetime.utcnow() + _ATTEMPT_TTL)
    db.add(attempt)
    db.commit()
    params = {"client_id": settings.meta_app_id, "redirect_uri": settings.meta_oauth_redirect_uri, "state": attempt.id, "response_type": "code", "scope": ",".join(_FACEBOOK_SCOPES), "code_challenge": code_challenge, "code_challenge_method": "S256"}
    return FacebookStartOut(authorization_url=f"https://www.facebook.com/v22.0/dialog/oauth?{urlencode(params)}")


def _pending_for_user(db: Session, attempt_id: str, user: User) -> MetaOAuthAttempt:
    attempt = db.get(MetaOAuthAttempt, attempt_id)
    if attempt is None or attempt.purpose != "facebook_login" or attempt.initiated_by_user_id != user.id or attempt.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=404, detail="ไม่พบหรือหมดอายุรายการ Facebook login")
    return attempt


@router.get("/facebook/pending/{attempt_id}", response_model=FacebookPendingOut)
def facebook_pending(attempt_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attempt = _pending_for_user(db, attempt_id, user)
    pages = []
    for page in attempt.available_pages:
        channel = db.query(Channel).filter_by(type=ChannelType.facebook_page, external_id=str(page.get("id"))).first()
        pages.append(FacebookPageOut(id=str(page["id"]), name=str(page.get("name") or "Facebook Page"), registered=channel is not None, channel_id=channel.id if channel else None, shop_id=channel.shop_id if channel else None))
    return FacebookPendingOut(id=attempt.id, pages=pages)


def _page_from_attempt(attempt: MetaOAuthAttempt, page_id: str) -> dict:
    page = next((item for item in attempt.available_pages if str(item.get("id")) == page_id), None)
    if page is None:
        raise HTTPException(status_code=422, detail="เพจที่เลือกไม่อยู่ในรายการสิทธิ์ Facebook")
    return page


@router.post("/facebook/pending/{attempt_id}/register", response_model=FacebookPageOut)
def facebook_register_page(attempt_id: str, payload: FacebookPageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attempt = _pending_for_user(db, attempt_id, user)
    page = _page_from_attempt(attempt, payload.page_id)
    if db.query(Channel).filter_by(type=ChannelType.facebook_page, external_id=payload.page_id).first():
        raise HTTPException(status_code=409, detail="Facebook Page นี้ลงทะเบียนแล้ว")
    try:
        token = decrypt_access_token(str(page["access_token"]))
        response = httpx.post(f"{_GRAPH_API}/{payload.page_id}/subscribed_apps", params={"subscribed_fields": "messages,messaging_postbacks", "access_token": token}, timeout=15)
        response.raise_for_status()
        encrypted_token = encrypt_access_token(token)
    except (httpx.HTTPError, KeyError, MetaTokenConfigurationError):
        raise HTTPException(status_code=502, detail="ไม่สามารถเชื่อม Webhook กับ Facebook Page นี้ได้") from None
    shop = Shop(name=str(page.get("name") or "Facebook Shop")[:255])
    db.add(shop); db.flush()
    db.add(ShopMembership(shop_id=shop.id, user_id=user.id, role=ShopMembershipRole.owner))
    channel = Channel(shop_id=shop.id, type=ChannelType.facebook_page, external_id=payload.page_id, name=str(page.get("name") or "")[:255], access_token=encrypted_token, connected_facebook_user_id=attempt.facebook_user_id)
    db.add(channel); db.flush()
    db.add(ChannelMembership(channel_id=channel.id, user_id=user.id, role=ChannelMembershipRole.page_owner, granted_by_user_id=user.id))
    db.add(ChannelAuditLog(channel_id=channel.id, actor_user_id=user.id, action="facebook_page_registered", detail={"page_id": payload.page_id}))
    attempt.completed_at = datetime.utcnow(); attempt.available_pages = []
    db.commit()
    return FacebookPageOut(id=payload.page_id, name=channel.name, registered=True, channel_id=channel.id, shop_id=shop.id)


@router.post("/facebook/pending/{attempt_id}/select", response_model=FacebookPageOut)
def facebook_select_page(attempt_id: str, payload: FacebookPageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attempt = _pending_for_user(db, attempt_id, user)
    page = _page_from_attempt(attempt, payload.page_id)
    channel = db.query(Channel).filter_by(type=ChannelType.facebook_page, external_id=payload.page_id).first()
    membership = db.query(ChannelMembership).filter_by(channel_id=channel.id if channel else None, user_id=user.id, is_active=True).first()
    if channel is None or membership is None:
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เข้าถึง Facebook Page นี้")
    # A Facebook login can select an already registered Page.  Refresh its
    # Page token and webhook subscription here too; previously this path only
    # switched shops, leaving legacy/expired connections unable to receive
    # Messenger events.
    try:
        token = decrypt_access_token(str(page["access_token"]))
        response = httpx.post(
            f"{_GRAPH_API}/{payload.page_id}/subscribed_apps",
            params={"subscribed_fields": "messages,messaging_postbacks", "access_token": token},
            timeout=15.0,
        )
        response.raise_for_status()
        channel.access_token = encrypt_access_token(token)
    except (httpx.HTTPError, KeyError, MetaTokenConfigurationError):
        raise HTTPException(status_code=502, detail="ไม่สามารถเชื่อม Webhook กับ Facebook Page นี้ได้") from None
    channel.name = str(page.get("name") or channel.name)[:255]
    channel.connected_facebook_user_id = attempt.facebook_user_id
    db.add(ChannelAuditLog(channel_id=channel.id, actor_user_id=user.id, action="facebook_page_token_refreshed", detail={"page_id": channel.external_id}))
    attempt.completed_at = datetime.utcnow(); attempt.available_pages = []
    db.commit()
    return FacebookPageOut(id=channel.external_id, name=channel.name, registered=True, channel_id=channel.id, shop_id=channel.shop_id)


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    session = create_session(db, user)
    db.commit()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
    )
    return _serialize(user)


@router.post("/unlock", response_model=UserOut)
def unlock(payload: UnlockIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or user.pin_hash is None or not verify_pin(payload.pin, user.pin_hash):
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือ PIN ไม่ถูกต้อง")
    session = create_session(db, user)
    db.commit()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
    )
    return _serialize(user)


@router.post("/set-pin")
def set_pin(payload: SetPinIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not payload.pin.isdigit() or len(payload.pin) < 4:
        raise HTTPException(status_code=400, detail="PIN ต้องเป็นตัวเลขอย่างน้อย 4 หลัก")
    user.pin_hash = hash_pin(payload.pin)
    db.commit()
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        delete_session(db, token)
        db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _serialize(user)
