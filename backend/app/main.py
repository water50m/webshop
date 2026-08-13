import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.api import (
    audit,
    bridges,
    auth,
    conversations,
    customers,
    draft_orders,
    events,
    expenses,
    export,
    history_preparation,
    ingredients,
    order_history,
    parser_v2,
    pos,
    products,
    promotions,
    reports,
    shifts,
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
from app.webhooks import line, meta

app = FastAPI(title="shop-sys backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(line.router)
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(users.router)
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
    product_columns = {column["name"] for column in inspect(engine).get_columns("products")}
    settings_columns = {column["name"] for column in inspect(engine).get_columns("shop_settings")}
    with engine.begin() as connection:
        if "status" not in conversation_columns:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'open'"))
        if "is_hidden" not in conversation_columns:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT FALSE"))
        if "unread_count" not in conversation_columns:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN unread_count INTEGER NOT NULL DEFAULT 0"))
        if "bill_count" not in conversation_columns:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN bill_count INTEGER NOT NULL DEFAULT 0"))
        if "show_in_menu_answer" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN show_in_menu_answer BOOLEAN NOT NULL DEFAULT TRUE"))
        if "menu_answer_format" not in settings_columns:
            connection.execute(text("ALTER TABLE shop_settings ADD COLUMN menu_answer_format VARCHAR(20) NOT NULL DEFAULT 'text'"))
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
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}
