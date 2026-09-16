# Suraksh Fire and Smoke Perception

Fire and smoke use a dedicated replaceable specialist boundary, separate from
the person/vehicle detector. `FireSmokeDetector` follows the common safety
model contract and produces class, confidence, box, and source-frame metadata
through `FrameInput`.

`TemporalFireSmokeVerifier` maintains bounded state per camera and event
family. It requires configurable confidence and consecutive-frame persistence;
a single weak frame cannot confirm an event. Smoke can confirm without a
visible flame. Suppression attributes cover headlights, red/orange lights,
sun glare, fog, haze, and dataset-supported steam.

The verifier produces perception results only and does not activate emergency
alerts or the Incident Engine. No external model or weights are bundled;
license verification is required before installing any candidate. Production
accuracy requires annotated fire/smoke footage across relevant lighting and
scene conditions.
