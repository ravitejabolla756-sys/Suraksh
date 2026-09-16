"""Adapter from safety perception events to the existing Incident/Event path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.models.entities import Camera, Event, EventType, SafetyIncidentGroup
from app.services.audit import record
from app.services.notifications import process_event_alerts
from app.safety.evidence import EvidenceFrameReference
from app.safety.fusion import FusedSafetyEvent


SAFETY_EVENT_TYPES = frozenset({
    "fire",
    "smoke",
    "vehicle_collision",
    "vehicle_crash",
    "pedestrian_vehicle_collision",
    "person_fall",
})
ACCIDENT_EVENT_TYPES = frozenset({
    "vehicle_collision",
    "vehicle_crash",
    "pedestrian_vehicle_collision",
    "person_fall",
})


@dataclass(frozen=True, slots=True)
class SafetyIncidentCandidate:
    """Validated perception output accepted by the incident adapter."""

    org_id: str
    camera_id: str
    event_type: str
    confidence: float
    uncertainty: float
    timestamp: datetime
    model_versions: Mapping[str, str]
    contributing_signals: Mapping[str, float]
    evidence_references: tuple[EvidenceFrameReference, ...]
    temporal_window: tuple[datetime, datetime]
    tracks: tuple[int, ...] = ()
    zone_id: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        event_type = self.event_type.strip().lower()
        if event_type not in SAFETY_EVENT_TYPES:
            raise ValueError(f"unsupported safety event type: {self.event_type}")
        if not self.org_id or not self.camera_id:
            raise ValueError("organization and camera are required")
        if not 0 <= self.confidence <= 1 or not 0 <= self.uncertainty <= 1:
            raise ValueError("confidence and uncertainty must be between 0 and 1")
        if not self.model_versions or any(not key or not value for key, value in self.model_versions.items()):
            raise ValueError("at least one model version is required")
        if any(not key or not 0 <= value <= 1 for key, value in self.contributing_signals.items()):
            raise ValueError("contributing signals must be named values between 0 and 1")
        started_at, ended_at = self.temporal_window
        if started_at > ended_at or not started_at <= self.timestamp <= ended_at:
            raise ValueError("timestamp must be inside temporal_window")
        if any(reference.camera_id != self.camera_id for reference in self.evidence_references):
            raise ValueError("evidence references must belong to the candidate camera")
        if any(item.tzinfo is None for item in (self.timestamp, started_at, ended_at)):
            raise ValueError("timestamps must be timezone-aware")
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    @classmethod
    def from_fused(
        cls,
        fused: FusedSafetyEvent,
        *,
        org_id: str,
        temporal_window: tuple[datetime, datetime],
        tracks: tuple[int, ...] = (),
        zone_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "SafetyIncidentCandidate":
        return cls(
            org_id=org_id,
            camera_id=fused.camera_id,
            event_type=fused.event_type,
            confidence=fused.confidence,
            uncertainty=fused.uncertainty,
            timestamp=fused.timestamp,
            model_versions=fused.model_versions,
            contributing_signals=fused.signal_contributions,
            evidence_references=fused.evidence_references,
            temporal_window=temporal_window,
            tracks=tracks,
            zone_id=zone_id,
            metadata=metadata,
        )

    def occurrence(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "timestamp": self.timestamp.isoformat(),
            "tracks": list(self.tracks),
            "model_versions": dict(self.model_versions),
            "contributing_signals": dict(self.contributing_signals),
            "temporal_window": {
                "started_at": self.temporal_window[0].isoformat(),
                "ended_at": self.temporal_window[1].isoformat(),
            },
        }


@dataclass(frozen=True, slots=True)
class SafetyIncidentBridgeConfig:
    cooldown_seconds: float = 60.0
    max_occurrences: int = 64
    max_evidence_references: int = 64

    def __post_init__(self) -> None:
        if self.cooldown_seconds < 0 or self.max_occurrences < 1 or self.max_evidence_references < 1:
            raise ValueError("invalid safety incident grouping limits")


@dataclass(frozen=True, slots=True)
class SafetyIncidentResult:
    status: str
    incident_id: str | None = None
    group_id: str | None = None
    occurrence_count: int = 0
    error: str | None = None


class SafetyIncidentBridge:
    """Thin, durable adapter; Incident/Event remains the source of truth."""

    def __init__(self, config: SafetyIncidentBridgeConfig | None = None):
        self.config = config or SafetyIncidentBridgeConfig()

    def ingest(self, db: Session, candidate: SafetyIncidentCandidate, *, actor_user_id: str | None = None) -> SafetyIncidentResult:
        camera = db.get(Camera, candidate.camera_id)
        if not camera or camera.org_id != candidate.org_id:
            raise ValueError("camera does not belong to candidate organization")

        group_key = self.group_key(candidate)
        group = (
            db.query(SafetyIncidentGroup)
            .filter(
                SafetyIncidentGroup.org_id == candidate.org_id,
                SafetyIncidentGroup.camera_id == candidate.camera_id,
                SafetyIncidentGroup.group_key == group_key,
            )
            .with_for_update()
            .first()
        )
        if group and candidate.timestamp <= _aware(group.cooldown_until):
            event = db.get(Event, group.incident_event_id)
            if not event or event.org_id != candidate.org_id or event.camera_id != candidate.camera_id:
                raise RuntimeError("safety group points to an invalid incident")
            self._merge_event(event, candidate)
            group.last_seen_at = max(_aware(group.last_seen_at), candidate.timestamp)
            group.cooldown_until = max(_aware(group.cooldown_until), candidate.timestamp + timedelta(seconds=self.config.cooldown_seconds))
            group.occurrence_count += 1
            record(db, candidate.org_id, "safety.incident.grouped", "event", event.id, actor_user_id, group_id=group.id, event_type=candidate.event_type, occurrence_count=group.occurrence_count)
            db.flush()
            return SafetyIncidentResult("grouped", event.id, group.id, group.occurrence_count)

        event = Event(
            org_id=candidate.org_id,
            camera_id=candidate.camera_id,
            zone_id=candidate.zone_id,
            type=EventType(candidate.event_type),
            confidence=candidate.confidence,
            edge_detected_at=candidate.timestamp,
            snapshot_url=self._first_uri(candidate.evidence_references),
            video_clip_url=self._first_recording(candidate.evidence_references),
            metadata_json=self._metadata(candidate, group_key),
        )
        db.add(event)
        db.flush()
        if group:
            group.incident_event_id = event.id
            group.first_seen_at = candidate.timestamp
            group.last_seen_at = candidate.timestamp
            group.cooldown_until = candidate.timestamp + timedelta(seconds=self.config.cooldown_seconds)
            group.occurrence_count = 1
        else:
            group = SafetyIncidentGroup(
                org_id=candidate.org_id,
                camera_id=candidate.camera_id,
                incident_event_id=event.id,
                group_key=group_key,
                first_seen_at=candidate.timestamp,
                last_seen_at=candidate.timestamp,
                cooldown_until=candidate.timestamp + timedelta(seconds=self.config.cooldown_seconds),
            )
            db.add(group)
        db.flush()
        process_event_alerts(db, event)
        record(db, candidate.org_id, "safety.incident.created", "event", event.id, actor_user_id, group_id=group.id, event_type=candidate.event_type, model_versions=dict(candidate.model_versions), temporal_window=self._metadata(candidate, group_key)["safety"]["temporal_window"])
        return SafetyIncidentResult("created", event.id, group.id, 1)

    def ingest_safely(self, db: Session, candidate: SafetyIncidentCandidate, *, actor_user_id: str | None = None) -> SafetyIncidentResult:
        """Contain advanced-AI/database failures at the camera boundary."""
        try:
            return self.ingest(db, candidate, actor_user_id=actor_user_id)
        except Exception as exc:  # the camera pipeline must remain alive
            db.rollback()
            return SafetyIncidentResult("failed", error=f"{type(exc).__name__}: {exc}")

    @staticmethod
    def group_key(candidate: SafetyIncidentCandidate) -> str:
        if candidate.event_type in ACCIDENT_EVENT_TYPES and candidate.tracks:
            return "accident:" + ":".join(str(track) for track in sorted(set(candidate.tracks)))
        if candidate.event_type in ACCIDENT_EVENT_TYPES:
            return "accident:scene"
        return candidate.event_type

    def _metadata(self, candidate: SafetyIncidentCandidate, group_key: str) -> dict[str, Any]:
        return {
            **candidate.metadata,
            "safety": {
                "schema_version": "1",
                "group_key": group_key,
                "event_type": candidate.event_type,
                "confidence": candidate.confidence,
                "uncertainty": candidate.uncertainty,
                "camera_id": candidate.camera_id,
                "timestamp": candidate.timestamp.isoformat(),
                "model_versions": dict(candidate.model_versions),
                "contributing_signals": dict(candidate.contributing_signals),
                "tracks": list(candidate.tracks),
                "temporal_window": {"started_at": candidate.temporal_window[0].isoformat(), "ended_at": candidate.temporal_window[1].isoformat()},
                "evidence_references": [self._reference(item) for item in candidate.evidence_references[: self.config.max_evidence_references]],
                "occurrences": [candidate.occurrence()],
            },
        }

    def _merge_event(self, event: Event, candidate: SafetyIncidentCandidate) -> None:
        metadata = dict(event.metadata_json or {})
        safety = dict(metadata.get("safety") or {})
        references = self._deduplicate_references([*safety.get("evidence_references", []), *(self._reference(item) for item in candidate.evidence_references)])
        occurrences = [*safety.get("occurrences", []), candidate.occurrence()]
        safety.update({"latest_event_type": candidate.event_type, "latest_timestamp": candidate.timestamp.isoformat(), "latest_confidence": candidate.confidence, "latest_uncertainty": candidate.uncertainty, "model_versions": {**(safety.get("model_versions") or {}), **candidate.model_versions}, "contributing_signals": dict(candidate.contributing_signals), "tracks": sorted(set((safety.get("tracks") or []) + list(candidate.tracks))), "evidence_references": references[-self.config.max_evidence_references :], "occurrences": occurrences[-self.config.max_occurrences :]})
        if safety.get("temporal_window"):
            started = min(safety["temporal_window"]["started_at"], candidate.temporal_window[0].isoformat())
            ended = max(safety["temporal_window"]["ended_at"], candidate.temporal_window[1].isoformat())
            safety["temporal_window"] = {"started_at": started, "ended_at": ended}
        else:
            safety["temporal_window"] = {"started_at": candidate.temporal_window[0].isoformat(), "ended_at": candidate.temporal_window[1].isoformat()}
        metadata["safety"] = safety
        event.metadata_json = metadata
        event.confidence = max(event.confidence, candidate.confidence)

    @staticmethod
    def _reference(reference: EvidenceFrameReference) -> dict[str, Any]:
        return {"camera_id": reference.camera_id, "sequence": reference.sequence, "timestamp": reference.timestamp.isoformat(), "recording_id": reference.recording_id, "frame_uri": reference.frame_uri, "offset_seconds": reference.offset_seconds, "sha256": reference.sha256}

    @staticmethod
    def _deduplicate_references(references: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[Any, ...]] = set()
        result = []
        for reference in references:
            key = (reference.get("camera_id"), reference.get("sequence"), reference.get("timestamp"), reference.get("frame_uri"))
            if key not in seen:
                seen.add(key)
                result.append(reference)
        return result

    @staticmethod
    def _first_uri(references: tuple[EvidenceFrameReference, ...]) -> str | None:
        return next((item.frame_uri for item in references if item.frame_uri), None)

    @staticmethod
    def _first_recording(references: tuple[EvidenceFrameReference, ...]) -> str | None:
        return next((item.recording_id for item in references if item.recording_id and (item.recording_id.startswith("/") or "://" in item.recording_id)), None)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
