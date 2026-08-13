from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, UserRole
from app.services.auth import get_session_user

SESSION_COOKIE_NAME = "session_token"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="ยังไม่ได้เข้าสู่ระบบ")
    user = get_session_user(db, token)
    if user is None:
        raise HTTPException(status_code=401, detail="เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่")
    return user


def require_role(*roles: UserRole):
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ทำรายการนี้")
        return user

    return _check
