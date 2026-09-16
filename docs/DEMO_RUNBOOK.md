# SURAKSH Demo Runbook

This runbook is for synthetic hackathon data only.

1. Start Compose with `scripts\demo-start.ps1` or `docker compose up --build`.
2. Confirm `http://localhost:8000/health`, `http://localhost:8091/health`, and `http://localhost:8092/health`.
3. Open `http://localhost:3000` and sign in using the intentionally local demo account in `README.md`.
4. Open CCTV Registry and inspect Ahmedabad, Surat, and Vadodara DEMO records.
5. Open Gujarat GIS and select a marker for registry details.
6. Open Federation to compare VMS A and VMS B schemas and status.
7. Open Investigations and search `GJ01AB1234`.
8. Open Watchlists and inspect the synthetic high-priority entry.
9. Open Unified Viewer. A stream is shown only when the MediaMTX HLS output is reachable; otherwise the state remains `STREAM UNAVAILABLE`.

The two RTSP publishers use generated test video frames and are valid synthetic media sources. They are not detection results. A YOLO result is only persisted when the edge process has decoded a frame and a local model was configured.

The current environment has OpenCV but no YOLO weights, FFmpeg binary, or OCR engine installed outside Docker. The edge worker therefore reports model or stream availability honestly and persists no fabricated detections.
