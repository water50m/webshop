from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Channel, ChannelMembership, ChannelMembershipRole, Conversation, ShopMembership, ShopMembershipRole, User, UserRole
from app.services.auth import get_session_user

SESSION_COOKIE_NAME = "session_token"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        authorization = request.headers.get("Authorization", "")
        scheme, _, bearer_token = authorization.partition(" ")
        if scheme.lower() == "bearer" and bearer_token:
            token = bearer_token
    if not token:
        raise HTTPException(status_code=401, detail="ยังไม่ได้เข้าสู่ระบบ")
    user = get_session_user(db, token)
    if user is None:
        raise HTTPException(status_code=401, detail="เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่")
    return user


def require_role(*roles: UserRole):
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ทำรายการนี้")
        return user

    return _check


CHANNEL_ROLE_ORDER = {
    ChannelMembershipRole.viewer: 0,
    ChannelMembershipRole.page_staff: 1,
    ChannelMembershipRole.page_manager: 2,
    ChannelMembershipRole.page_owner: 3,
}


def get_current_shop_membership(
    shop_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShopMembership:
    membership = (
        db.query(ShopMembership)
        .filter_by(shop_id=shop_id, user_id=user.id, is_active=True)
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เข้าถึงร้านนี้")
    return membership


def get_active_shop_membership(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShopMembership:
    """Resolve the requested shop and always verify its active membership.

    Clients can select a shop through ``X-Shop-ID``.  Omitting it preserves
    legacy behaviour by choosing the first shop available to the user.
    """
    requested = request.headers.get("X-Shop-ID")
    query = db.query(ShopMembership).filter_by(user_id=user.id, is_active=True)
    if requested:
        try:
            shop_id = int(requested)
        except ValueError:
            raise HTTPException(status_code=422, detail="X-Shop-ID ไม่ถูกต้อง") from None
        membership = query.filter_by(shop_id=shop_id).first()
    else:
        membership = query.order_by(ShopMembership.shop_id).first()
    if membership is None:
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เข้าถึงร้านนี้")
    return membership


def require_channel_access(
    channel_id: int,
    user: User,
    db: Session,
    minimum_role: ChannelMembershipRole = ChannelMembershipRole.viewer,
) -> ChannelMembership:
    """Return an active membership or deny without revealing channel contents."""
    membership = (
        db.query(ChannelMembership)
        .filter_by(channel_id=channel_id, user_id=user.id, is_active=True)
        .first()
    )
    if membership is None or CHANNEL_ROLE_ORDER[membership.role] < CHANNEL_ROLE_ORDER[minimum_role]:
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เข้าถึงเพจนี้")
    return membership


def require_conversation_access(
    conversation_id: int,
    user: User,
    db: Session,
    minimum_role: ChannelMembershipRole = ChannelMembershipRole.viewer,
) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    require_channel_access(conversation.channel_id, user, db, minimum_role)
    return conversation


def accessible_channel_ids(user: User, db: Session) -> list[int]:
    return [
        row[0]
        for row in db.query(ChannelMembership.channel_id)
        .filter_by(user_id=user.id, is_active=True)
        .all()
    ]
