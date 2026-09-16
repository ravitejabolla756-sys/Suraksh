"""Two local, schema-distinct VMS inventory adapters for recorded demo sources.

No detection/event fixture is served. AI evidence comes from anpr_runtime.py.
"""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]


def serve(source: str):
    port = 8091 if source == "A" else 8092
    video = ROOT / "demo-media" / f"anpr-vms-{source.lower()}.mp4"
    external = "AHM-DEMO-01" if source == "A" else "AHM-DEMO-02"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            cap = cv2.VideoCapture(str(video))
            try:
                readable = cap.isOpened() and cap.read()[0]
            finally:
                cap.release()
            now = datetime.now(timezone.utc).isoformat()
            status = "ONLINE" if readable else "OFFLINE"
            endpoint = f"http://127.0.0.1:8000/demo-media/{video.name}"
            if self.path == "/health":
                payload = {"status": "CONNECTED", "source": f"VMS-{source}", "video_readable": readable, "is_demo": True}
            elif source == "A":
                payload = {"system": "VMS_A", "cameras": [{"camera": external, "name": external + " DEMO / SYNTHETIC", "stream": endpoint, "status": status, "last_heartbeat": now}], "events": []}
            else:
                payload = {"system": "VMS_B", "devices": [{"deviceId": external, "label": external + " DEMO / SYNTHETIC", "hlsUrl": endpoint, "health": status, "lastSeen": now}], "records": []}
            payload["notice"] = "DEMO RECORDED CCTV SOURCE; inventory only; no synthetic detection records"
            encoded = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_):
            return

    print(f"VMS-{source} local inventory: http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["A", "B"], required=True)
    serve(parser.parse_args().source)
