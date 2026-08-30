import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.api import (
    audit,
    bridges,
    channel_memberships,
    auth,
    conversations,
    customers,
    draft_orders,
    events,
    expenses,
    export,
    history_preparation,
    ingredients,
    meta_connections,
    order_history,
    parser_v2,
    pos,
    products,
    promotions,
    reports,
    shifts,
    shops,
    stocktake,
    suppliers,
    system,
    users,
)
from app.api import settings as settings_api
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import User, UserRole
from app.services.auth import hash_password
from app.services.multi_page_access import bootstrap_legacy_access
from app.webhooks import line, meta

app = FastAPI(title="SStore backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(line.router)
app.include_router(auth.router)
app.include_router(meta_connections.router)
app.include_router(events.router)
app.include_router(users.router)
app.include_router(channel_memberships.router)
app.include_router(shops.router)
app.include_router(conversations.router)
app.include_router(draft_orders.router)
app.include_router(order_history.router)
app.include_router(expenses.router)
app.include_router(settings_api.router)
app.include_router(reports.router)
app.include_router(products.router)
app.include_router(pos.router)
app.include_router(promotions.router)
app.include_router(shifts.router)
app.include_router(audit.router)
app.include_router(bridges.router)
app.include_router(bridges.device_router)
app.include_router(customers.router)
app.include_router(suppliers.router)
app.include_router(suppliers.po_router)
app.include_router(export.router)
app.include_router(history_preparation.router)
app.include_router(parser_v2.router)
app.include_router(ingredients.router)
app.include_router(stocktake.router)
app.include_router(system.router)

UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    # Keep existing installations compatible until a full migration system is added.
    conversation_columns = {column["name"] for column in inspect(engine).get_columns("conversations")}
    customer_columns = {column["name"] for column in inspect(engine).get_columns("customers")}
    draft_order_columns = {column["name"] for column in inspect(engine).get_columns("draft_orders")}
    message_columns = {column["name"] for column in inspect(engine).get_columns("messages")}
    channel_columns = {column["name"] for column in inspect(engine).get_columns("channels")}
    product_columns = {column["name"] for column in inspect(engine).get_columns("products")}
    settings_columns = {column["name"] for column in inspect(engine).get_columns("shop_settings")}
    with engine.begin() as connection:
        if "status" not in conversation_columns:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'open'"))
        if "is_hidden" not in conversation_columns:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT FALSE"))
        if "is_pinned" not in conversation_columns:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN is_pinned BOOLEAN NOT NULL DEFAULT FALSE"))
        if "unread_count" not in conversation_columns:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN unread_count INTEGER NOT NULL DEFAULT 0"))
        if "bill_count" not in conversation_columns:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN bill_count INTEGER NOT NULL DEFAULT 0"))
        if "profile_image_url" not in customer_columns:
            connection.execute(text("ALTER TABLE customers ADD COLUMN profile_image_url VARCHAR(2000) NOT NULL DEFAULT ''"))
        if "source" not in draft_order_columns:
            connection.execute(text("ALTER TABLE draft_orders ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'parsed'"))
        if "confirmed_by_user_id" not in draft_order_columns:
            connection.execute(text("ALTER TABLE draft_orders ADD COLUMN confirmed_by_user_id INTEGER"))
        if "sent_by_user_id" not in message_columns:
            connection.execute(text("ALTER TABLE messages ADD COLUMN sent_by_user_id INTEGER"))
        if "connected_facebook_user_id" not in channel_columns:
            connection.execute(text("ALTER TABLE channels ADD COLUMN connected_facebook_user_id VARCHAR(255) NOT NULL DEFAULT ''"))
        if "show_in_menu_answer" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN show_in_menu_answer BOOLEAN NOT NULL DEFAULT TRUE"))
        if "menu_answer_format" not in settings_columns:
            connection.execute(text("ALTER TABLE shop_settings ADD COLUMN menu_answer_format VARCHAR(20) NOT NULL DEFAULT 'text'"))
        if "receipt_paper_width" not in settings_columns:
            connection.execute(text("ALTER TABLE shop_settings ADD COLUMN receipt_paper_width INTEGER NOT NULL DEFAULT 80"))
        if "receipt_logo_url" not in settings_columns:
            connection.execute(text("ALTER TABLE shop_settings ADD COLUMN receipt_logo_url VARCHAR(1000) NOT NULL DEFAULT ''"))
        if "receipt_show_logo" not in settings_columns:
            connection.execute(text("ALTER TABLE shop_settings ADD COLUMN receipt_show_logo BOOLEAN NOT NULL DEFAULT TRUE"))
        if "receipt_footer_text" not in settings_columns:
            connection.execute(text("ALTER TABLE shop_settings ADD COLUMN receipt_footer_text VARCHAR(255) NOT NULL DEFAULT 'ขอบคุณที่ใช้บริการ'"))
        if "receipt_show_cashier" not in settings_columns:
            connection.execute(text("ALTER TABLE shop_settings ADD COLUMN receipt_show_cashier BOOLEAN NOT NULL DEFAULT TRUE"))
        if "receipt_show_member" not in settings_columns:
            connection.execute(text("ALTER TABLE shop_settings ADD COLUMN receipt_show_member BOOLEAN NOT NULL DEFAULT TRUE"))
        for table_name in (
            "channels", "products", "ingredients", "suppliers", "purchase_orders",
            "loyalty_customers", "shifts", "sales", "promotions", "expenses",
            "shop_settings", "print_bridges", "order_options", "stocktake_sessions",
        ):
            columns = {column["name"] for column in inspect(engine).get_columns(table_name)}
            if "shop_id" not in columns:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN shop_id INTEGER"))
        attempt_columns = {column["name"] for column in inspect(engine).get_columns("meta_oauth_attempts")}
        if "shop_id" not in attempt_columns:
            connection.execute(text("ALTER TABLE meta_oauth_attempts ADD COLUMN shop_id INTEGER"))
        if "facebook_user_id" not in attempt_columns:
            connection.execute(text("ALTER TABLE meta_oauth_attempts ADD COLUMN facebook_user_id VARCHAR(255) NOT NULL DEFAULT ''"))
        identity_columns = {column["name"] for column in inspect(engine).get_columns("facebook_identities")}
        if "facebook_name" not in identity_columns:
            connection.execute(text("ALTER TABLE facebook_identities ADD COLUMN facebook_name VARCHAR(255) NOT NULL DEFAULT ''"))
        if "profile_picture_url" not in identity_columns:
            connection.execute(text("ALTER TABLE facebook_identities ADD COLUMN profile_picture_url VARCHAR(2000) NOT NULL DEFAULT ''"))
        if "purpose" not in attempt_columns:
            connection.execute(text("ALTER TABLE meta_oauth_attempts ADD COLUMN purpose VARCHAR(40) NOT NULL DEFAULT 'connection'"))
        if "code_verifier" not in attempt_columns:
            connection.execute(text("ALTER TABLE meta_oauth_attempts ADD COLUMN code_verifier VARCHAR(128) NOT NULL DEFAULT ''"))
        if "callback_completed_at" not in attempt_columns:
            # TIMESTAMP is accepted by both SQLite and PostgreSQL; DATETIME is
            # SQLite-specific and prevents PostgreSQL deployments from starting.
            connection.execute(text("ALTER TABLE meta_oauth_attempts ADD COLUMN callback_completed_at TIMESTAMP"))
        # Facebook-first attempts begin before an SStore user exists. PostgreSQL
        # installations created by an earlier release need this nullable change;
        # fresh databases receive it from the SQLAlchemy model.
        initiated_column = next((column for column in inspect(engine).get_columns("meta_oauth_attempts") if column["name"] == "initiated_by_user_id"), None)
        if initiated_column and not initiated_column["nullable"] and engine.dialect.name == "postgresql":
            connection.execute(text("ALTER TABLE meta_oauth_attempts ALTER COLUMN initiated_by_user_id DROP NOT NULL"))
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(
                User(
                    username="admin",
                    password_hash=hash_password("admin123"),
                    display_name="ผู้ดูแลระบบ",
                    role=UserRole.owner,
                )
            )
            db.commit()
            logging.warning("สร้างผู้ใช้เริ่มต้น admin/admin123 แล้ว กรุณาเปลี่ยนรหัสผ่านทันที")
        bootstrap_legacy_access(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}
