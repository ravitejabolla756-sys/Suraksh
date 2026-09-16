# Experimental Accident Detection

## Status and boundary

This is an experimental, event-based accident-perception framework. It is not a production safety system, does not send emergency notifications, and does not claim accuracy without annotated accident video. It is separate from the person/vehicle detector and consumes tracker outputs rather than treating `accident` as an object class.

Initial event subtypes:

- `vehicle_collision`
- `vehicle_crash`
- `pedestrian_vehicle_collision`
- `person_fall`

## Architecture

```text
detector/tracker output
  -> TrackObservation
  -> bounded per-camera TrajectoryExtractor
  -> motion, velocity, acceleration, distance and geometry features
  -> AccidentTemporalVerifier / subtype classifier
  -> deduplicated event + confidence
  -> evidence frame references
```

`AccidentPerceptionFrame` carries tracker observations in the shared `FrameInput.data` field. Each observation includes a track ID, class, box, optional zone, and optional pose attributes. `TrajectoryExtractor` keeps bounded points per ID. The verifier uses relative distance, box intersection/proximity, approach speed, deceleration, zone consistency, persistence, and optional fall pose/geometry.

## State, suppression and deduplication

State is camera-local when the model is registered as one worker per camera in `CameraSafetyRuntime`. Trajectory and event buffers are bounded. Configurable `AccidentConfig` values control confidence, persistence, geometry distance, impact deceleration, approach speed, evidence count, and deduplication duration.

False positives are suppressed unless the subtype-specific temporal conditions are met: collisions require two compatible tracks, collision geometry, approach motion, abrupt deceleration, persistence, and confidence; falls require a persistent person track plus pose or fall-like geometry. A deduplication key of subtype plus track IDs prevents repeated events during the configured cooldown.

## Output

`ExperimentalAccidentModel.event_payload()` exposes the requested event type, confidence, camera ID, timestamp, involved tracks, temporal window, signals, evidence sequence references, and model version. The shared `SafetyPerceptionResult` remains the internal contract. No alerts, notifications, database writes, or emergency actions occur.

## Evaluation

`evaluate_accident_events()` provides event-level precision, recall, and F1 hooks. Evaluation should use rights-approved annotated accident video, split by camera and time, and report results for each subtype plus false positives caused by hard braking, occlusion, crowding, parked vehicles, camera shake, and normal falls. The current unit tests use generated trajectories only; they are not representative accident footage and do not establish performance.

## Deployment consideration

The framework is detector/model agnostic. A future ONNX/OpenVINO detector, pose model, or learned temporal classifier can feed the same `TrackObservation` and feature boundaries without changing runtime isolation or alert policy. Approved model provenance, target-hardware latency, and annotated evaluation are required before deployment claims.
