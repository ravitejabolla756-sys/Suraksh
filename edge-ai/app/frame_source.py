"""Shared frame-source primitives for recorded, webcam, and RTSP inputs.

Sources expose timestamped packets and never retain an unbounded backlog. The
latest-frame buffer is intentionally small so a live source remains realtime
when inference is slower than capture.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import time
from typing import Any

import cv2
from .perception.contracts import FramePacket
    processing_timestamp: float | None = None


class FrameSource(ABC):
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.sequence_number = 0

    @abstractmethod
    def read(self) -> FramePacket | None:
        raise NotImplementedError


class OpenCVFrameSource(FrameSource):
    def __init__(self, camera_id: str, source: str | int):
        super().__init__(camera_id)
        self.source = source
        self.capture = cv2.VideoCapture(source)
        self.source_fps = float(self.capture.get(cv2.CAP_PROP_FPS) or 0.0)

    def read(self) -> FramePacket | None:
        ok, frame = self.capture.read()
        if not ok:
            return None
        frame_index = int(self.capture.get(cv2.CAP_PROP_POS_FRAMES) or 1) - 1
        position_ms = float(self.capture.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
        source_timestamp = position_ms / 1000 if position_ms > 0 else (
            frame_index / self.source_fps if self.source_fps > 0 else None)
        captured_at = time.monotonic()
        packet = FramePacket(frame, max(0, frame_index), source_timestamp or 0.0,
                             self.source_fps or 1.0, captured_at, self.camera_id,
                             None, self.sequence_number)
        self.sequence_number += 1
        return packet

    def close(self) -> None:
        self.capture.release()


class RecordedFileSource(OpenCVFrameSource):
    """OpenCV-backed MP4 source; caller controls whether it loops."""


class WebcamSource(OpenCVFrameSource):
    def __init__(self, camera_id: str, device_index: int = 0):
        super().__init__(camera_id, device_index)


class RTSPSource(OpenCVFrameSource):
    """RTSP credentials stay in the edge process and are never serialized."""
