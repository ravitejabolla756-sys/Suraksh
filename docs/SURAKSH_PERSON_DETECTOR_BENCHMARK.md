# Suraksh Person Detector Benchmark

## Scope

This benchmark evaluates person detection only. It does not change the
production detector or viewer configuration. Candidate adapters are:

- current Suraksh detector (`yolo11n.pt` at configured resolutions);
- current YOLO implementation and newer local YOLO checkpoints when present;
- RF-DETR Nano/Small/Medium candidates;
- RT-DETRv2 R18/R34 candidates.

All candidates use the shared `PersonDetectionBenchmark` and receive the same
decoded sample pixels, source frame indices, source timestamps, camera IDs,
and evaluation split. The benchmark filters both predictions and annotations
to `class_name == "person"`; vehicle detections cannot inflate person scores.

## Required dataset strata

The annotation manifest must tag frames/objects for close, distant, tiny,
crowded, nighttime, bright nighttime, partial occlusion, near vehicles,
behind objects, entering, leaving, walking, running, and stationary people.
`small`, `distant`, `night`, `low_light`, `crowded`, and `occluded` tags are
recognized by the evaluator. Untagged strata remain unmeasured rather than
being inferred.

## Metrics

With approved annotated ground truth, the report measures precision, recall,
F1, AP50, AP50:95, false positives, false negatives, small-person recall,
nighttime recall, occluded-person recall, and crowded-person recall. Metrics
are computed from IoU-matched person boxes only.

Runtime measurements include preprocessing, inference, postprocessing,
end-to-end latency, FPS, CPU time, RSS/RAM, and available GPU metadata. The
benchmark records candidate load failures explicitly; an unavailable optional
package is not converted into a score.

## Reproducible execution

Use an approved manifest and identical sampled frames for every candidate.
Run the existing benchmark orchestration from the repository’s Edge Agent
environment, for example:

```python
from pathlib import Path
from app.perception.benchmark import PersonDetectionBenchmark, default_candidates, sample_video

root = Path("C:/site/CC")
samples = sample_video(root / "annotated-video.mp4", "camera-1", max_frames=1000)
report = PersonDetectionBenchmark(root, default_candidates(root)).run(samples, annotated=True)
```

The manifest/evaluation path is the acceptance path. A runtime-only report is
allowed for latency smoke testing, but all quality fields must remain null
without annotations.

## Results status and decision rule

No Suraksh accuracy result is claimed in this repository until annotated
footage is supplied and the benchmark is run. Published vendor or internet
numbers are not Suraksh results. Production promotion requires a reviewed
comparison across the requested strata plus runtime budget evidence; this
task does not automatically change the production model.
