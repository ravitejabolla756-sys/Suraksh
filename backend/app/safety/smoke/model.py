"""Common SafetyModel adapter for experimental smoke perception."""

from __future__ import annotations

import time
from typing import Any, Protocol

from ..contracts import EventFamily, EvidenceFrame, InferenceRequest, ModelStatus, SafetyDetection, SafetyPerceptionResult
from ..models import TemporalSafetyModel
from .candidate import SmokeCandidateDetector
from .temporal import SmokeTemporalConfig, SmokeTemporalVerifier


class SmokeModelScorer(Protocol):
    """Optional crop scorer boundary for ONNX Runtime or OpenVINO adapters."""

    def __call__(self, crop: Any) -> float | None: ...


class ExperimentalSmokeModel(TemporalSafetyModel):
    event_family = EventFamily.SMOKE
    model_id = "experimental-smoke-perception"
    model_version = "0.1.0-candidate-temporal"

    def __init__(self, detector: SmokeCandidateDetector | None = None, temporal: SmokeTemporalConfig | None = None):
        self.detector = detector or SmokeCandidateDetector()
        self.verifier = SmokeTemporalVerifier(temporal)

    async def infer(self, request: InferenceRequest) -> SafetyPerceptionResult:
        started = time.perf_counter()
        window = request.temporal_window
        frames = window.frames if window is not None else (request.frame,)
        verification = None
        current = ()
        for frame in frames:
            current = self.detector.detect(frame.data)
            verification = self.verifier.observe(frame, current)
        assert verification is not None
        evidence = tuple(EvidenceFrame(frame) for frame in frames if frame.sequence in verification.evidence_indices)
        detections = tuple(SafetyDetection("smoke", verification.probability, "smoke_temporally_verified", tuple(float(v) for v in current[0].box), {"contributing_signals": verification.contributing_signals, "direction": verification.direction, "duration_seconds": verification.duration_seconds}) for _ in ([current[0]] if verification.verified and current else []))
        return SafetyPerceptionResult(EventFamily.SMOKE, request.frame.camera_id, request.model_id, request.model_version, detections, verification.probability if verification.verified else 0.0, evidence, window, (time.perf_counter() - started) * 1000, ModelStatus.READY)

    def event_payload(self, result: SafetyPerceptionResult) -> dict[str, Any]:
        return {"event_type": "smoke", "confidence": result.confidence, "camera_id": result.camera_id, "timestamp": result.processed_at.isoformat(), "evidence_frames": [item.frame.sequence for item in result.evidence_frames], "temporal_duration": result.temporal_window.ended_at.isoformat() if result.temporal_window else None, "model_version": result.model_version, "contributing_signals": result.detections[0].attributes.get("contributing_signals", ()) if result.detections else ()}
