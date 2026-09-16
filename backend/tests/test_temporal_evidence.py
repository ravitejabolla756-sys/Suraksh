from datetime import timedelta

from app.safety import (
    EventCandidate,
    EvidenceFrameReference,
    TemporalEvidenceConfig,
    TemporalEvidenceEngine,
    TemporalEvidenceSample,
    utc_now,
)


def sample(camera, sequence, timestamp, tracks=(1, 2)):
    return TemporalEvidenceSample(EvidenceFrameReference(camera, sequence, timestamp, recording_id=f"recording-{camera}", frame_uri=f"store://{camera}/{sequence}"), tracks)


def test_buffer_rollover_is_bounded_by_sample_count_and_age():
    engine = TemporalEvidenceEngine(TemporalEvidenceConfig(max_samples=3, max_buffer_seconds=20, pre_event_seconds=5, post_event_seconds=5))
    start = utc_now()
    for sequence in range(5):
        engine.ingest(sample("cam-a", sequence, start + timedelta(seconds=sequence)))
    assert engine.buffer_size("cam-a") == 3
    assert engine._state("cam-a").samples[0].reference.sequence == 2


def test_trigger_waits_for_post_event_and_extracts_pre_event_event_and_post_event():
    config = TemporalEvidenceConfig(pre_event_seconds=4, event_context_before_seconds=1, event_context_after_seconds=1, post_event_seconds=4, max_evidence_frames=3, max_buffer_seconds=12)
    engine = TemporalEvidenceEngine(config)
    start = utc_now()
    completed = []
    for sequence in range(0, 15):
        timestamp = start + timedelta(seconds=sequence)
        completed.extend(engine.ingest(sample("cam-a", sequence, timestamp)))
        if sequence == 6:
            assert engine.trigger(EventCandidate("fire", "cam-a", timestamp, (1, 2), .8))
        if sequence == 8:
            assert engine.pending_count("cam-a") == 1
    assert len(completed) == 1
    event = completed[0]
    assert event.event.event_type == "fire"
    assert event.pre_event and event.event_evidence and event.post_event
    assert event.track_history
    assert all(reference.frame_uri.startswith("store://") for reference in event.evidence)


def test_event_deduplication_suppresses_same_camera_event_and_allows_new_after_cooldown():
    config = TemporalEvidenceConfig(pre_event_seconds=1, post_event_seconds=1, max_buffer_seconds=5, deduplication_seconds=5)
    engine = TemporalEvidenceEngine(config)
    start = utc_now()
    engine.ingest(sample("cam-a", 0, start))
    candidate = EventCandidate("accident", "cam-a", start, (4, 5))
    assert engine.trigger(candidate)
    assert not engine.trigger(EventCandidate("accident", "cam-a", start, (5, 4)))
    engine.ingest(sample("cam-a", 1, start + timedelta(seconds=1)))
    assert not engine.trigger(EventCandidate("accident", "cam-a", start + timedelta(seconds=1), (4, 5)))
    assert engine.trigger(EventCandidate("accident", "cam-a", start + timedelta(seconds=7), (4, 5)))


def test_stale_event_cleanup_removes_pending_event_and_idle_camera_state():
    config = TemporalEvidenceConfig(pre_event_seconds=1, post_event_seconds=2, stale_event_grace_seconds=3, max_buffer_seconds=10)
    engine = TemporalEvidenceEngine(config)
    start = utc_now()
    engine.ingest(sample("cam-a", 0, start))
    assert engine.trigger(EventCandidate("smoke", "cam-a", start))
    engine.cleanup(start + timedelta(seconds=6))
    assert engine.pending_count("cam-a") == 0
    assert engine.buffer_size("cam-a") == 1


def test_multiple_cameras_have_independent_buffers_and_pending_events():
    config = TemporalEvidenceConfig(pre_event_seconds=1, post_event_seconds=1, max_buffer_seconds=5)
    engine = TemporalEvidenceEngine(config)
    start = utc_now()
    engine.ingest(sample("cam-a", 1, start))
    engine.ingest(sample("cam-b", 1, start))
    assert engine.trigger(EventCandidate("fire", "cam-a", start))
    assert engine.trigger(EventCandidate("fire", "cam-b", start))
    assert engine.pending_count("cam-a") == engine.pending_count("cam-b") == 1
    assert engine.buffer_size("cam-a") == engine.buffer_size("cam-b") == 1
