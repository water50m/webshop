import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "db_config.json"

DEFAULT_CONFIG = {"engine": "sqlite", "sqlite_path": "./dev.db", "postgres_url": ""}


def read_db_config() -> dict:
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)
    return {**DEFAULT_CONFIG, **data}


def write_db_config(engine: str, sqlite_path: str, postgres_url: str) -> None:
    CONFIG_PATH.write_text(
        json.dumps(
            {"engine": engine, "sqlite_path": sqlite_path, "postgres_url": postgres_url},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def build_url(engine: str, sqlite_path: str, postgres_url: str) -> str:
    if engine == "postgres":
        return postgres_url
    return f"sqlite:///{sqlite_path or './dev.db'}"


def has_env_override() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def resolve_database_url(fallback: str) -> str:
    """DATABASE_URL env var (tests/ops override) always wins; otherwise use the
    UI-managed db_config.json if present; otherwise fall back to the .env/default."""
    if has_env_override():
        return os.environ["DATABASE_URL"]
    if CONFIG_PATH.exists():
        config = read_db_config()
        if config["engine"] == "postgres" and config["postgres_url"]:
            return config["postgres_url"]
        if config["engine"] == "sqlite":
            return build_url("sqlite", config["sqlite_path"], "")
    return fallback
