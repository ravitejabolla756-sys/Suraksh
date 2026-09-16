import numpy as np
import pytest

from app.perception.contracts import Detection, DetectorInput
from app.perception.trackers import (BoTSORTConfig, BoTSORTTracker, ByteTrackConfig,
                                     ByteTrackTracker, UltralyticsTrackerAdapter)
from app.perception.reid import ColorHistogramEncoder, EmbeddingCache


def packet(index, camera="cam-1"):
    return DetectorInput(np.zeros((100, 160, 3), dtype=np.uint8), index, index / 30,
                         30, 10 + index / 30, camera)


def person(index, box=(20, 20, 50, 80)):
    return Detection(0, "person", .9, box, index, index / 30)


@pytest.mark.parametrize("kind", ["bytetrack", "botsort"])
def test_tracker_keeps_id_through_temporary_detector_loss(kind):
    tracker = UltralyticsTrackerAdapter(kind, 30, track_buffer=15)
    first = tracker.update(packet(0), (person(0),))
    confirmed = tracker.update(packet(1), (person(1, (21, 20, 51, 80)),))
    tracker.update(packet(2), ())
    third = tracker.update(packet(3), (person(3, (22, 20, 52, 80)),))
    assert first.tracks[0].track_id is not None
    assert confirmed.tracks[0].track_id == first.tracks[0].track_id
    assert third.tracks[0].track_id == first.tracks[0].track_id
    assert third.telemetry.reactivated_tracks >= 1


def test_tracker_rejects_out_of_order_frames():
    tracker = UltralyticsTrackerAdapter("bytetrack", 30)
    tracker.update(packet(3), (person(3),))
    with pytest.raises(ValueError):
        tracker.update(packet(2), (person(2),))


def test_two_camera_trackers_have_isolated_state():
    camera_a = UltralyticsTrackerAdapter("bytetrack", 30)
    camera_b = UltralyticsTrackerAdapter("bytetrack", 30)
    a = camera_a.update(packet(0, "a"), (person(0),))
    b = camera_b.update(packet(50, "b"), (person(50),))
    assert a.tracks[0].track_id is not None
    assert b.tracks[0].track_id is not None
    assert camera_a._last_frame_index == 0
    assert camera_b._last_frame_index == 50
    assert a.tracks[0].track_id == 1
    assert b.tracks[0].track_id == 1


def test_tracker_uses_source_time_to_advance_missing_frames():
    tracker = UltralyticsTrackerAdapter("bytetrack", 30, track_buffer=2)
    tracker.update(packet(0), (person(0),))
    late = DetectorInput(np.zeros((100, 160, 3), dtype=np.uint8), 1, 1.0, 30, 11, "cam-1")
    late_detection = Detection(0, "person", .9, (20, 20, 50, 80), 1, 1.0)
    tracker.update(late, (late_detection,))
    assert tracker._trackers[0].frame_id >= 5


def test_bytetrack_configuration_is_explicit_and_validated():
    config = ByteTrackConfig(track_high_threshold=.7, track_low_threshold=.2,
                             new_track_threshold=.75, match_threshold=.65,
                             track_buffer=12, minimum_hits=2, maximum_age=9)
    tracker = ByteTrackTracker(30, config=config)
    assert tracker.config == config
    with pytest.raises(ValueError):
        ByteTrackConfig(track_high_threshold=.1, track_low_threshold=.2)


def test_bytetrack_rejects_cross_class_detection_identity():
    tracker = ByteTrackTracker(30)
    first = tracker.update(packet(0), (person(0),))
    vehicle = Detection(2, "car", .9, (20, 20, 50, 80), 1, 1 / 30)
    result = tracker.update(packet(1), (vehicle,))
    assert first.tracks[0].track_id != result.tracks[0].track_id


def test_botsort_configuration_disables_expensive_features_by_default():
    config = BoTSORTConfig(track_buffer=18)
    tracker = BoTSORTTracker(30, config=config)
    assert tracker.bot_sort_config.camera_motion_compensation is False
    assert tracker.bot_sort_config.reid_enabled is False
    assert tracker.bot_sort_config.reid_weight == 0


def test_botsort_configuration_requires_reid_weight_when_enabled():
    with pytest.raises(ValueError):
        BoTSORTConfig(reid_enabled=True)


def test_botsort_rejects_disabled_configuration():
    with pytest.raises(ValueError):
        BoTSORTTracker(30, config=BoTSORTConfig(enabled=False))


def test_embedding_cache_is_bounded_and_anonymous():
    cache = EmbeddingCache(2)
    cache.put(1, np.ones(4))
    cache.put(2, np.ones(4))
    cache.put(3, np.ones(4))
    assert len(cache) == 2
    assert cache.get(1) is None
    assert cache.get(2) is not None


def test_appearance_encoder_returns_normalized_nonempty_vector():
    embedding = ColorHistogramEncoder().encode(np.zeros((8, 8, 3), dtype=np.uint8))
    assert np.linalg.norm(embedding) == pytest.approx(1.0)
