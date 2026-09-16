"""Stable data contracts for camera-local safety perception."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class EventFamily(str, Enum):
    FIRE = "FIRE"
    SMOKE = "SMOKE"
    ACCIDENT = "ACCIDENT"


class ModelStatus(str, Enum):
    READY = "READY"
    DISABLED = "DISABLED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class FrameInput:
    """A decoded frame; pixel ownership stays with the caller."""

    data: Any
    timestamp: datetime
    camera_id: str
    sequence: int


@dataclass(frozen=True, slots=True)
class TemporalWindow:
    """Bounded ordered context for a temporal/video model."""

    frames: tuple[FrameInput, ...]
    started_at: datetime
    ended_at: datetime

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("temporal window must contain at least one frame")
        if len(self.frames) > 64:
            raise ValueError("temporal window cannot exceed 64 frames")
        if any(frame.camera_id != self.frames[0].camera_id for frame in self.frames):
            raise ValueError("temporal window cannot mix cameras")


@dataclass(frozen=True, slots=True)
class InferenceRequest:
    """Input supplied to either a frame or temporal safety model."""

    frame: FrameInput
    model_id: str
    model_version: str
    temporal_window: TemporalWindow | None = None


@dataclass(frozen=True, slots=True)
class SafetyDetection:
    """A model-produced signal or localized detection."""

    label: str
    confidence: float
    signal: str | None = None
    box: tuple[float, float, float, float] | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.box is not None and len(self.box) != 4:
            raise ValueError("box must contain x1, y1, x2, y2")


@dataclass(frozen=True, slots=True)
class EvidenceFrame:
    """Reference to evidence retained by the caller or evidence store."""

    frame: FrameInput
    uri: str | None = None
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class SafetyPerceptionResult:
    event_family: EventFamily
    camera_id: str
    model_id: str
    model_version: str
    detections: tuple[SafetyDetection, ...]
    confidence: float
    evidence_frames: tuple[EvidenceFrame, ...]
    temporal_window: TemporalWindow | None
    inference_latency_ms: float
    model_status: ModelStatus
    processed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.inference_latency_ms < 0:
            raise ValueError("inference latency cannot be negative")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
