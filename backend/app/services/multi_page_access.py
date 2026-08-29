"""Bootstrap helpers for the multi-shop, page-scoped access model.

This is deliberately idempotent so it can safely run during application
startup after the schema migration has added the ``channels.shop_id`` column.
"""

from sqlalchemy.orm import Session

from app.models import (
    Channel,
    ChannelMembership,
    ChannelMembershipRole,
    Expense,
    FacebookIdentity,
    Ingredient,
    LoyaltyCustomer,
    OrderOption,
    PrintBridge,
    Product,
    Promotion,
    PurchaseOrder,
    Sale,
    Shop,
    ShopSettings,
    ShopMembership,
    ShopMembershipRole,
    Shift,
    StocktakeSession,
    Supplier,
    User,
    UserRole,
)


def _shop_role(user: User) -> ShopMembershipRole:
    if user.role == UserRole.owner:
        return ShopMembershipRole.owner
    if user.role == UserRole.manager:
        return ShopMembershipRole.manager
    return ShopMembershipRole.staff


def _channel_role(user: User) -> ChannelMembershipRole:
    if user.role == UserRole.owner:
        return ChannelMembershipRole.page_owner
    if user.role == UserRole.manager:
        return ChannelMembershipRole.page_manager
    return ChannelMembershipRole.page_staff


def bootstrap_legacy_access(db: Session) -> None:
    """Place pre-Facebook single-shop data into a default shop without removing access.

    Facebook-first accounts must choose a Page before they receive a shop or a
    Page membership.  In particular, do not let this startup compatibility
    routine turn a newly authenticated Facebook account into a member of the
    legacy default shop while it is still on the Page-selection screen.
    """
    shop = db.query(Shop).order_by(Shop.id).first()
    if shop is None:
        shop = Shop(name="ร้านเริ่มต้น")
        db.add(shop)
        db.flush()

    # A FacebookIdentity is conclusive evidence that the account was created
    # by the Page-scoped onboarding flow, not by the legacy single-shop flow.
    # Keep those accounts out of this deliberately broad compatibility grant.
    users = (
        db.query(User)
        .outerjoin(FacebookIdentity, FacebookIdentity.user_id == User.id)
        .filter(FacebookIdentity.id.is_(None))
        .all()
    )
    for user in users:
        membership = db.query(ShopMembership).filter_by(shop_id=shop.id, user_id=user.id).first()
        if membership is None:
            db.add(ShopMembership(shop_id=shop.id, user_id=user.id, role=_shop_role(user)))

    shop_scoped_models = (
        Channel, Product, Ingredient, Supplier, PurchaseOrder, LoyaltyCustomer,
        Shift, Sale, Promotion, Expense, ShopSettings, PrintBridge, OrderOption,
        StocktakeSession,
    )
    for model in shop_scoped_models:
        db.query(model).filter(model.shop_id.is_(None)).update({model.shop_id: shop.id}, synchronize_session=False)

    channels = db.query(Channel).all()
    for channel in channels:
        for user in users:
            membership = db.query(ChannelMembership).filter_by(channel_id=channel.id, user_id=user.id).first()
            if membership is None:
                db.add(
                    ChannelMembership(
                        channel_id=channel.id,
                        user_id=user.id,
                        role=_channel_role(user),
                    )
                )
    db.commit()
