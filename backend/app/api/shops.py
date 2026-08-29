"""Shop selection and creation for the multi-tenant boundary."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_role
from app.models import Channel, ChannelType, Shop, ShopMembership, ShopMembershipRole, User, UserRole

router = APIRouter(prefix="/api/shops", tags=["shops"], dependencies=[Depends(get_current_user)])


class ShopOut(BaseModel):
    id: int
    name: str
    role: ShopMembershipRole
    facebook_page_name: str | None = None
    facebook_page_id: str | None = None


class ShopIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)


@router.get("", response_model=list[ShopOut])
def list_shops(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    memberships = (
        db.query(ShopMembership)
        .filter_by(user_id=user.id, is_active=True)
        .order_by(ShopMembership.shop_id)
        .all()
    )
    shop_ids = [membership.shop_id for membership in memberships]
    pages_by_shop = {}
    if shop_ids:
        for page in (
            db.query(Channel)
            .filter(Channel.type == ChannelType.facebook_page, Channel.shop_id.in_(shop_ids), Channel.access_token != "")
            .order_by(Channel.id)
            .all()
        ):
            pages_by_shop.setdefault(page.shop_id, page)
    return [
        ShopOut(
            id=membership.shop.id,
            name=membership.shop.name,
            role=membership.role,
            facebook_page_name=pages_by_shop[membership.shop_id].name or None if membership.shop_id in pages_by_shop else None,
            facebook_page_id=pages_by_shop[membership.shop_id].external_id if membership.shop_id in pages_by_shop else None,
        )
        for membership in memberships
    ]


@router.post("", response_model=ShopOut, dependencies=[Depends(require_role(UserRole.owner))])
def create_shop(payload: ShopIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    shop = Shop(name=payload.name.strip())
    db.add(shop)
    db.flush()
    membership = ShopMembership(shop_id=shop.id, user_id=user.id, role=ShopMembershipRole.owner)
    db.add(membership)
    db.commit()
    return ShopOut(id=shop.id, name=shop.name, role=membership.role)
