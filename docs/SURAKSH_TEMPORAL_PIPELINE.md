# Suraksh Temporal Pipeline

## Contract

`edge-ai/app/perception/contracts.py` now defines the single authoritative `FramePacket` (with `DetectorInput` retained as a compatibility alias). Every packet entering a detector or tracker carries:

- camera ID
- monotonically increasing source frame index
- source-video timestamp and FPS
- monotonic capture timestamp
- processing timestamp assigned when a consumer pops the packet
- image payload

Source time is media time and is never replaced with wall-clock time. Capture and processing timestamps are monotonic diagnostics for latency only.

## Execution modes

`PerCameraFrameQueue` is bounded and camera-scoped. In `REALTIME`, overflow drops the oldest pending packet to keep latency bounded. In `EVALUATION`, overflow raises `OverflowError`; the producer must apply backpressure, so no frame is silently discarded. Submission and consumption reject backward source frame numbers.

The evaluation dataset decoder creates packets for the exact annotated source frame. Tracker adapters validate frame identity and source timestamp, and advance missing source frames with empty updates when a later packet skips indices. Motion therefore follows source elapsed time rather than CPU scheduling time.

## Replay synchronization

Prepared replay validates that cached samples have strictly increasing frame numbers and source timestamps before rendering. Canvas lookup is driven by browser media time and source FPS; invalid cache ordering is rejected, and samples outside their source-time interval are not drawn instead of attaching older analysis to a later video position. Interpolation remains an explicit visualization estimate between valid source-timestamped samples; it is not a new detector result.

## Boundaries and limitations

This task does not change detector architecture, weights, NMS, or tracker algorithm selection. It establishes the temporal identity contract needed to measure those components fairly. Realtime dropping is intentional and observable; evaluation mode is the deterministic path for frame accounting and metrics. The YouTube tile remains view-only and is not an AI input.
