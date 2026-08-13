from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    DiscountType,
    Product,
    Promotion,
    PromotionType,
    SaleItem,
)


def is_promotion_active(promotion: Promotion, now: datetime | None = None) -> bool:
    if not promotion.is_active:
        return False
    now = now or datetime.utcnow()
    if promotion.start_at is not None and now < promotion.start_at:
        return False
    if promotion.end_at is not None and now > promotion.end_at:
        return False
    return True


def get_discounted_price(db: Session, product: Product, now: datetime | None = None) -> float | None:
    promotions = (
        db.query(Promotion)
        .filter(Promotion.type == PromotionType.time_discount, Promotion.is_active == True)  # noqa: E712
        .all()
    )
    for promotion in promotions:
        if not is_promotion_active(promotion, now):
            continue
        item = next((i for i in promotion.items if i.product_id == product.id), None)
        if item is None:
            continue
        price = float(product.price)
        if promotion.discount_type == DiscountType.percent:
            return round(price * (1 - float(promotion.discount_value) / 100), 2)
        return max(0.0, price - float(promotion.discount_value))
    return None


def compute_bundle_discount(db: Session, sale_items: list[SaleItem], now: datetime | None = None) -> float:
    qty_in_cart: dict[int, int] = {}
    for item in sale_items:
        if item.product_id is not None:
            net_qty = item.quantity - item.refunded_quantity
            qty_in_cart[item.product_id] = qty_in_cart.get(item.product_id, 0) + net_qty

    bundles = (
        db.query(Promotion)
        .filter(Promotion.type == PromotionType.bundle, Promotion.is_active == True)  # noqa: E712
        .all()
    )

    total_discount = 0.0
    for bundle in bundles:
        if not is_promotion_active(bundle, now) or not bundle.items:
            continue
        possible_sets = min(
            (qty_in_cart.get(bundle_item.product_id, 0) // bundle_item.quantity for bundle_item in bundle.items),
            default=0,
        )
        if possible_sets <= 0:
            continue
        regular_total = sum(
            float(bundle_item.product.price) * bundle_item.quantity for bundle_item in bundle.items
        )
        total_discount += possible_sets * max(0.0, regular_total - float(bundle.bundle_price))
    return total_discount
