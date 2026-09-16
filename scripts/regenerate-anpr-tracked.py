"""Regenerate synthetic ANPR inputs with one locked Ultralytics vehicle track.

The source videos are read only. A plate is drawn only when the selected
track ID is present in that exact tracked frame; no last-known box is reused.
"""
from collections import defaultdict
import json
import os
from pathlib import Path
import cv2
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "demo-media"
EVIDENCE = ROOT / ".runtime" / "anpr"
MODEL_PATH = os.getenv("SURAKSH_YOLO_MODEL", str(ROOT / "yolo26s.pt"))
VEHICLES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
PLATE = "GJ01AB1234"
WATERMARK = "SYNTHETIC PLATE - HACKATHON TEST MEDIA"


def box_tuple(box):
    return tuple(max(0, int(v)) for v in box.xyxy[0].tolist())


def collect_tracks(source, model):
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open source {source}")
    frames, tracks = [], defaultdict(list)
    frame_index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            result = model.track(frame, persist=True, classes=list(VEHICLES), tracker="bytetrack.yaml", verbose=False)[0]
            frame_tracks = []
            ids = result.boxes.id
            for position, box in enumerate(result.boxes):
                cls = int(box.cls[0])
                if cls not in VEHICLES or ids is None:
                    continue
                track_id = int(ids[position])
                bbox = box_tuple(box)
                x1, y1, x2, y2 = bbox
                area = max(0, x2 - x1) * max(0, y2 - y1)
                record = {"frame": frame_index, "track_id": track_id, "vehicle_class": VEHICLES[cls],
                          "bbox": list(bbox), "area": area, "confidence": float(box.conf[0])}
                tracks[track_id].append(record)
                frame_tracks.append(record)
            frames.append(frame_tracks)
            frame_index += 1
    finally:
        cap.release()
    if not frames:
        raise RuntimeError(f"No frames decoded from {source}")
    return frames, tracks


def longest_run(items):
    indexes = sorted(item["frame"] for item in items)
    best = current = 1 if indexes else 0
    for previous, current_index in zip(indexes, indexes[1:]):
        current = current + 1 if current_index == previous + 1 else 1
        best = max(best, current)
    return best


def select_target(frames, tracks, probe_frame):
    candidates = []
    for track_id, items in tracks.items():
        classes = [item["vehicle_class"] for item in items]
        vehicle_class = max(set(classes), key=classes.count)
        visible = len(items)
        average_area = sum(item["area"] for item in items) / max(visible, 1)
        longest = longest_run(items)
        probe = next((item for item in items if item["frame"] == probe_frame), None)
        # A probe-visible target keeps the deterministic OCR frame usable when
        # possible. The choice still depends on real tracking metadata only.
        score = (1 if vehicle_class == "car" else 0, 1 if probe else 0,
                 longest, visible, average_area)
        candidates.append((score, track_id, vehicle_class, items, probe))
    if not candidates:
        raise RuntimeError("No stable vehicle tracks found")
    _, track_id, vehicle_class, items, probe = max(candidates, key=lambda value: value[0])
    return {"target_track_id": track_id, "vehicle_class": vehicle_class,
            "first_frame": items[0]["frame"], "last_frame": items[-1]["frame"],
            "visible_frames": len(items), "longest_consecutive_run": longest_run(items),
            "average_box_size": round(sum(item["area"] for item in items) / len(items), 2),
            "probe_frame": probe_frame, "probe_visible": bool(probe),
            "track_records": items}


def draw_plate(frame, bbox):
    x1, y1, x2, y2 = bbox
    width, height = x2 - x1, y2 - y1
    plate_w = max(120, min(int(width * 0.78), width - 12))
    plate_h = max(30, min(int(height * 0.21), 64))
    px1 = max(x1 + 6, x1 + (width - plate_w) // 2)
    py1 = max(y1 + 6, y1 + int(height * 0.69))
    if py1 + plate_h >= y2 - 5:
        py1 = max(y1 + 5, y2 - plate_h - 5)
    px2, py2 = min(x2 - 5, px1 + plate_w), min(y2 - 4, py1 + plate_h)
    cv2.rectangle(frame, (px1, py1), (px2, py2), (255, 255, 255), -1)
    cv2.rectangle(frame, (px1, py1), (px2, py2), (18, 18, 18), 2)
    font = cv2.FONT_HERSHEY_DUPLEX
    scale = max(0.48, min(1.45, (px2 - px1) / 190))
    thickness = max(1, int(scale * 2.1))
    (tw, th), _ = cv2.getTextSize(PLATE, font, scale, thickness)
    tx = px1 + max(4, (px2 - px1 - tw) // 2)
    ty = py1 + (py2 - py1 + th) // 2 - 2
    cv2.putText(frame, PLATE, (tx, ty), font, scale, (8, 8, 8), thickness, cv2.LINE_AA)
    return [px1, py1, px2, py2]


def watermark(frame):
    cv2.rectangle(frame, (8, 8), (390, 38), (15, 15, 15), -1)
    cv2.putText(frame, WATERMARK, (14, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 220, 255), 1, cv2.LINE_AA)


def render(source_name, probe_frame):
    source = MEDIA / f"vms-{source_name.lower()}.mp4"
    destination = MEDIA / f"anpr-vms-{source_name.lower()}.mp4"
    model = YOLO(MODEL_PATH)
    frames, tracks = collect_tracks(source, model)
    target = select_target(frames, tracks, probe_frame)
    target_id = target["target_track_id"]
    cap = cv2.VideoCapture(str(source))
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Cannot create {destination}")
    rendered = []
    frame_index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            current = next((item for item in frames[frame_index] if item["track_id"] == target_id), None)
            watermark(frame)
            if current:
                plate_bbox = draw_plate(frame, current["bbox"])
                rendered.append({"frame": frame_index, "track_id": target_id, "vehicle_bbox": current["bbox"], "plate_bbox": plate_bbox})
            writer.write(frame)
            frame_index += 1
    finally:
        cap.release()
        writer.release()
    metadata = {"source": f"VMS-{source_name}", "source_video": str(source.resolve()),
                "output_video": str(destination.resolve()), "synthetic_plate": PLATE,
                "watermark": WATERMARK, "target_track_id": target_id,
                "vehicle_class": target["vehicle_class"], "first_frame": target["first_frame"],
                "last_frame": target["last_frame"], "visible_frames": target["visible_frames"],
                "longest_consecutive_run": target["longest_consecutive_run"],
                "average_box_size": target["average_box_size"], "probe_frame": probe_frame,
                "probe_visible": target["probe_visible"], "rendered_plate_frames": len(rendered),
                "source_frame_count": len(frames), "rendered_frames": rendered}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / f"target-tracking-vms-{source_name.lower()}.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({k: metadata[k] for k in ("source", "target_track_id", "vehicle_class", "first_frame", "last_frame", "longest_consecutive_run", "average_box_size", "rendered_plate_frames")}, indent=2))
    return metadata


if __name__ == "__main__":
    render("A", 299)
    render("B", 80)
