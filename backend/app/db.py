from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings
from app.db_config import resolve_database_url

database_url = resolve_database_url(settings.database_url)
# SQLite is used for the local development setup.  Give short, legitimate
# overlapping writes (for example the web app and the history importer) time
# to finish instead of failing immediately with "database is locked".
engine = create_engine(
    database_url,
    connect_args={"timeout": 30} if database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
