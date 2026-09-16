"""Render evidence pages from a successful runtime report and its actual images.

These are explicitly labelled inference reports, not mock application screens.
"""
import argparse
from html import escape
import json
from pathlib import Path
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]


def build(run_id: str):
    folder = ROOT / ".runtime" / "phase4" / str(uuid.UUID(run_id))
    report = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    if not report["success"]:
        raise RuntimeError("Cannot publish evidence for an unsuccessful E2E run")
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=20) as client:
        token = client.post("/auth/login", json={"email": "admin@suraksh.demo", "password": "Suraksh123!"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        plate = report["observations"][0]["plate_text"]
        snapshot = {}
        for key, endpoint in {"detections": "/detections?plate=" + plate, "path": "/investigations/path?plate=" + plate,
                              "alerts": "/alerts", "audit": "/audit", "health": "/registry/health", "summary": "/analytics/summary"}.items():
            response = client.get(endpoint, headers=headers)
            response.raise_for_status()
            snapshot[key] = response.json()
    (folder / "api-final-snapshot.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    head = '''<!doctype html><html lang="en"><meta charset="utf-8"><title>SURAKSH real inference evidence</title>
    <style>body{margin:0;padding:32px;background:#0c141b;color:#e5edf3;font:15px system-ui}h1{font-size:25px}h2{font-size:19px;color:#42d392}p{line-height:1.5}main{display:grid;grid-template-columns:1fr 1fr;gap:24px}section{min-width:0;padding:20px;border:1px solid #30404a;background:#111d26}img{display:block;width:100%;object-fit:contain;margin:12px 0}.plate{background:#fff;max-height:130px}small{color:#a8bbc7;overflow-wrap:anywhere}strong{color:#42d392}.notice{color:#f2b84b}dl{display:grid;grid-template-columns:150px 1fr;gap:10px}dd{margin:0;overflow-wrap:anywhere}dt{color:#a8bbc7}</style><body>'''
    sources = [r for r in report["observations"] if r["tag"] in ("vms-a", "vms-b")]
    overview = head + '<h1>SURAKSH · Real YOLO11n inference evidence</h1><p class="notice">DEMO / SYNTHETIC INPUT — actual decoded frames, model boxes and OCR artifacts</p><main>'
    for number, row in enumerate(sources, 7):
        meta, tag = row["metadata"], row["tag"]
        facts = {"Detection ID": row["id"], "Source": row["source_system"], "Camera": row["camera_name"],
                 "Frame index": meta["frame_index"], "Frames decoded": meta["frames_decoded"], "Vehicle": row["vehicle_class"],
                 "YOLO confidence": f'{row["vehicle_confidence"]:.6f}', "Raw Tesseract OCR": meta["raw_ocr"],
                 "Normalized plate": row["plate_text"], "OCR confidence": f'{row["plate_confidence"]:.2%}',
                 "Preprocessing / PSM": f'{meta["variant"]} / {meta["psm"]}', "Real OCR attempts": meta["ocr_attempts"]}
        fields = "".join(f"<dt>{escape(k)}</dt><dd>{escape(str(v))}</dd>" for k, v in facts.items())
        body = head + f'<h1>SURAKSH · {escape(row["source_system"])} ANPR evidence</h1><p class="notice">DEMO / SYNTHETIC INPUT — replay observation, not a real police record</p><main><section><h2>Actual YOLO-annotated source frame</h2><img src="{tag}/yolo-annotated.png"><h2>Detected vehicle crop</h2><img src="{tag}/vehicle-crop.png"></section><section><h2>Tesseract input crop</h2><img class="plate" src="{tag}/ocr-preprocessed.png"><dl>{fields}</dl><small>Source SHA-256: {meta["source_sha256"]}</small></section></main></body></html>'
        (folder / f"{number:02d}-real-anpr-{tag}.html").write_text(body, encoding="utf-8")
        overview += f'<section><h2>{escape(row["source_system"])}</h2><img src="{tag}/yolo-annotated.png"><p>Frame {meta["frame_index"]} · {meta["vehicle_detections"]} vehicle detections</p><p>Selected {row["vehicle_class"]}: <strong>{row["vehicle_confidence"]:.2%}</strong></p><small>Detection {row["id"]}</small></section>'
    (folder / "06-real-yolo-detection.html").write_text(overview + "</main></body></html>", encoding="utf-8")
    print(f"Evidence pages: {folder}")
    print(f"Final API: {len(snapshot['detections'])} detections, {len(snapshot['path']['points'])} path points, {len(snapshot['alerts'])} alerts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    build(parser.parse_args().run_id)
