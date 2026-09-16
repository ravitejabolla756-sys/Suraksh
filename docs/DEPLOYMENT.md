# SURAKSH Deployment

## Local demo

1. Copy `.env.example` to `.env`, generate a random `SURAKSH_EDGE_INGEST_KEY`, and set `VISIONGUARD_EDGE_INGEST_KEY_HASH` to its SHA-256 digest.
2. Run `docker compose up --build` from the project root.
3. Alembic upgrades the backend schema before Uvicorn starts.
4. Open `http://localhost:3000`. The seeded local login is available only with demo seed enabled.

Compose includes PostGIS PostgreSQL, Redis, FastAPI, Next.js, MediaMTX, two FFmpeg RTSP publishers, and two VMS simulators. MediaMTX exposes RTSP on `8554`, HLS on `8888`, and WebRTC HTTP on `8889`.

The edge image includes OpenCV and Ultralytics. Model weights are intentionally not committed; set `SURAKSH_YOLO_MODEL` to an approved local weight path mounted into the edge container. PaddleOCR remains an optional local dependency from `edge-ai/requirements-ai.txt` and is never replaced with fabricated plate text.

## Production boundary

Use managed PostGIS, Redis, a secret manager, TLS termination, per-machine credentials, object storage for approved evidence, structured logs, and a production-grade browser stream gateway. Do not use the local Compose passwords or synthetic VMS services in production.
