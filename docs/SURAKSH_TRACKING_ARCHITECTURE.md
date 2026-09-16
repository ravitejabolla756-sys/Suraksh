# Suraksh Tracking Architecture

## Scope

Task 3 adds a detector-independent tracking contract to the Edge Agent. It does not change the backend viewer’s production default. The existing timestamp-aware IoU implementation remains available there as the legacy comparison path.

## Contract

`edge-ai/app/perception/trackers.py` defines `Tracker`, `Track`, and `TrackState`. A tracker receives a `FramePacket`/`DetectorInput` and detector-owned `Detection` records. It returns camera-local, anonymous IDs and source-timestamped tracking results. The frontend never creates or reuses IDs.

States are `NEW`, `TENTATIVE`, `CONFIRMED`, `LOST`, `REACTIVATED`, and `EXPIRED`. A concrete implementation owns lifecycle transitions, ID allocation, association, and source-time advancement. Track output includes class, box, confidence, state, age, hits, missed frames, velocity, and whether the box is predicted.

## Implementations

- `ByteTrackTracker` uses the Ultralytics ByteTrack adapter.
- `BoTSORTTracker` uses the Ultralytics BoT-SORT adapter.
- `LegacyIoUTracker` is retained as a compatibility/comparison name and is not selected as a new production default.

`ByteTrackConfig` centralizes `track_high_threshold`, `track_low_threshold`,
`new_track_threshold`, `match_threshold`, `track_buffer`, `minimum_hits`, and
`maximum_age`. The ByteTrack adapter passes the association thresholds and
buffer to the underlying implementation instead of scattering constants. Its
underlying Ultralytics tracker supplies the Kalman prediction and lost-track
management; skipped source frames are advanced with empty updates using source
time.

The adapters maintain one upstream tracker per class, advance missing source frames with empty updates, reject backward source frames, and map upstream IDs to Edge-local IDs. Separate tracker instances are required per camera. IDs are never generated in the frontend.

These adapters expose lifecycle telemetry and preserve reactivation/expiry information from the upstream tracker. The normalized `Track` contract is the boundary for future implementations; model-specific tracker internals must not leak into detector code.

## Non-goals and risks

This task does not claim that either tracker is accurate for Suraksh footage. Association quality still depends on detector recall, camera geometry, frame rate, occlusion, and configuration. Production selection remains deliberately unchanged until labelled MOT evaluation measures ID switches, fragmentation, recall, latency, and false associations.
