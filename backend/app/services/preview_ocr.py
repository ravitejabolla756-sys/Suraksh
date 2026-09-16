"""One pending OCR crop per camera; inference never waits for OCR."""
from collections import deque
import threading
import time
from typing import Any

import numpy as np

from app.services.plate_ocr import PlateOCR


class PreviewOCR:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.epoch = 0
        self.pending = None
        self.history: dict[int, deque] = {}
        self.results: dict[int, dict[str, Any]] = {}
        self.error: str | None = None
        self.attempts = 0

    def reset(self, epoch: int) -> None:
        with self.lock:
            self.epoch = epoch
            self.pending = None
            self.history.clear()
            self.results.clear()

    def submit(self, crop: np.ndarray, track_id: int, frame: int, epoch: int) -> None:
        with self.lock:
            if epoch != self.epoch:
                return
            self.pending = (crop.copy(), track_id, frame, epoch, time.monotonic())
            self.ready.set()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            now = time.monotonic()
            return {"plates": [dict(r) for r in self.results.values() if now - r["at"] < 5],
                    "ocr_attempts": self.attempts, "ocr_error": self.error}

    def run(self, stop: threading.Event) -> None:
        reader = PlateOCR()
        while not stop.is_set():
            if not self.ready.wait(0.1):
                continue
            with self.lock:
                job, self.pending = self.pending, None
                self.ready.clear()
            if job is None:
                continue
            crop, track_id, frame, epoch, captured = job
            if time.monotonic() - captured > 2:
                continue
            try:
                result = reader.read(crop)
                error = None
            except Exception as exc:
                result, error = None, type(exc).__name__
            with self.lock:
                self.attempts += 1
                self.error = error
                if epoch != self.epoch or result is None:
                    continue
                history = self.history.setdefault(track_id, deque(maxlen=5))
                history.append((frame, result))
                matching = [r for f, r in history if r["text"] == result["text"]]
                # Agreement must come from separate frames of the same track.
                frames = {f for f, r in history if r["text"] == result["text"]}
                if len(frames) >= 2:
                    self.results[track_id] = {"track_id": track_id, "text": result["text"],
                        "confidence": min(r["confidence"] for r in matching),
                        "last_seen_frame": frame, "at": time.monotonic()}
                if len(self.history) > 128:
                    oldest = next(iter(self.history))
                    self.history.pop(oldest)
                    self.results.pop(oldest, None)
