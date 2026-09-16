from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_admin
from app.models.database import get_db
from app.models.entities import AlertRule, Event, EventType
from app.schemas.dto import AlertRuleCreate, AlertRuleOut
from app.services.notifications import format_alert


router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])


@router.get("", response_model=list[AlertRuleOut])
def list_rules(db: Session = Depends(get_db), user=Depends(current_user)):
    return db.query(AlertRule).filter(AlertRule.org_id == user.org_id).order_by(AlertRule.created_at.desc()).all()


@router.post("", response_model=AlertRuleOut)
def create_rule(payload: AlertRuleCreate, db: Session = Depends(get_db), user=Depends(require_admin)):
    rule = AlertRule(org_id=user.org_id, event_type=EventType(payload.event_type), **payload.model_dump(exclude={"event_type"}))
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.post("/{rule_id}/test")
def test_rule(rule_id: str, db: Session = Depends(get_db), user=Depends(current_user)):
    rule = db.get(AlertRule, rule_id)
    if not rule or rule.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    event = (
        db.query(Event)
        .filter(Event.org_id == user.org_id, Event.type == rule.event_type)
        .order_by(Event.created_at.desc())
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="No matching demo event exists yet")
    return {"message": format_alert(event, "whatsapp"), "channels": rule.notify_channels}
