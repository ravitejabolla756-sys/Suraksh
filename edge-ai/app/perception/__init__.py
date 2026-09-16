"""Isolated person/vehicle detector and tracker benchmark primitives."""

from .contracts import Detection, DetectorInput, DetectorResult, FramePacket, TimingBreakdown
from .runtime import PerCameraFrameQueue, PipelineMode
from .reid import AppearanceEncoder, ColorHistogramEncoder, EmbeddingCache, ReIDConfig
from .splits import DatasetSplits, assert_no_source_leakage, split_by_source
from .small_person import CameraResolutionProfile, validate_profile_budget
from .counting import CountError, Direction, LineCrossingCounter, TrackPoint, count_error
from app.promotion import ModelPromotionManager, PromotionCandidate, PromotionResult
from .trackers import (BoTSORTConfig, BoTSORTTracker, ByteTrackConfig, ByteTrackTracker, LegacyIoUTracker,
                       Track, Tracker, TrackState)

__all__ = [
    "Detection", "DetectorInput", "FramePacket", "DetectorResult", "TimingBreakdown",
    "PerCameraFrameQueue", "PipelineMode",
    "Track", "TrackState", "Tracker", "ByteTrackConfig", "BoTSORTConfig", "ByteTrackTracker", "BoTSORTTracker", "LegacyIoUTracker",
    "AppearanceEncoder", "ColorHistogramEncoder", "EmbeddingCache", "ReIDConfig",
    "DatasetSplits", "split_by_source", "assert_no_source_leakage",
    "CameraResolutionProfile", "validate_profile_budget",
    "CountError", "Direction", "LineCrossingCounter", "TrackPoint", "count_error",
    "ModelPromotionManager", "PromotionCandidate", "PromotionResult",
]
