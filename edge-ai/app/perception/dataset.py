"""Rights-aware, deterministic benchmark dataset loading."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterator

import cv2

from .contracts import DetectorInput


@dataclass(frozen=True, slots=True)
class GroundTruthObject:
    class_id: int
    class_name: str
    bbox_xyxy: tuple[float, float, float, float]
    track_id: str | None = None
    occluded: bool = False
    visibility: float | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnnotatedFrame:
    video_path: Path
    camera_id: str
    frame_index: int
    source_timestamp: float
    source_fps: float
    tags: tuple[str, ...]
    objects: tuple[GroundTruthObject, ...]


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    name: str
    version: str
    provenance: str
    license_name: str
    intended_use_permitted: bool
    frames: tuple[AnnotatedFrame, ...]


def _bbox(value: Any) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("bbox_xyxy must contain four numbers")
    result = tuple(float(item) for item in value)
    if result[2] <= result[0] or result[3] <= result[1]:
        raise ValueError("bbox_xyxy must have positive area")
    return result


def load_manifest(path: Path) -> DatasetManifest:
    """Load an annotation manifest and reject ambiguous data rights."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    for key in ("name", "version", "provenance", "license", "intended_use_permitted", "frames"):
        if key not in raw:
            raise ValueError(f"dataset manifest is missing {key}")
    if not raw["provenance"] or not raw["license"]:
        raise ValueError("dataset provenance and license must be explicit")
    if raw["intended_use_permitted"] is not True:
        raise ValueError("dataset is not approved for the intended Suraksh evaluation use")

    frames: list[AnnotatedFrame] = []
    for item in raw["frames"]:
        source_fps = float(item["source_fps"])
        frame_index = int(item["frame_index"])
        expected_timestamp = frame_index / source_fps
        timestamp = float(item.get("source_timestamp", expected_timestamp))
        if abs(timestamp - expected_timestamp) > max(0.002, 0.1 / source_fps):
            raise ValueError(f"frame {frame_index} source_timestamp conflicts with source FPS")
        video_path = (path.parent / item["video_path"]).resolve()
        if not video_path.is_file():
            raise ValueError(f"video does not exist: {video_path}")
        objects = tuple(
            GroundTruthObject(
                class_id=int(obj["class_id"]),
                class_name=str(obj["class_name"]),
                bbox_xyxy=_bbox(obj["bbox_xyxy"]),
                track_id=str(obj["track_id"]) if obj.get("track_id") is not None else None,
                occluded=bool(obj.get("occluded", False)),
                visibility=float(obj["visibility"]) if obj.get("visibility") is not None else None,
                tags=tuple(str(tag) for tag in obj.get("tags", [])),
            ) for obj in item.get("objects", [])
        )
        frames.append(AnnotatedFrame(video_path, str(item["camera_id"]), frame_index,
                                     timestamp, source_fps,
                                     tuple(str(tag) for tag in item.get("tags", [])), objects))
    frames.sort(key=lambda frame: (frame.camera_id, str(frame.video_path), frame.frame_index))
    return DatasetManifest(str(raw["name"]), str(raw["version"]), str(raw["provenance"]),
                           str(raw["license"]), True, tuple(frames))


def decode_frame(annotation: AnnotatedFrame) -> DetectorInput:
    """Decode exactly the annotated source frame without silently substituting."""
    capture = cv2.VideoCapture(str(annotation.video_path))
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, annotation.frame_index)
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok:
        raise RuntimeError(f"could not decode frame {annotation.frame_index}: {annotation.video_path}")
    import time
    captured_at = time.perf_counter()
    return DetectorInput(frame, annotation.frame_index, annotation.source_timestamp,
                         annotation.source_fps, captured_at, annotation.camera_id)


def iter_inputs(manifest: DatasetManifest) -> Iterator[tuple[AnnotatedFrame, DetectorInput]]:
    for annotation in manifest.frames:
        yield annotation, decode_frame(annotation)
