from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import SESSION_COOKIE_NAME, get_current_user
from app.models import User
from app.services.auth import create_session, delete_session, hash_pin, verify_password, verify_pin

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class UnlockIn(BaseModel):
    username: str
    pin: str


class SetPinIn(BaseModel):
    pin: str


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    has_pin: bool


def _serialize(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role.value,
        has_pin=user.pin_hash is not None,
    )


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    session = create_session(db, user)
    db.commit()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
    )
    return _serialize(user)


@router.post("/unlock", response_model=UserOut)
def unlock(payload: UnlockIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or user.pin_hash is None or not verify_pin(payload.pin, user.pin_hash):
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือ PIN ไม่ถูกต้อง")
    session = create_session(db, user)
    db.commit()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
    )
    return _serialize(user)


@router.post("/set-pin")
def set_pin(payload: SetPinIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not payload.pin.isdigit() or len(payload.pin) < 4:
        raise HTTPException(status_code=400, detail="PIN ต้องเป็นตัวเลขอย่างน้อย 4 หลัก")
    user.pin_hash = hash_pin(payload.pin)
    db.commit()
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        delete_session(db, token)
        db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _serialize(user)
