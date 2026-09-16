"""Camera-specific accident policy; coordinate units are never inferred as km/h."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class CameraCalibration:
    """Map box anchors to a road plane. A homography must come from calibration."""

    version: str = "uncalibrated-pixels-v1"
    units: str = "pixels"
    homography: tuple[float, ...] | None = None
    anchor: str = "bottom_center"

    def __post_init__(self) -> None:
        if not self.version or self.units not in {"pixels", "meters"}:
            raise ValueError("calibration requires a version and pixels or meters")
        if self.anchor not in {"center", "bottom_center"}:
            raise ValueError("unsupported box anchor")
        if self.units == "meters" and self.homography is None:
            raise ValueError("metric coordinates require a calibrated homography")
        if self.homography is not None:
            h = self.homography
            if len(h) != 9 or not all(isfinite(value) for value in h):
                raise ValueError("homography must contain nine finite numbers")
            determinant = h[0]*(h[4]*h[8]-h[5]*h[7])-h[1]*(h[3]*h[8]-h[5]*h[6])+h[2]*(h[3]*h[7]-h[4]*h[6])
            if abs(determinant) < 1e-12:
                raise ValueError("homography must be invertible")

    def project(self, box: tuple[float, float, float, float]) -> tuple[float, float]:
        x = (box[0] + box[2]) / 2
        y = box[3] if self.anchor == "bottom_center" else (box[1] + box[3]) / 2
        if self.homography is None:
            return x, y
        h = self.homography
        denominator = h[6]*x + h[7]*y + h[8]
        if abs(denominator) < 1e-9:
            raise ValueError("box anchor lies outside the calibrated road plane")
        point = ((h[0]*x+h[1]*y+h[2])/denominator, (h[3]*x+h[4]*y+h[5])/denominator)
        if not all(isfinite(value) for value in point):
            raise ValueError("invalid projected coordinates")
        return point


@dataclass(frozen=True, slots=True)
class AccidentConfig:
    """Defaults are experimental pixel thresholds; deployments tune per camera."""

    window_size: int = 32
    persistence_frames: int = 3
    confidence_threshold: float = 0.7
    collision_distance: float = 55.0
    impact_deceleration: float = 35.0
    minimum_approach_speed: float = 12.0
    stationary_speed: float = 3.0
    speed_drop_ratio: float = 0.6
    heading_change_radians: float = 1.0
    visual_evidence_threshold: float = 0.75
    minimum_track_confidence: float = 0.5
    minimum_confirmation_seconds: float = 0.25
    approach_window_seconds: float = 2.0
    candidate_timeout_seconds: float = 4.0
    trajectory_horizon_seconds: float = 2.0
    max_track_gap_seconds: float = 2.0
    resolution_seconds: float = 3.0
    deduplication_seconds: float = 30.0
    deduplication_frames: int = 30
    max_evidence_frames: int = 8
    max_tracks: int = 128
    max_candidates: int = 256
    max_cameras: int = 64
    enabled: bool = False  # Explicit opt-in; registration alone is not enough.

    def __post_init__(self) -> None:
        counts = (self.window_size, self.persistence_frames, self.deduplication_frames,
                  self.max_evidence_frames, self.max_tracks, self.max_candidates, self.max_cameras)
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in counts):
            raise ValueError("accident count limits must be positive integers")
        if self.persistence_frames < 2 or self.window_size < max(3, self.persistence_frames):
            raise ValueError("confirmation requires multiple frames within the history window")
        if self.max_evidence_frames < 3:
            raise ValueError("retain at least approach, impact and confirmation evidence")
        positive = (self.collision_distance, self.impact_deceleration, self.minimum_approach_speed,
                    self.approach_window_seconds, self.candidate_timeout_seconds,
                    self.trajectory_horizon_seconds, self.max_track_gap_seconds, self.resolution_seconds,
                    self.minimum_confirmation_seconds, self.heading_change_radians)
        if any(not isfinite(value) or value <= 0 for value in positive):
            raise ValueError("accident motion and time thresholds must be finite and positive")
        if self.candidate_timeout_seconds < self.minimum_confirmation_seconds:
            raise ValueError("candidate timeout must allow the confirmation interval")
        for value in (self.confidence_threshold, self.speed_drop_ratio,
                      self.visual_evidence_threshold, self.minimum_track_confidence):
            if not isfinite(value) or not 0 < value <= 1:
                raise ValueError("accident confidence and ratio thresholds must be in (0, 1]")
        if any(not isfinite(value) or value < 0 for value in (self.stationary_speed, self.deduplication_seconds)):
            raise ValueError("stationary speed and cooldown must be nonnegative")
