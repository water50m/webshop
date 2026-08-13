from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import User, UserRole
from app.services.auth import hash_password

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_role(UserRole.owner))])


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str


class UserIn(BaseModel):
    username: str
    password: str
    display_name: str = ""
    role: UserRole = UserRole.cashier


class UserUpdateIn(BaseModel):
    display_name: str = ""
    role: UserRole
    password: str | None = None


def _serialize(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, display_name=user.display_name, role=user.role.value)


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return [_serialize(u) for u in db.query(User).order_by(User.username).all()]


@router.post("", response_model=UserOut)
def create_user(payload: UserIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first() is not None:
        raise HTTPException(status_code=400, detail="ชื่อผู้ใช้นี้ถูกใช้ไปแล้ว")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _serialize(user)


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdateIn, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.display_name = payload.display_name
    user.role = payload.role
    if payload.password:
        user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return _serialize(user)


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"ok": True}
