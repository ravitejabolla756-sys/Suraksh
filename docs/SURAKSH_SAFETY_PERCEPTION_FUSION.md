# Suraksh Safety Perception Fusion

`SafetyPerceptionFusion` is the unified perception boundary for person and
vehicle tracks, fire/smoke specialist results, accident candidates, zones,
camera metadata, and explicit evidence signals. It emits a `SafetyEvent`
candidate containing event ID/type, camera, severity, confidence, source frame
index/timestamp, involved track IDs, evidence references, state, and creation
time.

Supported types are `FIRE`, `SMOKE`, `ACCIDENT`, `PERSON_INTRUSION`,
`CROWDING`, and `VEHICLE_INTRUSION`. Inputs should be represented as explicit
`FusionSignal` records rather than an untraceable average.

This layer does not duplicate or own the Incident Engine. Perception emits
candidate evidence with state `CANDIDATE`; Incident Engine remains responsible
for operational lifecycle, assignment, severity policy, audit, notes,
notifications, and resolution. No alert is activated by this fusion class.
