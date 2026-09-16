# Experimental Smoke Detection

## Status and boundary

This is an experimental perception pipeline. It is not production smoke detection and does not create emergency alerts. No performance result is claimed without representative, rights-approved CCTV footage and annotated smoke episodes.

The smoke pipeline is separate from normal person/vehicle detection and from the experimental fire pipeline. It can be registered independently as a `TemporalSafetyModel` in `CameraSafetyRuntime`.

## Pipeline

```text
decoded frames
  -> SmokeCandidateDetector
  -> bounded per-camera temporal buffer
  -> motion / appearance / expansion / direction analysis
  -> SmokeTemporalVerifier
  -> probability + contributing signals
  -> evidence frame references
```

The candidate stage uses low-saturation diffuse appearance, luminance distribution, local texture, transparency proxy, and solid-object edge suppression. A static candidate is insufficient. Verification requires persistence and temporal change, and checks that the signal stays in a consistent scene region. Motion is measured from frame differences; box-centre displacement provides a direction vector; area trend provides expansion.

## Configuration and suppression

`SmokeCandidateConfig` controls candidate area, appearance, and transparency thresholds. `SmokeTemporalConfig` controls bounded window size, persistence frames, confidence, persistence, motion, expansion, and evidence limits. Flat or strongly edged objects, one-frame candidates, inconsistent regions, and static scenes are suppressed. Thresholds are experimental defaults and must be calibrated on annotated footage.

## Output and deployment

`ExperimentalSmokeModel.event_payload()` provides `event_type`, confidence, camera ID, timestamp, evidence frame sequence references, temporal duration, model version, and contributing signals. The model only returns perception results; it does not invoke alerts, notifications, or persistence.

`SmokeModelScorer` is an injection boundary for an ONNX Runtime or OpenVINO crop scorer. The current implementation does not load weights or claim accelerator performance. A future adapter can preprocess crops and return a normalized score without changing the temporal or alert boundaries.

## Evaluation

`evaluate_smoke_episodes()` calculates precision, recall, and F1 over equal-length annotated episode labels. Evaluation should split by camera and time, report false positives by scene type (fog, steam, dust, glare, clouds, headlights), and measure detection delay and alert suppression separately. Current tests use generated smoke-like and negative frames only; they are logic tests, not representative CCTV evaluation.
