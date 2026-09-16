"""Detector-neutral contracts for Suraksh Edge AI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class FramePacket:
    """Authoritative frame identity and timing crossing into AI perception.

    Source time identifies media position; monotonic timestamps identify local
    capture/processing latency and are never substituted for source time.
    ``processing_timestamp`` is assigned exactly once when a queue hands the
    packet to an AI consumer.
    """
    frame: Any
    source_frame_index: int
    source_timestamp: float
    source_fps: float
    capture_timestamp: float
    camera_id: str
    processing_timestamp: float | None = None
    sequence_number: int = 0

    def __post_init__(self) -> None:
        if self.source_frame_index < 0:
            raise ValueError("source_frame_index must be non-negative")
        if self.source_timestamp < 0 or self.source_fps <= 0:
            raise ValueError("source timing must be non-negative with positive FPS")
        if not self.camera_id:
            raise ValueError("camera_id is required")

    def for_processing(self, timestamp: float) -> "FramePacket":
        if timestamp < self.capture_timestamp:
            raise ValueError("processing timestamp cannot precede capture timestamp")
        if self.processing_timestamp is not None:
            return self
        return type(self)(self.frame, self.source_frame_index, self.source_timestamp,
                          self.source_fps, self.capture_timestamp, self.camera_id,
                          timestamp, self.sequence_number)


# Compatibility name retained for the existing detector contracts.
DetectorInput = FramePacket


@dataclass(frozen=True, slots=True)
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]
    source_frame_index: int
    source_timestamp: float

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between zero and one")
        x1, y1, x2, y2 = self.bbox_xyxy
        if x2 <= x1 or y2 <= y1:
            raise ValueError("bbox_xyxy must have positive area")


@dataclass(frozen=True, slots=True)
class TimingBreakdown:
    preprocessing_ms: float | None
    inference_ms: float | None
    postprocessing_ms: float | None
    total_ms: float
    processing_timestamp: float
    frame_age_ms: float


@dataclass(frozen=True, slots=True)
class DetectorResult:
    detector_id: str
    model_version: str
    input: DetectorInput
    detections: tuple[Detection, ...]
    timing: TimingBreakdown
    metadata: Mapping[str, Any] = field(default_factory=dict)


class DetectorUnavailable(RuntimeError):
    """Candidate cannot run locally; benchmark records the reason."""


class PersonVehicleDetector(ABC):
    detector_id: str
    model_version: str
    license_status: str

    @abstractmethod
    def load(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def detect(self, item: DetectorInput) -> DetectorResult:
        raise NotImplementedError

    def warmup(self, items: Sequence[DetectorInput]) -> None:
        if items:
            self.detect(items[0])
