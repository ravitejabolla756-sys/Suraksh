from datetime import datetime, timedelta, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import AlertRule, Event, NotificationLog, User


def _event_metadata(event: Event) -> dict:
    return event.metadata_json or {}


def rule_matches(rule: AlertRule, event: Event) -> bool:
    if not rule.enabled:
        return False
    if rule.event_type != event.type:
        return False
    if event.confidence < rule.confidence_threshold:
        return False
    if rule.camera_id and rule.camera_id != event.camera_id:
        return False
    if rule.zone_id and rule.zone_id != event.zone_id:
        return False
    if rule.condition_type == "crowd_threshold":
        person_count = int(_event_metadata(event).get("person_count", 0))
        return person_count >= int(rule.condition_value or 0)
    return True


def is_suppressed(db: Session, rule: AlertRule, event: Event) -> bool:
    since = datetime.now(timezone.utc) - timedelta(seconds=rule.suppress_duration_sec)
    existing = (
        db.query(NotificationLog)
        .join(Event, Event.id == NotificationLog.event_id)
        .filter(
            NotificationLog.alert_rule_id == rule.id,
            Event.camera_id == event.camera_id,
            Event.type == event.type,
            NotificationLog.created_at >= since,
            NotificationLog.status.in_(["queued", "sent", "delivered"]),
        )
        .order_by(desc(NotificationLog.created_at))
        .first()
    )
    return existing is not None


def format_alert(event: Event, channel: str) -> str:
    settings = get_settings()
    title = event.type.value.replace("_", " ").upper()
    link = f"{settings.public_dashboard_url}/events/{event.id}"
    meta = event.metadata_json or {}
    extra = ""
    if "person_count" in meta:
        extra = f" People: {meta['person_count']}."
    return (
        f"SURAKSH: {title} detected. "
        f"Confidence: {round(event.confidence * 100)}%.{extra} "
        f"Open: {link}"
    )


def process_event_alerts(db: Session, event: Event) -> list[NotificationLog]:
    rules = db.query(AlertRule).filter(AlertRule.org_id == event.org_id, AlertRule.enabled == True).all()  # noqa: E712
    created: list[NotificationLog] = []
    for rule in rules:
        if not rule_matches(rule, event) or is_suppressed(db, rule, event):
            continue

        users = db.query(User).filter(User.id.in_(rule.notify_user_ids or [])).all()
        for user in users:
            for channel in rule.notify_channels:
                recipient = user.email if channel == "email" else (user.whatsapp_phone or user.phone or user.email)
                log = NotificationLog(
                    org_id=event.org_id,
                    event_id=event.id,
                    alert_rule_id=rule.id,
                    user_id=user.id,
                    channel=channel,
                    recipient=recipient or "",
                    status="sent",
                    provider="demo",
                    message=format_alert(event, channel),
                )
                db.add(log)
                created.append(log)
    if created:
        event.alert_sent = True
    return created
