from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    InventoryMode,
    LoyaltyCustomer,
    PaymentMethod,
    Product,
    ProductModifier,
    ReceiptCounter,
    Sale,
    SaleAuditAction,
    SaleAuditLog,
    SaleItem,
    SaleItemModifier,
    SalePayment,
    SaleStatus,
    Shift,
    ShopSettings,
    StockMovementReason,
    User,
)
from app.services.promotions import compute_bundle_discount, get_discounted_price
from app.services.stock import adjust_ingredient_stock, adjust_stock


def _apply_inventory_change(
    db: Session,
    settings: ShopSettings | None,
    item: SaleItem,
    signed_quantity: float,
    reason: StockMovementReason,
    note: str,
    user: User,
) -> None:
    """signed_quantity: positive restocks, negative deducts (matches a Product's stock_quantity sign)."""
    product = item.product
    if product is None or signed_quantity == 0:
        return
    if settings is not None and settings.inventory_mode == InventoryMode.recipe and product.recipe_items:
        for recipe_item in product.recipe_items:
            ingredient_change = signed_quantity * float(recipe_item.quantity_per_unit)
            adjust_ingredient_stock(
                db,
                recipe_item.ingredient,
                ingredient_change,
                reason,
                note=note,
                allow_negative=True,
                created_by=user,
            )
    else:
        adjust_stock(db, product, int(round(signed_quantity)), reason, note=note, created_by=user)


def create_held_sale(db: Session, user: User) -> Sale:
    sale = Sale(status=SaleStatus.held, created_by_user_id=user.id)
    db.add(sale)
    db.flush()
    return sale


def _modifier_signature(modifiers) -> frozenset:
    return frozenset((m.name, float(m.price_delta)) for m in modifiers)


def add_item(
    db: Session,
    sale: Sale,
    product: Product,
    quantity: int,
    modifier_ids: list[int] | None = None,
) -> SaleItem:
    selected_modifiers = []
    if modifier_ids:
        selected_modifiers = (
            db.query(ProductModifier)
            .filter(ProductModifier.product_id == product.id, ProductModifier.id.in_(modifier_ids))
            .all()
        )
        if len(selected_modifiers) != len(set(modifier_ids)):
            raise ValueError("ตัวเลือกเสริมไม่ถูกต้องสำหรับสินค้านี้")

    new_sig = frozenset((m.name, float(m.price_delta)) for m in selected_modifiers)
    for item in sale.items:
        if item.product_id == product.id and _modifier_signature(item.modifiers) == new_sig:
            item.quantity += quantity
            return item

    discounted_price = get_discounted_price(db, product)
    item = SaleItem(
        sale_id=sale.id,
        product_id=product.id,
        product_name=product.name,
        sku=product.sku,
        quantity=quantity,
        unit_price=discounted_price if discounted_price is not None else product.price,
    )
    db.add(item)
    sale.items.append(item)
    db.flush()
    for modifier in selected_modifiers:
        db.add(SaleItemModifier(sale_item_id=item.id, name=modifier.name, price_delta=modifier.price_delta))
    db.flush()
    return item


def update_item(db: Session, item: SaleItem, quantity: int | None = None, discount_amount: float | None = None) -> SaleItem:
    if quantity is not None:
        item.quantity = quantity
    if discount_amount is not None:
        item.discount_amount = discount_amount
    return item


def remove_item(db: Session, item: SaleItem) -> None:
    db.delete(item)


def modifiers_unit_price(item: SaleItem) -> float:
    return float(item.unit_price) + sum(float(m.price_delta) for m in item.modifiers)


def line_total(item: SaleItem) -> float:
    net_qty = item.quantity - item.refunded_quantity
    return modifiers_unit_price(item) * net_qty - float(item.discount_amount)


def compute_totals(db: Session, sale: Sale) -> dict:
    subtotal = sum(modifiers_unit_price(item) * (item.quantity - item.refunded_quantity) for item in sale.items)
    item_discounts = sum(float(item.discount_amount) for item in sale.items)
    promotion_discount = compute_bundle_discount(db, sale.items)
    discount = item_discounts + float(sale.discount_amount) + promotion_discount
    total = max(0.0, subtotal - discount)
    return {
        "subtotal": subtotal,
        "discount": discount,
        "total": total,
        "promotion_discount": promotion_discount,
    }


def _next_receipt_no(db: Session) -> int:
    counter = db.query(ReceiptCounter).with_for_update().first()
    if counter is None:
        counter = ReceiptCounter(id=1, next_number=1)
        db.add(counter)
        db.flush()
    number = counter.next_number
    counter.next_number = number + 1
    return number


def checkout_sale(
    db: Session,
    sale: Sale,
    payments: list[tuple[PaymentMethod, float]],
    user: User,
    shift: Shift,
    customer: LoyaltyCustomer | None = None,
    redeem_points: int = 0,
) -> Sale:
    if sale.status != SaleStatus.held:
        raise ValueError("เฉพาะบิลที่ยังพักอยู่เท่านั้นที่ checkout ได้")
    if not sale.items:
        raise ValueError("บิลนี้ยังไม่มีรายการสินค้า")
    if not payments:
        raise ValueError("ต้องระบุวิธีชำระเงินอย่างน้อย 1 รายการ")

    totals = compute_totals(db, sale)

    redeem_discount = 0.0
    if redeem_points > 0:
        if customer is None:
            raise ValueError("ต้องระบุลูกค้าก่อนใช้แต้มสะสม")
        if redeem_points > customer.points:
            raise ValueError("แต้มสะสมไม่พอ")
        redeem_discount = min(float(redeem_points), totals["total"])
    total_due = max(0.0, totals["total"] - redeem_discount)

    total_tendered = sum(amount for _, amount in payments)
    if total_tendered < total_due:
        raise ValueError("จำนวนเงินที่รับมาไม่พอกับยอดรวม")

    cash_tendered = sum(amount for method, amount in payments if method == PaymentMethod.cash)
    non_cash_tendered = total_tendered - cash_tendered
    required_cash = max(0.0, total_due - non_cash_tendered)
    if cash_tendered < required_cash:
        raise ValueError("เงินสดที่รับมาไม่พอสำหรับส่วนที่เหลือ")
    change = cash_tendered - required_cash

    settings = db.get(ShopSettings, 1)
    for item in sale.items:
        _apply_inventory_change(
            db, settings, item, -item.quantity, StockMovementReason.pos_sale, f"POS sale #{sale.id}", user
        )

    for method, amount in payments:
        db.add(SalePayment(sale_id=sale.id, method=method, amount=amount))

    sale.status = SaleStatus.completed
    sale.payment_method = payments[0][0] if len(payments) == 1 else None
    sale.paid_amount = total_tendered
    sale.change_amount = change
    sale.completed_at = datetime.utcnow()
    sale.shift_id = shift.id
    sale.receipt_no = _next_receipt_no(db)

    if customer is not None:
        sale.customer_id = customer.id
        if redeem_points > 0:
            customer.points -= redeem_points
            sale.points_redeemed = redeem_points
        rate = float(settings.loyalty_baht_per_point) if settings else 0.0
        if rate > 0:
            earned = int(total_due // rate)
            customer.points += earned
            sale.points_earned = earned

    return sale


def void_sale(db: Session, sale: Sale, user: User, note: str = "") -> Sale:
    if sale.status == SaleStatus.voided:
        raise ValueError("บิลนี้ถูกยกเลิกไปแล้ว")
    if sale.status == SaleStatus.completed:
        settings = db.get(ShopSettings, 1)
        for item in sale.items:
            _apply_inventory_change(
                db,
                settings,
                item,
                item.quantity - item.refunded_quantity,
                StockMovementReason.pos_void,
                f"Void POS sale #{sale.id}",
                user,
            )
        db.add(SaleAuditLog(sale_id=sale.id, action=SaleAuditAction.void, user_id=user.id, note=note))
    sale.status = SaleStatus.voided
    return sale


def refund_items(db: Session, sale: Sale, refunds: list[tuple[int, int]], user: User, note: str = "") -> Sale:
    if sale.status != SaleStatus.completed:
        raise ValueError("คืนเงินได้เฉพาะบิลที่ชำระเงินสำเร็จแล้ว")
    if not refunds:
        raise ValueError("ต้องระบุรายการที่จะคืนอย่างน้อย 1 รายการ")

    settings = db.get(ShopSettings, 1)
    items_by_id = {item.id: item for item in sale.items}
    for item_id, quantity in refunds:
        item = items_by_id.get(item_id)
        if item is None:
            raise ValueError("ไม่พบรายการนี้ในบิล")
        remaining = item.quantity - item.refunded_quantity
        if quantity <= 0 or quantity > remaining:
            raise ValueError(f"จำนวนคืนของ {item.product_name} ไม่ถูกต้อง (คืนได้สูงสุด {remaining})")
        item.refunded_quantity += quantity
        _apply_inventory_change(
            db, settings, item, quantity, StockMovementReason.pos_void, note or f"Refund sale #{sale.id}", user
        )

    if all(item.refunded_quantity >= item.quantity for item in sale.items):
        sale.status = SaleStatus.voided
    db.add(SaleAuditLog(sale_id=sale.id, action=SaleAuditAction.refund, user_id=user.id, note=note))
    return sale
