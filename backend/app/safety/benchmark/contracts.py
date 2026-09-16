"""Serializable contracts used by every Suraksh safety benchmark candidate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from ..contracts import EventFamily


class SafetyStratum(str, Enum):
    DAY = "day"
    NIGHT = "night"
    INDOOR = "indoor"
    OUTDOOR = "outdoor"
    SMALL_DISTANT_EVENT = "small_distant_event"
    LARGE_EVENT = "large_event"
    DIFFICULT_LIGHTING = "difficult_lighting"


@dataclass(frozen=True, slots=True)
class BenchmarkCandidate:
    candidate_id: str
    display_name: str
    event_family: EventFamily
    model_version: str
    input_kind: str
    runtime: str
    model_size_mb: float | None = None
    artifact_uri: str | None = None
    approved: bool = False
    notes: str = ""


@dataclass(frozen=True, slots=True)
class GroundTruth:
    """One annotated clip/episode; event_type=None means a negative sample."""

    sample_id: str
    camera_id: str
    event_family: EventFamily
    event_type: str | None
    start: datetime
    end: datetime
    strata: tuple[SafetyStratum, ...] = ()
    track_ids: tuple[int, ...] = ()

    @property
    def duration_seconds(self) -> float:
        return max(0.0, (self.end - self.start).total_seconds())


@dataclass(frozen=True, slots=True)
class ModelOutput:
    """Candidate output plus measurements captured on the target machine."""

    event_type: str | None
    confidence: float
    detected_at: datetime | None = None
    track_ids: tuple[int, ...] = ()
    inference_latency_ms: float | None = None
    fps: float | None = None
    cpu_percent: float | None = None
    ram_mb: float | None = None
    model_size_mb: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class BenchmarkRecord:
    truth: GroundTruth
    output: ModelOutput
