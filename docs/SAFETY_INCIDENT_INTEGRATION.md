# Safety Perception to Incident Engine

Suraksh now has a thin integration boundary at `backend/app/services/safety_incidents.py`. It accepts validated safety perception output and routes it through the existing `Event` incident path. The adapter does not replace the incident engine, bypass tenant scoping, or implement a second lifecycle.

## Supported events

`fire`, `smoke`, `vehicle_collision`, `vehicle_crash`, `pedestrian_vehicle_collision`, and `person_fall` are accepted. Each candidate must contain its camera, timestamp, confidence, model versions, contributing signals, evidence references, and temporal window.

## Grouping and cooldown

`SafetyIncidentGroup` is durable integration state keyed by organization, camera, and a bounded group key. Fire and smoke use one key per camera. Accident events use an accident key plus sorted involved track IDs when available, so separate simultaneous accidents do not collapse into one episode. Accident subtypes with the same tracks can be grouped as one continuous episode.

Within the configured cooldown, the existing incident event is updated with bounded latest signals, model versions, evidence references, temporal window, and occurrence summaries. It is not re-created and its alert rules are not reprocessed. After cooldown, a new existing `Event` is opened and the group pointer moves to it.

Evidence is stored as references to the recorder (`frame_uri`, `recording_id`, offsets, hashes), never as decoded frames or duplicated video. Occurrences and references are capped by `SafetyIncidentBridgeConfig`.

## Existing capabilities preserved

New groups create normal `Event` rows and call `process_event_alerts`, so configured notification rules continue to work. Existing dismissal/lifecycle fields and API behavior remain unchanged. Creation and grouping are audit-recorded with organization scope. The ingest route uses the existing machine-ingest boundary; operator-facing event reads continue to use the existing authenticated organization filter and RBAC.

## Failure boundary

`ingest_safely()` catches advanced-AI and persistence failures, rolls back the current transaction, and returns a failed result so a camera worker can continue. The API reports the failure status and does not emit a partial incident. No emergency policy is activated by this adapter; configured existing alert rules remain the policy boundary.

Use `POST /safety/incidents/ingest` with the existing `X-Edge-Key`. This is an integration contract, not proof of model quality or production readiness. Safety model performance still requires representative, rights-approved annotated footage and the benchmark process.
