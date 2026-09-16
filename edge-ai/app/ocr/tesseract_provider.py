"""Local Tesseract OCR provider with deterministic plate preprocessing."""

from dataclasses import asdict, dataclass
import re
from typing import Any

import cv2
import numpy as np


@dataclass
class OCRResult:
    raw_text: str | None
    normalized_text: str | None
    confidence: float
    provider: str
    success: bool


def normalize_plate(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"[^A-Z0-9]", "", value.upper())
    # Correct only positionally unambiguous OCR confusions in the state prefix
    # and numeric portions; never turn arbitrary text into the expected plate.
    if len(text) >= 2:
        text = text[0] + text[1].replace("0", "O")
    if len(text) >= 4:
        chars = list(text)
        for index in (2, 3):
            if index < len(chars) and chars[index] in "OI":
                chars[index] = "0" if chars[index] == "O" else "1"
        text = "".join(chars)
    if not re.fullmatch(r"[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{1,4}", text):
        return None
    return text


class TesseractProvider:
    provider = "tesseract"

    def __init__(self, executable: str | None = None) -> None:
        import pytesseract

        self.pytesseract = pytesseract
        if executable:
            self.pytesseract.pytesseract.tesseract_cmd = executable

    @staticmethod
    def variants(image: np.ndarray) -> list[np.ndarray]:
        enlarged = cv2.resize(image, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        sharpened = cv2.addWeighted(clahe, 1.4, cv2.GaussianBlur(clahe, (0, 0), 1.0), -0.4, 0)
        threshold = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        return [image, enlarged, gray, clahe, threshold, sharpened]

    def recognize(self, image: np.ndarray) -> OCRResult:
        best: dict[str, Any] | None = None
        config = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        for variant in self.variants(image):
            data = self.pytesseract.image_to_data(variant, config=config, output_type=self.pytesseract.Output.DICT)
            words = [str(text).strip() for text in data.get("text", []) if str(text).strip()]
            raw = " ".join(words)
            confidences = [float(value) for value in data.get("conf", []) if float(value) >= 0]
            confidence = sum(confidences) / len(confidences) / 100 if confidences else 0.0
            candidate = {"raw_text": raw or None, "normalized_text": normalize_plate(raw), "confidence": confidence}
            if best is None or (candidate["normalized_text"] and not best["normalized_text"]) or candidate["confidence"] > best["confidence"]:
                best = candidate
        if best is None:
            return OCRResult(None, None, 0.0, self.provider, False)
        return OCRResult(**best, provider=self.provider, success=bool(best["normalized_text"]))


def result_dict(result: OCRResult) -> dict[str, Any]:
    return asdict(result)
