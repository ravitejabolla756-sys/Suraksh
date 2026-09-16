"""Benchmark the installed detector across model/input-size options.

This is an evidence script, not an automatic model switch. Missing yolo11s is
reported as unavailable and no weights are downloaded.
"""

import json
import os
from pathlib import Path
import time

import cv2
import torch
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
CLASS_IDS = [0, 2, 3, 5, 7]


def sample_frames(source: str):
    cap = cv2.VideoCapture(str(ROOT / "demo-media" / f"anpr-vms-{source.lower()}.mp4"))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    indices = [int(total * ratio) for ratio in (0.2, 0.45, 0.7, 0.9)]
    frames = []
    for index in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    cap.release()
    return frames


def run(model_path: Path, imgsz: int, frames: list):
    model = YOLO(str(model_path))
    timings, counts = [], []
    for frame in frames:
        started = time.perf_counter()
        result = model.predict(frame, classes=CLASS_IDS, imgsz=imgsz, device=0 if torch.cuda.is_available() else "cpu", verbose=False)[0]
        timings.append((time.perf_counter() - started) * 1000)
        counts.append(len(result.boxes) if result.boxes is not None else 0)
    return {"model": model_path.name, "imgsz": imgsz, "device": "CUDA" if torch.cuda.is_available() else "CPU", "average_inference_ms": round(sum(timings) / len(timings), 1), "effective_fps": round(1000 / (sum(timings) / len(timings)), 2), "detections_per_frame": [int(value) for value in counts]}


def main():
    results = {"device": "CUDA" if torch.cuda.is_available() else "CPU", "torch_cuda": bool(torch.cuda.is_available()), "runs": []}
    models = [ROOT / "yolo11n.pt", ROOT / "yolo11s.pt"]
    for model_path in models:
        if not model_path.is_file():
            results["runs"].append({"model": model_path.name, "status": "UNAVAILABLE_LOCAL_WEIGHTS"})
            continue
        for imgsz in (640, 768, 960):
            for source in ("A", "B"):
                results["runs"].append({"source": source, **run(model_path, imgsz, sample_frames(source))})
    output = ROOT / ".runtime" / "phase6" / "benchmark.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
