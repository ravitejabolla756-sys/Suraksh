"""Isolated safety-perception contracts and runtime primitives."""

from .contracts import (
    EvidenceFrame,
    EventFamily,
    FrameInput,
    InferenceRequest,
    ModelStatus,
    SafetyDetection,
    SafetyPerceptionResult,
    TemporalWindow,
    utc_now,
)
from .models import FrameSafetyModel, SafetyModel, TemporalSafetyModel
from .runtime import CameraSafetyRuntime, CameraRuntimeStats
from .evidence import (
    EventCandidate,
    EvidenceFrameReference,
    TemporalEvidence,
    TemporalEvidenceConfig,
    TemporalEvidenceEngine,
    TemporalEvidenceSample,
    TrackHistoryPoint,
    EvidenceAccessPolicy,
)
from .fusion import (EvidenceFusionConfig, FusedSafetyEvent, FusionRequest, FusionSignal,
                     SafetyEvidenceFusionEngine, SafetyEvent, SafetyPerceptionFusion, SignalPolarity)
from .fire_smoke import FireSmokeDetector, FireSmokePolicy, TemporalFireSmokeVerifier
from .accident import (AccidentConfig, CameraCalibration, AccidentFeatureRecord, AccidentEvent, AccidentMetrics, AnnotatedAccidentClip, AccidentPerceptionFrame,
                       AccidentState, AccidentTemporalVerifier, ExperimentalAccidentModel, TrackObservation,
                       TrajectoryExtractor, evaluate_accident_events, evaluate_annotated_clips)

__all__ = [
    "CameraRuntimeStats",
    "CameraSafetyRuntime",
    "EvidenceFusionConfig",
    "EventCandidate",
    "EvidenceFrameReference",
    "FusedSafetyEvent",
    "SafetyEvent", "SafetyPerceptionFusion",
    "FusionRequest",
    "FusionSignal",
    "EvidenceFrame",
    "EventFamily",
    "FrameInput",
    "FrameSafetyModel",
    "InferenceRequest",
    "ModelStatus",
    "SafetyDetection",
    "SafetyModel",
    "SafetyPerceptionResult",
    "SafetyEvidenceFusionEngine",
    "SignalPolarity",
    "TemporalEvidence",
    "TemporalEvidenceConfig",
    "TemporalEvidenceEngine",
    "TemporalEvidenceSample",
    "TemporalSafetyModel",
    "TrackHistoryPoint",
    "EvidenceAccessPolicy",
    "TemporalWindow",
    "utc_now",
    "FireSmokeDetector", "FireSmokePolicy", "TemporalFireSmokeVerifier",
    "AccidentConfig", "CameraCalibration", "AccidentFeatureRecord", "AccidentEvent", "AccidentMetrics", "AnnotatedAccidentClip", "AccidentPerceptionFrame",
    "AccidentState", "AccidentTemporalVerifier", "ExperimentalAccidentModel", "TrackObservation",
    "TrajectoryExtractor", "evaluate_accident_events", "evaluate_annotated_clips",
]
