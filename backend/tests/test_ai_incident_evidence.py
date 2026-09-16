from datetime import timedelta
from app.safety import (EvidenceAccessPolicy, EvidenceFrameReference, EventCandidate,
                        TemporalEvidenceConfig, TemporalEvidenceEngine,
                        TemporalEvidenceSample, utc_now)

def ref(camera, sequence, uri="store://recording/frame"):
    return EvidenceFrameReference(camera, sequence, utc_now() + timedelta(seconds=sequence), recording_id="r", frame_uri=uri)

def test_evidence_creation_and_bounded_retention():
    now = utc_now(); config = TemporalEvidenceConfig(pre_event_seconds=1, post_event_seconds=1, max_buffer_seconds=2, max_samples=3, max_evidence_frames=2)
    engine = TemporalEvidenceEngine(config)
    for i in range(6): engine.ingest(TemporalEvidenceSample(ref("cam", i), (i,)))
    assert engine.buffer_size("cam") <= 3
    candidate = EventCandidate("FIRE", "cam", now, (1,), .9)
    engine.trigger(candidate)
    assert engine.resolve(candidate.candidate_id)

def test_authorization_is_tenant_and_camera_scoped_and_paths_hidden():
    policy = EvidenceAccessPolicy({"cam-a": "org-a", "cam-b": "org-b"})
    safe = ref("cam-a", 1)
    unsafe = ref("cam-b", 2, "C:\\secret\\frame.jpg")
    assert policy.filter("org-a", (safe, unsafe)) == (safe,)
    assert unsafe.public_payload()["frame_uri"] is None

def test_missing_evidence_and_unknown_resolution_are_safe():
    assert TemporalEvidenceEngine().resolve("missing") == ()
