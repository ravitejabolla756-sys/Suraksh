"""Track and trajectory primitives for accident event analysis."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from math import atan2, hypot, isfinite, pi
from typing import Any, Iterable, Mapping

from ..contracts import FrameInput
from .config import CameraCalibration


@dataclass(frozen=True, slots=True)
class TrackObservation:
    track_id: int
    label: str
    box: tuple[float, float, float, float]
    confidence: float = 1.0
    zone: str | None = None
    pose: Mapping[str, Any] = field(default_factory=dict)
    visual_evidence: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.track_id, int) or isinstance(self.track_id, bool) or self.track_id < 0:
            raise ValueError("an anonymous numeric track ID is required")
        if len(self.box) != 4 or not all(isfinite(v) for v in self.box):
            raise ValueError("track box must have four finite coordinates")
        if self.box[2] <= self.box[0] or self.box[3] <= self.box[1]:
            raise ValueError("track box must have positive area")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("invalid track confidence")
        if any(not isfinite(v) or not 0 <= v <= 1 for v in self.visual_evidence.values()):
            raise ValueError("visual evidence scores must be in [0, 1]")

    @property
    def center(self) -> tuple[float, float]:
        return ((self.box[0] + self.box[2]) / 2, (self.box[1] + self.box[3]) / 2)

    @property
    def area(self) -> float:
        return max(0.0, self.box[2] - self.box[0]) * max(0.0, self.box[3] - self.box[1])


@dataclass(frozen=True, slots=True)
class TrajectoryPoint:
    frame_sequence: int
    timestamp: datetime
    center: tuple[float, float]
    box: tuple[float, float, float, float]
    speed: float
    acceleration: float
    zone: str | None
    velocity: tuple[float, float] = (0.0, 0.0)
    acceleration_vector: tuple[float, float] = (0.0, 0.0)
    heading: float | None = None
    heading_change: float = 0.0
    motion_valid: bool = False


@dataclass(frozen=True, slots=True)
class Trajectory:
    track_id: int
    label: str
    points: tuple[TrajectoryPoint, ...]


class TrajectoryExtractor:
    """One camera per extractor. Replayed/late frames never add motion evidence."""

    def __init__(self, max_tracks: int = 128, points_per_track: int = 32,
                 calibration: CameraCalibration | None = None, max_gap_seconds: float = 2.0):
        if max_tracks < 1 or points_per_track < 2 or not isfinite(max_gap_seconds) or max_gap_seconds <= 0:
            raise ValueError("invalid trajectory bounds")
        self.max_tracks, self.points_per_track = max_tracks, points_per_track
        self.calibration = calibration or CameraCalibration()
        self.max_gap_seconds = max_gap_seconds
        self._tracks: dict[int, deque[TrajectoryPoint]] = {}
        self._labels: dict[int, str] = {}
        self._camera_id: str | None = None
        self._last: tuple[int, datetime] | None = None

    def reset(self) -> None:
        self._tracks.clear()
        self._labels.clear()
        self._camera_id = None
        self._last = None

    def update(self, frame: FrameInput, observations: Iterable[TrackObservation]) -> tuple[Trajectory, ...]:
        if frame.timestamp.tzinfo is None or frame.sequence < 0 or not frame.camera_id:
            raise ValueError("source time must be timezone-aware with camera and sequence")
        if self._camera_id not in (None, frame.camera_id):
            raise ValueError("trajectory extractor cannot mix cameras; reset for a new stream")
        if self._last and (frame.sequence <= self._last[0] or frame.timestamp <= self._last[1]):
            return ()
        current = tuple(observations)
        if len({item.track_id for item in current}) != len(current):
            raise ValueError("duplicate track IDs in a frame")
        positions = {item.track_id: self.calibration.project(item.box) for item in current}
        self._camera_id = frame.camera_id
        self._last = (frame.sequence, frame.timestamp)
        stale = [key for key, points in self._tracks.items()
                 if (frame.timestamp - points[-1].timestamp).total_seconds() > self.max_gap_seconds]
        for key in stale:
            self._tracks.pop(key)
            self._labels.pop(key)
        for observation in current[:self.max_tracks]:
            key = observation.track_id
            if self._labels.get(key, observation.label) != observation.label:
                self._tracks.pop(key, None)
            if key not in self._tracks and len(self._tracks) >= self.max_tracks:
                oldest = min(self._tracks, key=lambda value: self._tracks[value][-1].timestamp)
                self._tracks.pop(oldest)
                self._labels.pop(oldest)
            points = self._tracks.setdefault(key, deque(maxlen=self.points_per_track))
            previous = points[-1] if points else None
            elapsed = (frame.timestamp - previous.timestamp).total_seconds() if previous else 1.0
            position = positions[key]
            velocity = tuple((position[i] - previous.center[i]) / elapsed for i in (0, 1)) if previous else (0.0, 0.0)
            speed = hypot(*velocity)
            acceleration = (speed - previous.speed) / elapsed if previous and previous.motion_valid else 0.0
            vector = tuple((velocity[i] - previous.velocity[i]) / elapsed for i in (0, 1)) if previous and previous.motion_valid else (0.0, 0.0)
            heading = atan2(velocity[1], velocity[0]) if speed > 1e-9 else None
            change = abs((heading - previous.heading + pi) % (2*pi) - pi) if previous and heading is not None and previous.heading is not None else 0.0
            points.append(TrajectoryPoint(frame.sequence, frame.timestamp, position, observation.box,
                                          speed, acceleration, observation.zone, velocity, vector,
                                          heading, change, previous is not None))
            self._labels[key] = observation.label
        current_ids = {item.track_id for item in current[:self.max_tracks]}
        return tuple(Trajectory(key, self._labels[key], tuple(points))
                     for key, points in self._tracks.items() if key in current_ids)
