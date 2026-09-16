import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".runtime" / "anpr"


def make_review(source):
    meta = json.loads((OUT / f"target-tracking-vms-{source.lower()}.json").read_text())
    video = ROOT / "demo-media" / f"anpr-vms-{source.lower()}.mp4"
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    samples = np.linspace(0, total - 1, 12, dtype=int).tolist()
    rendered = {int(row["frame"]): row for row in meta["rendered_frames"]}
    tiles = []
    for index in samples:
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = cap.read()
        if not ok:
            continue
        row = rendered.get(index)
        label = f"VMS-{source} frame {index}"
        if row:
            x1, y1, x2, y2 = row["vehicle_bbox"]
            px1, py1, px2, py2 = row["plate_bbox"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 0), 3)
            cv2.rectangle(frame, (px1, py1), (px2, py2), (0, 0, 255), 3)
            label += f"  TARGET track {row['track_id']}"
        else:
            label += "  no synthetic plate"
        cv2.putText(frame, label, (20, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 5, cv2.LINE_AA)
        cv2.putText(frame, label, (20, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
        tile_w = 640
        tile_h = max(1, int(frame.shape[0] * tile_w / frame.shape[1]))
        tiles.append(cv2.resize(frame, (tile_w, tile_h), interpolation=cv2.INTER_AREA))
    cap.release()
    cols = 3
    rows = (len(tiles) + cols - 1) // cols
    blank = np.zeros_like(tiles[0])
    sheet = np.vstack([np.hstack(tiles[i * cols:(i + 1) * cols] + [blank] * (cols - len(tiles[i * cols:(i + 1) * cols]))) for i in range(rows)])
    path = OUT / f"tracking-review-vms-{source.lower()}.jpg"
    cv2.imwrite(str(path), sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(json.dumps({"source": source, "samples": samples, "contact_sheet": str(path), "target_track_id": meta["target_track_id"], "target_only": True}, indent=2))


if __name__ == "__main__":
    make_review("A")
    make_review("B")
