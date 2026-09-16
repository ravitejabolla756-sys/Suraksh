"""Offline evaluation hooks; metrics require annotated ground truth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class BinaryMetrics:
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float


def evaluate_binary_events(expected: Iterable[bool], predicted: Iterable[bool]) -> BinaryMetrics:
    expected_values, predicted_values = list(expected), list(predicted)
    if len(expected_values) != len(predicted_values):
        raise ValueError("expected and predicted event sequences must have equal length")
    tp = sum(actual and guess for actual, guess in zip(expected_values, predicted_values))
    fp = sum(not actual and guess for actual, guess in zip(expected_values, predicted_values))
    fn = sum(actual and not guess for actual, guess in zip(expected_values, predicted_values))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return BinaryMetrics(tp, fp, fn, round(precision, 6), round(recall, 6), round(f1, 6))
