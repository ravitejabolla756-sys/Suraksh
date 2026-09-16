# SURAKSH Perception Acceptance Report

**Report status:** Framework ready; acceptance measurements pending approved annotated data
**Report date:** 2026-09-16
**Production promotion:** Not authorized by this report

## Executive decision summary

| Decision | Result |
|---|---|
| **BEST DETECTOR** | **PENDING MEASUREMENT** |
| **BEST TRACKER** | **PENDING MEASUREMENT** |
| **BEST DETECTOR + TRACKER** | **PENDING MEASUREMENT** |
| **BEST REALTIME CONFIGURATION** | **PENDING HARDWARE RUN** |
| **BEST ACCURACY CONFIGURATION** | **PENDING HELD-OUT TEST** |

No number, winner, or production recommendation is claimed. The repository
does not currently contain the approved, fully annotated and stratified test
corpus required to calculate these decisions.

## Candidates

### Detectors

- Current Suraksh/current YOLO checkpoint.
- Modern compatible YOLO candidate(s).
- RF-DETR candidate(s), subject to package/checkpoint availability and license review.
- RT-DETRv2 candidate(s), subject to package/checkpoint availability and license review.
- Suraksh fine-tuned checkpoint, only when trained and versioned from approved data.

### Trackers

- `LegacyIoUTracker` baseline.
- ByteTrack.
- BoT-SORT.
- BoT-SORT + ReID, only when explicitly enabled and available.

### Safety

- Fire specialist plus temporal verification.
- Smoke specialist plus temporal verification.
- Trajectory-based accident analysis.

All candidates must consume the same source frames, detector outputs where the
comparison requires tracker isolation, source timestamps, camera splits, and
evaluation protocol. Production defaults remain unchanged.

## Acceptance metrics

### Detection

Measure precision, recall, F1, AP50, AP50:95, false positives, and false
negatives for person and vehicle classes. Person results must include small,
distant, nighttime, crowded, and occluded strata.

### Tracking

Measure ID switches, IDF1, HOTA, MOTA where applicable, fragmentation, track
loss, and track persistence. Report lifecycle and reactivation behavior by
camera condition.

### Counting

Measure absolute count error and percentage error for visible counts, unique
track visits, line crossings, zone entry, and entry/exit. Counting must use
annotated track/event ground truth, never raw detector totals for unique counts.

### Safety events

For fire, smoke, and accident clips measure precision, recall, false-alarm
rate, detection delay, and missed events. Fire/smoke must include persistence
and false-positive strata; accident must include annotated non-accident clips.

### Runtime

Record source FPS, processed FPS, display FPS, detector latency, tracker
latency, safety-model latency, end-to-end latency, CPU, RAM, GPU, frame age,
and dropped frames. Record warmup policy, resolution, batch size, device,
precision, queue sizes, and ReID/GMC settings with every result.

## Protocol

1. Use one versioned dataset manifest with provenance, commercial-use license,
   checksums, camera/session identity, and scenario tags.
2. Keep complete camera/video sessions in one split; no adjacent-frame leakage.
3. Keep the test split completely held out from threshold, profile, and model
   selection.
4. Decode each source frame once and distribute identical pixels and source
   metadata to candidates.
5. Run detector-only, tracker-only, detector+tracker, counting, safety, and
   end-to-end runtime evaluations separately so failures are attributable.
6. Repeat runtime measurements on the target deployment hardware after
   warmup; report distributions, not only a best run.
7. Publish unavailable candidate reasons, package versions, model hashes, and
   licenses alongside results.

The existing entry points are `PersonDetectionBenchmark`, the shared
detector/tracker contracts, `evaluate_detections`, `evaluate_tracking`, and
the safety event evaluators. Runtime-only runs may measure latency, but all
quality fields remain `N/A` without annotations.

## Current evidence

| Area | Evidence currently available | Acceptance status |
|---|---|---|
| Detector framework | Shared adapters and person-only evaluator | Ready for data |
| Tracker framework | Legacy, ByteTrack, BoT-SORT adapters | Ready for data |
| ReID | Opt-in bounded configuration/cache | Not benchmarked |
| Counting | Track-based line primitive and error helper | Not validated on CCTV GT |
| Fire/smoke | Temporal specialist boundary/verifier | Not validated on CCTV GT |
| Accident | Temporal trajectory verifier | Not validated on CCTV GT |
| Runtime | Per-stage fields available in benchmark/debug paths | Hardware run pending |

## Remaining failure cases to test

- Tiny/distant people and vehicles.
- Night glare, headlights, red/orange lights, haze, fog, and rain.
- Occlusion, crowd crossings, and objects behind vehicles.
- Fast motion, camera vibration, panning, and perspective changes.
- Detector misses versus association failures.
- Track expiry/reactivation and ID switches.
- Boundary jitter and repeated line crossings.
- Fire/smoke false positives and brief illumination.
- Accident near-misses and stationary vehicles without impacts.
- Replay/display clock drift and dropped-frame behavior.

## Hardware requirements

No universal hardware requirement is declared. It must be derived from the
target camera count, source FPS/resolution, selected input profile, concurrent
streams, queue limits, safety workloads, and latency budget. Record CPU model,
RAM, GPU model/VRAM, driver/runtime versions, and power/thermal constraints in
the benchmark output.

## License and deployment limitations

Every checkpoint, dependency, dataset, and fine-tuned artifact requires a
recorded license and commercial-use review. Current candidate declarations
are adapter metadata, not legal approval. YOLO/Ultralytics, RF-DETR,
RT-DETRv2, ReID weights, OCR packages, and datasets must be reviewed by the
deployment owner before commercial release.

The system remains limited by camera placement, resolution, lighting,
occlusion, source rights, available compute, and the absence of representative
annotated ground truth. This report does not connect safety perception to
emergency policy and does not automatically promote any model or configuration.

## Acceptance sign-off

This report becomes an acceptance result only after attaching a generated
benchmark artifact containing all required metrics, dataset/checkpoint hashes,
hardware details, confidence intervals or run distributions where applicable,
and reviewer sign-off. Until then, every best-model field above remains
pending.
