# VMS Connector Specification

`backend/app/services/connectors.py` defines the adapter interface:

- `list_cameras()`
- `get_camera(camera_id)`
- `get_stream(camera_id)`
- `get_health(camera_id)`
- `get_events()`
- `normalize_event(payload)`

`VMSAConnector` consumes `camera`, `type`, `seen_at`, and `plate`. `VMSBConnector` consumes `deviceId`, `eventCode`, `timestamp`, and `metadata.registrationNumber`. Both emit a canonical camera ID, source system, event type, timestamp, confidence, and metadata object.

The included simulator endpoints are synthetic integration systems. They are not government VMS connections.
