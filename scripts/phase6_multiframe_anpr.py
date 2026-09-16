"""Genuine multi-frame Tesseract consensus for the validated target tracks."""

from collections import Counter
import json
from pathlib import Path
import re
import os
import cv2
import pytesseract

ROOT = Path(__file__).resolve().parents[1]
pytesseract.pytesseract.tesseract_cmd = os.environ.get("SURAKSH_TESSERACT", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
CONFIG = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def normalize(raw: str) -> str | None:
    text = re.sub(r"[^A-Z0-9]", "", raw.upper()).replace("O", "0").replace("I", "1").replace("L", "1")
    if re.fullmatch(r"[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{1,4}", text):
        return text
    return None


def choose_frames(source: str) -> tuple[dict, list[int]]:
    metadata = json.loads((ROOT / ".runtime" / "anpr" / f"target-tracking-vms-{source.lower()}.json").read_text())
    rows = metadata["rendered_frames"]
    return metadata, [rows[round(i * (len(rows) - 1) / 5)]["frame"] for i in range(6)]


def run_source(source: str) -> dict:
    metadata, frames = choose_frames(source)
    video = ROOT / "demo-media" / f"anpr-vms-{source.lower()}.mp4"
    cap = cv2.VideoCapture(str(video))
    rows = []
    for frame_index in frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        if not ok:
            continue
        target = next(item for item in metadata["rendered_frames"] if item["frame"] == frame_index)
        x1, y1, x2, y2 = target["plate_bbox"]
        crop = frame[y1:y2, x1:x2]
        up = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
        variants = {"gray": gray, "otsu": cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]}
        for variant, image in variants.items():
            data = pytesseract.image_to_data(image, config=CONFIG, output_type=pytesseract.Output.DICT, timeout=10)
            tokens = [(text.strip(), float(conf)) for text, conf in zip(data["text"], data["conf"]) if text.strip() and float(conf) >= 0]
            raw = " ".join(text for text, _ in tokens)
            rows.append({"frame_index": frame_index, "track_id": target["track_id"], "variant": variant, "raw_text": raw, "normalized_text": normalize(raw), "confidence": round(sum(conf for _, conf in tokens) / 100 / len(tokens), 4) if tokens else 0.0, "quality_score": round(min(1.0, min(cv2.Laplacian(gray, cv2.CV_64F).var() / 500, 1.0)), 4)})
    cap.release()
    valid = [row for row in rows if row["normalized_text"]]
    votes = Counter(row["normalized_text"] for row in valid)
    winner = votes.most_common(1)[0][0] if votes else None
    selected = [row for row in valid if row["normalized_text"] == winner]
    confidence = sum(row["confidence"] * max(row["quality_score"], 0.01) for row in selected) / sum(max(row["quality_score"], 0.01) for row in selected) if selected else 0.0
    return {"source": source, "track_id": metadata["target_track_id"], "candidate_frames": frames, "ocr_attempts": len(rows), "ocr_candidates": rows, "consensus": winner, "consensus_confidence": round(confidence, 4), "associated_only_with_target_track": bool(winner) and all(row["track_id"] == metadata["target_track_id"] for row in selected), "plate_detector": "validated synthetic fallback crop; no trained local plate model"}


if __name__ == "__main__":
    report = {source: run_source(source) for source in ("A", "B")}
    output = ROOT / ".runtime" / "phase6" / "anpr" / "consensus-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
