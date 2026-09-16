"""Camera-isolated candidate state machines over temporal trajectory evidence."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from itertools import combinations
from typing import Iterable, Mapping

from ..contracts import FrameInput
from .config import AccidentConfig, CameraCalibration
from .features import AccidentFeatureRecord, VEHICLE_CLASSES, extract_features
from .tracking import TrackObservation, TrajectoryExtractor


class AccidentState(str, Enum):
    NORMAL = "NORMAL"
    SUSPICIOUS = "SUSPICIOUS"
    CANDIDATE = "CANDIDATE"
    CONFIRMED = "CONFIRMED"
    RESOLVED = "RESOLVED"


@dataclass(frozen=True, slots=True)
class AccidentEvent:
    event_type: str
    confidence: float
    tracks: tuple[int, ...]
    signals: dict[str, float | str | bool]
    evidence_indices: tuple[int, ...]
    temporal_duration: float
    verified: bool
    reason: str
    camera_id: str
    timestamp: datetime
    started_at: datetime
    impact_at: datetime
    features: tuple[AccidentFeatureRecord, ...]
    state: AccidentState = AccidentState.CONFIRMED


@dataclass
class _Candidate:
    event_type: str
    state: AccidentState = AccidentState.NORMAL
    approach: AccidentFeatureRecord | None = None
    impact: AccidentFeatureRecord | None = None
    evidence: deque = field(default_factory=deque)
    support_frames: int = 0
    last_support: datetime | None = None
    last_seen: datetime | None = None
    confirmed_at: datetime | None = None
    confirmed_sequence: int | None = None
    resolved_at: datetime | None = None
    transitions: deque = field(default_factory=lambda: deque(maxlen=16))

    def transition(self, state: AccidentState, timestamp: datetime) -> None:
        if self.state != state:
            self.state = state
            self.transitions.append((state, timestamp))


@dataclass
class _Camera:
    config: AccidentConfig
    calibration: CameraCalibration
    extractor: TrajectoryExtractor
    candidates: dict = field(default_factory=dict)
    last_sequence: int = -1
    last_timestamp: datetime | None = None
    features: tuple[AccidentFeatureRecord, ...] = ()


class AccidentTemporalVerifier:
    """Emits only on entry to CONFIRMED. No database or notification side effects."""

    def __init__(self, config: AccidentConfig | None = None, *,
                 camera_configs: Mapping[str, AccidentConfig] | None = None,
                 calibrations: Mapping[str, CameraCalibration] | None = None):
        self.config = config or AccidentConfig()
        self.camera_configs = dict(camera_configs or {})
        self.calibrations = dict(calibrations or {})
        self._cameras: dict[str, _Camera] = {}

    def reset(self, camera_id: str | None = None) -> None:
        """Call at a recording/track-session discontinuity, never per frame."""
        if camera_id is None:
            self._cameras.clear()
        else:
            self._cameras.pop(camera_id, None)

    def _camera(self, camera_id: str) -> _Camera:
        if camera_id not in self._cameras:
            if len(self._cameras) >= self.config.max_cameras:
                raise ValueError("camera capacity reached; unregister an inactive camera")
            config = self.camera_configs.get(camera_id, self.config)
            calibration = self.calibrations.get(camera_id, CameraCalibration())
            self._cameras[camera_id] = _Camera(config, calibration, TrajectoryExtractor(
                config.max_tracks, config.window_size, calibration, config.max_track_gap_seconds))
        return self._cameras[camera_id]

    def state(self, camera_id: str, track_ids: tuple[int, ...], event_type="vehicle_collision") -> AccidentState:
        camera = self._cameras.get(camera_id)
        candidate = camera.candidates.get((event_type, tuple(sorted(track_ids)))) if camera else None
        return candidate.state if candidate else AccidentState.NORMAL

    def features(self, camera_id: str) -> tuple[AccidentFeatureRecord, ...]:
        camera = self._cameras.get(camera_id)
        return camera.features if camera else ()

    def transitions(self, camera_id: str, track_ids: tuple[int, ...], event_type="vehicle_collision") -> tuple:
        camera = self._cameras.get(camera_id)
        candidate = camera.candidates.get((event_type, tuple(sorted(track_ids)))) if camera else None
        return tuple(candidate.transitions) if candidate else ()

    def observe(self, frame_sequence: int, observations: Iterable[TrackObservation],
                frame_timestamp: datetime, camera_id: str = "accident-camera",
                scene_state: str = "normal") -> tuple[AccidentEvent, ...]:
        if frame_timestamp.tzinfo is None or frame_sequence < 0 or not camera_id:
            raise ValueError("camera, nonnegative frame index and aware source timestamp required")
        camera = self._camera(camera_id)
        config = camera.config
        if not config.enabled:
            return ()
        if camera.last_timestamp and (frame_sequence <= camera.last_sequence or frame_timestamp <= camera.last_timestamp):
            return ()
        current = tuple(observations)
        if len({item.track_id for item in current}) != len(current):
            raise ValueError("duplicate track IDs in one source frame")
        current = tuple(sorted((item for item in current if item.confidence >= config.minimum_track_confidence
                               and item.label in VEHICLE_CLASSES | {"person"}), key=lambda item: item.track_id))[:config.max_tracks]
        trajectories = camera.extractor.update(FrameInput(None, frame_timestamp, camera_id, frame_sequence), current)
        trajectory_map = {item.track_id: item for item in trajectories}
        camera.last_sequence, camera.last_timestamp = frame_sequence, frame_timestamp
        groups = [(tuple(pair), "pedestrian_vehicle_collision" if any(o.label == "person" for o in pair)
                   else "vehicle_collision") for pair in combinations(current, 2)
                  if any(o.label in VEHICLE_CLASSES for o in pair)]
        groups += [((item,), "person_fall" if item.label == "person" else "vehicle_crash") for item in current]
        records, events = [], []
        for items, event_type in groups:
            record = extract_features(camera_id, items, tuple(trajectory_map[item.track_id] for item in items),
                                      config, camera.calibration.units, camera.calibration.version, scene_state)
            # Distant pairs without an episode need not occupy bounded candidate state.
            key = (event_type, record.track_ids)
            if record.distance is not None and record.distance > config.collision_distance * 2 and key not in camera.candidates:
                continue
            records.append(record)
            candidate = camera.candidates.get(key)
            if candidate is None:
                if not self._approaching(record, event_type, config) or len(camera.candidates) >= config.max_candidates:
                    continue
                candidate = _Candidate(event_type, evidence=deque(maxlen=config.max_evidence_frames))
                camera.candidates[key] = candidate
            if candidate.last_seen and (frame_timestamp-candidate.last_seen).total_seconds() > config.max_track_gap_seconds:
                self._resolve(candidate, frame_timestamp)
            candidate.last_seen = frame_timestamp
            event = self._advance(candidate, record, config)
            if event:
                events.append(event)
        camera.features = tuple(records[:config.max_candidates])
        for key, candidate in list(camera.candidates.items()):
            reference = candidate.last_support or candidate.last_seen
            if reference and (frame_timestamp-reference).total_seconds() >= config.resolution_seconds:
                self._resolve(candidate, frame_timestamp)
            if candidate.resolved_at and (frame_timestamp-candidate.resolved_at).total_seconds() > max(config.deduplication_seconds, config.resolution_seconds):
                camera.candidates.pop(key)
        return tuple(events)

    @staticmethod
    def _approaching(record: AccidentFeatureRecord, event_type: str, config: AccidentConfig) -> bool:
        if not record.motion_valid or not record.zone_consistent or record.scene_state in {"camera_motion", "occluded", "discontinuity"}:
            return False
        if len(record.track_ids) == 2:
            return (record.closing_speed >= config.minimum_approach_speed and record.trajectory_intersection
                    and record.distance <= config.collision_distance * 2)
        moving = any((x*x+y*y)**0.5 >= config.minimum_approach_speed for x, y in record.velocities)
        return (moving or record.fallen) if event_type == "person_fall" else moving

    @staticmethod
    def _impact(record: AccidentFeatureRecord, event_type: str, config: AccidentConfig) -> bool:
        abrupt = (record.deceleration >= config.impact_deceleration and record.speed_drop_ratio >= config.speed_drop_ratio)
        visual = record.visual_impact >= config.visual_evidence_threshold
        if event_type == "person_fall":
            return record.fallen and (abrupt or record.heading_change >= config.heading_change_radians or visual or record.speed_drop_ratio >= config.speed_drop_ratio)
        if event_type == "vehicle_crash":
            # Braking by one vehicle is insufficient without independent visual evidence.
            return visual and (abrupt or record.heading_change >= config.heading_change_radians)
        return (record.distance <= config.collision_distance and
                (abrupt or (visual and record.heading_change >= config.heading_change_radians)))

    @staticmethod
    def _aftermath(record: AccidentFeatureRecord, event_type: str, config: AccidentConfig) -> bool:
        if event_type == "person_fall":
            return record.fallen
        geometry = record.distance is None or record.distance <= config.collision_distance
        return geometry and (record.stationary or record.fallen or record.visual_impact >= config.visual_evidence_threshold)

    @staticmethod
    def _resolve(candidate: _Candidate, timestamp: datetime) -> None:
        if candidate.state != AccidentState.RESOLVED:
            candidate.transition(AccidentState.RESOLVED, timestamp)
            candidate.resolved_at = timestamp
            candidate.support_frames = 0
            candidate.evidence.clear()

    def _advance(self, candidate: _Candidate, record: AccidentFeatureRecord, config: AccidentConfig) -> AccidentEvent | None:
        timestamp = record.timestamp
        if candidate.state == AccidentState.RESOLVED:
            if candidate.confirmed_at and ((timestamp-candidate.confirmed_at).total_seconds() < config.deduplication_seconds
                                          or record.source_frame_index-candidate.confirmed_sequence < config.deduplication_frames):
                return None
            candidate.transition(AccidentState.NORMAL, timestamp)
            candidate.approach = candidate.impact = None
            candidate.resolved_at = candidate.last_support = None
        if not record.motion_valid or not record.zone_consistent or record.scene_state in {"camera_motion", "occluded", "discontinuity"}:
            self._resolve(candidate, timestamp)
            return None
        if candidate.state == AccidentState.CONFIRMED:
            if self._aftermath(record, candidate.event_type, config):
                candidate.last_support = timestamp
            return None
        if candidate.state == AccidentState.NORMAL:
            if self._approaching(record, candidate.event_type, config):
                candidate.approach = record
                candidate.last_support = timestamp
                candidate.transition(AccidentState.SUSPICIOUS, timestamp)
            return None
        if candidate.state == AccidentState.SUSPICIOUS:
            if (timestamp-candidate.approach.timestamp).total_seconds() > config.approach_window_seconds:
                self._resolve(candidate, timestamp)
                return None
            if self._impact(record, candidate.event_type, config):
                candidate.impact = record
                candidate.support_frames = 1
                candidate.last_support = timestamp
                candidate.evidence.append(record)
                candidate.transition(AccidentState.CANDIDATE, timestamp)
            elif self._approaching(record, candidate.event_type, config):
                candidate.approach = record
                candidate.last_support = timestamp
            return None
        if (timestamp-candidate.impact.timestamp).total_seconds() > config.candidate_timeout_seconds:
            self._resolve(candidate, timestamp)
            return None
        if not self._aftermath(record, candidate.event_type, config):
            # Support must be consecutive; track presence alone never counts.
            candidate.support_frames = 0
            candidate.evidence.clear()
            return None
        candidate.support_frames += 1
        candidate.evidence.append(record)
        candidate.last_support = timestamp
        elapsed = (timestamp-candidate.impact.timestamp).total_seconds()
        if candidate.support_frames < config.persistence_frames or elapsed < config.minimum_confirmation_seconds:
            return None
        score = min(1.0, .35 + .35 * min(1.0, candidate.impact.deceleration/config.impact_deceleration)
                    + .20 * float(record.stationary or record.fallen) + .10*candidate.impact.visual_impact)
        if score < config.confidence_threshold:
            return None
        candidate.transition(AccidentState.CONFIRMED, timestamp)
        candidate.confirmed_at, candidate.confirmed_sequence = timestamp, record.source_frame_index
        # Pin approach/impact even when the tail rolls over.
        evidence = {item.source_frame_index: item for item in
                    (candidate.approach, candidate.impact, *list(candidate.evidence)[-(config.max_evidence_frames-2):])}
        features = tuple(sorted(evidence.values(), key=lambda item: item.timestamp))
        return AccidentEvent(candidate.event_type, round(score, 4), record.track_ids,
                             {"approach": 1.0, "impact": min(1.0, candidate.impact.deceleration/config.impact_deceleration),
                              "temporal_persistence": 1.0, "stationary_aftermath": float(record.stationary),
                              "visual_impact": candidate.impact.visual_impact},
                             tuple(item.source_frame_index for item in features),
                             (timestamp-candidate.approach.timestamp).total_seconds(), True,
                             "approach, impact dynamics and sustained aftermath",
                             record.camera_id, timestamp, candidate.approach.timestamp,
                             candidate.impact.timestamp, features)
