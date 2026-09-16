"""Offline evaluation for annotated accident and non-accident clips."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Protocol


class _EventLike(Protocol):
    event_type: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class AccidentMetrics:
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float
    false_alarm_rate: float = 0.0
    detection_delay_seconds: float | None = None
    missed_accidents: int = 0


@dataclass(frozen=True, slots=True)
class AnnotatedAccidentClip:
    """Ground truth for one clip; an absent event is a negative clip."""

    clip_id: str
    accident_type: str | None
    accident_at: datetime | None

    def __post_init__(self) -> None:
        if not self.clip_id or (self.accident_type is None) != (self.accident_at is None):
            raise ValueError("clip annotation must contain both event type/time or neither")


def evaluate_accident_events(expected: Iterable[str | None], predicted: Iterable[str | None]) -> AccidentMetrics:
    """Evaluate aligned event labels for compatibility with existing unit tests."""
    actual, guess = list(expected), list(predicted)
    if len(actual) != len(guess):
        raise ValueError("expected and predicted event sequences must have equal length")
    tp = sum(a is not None and a == p for a, p in zip(actual, guess))
    fp = sum(p is not None and a != p for a, p in zip(actual, guess))
    fn = sum(a is not None and a != p for a, p in zip(actual, guess))
    precision, recall = (tp / (tp + fp) if tp + fp else 0), (tp / (tp + fn) if tp + fn else 0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return AccidentMetrics(tp, fp, fn, round(precision, 6), round(recall, 6), round(f1, 6),
                           round(fp / len(actual), 6) if actual else 0.0, None, fn)


def evaluate_annotated_clips(clips: Iterable[AnnotatedAccidentClip],
                             predictions: dict[str, Iterable[_EventLike]]) -> AccidentMetrics:
    """Match at most one prediction per ground-truth clip and report delay."""
    true_positive = false_positive = false_negative = 0
    delays: list[float] = []
    clip_list = list(clips)
    for clip in clip_list:
        events = sorted(predictions.get(clip.clip_id, ()), key=lambda event: event.timestamp)
        matching = next((event for event in events if clip.accident_type and event.event_type == clip.accident_type), None)
        if clip.accident_type is None:
            false_positive += len(events)
        elif matching is None:
            false_negative += 1
            false_positive += len(events)
        else:
            true_positive += 1
            delays.append(max(0.0, (matching.timestamp - clip.accident_at).total_seconds()))
            false_positive += max(0, len(events) - 1)
    positives = sum(clip.accident_type is not None for clip in clip_list)
    negatives = sum(clip.accident_type is None for clip in clip_list)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return AccidentMetrics(true_positive, false_positive, false_negative,
                           round(precision, 6), round(recall, 6), round(f1, 6),
                           round(false_positive / negatives, 6) if negatives else 0.0,
                           round(sum(delays) / len(delays), 6) if delays else None,
                           positives - true_positive)
