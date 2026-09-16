"""Common SafetyModel adapter for the experimental fire pipeline."""

from __future__ import annotations

import time
from typing import Any, Protocol

from ..contracts import EventFamily, EvidenceFrame, InferenceRequest, ModelStatus, SafetyDetection, SafetyPerceptionResult
from ..models import TemporalSafetyModel
from .candidate import FireCandidateDetector
from .temporal import FireTemporalConfig, FireTemporalVerifier


class FireModelScorer(Protocol):
    """Optional crop scorer boundary for ONNX Runtime or OpenVINO adapters."""

    def __call__(self, crop: Any) -> float | None:
        """Return a normalized fire score, or None when unavailable."""


class ExperimentalFireModel(TemporalSafetyModel):
    """Candidate detector + temporal verifier; never emits alerts itself."""

    event_family = EventFamily.FIRE
    model_id = "experimental-fire-perception"
    model_version = "0.1.0-candidate-temporal"

    def __init__(self, detector: FireCandidateDetector | None = None, temporal: FireTemporalConfig | None = None):
        self.detector = detector or FireCandidateDetector()
        self.verifier = FireTemporalVerifier(temporal)

    async def infer(self, request: InferenceRequest) -> SafetyPerceptionResult:
        started = time.perf_counter()
        window = request.temporal_window
        frames = window.frames if window is not None else (request.frame,)
        verification = None
        current_candidates = ()
        for frame in frames:
            current_candidates = self.detector.detect(frame.data)
            verification = self.verifier.observe(frame, current_candidates)
        assert verification is not None
        evidence = tuple(EvidenceFrame(frame) for frame in frames if frame.sequence in verification.evidence_indices)
        detections = tuple(SafetyDetection(
            label="fire", signal="flame_candidate_temporally_verified", confidence=verification.probability,
            box=tuple(float(value) for value in current_candidates[0].box),
            attributes={"persistence": verification.persistence, "flicker": verification.flicker, "growth": verification.growth},
        ) for _ in ([current_candidates[0]] if verification.verified and current_candidates else []))
        return SafetyPerceptionResult(
            event_family=EventFamily.FIRE, camera_id=request.frame.camera_id,
            model_id=request.model_id, model_version=request.model_version,
            detections=detections, confidence=verification.probability if verification.verified else 0.0,
            evidence_frames=evidence, temporal_window=window,
            inference_latency_ms=(time.perf_counter() - started) * 1000,
            model_status=ModelStatus.READY,
        )
