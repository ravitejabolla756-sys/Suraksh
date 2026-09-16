# SURAKSH Phase 4 local runtime

This is a synthetic hackathon demonstration, not a deployed police system or a real-world ANPR accuracy claim. Camera locations and plates are synthetic; timestamps represent recorded-video replay observations.

## Start locally

From `C:\site\CC`, in separate terminals:

```powershell
python -u scripts/local_runtime.py
python -u scripts/local_vms.py --source A
python -u scripts/local_vms.py --source B
```

The backend launcher applies Alembic migrations before serving `http://127.0.0.1:8000`. Swagger is at `/docs`. It creates random machine/JWT credentials in ignored `.runtime/phase4.env`, and uses `.runtime/phase4.sqlite3`. Never publish that environment file. The local runtime seed creates configuration and demo users only, not detections, alerts, watchlists, or cameras.

From `C:\site\CC\frontend`:

```powershell
npm run build
npm run dev -- --hostname 127.0.0.1
```

Open `http://127.0.0.1:3000`. The intentionally local demo login is `admin@suraksh.demo` / `Suraksh123!`. Do not expose demo-seeded services publicly.

## Prove the pipeline

```powershell
.\scripts\e2e-demo-test.ps1 -Mode Local -BackendUrl http://127.0.0.1:8000
python scripts/verify_phase4_media.py
```

Every E2E run loads the local `yolo11n.pt`, opens the two generated MP4 inputs, decodes frames, invokes YOLO and Tesseract, and submits machine-authenticated observations. It never loads a previous recognition JSON or injects the expected plate. The expected string appears only in test assertions. The extractor chooses OCR output by agreement and confidence, independently of those assertions.

The default evidence frames are A:299 and B:80 (zero-based). After watchlist setup, A:300 is decoded and recognized independently. All preprocessing/PSM attempts are saved. No originals or generated input videos are rewritten by Phase 4.

Each run creates an evidence directory `.runtime/phase4/<run-id>/` containing `result.json`, source frames, YOLO annotation, detected vehicle crops, plate crops, preprocessed OCR inputs, and every OCR attempt. Retries within a replay occurrence use the same unique request ID; changed payloads with that key return HTTP 409. A new run is a new explicitly labelled replay occurrence, so its observation timestamps and IDs are new.

The test fails loudly unless exact-ID API retrieval, two-camera search, chronological path, watchlist-triggered persistence, audit records, and authenticated SSE delivery all succeed. Detections and alerts enter the database only through normal backend ingestion. API contract tests use a separate disposable database, never the runtime database.

For visual realtime verification, leave `/alerts` open with `SSE CONNECTED` before running E2E. The new alert must show `Received automatically via SSE` without refreshing. Reconnects use a persisted alert cursor and refresh the persisted list to close initial-subscription gaps.

## Runtime API additions

- `GET /detections/{id}`: exact persisted observation; authenticated organization visibility.
- `GET /investigations/path?plate=...`: chronological observations with coordinates and explicit missing-coordinate IDs. The UI label is **Observed Camera Detection Path**; connecting lines are not a claimed road route.
- `POST /detections/ingest`: existing machine-key authentication, optional idempotency key, camera/department validation, camera-owned coordinates, watchlist matching and transactional audit.
- `GET /alerts/stream`: authenticated fetch/SSE, committed rows only, reconnect cursor via `after` or `Last-Event-ID`, heartbeats and short-lived DB sessions.
- `GET /demo-media/{allowlisted-name}` and `/preview`: explicitly configured local-demo files only. Preview is a bounded compatibility adapter streaming real successive JPEG frames decoded by OpenCV.

The two VMS adapters deliberately expose different inventory schemas. Their event lists are empty: they are not a source of fabricated OCR detections. Click Sync in Federation to verify their actual HTTP reachability.

## Viewer and health boundaries

Chromium does not support the generated MPEG-4 video codec on this machine. The viewer tries native playback, then uses a clearly labelled OpenCV multipart-JPEG sampled replay. It is not a still-image placeholder, live RTSP, or a second ANPR result. At most four preview connections are allowed; it closes decoders on disconnect. Originals and frame dimensions/FPS remain unchanged on disk.

Camera health indicates that an actual file was readable at the most recent replay check, not continuous camera uptime. The legacy registry FPS is nominal/rounded; `CameraHealth.measured_fps` and the inference metadata retain the precise measurement.

## Architecture, scale and remaining production risks

Recognition remains separate from transport, API business logic, persistence and UI. Detection creation, matching alerts and action audit are one transaction. A database-backed stream was chosen for durable local reconnect behavior without adding infrastructure.

This does not certify millions-user production readiness. Before real deployment: replace per-client polling with an outbox and broker-backed fan-out; use the supported PostgreSQL/PostGIS deployment with indexed/paginated investigation queries; add department-level user grants and scoped per-edge credentials; deploy a proper media gateway; implement retention, access review and load/security testing. Current user visibility follows the existing organization boundary and watchlist matching is department-scoped. No department-specific user-grant model is claimed here.

The white-rectangle plate crop is a synthetic-input heuristic, not a trained general plate detector. Two positive synthetic examples do not establish ANPR precision, recall, calibration or robustness. OCR confidence is Tesseract's word confidence, not a probability that a vehicle is suspicious. OSM basemap tiles require network availability. No external notification or real police action is triggered.

## Regression commands

```powershell
# C:\site\CC\backend
python -m pytest -q
python -m compileall -q app
# C:\site\CC
python -m compileall -q edge-ai/app scripts
python scripts/local_runtime.py --migrate-only
.\scripts\e2e-demo-test.ps1 -Mode Local -BackendUrl http://127.0.0.1:8000
# C:\site\CC\frontend
npx tsc --noEmit
npm run lint
npm run build
```

Tests currently emit an upstream Starlette/httpx deprecation warning; it is not suppressed and working packages were not reinstalled to remove it.
