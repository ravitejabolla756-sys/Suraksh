from datetime import datetime, timedelta, timezone

from app.models.database import SessionLocal
from app.models.entities import AuditLog, Event, SafetyIncidentGroup
from app.services.safety_incidents import (
    SAFETY_EVENT_TYPES,
    SafetyIncidentBridge,
    SafetyIncidentBridgeConfig,
    SafetyIncidentCandidate,
)
from app.safety.evidence import EvidenceFrameReference
from test_mvp import client, machine_headers


def candidate(event_type: str, timestamp: datetime, *, camera_id: str = "cam_gate_1", org_id: str = "org_demo_school", tracks: tuple[int, ...] = ()):
    return SafetyIncidentCandidate(
        org_id=org_id,
        camera_id=camera_id,
        event_type=event_type,
        confidence=0.86,
        uncertainty=0.12,
        timestamp=timestamp,
        model_versions={"safety-temporal": "test-1"},
        contributing_signals={"temporal_persistence": 0.91, "scene_context": 0.72},
        evidence_references=(EvidenceFrameReference(camera_id, 1, timestamp, recording_id="rec-1", frame_uri="/frames/1.jpg"),),
        temporal_window=(timestamp - timedelta(seconds=10), timestamp + timedelta(seconds=10)),
        tracks=tracks,
    )


def test_all_supported_safety_event_types_are_explicitly_accepted():
    now = datetime.now(timezone.utc)
    assert SAFETY_EVENT_TYPES == {
        "fire",
        "smoke",
        "vehicle_collision",
        "vehicle_crash",
        "pedestrian_vehicle_collision",
        "person_fall",
    }
    for event_type in SAFETY_EVENT_TYPES:
        assert candidate(event_type, now).event_type == event_type


def test_created_incident_contains_required_safety_evidence_and_audit():
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        result = SafetyIncidentBridge().ingest(db, candidate("fire", now))
        db.commit()
        event = db.get(Event, result.incident_id)
        assert result.status == "created"
        assert event.type.value == "fire"
        safety = event.metadata_json["safety"]
        assert safety["model_versions"] == {"safety-temporal": "test-1"}
        assert safety["contributing_signals"]["temporal_persistence"] == 0.91
        assert safety["evidence_references"][0]["frame_uri"] == "/frames/1.jpg"
        assert safety["temporal_window"]["started_at"]
        assert db.query(AuditLog).filter(AuditLog.resource_id == event.id, AuditLog.action == "safety.incident.created").count() == 1


def test_continuous_episode_is_grouped_and_not_re_alerted():
    now = datetime.now(timezone.utc)
    bridge = SafetyIncidentBridge(SafetyIncidentBridgeConfig(cooldown_seconds=30, max_occurrences=2))
    with SessionLocal() as db:
        first = bridge.ingest(db, candidate("smoke", now))
        db.commit()
        second = bridge.ingest(db, candidate("smoke", now + timedelta(seconds=10)))
        db.commit()
        assert second.status == "grouped"
        assert second.incident_id == first.incident_id
        assert second.occurrence_count == 2
        assert db.query(Event).filter(Event.id == first.incident_id).count() == 1
        event = db.get(Event, first.incident_id)
        assert len(event.metadata_json["safety"]["occurrences"]) == 2
        assert db.query(SafetyIncidentGroup).filter(SafetyIncidentGroup.id == first.group_id).one().occurrence_count == 2


def test_accident_subtypes_with_same_tracks_share_a_group_but_cooldown_opens_new_event():
    now = datetime.now(timezone.utc)
    bridge = SafetyIncidentBridge(SafetyIncidentBridgeConfig(cooldown_seconds=20))
    with SessionLocal() as db:
        first = bridge.ingest(db, candidate("vehicle_collision", now, tracks=(7, 3)))
        db.commit()
        grouped = bridge.ingest(db, candidate("vehicle_crash", now + timedelta(seconds=5), tracks=(3, 7)))
        db.commit()
        reopened = bridge.ingest(db, candidate("vehicle_crash", now + timedelta(seconds=26), tracks=(3, 7)))
        db.commit()
        assert grouped.status == "grouped"
        assert grouped.incident_id == first.incident_id
        assert reopened.status == "created"
        assert reopened.incident_id != first.incident_id
        assert db.query(Event).filter(Event.camera_id == "cam_gate_1", Event.type.in_(["vehicle_collision", "vehicle_crash"])).count() >= 2


def test_grouping_is_tenant_and_camera_scoped():
    now = datetime.now(timezone.utc)
    bridge = SafetyIncidentBridge()
    with SessionLocal() as db:
        first = bridge.ingest(db, candidate("fire", now, camera_id="cam_gate_1"))
        db.commit()
        other_camera = bridge.ingest(db, candidate("fire", now + timedelta(seconds=1), camera_id="cam_hallway"))
        db.commit()
        assert other_camera.status == "created"
        assert other_camera.incident_id != first.incident_id
        other_tenant = bridge.ingest_safely(db, candidate("fire", now + timedelta(seconds=2), org_id="other-tenant"))
        assert other_tenant.status == "failed"


def test_advanced_ai_failure_is_contained_and_does_not_leave_partial_rows():
    now = datetime.now(timezone.utc)
    bridge = SafetyIncidentBridge()
    with SessionLocal() as db:
        failed = bridge.ingest_safely(db, candidate("fire", now, camera_id="missing-camera"))
        assert failed.status == "failed"
        assert failed.incident_id is None
        assert db.query(Event).filter(Event.camera_id == "missing-camera").count() == 0
        assert db.query(SafetyIncidentGroup).filter(SafetyIncidentGroup.camera_id == "missing-camera").count() == 0


def test_safety_ingest_api_uses_existing_machine_boundary():
    now = datetime.now(timezone.utc)
    payload = {
        "org_id": "org_demo_school",
        "camera_id": "cam_gate_1",
        "event_type": "person_fall",
        "confidence": 0.79,
        "uncertainty": 0.18,
        "timestamp": now.isoformat(),
        "model_versions": {"accident-temporal": "test-1"},
        "contributing_signals": {"trajectory": 0.83},
        "evidence_references": [{"camera_id": "cam_gate_1", "sequence": 8, "timestamp": now.isoformat(), "frame_uri": "/frames/8.jpg"}],
        "temporal_window": {"started_at": (now - timedelta(seconds=2)).isoformat(), "ended_at": (now + timedelta(seconds=2)).isoformat()},
        "tracks": [11],
    }
    response = client.post("/safety/incidents/ingest", json=payload, headers=machine_headers())
    assert response.status_code == 202
    assert response.json()["status"] == "created"
