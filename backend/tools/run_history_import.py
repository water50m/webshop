"""Background runner for the read-only Facebook history import.

It prints only aggregate counts and safe errors; tokens are never printed.
"""

import sys
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

# Running this file directly places tools/ first on sys.path; add the backend
# root so the application package remains importable in the background worker.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Base, SessionLocal, engine
from app.services.meta_history import MetaHistoryError, run_history_import


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        run = run_history_import(db)
        print(f"status={run.status}")
        print(f"run_id={run.id}")
        print(f"page_id={run.page_id}")
        print(f"conversations={run.conversation_count}")
        print(f"text_messages={run.message_count}")
        print(f"skipped_non_text={run.skipped_non_text_count}")
        print(f"error={run.error_detail}")
    except MetaHistoryError as exc:
        print("status=failed_before_import")
        print(f"error={exc}")
    except SQLAlchemyError:
        # Do not print a traceback: keep this unattended worker concise and
        # avoid accidentally exposing request configuration in diagnostics.
        print("status=failed_before_import")
        print("error=ฐานข้อมูลในเครื่องกำลังถูกใช้งานอยู่ กรุณาลองใหม่อีกครั้ง")
    finally:
        db.close()


if __name__ == "__main__":
    main()
