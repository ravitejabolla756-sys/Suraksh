# SURAKSH Traffic Analytics Validation

Date: 2026-09-10
Sources: generated recorded CCTV demo videos derived from VMS-A and VMS-B
Model: YOLO11n with Ultralytics YOLO.track(..., persist=True) and ByteTrack
Classes: person, car, motorcycle, bus, truck

The model count is the number of tracked detections visible in the sampled
frame. The manual count is a visual count of clearly distinguishable people
and vehicles in the contact sheet, excluding ambiguous distant/background
objects. It is a reasonableness check, not a ground-truth accuracy claim.

| Source | Frame | Model people | Manual people | Difference | Model vehicles | Manual vehicles | Difference |
|---|---:|---:|---:|---:|---:|---:|---:|
| VMS-A | 0 | 2 | 1 | +1 | 17 | 15 | +2 |
| VMS-A | 47 | 4 | 2 | +2 | 10 | 9 | +1 |
| VMS-A | 95 | 1 | 1 | 0 | 16 | 14 | +2 |
| VMS-A | 142 | 2 | 1 | +1 | 8 | 8 | 0 |
| VMS-A | 190 | 0 | 0 | 0 | 12 | 10 | +2 |
| VMS-A | 238 | 0 | 0 | 0 | 12 | 11 | +1 |
| VMS-A | 285 | 5 | 2 | +3 | 8 | 7 | +1 |
| VMS-A | 333 | 3 | 2 | +1 | 13 | 11 | +2 |
| VMS-A | 381 | 2 | 2 | 0 | 13 | 10 | +3 |
| VMS-A | 428 | 2 | 2 | 0 | 11 | 10 | +1 |
| VMS-A | 476 | 3 | 2 | +1 | 11 | 10 | +1 |
| VMS-A | 524 | 5 | 2 | +3 | 11 | 10 | +1 |
| VMS-B | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| VMS-B | 23 | 0 | 0 | 0 | 0 | 2 | -2 |
| VMS-B | 47 | 0 | 0 | 0 | 0 | 2 | -2 |
| VMS-B | 71 | 4 | 3 | +1 | 2 | 2 | 0 |
| VMS-B | 95 | 0 | 0 | 0 | 4 | 4 | 0 |
| VMS-B | 119 | 1 | 1 | 0 | 5 | 4 | +1 |
| VMS-B | 142 | 4 | 3 | +1 | 4 | 4 | 0 |
| VMS-B | 166 | 7 | 5 | +2 | 4 | 4 | 0 |
| VMS-B | 190 | 1 | 1 | 0 | 3 | 3 | 0 |
| VMS-B | 214 | 7 | 5 | +2 | 5 | 4 | +1 |
| VMS-B | 238 | 2 | 2 | 0 | 6 | 5 | +1 |
| VMS-B | 262 | 5 | 4 | +1 | 6 | 5 | +1 |

## Replay totals

| Source | Frames decoded | Unique people tracks | Unique vehicle tracks | Cars | Motorcycles | Buses | Trucks |
|---|---:|---:|---:|---:|---:|---:|---:|
| VMS-A | 525 | 30 | 130 | 93 | 5 | 2 | 30 |
| VMS-B | 263 | 39 | 31 | 19 | 0 | 5 | 7 |

The unique counts are session/window counts from stable tracker IDs. If a
tracker loses and recreates an ID, the unique total can over-count one physical
object; this is intentionally documented rather than hidden.

## Line crossing

The reusable service supports an optional virtual line and debounces each
`track_id`/direction pair. The current recorded-camera demo run used no
configured counting line, so persisted A→B and B→A counts are zero and are not
presented as measured traffic flow.

## Evidence

- `C:\site\CC\.runtime\phase5\analytics-results.json`
- `C:\site\CC\.runtime\phase5\analytics-review-vms-a.jpg`
- `C:\site\CC\.runtime\phase5\analytics-review-vms-b.jpg`

All analytics inputs are labelled synthetic recorded CCTV. No face recognition
or person identity inference is performed.
