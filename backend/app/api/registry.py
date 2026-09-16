from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, machine_ingest
from app.models.database import get_db
from app.models.entities import Camera, CameraHealth, CameraStatus, HealthStatus
from app.schemas.dto import GapAnalysis

router = APIRouter(prefix="/registry", tags=["registry"])


@router.get("/summary", response_model=GapAnalysis)
def registry_summary(db: Session = Depends(get_db), user=Depends(current_user)):
    cameras = db.query(Camera).filter(Camera.org_id == user.org_id).all()
    by_district: dict[str, int] = {}
    for camera in cameras:
        by_district[camera.district] = by_district.get(camera.district, 0) + 1
    total = len(cameras) or 1
    online = sum(camera.health_status == HealthStatus.online for camera in cameras)
    offline = sum(camera.health_status == HealthStatus.offline for camera in cameras)
    degraded = sum(camera.health_status == HealthStatus.degraded for camera in cameras)
    return GapAnalysis(total_cameras=len(cameras), by_district=by_district, online_ratio=round(online / total, 4), offline_ratio=round(offline / total, 4), degraded_ratio=round(degraded / total, 4), low_coverage_districts=[district for district, count in by_district.items() if count <= 1], synthetic_data_notice="SYNTHETIC HACKATHON DEMO DATA. This report does not represent statewide coverage.")


@router.get("/health")
def registry_health(db: Session = Depends(get_db), user=Depends(current_user)):
    cameras = db.query(Camera).filter(Camera.org_id == user.org_id).all()
    return [{"camera_id": camera.id, "name": camera.name, "health_status": camera.health_status.value, "stream_status": camera.stream_status, "last_heartbeat": camera.last_heartbeat.isoformat()} for camera in cameras]


class HealthUpdate(BaseModel):
    health_status: HealthStatus = HealthStatus.unknown
    stream_status: str = Field(default="UNKNOWN", max_length=100)
    stream_reachable: bool = False
    failure_count: int = Field(default=0, ge=0)
    measured_fps: float | None = Field(default=None, ge=0, le=1000)
    codec: str | None = Field(default=None, max_length=50)
    resolution: str | None = Field(default=None, max_length=50)


@router.post("/health/{camera_id}")
def update_health(camera_id: str, payload: HealthUpdate, db: Session = Depends(get_db), _machine_key: str = Depends(machine_ingest)):
    camera = db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    camera.health_status = payload.health_status
    camera.stream_status = payload.stream_status
    camera.status = {HealthStatus.online: CameraStatus.online, HealthStatus.offline: CameraStatus.offline,
                     HealthStatus.degraded: CameraStatus.degraded, HealthStatus.unknown: CameraStatus.error}[payload.health_status]
    camera.last_heartbeat = datetime.now(timezone.utc)
    if payload.measured_fps is not None:
        # Legacy registry field is integer nominal FPS; CameraHealth keeps the
        # exact floating-point file measurement below.
        camera.fps = round(payload.measured_fps)
    health = db.query(CameraHealth).filter(CameraHealth.camera_id == camera.id).first()
    if not health:
        health = CameraHealth(camera_id=camera.id)
        db.add(health)
    health.health_status = camera.health_status
    health.stream_reachable = payload.stream_reachable
    health.failure_count = payload.failure_count
    health.measured_fps = payload.measured_fps
    health.codec = payload.codec
    health.resolution = payload.resolution
    db.commit()
    return {"camera_id": camera.id, "health_status": camera.health_status.value, "stream_status": camera.stream_status}
