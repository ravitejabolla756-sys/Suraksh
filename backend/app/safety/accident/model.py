"""Common SafetyModel adapter for experimental accident events."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ..contracts import EventFamily, EvidenceFrame, InferenceRequest, ModelStatus, SafetyPerceptionResult
from ..models import TemporalSafetyModel
from .temporal import AccidentConfig, AccidentTemporalVerifier
from .tracking import TrackObservation


@dataclass(frozen=True, slots=True)
class AccidentPerceptionFrame:
    """Detector/tracker output passed as FrameInput.data to this model."""

    tracks: tuple[TrackObservation, ...]


class ExperimentalAccidentModel(TemporalSafetyModel):
    event_family = EventFamily.ACCIDENT
    model_id = "experimental-accident-perception"
    model_version = "0.1.0-event-temporal"

    def __init__(self, config: AccidentConfig | None = None):
        self.verifier = AccidentTemporalVerifier(config)

    async def infer(self, request: InferenceRequest) -> SafetyPerceptionResult:
        started = time.perf_counter()
        window = request.temporal_window
        frames = window.frames if window is not None else (request.frame,)
        events = []
        for frame in frames:
            data = frame.data
            tracks = data.tracks if isinstance(data, AccidentPerceptionFrame) else ()
            events.extend(self.verifier.observe(frame.sequence, tracks, frame.timestamp, request.frame.camera_id))
        latest = events[-1] if events else None
        evidence = tuple(EvidenceFrame(frame) for frame in frames if latest and frame.sequence in latest.evidence_indices)
        detections = ()
        confidence = 0.0
        if latest:
            from ..contracts import SafetyDetection
            detections = (SafetyDetection(latest.event_type, latest.confidence, "event_temporally_verified", None, {**latest.signals, "tracks": latest.tracks, "temporal_duration": latest.temporal_duration}),)
            confidence = latest.confidence
        return SafetyPerceptionResult(EventFamily.ACCIDENT, request.frame.camera_id, request.model_id, request.model_version, detections, confidence, evidence, window, (time.perf_counter() - started) * 1000, ModelStatus.READY)

    def event_payload(self, result: SafetyPerceptionResult) -> dict[str, Any]:
        detection = result.detections[0] if result.detections else None
        return {"event_type": detection.label if detection else "none", "confidence": result.confidence, "camera_id": result.camera_id, "timestamp": result.processed_at.isoformat(), "tracks": detection.attributes.get("tracks", ()) if detection else (), "temporal_window": detection.attributes.get("temporal_duration") if detection else None, "signals": detection.attributes if detection else {}, "evidence": [item.frame.sequence for item in result.evidence_frames], "model_version": result.model_version}
