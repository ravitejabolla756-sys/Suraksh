"""Capture one current JPEG from each local annotated preview stream."""
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".runtime" / "phase5" / "viewer-evidence"
OUT.mkdir(parents=True, exist_ok=True)

for source, target in (("anpr-vms-a.mp4", "vms-a-yolo-tracking.jpg"), ("anpr-vms-b.mp4", "vms-b-yolo-tracking.jpg")):
    response = requests.get(f"http://127.0.0.1:8000/demo-media/{source}/preview", stream=True, timeout=90)
    response.raise_for_status()
    buffer = b""
    for chunk in response.iter_content(chunk_size=65536):
        buffer += chunk
        start = buffer.find(b"\xff\xd8")
        end = buffer.find(b"\xff\xd9", start + 2)
        if start >= 0 and end >= 0:
            path = OUT / target
            path.write_bytes(buffer[start:end + 2])
            print(path)
            break
    response.close()
