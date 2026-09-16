import asyncio

import cv2
import numpy as np

from app.safety import FrameInput, InferenceRequest, TemporalWindow, utc_now
from app.safety.smoke import ExperimentalSmokeModel, SmokeCandidateDetector, SmokeTemporalConfig, SmokeTemporalVerifier, evaluate_smoke_episodes


def smoke_frame(size=120, radius=10, shift=0):
    image = np.zeros((size, size, 3), dtype=np.uint8)
    image[:] = (35, 35, 35)
    for index in range(3):
        cv2.circle(image, (55 + shift + index * 5, 55 - index * 8), radius + index * 2, (125 + index * 12, 125 + index * 12, 125 + index * 12), -1)
    return image


def test_detector_uses_diffuse_low_saturation_regions():
    detector = SmokeCandidateDetector()
    assert detector.detect(smoke_frame())
    solid_blue = np.zeros((120, 120, 3), dtype=np.uint8)
    solid_blue[35:80, 35:80] = (255, 0, 0)
    assert not detector.detect(solid_blue)


def test_temporal_verifier_requires_persistence_and_change():
    detector = SmokeCandidateDetector()
    verifier = SmokeTemporalVerifier(SmokeTemporalConfig(window_size=5, persistence_frames=3, confidence_threshold=.35))
    result = None
    for sequence in range(5):
        current = FrameInput(smoke_frame(radius=8 + sequence, shift=sequence), utc_now(), "cam-smoke", sequence)
        result = verifier.observe(current, detector.detect(current.data))
    assert result is not None and result.verified
    assert "persistence" in result.contributing_signals
    assert result.evidence_indices


def test_static_scene_is_suppressed_without_temporal_change():
    detector = SmokeCandidateDetector()
    verifier = SmokeTemporalVerifier(SmokeTemporalConfig(window_size=4, persistence_frames=3, confidence_threshold=.3))
    result = None
    for sequence in range(4):
        current = FrameInput(smoke_frame(), utc_now(), "cam-smoke", sequence)
        result = verifier.observe(current, detector.detect(current.data))
    assert result is not None and not result.verified


def test_model_returns_common_result_and_smoke_payload():
    model = ExperimentalSmokeModel(temporal=SmokeTemporalConfig(window_size=3, persistence_frames=2, confidence_threshold=.3))
    frames = tuple(FrameInput(smoke_frame(radius=8 + index, shift=index), utc_now(), "cam-smoke", index) for index in range(3))
    request = InferenceRequest(frames[-1], model.model_id, model.model_version, TemporalWindow(frames, frames[0].timestamp, frames[-1].timestamp))
    result = asyncio.run(model.infer(request))
    payload = model.event_payload(result)
    assert payload["event_type"] == "smoke"
    assert payload["camera_id"] == "cam-smoke"
    assert payload["model_version"] == model.model_version


def test_smoke_episode_metrics():
    metrics = evaluate_smoke_episodes([True, False, True], [True, True, False])
    assert (metrics.precision, metrics.recall, metrics.f1) == (.5, .5, .5)
