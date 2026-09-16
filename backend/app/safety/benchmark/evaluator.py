"""Same-metric evaluator for fire, smoke and accident candidate models."""

from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import mean
from typing import Iterable

from .contracts import BenchmarkCandidate, BenchmarkRecord, SafetyStratum


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    candidate_id: str
    sample_count: int
    evaluation_hours: float
    precision: float
    recall: float
    f1: float
    false_positives: int
    false_negatives: int
    false_positives_per_hour: float | None
    detection_delay_seconds: float | None
    inference_latency_ms: float | None
    fps: float | None
    cpu_percent: float | None
    ram_mb: float | None
    model_size_mb: float | None
    event_precision: float | None = None
    event_recall: float | None = None
    track_association_accuracy: float | None = None
    by_stratum: dict[str, "BenchmarkResult"] | None = None


class SafetyBenchmarkEvaluator:
    """Calculate metrics without choosing, promoting, or alerting for a model."""

    def evaluate(self, candidate: BenchmarkCandidate, records: Iterable[BenchmarkRecord], include_strata: bool = True) -> BenchmarkResult:
        rows = list(records)
        if any(row.truth.event_family != candidate.event_family for row in rows):
            raise ValueError("benchmark records must match the candidate event family")
        result = self._evaluate_rows(candidate, rows)
        if include_strata and candidate.event_family.value in {"FIRE", "SMOKE"}:
            strata: dict[str, BenchmarkResult] = {}
            for stratum in SafetyStratum:
                subset = [row for row in rows if stratum in row.truth.strata]
                if subset:
                    strata[stratum.value] = self.evaluate(candidate, subset, include_strata=False)
            return replace(result, by_stratum=strata)
        return result

    def _evaluate_rows(self, candidate: BenchmarkCandidate, rows: list[BenchmarkRecord]) -> BenchmarkResult:
        true_positive, false_positive, false_negative = 0, 0, 0
        delays: list[float] = []
        track_scores: list[float] = []
        for row in rows:
            actual, predicted = row.truth.event_type, row.output.event_type
            matches = actual is not None and predicted is not None and (actual == predicted if candidate.event_family.value == "ACCIDENT" else True)
            if matches:
                true_positive += 1
                if row.output.detected_at is not None:
                    delays.append(max(0.0, (row.output.detected_at - row.truth.start).total_seconds()))
                if candidate.event_family.value == "ACCIDENT" and row.truth.track_ids:
                    expected, observed = set(row.truth.track_ids), set(row.output.track_ids)
                    track_scores.append(len(expected & observed) / len(expected | observed) if expected | observed else 1.0)
            elif predicted is not None:
                false_positive += 1
                if actual is not None:
                    false_negative += 1
            elif actual is not None:
                false_negative += 1
        total_seconds = sum(row.truth.duration_seconds for row in rows)
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        latencies = [row.output.inference_latency_ms for row in rows if row.output.inference_latency_ms is not None]
        fps_values = [row.output.fps for row in rows if row.output.fps is not None]
        cpu_values = [row.output.cpu_percent for row in rows if row.output.cpu_percent is not None]
        ram_values = [row.output.ram_mb for row in rows if row.output.ram_mb is not None]
        sizes = [row.output.model_size_mb for row in rows if row.output.model_size_mb is not None]
        model_size = candidate.model_size_mb if candidate.model_size_mb is not None else (mean(sizes) if sizes else None)
        result = BenchmarkResult(
            candidate_id=candidate.candidate_id, sample_count=len(rows), evaluation_hours=total_seconds / 3600,
            precision=round(precision, 6), recall=round(recall, 6), f1=round(f1, 6),
            false_positives=false_positive, false_negatives=false_negative,
            false_positives_per_hour=round(false_positive / (total_seconds / 3600), 6) if total_seconds else None,
            detection_delay_seconds=round(mean(delays), 6) if delays else None,
            inference_latency_ms=round(mean(latencies), 6) if latencies else None,
            fps=round(mean(fps_values), 6) if fps_values else None,
            cpu_percent=round(mean(cpu_values), 6) if cpu_values else None,
            ram_mb=round(mean(ram_values), 6) if ram_values else None,
            model_size_mb=round(model_size, 6) if model_size is not None else None,
        )
        if candidate.event_family.value == "ACCIDENT":
            result = replace(result, event_precision=result.precision, event_recall=result.recall, track_association_accuracy=round(mean(track_scores), 6) if track_scores else None)
        return result
