"""Per-camera smoke motion, expansion, persistence and region verification."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np

from ..contracts import FrameInput
from .candidate import SmokeCandidate


@dataclass(frozen=True, slots=True)
class SmokeTemporalConfig:
    window_size: int = 12
    persistence_frames: int = 5
    confidence_threshold: float = 0.60
    persistence_threshold: float = 0.50
    motion_threshold: float = 0.015
    expansion_threshold: float = 0.03
    max_evidence_frames: int = 8


@dataclass(frozen=True, slots=True)
class SmokeVerification:
    probability: float
    verified: bool
    persistence: float
    motion: float
    expansion: float
    direction: tuple[float, float]
    region_consistency: float
    evidence_indices: tuple[int, ...]
    contributing_signals: tuple[str, ...]
    reason: str
    duration_seconds: float


def _iou(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    x1, y1 = max(first[0], second[0]), max(first[1], second[1])
    x2, y2 = min(first[2], second[2]), min(first[3], second[3])
    overlap = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(0, first[2] - first[0]) * max(0, first[3] - first[1])
    area_b = max(0, second[2] - second[0]) * max(0, second[3] - second[1])
    return overlap / max(area_a + area_b - overlap, 1)


class SmokeTemporalVerifier:
    """Verify one camera's ordered smoke observations with bounded state."""

    def __init__(self, config: SmokeTemporalConfig | None = None):
        self.config = config or SmokeTemporalConfig()
        if self.config.persistence_frames > self.config.window_size:
            raise ValueError("persistence_frames cannot exceed window_size")
        self._observations: deque[tuple[FrameInput, tuple[SmokeCandidate, ...]]] = deque(maxlen=self.config.window_size)

    def reset(self) -> None:
        self._observations.clear()

    def observe(self, frame: FrameInput, candidates: Iterable[SmokeCandidate]) -> SmokeVerification:
        self._observations.append((frame, tuple(candidates)))
        observations = list(self._observations)
        active = [items for items in observations if items[1]]
        if not active:
            return SmokeVerification(0, False, 0, 0, 0, (0, 0), 0, (), (), "no smoke candidate", 0)
        best = [items[1][0] for items in active]
        persistence = len(best) / len(observations)
        region_consistency = sum(item.region == best[-1].region for item in best) / len(best)
        motions, centers, areas = [], [], []
        for (previous_frame, previous), (current_frame, current) in zip(active, active[1:]):
            previous_candidate, current_candidate = previous[0], current[0]
            prev_gray = cv2.cvtColor(np.asarray(previous_frame.data), cv2.COLOR_BGR2GRAY)
            curr_gray = cv2.cvtColor(np.asarray(current_frame.data), cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(prev_gray, curr_gray).mean() / 255.0
            motions.append(float(np.clip(diff, 0, 1)))
            centers.append(((current_candidate.box[0] + current_candidate.box[2] - previous_candidate.box[0] - previous_candidate.box[2]) / 2,
                            (current_candidate.box[1] + current_candidate.box[3] - previous_candidate.box[1] - previous_candidate.box[3]) / 2))
            areas.append((current_candidate.area_ratio - previous_candidate.area_ratio) / max(previous_candidate.area_ratio, 1e-6))
        motion = float(np.mean(motions)) if motions else 0.0
        expansion = float(np.clip(np.mean(areas), -1, 1)) if areas else 0.0
        direction = tuple(round(float(value), 3) for value in (np.mean(centers, axis=0) if centers else (0, 0)))
        persistence_signal = min(1, persistence / max(self.config.persistence_threshold, 1e-6))
        motion_signal = min(1, motion / max(self.config.motion_threshold, 1e-6))
        expansion_signal = min(1, max(0, expansion) / max(self.config.expansion_threshold, 1e-6))
        appearance = float(np.mean([item.appearance_score for item in best]))
        probability = float(np.clip(0.30 * appearance + 0.22 * persistence_signal + 0.18 * motion_signal + 0.15 * expansion_signal + 0.15 * region_consistency, 0, 1))
        enough_history = len(best) >= self.config.persistence_frames
        changing = motion >= self.config.motion_threshold or expansion >= self.config.expansion_threshold
        verified = enough_history and persistence >= self.config.persistence_threshold and region_consistency >= 0.5 and changing and probability >= self.config.confidence_threshold
        evidence = tuple(item[0].sequence for item in active[-self.config.max_evidence_frames:]) if verified else ()
        signals = tuple(name for name, enabled in (("smoke_like_appearance", appearance >= .32), ("diffusion_transparency", np.mean([item.transparency_score for item in best]) >= .25), ("persistence", persistence >= self.config.persistence_threshold), ("motion", motion >= self.config.motion_threshold), ("expansion", expansion >= self.config.expansion_threshold), ("scene_region_consistency", region_consistency >= .5)) if enabled)
        duration = max(0.0, (observations[-1][0].timestamp - observations[0][0].timestamp).total_seconds())
        return SmokeVerification(round(probability, 4), verified, round(persistence, 4), round(motion, 4), round(expansion, 4), direction, round(region_consistency, 4), evidence, signals, "verified by temporal smoke characteristics" if verified else "temporal persistence/motion threshold not met", round(duration, 3))
