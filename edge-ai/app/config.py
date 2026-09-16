from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ZoneConfig(BaseModel):
    id: str
    type: str
    crowd_threshold: int | None = None


class PerCameraPerceptionConfig(BaseModel):
    detector_model: str = "yolo11n.pt"
    detector_resolution: int = 640
    detector_confidence: float = .15
    detector_nms_iou: float = .7
    tracker_type: str = "legacy_iou"
    tracker_thresholds: dict[str, float] = Field(default_factory=dict)
    track_buffer: int = 30
    reid_enabled: bool = False
    fire_smoke_model: str | None = None
    safety_thresholds: dict[str, float] = Field(default_factory=dict)
    mode: str = "realtime"


class SourceConfig(BaseModel):
    camera_id: str
    department_id: str
    name: str
    source_url: str
    zones: list[ZoneConfig] = Field(default_factory=list)
    perception: "PerCameraPerceptionConfig" = Field(default_factory=lambda: PerCameraPerceptionConfig())

class EdgeConfig(BaseModel):
    org_id: str
    edge_server_id: str
    backend_url: str = "http://localhost:8000"
    poll_seconds: int = 8
    sources: list[SourceConfig]
    ingest_key: str = ""


def load_config(path: str) -> EdgeConfig:
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return EdgeConfig(**raw)
