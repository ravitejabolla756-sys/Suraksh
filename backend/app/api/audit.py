from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.models.database import get_db
from app.models.entities import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit_logs(db: Session = Depends(get_db), user=Depends(require_admin), limit: int = Query(default=100, le=500)):
    return db.query(AuditLog).filter(AuditLog.org_id == user.org_id).order_by(AuditLog.created_at.desc()).limit(limit).all()
