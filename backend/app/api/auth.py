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
    has_facebook_identity: bool


class FacebookStartOut(BaseModel):
    authorization_url: str


class NativeSessionOut(UserOut):
    """Only returned to a Capacitor client after a successful credential check."""

    session_token: str


class FacebookNativeLoginIn(BaseModel):
    access_token: str


class FacebookNativeLoginOut(BaseModel):
    user: NativeSessionOut
    attempt_id: str


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
        has_facebook_identity=user.facebook_identity is not None,
    )


def _facebook_frontend_url() -> str:
    return (settings.meta_oauth_login_frontend_url or settings.meta_oauth_frontend_url).rstrip("/")


def facebook_onboarding_url() -> str:
    """Return the frontend root onboarding route, not the legacy /facebook page."""
    configured = _facebook_frontend_url()
    parts = urlsplit(configured)
    return urlunsplit((parts.scheme, parts.netloc, "/onboarding", "", ""))


def facebook_my_pages_url() -> str:
    """Return the absolute page-management route even when the configured
    frontend callback URL currently points at /facebook."""
    configured = _facebook_frontend_url()
    parts = urlsplit(configured)
    return urlunsplit((parts.scheme, parts.netloc, "/my-pages", "", ""))


def _require_facebook_oauth() -> None:
    if not all((settings.meta_app_id, settings.meta_app_secret, settings.meta_oauth_redirect_uri, _facebook_frontend_url(), settings.meta_token_encryption_key)):
        raise HTTPException(status_code=503, detail="ยังตั้งค่า Meta OAuth ไม่ครบ")


def _set_session(response: Response, db: Session, user: User) -> None:
    session = create_session(db, user)
    db.commit()
    response.set_cookie(SESSION_COOKIE_NAME, session.token, httponly=True, samesite="lax", max_age=7 * 24 * 60 * 60)


def _is_native_client(request: Request) -> bool:
    return request.headers.get("X-SStore-Client", "").lower() == "android"


def _native_session_out(db: Session, user: User) -> NativeSessionOut:
    session = create_session(db, user)
    db.commit()
    return NativeSessionOut(**_serialize(user).model_dump(), session_token=session.token)


def _facebook_pages_from_native_token(access_token: str) -> tuple[str, str, str, list[dict]]:
    """Validate a native SDK token with Meta and retain only encrypted Page tokens."""
    try:
        debug_response = httpx.get(
            f"{_GRAPH_API}/debug_token",
            params={"input_token": access_token, "access_token": f"{settings.meta_app_id}|{settings.meta_app_secret}"},
            timeout=15.0,
        )
        debug_response.raise_for_status()
        debug_data = debug_response.json().get("data", {})
        if not debug_data.get("is_valid") or str(debug_data.get("app_id") or "") != settings.meta_app_id:
            raise ValueError("invalid app token")
        profile_response = httpx.get(
            f"{_GRAPH_API}/me",
            params={"fields": "id,name,picture.type(large)", "access_token": access_token},
            timeout=15.0,
        )
        profile_response.raise_for_status()
        profile = profile_response.json()
        facebook_user_id = str(profile.get("id") or "")
        if not facebook_user_id:
            raise ValueError("missing Facebook user id")
        pages_response = httpx.get(
            f"{_GRAPH_API}/me/accounts",
            params={"fields": "id,name,category,tasks,access_token", "access_token": access_token},
            timeout=15.0,
        )
        pages_response.raise_for_status()
        pages = [
            {
                "id": str(page.get("id") or ""),
                "name": str(page.get("name") or ""),
                "category": str(page.get("category") or ""),
                "tasks": [str(task) for task in page.get("tasks", [])],
                "access_token": encrypt_access_token(str(page.get("access_token") or "")),
            }
            for page in pages_response.json().get("data", [])
            if page.get("id") and page.get("access_token")
        ]
        picture = profile.get("picture")
        picture_url = str(picture.get("data", {}).get("url") or "") if isinstance(picture, dict) else ""
        return facebook_user_id, str(profile.get("name") or "").strip(), picture_url, pages
    except (httpx.HTTPError, ValueError, TypeError, MetaTokenConfigurationError):
        raise HTTPException(status_code=401, detail="ไม่สามารถยืนยัน Facebook Login จากแอปได้") from None


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


@router.post("/facebook/native", response_model=FacebookNativeLoginOut)
def facebook_native_login(payload: FacebookNativeLoginIn, request: Request, db: Session = Depends(get_db)):
    """Exchange a token issued by the Android Facebook SDK for an SStore session.

    Page tokens are encrypted before entering the short-lived selection attempt;
    the Facebook user token is discarded immediately after this request.
    """
    _require_facebook_oauth()
    if not _is_native_client(request):
        raise HTTPException(status_code=400, detail="endpoint นี้ใช้สำหรับแอป Android เท่านั้น")
    facebook_user_id, facebook_name, picture_url, pages = _facebook_pages_from_native_token(payload.access_token)
    attempt = MetaOAuthAttempt(
        id=token_urlsafe(32),
        purpose="facebook_login",
        facebook_user_id=facebook_user_id,
        available_pages=pages,
        expires_at=datetime.utcnow() + _ATTEMPT_TTL,
        callback_completed_at=datetime.utcnow(),
    )
    db.add(attempt)
    db.flush()
    user = complete_facebook_login(db, attempt, facebook_name, picture_url)
    attempt.initiated_by_user_id = user.id
    db.commit()
    return FacebookNativeLoginOut(user=_native_session_out(db, user), attempt_id=attempt.id)


def _pending_for_user(db: Session, attempt_id: str, user: User, purpose: str = "facebook_login") -> MetaOAuthAttempt:
    attempt = db.get(MetaOAuthAttempt, attempt_id)
    if attempt is None or attempt.purpose != purpose or attempt.initiated_by_user_id != user.id or attempt.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=404, detail="ไม่พบหรือหมดอายุรายการ Facebook login")
    return attempt


@router.post("/facebook/pages/start", response_model=FacebookStartOut)
def facebook_pages_start(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Re-check only the Pages belonging to the Facebook account in this session."""
    _require_facebook_oauth()
    if user.facebook_identity is None:
        raise HTTPException(status_code=403, detail="หน้านี้ใช้ได้เฉพาะบัญชีที่ล็อกอินด้วย Facebook")
    verifier = token_urlsafe(64)
    challenge = sha256(verifier.encode()).digest()
    import base64
    code_challenge = base64.urlsafe_b64encode(challenge).decode().rstrip("=")
    attempt = MetaOAuthAttempt(
        id=token_urlsafe(32),
        initiated_by_user_id=user.id,
        purpose="account_pages",
        code_verifier=verifier,
        expires_at=datetime.utcnow() + _ATTEMPT_TTL,
    )
    db.add(attempt)
    db.commit()
    params = {"client_id": settings.meta_app_id, "redirect_uri": settings.meta_oauth_redirect_uri, "state": attempt.id, "response_type": "code", "scope": ",".join(_FACEBOOK_SCOPES), "code_challenge": code_challenge, "code_challenge_method": "S256"}
    return FacebookStartOut(authorization_url=f"https://www.facebook.com/v22.0/dialog/oauth?{urlencode(params)}")


@router.get("/facebook/pending/{attempt_id}", response_model=FacebookPendingOut)
def facebook_pending(attempt_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attempt = _pending_for_user(db, attempt_id, user)
    pages = []
    for page in attempt.available_pages:
        channel = db.query(Channel).filter_by(type=ChannelType.facebook_page, external_id=str(page.get("id"))).first()
        pages.append(FacebookPageOut(id=str(page["id"]), name=str(page.get("name") or "Facebook Page"), registered=channel is not None, channel_id=channel.id if channel else None, shop_id=channel.shop_id if channel else None))
    return FacebookPendingOut(id=attempt.id, pages=pages)


@router.get("/facebook/pages/pending/{attempt_id}", response_model=FacebookPendingOut)
def facebook_account_pages_pending(attempt_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attempt = _pending_for_user(db, attempt_id, user, "account_pages")
    return facebook_pending_pages(db, attempt)


@router.get("/facebook/pages", response_model=list[FacebookPageOut])
def list_facebook_account_pages(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """List the registered Pages this Facebook-login user may actively use.

    Page access is determined by ChannelMembership, rather than by the current
    shop selection, so a user who manages multiple Pages can switch between
    them from the account Pages screen.
    """
    if user.facebook_identity is None:
        raise HTTPException(status_code=403, detail="หน้านี้ใช้ได้เฉพาะบัญชีที่ล็อกอินด้วย Facebook")
    channels = (
        db.query(Channel)
        .join(ChannelMembership, ChannelMembership.channel_id == Channel.id)
        .filter(
            ChannelMembership.user_id == user.id,
            ChannelMembership.is_active.is_(True),
            Channel.type == ChannelType.facebook_page,
            Channel.shop_id.is_not(None),
        )
        .order_by(Channel.name, Channel.id)
        .all()
    )
    return [
        FacebookPageOut(
            id=channel.external_id,
            name=channel.name or "Facebook Page",
            registered=True,
            channel_id=channel.id,
            shop_id=channel.shop_id,
        )
        for channel in channels
    ]


def facebook_pending_pages(db: Session, attempt: MetaOAuthAttempt) -> FacebookPendingOut:
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


@router.post("/facebook/pages/pending/{attempt_id}/register", response_model=FacebookPageOut)
def facebook_account_register_page(attempt_id: str, payload: FacebookPageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attempt = _pending_for_user(db, attempt_id, user, "account_pages")
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
    db.add(shop)
    db.flush()
    db.add(ShopMembership(shop_id=shop.id, user_id=user.id, role=ShopMembershipRole.owner))
    channel = Channel(shop_id=shop.id, type=ChannelType.facebook_page, external_id=payload.page_id, name=str(page.get("name") or "")[:255], access_token=encrypted_token, connected_facebook_user_id=attempt.facebook_user_id)
    db.add(channel)
    db.flush()
    db.add(ChannelMembership(channel_id=channel.id, user_id=user.id, role=ChannelMembershipRole.page_owner, granted_by_user_id=user.id))
    db.add(ChannelAuditLog(channel_id=channel.id, actor_user_id=user.id, action="facebook_page_registered", detail={"page_id": payload.page_id}))
    attempt.completed_at = datetime.utcnow()
    attempt.available_pages = []
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


@router.post("/login", response_model=UserOut | NativeSessionOut)
def login(payload: LoginIn, response: Response, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    if _is_native_client(request):
        return _native_session_out(db, user)
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


@router.post("/dev-bypass", response_model=UserOut)
def dev_bypass_login(response: Response, request: Request, db: Session = Depends(get_db)):
    """Create a normal session for local UI development without credentials."""
    if not settings.dev_login_bypass_enabled:
        raise HTTPException(status_code=404, detail="ไม่พบหน้านี้")
    # The bypass is intentionally unavailable to native builds, which need a
    # real account token, and uses the existing owner account instead of a
    # separate hidden identity.
    if _is_native_client(request):
        raise HTTPException(status_code=404, detail="ไม่พบหน้านี้")
    user = db.query(User).filter(User.role == UserRole.owner).order_by(User.id).first()
    if user is None:
        raise HTTPException(status_code=503, detail="ยังไม่มีผู้ดูแลระบบสำหรับโหมดพัฒนา")
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


@router.post("/unlock", response_model=UserOut | NativeSessionOut)
def unlock(payload: UnlockIn, response: Response, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or user.pin_hash is None or not verify_pin(payload.pin, user.pin_hash):
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือ PIN ไม่ถูกต้อง")
    if _is_native_client(request):
        return _native_session_out(db, user)
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
    if not token:
        authorization = request.headers.get("Authorization", "")
        scheme, _, bearer_token = authorization.partition(" ")
        if scheme.lower() == "bearer" and bearer_token:
            token = bearer_token
    if token:
        delete_session(db, token)
        db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _serialize(user)
