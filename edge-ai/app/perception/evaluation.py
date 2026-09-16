"""Ground-truth-backed detection and tracking metrics for Suraksh."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean
from typing import Iterable, Sequence

from .contracts import Detection
from .dataset import AnnotatedFrame, GroundTruthObject
from .trackers import TrackerFrameResult


def intersection_over_union(a: Sequence[float], b: Sequence[float]) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def _match(gt: Sequence[GroundTruthObject], detections: Sequence[Detection], threshold: float):
    candidates = sorted(
        ((intersection_over_union(target.bbox_xyxy, detection.bbox_xyxy), gi, di)
         for gi, target in enumerate(gt) for di, detection in enumerate(detections)
         if target.class_id == detection.class_id), reverse=True)
    gt_used: set[int] = set()
    det_used: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for score, gi, di in candidates:
        if score < threshold or gi in gt_used or di in det_used:
            continue
        gt_used.add(gi); det_used.add(di)
        matches.append((gi, di, score))
    return matches, gt_used, det_used


@dataclass(frozen=True, slots=True)
class DetectionMetrics:
    precision: float | None
    recall: float | None
    f1: float | None
    false_positives: int | None
    false_negatives: int | None
    ap50: float | None
    ap50_95: float | None
    person_small_recall: float | None
    person_occluded_recall: float | None
    person_night_recall: float | None
    person_crowded_recall: float | None


def _average_precision(records: list[tuple[float, bool]], positives: int) -> float | None:
    if positives == 0:
        return None
    records.sort(key=lambda item: item[0], reverse=True)
    tp = fp = 0
    points = [(0.0, 1.0)]
    for _, correct in records:
        tp += int(correct); fp += int(not correct)
        points.append((tp / positives, tp / (tp + fp)))
    return sum(max((p for r, p in points if r >= level), default=0.0)
               for level in (i / 100 for i in range(101))) / 101


def evaluate_detections(frames: Sequence[tuple[AnnotatedFrame, Sequence[Detection]]]) -> DetectionMetrics:
    if not frames:
        return DetectionMetrics(*(None for _ in range(11)))
    positives = sum(len(frame.objects) for frame, _ in frames)
    if positives == 0:
        return DetectionMetrics(*(None for _ in range(11)))
    tp = fp = fn = 0
    strata = {"small": [0, 0], "occluded": [0, 0], "night": [0, 0], "crowded": [0, 0]}
    ap_by_iou = []
    for threshold in [0.5 + index * 0.05 for index in range(10)]:
        records: list[tuple[float, bool]] = []
        threshold_positives = 0
        for annotation, detections in frames:
            matches, _, det_used = _match(annotation.objects, detections, threshold)
            threshold_positives += len(annotation.objects)
            matched_detections = {di for _, di, _ in matches}
            records.extend((detection.confidence, index in matched_detections)
                           for index, detection in enumerate(detections))
        ap_by_iou.append(_average_precision(records, threshold_positives))
    for annotation, detections in frames:
        matches, gt_used, det_used = _match(annotation.objects, detections, 0.5)
        tp += len(matches); fp += len(detections) - len(det_used); fn += len(annotation.objects) - len(gt_used)
        for index, target in enumerate(annotation.objects):
            if target.class_name != "person":
                continue
            width = target.bbox_xyxy[2] - target.bbox_xyxy[0]
            height = target.bbox_xyxy[3] - target.bbox_xyxy[1]
            labels = set(annotation.tags) | set(target.tags)
            applicable = {
                "small": width * height < 32 * 32 or "small" in labels or "distant" in labels,
                "occluded": target.occluded or "occluded" in labels,
                "night": "night" in labels or "low_light" in labels,
                "crowded": "crowded" in labels,
            }
            for name, applies in applicable.items():
                if applies:
                    strata[name][1] += 1
                    strata[name][0] += int(index in gt_used)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    recall_for = lambda name: strata[name][0] / strata[name][1] if strata[name][1] else None
    return DetectionMetrics(precision, recall, f1, fp, fn, ap_by_iou[0],
                            mean(value for value in ap_by_iou if value is not None),
                            recall_for("small"), recall_for("occluded"),
                            recall_for("night"), recall_for("crowded"))


@dataclass(frozen=True, slots=True)
class TrackingMetrics:
    id_switches: int | None
    idf1: float | None
    hota: float | None
    mota: float | None
    fragmentation: int | None
    average_track_lifetime_frames: float | None
    actual_people: int | None
    detected_people: int | None
    unique_people: int | None
    count_error: int | None
    percentage_count_error: float | None


def evaluate_tracking(frames: Sequence[tuple[AnnotatedFrame, TrackerFrameResult]]) -> TrackingMetrics:
    if not frames or not any(obj.track_id for frame, _ in frames for obj in frame.objects):
        return TrackingMetrics(*(None for _ in range(11)))
    gt_to_last_track: dict[str, int] = {}
    gt_seen: dict[str, bool] = {}
    gt_fragments: dict[str, int] = {}
    predicted_lifetimes: dict[int, int] = {}
    id_switches = tp = fp = fn = 0
    matched_pairs: dict[tuple[str, int], int] = {}
    gt_identity_detections: dict[str, int] = {}
    predicted_identity_detections: dict[int, int] = {}
    detected_gt_people: set[str] = set()
    predicted_people: set[int] = set()
    actual_people = {obj.track_id for frame, _ in frames for obj in frame.objects
                     if obj.class_name == "person" and obj.track_id is not None}
    for annotation, result in frames:
        tracked = [item for item in result.tracks if item.track_id is not None]
        detections = [item.detection for item in tracked]
        for item in tracked:
            predicted_identity_detections[item.track_id] = predicted_identity_detections.get(item.track_id, 0) + 1
        for obj in annotation.objects:
            if obj.track_id is not None:
                gt_identity_detections[obj.track_id] = gt_identity_detections.get(obj.track_id, 0) + 1
        matches, gt_used, det_used = _match(annotation.objects, detections, 0.5)
        tp += len(matches); fp += len(detections) - len(det_used); fn += len(annotation.objects) - len(gt_used)
        present_gt_ids = {obj.track_id for obj in annotation.objects if obj.track_id is not None}
        for gt_id in present_gt_ids:
            if gt_seen.get(gt_id) is False:
                gt_fragments[gt_id] = gt_fragments.get(gt_id, 0) + 1
            gt_seen[gt_id] = False
        for gi, di, _ in matches:
            target, item = annotation.objects[gi], tracked[di]
            if target.track_id is None or item.track_id is None:
                continue
            if target.track_id in gt_to_last_track and gt_to_last_track[target.track_id] != item.track_id:
                id_switches += 1
            gt_to_last_track[target.track_id] = item.track_id
            gt_seen[target.track_id] = True
            matched_pairs[(target.track_id, item.track_id)] = matched_pairs.get((target.track_id, item.track_id), 0) + 1
            predicted_lifetimes[item.track_id] = predicted_lifetimes.get(item.track_id, 0) + 1
            if target.class_name == "person":
                detected_gt_people.add(target.track_id); predicted_people.add(item.track_id)
    gt_total = tp + fn
    mota = 1 - (fn + fp + id_switches) / gt_total if gt_total else None
    identity_tp = _optimal_identity_matches(matched_pairs)
    identity_gt = sum(gt_identity_detections.values())
    identity_predicted = sum(predicted_identity_detections.values())
    idf1 = (2 * identity_tp / (identity_gt + identity_predicted)
            if identity_tp is not None and identity_gt + identity_predicted else None)
    hota = _hota(frames)
    count_error = len(predicted_people) - len(actual_people)
    return TrackingMetrics(id_switches, idf1, hota, mota, sum(gt_fragments.values()),
                           mean(predicted_lifetimes.values()) if predicted_lifetimes else 0.0,
                           len(actual_people), len(detected_gt_people), len(predicted_people), count_error,
                           abs(count_error) / len(actual_people) * 100 if actual_people else None)


def _optimal_identity_matches(pair_counts: dict[tuple[str, int], int]) -> int | None:
    if not pair_counts:
        return 0
    gt_ids = sorted({pair[0] for pair in pair_counts})
    predicted_ids = sorted({pair[1] for pair in pair_counts})
    try:
        import numpy as np
        from scipy.optimize import linear_sum_assignment
    except ImportError:
        return None
    matrix = np.asarray([[-pair_counts.get((gt_id, predicted_id), 0)
                          for predicted_id in predicted_ids] for gt_id in gt_ids])
    rows, columns = linear_sum_assignment(matrix)
    return int(sum(-matrix[row, column] for row, column in zip(rows, columns)))


def _hota(frames: Sequence[tuple[AnnotatedFrame, TrackerFrameResult]]) -> float | None:
    """Compute HOTA over IoU thresholds 0.05..0.95 for annotated identities."""
    scores: list[float] = []
    for threshold_index in range(1, 20):
        threshold = threshold_index * .05
        gt_counts: dict[str, int] = {}
        predicted_counts: dict[int, int] = {}
        pairs: dict[tuple[str, int], int] = {}
        tp = fp = fn = 0
        for annotation, result in frames:
            targets = [obj for obj in annotation.objects if obj.track_id is not None]
            tracked = [item for item in result.tracks if item.track_id is not None]
            detections = [item.detection for item in tracked]
            for target in targets:
                gt_counts[target.track_id] = gt_counts.get(target.track_id, 0) + 1
            for item in tracked:
                predicted_counts[item.track_id] = predicted_counts.get(item.track_id, 0) + 1
            matches, gt_used, det_used = _match(targets, detections, threshold)
            tp += len(matches); fp += len(tracked) - len(det_used); fn += len(targets) - len(gt_used)
            for gi, di, _ in matches:
                pair = (targets[gi].track_id, tracked[di].track_id)
                pairs[pair] = pairs.get(pair, 0) + 1
        if not gt_counts:
            return None
        detection_accuracy = tp / (tp + fp + fn) if tp + fp + fn else 0.0
        association_accuracy = (
            sum(count * count / (gt_counts[gt_id] + predicted_counts[predicted_id] - count)
                for (gt_id, predicted_id), count in pairs.items()) / tp if tp else 0.0
        )
        scores.append(sqrt(detection_accuracy * association_accuracy))
    return mean(scores)
