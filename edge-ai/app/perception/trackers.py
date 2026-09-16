"""Detector-neutral ByteTrack and BoT-SORT benchmark adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from .contracts import Detection, DetectorInput
from .reid import ReIDConfig


class TrackState(str, Enum):
    NEW = "NEW"
    TENTATIVE = "TENTATIVE"
    CONFIRMED = "CONFIRMED"
    LOST = "LOST"
    REACTIVATED = "REACTIVATED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class Track:
    track_id: int
    class_id: int
    class_name: str
    bbox_xyxy: tuple[float, float, float, float]
    confidence: float
    state: TrackState
    source_frame_index: int
    source_timestamp: float
    age: int
    hits: int
    missed_frames: int
    velocity: tuple[float, float]
    predicted: bool = False


class Tracker(ABC):
    """Detector-independent, camera-local tracking contract."""

    @abstractmethod
    def update(self, frame: DetectorInput, detections: tuple[Detection, ...]) -> "TrackerFrameResult":
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ByteTrackConfig:
    track_high_threshold: float = .5
    track_low_threshold: float = .1
    new_track_threshold: float = .6
    match_threshold: float = .8
    track_buffer: int = 30
    minimum_hits: int = 3
    maximum_age: int = 30

    def __post_init__(self) -> None:
        if not (0 <= self.track_low_threshold <= self.track_high_threshold <= 1):
            raise ValueError("ByteTrack confidence thresholds are invalid")
        if not (0 <= self.new_track_threshold <= 1 and 0 <= self.match_threshold <= 1):
            raise ValueError("ByteTrack thresholds must be between zero and one")
        if self.track_buffer < 1 or self.maximum_age < 1 or self.minimum_hits < 1:
            raise ValueError("ByteTrack lifecycle values must be positive")


@dataclass(frozen=True, slots=True)
class BoTSORTConfig:
    enabled: bool = True
    match_threshold: float = .8
    track_buffer: int = 30
    camera_motion_compensation: bool = False
    reid_enabled: bool = False
    reid_weight: float = .0
    reid_distance_threshold: float = .3
    embedding_cache_size: int = 128

    def __post_init__(self) -> None:
        if not 0 <= self.match_threshold <= 1:
            raise ValueError("BoT-SORT match_threshold must be between zero and one")
        if self.track_buffer < 1 or not 0 <= self.reid_weight <= 1:
            raise ValueError("BoT-SORT configuration values are invalid")
        if self.reid_enabled and self.reid_weight <= 0:
            raise ValueError("reid_weight must be positive when ReID is enabled")
        ReIDConfig(self.reid_enabled, self.reid_weight, self.reid_distance_threshold,
                   self.embedding_cache_size)


@dataclass(frozen=True, slots=True)
class TrackedDetection:
    detection: Detection
    track_id: int | None
    state: str


@dataclass(frozen=True, slots=True)
class TrackerTelemetry:
    detections: int
    matched_tracks: int
    unmatched_detections: int
    unmatched_tracks: int
    new_tracks: int
    reactivated_tracks: int
    expired_tracks: int
    predicted_tracks: int


@dataclass(frozen=True, slots=True)
class TrackerFrameResult:
    tracker_id: str
    frame: DetectorInput
    tracks: tuple[TrackedDetection, ...]
    telemetry: TrackerTelemetry


class UltralyticsTrackerAdapter(Tracker):
    """Run one upstream tracker per class to prevent cross-class ID switches.

    Missing source frames advance the Kalman/lost-track state with empty
    updates. Therefore motion age follows source-frame time, not CPU time.
    """

    def __init__(self, kind: str, source_fps: float, track_buffer: int = 45,
                 config: ByteTrackConfig | None = None, tracker_options: dict[str, Any] | None = None):
        if kind not in {"bytetrack", "botsort"}:
            raise ValueError("kind must be bytetrack or botsort")
        self.kind = kind
        self.tracker_id = "ByteTrack" if kind == "bytetrack" else "BoT-SORT"
        self.source_fps = source_fps
        self.config = config or ByteTrackConfig(track_buffer=track_buffer, maximum_age=track_buffer)
        self.tracker_options = tracker_options or {}
        self.track_buffer = self.config.track_buffer
        self._trackers: dict[int, Any] = {}
        self._last_frame_index: int | None = None
        self._last_source_timestamp: float | None = None
        self._local_ids: dict[tuple[int, int], int] = {}
        self._next_local_id = 1

    def _tracker(self, class_id: int):
        if class_id in self._trackers:
            return self._trackers[class_id]
        from ultralytics.trackers.bot_sort import BOTSORT
        from ultralytics.trackers.byte_tracker import BYTETracker
        from ultralytics.utils import IterableSimpleNamespace, YAML
        from ultralytics.utils.checks import check_yaml
        config = YAML.load(check_yaml(f"{self.kind}.yaml"))
        config.update(track_high_thresh=self.config.track_high_threshold,
                      track_low_thresh=self.config.track_low_threshold,
                      new_track_thresh=self.config.new_track_threshold,
                      match_thresh=self.config.match_threshold,
                      track_buffer=self.config.track_buffer,
                      with_reid=False, gmc_method="none")
        config.update(self.tracker_options)
        tracker_class = BYTETracker if self.kind == "bytetrack" else BOTSORT
        arguments = IterableSimpleNamespace(**config)
        try:
            tracker = tracker_class(arguments, frame_rate=round(self.source_fps))
        except TypeError as exc:
            if "frame_rate" not in str(exc):
                raise
            # Ultralytics >=8.4 derives buffer age directly from config.
            tracker = tracker_class(arguments)
        self._trackers[class_id] = tracker
        return tracker

    @staticmethod
    def _boxes(detections: list[Detection], shape: tuple[int, int]):
        from ultralytics.engine.results import Boxes
        rows = np.asarray([[*item.bbox_xyxy, item.confidence, item.class_id]
                           for item in detections], dtype=np.float32)
        if not len(rows):
            rows = np.empty((0, 6), dtype=np.float32)
        return Boxes(rows, shape)

    @staticmethod
    def _ids(items: list[Any]) -> set[int]:
        return {int(item.track_id) for item in items}

    def _advance_missing_frames(self, frame: DetectorInput) -> None:
        if self._last_frame_index is None:
            return
        index_gap = frame.source_frame_index - self._last_frame_index - 1
        time_gap = 0
        if self._last_source_timestamp is not None:
            time_gap = round((frame.source_timestamp - self._last_source_timestamp) * self.source_fps) - 1
        missing = max(0, index_gap, time_gap)
        empty = self._boxes([], frame.frame.shape[:2])
        for _ in range(min(missing, self.track_buffer + 1)):
            for tracker in self._trackers.values():
                tracker.update(empty, frame.frame)

    def update(self, frame: DetectorInput, detections: tuple[Detection, ...]) -> TrackerFrameResult:
        if self._last_frame_index is not None and frame.source_frame_index <= self._last_frame_index:
            raise ValueError("frames must be strictly ordered within a replay epoch")
        if self._last_source_timestamp is not None and frame.source_timestamp <= self._last_source_timestamp:
            raise ValueError("source timestamps must be strictly ordered within a replay epoch")
        if any(item.source_frame_index != frame.source_frame_index or
               abs(item.source_timestamp - frame.source_timestamp) > 1e-6 for item in detections):
            raise ValueError("detections must belong to the tracker input frame and source timestamp")
        self._advance_missing_frames(frame)
        output: list[TrackedDetection] = []
        matched = new = reactivated = expired = unmatched_tracks = 0
        grouped = {class_id: [item for item in detections if item.class_id == class_id]
                   for class_id in {item.class_id for item in detections} | set(self._trackers)}
        for class_id, class_detections in grouped.items():
            tracker = self._tracker(class_id)
            before_active = self._ids(tracker.tracked_stracks)
            before_lost = self._ids(tracker.lost_stracks)
            tracks = tracker.update(self._boxes(class_detections, frame.frame.shape[:2]), frame.frame)
            by_detection = {int(track[-1]): int(track[4]) for track in tracks}
            visible = set(by_detection.values())
            after_lost = self._ids(tracker.lost_stracks)
            new += len(visible - before_active - before_lost)
            reactivated += len(visible & before_lost)
            expired += len(before_lost - after_lost - visible)
            unmatched_tracks += len(before_active - visible)
            for index, detection in enumerate(class_detections):
                upstream_id = by_detection.get(index)
                local_id = None
                if upstream_id is not None:
                    key = (class_id, upstream_id)
                    if key not in self._local_ids:
                        self._local_ids[key] = self._next_local_id
                        self._next_local_id += 1
                    local_id = self._local_ids[key]
                output.append(TrackedDetection(detection, local_id,
                                               "confirmed" if local_id is not None else "unmatched"))
                matched += int(local_id is not None)
        self._last_frame_index = frame.source_frame_index
        self._last_source_timestamp = frame.source_timestamp
        telemetry = TrackerTelemetry(len(detections), matched, len(detections) - matched,
                                     unmatched_tracks, new, reactivated, expired,
                                     sum(len(tracker.lost_stracks) for tracker in self._trackers.values()))
        return TrackerFrameResult(self.tracker_id, frame, tuple(output), telemetry)


class ByteTrackTracker(UltralyticsTrackerAdapter):
    """Interchangeable ByteTrack implementation; IDs are allocated at Edge."""
    def __init__(self, source_fps: float, track_buffer: int = 45,
                 config: ByteTrackConfig | None = None):
        super().__init__("bytetrack", source_fps, track_buffer, config)


class BoTSORTTracker(UltralyticsTrackerAdapter):
    """Interchangeable BoT-SORT implementation; IDs are camera-local."""
    def __init__(self, source_fps: float, track_buffer: int = 45,
                 config: BoTSORTConfig | None = None):
        self.bot_sort_config = config or BoTSORTConfig(track_buffer=track_buffer)
        if not self.bot_sort_config.enabled:
            raise ValueError("BoT-SORT tracker is disabled by configuration")
        super().__init__("botsort", source_fps, self.bot_sort_config.track_buffer,
                         tracker_options={
                             "with_reid": self.bot_sort_config.reid_enabled,
                             "gmc_method": "orb" if self.bot_sort_config.camera_motion_compensation else "none",
                             "appearance_thresh": 1 - self.bot_sort_config.reid_distance_threshold,
                             "model": "auto" if self.bot_sort_config.reid_enabled else "auto",
                         })

    def _tracker(self, class_id: int):
        tracker = super()._tracker(class_id)
        return tracker


class LegacyIoUTracker(Tracker):
    """Compatibility name for the pre-abstraction IoU tracker.

    The legacy backend implementation remains the production viewer path;
    this adapter intentionally is not selected by default.
    """
    def __init__(self, source_fps: float, track_buffer: int = 45):
        super().__init__()
        self._delegate = ByteTrackTracker(source_fps, track_buffer)

    def update(self, frame: DetectorInput, detections: tuple[Detection, ...]) -> TrackerFrameResult:
        return self._delegate.update(frame, detections)
