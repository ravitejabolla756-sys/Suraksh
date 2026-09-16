"""Deterministic detector/tracker benchmark orchestration.

This module never mutates the deployed detector configuration. Accuracy
metrics are emitted only when an approved annotation manifest is provided.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
import time
from typing import Any, Sequence

import cv2
import psutil

from .contracts import DetectorInput, DetectorUnavailable, PersonVehicleDetector
from .dataset import AnnotatedFrame, DatasetManifest, decode_frame
from .detectors import candidate_detectors
from .evaluation import evaluate_detections, evaluate_tracking
from .trackers import UltralyticsTrackerAdapter


def _hardware() -> dict[str, Any]:
    gpu: dict[str, Any] | None = None
    try:
        import torch
        if torch.cuda.is_available():
            gpu = {"name": torch.cuda.get_device_name(0), "cuda": torch.version.cuda}
    except ImportError:
        pass
    return {
        "cpu": psutil.cpu_count(logical=True),
        "cpu_name": __import__("platform").processor(),
        "ram_total_mb": round(psutil.virtual_memory().total / 1024 ** 2),
        "gpu": gpu,
    }


def sample_video(video_path: Path, camera_id: str, max_frames: int) -> list[tuple[AnnotatedFrame, Any]]:
    """Decode evenly spaced frames once so candidates receive identical pixels."""
    capture = cv2.VideoCapture(str(video_path))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    if total <= 0 or fps <= 0:
        capture.release()
        raise RuntimeError(f"invalid video metadata: {video_path}")
    count = min(max_frames, total)
    indices = sorted({round(index * (total - 1) / max(1, count - 1)) for index in range(count)})
    sampled: list[tuple[AnnotatedFrame, Any]] = []
    for frame_index in indices:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok:
            capture.release()
            raise RuntimeError(f"failed to decode frame {frame_index} from {video_path}")
        annotation = AnnotatedFrame(video_path.resolve(), camera_id, frame_index,
                                    frame_index / fps, fps, (), ())
        sampled.append((annotation, frame.copy()))
    capture.release()
    return sampled


class PersonDetectionBenchmark:
    def __init__(self, root: Path, candidates: Sequence[PersonVehicleDetector]):
        self.root = root
        self.candidates = list(candidates)

    def run(self, samples: Sequence[tuple[AnnotatedFrame, Any]], annotated: bool) -> dict[str, Any]:
        report: dict[str, Any] = {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "evaluation" if annotated else "runtime_only",
            "production_default_changed": False,
            "hardware": _hardware(),
            "frames": len(samples),
            "candidates": [],
        }
        process = psutil.Process()
        for detector in self.candidates:
            candidate: dict[str, Any] = {
                "detector_id": detector.detector_id,
                "model_version": detector.model_version,
                "license_status": detector.license_status,
            }
            try:
                load_started = time.perf_counter()
                detector.load()
                candidate["load_ms"] = round((time.perf_counter() - load_started) * 1000, 3)
                if samples:
                    annotation, pixels = samples[0]
                    warmup = DetectorInput(pixels, annotation.frame_index, annotation.source_timestamp,
                                           annotation.source_fps, time.perf_counter(), annotation.camera_id)
                    detector.warmup([warmup])
                cpu_start = process.cpu_times()
                wall_start = time.perf_counter()
                rss_start = process.memory_info().rss
                results = []
                per_frame = []
                for annotation, pixels in samples:
                    item = DetectorInput(pixels, annotation.frame_index, annotation.source_timestamp,
                                         annotation.source_fps, time.perf_counter(), annotation.camera_id)
                    result = detector.detect(item)
                    results.append((annotation, result))
                    per_frame.append({
                        "camera_id": annotation.camera_id,
                        "source_frame_index": annotation.frame_index,
                        "source_timestamp": annotation.source_timestamp,
                        "detections": len(result.detections),
                        "people": sum(item.class_name == "person" for item in result.detections),
                        "timing": asdict(result.timing),
                    })
                wall = time.perf_counter() - wall_start
                cpu_end = process.cpu_times()
                rss_end = process.memory_info().rss
                timings = [result.timing for _, result in results]
                candidate.update({
                    "status": "completed",
                    "runtime": {
                        "preprocessing_ms_mean": _mean_optional(item.preprocessing_ms for item in timings),
                        "inference_ms_mean": _mean_optional(item.inference_ms for item in timings),
                        "postprocessing_ms_mean": _mean_optional(item.postprocessing_ms for item in timings),
                        "end_to_end_ms_mean": round(mean(item.total_ms for item in timings), 3) if timings else None,
                        "fps": round(len(results) / wall, 3) if wall else None,
                        "cpu_percent_single_process": round(
                            ((cpu_end.user + cpu_end.system) - (cpu_start.user + cpu_start.system)) / wall * 100, 2
                        ) if wall else None,
                        "rss_mb_end": round(rss_end / 1024 ** 2, 2),
                        "rss_mb_delta": round((rss_end - rss_start) / 1024 ** 2, 2),
                        "gpu": report["hardware"]["gpu"],
                        "frame_age_ms_mean": round(mean(item.frame_age_ms for item in timings), 3) if timings else None,
                    },
                    "detection_metrics": asdict(evaluate_detections(
                        [(self._person_annotation(annotation),
                          tuple(item for item in result.detections if item.class_name == "person"))
                         for annotation, result in results]
                    )) if annotated else _unmeasured_detection_metrics(),
                    "frames": per_frame,
                    "trackers": [],
                })
                for tracker_kind in ("bytetrack", "botsort"):
                    try:
                        tracker_result = self._run_tracker(tracker_kind, results, annotated)
                    except Exception as exc:
                        tracker_result = {
                            "tracker": "ByteTrack" if tracker_kind == "bytetrack" else "BoT-SORT",
                            "reid": False, "status": "failed",
                            "reason": f"{type(exc).__name__}: {exc}",
                        }
                    candidate["trackers"].append(tracker_result)
            except Exception as exc:
                status = "unavailable" if isinstance(exc, (DetectorUnavailable, ImportError)) else "failed"
                candidate.update(status=status, reason=f"{type(exc).__name__}: {exc}")
            report["candidates"].append(candidate)
        return report

    @staticmethod
    def _person_annotation(annotation: AnnotatedFrame) -> AnnotatedFrame:
        return AnnotatedFrame(annotation.video_path, annotation.camera_id,
                              annotation.frame_index, annotation.source_timestamp,
                              annotation.source_fps, annotation.tags,
                              tuple(item for item in annotation.objects if item.class_name == "person"))

    @staticmethod
    def _run_tracker(kind: str, results: Sequence[tuple[AnnotatedFrame, Any]], annotated: bool):
        by_camera: dict[str, UltralyticsTrackerAdapter] = {}
        tracked = []
        totals = {name: 0 for name in (
            "detections", "matched_tracks", "unmatched_detections", "unmatched_tracks",
            "new_tracks", "reactivated_tracks", "expired_tracks", "predicted_tracks")}
        for annotation, result in results:
            tracker = by_camera.setdefault(annotation.camera_id,
                                           UltralyticsTrackerAdapter(kind, annotation.source_fps))
            frame_result = tracker.update(result.input, result.detections)
            tracked.append((annotation, frame_result))
            for name in totals:
                totals[name] += getattr(frame_result.telemetry, name)
        return {
            "tracker": "ByteTrack" if kind == "bytetrack" else "BoT-SORT",
            "reid": False,
            "status": "completed",
            "telemetry": totals,
            "metrics": asdict(evaluate_tracking(tracked)) if annotated else _unmeasured_tracking_metrics(),
        }


def _mean_optional(values) -> float | None:
    present = [value for value in values if value is not None]
    return round(mean(present), 3) if present else None


def _unmeasured_detection_metrics() -> dict[str, None]:
    return {name: None for name in DetectionMetricsFields}


def _unmeasured_tracking_metrics() -> dict[str, None]:
    return {name: None for name in TrackingMetricsFields}


DetectionMetricsFields = (
    "precision", "recall", "f1", "false_positives", "false_negatives", "ap50", "ap50_95",
    "person_small_recall", "person_occluded_recall", "person_night_recall", "person_crowded_recall",
)
TrackingMetricsFields = (
    "id_switches", "idf1", "hota", "mota", "fragmentation", "average_track_lifetime_frames",
    "actual_people", "detected_people", "unique_people", "count_error", "percentage_count_error",
)


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)


def default_candidates(root: Path, selected: set[str] | None = None):
    all_candidates = candidate_detectors(root)
    return [candidate for candidate in all_candidates
            if not selected or candidate.detector_id in selected]
