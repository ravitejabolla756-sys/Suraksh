"""Candidate generation using fire-specific visual signals, not red-pixel rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class FireCandidateConfig:
    min_area_ratio: float = 0.00015
    max_area_ratio: float = 0.28
    min_color_score: float = 0.42
    min_shape_score: float = 0.22
    min_warm_fraction: float = 0.015


@dataclass(frozen=True, slots=True)
class FireCandidate:
    box: tuple[int, int, int, int]
    appearance_score: float
    flame_color_score: float
    flame_shape_score: float
    area_ratio: float
    mean_luminance: float
    warm_pixel_fraction: float


FireModelScorer = Callable[[np.ndarray], float | None]


class FireCandidateDetector:
    """Find regions with warm flame-like color and shape characteristics.

    This is deliberately only a candidate stage. Temporal verification is
    required before the pipeline emits a positive fire result.
    """

    def __init__(self, config: FireCandidateConfig | None = None, scorer: FireModelScorer | None = None):
        self.config = config or FireCandidateConfig()
        self.scorer = scorer

    def detect(self, frame: Any) -> tuple[FireCandidate, ...]:
        image = np.asarray(frame)
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("fire candidate detector expects a BGR/RGB color frame")
        height, width = image.shape[:2]
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        # Warm, bright and sufficiently saturated. A red-only region does not
        # pass the color-diversity requirement below.
        warm = cv2.inRange(hsv, np.array([0, 80, 120]), np.array([45, 255, 255]))
        warm = cv2.morphologyEx(warm, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        warm = cv2.morphologyEx(warm, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(warm, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        frame_area = float(height * width)
        candidates: list[FireCandidate] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            ratio = area / frame_area
            if not self.config.min_area_ratio <= ratio <= self.config.max_area_ratio:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            patch_hsv = hsv[y:y + h, x:x + w]
            patch_mask = warm[y:y + h, x:x + w] > 0
            warm_fraction = float(patch_mask.mean())
            if warm_fraction < self.config.min_warm_fraction:
                continue
            hue = patch_hsv[..., 0][patch_mask]
            sat = patch_hsv[..., 1][patch_mask]
            value = patch_hsv[..., 2][patch_mask]
            if not len(hue):
                continue
            orange_yellow_fraction = float(((hue >= 8) & (hue <= 40)).mean())
            red_fraction = float((hue < 8).mean())
            if orange_yellow_fraction < 0.08 or red_fraction > 0.93:
                # A single red paint/sign/vehicle region is not a fire cue.
                continue
            color_score = float(np.clip(
                0.45 * (value.mean() / 255) + 0.30 * (sat.mean() / 255)
                + 0.25 * min(1.0, orange_yellow_fraction / 0.35), 0, 1
            ))
            # A red object tends to be hue-uniform; fire candidates need warm
            # color variation instead of a single red block.
            color_score *= float(np.clip(1.0 - max(0.0, red_fraction - 0.75), 0.25, 1.0))
            perimeter = max(cv2.arcLength(contour, True), 1.0)
            circularity = float(4 * np.pi * area / (perimeter * perimeter))
            verticality = min(1.0, h / max(w, 1) / 2.0)
            irregularity = float(np.clip(1.0 - circularity, 0, 1))
            shape_score = float(np.clip(0.55 * verticality + 0.45 * irregularity, 0, 1))
            if color_score < self.config.min_color_score or shape_score < self.config.min_shape_score:
                continue
            appearance = 0.60 * color_score + 0.40 * shape_score
            if self.scorer is not None:
                model_score = self.scorer(image[y:y + h, x:x + w])
                if model_score is not None:
                    appearance = float(np.clip(0.65 * appearance + 0.35 * model_score, 0, 1))
            candidates.append(FireCandidate(
                (x, y, x + w, y + h), round(appearance, 4), round(color_score, 4),
                round(shape_score, 4), round(ratio, 6), round(float(value.mean()) / 255, 4),
                round(warm_fraction, 4),
            ))
        return tuple(sorted(candidates, key=lambda item: item.appearance_score, reverse=True))
