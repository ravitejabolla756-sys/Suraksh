# Safety Perception Framework

## Purpose

SURAKSH now has an isolated, model-agnostic perception boundary for three event families:

- `FIRE`
- `SMOKE`
- `ACCIDENT`

This layer does not load model weights, create alerts, persist detections, or connect to production CCTV. It is an execution contract that future approved models can implement and test independently.

## Contract

The Python contracts live in `backend/app/safety/contracts.py`:

- `FrameInput`: decoded frame, UTC timestamp, camera ID, and source sequence.
- `InferenceRequest`: frame plus model identity/version and an optional bounded `TemporalWindow`.
- `SafetyDetection`: model signal/localization, confidence, optional box, and extensible attributes.
- `EvidenceFrame`: frame reference with optional evidence URI and SHA-256.
- `SafetyPerceptionResult`: event family, camera/model identity, detections, aggregate confidence, evidence, temporal context, latency, status, and safe error text.

All timestamps must be timezone-aware. Confidence values are normalized to `0.0..1.0`. Temporal windows cannot mix cameras and are capped at 64 frames at the contract boundary.

## Model types

Implement one of the two base classes in `backend/app/safety/models.py`:

```python
class FireModel(FrameSafetyModel):
    event_family = EventFamily.FIRE
    model_id = "approved-fire-detector"
    model_version = "2026.1"

    async def infer(self, request: InferenceRequest) -> SafetyPerceptionResult:
        ...
```

`FrameSafetyModel` receives the current frame. `TemporalSafetyModel` receives a bounded, ordered window ending at the current frame. Both use the same result contract.

## Runtime guarantees

`CameraSafetyRuntime` creates an independent worker for each `(camera_id, model_id)` pair.

- Bounded queue with configurable size; when full, the oldest pending frame is dropped so memory remains bounded and the worker stays fresh.
- Async inference boundary; slow video models do not block the event loop while the contract is awaited.
- Per-camera/model history for temporal inference, capped by `window_size` and 64 frames.
- Model exceptions are caught and published as `ModelStatus.FAILED` results; they do not terminate other workers.
- Runtime statistics expose accepted, dropped, failed, queue, and status information.
- No alert, notification, database, or production event call is made by this package.

## Testing

`backend/tests/test_safety_perception.py` uses fake frame, temporal, and failing models only. It verifies the common contract, same-camera temporal windows, bounded dropping, and failure isolation. Real model tests should be added separately once approved weights, datasets, and evaluation thresholds exist.

## Future integration boundary

Before connecting this framework to alerts, add an explicit policy layer for temporal smoothing, confidence thresholds, cooldowns, duplicate suppression, evidence retention, role/department authorization, and audit records. That policy must consume `SafetyPerceptionResult`; models must remain free of alert side effects.
