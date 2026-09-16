# Suraksh Person Detection and Tracking Benchmark

Status: **runtime benchmark complete; accuracy benchmark blocked by missing annotated ground truth. No production model selected.**

Generated from `.runtime/person-benchmark/results.json` on 2026-09-15. This was an eight-frame CPU smoke benchmark using exactly the same sampled frames from `demo-media/anpr-vms-a.mp4` and `demo-media/OP.mp4` for every configuration. One warm-up inference was excluded from the reported per-frame mean. The sample is too small for acceptance decisions.

## Current decision

The deployed demo default remains `yolo11n.pt`. No detector/tracker combination is promoted. The repository has no person bounding-box or identity ground truth, so person recall, precision, F1, AP, IDF1, HOTA, ID switches, and count error cannot honestly be reported. Detection totals below are diagnostic only; a model can produce more boxes because it has better recall or because it has more false positives.

## Host

- CPU: Intel64 Family 6 Model 170, 18 logical processors
- RAM: 15,989 MB
- GPU: none available to Torch
- Execution: PyTorch CPU in `.venv-ai`
- Sources: two local recorded videos; four evenly sampled frames from each

## Runtime results

| Detector configuration | Status | Mean end-to-end ms | Effective FPS | Process RSS MB at end | Person boxes / 8 frames | Weight/cache MB |
|---|---:|---:|---:|---:|---:|---:|
| Current YOLO11n 640 | completed | 451.133 | 2.213 | 401.77 | 36 | 5.35 |
| Current YOLO11n 960 | completed | 693.130 | 1.441 | 499.52 | 82 | 5.35 |
| YOLO26n 640 | completed | 281.914 | 3.538 | 494.41 | 30 | 5.29 |
| YOLO26n 960 | completed | 310.004 | 3.217 | 556.11 | 74 | 5.29 |
| YOLO26s 640 | completed | 600.399 | 1.663 | 624.69 | 61 | 19.48 |
| YOLO26s 960 | completed | 938.086 | 1.065 | 775.82 | 94 | 19.48 |
| RF-DETR Nano | completed | 950.886 | 1.051 | 914.33 | 209 | 349.32 |
| RF-DETR Small | completed | 1,511.665 | 0.661 | 1,073.11 | 210 | 368.16 |
| RF-DETR Medium | completed | 1,873.473 | 0.533 | 1,186.00 | 233 | 386.23 |
| RT-DETRv2 R18 | completed | 1,866.145 | 0.532 | 1,291.69 | 423 | 77.16 |
| RT-DETRv2 R34 | completed | 2,447.287 | 0.405 | 1,416.05 | 458 | 120.15 |

These are local PyTorch CPU measurements, not ONNX/OpenVINO results. RF-DETR warned that the models were not optimized for inference. CPU percentages in the raw JSON can exceed 100% because the process uses multiple logical cores.

## Accuracy and tracking results

| Required output | Current | YOLO26 | RF-DETR | RT-DETRv2 | Why |
|---|---:|---:|---:|---:|---|
| Person precision / recall / F1 | not measured | not measured | not measured | not measured | No annotated person boxes |
| AP50 / AP50:95 | not measured | not measured | not measured | not measured | No annotated person/vehicle boxes |
| Small / occluded / night / crowded recall | not measured | not measured | not measured | not measured | No tagged ground truth |
| ByteTrack IDF1 / HOTA / ID switches | not measured | not measured | not measured | not measured | No identity tracks |
| BoT-SORT IDF1 / HOTA / ID switches | not measured | not measured | not measured | not measured | No identity tracks |
| Actual/detected/unique people and count error | not measured | not measured | not measured | not measured | No line/zone count ground truth |

Both ByteTrack and BoT-SORT executed for every detector output through the common normalized contract with ReID disabled. Unit tests establish timestamp propagation, strict frame ordering, temporary-loss reactivation, and per-camera isolation. Those tests validate behavior, not real-world accuracy.

## Licensing and deployment gate

| Family | Current status | Deployment note |
|---|---|---|
| Ultralytics YOLO | review required | Installed package/weights are under AGPL-3.0 terms unless an appropriate enterprise license applies. Legal review is required for proprietary deployment. |
| RF-DETR Nano/Small/Medium | permissive core, verify artifact | Installed `rfdetr` package reports Apache-2.0. Record the exact checkpoint provenance and terms in the deployment bill of materials. |
| RT-DETRv2 R18/R34 | checkpoint review required | The official implementation is Apache-2.0, but the cached Hugging Face checkpoint snapshots do not include a local model card/license file. Verify checkpoint terms before promotion. |

The [official RF-DETR project](https://github.com/roboflow/rf-detr) documents Nano/Small/Medium and export support. The [official RT-DETR project](https://github.com/lyuwenyu/RT-DETR) and [Transformers RT-DETRv2 documentation](https://huggingface.co/docs/transformers/model_doc/rt_detr_v2) cover RT-DETRv2 and its R18/R34 checkpoints. Published vendor metrics are not used as Suraksh results.

## What the evidence currently says

- No candidate reaches live CCTV speed on this CPU in unoptimized PyTorch. A bounded latest-frame queue is mandatory for live mode; deterministic evaluation must use backpressure and process every selected frame.
- YOLO26n was fastest in this small run, but speed alone does not justify selection.
- Higher resolution generally produced more person boxes, but without ground truth this cannot be called better recall.
- RF-DETR and RT-DETRv2 produced many more low-threshold person boxes while using much more memory and latency. This could include both distant people and false positives.
- Tracker quality cannot be ranked from sparse unannotated frames. ByteTrack versus BoT-SORT remains undecided.

## Acceptance benchmark required next

1. Build or obtain a rights-approved, representative Suraksh CCTV set with person/vehicle boxes, anonymous track IDs, count-line events, occlusion/visibility, and scene tags.
2. Use camera-grouped train/validation/test splits so adjacent frames and the same camera do not leak across splits.
3. Run at least the 640/960 configurations above on all selected frames in evaluation mode; add sliced inference as a separate candidate only if small-person recall remains weak.
4. Rank first by person recall, then precision, small/night recall, IDF1/HOTA, ID switches, count error, end-to-end latency, memory, deployment compatibility, and licensing.
5. Benchmark ONNX/OpenVINO on the target edge hardware and ReID as an explicit optional configuration.
6. Promote only after a documented review. Never switch defaults automatically.

## Remaining failure cases and risks

- Unmeasured false positives on signs, poles, reflections, headlights, and bright nighttime regions.
- Unmeasured distant-person and partial-occlusion misses.
- No crowded crossing or long-occlusion identity evaluation.
- No camera-motion, rain, indoor, or multiple-focal-length coverage.
- No calibrated count line/zone ground truth.
- CPU PyTorch latency is not representative of optimized edge deployment.
- Model and dataset licensing still require a deployment-specific bill of materials and approval.
