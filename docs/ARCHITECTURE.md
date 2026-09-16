# SURAKSH Architecture

SURAKSH is a federation and metadata layer above departmental CCTV/VMS systems. Department VMS A and VMS B remain operational and own their streams. SURAKSH stores a central registry, connector health, normalized detection metadata, watchlists, alerts, and audit records.

```text
VMS A / VMS B -> VMSConnector adapters -> canonical events
RTSP demo sources -> MediaMTX -> HLS browser output
RTSP/source -> OpenCV -> optional local YOLO/OCR -> authenticated ingestion
                              -> FastAPI -> PostgreSQL/PostGIS + Redis boundary
                              -> control-room dashboard / GIS / investigations
```

PostGIS is enabled by the Compose database image. Redis is reserved for connector health, rate limiting, and the future WebSocket alert fan-out. SURAKSH does not attempt to centralize every statewide video stream.
