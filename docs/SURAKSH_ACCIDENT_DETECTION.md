# SURAKSH Temporal Accident Detection

Accident detection is an experimental temporal event-analysis layer above the
existing person and vehicle tracker. It does not use a generic YOLO `accident`
class and it never creates a vehicle identity from an accident signal.

```text
tracker output
  -> bounded anonymous trajectories
  -> velocity, acceleration, heading and closest-approach features
  -> camera-specific temporal state machine
  -> multi-frame confirmation
  -> existing safety incident bridge
```

## State machine

Each camera and sorted anonymous track tuple has an independent state:

`NORMAL -> SUSPICIOUS -> CANDIDATE -> CONFIRMED -> RESOLVED`

`SUSPICIOUS` requires an approach or fall precursor. `CANDIDATE` requires an
impact-like change such as abrupt deceleration, a heading change, or separately
provided visual evidence. `CONFIRMED` requires consecutive aftermath support
within the configured temporal window. A single frame, proximity alone, or OCR
output cannot create a confirmed accident.

The verifier emits only when entering `CONFIRMED`. It retains the approach,
impact, and confirmation feature records so the incident bridge can retain
source frame references and model metadata. Repeated observations are
deduplicated by camera, event type, track tuple, frame interval, and cooldown.

## Features and calibration

`backend/app/safety/accident/tracking.py` computes source-timestamped velocity,
acceleration, heading, heading change, and bounded track history. The feature
record also contains relative velocity, distance, predicted closest approach,
trajectory intersection, overlap, stationary aftermath, fall evidence, visual
impact evidence, scene state, and model calibration version.

The default coordinate unit is `pixels`. Pixel thresholds are camera-specific
experimental values and must not be presented as road speed. A deployment may
provide a `CameraCalibration` with an invertible homography and `meters` units.
The calibration version is carried into every feature record. Frames with
camera motion, occlusion, discontinuity, out-of-order timestamps, or excessive
track gaps are excluded from motion confirmation.

Thresholds live in `AccidentConfig`, and camera-specific policies can be passed
to `AccidentTemporalVerifier(camera_configs=...)`. The capability is bounded by
camera count, track count, candidate count, history size, and evidence frame
count. It is only active for a model explicitly registered with the safety
runtime and with `AccidentConfig(enabled=True)`; the default is disabled.

## Incident integration

`ExperimentalAccidentModel` implements the common temporal safety-model
contract. It returns `SafetyPerceptionResult` with the contributing tracks,
signals, temporal duration, and evidence frame sequences. The existing
`SafetyIncidentBridge` remains responsible for tenant validation, durable event
grouping, audit records, evidence references, and notification policy. The
accident verifier itself has no database or notification side effects.

## Evaluation

Use an annotated dataset containing accident and non-accident clips. Each clip
must identify its event type and source timestamp, or explicitly be marked
negative. `evaluate_annotated_clips` reports:

- precision, recall, and F1
- false-alarm rate over negative clips
- mean detection delay for matched accidents
- missed accident count

The dataset and results must be stratified by day/night, camera angle,
distance, blur, glare, weather, object scale, and scene density. Detection
quality and track-to-event association should be evaluated separately from
downstream incident delivery. No metrics are included in this repository until
an approved ground-truth dataset is run.

This capability remains experimental and is not production-ready without a
dedicated ground-truth evaluation, camera calibration validation, failure-mode
review, and production monitoring of false alarms and missed accidents.
