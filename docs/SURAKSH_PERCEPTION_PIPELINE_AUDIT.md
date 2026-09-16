# Suraksh Perception Pipeline Audit

**Audit date:** 2026-09-15
**Scope:** existing person/vehicle perception and replay paths in this repository
**Change policy:** audit only; no runtime or unrelated module changes were made.

## Executive summary

The `/viewer` implementation is a local recorded-video preview. It is not a complete production MOT pipeline and it is not processing the embedded YouTube camera. The active path is:

```text
MP4 -> OpenCV decode thread -> one-slot latest-frame buffer
     -> AI thread (at most 5 FPS) -> YOLO inference -> custom timestamp tracker
     -> current-frame counts/JPEG -> multipart MJPEG preview + 300 ms runtime polling
```

`OP.mp4` uses a different path:

```text
OP.mp4 -> prepared offline cache (YOLO26n + custom timestamp tracker)
        -> normal-speed HTML video -> canvas lookup/interpolation by media time
```

The following are confirmed causes of temporal gaps, apparent slow/unsynchronised analysis, and ID instability:

1. Decode uses a single-slot latest-frame buffer. Frames are overwritten when AI is behind; there is no FIFO queue or backpressure policy that preserves every frame.
2. The decoder intentionally calls `grab()` to skip overdue source frames in real-time mode. It records `playback_drops`, and the AI loop records skipped source indices as `frame_drops`.
3. AI runs at `SURAKSH_AI_FPS` default 5 FPS while demo containers are normally around 25 FPS. A vehicle can therefore enter and leave between inference samples.
4. Inference and display have separate clocks. The MJPEG endpoint repeats the most recent encoded result until a newer version exists, while runtime is polled independently every 300 ms.
5. The active tracker is `TimestampAwareTracker`, not Ultralytics BoT-SORT. It uses greedy class-aware matching based on predicted-box IoU and centre distance, with exponentially smoothed linear velocity. There is no Kalman filter, Hungarian assignment, explicit lost state, track reactivation state, or occlusion model.
6. Tracks are confirmed only after `min_hits=2`; tracks are deleted after 1.5 seconds of timestamped misses by default. A later detection creates a new ID.
7. Counts are detections visible in the latest accepted inference, not a ground-truth count and not a stable unique-object count. The `unique_*` fields are IDs observed during the current replay epoch and inherit ID recreation errors.
8. `OP.mp4` is cached at `SURAKSH_OP_REPLAY_STEP` default 1 in the current script, but its canvas only has detection samples and interpolates between them. A missing detection is not recovered by interpolation; it is suppressed after the interpolation gap threshold.

These findings do **not** prove that YOLO is the root cause. The repository contains no labelled MOT evaluation for the affected clips, so detector recall, precision, localization quality, and class confusion are not quantified. The evidence currently supports a system-level sampling/tracking/synchronization diagnosis, with detector misses still a separate possible contributor.

## Inspected implementation

- `backend/app/services/tracking_preview.py` — active worker, decode, inference, counting, JPEG publication.
- `backend/app/services/timestamp_tracker.py` — active viewer tracker.
- `backend/app/services/preview_ocr.py` — asynchronous sidecar OCR.
- `backend/app/api/demo_media.py` — preview, runtime, media, and prepared-track endpoints.
- `frontend/components/RecordedViewer.tsx` — normal recorded preview and runtime polling.
- `frontend/components/PreparedReplay.tsx` — OP prepared replay.
- `scripts/prepare_op_replay.py` and `docs/OP-REPLAY.md` — OP cache generation and stated limitations.
- `edge-ai/app/frame_source.py`, `detector.py`, `tracking.py`, and `app/perception/*` — parallel edge/evaluation code, not the backend `/viewer` worker.

## Stage-by-stage trace

### 1. Source, capture, and timestamps

The demo API allowlist admits `anpr-vms-a.mp4`, `anpr-vms-b.mp4`, and `OP.mp4`. `TrackingPreviewWorker` opens the selected file with `cv2.VideoCapture`. Container FPS is read from `CAP_PROP_FPS`, clamped to at least 1 FPS, and defaults to 25 FPS if unavailable. Each decoded frame receives:

- `frame_index`: `CAP_PROP_POS_FRAMES - 1`.
- `source_timestamp`: `CAP_PROP_POS_MSEC / 1000`, or `frame_index / source_fps` when the container timestamp is unavailable.
- `captured_at`: `time.monotonic()` for local processing age, not source time.
- `epoch`: incremented when playback reaches EOF and loops back to frame zero.

The source timestamp is therefore media time; `captured_at` is processing/arrival time. They must not be compared as if they were the same clock.

The parallel `edge-ai` `FramePacket` has the same conceptual split (`source_timestamp`, `source_fps`, `captured_at`, and sequence number), but its `OpenCVFrameSource` is not called by the current `/viewer` route. It should not be used as evidence about the active backend path.

### 2. Queue and frame dropping

There is no bounded FIFO frame queue in `TrackingPreviewWorker`. The decoder stores only `latest_frame`, `latest_frame_index`, `source_timestamp`, and `captured_at` under a lock. The AI thread copies that frame under the same lock.

When real-time decode is overdue, the decoder computes overdue source frames and calls `cap.grab()` for up to 100 of them. These are counted as `playback_drops`. If the AI sees a later index than the previous processed index, the skipped indices are added to `frame_drops`. Consequently, `frame_drops` measures source indices not analysed by AI, not necessarily decoder failure.

The preview endpoint polls the worker in a thread pool and emits the latest JPEG roughly every 40 ms. It does not create a frame-preserving stream: the same encoded version can be emitted repeatedly, and intermediate source frames can never be displayed if they were overwritten.

### 3. Preprocessing and detector

The active detector is Ultralytics `YOLO` loaded from `SURAKSH_YOLO_MODEL`, defaulting to repository-root `yolo11n.pt`. The requested classes are COCO IDs `[0, 2, 3, 5, 7]`: person, car, motorcycle, bus, and truck. An optional per-camera ROI crops the image before inference and offsets boxes back to full-frame coordinates.

Default runtime settings in `tracking_preview.py` are:

| Setting | Current behavior |
|---|---|
| Inference size | 640; 960 for `OP.mp4` via `SURAKSH_OP_INFERENCE_SIZE` |
| Inference rate | `SURAKSH_AI_FPS`, default 5 FPS |
| Detector confidence | tracker low threshold, default 0.15 |
| NMS IoU | no explicit `iou` argument in `model.predict`; Ultralytics default applies |
| Device | CUDA if available, otherwise CPU |
| Torch threads | forced to 2 in the AI loop |
| Classes | person, car, motorcycle, bus, truck |

Postprocessing calls `prediction.boxes.cpu().numpy()` and keeps only the known class IDs. The active call does not provide an explicit NMS IoU threshold; therefore the exact Ultralytics-version default must be treated as a dependency setting, not as a Suraksh acceptance value. The code does not currently expose detector precision/recall or per-class miss diagnostics.

`prepare_op_replay.py` is different: it loads `yolo26n.pt`, performs a 1280-pixel full-scene pass and a 960-pixel pass over the left 62% of the frame, uses confidence `.18`, then applies its own class-aware NMS at IoU `.45` before tracker association. This is an offline OP-specific pipeline, not the normal worker.

### 4. Tracker and lifecycle

The active worker constructs `TimestampAwareTracker` on each replay epoch. Its defaults are:

| Parameter | Default |
|---|---:|
| high confidence | 0.35 |
| low confidence | 0.15 |
| new-track confidence | 0.45 |
| association IoU threshold | 0.05 |
| max lost seconds | 1.5 |
| minimum hits | 2 |

The tracker splits detections into high and low confidence sets. Existing tracks are associated to high detections and then low detections. Matching is class-aware and greedy: candidate pairs are sorted by score, and a pair score combines IoU of a linearly predicted box (0.65) with centre-distance similarity (0.35). A centre-distance gate is also applied.

Track state includes the last box, confidence, class, hit/miss timestamps, hit count, and exponentially smoothed velocity. It is **not** a Kalman state. There is no appearance/ReID feature in the active tracker, despite the `PreviewTracker(BOTSORT)` class existing in the module; that class is not instantiated by `_ai_loop`.

- Creation: only detections at or above `new_track_confidence` create a track.
- Confirmation: output ID is withheld until `hits >= min_hits`.
- Matching: existing tracks retain their ID while they can be matched within the timestamp loss horizon.
- Miss/loss: unmatched tracks remain internally until `missed_seconds > max_lost_seconds`.
- Deletion: expired tracks are removed.
- Reactivation: there is no explicit reactivation path or telemetry. A detection after deletion creates a new track ID.
- Occlusion: there is no appearance association, multi-frame occlusion buffer, or predicted-track output; an occluded object can disappear from visible results and later return as a new ID.

The tracker emits telemetry for high/low detections, matches, unmatched detections, creation, active, visible, and deletion. It does not report a detector miss, an occlusion, an ID switch, or a reactivation separately.

### 5. Counting and event generation

`_analysis()` counts the known detections returned by the detector on the current analysed frame. `vehicles` is the sum of cars, motorcycles, buses, and trucks. `unique_*` is the size of per-epoch sets of IDs that have appeared; it is not a verified unique-object metric.

`_publish()` marks an observation fresh when it belongs to the current epoch and is no older than `COUNT_TTL_SECONDS` (default 1.5 seconds) in real-time replay. Fresh counts are shown; stale counts are changed to `null` rather than fabricated zeroes. This is correct uncertainty handling, but it means an operator can see rapidly changing or blank counts while AI lags the display.

This worker does not generate incidents or safety events. The backend event and safety-incident APIs are separate ingestion paths. The embedded YouTube tile is explicitly view-only and has no backend AI ingestion. Therefore a YouTube frame cannot be counted or tracked by this worker.

### 6. Snapshot/JPEG publication

For each successful AI result, `_publish()` resizes the source frame to at most `PREVIEW_WIDTH` (default 960), draws boxes only when the analysis is fresh, adds a status/frame label, and encodes three annotation/track-ID variants at JPEG quality 90. The cached JPEG and snapshot are replaced atomically under the worker lock. The JPEG is from the same source frame as the analysis, but it is not necessarily the frame currently being decoded when the browser receives it.

On detector exceptions, the worker records `AI_ERROR`, resets its processed marker, waits 0.5 seconds, and continues. This prevents an inference failure from killing the decode loop, but it also creates a visible analysis gap and can reset effective tracking continuity after recovery.

### 7. Frontend replay and display

For `anpr-vms-a.mp4` and `anpr-vms-b.mp4`, `RecordedViewer` renders the multipart JPEG preview and polls `/runtime` every 300 ms. Pause stops the image request. The browser does not control source playback timing for these previews; the backend decode worker does.

For `OP.mp4`, `RecordedViewer` renders `PreparedReplay`. The browser plays the original MP4 at normal speed. `requestVideoFrameCallback` uses `metadata.mediaTime`, converts it to a cache frame using cached FPS, binary-searches adjacent analysed samples, and linearly interpolates matching IDs. It suppresses a missing object after a ratio greater than `.45` and delays a newly appearing object until `.55`. Those estimates improve visual smoothness between cache samples, but they cannot restore detections absent from the cache. The displayed count is the object count at the preceding cache sample, not a live per-frame detector count.

## Precise root-cause analysis

### Confirmed system causes

- **Temporal sampling loss:** default 5 FPS AI processing and the latest-only buffer guarantee that many source frames are never analysed.
- **Real-time skip policy:** overdue decode explicitly skips source frames, so fast objects may have no analysed frame while crossing the scene.
- **Weak association model:** greedy IoU/centre matching with linear velocity is vulnerable to crossing objects, scale changes, fast motion, camera perspective, and occlusion.
- **Short lifecycle horizon:** 1.5 seconds is insufficient for prolonged occlusion or detector gaps; after expiry IDs are recreated.
- **Delayed confirmation:** `min_hits=2` hides first appearances and makes short-lived objects invisible to the displayed track count.
- **Clock/display mismatch:** source timestamps, wall-clock capture age, AI scheduling, multipart polling, and browser video time are separate timelines.
- **Prepared replay interpolation limits:** OP interpolation visually bridges samples but cannot infer an object missed by both adjacent analysed samples.

### Not yet proven

- YOLO class recall or localization quality.
- Whether the selected weights are appropriate for this camera geometry, night scene, or object scale.
- Whether the default Ultralytics NMS setting causes material duplicate suppression.
- Exact ID-switch rate, false positives/hour, or count error.

Those require annotated frames/sequences and an evaluator that aligns source timestamps, detector boxes, tracks, and ground truth. The existing evaluation utilities are useful infrastructure, but no result from them is evidence for this audit’s specific videos unless run against matching annotations.

## Where frame ordering can fail

1. Decoder skips frames before publishing the next frame when wall-clock decode falls behind.
2. Latest-frame overwrite allows AI to observe frame `N+K` after `N`, with no intermediate frames available.
3. AI results are published asynchronously from decode; the preview can show a newer raw frame while the overlay/snapshot describes an older frame.
4. Runtime polling and MJPEG delivery are independent requests and can observe different versions.
5. At EOF, epoch increments and the analysis/tracker state is cleared while the browser may still hold the prior JPEG briefly.
6. OP canvas lookup uses media time and cached source FPS; cache samples and browser decoded frames are not the same object stream, and interpolation intentionally suppresses long gaps.

## Detection miss versus tracking failure

The current telemetry cannot conclusively distinguish these cases:

- **Detector miss:** no candidate box exists for the object in an analysed frame. The tracker sees no input and cannot preserve a visible ID.
- **Association failure:** a candidate exists, but no existing track passes the class/IoU/distance gate, so a new ID may be created or the detection remains untracked.
- **Track expiry:** no candidate matched within the 1.5-second horizon, so the prior ID is deleted.
- **Display staleness:** the object may be present in the current decoded frame, but the displayed analysis is older or has been marked stale.

To separate them, diagnostics need per-source-frame detector outputs, matched/unmatched track records, explicit track state transitions, and labelled MOT metrics. Current `detector_high/low`, `matched_high/low`, `created`, and `deleted` counters are useful but insufficient for that attribution.

## Test execution

The audit itself introduced no code changes outside this document. After inspection, run the repository’s existing backend and edge test suites and record their exact results here before delivery. No production accuracy claim is made by this document.

Results from this audit run:

- `python -m pytest backend/tests -q` — **83 passed**, 1 dependency deprecation warning, 18.18 seconds.
- `python -m pytest edge-ai/tests -q --basetemp=.runtime/pytest-edge-audit` — **15 passed**, 8.79 seconds.

## Recommended next step (outside this audit)

Do not replace the detector blindly. First capture a labelled evaluation slice from each camera condition and measure detector recall separately from association metrics. Then address the confirmed timing contract (source-frame policy, queue/backpressure, timestamps, and replay mode) and tracker lifecycle using measured failure cases. Any implementation change should be a separate task with regression tests and explicit acceptance metrics.
