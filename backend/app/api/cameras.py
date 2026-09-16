import csv
import io
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_admin
from app.models.database import get_db
from app.models.entities import Camera, ConnectorStatus, Department, HealthStatus, VMSSystem
from app.services.connectors import VMSAConnector, VMSBConnector
from app.services.audit import record
from app.schemas.dto import CameraImportResult, CameraOut, CameraPatch, CameraRegistryCreate, DepartmentOut, VMSOut

router = APIRouter(prefix="/cameras", tags=["cameras"])
department_router = APIRouter(prefix="/departments", tags=["departments"])
vms_router = APIRouter(prefix="/integrations", tags=["integrations"])


def _department(db: Session, department_id: str, org_id: str) -> Department:
    department = db.get(Department, department_id)
    if not department or department.org_id != org_id:
        raise HTTPException(status_code=404, detail="Department not found")
    return department


def _camera_query(db: Session, user, department: str | None, district: str | None, vendor: str | None, vms: str | None, health: str | None, search: str | None):
    query = db.query(Camera).filter(Camera.org_id == user.org_id)
    if department:
        query = query.filter(Camera.department_id == department)
    if district:
        query = query.filter(Camera.district == district)
    if vendor:
        query = query.filter(Camera.vendor == vendor)
    if vms:
        query = query.filter(Camera.vms_system_id == vms)
    if health:
        try:
            query = query.filter(Camera.health_status == HealthStatus(health.upper()))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid health status") from exc
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(Camera.name.ilike(term), Camera.external_id.ilike(term), Camera.district.ilike(term)))
    return query.order_by(Camera.name)


@router.get("", response_model=list[CameraOut])
def list_cameras(db: Session = Depends(get_db), user=Depends(current_user), department: str | None = Query(default=None), district: str | None = Query(default=None), vendor: str | None = Query(default=None), vms: str | None = Query(default=None), health: str | None = Query(default=None), search: str | None = Query(default=None, max_length=100)):
    return _camera_query(db, user, department, district, vendor, vms, health, search).limit(500).all()


@router.get("/{camera_id}", response_model=CameraOut)
def get_camera(camera_id: str, db: Session = Depends(get_db), user=Depends(current_user)):
    camera = db.get(Camera, camera_id)
    if not camera or camera.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@router.post("", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
def create_camera(payload: CameraRegistryCreate, db: Session = Depends(get_db), user=Depends(require_admin)):
    _department(db, payload.department_id, user.org_id)
    if payload.vms_system_id:
        vms = db.get(VMSSystem, payload.vms_system_id)
        if not vms or vms.department_id != payload.department_id:
            raise HTTPException(422, "VMS must belong to camera department")
    values = payload.model_dump()
    values["source_url"] = values.pop("stream_endpoint")
    values["location_name"] = values["zone"]
    camera = Camera(org_id=user.org_id, **values)
    db.add(camera)
    db.flush()
    record(db, user.org_id, "camera.onboard", "camera", camera.id, user.id,
           department_id=camera.department_id, is_demo=camera.is_demo)
    db.commit()
    db.refresh(camera)
    return camera


@router.patch("/{camera_id}", response_model=CameraOut)
def update_camera(camera_id: str, payload: CameraPatch, db: Session = Depends(get_db), user=Depends(require_admin)):
    camera = db.get(Camera, camera_id)
    if not camera or camera.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Camera not found")
    values = payload.model_dump(exclude_unset=True)
    if "department_id" in values:
        _department(db, values["department_id"], user.org_id)
    if "stream_endpoint" in values:
        values["source_url"] = values.pop("stream_endpoint")
    for key, value in values.items():
        if key == "health_status" and value is not None:
            value = HealthStatus(value.upper())
        setattr(camera, key, value)
    camera.updated_at = datetime.now(timezone.utc)
    record(db, user.org_id, "camera.update", "camera", camera.id, user.id,
           department_id=camera.department_id, is_demo=camera.is_demo)
    db.commit()
    db.refresh(camera)
    return camera


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_camera(camera_id: str, db: Session = Depends(get_db), user=Depends(require_admin)):
    camera = db.get(Camera, camera_id)
    if not camera or camera.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Camera not found")
    camera.health_status = HealthStatus.unknown
    camera.stream_status = "DEACTIVATED"
    db.commit()


@router.get("/import/template", response_class=PlainTextResponse)
def import_template(user=Depends(require_admin)):
    return "name,external_id,department_id,district,zone,latitude,longitude,camera_type,vendor,model,vms_system_id,protocol,stream_endpoint,storage_type,retention_days,is_demo\n"


@router.post("/import", response_model=CameraImportResult)
async def import_cameras(file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(require_admin)):
    if file.content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel"} and not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="CSV file required")
    raw = await file.read(1_100_001)
    if len(raw) > 1_000_000:
        raise HTTPException(status_code=413, detail="CSV exceeds 1 MB limit")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    created = updated = 0
    errors: list[dict] = []
    for row_number, row in enumerate(reader, start=2):
        if row_number > 1001:
            errors.append({"row": row_number, "error": "maximum 1000 rows exceeded"})
            break
        try:
            payload = CameraRegistryCreate(name=row.get("name", ""), external_id=row.get("external_id") or None, department_id=row.get("department_id", ""), district=row.get("district", ""), zone=row.get("zone") or "Unknown", latitude=float(row["latitude"]) if row.get("latitude") else None, longitude=float(row["longitude"]) if row.get("longitude") else None, camera_type=row.get("camera_type") or "fixed", vendor=row.get("vendor") or "Unknown", model=row.get("model") or "Unknown", vms_system_id=row.get("vms_system_id") or None, protocol=row.get("protocol") or "RTSP", stream_endpoint=row.get("stream_endpoint") or "", storage_type=row.get("storage_type") or "VMS", retention_days=int(row.get("retention_days") or 30), is_demo=(row.get("is_demo", "true").lower() != "false"))
            _department(db, payload.department_id, user.org_id)
            camera = db.query(Camera).filter(Camera.org_id == user.org_id, Camera.external_id == payload.external_id).first() if payload.external_id else None
            values = payload.model_dump()
            values["source_url"] = values.pop("stream_endpoint")
            values["location_name"] = values["zone"]
            if camera:
                for key, value in values.items():
                    setattr(camera, key, value)
                updated += 1
            else:
                db.add(Camera(org_id=user.org_id, **values))
                created += 1
        except (ValueError, TypeError, HTTPException) as exc:
            errors.append({"row": row_number, "error": getattr(exc, "detail", str(exc))})
    db.commit()
    return CameraImportResult(created_count=created, updated_count=updated, failed_count=len(errors), errors=errors)


@department_router.get("", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db), user=Depends(current_user)):
    return db.query(Department).filter(Department.org_id == user.org_id).order_by(Department.name).all()


@vms_router.get("/vms", response_model=list[VMSOut])
def list_vms(db: Session = Depends(get_db), user=Depends(current_user)):
    vms = db.query(VMSSystem).join(Department, Department.id == VMSSystem.department_id).filter(Department.org_id == user.org_id).all()
    return [VMSOut.model_validate({**item.__dict__, "camera_count": db.query(Camera).filter(Camera.vms_system_id == item.id).count()}) for item in vms]


@vms_router.post("/vms/{vms_id}/sync")
def sync_vms(vms_id: str, db: Session = Depends(get_db), user=Depends(current_user)):
    item = db.get(VMSSystem, vms_id)
    if not item or not db.query(Department).filter(Department.id == item.department_id, Department.org_id == user.org_id).first():
        raise HTTPException(status_code=404, detail="VMS system not found")
    try:
        response = httpx.get(item.base_url, timeout=5)
        response.raise_for_status()
        connector = VMSAConnector(response.json()) if item.vendor == "Federated Vendor A" else VMSBConnector(response.json())
        item.last_sync = datetime.now(timezone.utc)
        item.status = ConnectorStatus.connected
        db.commit()
        return {"vms_id": item.id, "status": item.status.value if hasattr(item.status, "value") else item.status, "camera_count": len(connector.list_cameras()), "normalized_events": [connector.normalize_event(event) for event in connector.get_events()], "demo_notice": "SYNTHETIC VMS SIMULATOR"}
    except (httpx.HTTPError, ValueError) as exc:
        item.status = ConnectorStatus.offline
        db.commit()
        raise HTTPException(status_code=503, detail=f"VMS connector unavailable: {exc}") from exc
