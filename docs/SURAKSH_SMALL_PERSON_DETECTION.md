# Suraksh Small Person Detection

## Goal

Improve distant and small-person recall on actual Suraksh CCTV footage while
preserving realtime behavior. Resolution is a per-camera profile, not a
global maximum. The production detector remains unchanged until measured
results justify a change.

## Configuration

`CameraResolutionProfile` supports:

- `camera_id`
- `inference_size`
- opt-in `tiled_inference`
- `tile_size` and `tile_overlap`
- explicit `image_enhancement` mode

Profiles should be selected from camera geometry and measured hardware. Higher
resolution can improve tiny-object recall while reducing FPS and increasing
RAM/latency. Enhancement must be evaluated against glare, night noise, and
compression artifacts rather than assumed beneficial.

## Benchmark matrix

For each target camera, evaluate the same annotated frames with:

1. baseline resolution;
2. higher detector input resolutions;
3. detector-specific small-object settings;
4. preprocessing variants;
5. tiled/sliced inference only as an opt-in candidate;
6. camera-specific profiles.

Record small-person recall, overall person recall, precision, latency, FPS,
CPU, and RAM. Stratify by tiny/distant, day/night, occlusion, crowdedness, and
camera type. Use a held-out test set; do not tune against it.

Tiling must not be enabled globally. It is justified only when its measured
small-person recall gain is meaningful and the resulting latency/FPS meets the
camera’s realtime budget. No configuration is selected without actual
Suraksh-labelled footage and hardware measurements.
