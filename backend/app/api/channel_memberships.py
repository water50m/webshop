"""Page-team administration, enforced independently of the legacy user role."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_channel_access
from app.models import Channel, ChannelAuditLog, ChannelMembership, ChannelMembershipRole, ShopMembership, User

router = APIRouter(prefix="/api/channels", tags=["channel-memberships"])


class MemberOut(BaseModel):
    user_id: int
    username: str
    display_name: str
    facebook_name: str = ""
    profile_picture_url: str = ""
    role: ChannelMembershipRole
    is_active: bool


class MemberIn(BaseModel):
    user_id: int
    role: ChannelMembershipRole


class UserLookupOut(BaseModel):
    id: int
    username: str
    display_name: str


class ChannelAuditOut(BaseModel):
    id: int
    action: str
    actor_name: str | None
    target_name: str | None
    detail: dict
    created_at: str


def _member_out(member: ChannelMembership) -> MemberOut:
    identity = member.user.facebook_identity
    return MemberOut(
        user_id=member.user_id,
        username=member.user.username,
        display_name=member.user.display_name,
        facebook_name=identity.facebook_name if identity else "",
        profile_picture_url=identity.profile_picture_url if identity else "",
        role=member.role,
        is_active=member.is_active,
    )


def _manager_can_change(actor: ChannelMembership, target: ChannelMembership | None, requested: ChannelMembershipRole) -> bool:
    if actor.role == ChannelMembershipRole.page_owner:
        return True
    return (
        actor.role == ChannelMembershipRole.page_manager
        and (target is None or target.role != ChannelMembershipRole.page_owner)
        and requested != ChannelMembershipRole.page_owner
    )


def _require_team_admin(channel_id: int, user: User, db: Session) -> ChannelMembership:
    return require_channel_access(channel_id, user, db, ChannelMembershipRole.page_manager)


@router.get("/{channel_id}/members", response_model=list[MemberOut])
def list_members(channel_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_channel_access(channel_id, user, db)
    return [_member_out(member) for member in db.query(ChannelMembership).filter_by(channel_id=channel_id).order_by(ChannelMembership.id).all()]


@router.get("/{channel_id}/audit", response_model=list[ChannelAuditOut])
def list_channel_audit(channel_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_channel_access(channel_id, user, db, ChannelMembershipRole.page_manager)
    rows = db.query(ChannelAuditLog).filter_by(channel_id=channel_id).order_by(ChannelAuditLog.created_at.desc()).limit(200).all()
    return [
        ChannelAuditOut(
            id=row.id,
            action=row.action,
            actor_name=(row.actor.display_name or row.actor.username) if row.actor else None,
            target_name=(row.target_user.display_name or row.target_user.username) if row.target_user else None,
            detail=row.detail,
            created_at=row.created_at.isoformat(),
        )
        for row in rows
    ]


@router.get("/{channel_id}/users", response_model=UserLookupOut)
def find_shop_user(channel_id: int, username: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_team_admin(channel_id, user, db)
    channel = db.get(Channel, channel_id)
    target = db.query(User).filter(User.username == username.strip()).first()
    if channel is None or target is None:
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้งานในร้านนี้")
    if channel.shop_id is not None and not db.query(ShopMembership).filter_by(shop_id=channel.shop_id, user_id=target.id, is_active=True).first():
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้งานในร้านนี้")
    return UserLookupOut(id=target.id, username=target.username, display_name=target.display_name)


@router.put("/{channel_id}/members", response_model=MemberOut)
def grant_or_update_member(channel_id: int, payload: MemberIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    actor = _require_team_admin(channel_id, user, db)
    if db.get(Channel, channel_id) is None:
        raise HTTPException(status_code=404, detail="ไม่พบเพจ")
    target_user = db.get(User, payload.user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้งาน")
    membership = db.query(ChannelMembership).filter_by(channel_id=channel_id, user_id=payload.user_id).first()
    if not _manager_can_change(actor, membership, payload.role):
        raise HTTPException(status_code=403, detail="page_manager จัดการ page_owner ไม่ได้")
    if membership is not None and membership.role == ChannelMembershipRole.page_owner and payload.role != ChannelMembershipRole.page_owner:
        owner_count = db.query(ChannelMembership).filter_by(channel_id=channel_id, role=ChannelMembershipRole.page_owner, is_active=True).count()
        if owner_count <= 1:
            raise HTTPException(status_code=409, detail="ไม่สามารถลดสิทธิ์ page_owner คนสุดท้ายได้")
    if membership is None:
        membership = ChannelMembership(channel_id=channel_id, user_id=payload.user_id, role=payload.role, granted_by_user_id=user.id)
        db.add(membership)
        action = "member_granted"
    else:
        membership.role = payload.role
        membership.is_active = True
        membership.granted_by_user_id = user.id
        action = "member_updated"
    db.add(ChannelAuditLog(channel_id=channel_id, actor_user_id=user.id, target_user_id=payload.user_id, action=action, detail={"role": payload.role.value}))
    db.commit()
    db.refresh(membership)
    return _member_out(membership)


@router.delete("/{channel_id}/members/{target_user_id}")
def revoke_member(channel_id: int, target_user_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    actor = _require_team_admin(channel_id, user, db)
    membership = db.query(ChannelMembership).filter_by(channel_id=channel_id, user_id=target_user_id, is_active=True).first()
    if membership is None:
        raise HTTPException(status_code=404, detail="ไม่พบสมาชิกเพจ")
    if not _manager_can_change(actor, membership, membership.role):
        raise HTTPException(status_code=403, detail="page_manager จัดการ page_owner ไม่ได้")
    if membership.role == ChannelMembershipRole.page_owner:
        owner_count = db.query(ChannelMembership).filter_by(channel_id=channel_id, role=ChannelMembershipRole.page_owner, is_active=True).count()
        if owner_count <= 1:
            raise HTTPException(status_code=409, detail="ไม่สามารถถอน page_owner คนสุดท้ายได้")
    membership.is_active = False
    db.add(ChannelAuditLog(channel_id=channel_id, actor_user_id=user.id, target_user_id=target_user_id, action="member_revoked", detail={}))
    db.commit()
    return {"ok": True}
