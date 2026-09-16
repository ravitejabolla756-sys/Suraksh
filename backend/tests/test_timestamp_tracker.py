from app.services.timestamp_tracker import TimestampAwareTracker, TrackerConfig


def detection(box, confidence=.9, class_id=2):
    return {"box": box, "class_id": class_id, "confidence": confidence}


def test_tracker_confirms_and_keeps_id_across_timestamp_gap():
    tracker = TimestampAwareTracker(TrackerConfig(max_lost_seconds=1.0))
    first = tracker.update([detection([0, 0, 20, 20])], 10.0)
    assert first["detections"][0]["id"] is None
    second = tracker.update([detection([18, 0, 38, 20])], 10.4)
    track_id = second["detections"][0]["id"]
    assert track_id is not None
    third = tracker.update([detection([40, 0, 60, 20])], 10.8)
    assert third["detections"][0]["id"] == track_id
    assert third["telemetry"]["matched_high"] == 1


def test_low_confidence_detection_reactivates_existing_track():
    tracker = TimestampAwareTracker(TrackerConfig(high_confidence=.7, low_confidence=.2))
    tracker.update([detection([0, 0, 40, 40], .9)], 0.0)
    confirmed = tracker.update([detection([1, 0, 41, 40], .9)], .2)
    track_id = confirmed["detections"][0]["id"]
    result = tracker.update([detection([3, 0, 43, 40], .3)], .4)
    assert result["detections"][0]["id"] == track_id
    assert result["telemetry"]["matched_low"] == 1


def test_stale_tracks_are_bounded_and_deleted():
    tracker = TimestampAwareTracker(TrackerConfig(max_lost_seconds=.5))
    tracker.update([detection([0, 0, 20, 20])], 0.0)
    tracker.update([detection([1, 0, 21, 20])], .1)
    result = tracker.update([], 1.0)
    assert result["telemetry"]["deleted"] == 1
    assert result["telemetry"]["active"] == 0


def test_class_aware_matching_does_not_switch_vehicle_class():
    tracker = TimestampAwareTracker()
    tracker.update([detection([0, 0, 30, 30], class_id=2)], 0.0)
    tracker.update([detection([1, 0, 31, 30], class_id=2)], .1)
    result = tracker.update([detection([2, 0, 32, 30], class_id=3)], .2)
    assert result["detections"][0]["id"] is None
    assert result["telemetry"]["created"] == 1
