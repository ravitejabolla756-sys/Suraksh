import asyncio
from datetime import timedelta

from app.safety import FrameInput, InferenceRequest, TemporalWindow, utc_now
from app.safety.accident import AccidentConfig, AccidentPerceptionFrame, AccidentState, AccidentTemporalVerifier, ExperimentalAccidentModel, TrackObservation, TrajectoryExtractor, evaluate_accident_events, evaluate_annotated_clips, AnnotatedAccidentClip


def tracks(distance, person=False, fall=False):
    items = [TrackObservation(1, "vehicle", (40, 40, 80, 70), zone="road")]
    if person:
        items.append(TrackObservation(2, "person", (40 + distance, 40, 55 + distance, 85), zone="road", pose={"posture": "horizontal" if fall else "standing"}))
    else:
        items.append(TrackObservation(2, "vehicle", (100 + distance, 40, 140 + distance, 70), zone="road"))
    return tuple(items)


def test_trajectory_extractor_is_bounded_and_computes_motion():
    extractor = TrajectoryExtractor(max_tracks=2, points_per_track=2)
    now = utc_now()
    frame = FrameInput(None, now, "cam-1", 1)
    first = extractor.update(frame, tracks(40))
    second = extractor.update(FrameInput(None, now + timedelta(seconds=1), "cam-1", 2), tracks(0))
    assert len(second[0].points) == 2
    assert any(item.points[-1].speed > 0 for item in second)


def test_vehicle_collision_requires_temporal_impact_signals():
    verifier = AccidentTemporalVerifier(AccidentConfig(enabled=True, window_size=4, persistence_frames=2, confidence_threshold=.3, collision_distance=110, impact_deceleration=.1, minimum_approach_speed=.1))
    now = utc_now()
    verifier.observe(1, tracks(50), now)
    verifier.observe(2, tracks(0), now + timedelta(seconds=1))
    verifier.observe(3, tracks(0), now + timedelta(seconds=2))
    events = verifier.observe(4, tracks(0), now + timedelta(seconds=3))
    assert any(event.event_type == "vehicle_collision" for event in events)
    assert events[0].tracks == (1, 2)
    assert verifier.state("accident-camera", (1, 2)) is AccidentState.CONFIRMED


def test_pedestrian_vehicle_collision_is_distinct_subtype():
    verifier = AccidentTemporalVerifier(AccidentConfig(enabled=True, window_size=4, persistence_frames=2, confidence_threshold=.3, collision_distance=110, impact_deceleration=.1, minimum_approach_speed=.1))
    now = utc_now()
    verifier.observe(1, tracks(50, person=True), now)
    verifier.observe(2, tracks(0, person=True), now + timedelta(seconds=1))
    verifier.observe(3, tracks(0, person=True), now + timedelta(seconds=2))
    events = verifier.observe(4, tracks(0, person=True), now + timedelta(seconds=3))
    assert any(event.event_type == "pedestrian_vehicle_collision" for event in events)


def test_person_fall_uses_pose_or_geometry_and_is_deduplicated():
    config = AccidentConfig(enabled=True, window_size=4, persistence_frames=2, confidence_threshold=.3, collision_distance=110, impact_deceleration=.1, minimum_approach_speed=.1, deduplication_frames=10)
    verifier = AccidentTemporalVerifier(config)
    now = utc_now()
    verifier.observe(1, tracks(50, person=True, fall=True), now)
    verifier.observe(2, tracks(0, person=True, fall=True), now + timedelta(seconds=1))
    verifier.observe(3, tracks(0, person=True, fall=True), now + timedelta(seconds=2))
    first = verifier.observe(4, tracks(0, person=True, fall=True), now + timedelta(seconds=3))
    second = verifier.observe(5, tracks(0, person=True, fall=True), now + timedelta(seconds=4))
    assert any(event.event_type == "person_fall" for event in first)
    assert not any(event.event_type == "person_fall" for event in second)


def test_model_returns_common_contract_and_event_payload():
    model = ExperimentalAccidentModel(AccidentConfig(enabled=True, window_size=3, persistence_frames=2, confidence_threshold=.3, collision_distance=60, impact_deceleration=.1, minimum_approach_speed=.1))
    now = utc_now()
    frames = tuple(FrameInput(AccidentPerceptionFrame(tracks(0)), now + timedelta(seconds=i), "cam-1", i) for i in range(3))
    request = InferenceRequest(frames[-1], model.model_id, model.model_version, TemporalWindow(frames, frames[0].timestamp, frames[-1].timestamp))
    result = asyncio.run(model.infer(request))
    payload = model.event_payload(result)
    assert result.event_family.value == "ACCIDENT"
    assert payload["camera_id"] == "cam-1"
    assert payload["model_version"] == model.model_version


def test_event_evaluation_hook():
    metrics = evaluate_accident_events(["vehicle_collision", None, "person_fall"], ["vehicle_collision", "person_fall", None])
    assert (metrics.precision, metrics.recall, metrics.f1) == (0.5, 0.5, 0.5)


def test_annotated_clip_evaluation_reports_delay_and_false_alarm_rate():
    from dataclasses import dataclass
    from datetime import datetime, timezone

    @dataclass
    class Event:
        event_type: str
        timestamp: datetime

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    metrics = evaluate_annotated_clips(
        [AnnotatedAccidentClip("positive", "vehicle_collision", start), AnnotatedAccidentClip("negative", None, None)],
        {"positive": [Event("vehicle_collision", start + timedelta(seconds=2))],
         "negative": [Event("vehicle_collision", start + timedelta(seconds=1))]},
    )
    assert metrics.precision == 0.5
    assert metrics.recall == 1.0
    assert metrics.false_alarm_rate == 1.0
    assert metrics.detection_delay_seconds == 2.0


def test_state_is_camera_scoped_and_calibration_is_explicit():
    from app.safety.accident import CameraCalibration

    verifier = AccidentTemporalVerifier(AccidentConfig(enabled=True, max_cameras=2), calibrations={"cam-m": CameraCalibration(units="meters", homography=(1, 0, 0, 0, 1, 0, 0, 0, 1))})
    now = utc_now()
    verifier.observe(1, tracks(50), now, "cam-a")
    verifier.observe(1, tracks(50), now, "cam-b")
    assert verifier.state("cam-a", (1, 2)) is AccidentState.NORMAL
    assert verifier.features("cam-m") == ()
