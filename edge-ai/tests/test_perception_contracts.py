import numpy as np
import pytest

from app.perception.contracts import Detection, DetectorInput, FramePacket
from app.perception.runtime import PerCameraFrameQueue, PipelineMode


def frame(index=3, camera="cam-1"):
    return DetectorInput(np.zeros((80, 120, 3), dtype=np.uint8), index, index / 30,
                         30, 100.0, camera)


def test_detector_contract_preserves_source_timing():
    item = frame()
    detection = Detection(0, "person", .8, (1, 2, 10, 30),
                          item.source_frame_index, item.source_timestamp)
    assert item.source_timestamp == pytest.approx(.1)
    assert detection.source_frame_index == 3
    assert detection.source_timestamp == pytest.approx(.1)


def test_realtime_queue_is_bounded_and_keeps_newest_frame():
    queue = PerCameraFrameQueue("cam-1", PipelineMode.REALTIME, capacity=2)
    for index in range(3):
        queue.submit(frame(index))
    assert queue.stats.stale_dropped == 1
    assert queue.pop().source_frame_index == 1
    assert queue.pop().source_frame_index == 2


def test_evaluation_queue_applies_backpressure_instead_of_dropping():
    queue = PerCameraFrameQueue("cam-1", PipelineMode.EVALUATION, capacity=1)
    queue.submit(frame(0))
    with pytest.raises(OverflowError):
        queue.submit(frame(1))
    assert queue.stats.stale_dropped == 0


def test_per_camera_queue_rejects_another_camera():
    queue = PerCameraFrameQueue("cam-1", PipelineMode.REALTIME)
    with pytest.raises(ValueError):
        queue.submit(frame(camera="cam-2"))


def test_frame_packet_assigns_processing_time_without_changing_source_time():
    item = frame(100)
    processed = item.for_processing(101.25)
    assert isinstance(processed, FramePacket)
    assert processed.source_frame_index == 100
    assert processed.source_timestamp == pytest.approx(100 / 30)
    assert processed.capture_timestamp == 100.0
    assert processed.processing_timestamp == pytest.approx(101.25)


def test_queue_marks_processing_time_and_preserves_source_gap():
    queue = PerCameraFrameQueue("cam-1", PipelineMode.EVALUATION, capacity=3)
    queue.submit(frame(100))
    queue.submit(frame(105))
    first, second = queue.pop(), queue.pop()
    assert first.processing_timestamp is not None
    assert second.processing_timestamp is not None
    assert second.source_frame_index - first.source_frame_index == 5
    assert second.source_timestamp - first.source_timestamp == pytest.approx(5 / 30)


def test_queue_rejects_backward_source_order():
    queue = PerCameraFrameQueue("cam-1", PipelineMode.EVALUATION, capacity=2)
    queue.submit(frame(2))
    with pytest.raises(ValueError):
        queue.submit(frame(1))
