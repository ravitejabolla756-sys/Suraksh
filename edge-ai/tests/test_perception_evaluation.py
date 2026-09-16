import numpy as np

from app.perception.contracts import Detection, DetectorInput
from app.perception.dataset import AnnotatedFrame, GroundTruthObject
from app.perception.evaluation import evaluate_detections, evaluate_tracking
from app.perception.benchmark import PersonDetectionBenchmark
from app.perception.trackers import TrackedDetection, TrackerFrameResult, TrackerTelemetry


def annotation(objects):
    return AnnotatedFrame(__file__, "cam-1", 0, 0, 30, ("night", "crowded"), tuple(objects))


def test_detection_metrics_require_ground_truth():
    metrics = evaluate_detections([(annotation([]), [])])
    assert metrics.precision is None
    assert metrics.ap50 is None


def test_detection_metrics_and_person_strata_are_measured_from_annotations():
    target = GroundTruthObject(0, "person", (0, 0, 20, 20), "p-1", True, .5, ("small",))
    detection = Detection(0, "person", .9, (0, 0, 20, 20), 0, 0)
    metrics = evaluate_detections([(annotation([target]), [detection])])
    assert metrics.precision == 1
    assert metrics.recall == 1
    assert metrics.ap50 == 1
    assert metrics.person_small_recall == 1
    assert metrics.person_occluded_recall == 1
    assert metrics.person_night_recall == 1
    assert metrics.person_crowded_recall == 1


def test_tracking_metrics_are_null_without_track_annotations():
    item = DetectorInput(np.zeros((10, 10, 3)), 0, 0, 30, 1, "cam-1")
    result = TrackerFrameResult("ByteTrack", item, (), TrackerTelemetry(0, 0, 0, 0, 0, 0, 0, 0))
    assert evaluate_tracking([(annotation([]), result)]).idf1 is None


def test_tracking_metrics_count_stable_identity():
    target = GroundTruthObject(0, "person", (0, 0, 20, 20), "p-1")
    detection = Detection(0, "person", .9, (0, 0, 20, 20), 0, 0)
    item = DetectorInput(np.zeros((30, 30, 3)), 0, 0, 30, 1, "cam-1")
    result = TrackerFrameResult("ByteTrack", item, (TrackedDetection(detection, 7, "confirmed"),),
                                TrackerTelemetry(1, 1, 0, 0, 1, 0, 0, 0))
    metrics = evaluate_tracking([(annotation([target]), result)])
    assert metrics.id_switches == 0
    assert metrics.idf1 == 1
    assert metrics.unique_people == 1
    assert metrics.count_error == 0
    assert metrics.hota == 1


def test_person_benchmark_filters_non_person_objects():
    car = GroundTruthObject(2, "car", (0, 0, 20, 20))
    person_target = GroundTruthObject(0, "person", (30, 0, 50, 20))
    person_detection = Detection(0, "person", .9, (30, 0, 50, 20), 0, 0)
    item = annotation([car, person_target])
    filtered = PersonDetectionBenchmark._person_annotation(item)
    assert [obj.class_name for obj in filtered.objects] == ["person"]
    assert evaluate_detections([(filtered, [person_detection])]).recall == 1
