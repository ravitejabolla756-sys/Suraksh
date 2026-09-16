"""Bounded per-camera execution policies for live and evaluation modes."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from threading import Lock
import time

from .contracts import DetectorInput


class PipelineMode(str, Enum):
    REALTIME = "realtime"
    EVALUATION = "evaluation"


@dataclass(frozen=True, slots=True)
class QueueStats:
    accepted: int
    stale_dropped: int
    pending: int


class PerCameraFrameQueue:
    """Small thread-safe queue; realtime keeps newest, evaluation rejects overflow."""

    def __init__(self, camera_id: str, mode: PipelineMode, capacity: int = 2):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.camera_id = camera_id
        self.mode = mode
        self.capacity = capacity
        self._frames: deque[DetectorInput] = deque()
        self._accepted = self._dropped = 0
        self._last_submitted_index: int | None = None
        self._last_popped_index: int | None = None
        self._lock = Lock()

    def submit(self, frame: DetectorInput) -> None:
        if frame.camera_id != self.camera_id:
            raise ValueError("a per-camera queue cannot accept another camera")
        with self._lock:
            if self._last_submitted_index is not None and frame.source_frame_index <= self._last_submitted_index:
                raise ValueError("source frame numbers must be strictly increasing")
            if len(self._frames) >= self.capacity:
                if self.mode == PipelineMode.EVALUATION:
                    raise OverflowError("evaluation mode never drops frames; consumer must apply backpressure")
                self._frames.popleft()
                self._dropped += 1
            self._frames.append(frame)
            self._last_submitted_index = frame.source_frame_index
            self._accepted += 1

    def pop(self) -> DetectorInput | None:
        with self._lock:
            frame = self._frames.popleft() if self._frames else None
            if frame is None:
                return None
            if self._last_popped_index is not None and frame.source_frame_index <= self._last_popped_index:
                raise ValueError("source frame numbers must be strictly increasing")
            self._last_popped_index = frame.source_frame_index
            return frame.for_processing(time.perf_counter())

    @property
    def stats(self) -> QueueStats:
        with self._lock:
            return QueueStats(self._accepted, self._dropped, len(self._frames))
