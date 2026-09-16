from app.promotion import ModelPromotionManager, PromotionCandidate
from app.config import PerCameraPerceptionConfig

def candidate(version, passed=True, status="accepted"):
    return PromotionCandidate("model.pt", version, "ByteTrack", status, passed)

def test_promotion_requires_acceptance_and_health():
    manager = ModelPromotionManager()
    assert not manager.promote("cam", candidate("2", False), {"healthy": True}).promoted
    assert not manager.promote("cam", candidate("2"), {"healthy": False}).promoted

def test_promotion_retains_previous_for_rollback():
    manager = ModelPromotionManager()
    manager.promote("cam", candidate("1"), {"healthy": True})
    manager.promote("cam", candidate("2"), {"healthy": True})
    assert manager.rollback("cam").promoted
    assert manager.version("cam") == "1"

def test_per_camera_config_is_explicit():
    config = PerCameraPerceptionConfig(detector_model="winner.onnx", tracker_type="botsort", reid_enabled=True)
    assert config.detector_model == "winner.onnx"
    assert config.tracker_type == "botsort"
