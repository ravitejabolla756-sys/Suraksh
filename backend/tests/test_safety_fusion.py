from datetime import timedelta

import pytest

from app.safety import EventCandidate, EvidenceFrameReference, FusionRequest, FusionSignal, SafetyEvidenceFusionEngine, SignalPolarity, utc_now


def evidence(camera, sequence):
    timestamp = utc_now() + timedelta(seconds=sequence)
    return EvidenceFrameReference(camera, sequence, timestamp, recording_id="r-1", frame_uri=f"store://{camera}/{sequence}")


def request(signals):
    return FusionRequest("fire", "cam-1", utc_now(), tuple(signals))


def test_fusion_keeps_signals_explicit_and_does_not_average_confidence():
    engine = SafetyEvidenceFusionEngine()
    one = engine.fuse(request((FusionSignal("fire_detector", .81, "fire", "1", (evidence("cam-1", 1),), correlation_group="visual"),)))
    two = engine.fuse(request((FusionSignal("fire_detector", .81, "fire", "1", correlation_group="visual"), FusionSignal("temporal_persistence", .91, "temporal", "1", correlation_group="temporal"))))
    assert two.confidence > one.confidence
    assert two.contributing_signals == ("fire_detector", "temporal_persistence")
    assert two.confidence != (.81 + .91) / 2


def test_correlated_signals_are_penalized_and_evidence_is_deduplicated():
    engine = SafetyEvidenceFusionEngine()
    ref = evidence("cam-1", 1)
    result = engine.fuse(request((FusionSignal("fire_detector", .8, "fire-a", "1", (ref,), correlation_group="visual"), FusionSignal("smoke_detector", .8, "smoke-a", "2", (ref,), correlation_group="visual"))))
    assert result.confidence < .96
    assert len(result.evidence_references) == 1
    assert result.model_versions == {"fire-a": "1", "smoke-a": "2"}


def test_contradicting_signal_reduces_confidence_and_increases_uncertainty():
    engine = SafetyEvidenceFusionEngine()
    positive = engine.fuse(request((FusionSignal("fire_detector", .9, "fire", "1"), FusionSignal("temporal_persistence", .8, "temporal", "1"))))
    mixed = engine.fuse(request((FusionSignal("fire_detector", .9, "fire", "1"), FusionSignal("temporal_persistence", .8, "temporal", "1"), FusionSignal("clear_scene", .9, "scene", "1", polarity=SignalPolarity.CONTRADICT))))
    assert mixed.confidence < positive.confidence
    assert mixed.uncertainty > positive.uncertainty
    assert mixed.contradicting_groups == ("clear_scene",)


def test_fusion_rejects_evidence_from_another_camera_and_invalid_signal():
    with pytest.raises(ValueError):
        FusionSignal("bad", 1.1, "model", "1")
    with pytest.raises(ValueError):
        SafetyEvidenceFusionEngine().fuse(request((FusionSignal("fire", .8, "m", "1", (evidence("cam-2", 1),)),)))


def test_fusion_is_deterministic_and_has_no_alert_policy_field():
    signals = (FusionSignal("tracker", .7, "tracker", "2", correlation_group="tracking"), FusionSignal("trajectory", .75, "trajectory", "2", correlation_group="motion"))
    first = SafetyEvidenceFusionEngine().fuse(request(signals))
    second = SafetyEvidenceFusionEngine().fuse(FusionRequest("fire", "cam-1", first.timestamp, signals))
    assert first.confidence == second.confidence
    assert first.as_payload()["model_versions"] == {"tracker": "2", "trajectory": "2"}
    assert "should_alert" not in first.as_payload()
