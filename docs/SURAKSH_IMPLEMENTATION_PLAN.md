# SURAKSH Implementation Plan

## 1. Mission and delivery boundary

Transform VisionGuard AI from a school safety demo into SURAKSH, a vendor-neutral government CCTV federation platform for the Gujarat Police Hackathon 2026.

The MVP will implement Model 1 (central CCTV registry and GIS foundation), Model 3 (VMS federation middleware), and the most defensible Model 2 capabilities: unified browser viewing, vehicle metadata search, watchlists, health, and observed cross-camera paths. Existing departmental VMS systems remain authoritative; SURAKSH stores registry and event metadata rather than statewide video.

All sample departments, cameras, VMS systems, streams, detections, and plates are synthetic and visibly marked `DEMO`. A local stream source is valid test media; a generated detection is not valid evidence unless it came from decoded frames and the configured detector/OCR pipeline.

## 2. Stage 0 audit findings

### Reusable

- FastAPI application, SQLAlchemy models, Pydantic DTOs, JWT authentication, role checks, org-scoped camera/event queries, notification cooldown logic, audit log entity, and backend test harness.
- Docker Compose PostgreSQL/Redis topology and standalone Next.js build.
- Existing camera/event/alert UI primitives and API client patterns.
- Edge upload buffering, YAML source configuration, and the existing event normalization boundary.

### Replace or isolate

- `DemoDetector` synthetic crowd/intrusion generation must become a real frame-processing adapter; demo fixtures belong only in explicit seeded/demo mode.
- `WebsiteFlow` silently falls back to hardcoded data and contains school, pricing, CRM, and fake onboarding states. It will become a SURAKSH control-room shell with explicit loading, empty, unavailable, and DEMO states.
- Static camera images are not active feeds. Add MediaMTX HLS/RTSP plumbing and an explicit unavailable state.
- `create_all` is not a deployment migration strategy. Add Alembic and PostGIS-ready schema migrations.
- Event ingestion is public and trusts caller-supplied organization identity. Add machine credentials, connector identity, validation, rate-limit hooks, and audit records.

### Environment boundaries confirmed

- Docker is installed.
- OpenCV, FastAPI, SQLAlchemy, and Alembic are installed locally.
- FFmpeg, Ultralytics, OCR packages, GeoAlchemy2, and HLS.js are not installed locally.
- No real camera, government system, VAHAN, SARTHI, eGujCop, AFIS, or NAFIS access exists in the repository.
- The current Git root is `C:\site`; `CC` is an untracked project directory. Parent history and files are out of scope.

## 3. Target architecture

```text
VMS A / VMS B simulators or departmental adapters
        -> connector interface and canonical normalization
RTSP test sources -> MediaMTX -> HLS/WebRTC browser URLs
        -> edge frame processor (OpenCV, optional YOLO/OCR adapters)
        -> authenticated event/detection ingestion
        -> FastAPI federation and metadata services
        -> PostgreSQL/PostGIS + Redis/WebSocket boundary
        -> SURAKSH control-room registry, GIS, viewer, search, watchlists
```

## 4. Exact implementation stages

### Stage 1: Domain and data foundation

Add Department, VMSSystem, Connector, CameraHealth, DetectionEvent, Watchlist, WatchlistEntry, Alert, and investigation-ready relationships. Preserve existing users/events where migration is safe. Add demo departments and Gujarat-oriented sample registry records with `is_demo` markers.

### Stage 2: Alembic and PostGIS readiness

Add Alembic configuration and an initial migration. Enable PostGIS in the database service and use a nullable geography point when GeoAlchemy2 is installed. Keep SQLite-compatible test paths where necessary, while production Compose uses PostgreSQL.

### Stage 3: Registry and GIS APIs

Implement camera CRUD/deactivation, bounded filters/search, CSV import with per-row errors, template download, camera health, summary/gap-analysis endpoints, and department isolation. Never return connector credentials.

### Stage 4: Federation

Create VMS A and VMS B simulators with intentionally different payload shapes. Implement `VMSConnector`, capability reporting, adapters, sync/status APIs, and canonical event normalization.

### Stage 5: Streaming and health

Add MediaMTX plus two independent local demo RTSP publishers in Compose. Expose HLS URLs and explicit connection test/health results. Add frontend viewer support for HLS where the browser/player dependency exists; unavailable streams must remain visibly unavailable.

### Stage 6: Real edge analytics boundary

Replace synthetic edge event generation with decoded-frame processing. Add vehicle detection and OCR adapter interfaces, Indian plate normalization, null/uncertain OCR handling, inference throttling, authenticated upload, and focused tests. The pipeline must fail honestly when model/OCR dependencies are absent.

### Stage 7: Detection, investigation, and watchlists

Persist canonical vehicle detections, implement search and observed camera path reconstruction, add watchlists and alert creation, and add a WebSocket-compatible notification boundary with polling fallback.

### Stage 8: Control-room frontend

Replace school marketing/pilot surfaces with login, registry, Gujarat GIS, viewer, investigations, watchlists, integrations, health, audit, and settings. Use real API states, clearly labeled synthetic demo records, and no backend-failure fallback to fake operational data.

### Stage 9: Security and operations

Move secrets to environment variables, add `.env.example`, machine credential hashing/revocation, audit sensitive actions, tighten CORS and limits, validate CSV size/rows, enforce role and department access server-side, and document government-integration boundaries.

### Stage 10: Verification and handoff

Run frontend typecheck/lint/build, backend tests, edge tests, migration upgrade, Compose config validation, and demo services where dependencies permit. Record exact commands and blockers in the final report. Never claim real camera, YOLO, OCR, or VMS success without execution evidence.

## 5. Verification plan

- Backend: auth, RBAC, department isolation, CRUD/filter/import, connector adapters, normalized events, plate parsing, watchlists, alerts, health, gap analysis, and audit.
- Edge: decoded-frame interface, detector/OCR dependency behavior, normalization, null OCR, authenticated payload formatting, and buffering.
- Frontend: typecheck, lint, build, explicit API/stream error states, route smoke checks, and accessible keyboard operation.
- Integration: PostGIS migration, two VMS simulators, two stream paths, HLS output, detection persistence, search, route map, and watchlist alert.

## 6. Known risks

- CPU-only environments may not support acceptable YOLO/OCR throughput.
- Browser HLS/WebRTC support varies and needs a bundled player or gateway validation.
- PostGIS availability must be tested in the actual Compose database, not inferred from SQLAlchemy imports.
- Government integrations require official authorization and are intentionally represented only by abstractions and clearly marked simulators.
- The current large frontend component should be split incrementally after the core vertical path is stable.

## 7. Current implementation status

Completed in this checkout:

- SURAKSH control-room branding and school/pilot UI removal from routed pages.
- Department, VMS, camera registry, health, detection, watchlist, alert, and audit API foundations.
- Camera filtering/search, CRUD/deactivation, bounded CSV import, and template endpoint.
- PostGIS-ready model type, Alembic baseline, Compose PostGIS service, and migration startup command.
- VMS A/VMS B schema-specific simulators, adapter interface, normalization, and sync endpoint.
- MediaMTX and two generated RTSP publisher definitions in Compose.
- OpenCV frame decoding, optional Ultralytics vehicle inference, optional PaddleOCR attempt, plate null/uncertain handling, authenticated edge ingestion, and health reporting.
- Leaflet Gujarat map, HLS.js viewer wiring, persisted detection search, synthetic-data labels, API error states, and no silent hardcoded frontend fallback.
- Documentation, demo start/reset scripts, 19 backend tests, edge compilation, frontend typecheck/lint/build, migration validation, and Compose config validation.

Blocked or intentionally incomplete:

- Docker service smoke tests could not run because Docker Desktop's Linux engine is unavailable in the current environment.
- Real RTSP/HLS frames, YOLO inference, and OCR were not executed here. FFmpeg is not installed locally, no approved model weights are present, and OCR packages are not installed locally. The code reports these states instead of fabricating results.
- WebSocket alert fan-out, full audit table UI, camera import UI action, route polyline rendering, and production connector credential lifecycle remain follow-up work.
