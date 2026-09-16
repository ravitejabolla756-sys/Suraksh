from app.safety import EventFamily, FireSmokePolicy, FrameInput, ModelStatus, SafetyDetection, SafetyPerceptionResult, TemporalFireSmokeVerifier, utc_now

def result(confidence=.8, attributes=None, family=EventFamily.FIRE):
    now = utc_now(); frame = FrameInput(b"frame", now, "cam-1", 1)
    d = SafetyDetection("fire" if family is EventFamily.FIRE else "smoke", confidence, box=(1,1,10,10), attributes=attributes or {})
    return SafetyPerceptionResult(family, "cam-1", "specialist", "test", (d,), confidence, (), None, 1, ModelStatus.READY, now)

def test_single_weak_frame_is_not_confirmed():
    assert TemporalFireSmokeVerifier().observe(result(.7)) is None

def test_persistent_fire_is_confirmed():
    v = TemporalFireSmokeVerifier(FireSmokePolicy(minimum_consecutive_frames=3))
    assert [v.observe(result()) for _ in range(2)][-1] is None
    assert v.observe(result()) is not None

def test_known_light_false_positive_is_suppressed():
    v = TemporalFireSmokeVerifier(FireSmokePolicy(minimum_consecutive_frames=2))
    assert v.observe(result(.95, {"red_light": True})) is None
    assert v.observe(result(.95, {"red_light": True})) is None

def test_smoke_confirms_without_flame():
    v = TemporalFireSmokeVerifier(FireSmokePolicy(minimum_consecutive_frames=2))
    v.observe(result(family=EventFamily.SMOKE))
    assert v.observe(result(family=EventFamily.SMOKE)).detections[0].label == "smoke"
