"""Run real YOLO11 ByteTrack analytics over both recorded demo sources.

No values are seeded: every count originates from YOLO.track result boxes and
anonymous track IDs. The optional --ingest flag persists minute buckets via the
authenticated analytics API.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import httpx
import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "edge-ai"))
from app.analytics import AnalyticsSession  # noqa: E402
from app.tracking import AnonymousTracker, result_detections  # noqa: E402

MODEL = ROOT / "yolo11n.pt"
CLASS_IDS = [0, 2, 3, 5, 7]


def run_source(source: str, model: YOLO):
    video = ROOT / "demo-media" / f"anpr-vms-{source.lower()}.mp4"
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot decode {video}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    sample_indices = np.linspace(0, total - 1, 12, dtype=int).tolist()
    sample_set = set(sample_indices)
    tracker = AnonymousTracker(f"AHM-DEMO-0{'1' if source == 'A' else '2'}")
    session = AnalyticsSession(tracker.camera_id, "", f"VMS-{source}")
    run_started = datetime.now(timezone.utc)
    samples = []
    frame_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        result = model.track(frame, persist=True, classes=CLASS_IDS, tracker="bytetrack.yaml", verbose=False)[0]
        detections = result_detections(result)
        now = run_started + timedelta(seconds=frame_index / fps)
        snapshot = tracker.update(detections, now)
        session.ingest(snapshot, now)
        if frame_index in sample_set:
            annotated = result.plot()
            cv2.putText(annotated, f"VMS-{source} frame {frame_index}  people={snapshot['visible']['people']} vehicles={snapshot['visible']['vehicles']}", (18, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(annotated, f"VMS-{source} frame {frame_index}  people={snapshot['visible']['people']} vehicles={snapshot['visible']['vehicles']}", (18, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
            samples.append({"frame": frame_index, "model": snapshot["visible"], "annotated": annotated})
        frame_index += 1
    cap.release()
    buckets = list(session.buckets.values())
    return {"source": source, "video": str(video), "frames_decoded": frame_index, "fps": fps,
            "sample_indices": sample_indices, "samples": samples, "final": tracker.snapshot(),
            "buckets": buckets, "unique_track_ids": {label: sorted(state.track_id for state in tracker.tracks.values() if state.object_class == label) for label in ("person", "car", "motorcycle", "bus", "truck")}}


def save_contact_sheet(source, samples):
    tiles = [cv2.resize(item["annotated"], (640, 360), interpolation=cv2.INTER_AREA) for item in samples]
    blank = np.zeros_like(tiles[0])
    rows = []
    for offset in range(0, len(tiles), 3):
        row = tiles[offset:offset + 3]
        rows.append(np.hstack(row + [blank] * (3 - len(row))))
    path = ROOT / ".runtime" / "phase5" / f"analytics-review-vms-{source.lower()}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 92])
    return path


def ingest(results):
    from local_runtime import environment
    os.environ.update(environment())
    base = "http://127.0.0.1:8000"
    with httpx.Client(base_url=base, timeout=30) as client:
        token = client.post("/auth/login", json={"email": "admin@suraksh.demo", "password": "Suraksh123!"}).raise_for_status()
        access = client.post("/auth/login", json={"email": "admin@suraksh.demo", "password": "Suraksh123!"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {access}"}
        cameras = client.get("/cameras", headers=headers).json()
        machine = {"X-Edge-Key": os.environ["SURAKSH_EDGE_INGEST_KEY"]}
        for result in results:
            external = f"AHM-DEMO-0{'1' if result['source'] == 'A' else '2'}"
            camera = next(camera for camera in cameras if camera["external_id"] == external)
            for bucket in result["buckets"]:
                bucket["camera_id"] = camera["id"]
                bucket["department_id"] = camera["department_id"]
                client.post("/analytics/ingest", headers=machine, json=bucket).raise_for_status()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ingest", action="store_true")
    args = parser.parse_args()
    model = YOLO(str(MODEL))
    results = [run_source(source, model) for source in ("A", "B")]
    serializable = []
    for result in results:
        result["contact_sheet"] = str(save_contact_sheet(result["source"], result["samples"]))
        serializable.append({key: value for key, value in result.items() if key != "samples"})
    output = ROOT / ".runtime" / "phase5" / "analytics-results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    if args.ingest:
        ingest(results)
    print(json.dumps(serializable, indent=2))


if __name__ == "__main__":
    main()
