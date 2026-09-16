from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import current_user, machine_ingest
from app.models.database import get_db
from app.models.entities import Alert, Camera, CameraAnalyticsSnapshot, CameraStatus, Department, DetectionEvent, Event
from app.schemas.dto import AnalyticsIngest, AnalyticsSnapshotOut, AnalyticsSummary

router = APIRouter(prefix="/analytics", tags=["analytics"])
VEHICLES = ("cars", "motorcycles", "buses", "trucks")


def _scope(db, user, camera_id=None, department=None, source_vms=None):
    query = db.query(CameraAnalyticsSnapshot).join(Department, Department.id == CameraAnalyticsSnapshot.department_id).filter(Department.org_id == user.org_id)
    if camera_id:
        query = query.filter(CameraAnalyticsSnapshot.camera_id == camera_id)
    if department:
        query = query.filter(CameraAnalyticsSnapshot.department_id == department)
    if source_vms:
        query = query.filter(CameraAnalyticsSnapshot.source_vms == source_vms)
    return query


def _out(item):
    return AnalyticsSnapshotOut.model_validate({**item.__dict__})


def _sum(rows):
    result = {"people": 0, "vehicles": 0, "cars": 0, "motorcycles": 0, "buses": 0, "trucks": 0}
    for row in rows:
        result["people"] += row.unique_people
        result["vehicles"] += row.unique_vehicles
        for field in VEHICLES:
            result[field] += getattr(row, f"unique_{field}")
    return result


@router.get("/summary", response_model=AnalyticsSummary)
def summary(db: Session = Depends(get_db), user=Depends(current_user)):
    cameras = db.query(Camera).filter(Camera.org_id == user.org_id).all()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    events = db.query(Event).filter(Event.org_id == user.org_id, Event.created_at >= today_start).all()
    detections = db.query(DetectionEvent).join(Department).filter(Department.org_id == user.org_id, DetectionEvent.detected_at >= today_start).all()
    active_alerts = len([event for event in events if event.dismissed_at is None and event.type.value != "person"])
    active_alerts += db.query(Alert).join(Department).filter(Department.org_id == user.org_id, Alert.status == "active").count()
    breakdown = {}
    for event in events:
        breakdown[event.type.value] = breakdown.get(event.type.value, 0) + 1
    for detection in detections:
        breakdown[detection.vehicle_class] = breakdown.get(detection.vehicle_class, 0) + 1
    latest = _scope(db, user).order_by(CameraAnalyticsSnapshot.bucket_start.desc()).limit(max(1, len(cameras))).all()
    totals = _sum(latest)
    current = {"people": 0, "vehicles": 0, "cars": 0, "motorcycles": 0, "buses": 0, "trucks": 0}
    for row in latest:
        current["people"] += row.people_visible_peak
        current["vehicles"] += row.vehicle_visible_peak
        for field in VEHICLES:
            current[field] += getattr(row, f"unique_{field}")
    return AnalyticsSummary(cameras_online=len([camera for camera in cameras if camera.status == CameraStatus.online]), cameras_total=len(cameras), events_today=len(events) + len(detections), active_alerts=active_alerts, event_breakdown=breakdown, recent_camera_health=[{"id": camera.id, "name": camera.name, "status": camera.status.value, "last_heartbeat": camera.last_heartbeat.isoformat()} for camera in cameras], people_visible=current["people"], vehicles_visible=current["vehicles"], cars=current["cars"], motorcycles=current["motorcycles"], buses=current["buses"], trucks=current["trucks"], unique_people=totals["people"], unique_vehicles=totals["vehicles"])


@router.post("/ingest", response_model=AnalyticsSnapshotOut)
def ingest(payload: AnalyticsIngest, db: Session = Depends(get_db), _key: str = Depends(machine_ingest)):
    camera = db.get(Camera, payload.camera_id)
    if not camera or camera.department_id != payload.department_id:
        raise HTTPException(404, "Camera not found for department")
    if not db.get(Department, payload.department_id):
        raise HTTPException(404, "Department not found")
    item = db.query(CameraAnalyticsSnapshot).filter(CameraAnalyticsSnapshot.camera_id == camera.id, CameraAnalyticsSnapshot.bucket_start == payload.bucket_start).first()
    values = payload.model_dump()
    if item is None:
        item = CameraAnalyticsSnapshot(**values)
        db.add(item)
    else:
        for key, value in values.items():
            setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return _out(item)


@router.get("/cameras/{camera_id}")
def camera_analytics(camera_id: str, department: str | None = None, source_vms: str | None = None, since: datetime | None = None, until: datetime | None = None, db: Session = Depends(get_db), user=Depends(current_user)):
    camera = db.get(Camera, camera_id)
    if not camera or camera.org_id != user.org_id:
        raise HTTPException(404, "Camera not found")
    query = _scope(db, user, camera_id, department, source_vms)
    if since:
        query = query.filter(CameraAnalyticsSnapshot.bucket_start >= since)
    if until:
        query = query.filter(CameraAnalyticsSnapshot.bucket_start <= until)
    rows = query.order_by(CameraAnalyticsSnapshot.bucket_start).all()
    latest = rows[-1] if rows else None
    return {"camera_id": camera_id, "camera_name": camera.name, "source_vms": latest.source_vms if latest else None, "traffic_state": traffic_state(latest.vehicle_visible_peak if latest else 0), "current": {"people": latest.people_visible_peak if latest else 0, "vehicles": latest.vehicle_visible_peak if latest else 0}, "period_totals": _sum(rows), "line_crossings": _crossings(rows), "timeseries": [_out(row) for row in rows]}


@router.get("/timeseries")
def timeseries(camera: str | None = None, department: str | None = None, vms: str | None = None, since: datetime | None = None, until: datetime | None = None, db: Session = Depends(get_db), user=Depends(current_user)):
    query = _scope(db, user, camera, department, vms)
    if since:
        query = query.filter(CameraAnalyticsSnapshot.bucket_start >= since)
    if until:
        query = query.filter(CameraAnalyticsSnapshot.bucket_start <= until)
    rows = query.order_by(CameraAnalyticsSnapshot.bucket_start).limit(2000).all()
    return {"buckets": [_out(row) for row in rows], "notice": "Synthetic recorded CCTV analytics; counts are approximate when tracker IDs are recreated."}


def _crossings(rows):
    fields = [f"{vehicle}_crossed_{direction}" for vehicle in VEHICLES for direction in ("a_to_b", "b_to_a")]
    return {field: sum(getattr(row, field) for row in rows) for field in fields}


def traffic_state(vehicles: int) -> str:
    """Demo thresholds: LOW 0-4, MEDIUM 5-11, HIGH 12+ visible vehicles."""
    return "HIGH" if vehicles >= 12 else "MEDIUM" if vehicles >= 5 else "LOW"
