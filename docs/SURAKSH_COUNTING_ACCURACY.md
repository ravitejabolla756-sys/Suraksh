# Suraksh Counting Accuracy

## Audit result

The viewer’s current `tracking_preview.py` counts current detector boxes for
visible people/vehicles. Its `unique_*` values are sets of observed tracker
IDs for one replay epoch. They are not raw unique detections, but they inherit
all ID recreation and track-loss errors. The backend analytics layer consumes
snapshot counts and crossing records; this audit found no complete trajectory
based line/zone counter integrated into the active viewer path. Entry/exit and
zone semantics therefore require explicit track-based implementation before
being treated as accurate.

## Hardened primitive

`edge-ai/app/perception/counting.py` provides a per-camera-compatible
`LineCrossingCounter`. It accepts stable Edge track IDs and source-timestamped
trajectory points, uses a signed line side rather than independent boxes,
applies a boundary deadband, and debounces rapid reversals. A track that is
temporarily missed or reactivated retains its identity because state is keyed
by `track_id`; callers should expire state only when the tracker emits
`EXPIRED`. Tracks entering or leaving the frame do not create a crossing
without observations on both sides of the line.

The same contract can support zone entry/exit by replacing line side with
inside/outside polygon state and retaining per-track hysteresis. Raw detector
counts may describe current visibility, but must never be used for unique
visits or crossing totals.

## Accuracy measurement

Measure current visible counts, unique visits, line crossings, zone entries,
and exits against annotated track/event ground truth. Report absolute and
signed count error, precision/recall for crossing events, duplicate crossings,
missed crossings, ID fragmentation, and error by occlusion, boundary jitter,
entry/exit, and reactivation. Use source timestamps and a completely held-out
test sequence. No accuracy result is claimed without annotations.
