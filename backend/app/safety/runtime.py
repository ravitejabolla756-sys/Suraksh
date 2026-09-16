"""Bounded, per-camera async execution for safety models."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from .contracts import FrameInput, InferenceRequest, ModelStatus, SafetyPerceptionResult, TemporalWindow, utc_now
from .models import SafetyModel

ResultSink = Callable[[SafetyPerceptionResult], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class CameraRuntimeStats:
    camera_id: str
    accepted: int
    dropped: int
    failed: int
    queue_size: int
    model_status: ModelStatus


class _CameraWorker:
    def __init__(self, camera_id: str, model: SafetyModel, max_queue: int, window_size: int, sink: ResultSink | None):
        if max_queue < 1 or window_size < 1 or window_size > 64:
            raise ValueError("max_queue must be positive and window_size must be between 1 and 64")
        self.camera_id, self.model, self.window_size, self.sink = camera_id, model, window_size, sink
        self.queue: asyncio.Queue[FrameInput] = asyncio.Queue(maxsize=max_queue)
        self.history: list[FrameInput] = []
        self.task: asyncio.Task[None] | None = None
        self.accepted = self.dropped = self.failed = 0
        self.status = ModelStatus.READY

    def start(self) -> None:
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._run(), name=f"safety-{self.camera_id}")

    async def stop(self) -> None:
        if self.task is None:
            return
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        self.task = None

    def submit(self, frame: FrameInput) -> bool:
        if frame.camera_id != self.camera_id:
            raise ValueError("frame camera_id does not match runtime camera")
        try:
            self.queue.put_nowait(frame)
            self.accepted += 1
            return True
        except asyncio.QueueFull:
            # Drop the oldest pending frame to preserve bounded memory and freshness.
            self.queue.get_nowait()
            self.queue.put_nowait(frame)
            self.dropped += 1
            return False

    async def _run(self) -> None:
        while True:
            frame = await self.queue.get()
            self.history.append(frame)
            self.history = self.history[-self.window_size:]
            window = TemporalWindow(tuple(self.history), self.history[0].timestamp, frame.timestamp) if self.model.is_temporal else None
            request = InferenceRequest(frame, self.model.model_id, self.model.model_version, window)
            try:
                result = await self.model.infer(request)
                self.status = result.model_status
                if self.sink is not None:
                    delivered = self.sink(result)
                    if delivered is not None:
                        await delivered
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # Model failures must not kill other camera workers.
                self.failed += 1
                self.status = ModelStatus.FAILED
                failure = SafetyPerceptionResult(
                    event_family=self.model.event_family, camera_id=self.camera_id,
                    model_id=self.model.model_id, model_version=self.model.model_version,
                    detections=(), confidence=0.0, evidence_frames=(), temporal_window=window,
                    inference_latency_ms=0.0, model_status=ModelStatus.FAILED,
                    processed_at=utc_now(), error=f"{type(exc).__name__}: {exc}",
                )
                if self.sink is not None:
                    delivered = self.sink(failure)
                    if delivered is not None:
                        await delivered


class CameraSafetyRuntime:
    """Registry of independent bounded workers, one worker per camera/model pair."""

    def __init__(self, max_queue: int = 2, window_size: int = 16, sink: ResultSink | None = None):
        self.max_queue, self.window_size, self.sink = max_queue, window_size, sink
        self._workers: dict[tuple[str, str], _CameraWorker] = {}

    def register(self, camera_id: str, model: SafetyModel) -> None:
        key = (camera_id, model.model_id)
        if key in self._workers:
            raise ValueError(f"model {model.model_id} is already registered for camera {camera_id}")
        self._workers[key] = _CameraWorker(camera_id, model, self.max_queue, self.window_size, self.sink)

    def submit(self, camera_id: str, model_id: str, frame: FrameInput) -> bool:
        worker = self._workers[(camera_id, model_id)]
        worker.start()
        return worker.submit(frame)

    async def stop(self) -> None:
        await asyncio.gather(*(worker.stop() for worker in self._workers.values()))

    def stats(self, camera_id: str, model_id: str) -> CameraRuntimeStats:
        worker = self._workers[(camera_id, model_id)]
        return CameraRuntimeStats(camera_id, worker.accepted, worker.dropped, worker.failed,
                                  worker.queue.qsize(), worker.status)
