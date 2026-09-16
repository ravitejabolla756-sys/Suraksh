# Experimental Fire Detection

## Status and boundary

This is an experimental perception pipeline. It is not production fire detection, does not claim emergency safety coverage, and does not create alerts. Production readiness requires representative, rights-approved CCTV footage with frame- or event-level fire annotations, a held-out camera/time split, false-positive analysis, latency measurements on target hardware, and a reviewed operating policy.

The implementation is separate from person/vehicle detection under `backend/app/safety/fire/`. It can be registered as its own `TemporalSafetyModel` in `CameraSafetyRuntime`; no normal traffic detector code is imported by the fire pipeline.

## Pipeline

```text
decoded frame
  -> FireCandidateDetector
  -> per-camera bounded temporal window
  -> FireTemporalVerifier
  -> fire probability + verification decision
  -> evidence frame references
```

`FireCandidateDetector` combines warm flame color distribution, brightness/saturation, contour shape/verticality, irregularity, and candidate size. It deliberately rejects a uniform red block. The candidate stage is not sufficient to report fire.

`FireTemporalVerifier` requires configurable persistence and confidence thresholds, then combines spatial persistence, temporal luminance change (flicker), and positive area change (growth). The bounded history is per verifier/runtime camera and can be reset at a camera epoch boundary. Large uniform regions, weak color variation, and candidates that do not persist are suppressed.

## Configuration

`FireCandidateConfig` controls candidate area and visual thresholds. `FireTemporalConfig` controls `window_size`, `persistence_frames`, `confidence_threshold`, `persistence_threshold`, `flicker_threshold`, `growth_threshold`, and maximum evidence frames. Thresholds must be calibrated against annotated footage; the test values are not operational defaults.

## Common output

`ExperimentalFireModel` returns the shared `SafetyPerceptionResult` and detections with `signal="flame_candidate_temporally_verified"`. A future API serializer can map it to:

```json
{
  "event_type": "fire",
  "confidence": 0.0,
  "camera_id": "camera-123",
  "timestamp": "2026-09-15T00:00:00Z",
  "evidence": [],
  "temporal_window": "bounded camera-local window",
  "model_version": "0.1.0-candidate-temporal"
}
```

No alert or notification is emitted by this model.

## ONNX/OpenVINO boundary

`FireModelScorer` is an optional crop-scoring protocol. An ONNX Runtime or OpenVINO implementation can be injected into `FireCandidateDetector` without changing candidate, temporal, runtime, or alert boundaries. The current checkout intentionally does not load weights or claim accelerator support because no approved fire model and evaluation package are present.

## Evaluation

`backend/app/safety/fire/evaluation.py` provides precision, recall, and F1 hooks for equal-length event-label sequences. Use representative CCTV footage with annotations to produce labels and predictions, then report results by camera and event episode—not only aggregate frame accuracy. Current unit tests use generated flame-like and negative frames to validate logic only; they are not representative footage and do not establish production performance.
