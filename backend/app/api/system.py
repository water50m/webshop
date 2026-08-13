from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text

from app.db_config import build_url, has_env_override, read_db_config, write_db_config
from app.deps import get_current_user, require_role
from app.models import UserRole

router = APIRouter(
    prefix="/api/system",
    tags=["system"],
    dependencies=[Depends(get_current_user)],
)
owner_only = Depends(require_role(UserRole.owner))


class DbConfigOut(BaseModel):
    engine: str
    sqlite_path: str
    postgres_url: str
    env_override: bool


class DbConfigIn(BaseModel):
    engine: str
    sqlite_path: str = "./dev.db"
    postgres_url: str = ""


class DbTestOut(BaseModel):
    ok: bool
    detail: str


def _serialize() -> DbConfigOut:
    config = read_db_config()
    return DbConfigOut(
        engine=config["engine"],
        sqlite_path=config["sqlite_path"],
        postgres_url=config["postgres_url"],
        env_override=has_env_override(),
    )


def _validate(payload: DbConfigIn) -> None:
    if payload.engine not in ("sqlite", "postgres"):
        raise HTTPException(status_code=400, detail="engine ต้องเป็น sqlite หรือ postgres")
    if payload.engine == "postgres" and not payload.postgres_url.strip():
        raise HTTPException(status_code=400, detail="ต้องระบุ connection string ของ PostgreSQL")


@router.get("/db-config", response_model=DbConfigOut, dependencies=[owner_only])
def get_db_config():
    return _serialize()


@router.put("/db-config", response_model=DbConfigOut, dependencies=[owner_only])
def update_db_config(payload: DbConfigIn):
    _validate(payload)
    write_db_config(payload.engine, payload.sqlite_path or "./dev.db", payload.postgres_url)
    return _serialize()


@router.post("/db-config/test", response_model=DbTestOut, dependencies=[owner_only])
def test_db_config(payload: DbConfigIn):
    _validate(payload)
    url = build_url(payload.engine, payload.sqlite_path, payload.postgres_url)
    try:
        test_engine = create_engine(url)
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        test_engine.dispose()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"เชื่อมต่อไม่สำเร็จ: {exc}") from exc
    return DbTestOut(ok=True, detail="เชื่อมต่อสำเร็จ")
