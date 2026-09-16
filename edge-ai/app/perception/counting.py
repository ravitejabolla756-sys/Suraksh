"""Track-identity counting primitives with hysteresis and debounce."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import copysign
from typing import Iterable


class Direction(str, Enum):
    A_TO_B = "A_TO_B"
    B_TO_A = "B_TO_A"


@dataclass(frozen=True, slots=True)
class TrackPoint:
    track_id: int
    class_name: str
    x: float
    y: float
    source_timestamp: float


def _side(point: TrackPoint, line: tuple[tuple[float, float], tuple[float, float]]) -> float:
    (x1, y1), (x2, y2) = line
    return (x2 - x1) * (point.y - y1) - (y2 - y1) * (point.x - x1)


class LineCrossingCounter:
    """Count each stable track once per direction after a deadband crossing."""

    def __init__(self, line, deadband: float = 4.0, debounce_seconds: float = 1.0):
        if deadband < 0 or debounce_seconds < 0:
            raise ValueError("deadband and debounce must be non-negative")
        self.line = line
        self.deadband = deadband
        self.debounce_seconds = debounce_seconds
        self._state: dict[int, tuple[str, float, float]] = {}
        self.counts = {Direction.A_TO_B: 0, Direction.B_TO_A: 0}

    def update(self, point: TrackPoint) -> Direction | None:
        signed = _side(point, self.line)
        side = "A" if signed > self.deadband else "B" if signed < -self.deadband else "boundary"
        previous = self._state.get(point.track_id)
        if side == "boundary":
            return None
        self._state[point.track_id] = (side, point.source_timestamp,
                                       previous[2] if previous else -float("inf"))
        if previous is None or previous[0] == "boundary":
            return None
        if side == previous[0] or point.source_timestamp - previous[2] < self.debounce_seconds:
            return None
        direction = Direction.A_TO_B if previous[0] == "A" else Direction.B_TO_A
        self.counts[direction] += 1
        self._state[point.track_id] = (side, point.source_timestamp, point.source_timestamp)
        return direction

    def forget(self, track_id: int) -> None:
        self._state.pop(track_id, None)


@dataclass(frozen=True, slots=True)
class CountError:
    predicted: int
    actual: int
    absolute_error: int


def count_error(predicted: int, actual: int) -> CountError:
    return CountError(predicted, actual, abs(predicted - actual))
