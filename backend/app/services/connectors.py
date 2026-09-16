from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class VMSConnector(ABC):
    source_system: str

    @abstractmethod
    def list_cameras(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_camera(self, camera_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def get_stream(self, camera_id: str) -> str | None: ...

    @abstractmethod
    def get_health(self, camera_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def get_events(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def normalize_event(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class VMSAConnector(VMSConnector):
    source_system = "VMS_A"

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def list_cameras(self) -> list[dict[str, Any]]:
        return self.payload.get("cameras", [])

    def get_camera(self, camera_id: str) -> dict[str, Any] | None:
        return next((camera for camera in self.list_cameras() if camera.get("camera") == camera_id), None)

    def get_stream(self, camera_id: str) -> str | None:
        camera = self.get_camera(camera_id)
        return camera.get("stream") if camera else None

    def get_health(self, camera_id: str) -> dict[str, Any]:
        camera = self.get_camera(camera_id) or {}
        return {"status": camera.get("status", "UNKNOWN"), "last_heartbeat": camera.get("last_heartbeat")}

    def get_events(self) -> list[dict[str, Any]]:
        return self.payload.get("events", [])

    def normalize_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "camera_id": payload["camera"],
            "source_system": self.source_system,
            "event_type": "vehicle_detected" if payload.get("type") == "vehicle" else str(payload.get("type", "unknown")),
            "timestamp": payload.get("seen_at") or datetime.now().isoformat(),
            "confidence": float(payload.get("confidence", 0.0)),
            "metadata": {"plate": payload.get("plate")},
        }


class VMSBConnector(VMSConnector):
    source_system = "VMS_B"

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def list_cameras(self) -> list[dict[str, Any]]:
        return self.payload.get("devices", [])

    def get_camera(self, camera_id: str) -> dict[str, Any] | None:
        return next((camera for camera in self.list_cameras() if camera.get("deviceId") == camera_id), None)

    def get_stream(self, camera_id: str) -> str | None:
        camera = self.get_camera(camera_id)
        return camera.get("hlsUrl") if camera else None

    def get_health(self, camera_id: str) -> dict[str, Any]:
        camera = self.get_camera(camera_id) or {}
        return {"status": camera.get("health", "UNKNOWN"), "last_heartbeat": camera.get("lastSeen")}

    def get_events(self) -> list[dict[str, Any]]:
        return self.payload.get("records", [])

    def normalize_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = payload.get("metadata", {})
        return {
            "camera_id": payload["deviceId"],
            "source_system": self.source_system,
            "event_type": "vehicle_detected" if payload.get("eventCode") == "VEHICLE_DETECTED" else str(payload.get("eventCode", "unknown")).lower(),
            "timestamp": payload.get("timestamp") or datetime.now().isoformat(),
            "confidence": float(metadata.get("confidence", 0.0)),
            "metadata": {"plate": metadata.get("registrationNumber")},
        }
