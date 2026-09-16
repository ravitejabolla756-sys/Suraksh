from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import machine_ingest
from app.models.database import get_db
from app.models.entities import Camera
from app.schemas.dto import SafetyIncidentIngest
from app.services.safety_incidents import SafetyIncidentBridge, SafetyIncidentCandidate
from app.safety.evidence import EvidenceFrameReference


router = APIRouter(prefix="/safety/incidents", tags=["safety incidents"])
bridge = SafetyIncidentBridge()


@router.post("/ingest", status_code=202)
def ingest_safety_incident(payload: SafetyIncidentIngest, db: Session = Depends(get_db), _machine_key: str = Depends(machine_ingest)):
    camera = db.get(Camera, payload.camera_id)
    if not camera or camera.org_id != payload.org_id:
        raise HTTPException(status_code=404, detail="Camera not found for organization")
    try:
        candidate = SafetyIncidentCandidate(
            org_id=payload.org_id,
            camera_id=payload.camera_id,
            event_type=payload.event_type,
            confidence=payload.confidence,
            uncertainty=payload.uncertainty,
            timestamp=payload.timestamp,
            model_versions=payload.model_versions,
            contributing_signals=payload.contributing_signals,
            evidence_references=tuple(EvidenceFrameReference(**item.model_dump()) for item in payload.evidence_references),
            temporal_window=(payload.temporal_window.started_at, payload.temporal_window.ended_at),
            tracks=tuple(payload.tracks),
            zone_id=payload.zone_id,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = bridge.ingest_safely(db, candidate)
    if result.status != "failed":
        db.commit()
    return {"status": result.status, "incident_id": result.incident_id, "group_id": result.group_id, "occurrence_count": result.occurrence_count, "error": result.error}
