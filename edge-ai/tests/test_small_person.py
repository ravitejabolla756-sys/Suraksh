import pytest

from app.perception.small_person import CameraResolutionProfile, validate_profile_budget


def test_camera_profile_is_explicit_and_tiling_is_opt_in():
    profile = CameraResolutionProfile("cam-small", inference_size=960)
    assert profile.tiled_inference is False
    assert profile.inference_size == 960


def test_profile_rejects_invalid_resolution_and_overlap():
    with pytest.raises(ValueError):
        CameraResolutionProfile("cam", inference_size=100)
    with pytest.raises(ValueError):
        CameraResolutionProfile("cam", tile_overlap=1)


def test_realtime_budget_requires_measurement():
    profile = CameraResolutionProfile("cam")
    assert validate_profile_budget(profile, 5, 5.1)
    assert not validate_profile_budget(profile, 5, 4.9)
    assert not validate_profile_budget(profile, 5, None)
