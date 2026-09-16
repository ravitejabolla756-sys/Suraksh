from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.api.deps import current_user, machine_ingest, require_admin
from app.models.database import get_db
from app.models.entities import Alert, Camera, Department, DetectionEvent, Watchlist, WatchlistEntry
from app.schemas.dto import DetectionCreate, DetectionOut, WatchlistCreate, WatchlistEntryCreate, WatchlistEntryOut, WatchlistOut
from app.services.plates import normalize_plate
from app.services.audit import record
from app.services.alert_stream import alert_query, alert_out

router = APIRouter(tags=["detections"])


def _department(db: Session, department_id: str, org_id: str) -> Department:
    department = db.get(Department, department_id)
    if not department or department.org_id != org_id:
        raise HTTPException(status_code=404, detail="Department not found")
    return department


def _detection_out(db: Session, item: DetectionEvent) -> DetectionOut:
    camera = db.get(Camera, item.camera_id)
    department = db.get(Department, item.department_id)
    return DetectionOut.model_validate({**item.__dict__, "metadata": item.metadata_json or {}, "camera_name": camera.name if camera else None, "district": camera.district if camera else None, "department_name": department.name if department else None})


@router.get("/detections", response_model=list[DetectionOut])
def list_detections(db: Session = Depends(get_db), user=Depends(current_user), plate: str | None = Query(default=None), camera: str | None = Query(default=None), department: str | None = Query(default=None), vehicle_type: str | None = Query(default=None), since: datetime | None = Query(default=None), until: datetime | None = Query(default=None), limit: int = Query(default=100, le=500)):
    query = db.query(DetectionEvent).join(Department, Department.id == DetectionEvent.department_id).filter(Department.org_id == user.org_id)
    if plate:
        normalized = normalize_plate(plate)
        if not normalized:
            return []
        query = query.filter(DetectionEvent.plate_text == normalized)
    if camera:
        query = query.filter(DetectionEvent.camera_id == camera)
    if department:
        query = query.filter(DetectionEvent.department_id == department)
    if vehicle_type:
        query = query.filter(DetectionEvent.vehicle_class == vehicle_type)
    if since:
        query = query.filter(DetectionEvent.detected_at >= since)
    if until:
        query = query.filter(DetectionEvent.detected_at <= until)
    return [_detection_out(db, item) for item in query.order_by(DetectionEvent.detected_at.asc(), DetectionEvent.id.asc()).limit(limit).all()]


@router.get("/detections/{detection_id}", response_model=DetectionOut)
def get_detection(detection_id: str, db: Session = Depends(get_db), user=Depends(current_user)):
    item = db.query(DetectionEvent).join(Department).filter(DetectionEvent.id == detection_id, Department.org_id == user.org_id).first()
    if not item:
        raise HTTPException(404, "Detection not found")
    return _detection_out(db, item)


@router.get("/investigations/path")
def observed_path(plate: str, db: Session = Depends(get_db), user=Depends(current_user)):
    normalized = normalize_plate(plate)
    if not normalized:
        raise HTTPException(422, "Invalid registration")
    items = db.query(DetectionEvent).join(Department).filter(Department.org_id == user.org_id, DetectionEvent.plate_text == normalized).order_by(DetectionEvent.detected_at, DetectionEvent.id).limit(500).all()
    points, missing = [], []
    for item in items:
        value = _detection_out(db, item).model_dump(mode="json")
        if value["latitude"] is None or value["longitude"] is None:
            missing.append(item.id)
        else:
            points.append(value)
    return {"label": "Observed Camera Detection Path", "plate": normalized, "points": points, "missing_coordinates": missing, "limit": 500}


@router.post("/detections/ingest", response_model=DetectionOut)
def ingest_detection(payload: DetectionCreate, db: Session = Depends(get_db), _key: str = Depends(machine_ingest)):
    camera = db.get(Camera, payload.camera_id)
    if not camera or camera.department_id != payload.department_id:
        raise HTTPException(status_code=404, detail="Camera not found for department")
    department = _department(db, payload.department_id, camera.org_id)
    def replay():
        old = db.query(DetectionEvent).filter(DetectionEvent.request_id == payload.request_id).first()
        if old:
            old_time = old.detected_at.replace(tzinfo=timezone.utc) if old.detected_at.tzinfo is None else old.detected_at
            new_time = payload.detected_at.replace(tzinfo=timezone.utc) if payload.detected_at.tzinfo is None else payload.detected_at
            stored = (old.camera_id, old.source_system, old_time, old.vehicle_class, old.vehicle_confidence,
                      old.plate_text, old.plate_confidence, old.evidence_url, old.metadata_json, old.is_demo)
            incoming = (camera.id, payload.source_system, new_time, payload.vehicle_class, payload.vehicle_confidence,
                        normalize_plate(payload.plate_text), payload.plate_confidence, payload.evidence_url, payload.metadata, payload.is_demo)
            if stored != incoming:
                raise HTTPException(409, "Idempotency key already used for another observation")
        return _detection_out(db, old) if old else None
    if payload.request_id:
        previous = replay()
        if previous:
            return previous
    # Coordinates belong to the camera registry, not to caller-supplied locations.
    item = DetectionEvent(request_id=payload.request_id, camera_id=camera.id, department_id=department.id, source_system=payload.source_system, detected_at=payload.detected_at, vehicle_class=payload.vehicle_class, vehicle_confidence=payload.vehicle_confidence, plate_text=normalize_plate(payload.plate_text), plate_confidence=payload.plate_confidence, evidence_url=payload.evidence_url, latitude=camera.latitude, longitude=camera.longitude, metadata_json=payload.metadata, is_demo=payload.is_demo)
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if payload.request_id:
            previous = replay()
            if previous:
                return previous
        raise
    record(db, camera.org_id, "detection.ingest", "detection", item.id,
           department_id=department.id, source_system=item.source_system, is_demo=item.is_demo)
    if item.plate_text:
        entries = db.query(WatchlistEntry).join(Watchlist, Watchlist.id == WatchlistEntry.watchlist_id).filter(Watchlist.department_id == department.id, Watchlist.active.is_(True), WatchlistEntry.active.is_(True), WatchlistEntry.plate_text == item.plate_text).all()
        for entry in entries:
            alert = Alert(department_id=department.id, detection_id=item.id, watchlist_entry_id=entry.id, priority=entry.priority)
            db.add(alert)
            db.flush()
            record(db, camera.org_id, "alert.generate", "alert", alert.id,
                   department_id=department.id, detection_id=item.id, watchlist_entry_id=entry.id, is_demo=item.is_demo)
    db.commit()
    db.refresh(item)
    return _detection_out(db, item)


@router.get("/watchlists", response_model=list[WatchlistOut])
def list_watchlists(db: Session = Depends(get_db), user=Depends(current_user)):
    departments = {item.id for item in db.query(Department).filter(Department.org_id == user.org_id).all()}
    result = []
    for item in db.query(Watchlist).filter(Watchlist.department_id.in_(departments)).order_by(Watchlist.created_at.desc()).all():
        entries = db.query(WatchlistEntry).filter(WatchlistEntry.watchlist_id == item.id).all()
        result.append(WatchlistOut.model_validate({**item.__dict__, "entries": entries}))
    return result


@router.post("/watchlists", response_model=WatchlistOut)
def create_watchlist(payload: WatchlistCreate, db: Session = Depends(get_db), user=Depends(require_admin)):
    _department(db, payload.department_id, user.org_id)
    item = Watchlist(department_id=payload.department_id, name=payload.name, description=payload.description, active=payload.active, created_by=user.id)
    db.add(item)
    db.flush()
    record(db, user.org_id, "watchlist.create", "watchlist", item.id, user.id,
           department_id=item.department_id, description=item.description)
    db.commit()
    db.refresh(item)
    return WatchlistOut.model_validate({**item.__dict__, "entries": []})


@router.post("/watchlists/{watchlist_id}/entries", response_model=WatchlistEntryOut)
def add_watchlist_entry(watchlist_id: str, payload: WatchlistEntryCreate, db: Session = Depends(get_db), user=Depends(require_admin)):
    item = db.get(Watchlist, watchlist_id)
    if not item or not db.query(Department).filter(Department.id == item.department_id, Department.org_id == user.org_id).first():
        raise HTTPException(status_code=404, detail="Watchlist not found")
    plate = normalize_plate(payload.plate_text)
    if not plate:
        raise HTTPException(status_code=422, detail="Invalid Indian registration format")
    entry = WatchlistEntry(watchlist_id=item.id, plate_text=plate, priority=payload.priority, reason=payload.reason, active=payload.active)
    db.add(entry)
    db.flush()
    record(db, user.org_id, "watchlist.entry.add", "watchlist_entry", entry.id, user.id,
           department_id=item.department_id, watchlist_id=item.id, reason=entry.reason)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/alerts")
def list_alerts(db: Session = Depends(get_db), user=Depends(current_user), limit: int = Query(default=100, le=500)):
    return [alert_out(db, item) for item in alert_query(db, user.org_id).order_by(Alert.created_at.desc(), Alert.id.desc()).limit(limit).all()]
