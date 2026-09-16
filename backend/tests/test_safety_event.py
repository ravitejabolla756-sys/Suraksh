from app.safety import FusionSignal, SafetyPerceptionFusion, utc_now

def test_unified_safety_candidate_contains_source_and_tracks():
    now = utc_now()
    event = SafetyPerceptionFusion().candidate("FIRE", "cam-1", 42, 1.4, .8,
                                              (FusionSignal("fire", .8, "m", "1"),),
                                              track_ids=[3, 3, 2])
    payload = event.as_payload()
    assert payload["event_type"] == "FIRE"
    assert payload["source_frame_index"] == 42
    assert event.involved_track_ids == (2, 3)
    assert event.state == "CANDIDATE"

def test_candidate_rejects_unknown_event_type():
    try:
        SafetyPerceptionFusion().candidate("UNKNOWN", "cam", 1, 0, .5)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown type was accepted")
