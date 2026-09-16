import json
from pathlib import Path

import httpx


class CloudClient:
    def __init__(self, backend_url: str, ingest_key: str, buffer_dir: str = "data/buffer") -> None:
        self.backend_url = backend_url.rstrip("/")
        self.ingest_key = ingest_key
        self.buffer_dir = Path(buffer_dir)
        self.buffer_dir.mkdir(parents=True, exist_ok=True)

    def upload_event(self, payload: dict) -> bool:
        try:
            response = httpx.post(f"{self.backend_url}/events/ingest", json=payload, headers={"X-Edge-Key": self.ingest_key}, timeout=10)
            response.raise_for_status()
            print(f"uploaded event {payload['type']} for {payload['camera_id']}")
            return True
        except Exception as exc:
            self._buffer(payload)
            print(f"buffered event because upload failed: {exc}")
            return False

    def upload_detection(self, payload: dict) -> bool:
        try:
            response = httpx.post(f"{self.backend_url}/detections/ingest", json=payload, headers={"X-Edge-Key": self.ingest_key}, timeout=10)
            response.raise_for_status()
            print(f"uploaded vehicle detection for {payload['camera_id']}")
            return True
        except Exception as exc:
            self._buffer(payload)
            print(f"buffered detection because upload failed: {exc}")
            return False

    def upload_health(self, payload: dict) -> bool:
        try:
            response = httpx.post(f"{self.backend_url}/registry/health/{payload['camera_id']}", json=payload, headers={"X-Edge-Key": self.ingest_key}, timeout=10)
            response.raise_for_status()
            return True
        except Exception as exc:
            print(f"health update failed for {payload['camera_id']}: {exc}")
            return False

    def flush_buffer(self) -> None:
        for path in sorted(self.buffer_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            try:
                path = "/detections/ingest" if "vehicle_class" in payload else "/events/ingest"
                response = httpx.post(f"{self.backend_url}{path}", json=payload, headers={"X-Edge-Key": self.ingest_key}, timeout=10)
                response.raise_for_status()
                path.unlink()
                print(f"flushed buffered event {path.name}")
            except Exception as exc:
                print(f"still buffered {path.name}: {exc}")
                return

    def _buffer(self, payload: dict) -> None:
        event_name = payload.get("type", payload.get("vehicle_class", "detection"))
        timestamp = payload.get("edge_detected_at", payload.get("detected_at", "unknown"))
        file_name = f"{payload['camera_id']}_{event_name}_{timestamp.replace(':', '-')}.json"
        (self.buffer_dir / file_name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
