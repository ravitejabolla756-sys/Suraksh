"""Smoke candidate generation from diffusion/transparency appearance signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class SmokeCandidateConfig:
    min_area_ratio: float = 0.0003
    max_area_ratio: float = 0.30
    min_appearance_score: float = 0.32
    min_transparency_score: float = 0.25


@dataclass(frozen=True, slots=True)
class SmokeCandidate:
    box: tuple[int, int, int, int]
    appearance_score: float
    diffusion_score: float
    transparency_score: float
    area_ratio: float
    mean_luminance: float
    region: tuple[int, int]


SmokeModelScorer = Callable[[np.ndarray], float | None]


class SmokeCandidateDetector:
    """Generate candidates; persistence and motion verification happen later."""

    def __init__(self, config: SmokeCandidateConfig | None = None, scorer: SmokeModelScorer | None = None):
        self.config = config or SmokeCandidateConfig()
        self.scorer = scorer

    def detect(self, frame: Any) -> tuple[SmokeCandidate, ...]:
        image = np.asarray(frame)
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("smoke candidate detector expects a BGR/RGB color frame")
        height, width = image.shape[:2]
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Smoke-like regions are low-saturation, partially transparent-looking
        # areas with enough local luminance variation to avoid flat backgrounds.
        low_sat = cv2.inRange(hsv, np.array([0, 0, 35]), np.array([179, 115, 245]))
        local_std = cv2.blur(gray.astype(np.float32) ** 2, (9, 9)) - cv2.blur(gray.astype(np.float32), (9, 9)) ** 2
        diffuse = ((local_std > 20) & (local_std < 220)).astype(np.uint8) * 255
        mask = cv2.bitwise_and(low_sat, diffuse)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates: list[SmokeCandidate] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            area_ratio = area / float(height * width)
            if not self.config.min_area_ratio <= area_ratio <= self.config.max_area_ratio:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            patch_hsv, patch_gray = hsv[y:y + h, x:x + w], gray[y:y + h, x:x + w]
            patch_mask = mask[y:y + h, x:x + w] > 0
            if not patch_mask.any():
                continue
            saturation = patch_hsv[..., 1][patch_mask]
            luminance = patch_gray[patch_mask]
            transparency = float(np.clip(1.0 - saturation.mean() / 255.0, 0, 1))
            diffusion = float(np.clip(1.0 - np.std(luminance) / 96.0, 0, 1))
            edge_density = cv2.Canny(patch_gray, 80, 160).mean() / 255.0
            # Very sharp, high-edge regions are more likely solid objects.
            diffusion *= float(np.clip(1.0 - edge_density, 0.2, 1.0))
            appearance = 0.55 * transparency + 0.45 * diffusion
            if appearance < self.config.min_appearance_score or transparency < self.config.min_transparency_score:
                continue
            if self.scorer is not None:
                score = self.scorer(image[y:y + h, x:x + w])
                if score is not None:
                    appearance = float(np.clip(0.65 * appearance + 0.35 * score, 0, 1))
            candidates.append(SmokeCandidate(
                (x, y, x + w, y + h), round(appearance, 4), round(diffusion, 4),
                round(transparency, 4), round(area_ratio, 6), round(float(luminance.mean()) / 255, 4),
                (x // max(width // 4, 1), y // max(height // 4, 1)),
            ))
        return tuple(sorted(candidates, key=lambda item: item.appearance_score, reverse=True))
