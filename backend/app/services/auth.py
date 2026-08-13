import secrets
from datetime import datetime, timedelta

import bcrypt
from sqlalchemy.orm import Session

from app.models import Session as SessionModel
from app.models import User

SESSION_TTL = timedelta(days=7)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def verify_pin(pin: str, pin_hash: str) -> bool:
    return bcrypt.checkpw(pin.encode(), pin_hash.encode())


def create_session(db: Session, user: User) -> SessionModel:
    session = SessionModel(
        token=secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=datetime.utcnow() + SESSION_TTL,
    )
    db.add(session)
    db.flush()
    return session


def get_session_user(db: Session, token: str) -> User | None:
    session = db.query(SessionModel).filter(SessionModel.token == token).first()
    if session is None:
        return None
    if session.expires_at < datetime.utcnow():
        return None
    return session.user


def delete_session(db: Session, token: str) -> None:
    db.query(SessionModel).filter(SessionModel.token == token).delete()
