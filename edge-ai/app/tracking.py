"""Anonymous YOLO track state and line-crossing analytics.

This module deliberately stores only anonymous track IDs, class labels,
centroids, and confidence. It never attempts person identification.
"""
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable


COCO_CLASSES = {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck"}


@dataclass
class TrackState:
    track_id: int
    object_class: str
    camera_id: str
    first_seen: datetime
    last_seen: datetime
    confidence: float
    centroids: deque = field(default_factory=lambda: deque(maxlen=32))
    crossed_lines: set[str] = field(default_factory=set)


class AnonymousTracker:
    """Accumulate stable YOLO track IDs for one camera analytics session."""

    def __init__(self, camera_id: str, line: tuple[tuple[float, float], tuple[float, float]] | None = None):
        self.camera_id = camera_id
        self.line = line
        self.tracks: dict[int, TrackState] = {}
        self.crossings: list[dict] = []

    def update(self, detections: Iterable[dict], timestamp: datetime | None = None) -> dict:
        now = timestamp or datetime.now(timezone.utc)
        visible = Counter()
        for detection in detections:
            track_id = int(detection["track_id"])
            label = str(detection["object_class"])
            centroid = tuple(float(value) for value in detection["centroid"])
            confidence = float(detection.get("confidence", 0.0))
            state = self.tracks.get(track_id)
            if state is None:
                state = TrackState(track_id, label, self.camera_id, now, now, confidence)
                self.tracks[track_id] = state
            state.last_seen = now
            state.confidence = max(state.confidence, confidence)
            state.centroids.append(centroid)
            visible[label] += 1
            self._maybe_cross(state, centroid, now)
        return self.snapshot(visible)

    def snapshot(self, visible: Counter | None = None) -> dict:
        visible = visible or Counter()
        unique = Counter(state.object_class for state in self.tracks.values())
        return {
            "camera_id": self.camera_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "visible": self._counts(visible),
            "unique_window": self._counts(unique),
            "crossings": list(self.crossings),
        }

    @staticmethod
    def _counts(counts: Counter) -> dict:
        people = int(counts.get("person", 0))
        cars = int(counts.get("car", 0))
        motorcycles = int(counts.get("motorcycle", 0))
        buses = int(counts.get("bus", 0))
        trucks = int(counts.get("truck", 0))
        return {"people": people, "vehicles": cars + motorcycles + buses + trucks,
                "cars": cars, "motorcycles": motorcycles, "buses": buses, "trucks": trucks}

    def _maybe_cross(self, state: TrackState, current: tuple[float, float], now: datetime) -> None:
        if self.line is None or len(state.centroids) < 2:
            return
        previous = state.centroids[-2]
        before = self._side(previous)
        after = self._side(current)
        if before == 0 or after == 0 or before == after:
            return
        direction = "A_TO_B" if before < after else "B_TO_A"
        key = f"{state.track_id}:{direction}"
        if key in state.crossed_lines:
            return
        state.crossed_lines.add(key)
        self.crossings.append({"class": state.object_class, "track_id": state.track_id,
                               "timestamp": now.isoformat(), "direction": direction,
                               "camera": self.camera_id})

    def _side(self, point: tuple[float, float]) -> float:
        (ax, ay), (bx, by) = self.line
        return (bx - ax) * (point[1] - ay) - (by - ay) * (point[0] - ax)


def result_detections(result) -> list[dict]:
    """Convert one Ultralytics track result into stable analytics records."""
    boxes = getattr(result, "boxes", None)
    if boxes is None or boxes.id is None:
        return []
    rows = []
    for box, track_id in zip(boxes, boxes.id.int().tolist()):
        class_id = int(box.cls[0])
        label = COCO_CLASSES.get(class_id)
        if label is None:
            continue
        x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
        rows.append({"track_id": track_id, "object_class": label,
                     "centroid": ((x1 + x2) / 2, (y1 + y2) / 2),
                     "confidence": float(box.conf[0])})
    return rows
