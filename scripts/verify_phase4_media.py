"""Check recorded-preview bytes from both actual HTTP streams, without a browser."""
import hashlib
import json
from pathlib import Path
import re

import cv2
import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def verify():
    results = []
    for source in ("a", "b"):
        frames = []
        with httpx.stream("GET", f"http://127.0.0.1:8000/demo-media/anpr-vms-{source}.mp4/preview", timeout=20) as response:
            response.raise_for_status()
            data = b""
            for chunk in response.iter_bytes():
                data += chunk
                while b"\r\n\r\n" in data:
                    boundary = data.index(b"\r\n\r\n")
                    header = data[:boundary]
                    match = re.search(rb"Content-Length: (\d+)", header)
                    if not match:
                        raise AssertionError("Preview has no frame length")
                    size = int(match[1])
                    if len(data) < boundary + 4 + size:
                        break
                    jpeg = data[boundary + 4:boundary + 4 + size]
                    data = data[boundary + 4 + size + 2:]
                    frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    assert frame is not None
                    index = int(re.search(rb"X-Frame-Index: (\d+)", header)[1])
                    frames.append({"index": index, "width": frame.shape[1], "height": frame.shape[0], "sha256": hashlib.sha256(jpeg).hexdigest()})
                if len(frames) >= 3:
                    break
        assert len(frames) >= 3 and len({f["sha256"] for f in frames}) >= 2
        assert frames[-1]["index"] > frames[0]["index"]
        results.append({"source": source, "frames": frames, "pass": True})
        print(f"PASS VMS-{source.upper()}: 3+ different decoded JPEG frames delivered over HTTP")
    (ROOT / ".runtime" / "phase4" / "media-verification.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    verify()
