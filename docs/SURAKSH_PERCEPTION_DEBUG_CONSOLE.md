# Suraksh Perception Debug Console

The recorded viewer now exposes an optional developer-only diagnostics panel
when running a non-production frontend build. It is intentionally gated by
`NODE_ENV !== "production"` and the operator checkbox; normal customer UI
does not render these internal fields.

The panel displays source/detection frame identity, source timestamp/FPS,
processing FPS, inference latency, tracker latency when supplied, frame age,
queue depth, processed/dropped counts, and source versus displayed frame
indices. It also renders available per-object ID, class, confidence, and
lifecycle fields. Fields unavailable from the current legacy runtime are
shown as `—` rather than inferred.

This is a diagnostic presentation layer only. It does not create track IDs,
change tracker state, expose filesystem paths, or make internal telemetry part
of the production customer API contract. Full lifecycle details require the
new tracker runtime to publish them in its snapshot.
