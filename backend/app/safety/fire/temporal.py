"""Temporal persistence, flicker, growth and false-positive suppression."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from ..contracts import FrameInput
from .candidate import FireCandidate


@dataclass(frozen=True, slots=True)
class FireTemporalConfig:
    window_size: int = 12
    persistence_frames: int = 5
    confidence_threshold: float = 0.62
    persistence_threshold: float = 0.50
    flicker_threshold: float = 0.025
    growth_threshold: float = 0.04
    max_evidence_frames: int = 8


@dataclass(frozen=True, slots=True)
class FireVerification:
    probability: float
    verified: bool
    persistence: float
    flicker: float
    growth: float
    evidence_indices: tuple[int, ...]
    reason: str


class FireTemporalVerifier:
    """Verify one camera's ordered candidate observations."""

    def __init__(self, config: FireTemporalConfig | None = None):
        self.config = config or FireTemporalConfig()
        if self.config.persistence_frames > self.config.window_size:
            raise ValueError("persistence_frames cannot exceed window_size")
        self._observations: deque[tuple[FrameInput, tuple[FireCandidate, ...]]] = deque(maxlen=self.config.window_size)

    def reset(self) -> None:
        self._observations.clear()

    def observe(self, frame: FrameInput, candidates: Iterable[FireCandidate]) -> FireVerification:
        self._observations.append((frame, tuple(candidates)))
        observations = list(self._observations)
        active = [items[0] for items in observations if items[1]]
        if not active:
            return FireVerification(0.0, False, 0.0, 0.0, 0.0, (), "no visual fire candidate")
        best = [items[1][0] for items in observations if items[1]]
        persistence = len(best) / len(observations)
        luminance = np.asarray([item.mean_luminance for item in best], dtype=np.float32)
        areas = np.asarray([item.area_ratio for item in best], dtype=np.float32)
        flicker = float(np.clip(np.std(luminance), 0, 1)) if len(luminance) > 1 else 0.0
        growth = float(np.clip(np.polyfit(np.arange(len(areas)), areas, 1)[0] / max(float(areas.mean()), 1e-6), -1, 1)) if len(areas) > 1 else 0.0
        growth_signal = max(0.0, growth)
        flicker_signal = min(1.0, flicker / max(self.config.flicker_threshold, 1e-6))
        persistence_signal = min(1.0, persistence / max(self.config.persistence_threshold, 1e-6))
        appearance = float(np.mean([item.appearance_score for item in best]))
        probability = float(np.clip(
            0.42 * appearance + 0.25 * persistence_signal + 0.20 * flicker_signal + 0.13 * min(1.0, growth_signal / max(self.config.growth_threshold, 1e-6)), 0, 1
        ))
        enough_history = len(best) >= self.config.persistence_frames
        verified = enough_history and persistence >= self.config.persistence_threshold and probability >= self.config.confidence_threshold
        evidence = tuple(item.sequence for item in active[-self.config.max_evidence_frames:]) if verified else ()
        reason = "verified by appearance, persistence and temporal change" if verified else "temporal persistence/confidence threshold not met"
        return FireVerification(round(probability, 4), verified, round(persistence, 4), round(flicker, 4), round(growth, 4), evidence, reason)
