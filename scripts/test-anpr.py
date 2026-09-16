"""Run genuine YOLO vehicle detection followed by EasyOCR on plate crops."""

from pathlib import Path
import json
import os
import re

import cv2
import easyocr
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "demo-media"
EVIDENCE = ROOT / ".runtime" / "anpr"
MODEL_PATH = os.getenv("SURAKSH_YOLO_MODEL", str(ROOT / "yolo26s.pt"))
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def normalize(text):
    value = re.sub(r"[^A-Z0-9]", "", text.upper())
    return value if re.fullmatch(r"[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{1,4}", value) else None


def plate_crop(frame, bbox):
    x1, y1, x2, y2 = bbox
    width, height = x2 - x1, y2 - y1
    px1 = max(x1 + 4, x1 + int(width * 0.19))
    px2 = min(x2 - 4, x1 + int(width * 0.81))
    py1 = max(y1 + 4, y1 + int(height * 0.60))
    py2 = min(y2 - 3, y1 + int(height * 0.90))
    return frame[py1:py2, px1:px2], (px1, py1, px2, py2)


def run(video: Path):
    name = video.stem
    out = EVIDENCE / name
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {video}")
    model = YOLO(MODEL_PATH)
    ocr_error = None
    try:
        reader = easyocr.Reader(
            ["en"],
            gpu=False,
            verbose=False,
            model_storage_directory=str(ROOT / ".runtime" / "easyocr"),
            user_network_directory=str(ROOT / ".runtime" / "easyocr"),
        )
    except Exception as exc:
        reader = None
        ocr_error = f"EasyOCR model initialization failed: {exc}"
        print(ocr_error)
    frames = detections = attempts = 0
    best = None
    best_area = -1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames += 1
        if frames % 3:
            continue
        result = model.predict(frame, classes=list(VEHICLE_CLASSES), verbose=False)[0]
        annotated = result.plot()
        cv2.imwrite(str(out / "yolo-annotated-best.jpg"), annotated)
        for box in result.boxes:
            cls = int(box.cls[0])
            if cls not in VEHICLE_CLASSES:
                continue
            x1, y1, x2, y2 = [max(0, int(v)) for v in box.xyxy[0].tolist()]
            vehicle = frame[y1:y2, x1:x2]
            candidate, coords = plate_crop(frame, (x1, y1, x2, y2))
            if candidate.size == 0 or vehicle.size == 0:
                continue
            detections += 1
            attempts += 1
            area = max(0, x2 - x1) * max(0, y2 - y1)
            if best is None or area > best_area:
                best_area = area
                best = {"raw": None, "normalized": None, "confidence": 0.0, "vehicle_class": VEHICLE_CLASSES[cls], "frame": frames, "bbox": [x1, y1, x2, y2]}
                cv2.imwrite(str(out / "source-frame-best.jpg"), frame)
                cv2.imwrite(str(out / "vehicle-crop-best.jpg"), vehicle)
                cv2.imwrite(str(out / "plate-crop-best.jpg"), candidate)
            if reader is None:
                continue
            enlarged = cv2.resize(candidate, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            variants = [enlarged, cv2.threshold(cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]]
            for variant in variants:
                results = reader.readtext(variant, detail=1, paragraph=False, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
                raw = " ".join(str(item[1]) for item in results).strip()
                confidence = max((float(item[2]) for item in results), default=0.0)
                normalized = normalize(raw)
                if best is None or (normalized is not None and confidence > best["confidence"]):
                    best = {"raw": raw, "normalized": normalized, "confidence": confidence, "vehicle_class": VEHICLE_CLASSES[cls], "frame": frames, "bbox": [x1, y1, x2, y2]}
                    cv2.imwrite(str(out / "source-frame-best.jpg"), frame)
                    cv2.imwrite(str(out / "vehicle-crop-best.jpg"), vehicle)
                    cv2.imwrite(str(out / "plate-crop-best.jpg"), candidate)
    cap.release()
    result = {"video": str(video), "frames_decoded": frames, "vehicle_detections": detections, "ocr_attempts": attempts, "ocr_error": ocr_error, "best": best}
    (out / "ocr-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    results = [run(MEDIA / "anpr-vms-a.mp4"), run(MEDIA / "anpr-vms-b.mp4")]
    if not all(item["best"] and item["best"]["normalized"] == "GJ01AB1234" for item in results):
        raise SystemExit("ANPR FAIL: EasyOCR did not genuinely recognize GJ01AB1234 from both generated videos")
    print("ANPR PASS: both generated videos produced the expected normalized plate from EasyOCR")
