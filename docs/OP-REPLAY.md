# OP.mp4 prepared replay

The OP tile uses browser H.264 playback at the source's normal speed. A transparent
canvas draws cached detections using `requestVideoFrameCallback` media timestamps.
Seeking and looping use the same timeline lookup. Counts come from the preceding
analysed sample. Positions interpolate only between matching track IDs, at most
one sample interval apart; these intermediate positions are estimates.

Generate analysis from the repository root:

```powershell
python scripts/prepare_op_replay.py
```

The worker uses local YOLO26n weights, a 1280-pixel full-scene pass and a 960-pixel
pass over the left 62% of the frame to cover the left road and station entrance.
Overlapping same-class predictions are suppressed before BoT-SORT association.
Analysis runs at 3 samples per source second; this is not live 30 FPS inference.
The original video is never changed. Processing runs once and is shared by all
viewers, which no longer start an OP live inference worker.

`.runtime/op-replay/tracks.json` is published atomically after the whole clip is
decoded. The API rejects the cache if source size or modification time changes.
Until analysis is available, the UI plays the source with an analysis-pending
message and no counts. Refreshing or seeking does not restart analysis.

The existing demo-media allowlist and demo-mode gate also apply to `/tracks`.
This local demo transport does not provide production media authorization.

Model confidence and predicted counts do not establish measured accuracy.
Distant, occluded and glare-covered objects may still be missed. Evaluate labelled
frames and ID continuity before making quantitative accuracy claims. This change
does not add plate recognition or fabricate plates.
