from datetime import datetime, timezone

import numpy as np

from app.anpr import ANPRConfig, OCRObservation, PlateDetection, VehicleTrack
from app.anpr.association import associate
from app.anpr.quality import assess
from app.anpr.validation import PlateValidator


def track(track_id=82, camera="cam-1", org="org-1"):
    return VehicleTrack(org, camera, track_id, "car", (10, 10, 210, 160), 101, 4.0,
                        datetime.now(timezone.utc), "session-1")


def test_plate_is_associated_only_when_unambiguous():
    plate = PlateDetection((80, 110, 140, 130), .9, 101, 4.0)
    assert associate(plate, [track()], {}) is not None
    assert associate(plate, [track(), track(83)], {}) is None


def test_quality_gate_rejects_small_or_blurred_crop_without_mutating_frame():
    frame = np.full((200, 240, 3), 128, dtype=np.uint8)
    original = frame.copy()
    crop, quality = assess(frame, PlateDetection((20, 20, 30, 25), .9, 1, 1.0), ANPRConfig())
    assert crop.size and "small_crop" in quality.rejection_reasons
    assert np.array_equal(frame, original)


def test_validation_rules_are_deployment_configurable_and_do_not_guess():
    validator = PlateValidator("TEST", "rules-1", (r"ZZ[0-9]{4}",))
    valid = validator.validate("zz 1234")
    invalid = validator.validate("ZZ1235")
    assert valid.valid and valid.normalized_text == "ZZ1234"
    assert invalid.valid
    assert not validator.validate("ZZ12S4").valid


def test_observation_preserves_source_identity():
    observation = OCRObservation("GJ01 AB1234", "GJ01AB1234", .8, 101, 4.0)
    assert observation.source_frame_index == 101
    assert observation.source_timestamp == 4.0
