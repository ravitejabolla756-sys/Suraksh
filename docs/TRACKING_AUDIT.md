# Suraksh Tracking Audit

Status: baseline audit and corrective implementation complete for the local
recorded viewer. This document records code-grounded findings; it does not
claim detector accuracy without annotated evaluation footage.

## Baseline data path

The A/B demo tiles use `backend/app/services/tracking_preview.py`: OpenCV
decodes a recorded MP4, a one-slot latest-frame buffer feeds Ultralytics, and
the encoded annotated JPEG is served through `/demo-media/{name}/preview`.
The browser polls `/runtime` for the metadata overlay.

`OP.mp4` previously used a separate browser canvas path. It read sparse
precomputed samples (`step=10`, approximately 3 analysed FPS), interpolated
boxes by ID, and played the original video independently. The two paths used
different model/input-size settings and different timing semantics.

Measured source metadata in the repository:

| Source | FPS | Frames | Resolution |
| --- | ---: | ---: | --- |
| `anpr-vms-a.mp4` | 25.000 | 525 | 1920x1080 |
| `anpr-vms-b.mp4` | 23.976 | 263 | 1280x720 |
| `OP.mp4` | 30.000 | 5478 | 1918x1138 |

## Exact baseline loss points

1. The live worker sampled at `AI_FPS=5`, overwrote a single latest frame, and
   explicitly dropped source frames. The tracker received non-consecutive
   detections without source-frame timestamps, so its motion model could not
   use the real `Δt`.
2. A/B used a 320-pixel inference size and one detector confidence threshold.
   The UI could not distinguish detector misses from association misses.
3. The previous mapping from tracker output to detector indexes was opaque;
   detector boxes were counted even when they had no track ID. This produced
   visible-count/ID-count disagreement and unstable anonymous histories.
4. BoT-SORT ran with GMC disabled and ReID disabled. GMC is reasonable for
   fixed CCTV, but no project telemetry existed for matches, unmatched boxes,
   created tracks, lost tracks, or deletion.
5. `OP.mp4` used sparse samples and browser interpolation without source
   timestamps, visibility intervals, or entering/exiting-track handling. A
   separate analysis-paced backend path could also block playback behind CPU
   inference.
6. The edge path reopened each source for every read, used wall-clock event
   timestamps, and its `AnonymousTracker` performed no association or expiry.
7. The local runtime had a Torchvision binary that imported but failed at
   Ultralytics NMS warm-up (`torchvision::nms`), causing `AI_ERROR` before any
   detections could be produced.

## Corrective implementation

- A/B publication now pairs the annotated image and analysis from the same
  source frame. Decode remains bounded/latest-only; it no longer publishes
  stale boxes over newer pixels.
- Source frame index, source-relative timestamp, capture age, and processing
  telemetry are carried through the worker. Tracker association uses source
  time rather than wall-clock polling cadence.
- `TimestampAwareTracker` provides per-camera state, high/low confidence
  association, class-aware matching, velocity prediction, confirmation,
  bounded lost-track retention, deletion, and lifecycle telemetry.
- `OP.mp4` evaluation generation supports every decoded frame (`step=1` by
  default) and emits source timestamps. Prepared replay remains 1x source
  playback and handles short track entry/exit gaps explicitly.
- The launcher detects the available server environment, while the viewer
  patches the known missing compiled NMS extension to Ultralytics' pure Torch
  implementation. This is a runtime compatibility fallback, not a model
  change.

Runtime tuning is explicit and local-only: `SURAKSH_YOLO_MODEL`,
`SURAKSH_AI_FPS`, `SURAKSH_INFERENCE_SIZE`, `SURAKSH_TRACK_HIGH_CONF`,
`SURAKSH_TRACK_LOW_CONF`, `SURAKSH_NEW_TRACK_CONF`,
`SURAKSH_TRACK_IOU`, `SURAKSH_TRACK_MAX_LOST_SECONDS`, and
`SURAKSH_TRACK_MIN_HITS`. Lowering thresholds may increase recall and false
positives; acceptance values must come from the annotated evaluation set.

## Remaining acceptance gates

The repository still needs an annotated, rights-approved evaluation set to
measure precision, recall, IDF1, ID switches, MOTA, detection delay, and
false positives/hour. No production accuracy claim should be made from the
synthetic demo recordings alone.
