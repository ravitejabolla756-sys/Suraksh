from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_access_token, verify_machine_key
from app.models.database import get_db
from app.models.entities import User


bearer = HTTPBearer()


def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    try:
        user_id = decode_access_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


def machine_ingest(x_edge_key: str | None = Header(default=None)) -> str:
    configured = get_settings().edge_ingest_key
    if not configured or not x_edge_key or not verify_machine_key(x_edge_key, configured):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Valid machine ingest key required")
    return x_edge_key
