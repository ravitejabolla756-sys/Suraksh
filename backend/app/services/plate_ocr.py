"""Bounded plate-region OCR for the recorded and edge preview paths."""

from __future__ import annotations

import os
import re
from typing import Any

import cv2
import numpy as np
import pytesseract

from app.services.plates import normalize_plate


class PlateOCR:
    """Find likely plate bands inside a vehicle crop and read only real OCR output."""

    def __init__(self) -> None:
        pytesseract.pytesseract.tesseract_cmd = os.environ.get(
            "SURAKSH_TESSERACT", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )
        self.configs = (
            "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            "--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        )

    def read(self, vehicle: np.ndarray) -> dict[str, Any] | None:
        if vehicle.size == 0 or vehicle.shape[0] < 24 or vehicle.shape[1] < 40:
            return None
        regions = self._regions(vehicle)
        best: dict[str, Any] | None = None
        for region in regions:
            for image in self._variants(region):
                for config in self.configs:
                    try:
                        data = pytesseract.image_to_data(
                            image, config=config, output_type=pytesseract.Output.DICT, timeout=0.75
                        )
                    except Exception:
                        continue
                    raw = "".join(str(value) for value in data.get("text", []))
                    candidate = normalize_plate(re.sub(r"[^A-Za-z0-9]", "", raw))
                    if not candidate:
                        continue
                    confidence = self._confidence(data)
                    result = {"text": candidate, "confidence": round(confidence, 4)}
                    if best is None or result["confidence"] > best["confidence"]:
                        best = result
        return best if best and best["confidence"] >= 0.45 else None

    @staticmethod
    def _regions(vehicle: np.ndarray) -> list[np.ndarray]:
        height, width = vehicle.shape[:2]
        lower = vehicle[int(height * 0.45): int(height * 0.98), :]
        gray = cv2.cvtColor(lower, cv2.COLOR_BGR2GRAY)
        bright = cv2.inRange(gray, 150, 255)
        contours, _ = cv2.findContours(bright, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        regions: list[np.ndarray] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            aspect = w / max(h, 1)
            if w >= max(24, int(width * 0.12)) and h >= 5 and 2.0 <= aspect <= 9.0:
                regions.append(lower[max(0, y - 3): min(lower.shape[0], y + h + 3), max(0, x - 5): min(width, x + w + 5)])
        regions.append(lower)
        return regions[:2]

    @staticmethod
    def _variants(region: np.ndarray) -> tuple[np.ndarray, ...]:
        scale = min(4.0, 960 / max(region.shape[:2]))
        enlarged = cv2.resize(region, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return clahe, otsu

    @staticmethod
    def _confidence(data: dict[str, Any]) -> float:
        values = []
        for value in data.get("conf", []):
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number >= 0:
                values.append(number / 100.0)
        return min(1.0, sum(values) / len(values)) if values else 0.0
