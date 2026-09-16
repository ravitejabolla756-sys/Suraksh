# SURAKSH Safety Evidence Fusion Engine

## Purpose and boundary

The Safety Evidence Fusion Engine combines explicit outputs from fire, smoke, accident, tracker, trajectory, temporal, and scene-context components. It produces a perception event with confidence, uncertainty, contributing signals, evidence references, and model versions. It does not decide severity, alert eligibility, escalation, notification, retention, or emergency response.

The implementation is `backend/app/safety/fusion.py`. It is independent of the normal person/vehicle detector and does not write alerts or database records.

## Input

Each `FusionSignal` contains:

- signal name, for example `fire_detector` or `temporal_persistence`;
- normalized value `0..1`;
- producing model ID and version;
- evidence references;
- source reliability;
- support or contradiction polarity;
- optional correlation group.

Example:

```python
FusionSignal("fire_detector", 0.81, "fire-v1", "2026.1", correlation_group="visual")
FusionSignal("smoke_detector", 0.74, "smoke-v1", "2026.1", correlation_group="visual")
FusionSignal("temporal_persistence", 0.91, "temporal-v1", "2026.1", correlation_group="temporal")
FusionSignal("spatial_growth", 0.87, "motion-v1", "2026.1", correlation_group="motion")
```

## Fusion method

The engine does not average model confidence. It:

1. weights each signal by its declared reliability;
2. combines signals within a correlation group with a noisy-OR;
3. applies a configurable correlation penalty so related visual signals do not count as independent proof;
4. combines independent supporting groups with a second noisy-OR;
5. applies explicit contradiction penalties;
6. computes uncertainty from residual confidence, contradiction, independent-source coverage, and signal disagreement;
7. unions and deterministically orders evidence references;
8. preserves every contributing signal and model version in the output.

The method is transparent and deterministic. It is a perception aggregation mechanism, not a calibrated probability claim. Calibration and policy thresholds require annotated validation data.

## Output

`FusedSafetyEvent.as_payload()` returns:

```json
{
  "event_type": "fire",
  "camera_id": "cam-17",
  "timestamp": "2026-09-15T00:00:00+00:00",
  "confidence": 0.0,
  "uncertainty": 0.0,
  "contributing_signals": {
    "fire_detector": 0.81,
    "temporal_persistence": 0.91
  },
  "evidence_references": [],
  "model_versions": {
    "fire-v1": "2026.1",
    "temporal-v1": "2026.1"
  }
}
```

No `should_alert` or escalation field is emitted. A later policy layer must consume this perception output and separately apply authorization, deduplication, severity, cooldown, evidence retention, and human-review rules.

## Camera and evidence boundaries

The engine validates that all evidence references belong to the request camera. It stores references only and deduplicates identical references; it does not copy decoded frames or duplicate video storage. Per-camera temporal buffering remains the responsibility of `TemporalEvidenceEngine` and the model/runtime that creates the signals.

## Testing and limitations

`backend/tests/test_safety_fusion.py` covers explicit signal preservation, non-averaging behavior, correlation penalties, contradiction handling, evidence deduplication, model-version preservation, camera validation, determinism, and the absence of alert policy fields.

These are deterministic unit tests only. No production accuracy, calibrated probability, or emergency-response performance is claimed.
