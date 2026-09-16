import re
from typing import Any


class PlateReader:
    """Optional local OCR adapter. Failure is represented as no plate text."""

    def __init__(self) -> None:
        self.engine: Any = None
        try:
            from paddleocr import PaddleOCR

            self.engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        except Exception as exc:
            print(f"OCR unavailable: {exc}")

    def read(self, frame) -> tuple[str | None, float | None, str]:
        if self.engine is None:
            return None, None, "unavailable"
        try:
            result = self.engine.ocr(frame, cls=True)
            candidates: list[tuple[str, float]] = []
            for line in result or []:
                for item in line or []:
                    text, score = item[1]
                    normalized = re.sub(r"[^A-Za-z0-9]", "", str(text)).upper()
                    if normalized:
                        candidates.append((normalized, float(score)))
            if not candidates:
                return None, None, "uncertain"
            value, confidence = max(candidates, key=lambda candidate: candidate[1])
            return value, confidence, "read"
        except Exception as exc:
            print(f"OCR attempt failed: {exc}")
            return None, None, "error"
