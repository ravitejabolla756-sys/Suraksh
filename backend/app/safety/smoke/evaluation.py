"""Offline smoke episode evaluation hooks; no performance claims are implied."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class SmokeEpisodeMetrics:
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float


def evaluate_smoke_episodes(expected: Iterable[bool], predicted: Iterable[bool]) -> SmokeEpisodeMetrics:
    actual, guess = list(expected), list(predicted)
    if len(actual) != len(guess):
        raise ValueError("expected and predicted episode sequences must have equal length")
    tp = sum(a and p for a, p in zip(actual, guess))
    fp = sum(not a and p for a, p in zip(actual, guess))
    fn = sum(a and not p for a, p in zip(actual, guess))
    precision, recall = (tp / (tp + fp) if tp + fp else 0), (tp / (tp + fn) if tp + fn else 0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return SmokeEpisodeMetrics(tp, fp, fn, round(precision, 6), round(recall, 6), round(f1, 6))
