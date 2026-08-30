import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    JSON,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ChannelType(str, enum.Enum):
    facebook_page = "facebook_page"
    instagram = "instagram"
    line = "line"


class DraftOrderStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"


class ExpenseCategory(str, enum.Enum):
    cost_of_goods = "cost_of_goods"
    shipping = "shipping"
    rent = "rent"
    utilities = "utilities"
    marketing = "marketing"
    other = "other"


class ShopType(str, enum.Enum):
    individual = "individual"
    juristic = "juristic"


class StockMovementReason(str, enum.Enum):
    pos_sale = "pos_sale"
    pos_void = "pos_void"
    channel_order_confirm = "channel_order_confirm"
    adjustment = "adjustment"
    restock = "restock"
    stocktake = "stocktake"


class InventoryMode(str, enum.Enum):
    simple = "simple"
    recipe = "recipe"


class OrderParserMode(str, enum.Enum):
    algorithm = "algorithm"
    ai = "ai"


class StocktakeStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class SaleStatus(str, enum.Enum):
    held = "held"
    completed = "completed"
    voided = "voided"


class PaymentMethod(str, enum.Enum):
    cash = "cash"
    transfer = "transfer"


class PromotionType(str, enum.Enum):
    time_discount = "time_discount"
    bundle = "bundle"


class DiscountType(str, enum.Enum):
    percent = "percent"
    amount = "amount"


class UserRole(str, enum.Enum):
    owner = "owner"
    manager = "manager"
    cashier = "cashier"


class ShopMembershipRole(str, enum.Enum):
    owner = "owner"
    manager = "manager"
    staff = "staff"


class ChannelMembershipRole(str, enum.Enum):
    page_owner = "page_owner"
    page_manager = "page_manager"
    page_staff = "page_staff"
    viewer = "viewer"


class SaleAuditAction(str, enum.Enum):
    void = "void"
    refund = "refund"


class PurchaseOrderStatus(str, enum.Enum):
    draft = "draft"
    ordered = "ordered"
    received = "received"
    cancelled = "cancelled"


class BridgeCommandStatus(str, enum.Enum):
    pending = "pending"
    delivered = "delivered"
    succeeded = "succeeded"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.cashier)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    facebook_identity: Mapped["FacebookIdentity | None"] = relationship(back_populates="user", uselist=False)


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    memberships: Mapped[list["ShopMembership"]] = relationship(back_populates="shop", cascade="all, delete-orphan")


class ShopMembership(Base):
    __tablename__ = "shop_memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role: Mapped[ShopMembershipRole] = mapped_column(Enum(ShopMembershipRole))
    invited_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("shop_id", "user_id", name="uq_shop_membership"),)

    shop: Mapped["Shop"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(foreign_keys="ShopMembership.user_id")
    invited_by: Mapped["User | None"] = relationship(foreign_keys="ShopMembership.invited_by_user_id")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(255), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship()


class MetaOAuthAttempt(Base):
    """Short-lived, single-use state for selecting a Facebook Page after OAuth."""

    __tablename__ = "meta_oauth_attempts"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    initiated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    purpose: Mapped[str] = mapped_column(String(40), default="connection")
    code_verifier: Mapped[str] = mapped_column(String(128), default="")
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True)
    # Meta app-scoped ID only.  This lets the Data Deletion Callback find the
    # Pages that a person connected without storing their Facebook profile.
    facebook_user_id: Mapped[str] = mapped_column(String(255), default="")
    available_pages: Mapped[list] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    callback_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    initiated_by: Mapped["User | None"] = relationship()


class FacebookIdentity(Base):
    """The stable, app-scoped Facebook identity of an SStore user."""

    __tablename__ = "facebook_identities"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    facebook_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    facebook_name: Mapped[str] = mapped_column(String(255), default="")
    profile_picture_url: Mapped[str] = mapped_column(String(2000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="facebook_identity")


class ReceiptCounter(Base):
    __tablename__ = "receipt_counters"

    id: Mapped[int] = mapped_column(primary_key=True)
    next_number: Mapped[int] = mapped_column(default=1)


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[ChannelType] = mapped_column(Enum(ChannelType))
    external_id: Mapped[str] = mapped_column(String(255))  # page_id or ig_id
    name: Mapped[str] = mapped_column(String(255), default="")
    access_token: Mapped[str] = mapped_column(String(1024), default="")
    connected_facebook_user_id: Mapped[str] = mapped_column(String(255), default="")
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("type", "external_id", name="uq_channel_type_external_id"),)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="channel")
    shop: Mapped["Shop | None"] = relationship()
    memberships: Mapped[list["ChannelMembership"]] = relationship(back_populates="channel", cascade="all, delete-orphan")


class DataDeletionRequest(Base):
    """A minimal status record for an owner request or Meta deauthorization.

    It deliberately retains no message, customer, access-token, or Facebook
    profile data.  The confirmation code is what Meta and the requester use to
    check that a page-scoped deletion has been completed.
    """

    __tablename__ = "data_deletion_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    confirmation_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    page_external_id: Mapped[str] = mapped_column(String(255), default="")
    request_source: Mapped[str] = mapped_column(String(40), default="owner_portal")
    status: Mapped[str] = mapped_column(String(40), default="pending_verification")
    requester_email: Mapped[str] = mapped_column(String(255), default="")
    requester_name: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChannelMembership(Base):
    __tablename__ = "channel_memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role: Mapped[ChannelMembershipRole] = mapped_column(Enum(ChannelMembershipRole))
    granted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("channel_id", "user_id", name="uq_channel_membership"),)

    channel: Mapped["Channel"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(foreign_keys="ChannelMembership.user_id")
    granted_by: Mapped["User | None"] = relationship(foreign_keys="ChannelMembership.granted_by_user_id")


class ChannelAuditLog(Base):
    __tablename__ = "channel_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    channel: Mapped["Channel"] = relationship()
    actor: Mapped["User | None"] = relationship(foreign_keys="ChannelAuditLog.actor_user_id")
    target_user: Mapped["User | None"] = relationship(foreign_keys="ChannelAuditLog.target_user_id")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    external_user_id: Mapped[str] = mapped_column(String(255))  # PSID or IGSID
    display_name: Mapped[str] = mapped_column(String(255), default="")
    profile_image_url: Mapped[str] = mapped_column(String(2000), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    address: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("channel_id", "external_user_id", name="uq_customer_channel_external_user"),
    )

    channel: Mapped["Channel"] = relationship()


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(30), default="open")
    is_hidden: Mapped[bool] = mapped_column(default=False)
    is_pinned: Mapped[bool] = mapped_column(default=False)
    unread_count: Mapped[int] = mapped_column(default=0)
    bill_count: Mapped[int] = mapped_column(default=0)
    delivery_note: Mapped[str] = mapped_column(String(1000), default="")

    __table_args__ = (
        UniqueConstraint("channel_id", "customer_id", name="uq_conversation_channel_customer"),
    )

    channel: Mapped["Channel"] = relationship(back_populates="conversations")
    customer: Mapped["Customer"] = relationship()
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.created_at")
    draft_orders: Mapped[list["DraftOrder"]] = relationship(back_populates="conversation")
    labels: Mapped[list["ConversationLabel"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ConversationLabel.created_at"
    )


class ConversationLabel(Base):
    """A short operational label; Inbox permits at most two per conversation."""

    __tablename__ = "conversation_labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    name: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("conversation_id", "name", name="uq_conversation_label_name"),)

    conversation: Mapped["Conversation"] = relationship(back_populates="labels")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    direction: Mapped[str] = mapped_column(String(10))  # "in" or "out"
    text: Mapped[str] = mapped_column(String(4000), default="")
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    sent_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    sent_by: Mapped["User | None"] = relationship(foreign_keys="Message.sent_by_user_id")


class ParserV2ConversationState(Base):
    """Minimal, non-sensitive Parser v2 memory bound to one live conversation.

    It intentionally stores product references and workflow state only; message
    text, addresses, payment details, and other personal data remain in their
    existing conversation systems and are not copied here.
    """

    __tablename__ = "parser_v2_conversation_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), unique=True)
    state: Mapped[str] = mapped_column(String(50), default="idle")
    last_items: Mapped[list] = mapped_column(JSON, default=list)
    delivery_context_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship()


class HistoryImportRun(Base):
    """An isolated, read-only Facebook-history import for offline analysis."""

    __tablename__ = "history_import_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(30), default="facebook")
    page_id: Mapped[str] = mapped_column(String(255), default="")
    lookback_days: Mapped[int] = mapped_column(default=60)
    status: Mapped[str] = mapped_column(String(30), default="running")
    conversation_count: Mapped[int] = mapped_column(default=0)
    message_count: Mapped[int] = mapped_column(default=0)
    skipped_non_text_count: Mapped[int] = mapped_column(default=0)
    error_detail: Mapped[str] = mapped_column(String(1000), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HistoryConversation(Base):
    """Local copy of a Facebook conversation, kept separate from live Inbox."""

    __tablename__ = "history_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), unique=True)
    page_id: Mapped[str] = mapped_column(String(255), default="")
    customer_external_id: Mapped[str] = mapped_column(String(255), default="")
    customer_display_name: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    messages: Mapped[list["HistoryMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class HistoryMessage(Base):
    """Text-only message staging data. Attachments are never stored here."""

    __tablename__ = "history_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    history_conversation_id: Mapped[int] = mapped_column(ForeignKey("history_conversations.id"))
    external_id: Mapped[str] = mapped_column(String(255), unique=True)
    direction: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(String(4000))
    sent_at: Mapped[datetime] = mapped_column(DateTime)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped["HistoryConversation"] = relationship(back_populates="messages")


class HistoryAnalysisPreparation(Base):
    """A locally stored, redacted snapshot prepared for human review before AI use."""

    __tablename__ = "history_analysis_preparations"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    conversation_count: Mapped[int] = mapped_column(default=0)
    message_count: Mapped[int] = mapped_column(default=0)
    batch_count: Mapped[int] = mapped_column(default=0)
    redaction_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    batches: Mapped[list["HistoryAnalysisBatch"]] = relationship(
        back_populates="preparation", cascade="all, delete-orphan", order_by="HistoryAnalysisBatch.batch_number"
    )


class HistoryAnalysisBatch(Base):
    """One reviewable redacted context chunk. It is never sent automatically."""

    __tablename__ = "history_analysis_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    preparation_id: Mapped[int] = mapped_column(ForeignKey("history_analysis_preparations.id"))
    batch_number: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(30), default="draft")
    conversation_count: Mapped[int] = mapped_column(default=0)
    message_count: Mapped[int] = mapped_column(default=0)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("preparation_id", "batch_number", name="uq_analysis_batch_preparation_number"),)

    preparation: Mapped["HistoryAnalysisPreparation"] = relationship(back_populates="batches")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, index=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(100), default="")
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    cost_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    stock_quantity: Mapped[int] = mapped_column(default=0)
    stock_mode: Mapped[str] = mapped_column(String(30), default="tracked")
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    low_stock_threshold: Mapped[int] = mapped_column(default=5)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    show_in_menu_answer: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    modifiers: Mapped[list["ProductModifier"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    aliases: Mapped[list["ProductAlias"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    recipe_items: Mapped[list["RecipeItem"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class ProductAlias(Base):
    """An owner-approved alternate spelling/name used only by Parser v2."""

    __tablename__ = "product_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    alias_text: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="approved")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("product_id", "alias_text", name="uq_product_alias_product_text"),)

    product: Mapped["Product"] = relationship(back_populates="aliases")


class AdminHandoffLog(Base):
    """Redacted Parser v2 cases that require a human decision for future rule work."""

    __tablename__ = "admin_handoff_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), default="parser_v2_test")
    redacted_text: Mapped[str] = mapped_column(String(4000))
    intent: Mapped[str] = mapped_column(String(100), default="unknown")
    reason: Mapped[str] = mapped_column(String(100))
    candidates: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    resolution: Mapped[str] = mapped_column(String(4000), default="")
    resolved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrderOption(Base):
    """A shop-wide order option, such as sauce, that can be unlimited or stock-tracked."""

    __tablename__ = "order_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    stock_mode: Mapped[str] = mapped_column(String(30), default="unlimited")
    stock_quantity: Mapped[int] = mapped_column(default=0)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductModifier(Base):
    __tablename__ = "product_modifiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    name: Mapped[str] = mapped_column(String(100))
    price_delta: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    product: Mapped["Product"] = relationship(back_populates="modifiers")


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str] = mapped_column(String(50), default="")
    stock_quantity: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    low_stock_threshold: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RecipeItem(Base):
    __tablename__ = "recipe_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    quantity_per_unit: Mapped[float] = mapped_column(Numeric(10, 4), default=0)

    product: Mapped["Product"] = relationship(back_populates="recipe_items")
    ingredient: Mapped["Ingredient"] = relationship()


class IngredientMovement(Base):
    __tablename__ = "ingredient_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    change: Mapped[float] = mapped_column(Numeric(10, 2))
    reason: Mapped[StockMovementReason] = mapped_column(Enum(StockMovementReason))
    note: Mapped[str] = mapped_column(String(500), default="")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    ingredient: Mapped["Ingredient"] = relationship()
    created_by: Mapped["User"] = relationship()


class StocktakeSession(Base):
    __tablename__ = "stocktake_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, index=True)
    status: Mapped[StocktakeStatus] = mapped_column(Enum(StocktakeStatus), default=StocktakeStatus.open)
    entity_type: Mapped[str] = mapped_column(String(20), default="product")
    opened_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="")

    opened_by: Mapped["User"] = relationship(foreign_keys="StocktakeSession.opened_by_user_id")
    closed_by: Mapped["User"] = relationship(foreign_keys="StocktakeSession.closed_by_user_id")
    lines: Mapped[list["StocktakeLine"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class StocktakeLine(Base):
    __tablename__ = "stocktake_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("stocktake_sessions.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    ingredient_id: Mapped[int | None] = mapped_column(ForeignKey("ingredients.id"), nullable=True)
    expected_quantity: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    counted_quantity: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    session: Mapped["StocktakeSession"] = relationship(back_populates="lines")
    product: Mapped["Product"] = relationship()
    ingredient: Mapped["Ingredient"] = relationship()


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(50), default="")
    address: Mapped[str] = mapped_column(String(500), default="")
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="supplier")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    status: Mapped[PurchaseOrderStatus] = mapped_column(Enum(PurchaseOrderStatus), default=PurchaseOrderStatus.draft)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    supplier: Mapped["Supplier"] = relationship(back_populates="purchase_orders")
    created_by: Mapped["User"] = relationship()
    items: Mapped[list["PurchaseOrderItem"]] = relationship(back_populates="purchase_order", cascade="all, delete-orphan")


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(255), default="")
    quantity: Mapped[int] = mapped_column(default=1)
    unit_cost: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()


class LoyaltyCustomer(Base):
    __tablename__ = "loyalty_customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, index=True)
    phone: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    points: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    change: Mapped[int] = mapped_column()
    reason: Mapped[StockMovementReason] = mapped_column(Enum(StockMovementReason))
    note: Mapped[str] = mapped_column(String(500), default="")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped["Product"] = relationship()
    created_by: Mapped["User"] = relationship()


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, index=True)
    opened_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    opening_cash: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    closing_cash_counted: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="")

    opened_by: Mapped["User"] = relationship(foreign_keys="Shift.opened_by_user_id")
    closed_by: Mapped["User"] = relationship(foreign_keys="Shift.closed_by_user_id")


class DraftOrder(Base):
    __tablename__ = "draft_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    status: Mapped[DraftOrderStatus] = mapped_column(Enum(DraftOrderStatus), default=DraftOrderStatus.pending)
    source: Mapped[str] = mapped_column(String(20), default="parsed")
    note: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="draft_orders")
    items: Mapped[list["DraftOrderItem"]] = relationship(back_populates="draft_order", cascade="all, delete-orphan")
    confirmed_by: Mapped["User | None"] = relationship(foreign_keys="DraftOrder.confirmed_by_user_id")


class DraftOrderItem(Base):
    __tablename__ = "draft_order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_order_id: Mapped[int] = mapped_column(ForeignKey("draft_orders.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    matched_text: Mapped[str] = mapped_column(String(255), default="")
    quantity: Mapped[int] = mapped_column(default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    special_request: Mapped[str] = mapped_column(String(500), default="")

    draft_order: Mapped["DraftOrder"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, index=True)
    receipt_no: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[SaleStatus] = mapped_column(Enum(SaleStatus), default=SaleStatus.held)
    payment_method: Mapped[PaymentMethod | None] = mapped_column(Enum(PaymentMethod), nullable=True)
    discount_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    paid_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    change_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("loyalty_customers.id"), nullable=True)
    points_earned: Mapped[int] = mapped_column(default=0)
    points_redeemed: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["SaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    payments: Mapped[list["SalePayment"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    audit_logs: Mapped[list["SaleAuditLog"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    created_by: Mapped["User"] = relationship()
    shift: Mapped["Shift"] = relationship()
    customer: Mapped["LoyaltyCustomer"] = relationship()


class SaleAuditLog(Base):
    __tablename__ = "sale_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    action: Mapped[SaleAuditAction] = mapped_column(Enum(SaleAuditAction))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    sale: Mapped["Sale"] = relationship(back_populates="audit_logs")
    user: Mapped["User"] = relationship()


class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(255), default="")
    sku: Mapped[str] = mapped_column(String(64), default="")
    quantity: Mapped[int] = mapped_column(default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    refunded_quantity: Mapped[int] = mapped_column(default=0)

    sale: Mapped["Sale"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()
    modifiers: Mapped[list["SaleItemModifier"]] = relationship(back_populates="sale_item", cascade="all, delete-orphan")


class SaleItemModifier(Base):
    __tablename__ = "sale_item_modifiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_item_id: Mapped[int] = mapped_column(ForeignKey("sale_items.id"))
    name: Mapped[str] = mapped_column(String(100))
    price_delta: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    sale_item: Mapped["SaleItem"] = relationship(back_populates="modifiers")


class SalePayment(Base):
    __tablename__ = "sale_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod))
    amount: Mapped[float] = mapped_column(Numeric(10, 2))

    sale: Mapped["Sale"] = relationship(back_populates="payments")


class Promotion(Base):
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[PromotionType] = mapped_column(Enum(PromotionType))
    is_active: Mapped[bool] = mapped_column(default=True)
    discount_type: Mapped[DiscountType | None] = mapped_column(Enum(DiscountType), nullable=True)
    discount_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    bundle_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    items: Mapped[list["PromotionItem"]] = relationship(back_populates="promotion", cascade="all, delete-orphan")
    created_by: Mapped["User"] = relationship()


class PromotionItem(Base):
    __tablename__ = "promotion_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    promotion_id: Mapped[int] = mapped_column(ForeignKey("promotions.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(default=1)

    promotion: Mapped["Promotion"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, index=True)
    category: Mapped[ExpenseCategory] = mapped_column(Enum(ExpenseCategory))
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    description: Mapped[str] = mapped_column(String(500), default="")
    expense_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ShopSettings(Base):
    __tablename__ = "shop_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, unique=True, index=True)
    shop_type: Mapped[ShopType] = mapped_column(Enum(ShopType), default=ShopType.individual)
    shop_name: Mapped[str] = mapped_column(String(255), default="")
    address: Mapped[str] = mapped_column(String(500), default="")
    tax_id: Mapped[str] = mapped_column(String(50), default="")
    promptpay_id: Mapped[str] = mapped_column(String(20), default="")
    loyalty_baht_per_point: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    low_stock_line_token: Mapped[str] = mapped_column(String(255), default="")
    low_stock_line_target_id: Mapped[str] = mapped_column(String(255), default="")
    receipt_printer_ip: Mapped[str] = mapped_column(String(255), default="")
    receipt_printer_port: Mapped[int] = mapped_column(default=9100)
    receipt_paper_width: Mapped[int] = mapped_column(default=80)
    receipt_logo_url: Mapped[str] = mapped_column(String(1000), default="")
    receipt_show_logo: Mapped[bool] = mapped_column(Boolean, default=True)
    receipt_footer_text: Mapped[str] = mapped_column(String(255), default="ขอบคุณที่ใช้บริการ")
    receipt_show_cashier: Mapped[bool] = mapped_column(Boolean, default=True)
    receipt_show_member: Mapped[bool] = mapped_column(Boolean, default=True)
    inventory_mode: Mapped[InventoryMode] = mapped_column(Enum(InventoryMode), default=InventoryMode.simple)
    order_parser_mode: Mapped[OrderParserMode] = mapped_column(
        Enum(OrderParserMode), default=OrderParserMode.algorithm
    )
    ai_api_key: Mapped[str] = mapped_column(String(255), default="")
    menu_answer_format: Mapped[str] = mapped_column(String(20), default="text")


class PrintBridge(Base):
    __tablename__ = "print_bridges"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    device_token: Mapped[str] = mapped_column(String(128), unique=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    wifi_ssid: Mapped[str] = mapped_column(String(255), default="")
    wifi_rssi: Mapped[int | None] = mapped_column(nullable=True)
    printer_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    printer_name: Mapped[str] = mapped_column(String(255), default="")
    printer_address: Mapped[str] = mapped_column(String(64), default="")
    printer_error: Mapped[str] = mapped_column(String(500), default="")
    firmware_version: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    commands: Mapped[list["PrintBridgeCommand"]] = relationship(back_populates="bridge", cascade="all, delete-orphan")


class PrintBridgeCommand(Base):
    __tablename__ = "print_bridge_commands"

    id: Mapped[int] = mapped_column(primary_key=True)
    bridge_id: Mapped[int] = mapped_column(ForeignKey("print_bridges.id"))
    command: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[BridgeCommandStatus] = mapped_column(Enum(BridgeCommandStatus), default=BridgeCommandStatus.pending)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    bridge: Mapped["PrintBridge"] = relationship(back_populates="commands")
