"""Replaceable fire/smoke specialist boundary and temporal confirmation."""
from __future__ import annotations
from abc import ABC
from collections import deque
from dataclasses import dataclass
from .contracts import EventFamily, ModelStatus, SafetyDetection, SafetyPerceptionResult
from .models import FrameSafetyModel

@dataclass(frozen=True, slots=True)
class FireSmokePolicy:
    confidence_threshold: float = .65
    minimum_consecutive_frames: int = 3
    maximum_gap_seconds: float = 1.5
    buffer_size: int = 16

class FireSmokeDetector(FrameSafetyModel, ABC):
    """Dedicated replaceable specialist; no weights are bundled here."""
    event_family = EventFamily.FIRE

class TemporalFireSmokeVerifier:
    def __init__(self, policy: FireSmokePolicy = FireSmokePolicy()):
        if policy.minimum_consecutive_frames < 2 or policy.buffer_size < policy.minimum_consecutive_frames:
            raise ValueError("temporal policy requires a bounded sufficient buffer")
        self.policy = policy
        self._history: dict[tuple[str, EventFamily], deque] = {}

    def observe(self, result: SafetyPerceptionResult) -> SafetyPerceptionResult | None:
        if result.event_family not in {EventFamily.FIRE, EventFamily.SMOKE}:
            raise ValueError("fire/smoke verifier accepts only fire and smoke")
        detections = tuple(d for d in result.detections if d.confidence >= self.policy.confidence_threshold and not self._suppressed(d))
        clean = SafetyPerceptionResult(result.event_family, result.camera_id, result.model_id, result.model_version,
                                       detections, max((d.confidence for d in detections), default=0),
                                       result.evidence_frames, result.temporal_window, result.inference_latency_ms,
                                       result.model_status, result.processed_at, result.error)
        history = self._history.setdefault((result.camera_id, result.event_family), deque(maxlen=self.policy.buffer_size))
        history.append(clean)
        recent = list(history)[-self.policy.minimum_consecutive_frames:]
        if len(recent) < self.policy.minimum_consecutive_frames or any(not r.detections for r in recent):
            return None
        if recent[-1].processed_at.timestamp() - recent[0].processed_at.timestamp() > self.policy.maximum_gap_seconds:
            return None
        return SafetyPerceptionResult(clean.event_family, clean.camera_id, clean.model_id, clean.model_version,
                                      recent[-1].detections, max(r.confidence for r in recent),
                                      tuple(f for r in recent for f in r.evidence_frames), clean.temporal_window,
                                      clean.inference_latency_ms, clean.model_status, clean.processed_at, clean.error)

    @staticmethod
    def _suppressed(detection: SafetyDetection) -> bool:
        flags = {str(k).lower() for k, v in detection.attributes.items() if v}
        return bool(flags & {"headlight", "headlights", "red_light", "orange_light", "sun_glare", "fog", "haze", "steam"})

    def clear_camera(self, camera_id: str) -> None:
        for key in tuple(self._history):
            if key[0] == camera_id:
                del self._history[key]
