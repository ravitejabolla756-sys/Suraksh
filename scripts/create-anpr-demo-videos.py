"""Create synthetic-input ANPR videos without modifying the source videos.

The only synthetic content added is a visible test plate and watermark. Vehicle
locations are selected from real YOLO detections in the source frames.
"""

from pathlib import Path
import os

import cv2
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "demo-media"
MODEL_PATH = os.getenv("SURAKSH_YOLO_MODEL", str(ROOT / "yolo26s.pt"))
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
PLATE = "GJ01AB1234"


def largest_vehicle(result):
    best = None
    for box in result.boxes:
        cls = int(box.cls[0])
        if cls not in VEHICLE_CLASSES:
            continue
        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
        area = max(0, x2 - x1) * max(0, y2 - y1)
        if best is None or area > best[0]:
            best = (area, (x1, y1, x2, y2), VEHICLE_CLASSES[cls], float(box.conf[0]))
    return best


def draw_plate(frame, bbox):
    x1, y1, x2, y2 = bbox
    width, height = x2 - x1, y2 - y1
    plate_w = max(120, min(int(width * 0.62), width - 8))
    plate_h = max(24, min(int(height * 0.16), 52))
    px1 = max(x1 + 4, x1 + (width - plate_w) // 2)
    py1 = max(y1 + 4, y1 + int(height * 0.68))
    if py1 + plate_h >= y2 - 3:
        py1 = max(y1 + 4, y2 - plate_h - 4)
    px2, py2 = min(x2 - 4, px1 + plate_w), min(y2 - 3, py1 + plate_h)
    overlay = frame.copy()
    cv2.rectangle(overlay, (px1, py1), (px2, py2), (255, 255, 255), -1)
    cv2.addWeighted(overlay, 0.96, frame, 0.04, 0, frame)
    cv2.rectangle(frame, (px1, py1), (px2, py2), (20, 20, 20), 2)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = max(0.35, min(1.2, (px2 - px1) / 230))
    thickness = max(1, int(scale * 2))
    (tw, th), _ = cv2.getTextSize(PLATE, font, scale, thickness)
    cv2.putText(frame, PLATE, (px1 + max(3, (px2 - px1 - tw) // 2), py1 + (py2 - py1 + th) // 2 - 2), font, scale, (10, 10, 10), thickness, cv2.LINE_AA)
    return (px1, py1, px2, py2)


def watermark(frame):
    text = "SYNTHETIC PLATE - HACKATHON TEST MEDIA"
    cv2.rectangle(frame, (8, 8), (390, 38), (15, 15, 15), -1)
    cv2.putText(frame, text, (14, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 220, 255), 1, cv2.LINE_AA)


def create(source: Path, destination: Path):
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open source: {source}")
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Cannot create output: {destination}")
    model = YOLO(MODEL_PATH)
    last_bbox = None
    detected = 0
    frame_no = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_no % 5 == 0:
            result = model.predict(frame, classes=list(VEHICLE_CLASSES), verbose=False)[0]
            match = largest_vehicle(result)
            if match:
                last_bbox = match[1]
                detected += 1
        watermark(frame)
        if last_bbox:
            draw_plate(frame, last_bbox)
        writer.write(frame)
        frame_no += 1
    cap.release()
    writer.release()
    if frame_no == 0 or detected == 0:
        raise RuntimeError(f"No vehicle detection found in {source}")
    print(f"PASS source={source} output={destination} frames={frame_no} sampled_vehicle_detections={detected} fps={fps:.3f}")


if __name__ == "__main__":
    MEDIA.mkdir(parents=True, exist_ok=True)
    create(MEDIA / "vms-a.mp4", MEDIA / "anpr-vms-a.mp4")
    create(MEDIA / "vms-b.mp4", MEDIA / "anpr-vms-b.mp4")
