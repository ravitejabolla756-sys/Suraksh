from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_admin
from app.core.security import hash_password
from app.models.database import get_db
from app.models.entities import AuditLog, Role, User
from app.schemas.dto import StaffInviteCreate, UserOut


router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return db.query(User).filter(User.org_id == user.org_id).order_by(User.created_at.asc()).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def invite_user(
    payload: StaffInviteCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")
    try:
        role = Role(payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid role") from exc

    user = User(
        org_id=admin.org_id,
        email=payload.email.lower(),
        password_hash=hash_password(payload.temporary_password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        phone=payload.phone,
        whatsapp_phone=payload.whatsapp_phone or payload.phone,
        role=role,
    )
    db.add(user)
    db.flush()
    db.add(
        AuditLog(
            org_id=admin.org_id,
            user_id=admin.id,
            action="invite_user",
            resource_type="user",
            resource_id=user.id,
            new_values={"email": user.email, "role": user.role.value},
        )
    )
    db.commit()
    db.refresh(user)
    return user
