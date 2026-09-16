# Suraksh CCTV Dataset Pipeline

## Purpose

Suraksh training data must represent the actual target domain: high-mounted
and wide-angle cameras, distant/tiny people, day/night/low-light scenes,
crowded intersections, sparse scenes, occlusions, vehicles blocking people,
pedestrians near vehicles, and indoor/outdoor cameras. The repository does
not invent or silently download footage; approved recordings must be supplied
and annotated.

## Layout

```text
dataset/
  train/
  val/
  test/
  manifest.json
  annotations/
```

The existing manifest format in `edge-ai/app/perception/dataset.py` stores
camera/session identity, source frame index, source timestamp/FPS, boxes,
classes, optional track IDs, occlusion/visibility, and scenario tags. Export
to the selected detector’s native format only after validation; keep the
manifest as the canonical provenance and evaluation index.

## Provenance and licensing

Every source requires origin/owner, capture date, camera/session identifier,
consent or collection authority, license text/URL, permitted commercial use,
redistribution restrictions, and a checksum. `intended_use_permitted` must be
true before loading. Unknown, research-only, non-commercial, or incompatible
licenses are excluded from Suraksh training and evaluation.

## Leakage-safe splits

Use `split_by_source()` to assign complete camera/video sessions to one split.
Never split adjacent frames from one recording across train, validation, and
test. Run `assert_no_source_leakage()` before training. The test set must stay
completely held out, including during threshold selection and checkpoint
selection.

## Training boundary

Train only the detector selected after the person/vehicle benchmark and a
commercial license review. Preserve the pretrained checkpoint as candidate A
and record the fine-tuned checkpoint, configuration, dataset version, class
map, and export format as candidate B. Do not change production weights from
this pipeline automatically.
