from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import current_user, machine_ingest
from app.models.database import get_db
from app.models.entities import AuditLog, Camera, Event, EventType, Zone
from app.schemas.dto import DismissRequest, EventIngest, EventOut
from app.services.notifications import process_event_alerts


router = APIRouter(prefix="/events", tags=["events"])


def event_out(db: Session, event: Event) -> EventOut:
    camera = db.get(Camera, event.camera_id)
    zone = db.get(Zone, event.zone_id) if event.zone_id else None
    return EventOut(
        id=event.id,
        org_id=event.org_id,
        camera_id=event.camera_id,
        edge_server_id=event.edge_server_id,
        zone_id=event.zone_id,
        type=event.type.value,
        confidence=event.confidence,
        edge_detected_at=event.edge_detected_at,
        cloud_received_at=event.cloud_received_at,
        snapshot_url=event.snapshot_url,
        video_clip_url=event.video_clip_url,
        metadata=event.metadata_json or {},
        alert_sent=event.alert_sent,
        dismissed_by=event.dismissed_by,
        dismissed_at=event.dismissed_at,
        dismiss_reason=event.dismiss_reason,
        camera_name=camera.name if camera else None,
        zone_name=zone.name if zone else None,
    )


@router.get("", response_model=list[EventOut])
def list_events(
    db: Session = Depends(get_db),
    user=Depends(current_user),
    event_type: str | None = Query(default=None),
    camera_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    query = db.query(Event).filter(Event.org_id == user.org_id)
    if event_type:
        query = query.filter(Event.type == EventType(event_type))
    if camera_id:
        query = query.filter(Event.camera_id == camera_id)
    events = query.order_by(desc(Event.created_at)).limit(limit).all()
    return [event_out(db, event) for event in events]


@router.post("/ingest", response_model=EventOut)
def ingest_event(payload: EventIngest, db: Session = Depends(get_db), _machine_key: str = Depends(machine_ingest)):
    camera = db.get(Camera, payload.camera_id)
    if not camera or camera.org_id != payload.org_id:
        raise HTTPException(status_code=404, detail="Camera not found for organization")

    event = Event(
        org_id=payload.org_id,
        camera_id=payload.camera_id,
        edge_server_id=payload.edge_server_id,
        zone_id=payload.zone_id,
        type=EventType(payload.type),
        confidence=payload.confidence,
        edge_detected_at=payload.edge_detected_at or datetime.now(timezone.utc),
        snapshot_url=payload.snapshot_url,
        video_clip_url=payload.video_clip_url,
        metadata_json=payload.metadata,
    )
    db.add(event)
    db.flush()
    process_event_alerts(db, event)
    db.commit()
    db.refresh(event)
    return event_out(db, event)


@router.post("/{event_id}/dismiss", response_model=EventOut)
def dismiss_event(event_id: str, payload: DismissRequest, db: Session = Depends(get_db), user=Depends(current_user)):
    event = db.get(Event, event_id)
    if not event or event.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Event not found")
    event.dismissed_by = user.id
    event.dismissed_at = datetime.now(timezone.utc)
    event.dismiss_reason = payload.reason
    db.add(
        AuditLog(
            org_id=user.org_id,
            user_id=user.id,
            action="dismiss_event",
            resource_type="event",
            resource_id=event.id,
            new_values={"reason": payload.reason},
        )
    )
    db.commit()
    db.refresh(event)
    return event_out(db, event)
