# Suraksh Tracker Comparison

## Scope

The Edge Agent exposes three comparison choices behind the same detector-neutral interface:

| Tracker | Role | Production default changed? |
|---|---|---|
| `LegacyIoUTracker` | Existing compatibility baseline | No |
| `ByteTrackTracker` | High/low confidence association with Kalman/lost-track support | No |
| `BoTSORTTracker` | ByteTrack-style association with BoT-SORT motion/GMC/ReID options | No |

## BoT-SORT configuration

`BoTSORTConfig` makes the following explicit:

- `enabled`
- `match_threshold`
- `track_buffer`
- `camera_motion_compensation`
- `reid_enabled`
- `reid_weight`

ReID is disabled by default. Camera-motion compensation is also disabled by default because static CCTV does not need its additional cost. Enable it only for moving, panning, or vibrating cameras after evaluating the relevant footage. ReID must likewise be benchmarked before activation.

Task 6 adds `reid_distance_threshold` and `embedding_cache_size`, plus a
bounded camera-local `EmbeddingCache` and optional lightweight appearance
encoder. Embeddings are anonymous vectors used only for short-term track
association; no face recognition, identity labels, persistence, or biometric
identity store is introduced. Appearance similarity cannot be used as the
sole association decision: the tracker still enforces class and motion/box
gates.

The adapter uses the underlying Ultralytics BoT-SORT Kalman and lifecycle implementation, while retaining Edge-owned camera-local ID mapping and source-time advancement for skipped frames.

## Required benchmark protocol

Run LegacyIoU, ByteTrack, and BoT-SORT against the same replay videos, exact same decoded frame indices, detector outputs, confidence thresholds, source timestamps, camera partition, and evaluation split. Record at minimum:

- detection-to-track matches, track recall, fragmentation, and ID switches;
- IDF1, MOTA, and association accuracy where ground truth supports them;
- event/count continuity, reactivation rate, false associations, and expiry rate;
- detection delay, inference latency, FPS, CPU, RAM, and model/runtime settings.

For BoT-SORT, run separate controlled variants for static camera, vibration/pan with GMC, and ReID enabled. Do not compare a feature-enabled variant against a baseline with different detector outputs or thresholds.

No numerical winner is reported here. The repository does not currently contain annotated replay ground truth sufficient to produce valid tracker acceptance metrics. Runtime telemetry or visual inspection alone cannot establish superiority.

For the ReID experiment, run BoT-SORT twice with identical detector outputs,
source frames, thresholds, and hardware: `reid_enabled=false` and
`reid_enabled=true`. Report ID switches, IDF1, HOTA, fragmentation, track
loss, latency, FPS, CPU, RAM, cache size, and the percentage of associations
using appearance. A stability improvement that violates the realtime budget
must be reported as a regression, not promoted.
