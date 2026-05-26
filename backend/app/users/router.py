from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.shared.database import get_db
from app.shared.models import AuditLog, Role, User
from app.shared.schemas import UserCreate, UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return list(db.scalars(select(User).order_by(User.created_at.desc())))


@router.post("", response_model=UserOut)
def create_user(payload: UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if payload.role not in {Role.employee.value, Role.admin.value}:
        raise HTTPException(status_code=400, detail="Invalid role")
    existing = db.scalar(select(User).where(User.ldap_id == payload.ldap_id))
    if existing:
        raise HTTPException(status_code=409, detail="LDAP ID already exists")
    user = User(
        username=f"ldap:{payload.ldap_id}",
        ldap_id=payload.ldap_id,
        display_name=payload.display_name,
        password_hash=None,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(AuditLog(actor_user_id=admin.id, action="user.create", target_type="user", target_id=str(user.id), detail={}))
    db.commit()
    return user


@router.patch("/{user_id}/active", response_model=UserOut)
def set_user_active(user_id: int, is_active: bool, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = is_active
    db.add(AuditLog(actor_user_id=admin.id, action="user.active", target_type="user", target_id=str(user.id), detail={"is_active": is_active}))
    db.commit()
    db.refresh(user)
    return user
