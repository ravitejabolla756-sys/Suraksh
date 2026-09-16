"""Small, timestamp-aware multi-object tracker for the recorded viewer.

The viewer receives detections at a lower rate than the source video.  This
tracker deliberately keeps source time in the association loop, performs
high/low confidence association, and exposes lifecycle telemetry so detector
misses can be separated from association misses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from math import hypot
from threading import Lock
from typing import Any


_IDS = count(1)
_ID_LOCK = Lock()


@dataclass(frozen=True)
class TrackerConfig:
    high_confidence: float = 0.35
    low_confidence: float = 0.15
    new_track_confidence: float = 0.45
    iou_threshold: float = 0.05
    max_lost_seconds: float = 1.5
    min_hits: int = 2
    history_size: int = 64


@dataclass
class _Track:
    track_id: int
    class_id: int
    box: list[float]
    confidence: float
    timestamp: float
    hits: int = 1
    missed_seconds: float = 0.0
    velocity: tuple[float, float] = (0.0, 0.0)
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def confirmed(self) -> bool:
        return self.hits >= 2

    def predicted_box(self, timestamp: float) -> list[float]:
        dt = max(0.0, min(timestamp - self.timestamp, 2.0))
        dx, dy = self.velocity[0] * dt, self.velocity[1] * dt
        return [self.box[0] + dx, self.box[1] + dy,
                self.box[2] + dx, self.box[3] + dy]


def _center(box: list[float]) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _iou(first: list[float], second: list[float]) -> float:
    x1, y1 = max(first[0], second[0]), max(first[1], second[1])
    x2, y2 = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    return intersection / max(first_area + second_area - intersection, 1e-6)


class TimestampAwareTracker:
    """Per-camera, bounded tracker with explicit lifecycle and telemetry."""

    def __init__(self, config: TrackerConfig | None = None) -> None:
        self.config = config or TrackerConfig()
        self._tracks: dict[int, _Track] = {}
        self._last_timestamp: float | None = None
        self._telemetry: dict[str, int] = {}

    @staticmethod
    def _new_id() -> int:
        with _ID_LOCK:
            return next(_IDS)

    def reset(self) -> None:
        self._tracks.clear()
        self._last_timestamp = None
        self._telemetry = {}

    def _pair_score(self, track: _Track, detection: dict[str, Any], timestamp: float) -> float | None:
        if track.class_id != int(detection["class_id"]):
            return None
        predicted = track.predicted_box(timestamp)
        box = [float(value) for value in detection["box"]]
        iou = _iou(predicted, box)
        px, py = _center(predicted)
        dx, dy = _center(box)
        distance = hypot(px - dx, py - dy)
        width = max(predicted[2] - predicted[0], box[2] - box[0], 1.0)
        height = max(predicted[3] - predicted[1], box[3] - box[1], 1.0)
        gate = max(0.75 * hypot(width, height), 32.0)
        if iou < self.config.iou_threshold and distance > gate:
            return None
        distance_score = max(0.0, 1.0 - distance / gate)
        return 0.65 * iou + 0.35 * distance_score

    def _associate(self, track_ids: list[int], detections: list[dict[str, Any]],
                   timestamp: float, allowed: set[int]) -> tuple[dict[int, int], set[int], set[int]]:
        candidates: list[tuple[float, int, int]] = []
        for track_id in track_ids:
            if track_id not in allowed:
                continue
            for index, detection in enumerate(detections):
                score = self._pair_score(self._tracks[track_id], detection, timestamp)
                if score is not None:
                    candidates.append((score, track_id, index))
        candidates.sort(reverse=True)
        matches: dict[int, int] = {}
        used_tracks: set[int] = set()
        used_detections: set[int] = set()
        for _, track_id, index in candidates:
            if track_id in used_tracks or index in used_detections:
                continue
            used_tracks.add(track_id)
            used_detections.add(index)
            matches[index] = track_id
        return matches, used_tracks, used_detections

    def _update_track(self, track: _Track, detection: dict[str, Any], timestamp: float) -> None:
        previous = _center(track.box)
        current_box = [float(value) for value in detection["box"]]
        current = _center(current_box)
        dt = max(timestamp - track.timestamp, 1e-3)
        measured = ((current[0] - previous[0]) / dt, (current[1] - previous[1]) / dt)
        track.velocity = (0.65 * track.velocity[0] + 0.35 * measured[0],
                          0.65 * track.velocity[1] + 0.35 * measured[1])
        track.box = current_box
        track.confidence = float(detection["confidence"])
        track.timestamp = timestamp
        track.hits += 1
        track.missed_seconds = 0.0
        track.history.append({"timestamp": timestamp, "box": list(current_box)})
        del track.history[:-self.config.history_size]

    def _expire(self, timestamp: float, matched: set[int]) -> int:
        deleted = 0
        for track_id, track in list(self._tracks.items()):
            if track_id in matched:
                continue
            dt = max(0.0, timestamp - track.timestamp)
            track.missed_seconds = max(track.missed_seconds, dt)
            if track.missed_seconds > self.config.max_lost_seconds:
                del self._tracks[track_id]
                deleted += 1
        return deleted

    def update(self, detections: list[dict[str, Any]], timestamp: float) -> dict[str, Any]:
        if self._last_timestamp is not None:
            timestamp = max(timestamp, self._last_timestamp)
        self._last_timestamp = timestamp
        high = [d for d in detections if float(d["confidence"]) >= self.config.high_confidence]
        low = [d for d in detections if self.config.low_confidence <= float(d["confidence"]) < self.config.high_confidence]
        track_ids = list(self._tracks)
        matched, matched_tracks, matched_high = self._associate(track_ids, high, timestamp, set(track_ids))
        low_matches, low_tracks, matched_low = self._associate(
            [track_id for track_id in track_ids if track_id not in matched_tracks],
            low, timestamp, set(track_ids) - matched_tracks)
        matches = {**matched, **{len(high) + index: track_id for index, track_id in low_matches.items()}}
        all_detections = high + low
        for index, track_id in matches.items():
            self._update_track(self._tracks[track_id], all_detections[index], timestamp)
        matched_tracks |= low_tracks
        created = 0
        for index, detection in enumerate(all_detections):
            if index in matches or float(detection["confidence"]) < self.config.new_track_confidence:
                continue
            track_id = self._new_id()
            box = [float(value) for value in detection["box"]]
            track = _Track(track_id, int(detection["class_id"]), box,
                           float(detection["confidence"]), timestamp,
                           history=[{"timestamp": timestamp, "box": list(box)}])
            self._tracks[track_id] = track
            matches[index] = track_id
            matched_tracks.add(track_id)
            created += 1
        deleted = self._expire(timestamp, matched_tracks)
        output = []
        for index, detection in enumerate(all_detections):
            track_id = matches.get(index)
            item = dict(detection)
            track = self._tracks.get(track_id)
            item["id"] = track_id if track is not None and track.hits >= self.config.min_hits else None
            output.append(item)
        self._telemetry = {
            "detector_high": len(high), "detector_low": len(low),
            "matched_high": len(matched_high), "matched_low": len(matched_low),
            "unmatched_high": len(high) - len(matched_high),
            "unmatched_low": len(low) - len(matched_low),
            "created": created, "active": len(self._tracks), "deleted": deleted,
            "visible": sum(item["id"] is not None for item in output),
        }
        return {"detections": output, "telemetry": dict(self._telemetry)}
