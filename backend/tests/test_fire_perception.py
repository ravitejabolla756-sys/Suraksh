import asyncio
import cv2
import numpy as np

from app.safety import FrameInput, InferenceRequest, TemporalWindow, utc_now
from app.safety.fire import (
    ExperimentalFireModel,
    FireCandidateDetector,
    FireTemporalConfig,
    FireTemporalVerifier,
    evaluate_binary_events,
)


def flame_frame(size=100, radius=12, shift=0):
    image = np.zeros((size, size, 3), dtype=np.uint8)
    cv2.ellipse(image, (50 + shift, 55), (radius, radius * 2), 0, 0, 360, (0, 150, 255), -1)
    cv2.circle(image, (50 + shift, 48), radius // 2, (0, 220, 255), -1)
    return image


def test_candidate_requires_flame_like_color_and_shape_not_red_pixels():
    detector = FireCandidateDetector()
    fire = detector.detect(flame_frame())
    red_block = np.zeros((100, 100, 3), dtype=np.uint8)
    red_block[35:65, 35:65] = (0, 0, 255)
    assert fire
    assert not detector.detect(red_block)


def test_temporal_verifier_requires_persistence_and_change():
    detector = FireCandidateDetector()
    verifier = FireTemporalVerifier(FireTemporalConfig(window_size=5, persistence_frames=3, confidence_threshold=.45))
    result = None
    for sequence in range(5):
        frame = FrameInput(flame_frame(120, 10 + sequence), utc_now(), "cam-fire", sequence)
        result = verifier.observe(frame, detector.detect(frame.data))
    assert result is not None and result.verified
    assert result.persistence == 1.0
    assert result.evidence_indices


def test_static_warm_signal_is_not_verified_without_temporal_persistence():
    detector = FireCandidateDetector()
    verifier = FireTemporalVerifier(FireTemporalConfig(window_size=4, persistence_frames=3, confidence_threshold=.4))
    result = None
    for sequence in range(2):
        frame = FrameInput(flame_frame(), utc_now(), "cam-fire", sequence)
        result = verifier.observe(frame, detector.detect(frame.data))
    assert result is not None and not result.verified


def test_experimental_model_returns_common_fire_result_without_alert_side_effect():
    model = ExperimentalFireModel(temporal=FireTemporalConfig(window_size=3, persistence_frames=2, confidence_threshold=.4))
    frames = tuple(FrameInput(flame_frame(120, 10 + index), utc_now(), "cam-fire", index) for index in range(3))
    request = InferenceRequest(frames[-1], model.model_id, model.model_version, TemporalWindow(frames, frames[0].timestamp, frames[-1].timestamp))
    result = asyncio.run(model.infer(request))
    assert result.event_family.value == "FIRE"
    assert result.camera_id == "cam-fire"
    assert result.model_version == "0.1.0-candidate-temporal"


def test_evaluation_hook_calculates_precision_recall_and_f1():
    metrics = evaluate_binary_events([True, False, True, False], [True, True, False, False])
    assert metrics.true_positive == 1
    assert metrics.false_positive == 1
    assert metrics.false_negative == 1
    assert metrics.precision == metrics.recall == metrics.f1 == 0.5
