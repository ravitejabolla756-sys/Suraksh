# Shared Temporal Evidence Engine

## Purpose

`backend/app/safety/evidence.py` provides a reusable temporal evidence boundary for safety events that require more than one frame. Initial consumers are fire, smoke, and accident perception. Future fall, fight, or other event models can submit the same samples and candidates without implementing their own rolling buffers.

The engine does not run models, write alerts, send notifications, or own video storage.

## Data flow

```text
existing recorder/frame metadata + tracker snapshot
  -> TemporalEvidenceSample
  -> camera-local rolling buffer
  -> EventCandidate at T
  -> wait for post-event coverage
  -> bounded evidence selection
  -> TemporalEvidence
```

At candidate time `T`, the default window is `T - 10s` through `T + 10s`. The event-context portion defaults to `T - 2s` through `T + 2s`; pre-event and post-event references are returned separately.

## No duplicated video storage

`TemporalEvidenceSample` stores an `EvidenceFrameReference`, not decoded pixels. The reference points to existing recording/evidence infrastructure through `recording_id`, `frame_uri`, frame sequence, offset, and optional hash. A model or recorder may retain its own frame briefly, but this engine never copies or owns the video. Consumers should resolve references only when evidence must be displayed or exported.

## Guarantees

- Independent state for every camera.
- `deque(maxlen=max_samples)` plus age-based pruning; memory is bounded by configuration.
- Candidate timestamps and involved track IDs are preserved.
- Pre-event, event, and post-event evidence are selected independently and capped by `max_evidence_frames`.
- Track ID snapshots are retained as lightweight history points.
- Event finalization waits until post-event coverage is available through `ingest()`/`poll()`.
- Duplicate candidates are suppressed by event type and sorted track IDs for the configured cooldown.
- `cleanup()` removes stale pending candidates and old deduplication records.
- Out-of-order samples for a camera are rejected to protect temporal correctness.

## Consumer usage

```python
engine = TemporalEvidenceEngine(TemporalEvidenceConfig(
    pre_event_seconds=10,
    post_event_seconds=10,
    max_samples=512,
))

engine.ingest(TemporalEvidenceSample(reference, track_ids=(12, 18)))
engine.trigger(EventCandidate(
    event_type="vehicle_collision",
    camera_id="cam-17",
    timestamp=reference.timestamp,
    track_ids=(12, 18),
    confidence=0.81,
))

# Call as frames arrive. A tuple is returned once T + post_event_seconds exists.
completed = engine.ingest(next_reference_sample)
```

The completed object exposes `event`, `temporal_window`, `pre_event`, `event_evidence`, `post_event`, combined `evidence`, and `track_history`. Models remain responsible for deciding that a candidate exists; the evidence engine only packages the bounded temporal context.

## Operational boundary

This engine is not connected to production alerts. Before any alert integration, define retention authorization, evidence access control, redaction, storage failure behavior, clock synchronization, event severity policy, and audit logging. Do not use synthetic unit-test references as production evidence.

## Testing

`backend/tests/test_temporal_evidence.py` covers buffer rollover, delayed event finalization, evidence extraction, track history, deduplication, stale cleanup, and simultaneous independent cameras. Tests use storage references only; they do not claim video-quality or model-performance results.
