from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.models.database import get_db
from app.models.entities import Camera, Event, NotificationLog
from app.schemas.dto import NotificationLogOut


router = APIRouter(prefix="/notifications", tags=["notifications"])


def notification_out(db: Session, log: NotificationLog) -> NotificationLogOut:
    event = db.get(Event, log.event_id)
    camera = db.get(Camera, event.camera_id) if event else None
    return NotificationLogOut(
        id=log.id,
        org_id=log.org_id,
        event_id=log.event_id,
        alert_rule_id=log.alert_rule_id,
        user_id=log.user_id,
        channel=log.channel,
        recipient=log.recipient,
        status=log.status,
        provider=log.provider,
        message=log.message,
        created_at=log.created_at,
        event_type=event.type.value if event else None,
        camera_name=camera.name if camera else None,
    )


@router.get("", response_model=list[NotificationLogOut])
def list_notifications(
    db: Session = Depends(get_db),
    user=Depends(current_user),
    limit: int = Query(default=50, le=200),
):
    logs = (
        db.query(NotificationLog)
        .filter(NotificationLog.org_id == user.org_id)
        .order_by(desc(NotificationLog.created_at))
        .limit(limit)
        .all()
    )
    return [notification_out(db, log) for log in logs]
