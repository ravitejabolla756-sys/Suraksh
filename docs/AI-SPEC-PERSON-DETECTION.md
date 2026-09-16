# Suraksh Person/Vehicle Perception Contract

## Scope and boundary

This package is an isolated detector/tracker benchmark inside Edge AI. It does not change the deployed viewer detector, incident policy, alerts, identity systems, face recognition, or plate recognition. Track IDs are anonymous, session-local, and camera-local.

## Architecture

```text
Frame source
  -> source timing envelope
  -> detector adapter
  -> normalized detections
  -> class-aware ByteTrack or BoT-SORT
  -> temporal track state
  -> benchmark metrics / developer diagnostics
```

`DetectorInput` carries pixels, source frame index, source timestamp, source FPS, capture timestamp, and camera ID. `Detection` carries class, confidence, box, and the same source position. A tracker receives only normalized detections; it has no detector-specific branch.

Implemented adapters:

- Ultralytics: current `yolo11n.pt`, `yolo26n.pt`, and `yolo26s.pt`, each at 640 and 960 input size.
- RF-DETR: Nano, Small, and Medium through the optional `rfdetr` package.
- RT-DETRv2: R18 and R34 through the optional Transformers package.
- Trackers: ByteTrack and BoT-SORT with one state machine per camera and class. ReID is off by default.

## Time and execution semantics

Recorded frames use `source_timestamp = source_frame_index / source_fps` when the container does not expose an authoritative presentation timestamp. Processing timestamps use a monotonic clock. Tracker progression follows source frame positions, never inference wall time.

`PipelineMode.REALTIME` uses a bounded per-camera queue and drops the oldest pending frame when full. `PipelineMode.EVALUATION` never drops; queue saturation applies backpressure as an explicit error so the caller must drain it. Evaluation input order is deterministic.

## Metrics

With approved ground truth, the evaluator computes class-aware precision, recall, F1, false positives, false negatives, AP50, AP50:95, small/occluded/night/crowded person recall, ID switches, IDF1, HOTA over IoU thresholds 0.05 through 0.95, MOTA, fragmentation, average matched track lifetime, and count error.

Without ground truth, all accuracy and tracking-quality metrics are `null`. Raw detection counts are diagnostics and must not be interpreted as recall.

Per-frame tracker telemetry distinguishes detector outputs, matched tracks, unmatched detections, unmatched tracks, new tracks, reactivated tracks, expired tracks, and predicted/lost tracks. The viewer's diagnostics are available only in a non-production build.

## Dataset contract

The JSON manifest must declare dataset name/version, provenance, license, explicit intended-use permission, video path, camera, source frame index/FPS/timestamp, scene tags, object boxes, classes, optional track IDs, visibility, and occlusion. Loading fails closed when provenance, license, permission, media, or timestamp consistency is missing.

The benchmark does not download or create training data. Fine-tuning is a later gate after counsel or the data owner confirms commercial rights.

## Failure handling

Each candidate loads and executes independently. Missing packages, weights, incompatible checkpoints, and runtime failures are recorded per candidate and do not modify the deployed configuration. Atomic JSON replacement prevents partial result files.

## Running

```powershell
.\.venv-ai\Scripts\python.exe -m pip install -r edge-ai\requirements-benchmark.txt
.\.venv-ai\Scripts\python.exe scripts\person_detection_benchmark.py --max-frames 8
.\.venv-ai\Scripts\python.exe scripts\person_detection_benchmark.py --manifest C:\path\approved-manifest.json --max-frames 256
```

The first command installs only optional benchmark dependencies. The second is runtime-only. The third is an accuracy evaluation and will refuse a manifest without explicit provenance and intended-use permission.

## Production promotion gate

A candidate may be proposed only after a sufficiently large, representative, rights-approved CCTV evaluation covers day, night, low light, indoor/outdoor, distant/small people, occlusion, crowds, camera heights, focal lengths, entry/exit, and person/vehicle interaction. Promotion requires accuracy, tracking, count, latency, memory, deployment, and licensing review. This framework never promotes automatically.
