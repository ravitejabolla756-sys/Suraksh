from app.services.connectors import VMSAConnector, VMSBConnector


def test_vms_a_normalizes_its_schema():
    connector = VMSAConnector({"cameras": [{"camera": "CAM_A_01", "stream": "rtsp://demo"}], "events": []})
    event = connector.normalize_event({"camera": "CAM_A_01", "type": "vehicle", "seen_at": "2026-01-01T00:00:00Z", "plate": "GJ01AB1234", "confidence": 0.94})
    assert event["camera_id"] == "CAM_A_01"
    assert event["event_type"] == "vehicle_detected"
    assert event["metadata"]["plate"] == "GJ01AB1234"


def test_vms_b_normalizes_its_different_schema():
    connector = VMSBConnector({"devices": [{"deviceId": "B-100", "hlsUrl": "http://demo"}], "records": []})
    event = connector.normalize_event({"deviceId": "B-100", "eventCode": "VEHICLE_DETECTED", "timestamp": "2026-01-01T00:00:00Z", "metadata": {"registrationNumber": "GJ 05 XY 7788", "confidence": 0.91}})
    assert event["camera_id"] == "B-100"
    assert event["event_type"] == "vehicle_detected"
    assert event["metadata"]["plate"] == "GJ 05 XY 7788"
