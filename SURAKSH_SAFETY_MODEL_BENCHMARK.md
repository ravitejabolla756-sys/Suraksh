# SURAKSH Safety Model Benchmark

## Purpose and decision boundary

This benchmark compares candidate implementations for:

1. Fire detection
2. Smoke detection
3. Accident detection

It uses one normalized Suraksh evaluation framework for every candidate. It does not assume the current person/vehicle detector is optimal, does not use published benchmark numbers as Suraksh acceptance numbers, and never promotes a model automatically. A result is measurement evidence only; production selection requires an explicit human review and a separate deployment gate.

The benchmark code is under `backend/app/safety/benchmark/`. It is intentionally independent of emergency notifications and the production alert path.

## Candidate model pool

Candidates should be implemented behind the same adapter and recorded with immutable model identity, version, artifact digest, runtime, and model size. The following are candidate families to test, not recommendations or measured results:

| Family | Candidate | Intended role | Runtime consideration |
|---|---|---|---|
| Fire | Current experimental multi-signal temporal pipeline | Transparent baseline and suppression comparison | CPU/OpenCV; no learned weights |
| Fire | Custom fire detector with YOLO11/YOLO26 or RT-DETR head | Localized flame candidate generation | ONNX Runtime/OpenVINO export should be tested |
| Fire | EfficientNetV2/ConvNeXt frame classifier plus temporal verifier | Frame appearance candidate scoring | CPU-friendly classifier comparison |
| Fire | MoViNet/X3D small temporal classifier | Learned short-window motion verification | Measure temporal buffering and accelerator cost |
| Smoke | Current experimental diffusion/motion temporal pipeline | Transparent baseline and suppression comparison | CPU/OpenCV; no learned weights |
| Smoke | Custom smoke segmentation/detection model | Diffuse region localization | Evaluate fog, steam, dust and glare negatives |
| Smoke | EfficientNetV2/ConvNeXt plus temporal buffer | Appearance scoring candidate | ONNX/OpenVINO classifier path |
| Smoke | MoViNet/X3D small temporal model | Learned diffusion/motion verification | Measure window latency and FPS |
| Accident | Trajectory-feature classifier | Track/geometry event baseline | CPU; consumes detector/tracker outputs |
| Accident | X3D-S/SlowFast small temporal model | Video event classification | Compare clip latency and memory |
| Accident | Video Swin-T or equivalent small video transformer | Higher-capacity event candidate | Measure RAM and accelerator dependency |
| Accident | Pose-assisted temporal fall model | Person-fall specialization | Pose latency and missing-pose behavior required |

Candidate names describe evaluation slots. No weights are bundled or assumed. Each candidate must state its license, training provenance, preprocessing, input resolution, quantization, and whether it supports ONNX/OpenVINO execution.

## Common input/output record

Every candidate is evaluated as a `BenchmarkCandidate` and emits `ModelOutput` for a `GroundTruth` record:

- sample ID, camera ID, event family, event type, start/end timestamps
- event label or `None` for a negative sample
- candidate confidence and detection timestamp
- evidence/track IDs where applicable
- inference latency, FPS, CPU percent, RAM MB, and model size MB
- environment metadata: OS, Python, runtime/provider, device, threads, resolution, batch size, quantization

The evaluator is event-family scoped and rejects mixed-family records. All raw predictions and resource samples should be retained with the report so aggregates are auditable.

## Dataset and split protocol

Use rights-approved representative CCTV footage with frame or episode annotations. The current checkout does not contain an annotated fire, smoke, or accident benchmark dataset, so no acceptance numbers are populated here.

Required protocol:

1. Split by camera and time, never random adjacent frames across train/test.
2. Keep a locked test set and do not tune thresholds on it.
3. Include negative footage with ordinary traffic, people, headlights, reflections, fog, steam, dust, clouds, construction, camera shake, hard braking, occlusion, and parked vehicles.
4. Record event start, event end, subtype, camera ID, evidence interval, and involved track IDs where available.
5. Run every candidate on identical decoded frames, resolution, sampling rate, hardware, thread count, and warm-up policy.
6. Repeat each run sufficiently to report variance; retain raw per-sample results.

## Metrics

The shared evaluator reports:

- precision, recall, F1
- false positives and false negatives
- false positives/hour using annotated evaluation duration
- mean detection delay from ground-truth event start
- mean inference latency in milliseconds
- mean processed FPS
- mean CPU utilization
- mean RAM usage
- model size in MB from the artifact, not a published estimate

For accident candidates it additionally reports:

- event-level precision and recall, requiring subtype agreement
- event detection delay
- track-association accuracy using Jaccard overlap of annotated and predicted involved track IDs

For fire and smoke, results must be reported separately for:

- day
- night
- indoor
- outdoor
- small/distant event
- large event
- difficult lighting

The implementation stores stratified results under `BenchmarkResult.by_stratum`. Missing strata remain missing; they are not filled with zero.

## Reproducible execution requirements

The harness is an evaluator for normalized records. A future runner should:

1. load one candidate artifact and its adapter;
2. warm up once outside measured samples;
3. decode the locked sample list once;
4. capture prediction, evidence, latency and resource data;
5. write `BenchmarkRecord` rows;
6. call `SafetyBenchmarkEvaluator.evaluate()`;
7. export raw rows, aggregate JSON, and this report metadata.

Do not compare a candidate measured with GPU acceleration against a CPU-only candidate without labelling the environment. Do not include model download time in inference latency; report it separately if relevant.

## Acceptance and promotion policy

There are no acceptance thresholds or benchmark results in this document. Suraksh acceptance thresholds must be set after the annotation protocol, operational risk review, camera mix, and target hardware are agreed. A candidate cannot be promoted from this benchmark automatically. Promotion requires explicit review of:

- per-stratum quality and false-positive rate
- false-negative examples and missed-event severity
- detection delay and evidence quality
- resource envelope and failure behavior
- license/provenance and security review
- shadow-mode validation without emergency side effects

The benchmark does not connect to emergency notifications, create production alerts, or claim production accuracy.
