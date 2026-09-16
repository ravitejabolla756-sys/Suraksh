# SURAKSH API

The FastAPI OpenAPI document is available at `/docs` when the backend is running.

## Authentication

`POST /auth/login` returns a bearer token. Browser requests use `Authorization: Bearer <token>`. Machine requests use `X-Edge-Key`; the backend compares the SHA-256 digest configured in `VISIONGUARD_EDGE_INGEST_KEY`.

## Registry

- `GET /departments`
- `GET /cameras?district=&vendor=&vms=&health=&search=`
- `GET /cameras/{camera_id}`
- `POST /cameras`
- `PATCH /cameras/{camera_id}`
- `DELETE /cameras/{camera_id}` (deactivates)
- `GET /cameras/import/template`
- `POST /cameras/import` with bounded CSV upload
- `GET /registry/summary`
- `GET /registry/health`
- `POST /registry/health/{camera_id}` with machine authentication for edge observations

## Federation and metadata

- `GET /integrations/vms`
- `GET /detections?plate=&camera=&department=&vehicle_type=&since=&until=`
- `POST /detections/ingest` with machine authentication
- `GET /watchlists`, `POST /watchlists`
- `POST /watchlists/{watchlist_id}/entries`
- `GET /alerts`
- `GET /audit` for administrators

## Safety incident integration

- `POST /safety/incidents/ingest` with the existing `X-Edge-Key` machine boundary. The payload must contain a supported safety event type, camera, timestamp, confidence, model versions, contributing signals, evidence references, and temporal window. The response is `202` with `created`, `grouped`, or `failed` status. Grouped observations update the existing incident and do not re-run notifications.

The ingestion response normalizes Indian registration formats. Failed OCR is represented as `plate_text: null`; the API never invents a plate value.
