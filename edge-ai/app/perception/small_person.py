"""Configurable small-person inference profiles; no global resolution override."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CameraResolutionProfile:
    camera_id: str
    inference_size: int = 640
    tiled_inference: bool = False
    tile_size: int = 640
    tile_overlap: float = .2
    image_enhancement: str = "none"

    def __post_init__(self) -> None:
        if not self.camera_id or self.inference_size < 320:
            raise ValueError("camera profile requires a valid camera and resolution")
        if self.tiled_inference and self.tile_size < 320:
            raise ValueError("tile_size is too small")
        if not 0 <= self.tile_overlap < 1:
            raise ValueError("tile_overlap must be in [0, 1)")


def validate_profile_budget(profile: CameraResolutionProfile, max_fps: float | None,
                            measured_fps: float | None) -> bool:
    """Return whether a measured profile meets its optional realtime budget."""
    return max_fps is None or (measured_fps is not None and measured_fps >= max_fps)
