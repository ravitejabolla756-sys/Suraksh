from datetime import timedelta

from app.safety import EventFamily, utc_now
from app.safety.benchmark import BenchmarkCandidate, BenchmarkRecord, GroundTruth, ModelOutput, SafetyBenchmarkEvaluator, SafetyStratum


def candidate(family):
    return BenchmarkCandidate(f"{family.value.lower()}-candidate", "Test candidate", family, "test", "temporal", "cpu", model_size_mb=12.5)


def record(family, event_type, predicted, strata=()):
    start = utc_now()
    truth = GroundTruth("sample", "cam-1", family, event_type, start, start + timedelta(hours=1), tuple(strata), (1, 2) if family is EventFamily.ACCIDENT and event_type else ())
    output = ModelOutput(predicted, .8, start + timedelta(seconds=2) if predicted else None, (1, 2) if predicted else (), 10, 20, 30, 100, 12.5)
    return BenchmarkRecord(truth, output)


def test_fire_benchmark_calculates_metrics_and_strata():
    candidate_model = candidate(EventFamily.FIRE)
    rows = [record(EventFamily.FIRE, "fire", "fire", (SafetyStratum.DAY,)), record(EventFamily.FIRE, None, "fire", (SafetyStratum.NIGHT,)), record(EventFamily.FIRE, "fire", None, (SafetyStratum.DAY,))]
    result = SafetyBenchmarkEvaluator().evaluate(candidate_model, rows)
    assert (result.precision, result.recall, result.f1) == (.5, .5, .5)
    assert result.false_positives_per_hour == .333333
    assert result.by_stratum["day"].false_negatives == 1


def test_accident_benchmark_adds_event_and_track_metrics():
    candidate_model = candidate(EventFamily.ACCIDENT)
    result = SafetyBenchmarkEvaluator().evaluate(candidate_model, [record(EventFamily.ACCIDENT, "vehicle_collision", "vehicle_collision")])
    assert result.event_precision == result.event_recall == 1.0
    assert result.track_association_accuracy == 1.0


def test_benchmark_rejects_mixed_event_families():
    import pytest
    with pytest.raises(ValueError):
        SafetyBenchmarkEvaluator().evaluate(candidate(EventFamily.SMOKE), [record(EventFamily.FIRE, "fire", "fire")])


def test_benchmark_rejects_invalid_confidence():
    import pytest
    with pytest.raises(ValueError):
        ModelOutput("fire", 1.2)
