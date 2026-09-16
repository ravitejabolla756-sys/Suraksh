from datetime import datetime, timezone
import os
from typing import Any

from app.config import EdgeConfig, SourceConfig
from app.ocr import PlateReader

try:
    import cv2
except ImportError:  # pragma: no cover - dependency is installed in the edge image
    cv2 = None


class FrameDetector:
    """Decode real source frames and run an optional local YOLO vehicle model.

    A missing model or unreachable stream produces an explicit unavailable result;
    it never manufactures a detection event.
    """

    def __init__(self, config: EdgeConfig) -> None:
        self.config = config
        self.model: Any = None
        self.ocr = PlateReader()
        self.health: dict[str, dict[str, Any]] = {}
        self.model_path = os.getenv("SURAKSH_YOLO_MODEL", "")
        self.inference_every_n_frames = max(1, int(os.getenv("SURAKSH_INFERENCE_EVERY_N_FRAMES", "5")))
        self.frame_count: dict[str, int] = {}
        if self.model_path:
            try:
                from ultralytics import YOLO

                self.model = YOLO(self.model_path)
            except Exception as exc:
                print(f"YOLO unavailable: {exc}")

    def next_detections(self) -> list[dict[str, Any]]:
        if cv2 is None:
            print("OpenCV unavailable; no frames processed")
            return []
        detections: list[dict[str, Any]] = []
        for source in self.config.sources:
            frame = self._read_frame(source)
            if frame is None:
                continue
            count = self.frame_count.get(source.camera_id, 0) + 1
            self.frame_count[source.camera_id] = count
            if count % self.inference_every_n_frames != 0:
                continue
            detections.extend(self._infer(source, frame))
        return detections

    def health_updates(self) -> list[dict[str, Any]]:
        return list(self.health.values())

    def _read_frame(self, source: SourceConfig):
        capture = cv2.VideoCapture(source.source_url)
        if not capture.isOpened():
            print(f"STREAM UNAVAILABLE: {source.name} ({source.source_url})")
            self.health[source.camera_id] = {"camera_id": source.camera_id, "health_status": "OFFLINE", "stream_status": "OFFLINE", "stream_reachable": False, "failure_count": 1}
            capture.release()
            return None
        ok, frame = capture.read()
        capture.release()
        if not ok or frame is None:
            print(f"FRAME UNAVAILABLE: {source.name}")
            self.health[source.camera_id] = {"camera_id": source.camera_id, "health_status": "DEGRADED", "stream_status": "DEGRADED", "stream_reachable": True, "failure_count": 1}
            return None
        height, width = frame.shape[:2]
        self.health[source.camera_id] = {"camera_id": source.camera_id, "health_status": "ONLINE", "stream_status": "ONLINE", "stream_reachable": True, "failure_count": 0, "resolution": f"{width}x{height}"}
        return frame

    def _infer(self, source: SourceConfig, frame) -> list[dict[str, Any]]:
        if self.model is None:
            print(f"MODEL UNAVAILABLE: decoded frame received from {source.name}; configure SURAKSH_YOLO_MODEL")
            return []
        results = self.model.predict(frame, classes=[2, 3, 5, 7], verbose=False)
        events: list[dict[str, Any]] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                confidence = float(box.conf[0])
                coordinates = [round(float(value), 2) for value in box.xyxy[0].tolist()]
                x1, y1, x2, y2 = [max(0, int(value)) for value in coordinates]
                plate_text, plate_confidence, ocr_status = self.ocr.read(frame[y1:y2, x1:x2])
                events.append({
                    "camera_id": source.camera_id,
                    "department_id": source.department_id,
                    "source_system": self.config.edge_server_id,
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    "vehicle_class": "vehicle",
                    "vehicle_confidence": confidence,
                    "plate_text": plate_text,
                    "plate_confidence": plate_confidence,
                    "metadata": {"bbox": coordinates, "ocr_status": ocr_status},
                    "is_demo": True,
                })
        return events
