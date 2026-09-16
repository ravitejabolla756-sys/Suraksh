"""Tracker-independent ANPR contracts. Coordinates are source-image pixels."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from typing import Any

BBox = tuple[float, float, float, float]


def valid_box(box: BBox) -> bool:
    return len(box) == 4 and all(isfinite(v) for v in box) and box[2] > box[0] and box[3] > box[1]


@dataclass(frozen=True, slots=True)
class VehicleTrack:
    organization_id: str
    camera_id: str
    track_id: int
    vehicle_class: str
    bbox: BBox
    source_frame_index: int
    source_timestamp: float
    observed_at: datetime
    tracker_session_id: str

    def __post_init__(self):
        if not all((self.organization_id, self.camera_id, self.tracker_session_id)):
            raise ValueError("Track scope is required")
        if self.track_id < 0 or self.source_frame_index < 0 or not isfinite(self.source_timestamp) or self.source_timestamp < 0:
            raise ValueError("Invalid source identity")
        if not valid_box(self.bbox) or self.observed_at.tzinfo is None:
            raise ValueError("Valid box and timezone-aware observation time required")

    @property
    def key(self) -> tuple[str, str, str, int]:
        return self.organization_id, self.camera_id, self.tracker_session_id, self.track_id


@dataclass(frozen=True, slots=True)
class PlateQuality:
    width: int
    height: int
    blur: float
    brightness: float
    contrast: float
    detector_confidence: float
    score: float
    visibility: float = 1.0
    angle_degrees: float | None = None
    perspective_ratio: float | None = None
    rejection_reasons: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return not self.rejection_reasons


@dataclass(frozen=True, slots=True)
class PlateDetection:
    bbox: BBox
    confidence: float
    source_frame_index: int
    source_timestamp: float
    quality: PlateQuality | None = None
    corners: tuple[tuple[float, float], ...] = ()  # TL, TR, BR, BL when supplied
    visibility: float | None = None

    def __post_init__(self):
        if not valid_box(self.bbox) or not 0 <= self.confidence <= 1:
            raise ValueError("Invalid plate detection")
        if self.visibility is not None and not 0 <= self.visibility <= 1:
            raise ValueError("Invalid visibility")

    @property
    def plate_quality_features(self) -> PlateQuality | None:
        return self.quality


class NumberPlateDetector(ABC):
    model_id: str
    model_version: str

    @abstractmethod
    def detect(self, frame: Any, source_frame_index: int, source_timestamp: float) -> tuple[PlateDetection, ...]:
        """Return plate boxes, never vehicle identities."""


class OCRReader(ABC):
    model_id: str
    model_version: str

    @abstractmethod
    def read(self, crop: Any, source_frame_index: int, source_timestamp: float) -> OCRObservation:
        """Read a gated crop; business validation belongs to the pipeline."""


@dataclass(frozen=True, slots=True)
class OCRObservation:
    raw_text: str
    normalized_text: str | None
    confidence: float
    source_frame_index: int
    source_timestamp: float
    character_confidence: tuple[float, ...] = ()

    def __post_init__(self):
        if len(self.raw_text) > 128 or not 0 <= self.confidence <= 1 or self.source_frame_index < 0:
            raise ValueError("Invalid OCR observation")
        if not isfinite(self.source_timestamp) or self.source_timestamp < 0:
            raise ValueError("Invalid OCR timestamp")
        if any(not 0 <= value <= 1 for value in self.character_confidence):
            raise ValueError("Invalid character confidence")


@dataclass(frozen=True, slots=True)
class PlateRecognitionResult:
    result_id: str
    organization_id: str
    camera_id: str
    vehicle_track_id: int
    raw_text: str
    normalized_text: str
    confidence: float
    detection_confidence: float
    ocr_confidence: float
    quality_score: float
    first_seen_at: datetime
    last_seen_at: datetime
    source_frame_index: int
    source_timestamp: float
    evidence_reference: str
    model_version: str
    validation_result: str
    tracker_session_id: str = "legacy"
    vehicle_class: str = "vehicle"
    plate_crop_reference: str = ""
    vehicle_track_reference: str = ""
    model_versions: dict[str, str] = field(default_factory=dict)
    observation_count: int = 0
    validation_rule: str | None = None


@dataclass(frozen=True, slots=True)
class ANPRConfig:
    enabled: bool = False
    minimum_observations: int = 3
    confidence_weighting: bool = True
    character_voting: bool = True
    temporal_window_seconds: float = 8.0
    maximum_disagreement: int = 2
    plate_stability_requirement: float = .7
    minimum_crop_width: int = 64
    minimum_crop_height: int = 20
    minimum_blur_variance: float = 35.0
    minimum_contrast: float = 12.0
    minimum_brightness: float = 25.0
    maximum_brightness: float = 235.0
    minimum_visibility: float = .9
    minimum_detector_confidence: float = .5
    minimum_ocr_confidence: float = .5
    maximum_angle_degrees: float = 35.0
    minimum_perspective_ratio: float = .4
    sample_interval_seconds: float = .5
    confirmed_interval_seconds: float = 4.0
    continuity_gap_seconds: float = 3.0
    retention_seconds: float = 30.0  # in-memory idle track TTL, not durable retention
    max_tracks: int = 256
    max_observations: int = 32
    max_ocr_per_frame: int = 4
    enhancement: bool = False
    region: str = "IN"
    validation_rule_version: str = "in-standard-bh-v1"
    validation_patterns: tuple[str, ...] = (r"[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{1,4}", r"[0-9]{2}BH[0-9]{4}[A-Z]{1,2}")

    def __post_init__(self):
        numeric = [v for v in self.__dataclass_fields__ if isinstance(getattr(self, v), (int, float))]
        if any(not isfinite(getattr(self, key)) for key in numeric):
            raise ValueError("ANPR thresholds must be finite")
        if not 2 <= self.minimum_observations <= self.max_observations <= 256:
            raise ValueError("At least two distinct observations required")
        if min(self.temporal_window_seconds, self.retention_seconds, self.sample_interval_seconds, self.continuity_gap_seconds) <= 0:
            raise ValueError("ANPR intervals must be positive")
        if self.confirmed_interval_seconds < self.sample_interval_seconds or min(self.max_tracks, self.max_ocr_per_frame, self.minimum_crop_width, self.minimum_crop_height) < 1:
            raise ValueError("Invalid ANPR budget")
        if self.maximum_disagreement < 0 or not .5 < self.plate_stability_requirement <= 1:
            raise ValueError("Invalid stability requirement")
        if any(not 0 <= v <= 1 for v in (self.minimum_visibility, self.minimum_detector_confidence, self.minimum_ocr_confidence, self.minimum_perspective_ratio)):
            raise ValueError("Invalid confidence threshold")
        if not 0 <= self.minimum_brightness < self.maximum_brightness <= 255 or min(self.minimum_contrast, self.minimum_blur_variance) < 0:
            raise ValueError("Invalid quality thresholds")
        if not self.region or not self.validation_rule_version or not self.validation_patterns:
            raise ValueError("Explicit deployment validation rules required")
