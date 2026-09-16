"""Reproducible recorded-frame YOLO/Tesseract observations.

No prior JSON result is read. Every observation originates from a fresh video
decode and OCR call. Test expectations belong to the caller, never the extractor.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from dataclasses import dataclass
from typing import Protocol

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / ".runtime" / "ultralytics"))
Path(os.environ["YOLO_CONFIG_DIR"]).mkdir(parents=True, exist_ok=True)
(ROOT / ".runtime" / "tmp").mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(ROOT / ".runtime" / "tmp")

import cv2
import pytesseract
from ultralytics import YOLO

VEHICLES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def normalize(raw):
    text = re.sub(r"[^A-Z0-9]", "", raw.upper())
    # OCR commonly adds one border/noise glyph and confuses O/0 or I/1.
    # Try only small, plate-agnostic cleanup candidates; never insert the
    # expected plate or replace a failed OCR result with it.
    candidates = [text]
    if len(text) > 10:
        candidates.extend([text[1:], text[:-1]])
    for candidate in candidates:
        for source, target in (("O", "0"), ("Q", "0"), ("I", "1"), ("L", "1")):
            candidate = candidate.replace(source, target)
        if re.fullmatch(r"[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{1,4}", candidate):
            return candidate
    return None


def variants(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    up = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    upgray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(2.0, (8, 8)).apply(upgray)
    sharp = cv2.addWeighted(upgray, 1.4, cv2.GaussianBlur(upgray, (0, 0), 1), -0.4, 0)
    return {"original": crop, "gray": gray, "4x": up, "gray4x": upgray,
            "clahe": clahe, "otsu": cv2.threshold(upgray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1], "sharp": sharp}


@dataclass(frozen=True)
class PlateCandidate:
    crop: object
    bounds: tuple[int, int, int, int]
    quality_score: float
    rejection_reason: str | None = None


class PlateDetector(Protocol):
    """Detector contract; a trained plate model can replace the fallback."""

    name: str

    def detect(self, vehicle):
        """Return candidate crops and quality metadata, never OCR text."""


class HeuristicPlateDetector:
    name = "white-rectangle-fallback"

    def detect(self, vehicle):
        for crop, bounds in plate_candidates(vehicle):
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            contrast = float(gray.std())
            quality = min(1.0, (min(crop.shape[1], 500) / 500) * 0.5 + min(sharpness / 500, 1.0) * 0.3 + min(contrast / 80, 1.0) * 0.2)
            yield PlateCandidate(crop, bounds, quality)


def plate_candidates(vehicle):
    """Find bright rectangular candidates inside the detected vehicle.

    This heuristic is suitable for the white synthetic test input; it is not a
    trained plate detector or a claim of real-world ANPR accuracy.
    """
    mask = cv2.inRange(vehicle, (215, 215, 215), (255, 255, 255))
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    h, w = vehicle.shape[:2]
    for x, y, rw, rh, area in sorted(stats[1:], key=lambda s: int(s[4]), reverse=True):
        if rw < 100 or rh < 18 or not 4 <= rw / rh <= 16 or area < 1000:
            continue
        if y + rh < h * 0.45 or x <= 0 or x + rw >= w:
            continue
        bounds = (max(0, int(x) - 5), max(0, int(y) - 5), min(w, int(x + rw) + 5), min(h, int(y + rh) + 5))
        x1, y1, x2, y2 = bounds
        yield vehicle[y1:y2, x1:x2], bounds


class RuntimeANPR:
    def __init__(self):
        model_path = Path(os.environ.get("SURAKSH_YOLO_MODEL", str(ROOT / "yolo11n.pt")))
        if not model_path.is_file():
            raise RuntimeError(f"YOLO weights missing: {model_path}")
        self.model = YOLO(str(model_path))
        self.model_path = str(model_path.resolve())
        self.plate_detector: PlateDetector = HeuristicPlateDetector()
        pytesseract.pytesseract.tesseract_cmd = os.environ.get("SURAKSH_TESSERACT", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        self.version = str(pytesseract.get_tesseract_version())

    def observe(self, source, frame_index, evidence_dir):
        video = ROOT / "demo-media" / f"anpr-vms-{source.lower()}.mp4"
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot decode {video}")
        fps, total = float(cap.get(cv2.CAP_PROP_FPS)), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame, decoded = None, 0
        try:
            for _ in range(frame_index + 1):
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError(f"Decode failed at frame {decoded}")
                decoded += 1
        finally:
            cap.release()
        started = time.perf_counter()
        prediction = self.model.predict(frame, classes=list(VEHICLES), verbose=False)[0]
        latency = (time.perf_counter() - started) * 1000
        boxes = sorted(prediction.boxes, key=lambda b: float((b.xyxy[0][2]-b.xyxy[0][0])*(b.xyxy[0][3]-b.xyxy[0][1])), reverse=True)
        attempts, observations = [], []
        for box in boxes[:3]:
            x1, y1, x2, y2 = [max(0, int(v)) for v in box.xyxy[0].tolist()]
            vehicle = frame[y1:y2, x1:x2]
            for plate in list(self.plate_detector.detect(vehicle))[:2]:
                candidate, bounds = plate.crop, plate.bounds
                images = variants(candidate)
                rows = []
                for name, img in images.items():
                    for psm in (7, 8, 13):
                        data = pytesseract.image_to_data(img, config=f"--psm {psm} -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", output_type=pytesseract.Output.DICT, timeout=15)
                        tokens = [(str(t).strip(), float(c)) for t, c in zip(data["text"], data["conf"]) if str(t).strip() and float(c) >= 0]
                        raw = " ".join(t for t, _ in tokens)
                        # Mean of nonempty word confidences, scaled from 0..100.
                        confidence = sum(c for _, c in tokens) / (100 * len(tokens)) if tokens else 0.0
                        row = {"raw_text": raw, "normalized_text": normalize(raw), "confidence": confidence, "quality_score": plate.quality_score, "variant": name, "psm": psm}
                        rows.append(row)
                        attempts.append({**row, "vehicle_bbox": [x1, y1, x2, y2], "plate_bbox": list(bounds), "plate_detector": self.plate_detector.name})
                valid = [r for r in rows if r["normalized_text"]]
                if valid:
                    # Consensus then confidence. The expected plate is never used
                    # to select a candidate or to correct recognition output.
                    votes = Counter(r["normalized_text"] for r in valid)
                    best = max(valid, key=lambda r: (votes[r["normalized_text"]], r["confidence"]))
                    observations.append((votes[best["normalized_text"]], best, candidate, images[best["variant"]], vehicle, [x1, y1, x2, y2], float(box.conf[0]), VEHICLES[int(box.cls[0])]))
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "ocr-attempts.json").write_text(json.dumps(attempts, indent=2), encoding="utf-8")
        if not observations:
            raise RuntimeError(f"No valid OCR result for VMS-{source}, frame {frame_index}; {len(attempts)} OCR calls")
        _, best, crop, processed, vehicle, bbox, confidence, cls = max(observations, key=lambda o: (o[0], o[1]["confidence"]))
        evidence = {"source-frame.png": frame, "yolo-annotated.png": prediction.plot(), "vehicle-crop.png": vehicle, "plate-crop.png": crop, "ocr-preprocessed.png": processed}
        for name, img in evidence.items():
            if not cv2.imwrite(str(evidence_dir / name), img):
                raise RuntimeError(f"Evidence write failed: {name}")
        result = {**best, "provider": "tesseract", "source_video": str(video), "source_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
                  "frame_index": frame_index, "frame_time_seconds": frame_index / fps,
                  "frames_decoded": decoded, "total_frames": total, "fps": fps,
                  "vehicle_class": cls, "vehicle_confidence": confidence, "vehicle_bbox": bbox,
                  "vehicle_detections": len(boxes), "ocr_attempts": len(attempts),
                  "detected_at": datetime.now(timezone.utc).isoformat(), "source_system": f"VMS-{source}",
                  "inference_ms": latency, "model": self.model_path, "tesseract_version": self.version,
                  "evidence_dir": str(evidence_dir), "is_demo": True,
                  "notice": "DEMO / SYNTHETIC INPUT; recorded-video replay time, synthetic camera locations"}
        (evidence_dir / "ocr-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["A", "B"], required=True)
    parser.add_argument("--frame", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(RuntimeANPR().observe(args.source, args.frame, ROOT / ".runtime" / "phase4" / f"probe-{args.source}"), indent=2))
