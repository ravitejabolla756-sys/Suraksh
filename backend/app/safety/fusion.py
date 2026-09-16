"""Correlation-aware evidence fusion for safety perception, without policy decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import prod
from typing import Any, Mapping, Sequence
from uuid import uuid4

from .evidence import EvidenceFrameReference


class SignalPolarity(str, Enum):
    SUPPORT = "support"
    CONTRADICT = "contradict"


@dataclass(frozen=True, slots=True)
class FusionSignal:
    """One explicit signal; model confidence is not silently treated as truth."""

    name: str
    value: float
    model_id: str
    model_version: str
    evidence: tuple[EvidenceFrameReference, ...] = ()
    reliability: float = 1.0
    polarity: SignalPolarity = SignalPolarity.SUPPORT
    correlation_group: str | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.model_id or not self.model_version:
            raise ValueError("signal and model identity fields are required")
        if not 0.0 <= self.value <= 1.0 or not 0.0 <= self.reliability <= 1.0:
            raise ValueError("signal value and reliability must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class FusionRequest:
    event_type: str
    camera_id: str
    timestamp: datetime
    signals: tuple[FusionSignal, ...]


@dataclass(frozen=True, slots=True)
class EvidenceFusionConfig:
    """Transparent fusion parameters, not emergency-alert policy."""

    correlation_penalty: float = 0.25
    contradiction_penalty: float = 0.75
    minimum_independent_groups: int = 2
    sparse_evidence_uncertainty: float = 0.20

    def __post_init__(self) -> None:
        if not 0 <= self.correlation_penalty <= 1 or not 0 <= self.contradiction_penalty <= 1:
            raise ValueError("fusion penalties must be between 0 and 1")
        if self.minimum_independent_groups < 1 or not 0 <= self.sparse_evidence_uncertainty <= 1:
            raise ValueError("fusion limits are invalid")


@dataclass(frozen=True, slots=True)
class FusedSafetyEvent:
    event_type: str
    camera_id: str
    timestamp: datetime
    confidence: float
    uncertainty: float
    contributing_signals: tuple[str, ...]
    signal_contributions: Mapping[str, float]
    evidence_references: tuple[EvidenceFrameReference, ...]
    model_versions: Mapping[str, str]
    supporting_groups: tuple[str, ...]
    contradicting_groups: tuple[str, ...]

    def as_payload(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "camera_id": self.camera_id,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "contributing_signals": dict(self.signal_contributions),
            "evidence_references": [
                {"camera_id": item.camera_id, "sequence": item.sequence, "timestamp": item.timestamp.isoformat(), "recording_id": item.recording_id, "frame_uri": item.frame_uri, "offset_seconds": item.offset_seconds, "sha256": item.sha256}
                for item in self.evidence_references
            ],
            "model_versions": dict(self.model_versions),
        }


class SafetyEvidenceFusionEngine:
    """Fuse explicit signals into perception evidence; never emits policy actions."""

    def __init__(self, config: EvidenceFusionConfig | None = None):
        self.config = config or EvidenceFusionConfig()

    def fuse(self, request: FusionRequest) -> FusedSafetyEvent:
        if any(reference.camera_id != request.camera_id for signal in request.signals for reference in signal.evidence):
            raise ValueError("signal evidence must belong to the request camera")
        groups: dict[str, list[FusionSignal]] = {}
        for signal in request.signals:
            groups.setdefault(signal.correlation_group or signal.name, []).append(signal)
        supporting, contradicting = [], []
        group_support: dict[str, float] = {}
        group_contradiction: dict[str, float] = {}
        for group, signals in groups.items():
            values = [signal.value * signal.reliability for signal in signals]
            combined = 1.0 - prod(1.0 - value for value in values)
            # Correlated visual signals reinforce one another less than
            # independent detector/tracker/temporal sources.
            combined *= 1.0 - self.config.correlation_penalty * max(0, len(signals) - 1) / len(signals)
            if any(signal.polarity is SignalPolarity.SUPPORT for signal in signals):
                group_support[group] = combined
                supporting.append(group)
            if any(signal.polarity is SignalPolarity.CONTRADICT for signal in signals):
                group_contradiction[group] = combined
                contradicting.append(group)
        support = 1.0 - prod(1.0 - value for value in group_support.values())
        contradiction = 1.0 - prod(1.0 - value for value in group_contradiction.values())
        confidence = support * (1.0 - self.config.contradiction_penalty * contradiction)
        independent_coverage = min(1.0, len(supporting) / self.config.minimum_independent_groups)
        support_values = [signal.value for signal in request.signals if signal.polarity is SignalPolarity.SUPPORT]
        disagreement = (max(support_values) - min(support_values)) if len(support_values) > 1 else 1.0
        uncertainty = min(1.0, (1.0 - confidence) * 0.45 + contradiction * 0.25 + (1.0 - independent_coverage) * self.config.sparse_evidence_uncertainty + disagreement * 0.10)
        contributions = {signal.name: round(signal.value * signal.reliability, 6) for signal in request.signals}
        evidence: dict[tuple[Any, ...], EvidenceFrameReference] = {}
        versions: dict[str, str] = {}
        for signal in request.signals:
            versions[signal.model_id] = signal.model_version
            for reference in signal.evidence:
                key = (reference.camera_id, reference.sequence, reference.timestamp, reference.frame_uri)
                evidence[key] = reference
        return FusedSafetyEvent(request.event_type, request.camera_id, request.timestamp, round(max(0.0, min(1.0, confidence)), 6), round(max(0.0, min(1.0, uncertainty)), 6), tuple(signal.name for signal in request.signals if signal.value * signal.reliability >= .1), contributions, tuple(sorted(evidence.values(), key=lambda item: (item.timestamp, item.sequence))), dict(sorted(versions.items())), tuple(sorted(supporting)), tuple(sorted(contradicting)))


@dataclass(frozen=True, slots=True)
class SafetyEvent:
    """Perception candidate; operational lifecycle belongs to Incident Engine."""
    event_id: str
    camera_id: str
    event_type: str
    severity: str
    confidence: float
    source_frame_index: int
    source_timestamp: float
    involved_track_ids: tuple[int, ...]
    evidence_references: tuple[EvidenceFrameReference, ...]
    state: str
    created_at: datetime

    def as_payload(self) -> dict[str, Any]:
        return {"event_id": self.event_id, "camera_id": self.camera_id, "event_type": self.event_type,
                "severity": self.severity, "confidence": self.confidence,
                "source_frame_index": self.source_frame_index, "source_timestamp": self.source_timestamp,
                "involved_track_ids": list(self.involved_track_ids), "state": self.state,
                "created_at": self.created_at.isoformat(),
                "evidence_references": [ref.frame_uri for ref in self.evidence_references]}


class SafetyPerceptionFusion:
    """Normalize specialist and track inputs into candidate SafetyEvents only."""
    EVENT_TYPES = {"FIRE", "SMOKE", "ACCIDENT", "PERSON_INTRUSION", "CROWDING", "VEHICLE_INTRUSION"}

    def candidate(self, event_type: str, camera_id: str, source_frame_index: int,
                  source_timestamp: float, confidence: float, signals: Sequence[FusionSignal] = (),
                  severity: str = "medium", track_ids: Sequence[int] = (), state: str = "CANDIDATE") -> SafetyEvent:
        if event_type not in self.EVENT_TYPES or not camera_id or not 0 <= confidence <= 1:
            raise ValueError("invalid safety event candidate")
        evidence = tuple(ref for signal in signals for ref in signal.evidence)
        return SafetyEvent(str(uuid4()), camera_id, event_type, severity, confidence,
                           source_frame_index, source_timestamp, tuple(sorted(set(track_ids))), evidence,
                           state, datetime.now(timezone.utc))
