import asyncio

import pytest

from app.safety import (
    CameraSafetyRuntime,
    EventFamily,
    FrameInput,
    FrameSafetyModel,
    ModelStatus,
    SafetyDetection,
    SafetyPerceptionResult,
    TemporalSafetyModel,
    utc_now,
)


class FakeFrameModel(FrameSafetyModel):
    event_family = EventFamily.FIRE
    model_id = "fire-test"
    model_version = "0.1"

    async def infer(self, request):
        return SafetyPerceptionResult(
            EventFamily.FIRE, request.frame.camera_id, self.model_id, self.model_version,
            (SafetyDetection("flame", 0.9),), 0.9, (), None, 1.2, ModelStatus.READY,
        )


class FakeTemporalModel(TemporalSafetyModel):
    event_family = EventFamily.ACCIDENT
    model_id = "accident-test"
    model_version = "0.1"

    async def infer(self, request):
        assert request.temporal_window is not None
        return SafetyPerceptionResult(
            EventFamily.ACCIDENT, request.frame.camera_id, self.model_id, self.model_version,
            (), 0.0, (), request.temporal_window, 2.0, ModelStatus.READY,
        )


class FailingModel(FakeFrameModel):
    model_id = "failing-test"

    async def infer(self, request):
        raise RuntimeError("weights unavailable")


def frame(camera_id="cam-1", sequence=1):
    return FrameInput(data=b"frame", timestamp=utc_now(), camera_id=camera_id, sequence=sequence)


def test_frame_model_uses_common_contract_and_delivers_result():
    async def run():
        results = []
        runtime = CameraSafetyRuntime(sink=results.append)
        runtime.register("cam-1", FakeFrameModel())
        assert runtime.submit("cam-1", "fire-test", frame()) is True
        await asyncio.sleep(0.01)
        await runtime.stop()
        assert results[0].event_family is EventFamily.FIRE
        assert results[0].detections[0].label == "flame"

    asyncio.run(run())


def test_temporal_model_receives_bounded_same_camera_window():
    async def run():
        results = []
        runtime = CameraSafetyRuntime(window_size=2, sink=results.append)
        runtime.register("cam-1", FakeTemporalModel())
        runtime.submit("cam-1", "accident-test", frame(sequence=1))
        runtime.submit("cam-1", "accident-test", frame(sequence=2))
        await asyncio.sleep(0.02)
        await runtime.stop()
        assert results
        assert len(results[-1].temporal_window.frames) <= 2
        assert all(item.camera_id == "cam-1" for item in results[-1].temporal_window.frames)

    asyncio.run(run())


def test_queue_is_bounded_and_drops_old_pending_frames():
    async def run():
        runtime = CameraSafetyRuntime(max_queue=1)
        runtime.register("cam-1", FakeFrameModel())
        runtime.submit("cam-1", "fire-test", frame(sequence=1))
        accepted = runtime.submit("cam-1", "fire-test", frame(sequence=2))
        assert accepted is False
        assert runtime.stats("cam-1", "fire-test").dropped == 1
        await runtime.stop()

    asyncio.run(run())


def test_model_failure_is_isolated_and_reported_as_failed_result():
    async def run():
        results = []
        runtime = CameraSafetyRuntime(sink=results.append)
        runtime.register("cam-1", FailingModel())
        runtime.submit("cam-1", "failing-test", frame())
        await asyncio.sleep(0.01)
        await runtime.stop()
        assert results[0].model_status is ModelStatus.FAILED
        assert "weights unavailable" in results[0].error

    asyncio.run(run())


def test_contract_rejects_invalid_confidence_and_mixed_temporal_cameras():
    with pytest.raises(ValueError):
        SafetyDetection("smoke", 1.1)
    first = frame("cam-1")
    second = frame("cam-2")
    from app.safety import TemporalWindow
    with pytest.raises(ValueError):
        TemporalWindow((first, second), first.timestamp, second.timestamp)
