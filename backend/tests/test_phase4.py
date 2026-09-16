"""Isolated API contract tests. Fixtures here are not runtime demo evidence."""
from datetime import datetime, timedelta, timezone
import uuid

from app.core.security import create_access_token
from app.models.database import SessionLocal
from app.models.entities import Department, Organization, Role, User
from app.services.alert_stream import read_after
from test_mvp import auth_headers, client, machine_headers


def observation(camera="cam_gate_1", department="dept_home_demo", plate="GJ99QA8765", time=None):
    return {"request_id": str(uuid.uuid4()), "camera_id": camera, "department_id": department,
            "source_system": "VMS-A", "detected_at": (time or datetime.now(timezone.utc)).isoformat(),
            "vehicle_class": "car", "vehicle_confidence": 0.81, "plate_text": plate,
            "plate_confidence": 0.72, "metadata": {"test_fixture": True}, "is_demo": True}


def ingest(payload):
    response = client.post("/detections/ingest", json=payload, headers=machine_headers())
    assert response.status_code == 200, response.text
    return response.json()


def test_machine_auth_required():
    for headers in ({}, {"X-Edge-Key": "invalid"}):
        assert client.post("/detections/ingest", json=observation(), headers=headers).status_code == 401


def test_exact_id_retrieval_and_retry_deduplication():
    payload = observation()
    first = ingest(payload)
    assert ingest(payload)["id"] == first["id"]
    saved = client.get(f"/detections/{first['id']}", headers=auth_headers()).json()
    assert saved["metadata"] == payload["metadata"]
    assert saved["request_id"] == payload["request_id"]
    for change in ({"plate_confidence": 0.1}, {"source_system": "different"}, {"vehicle_class": "bus"}):
        assert client.post("/detections/ingest", json={**payload, **change}, headers=machine_headers()).status_code == 409


def test_normalized_search_order_and_department_filter():
    now = datetime.now(timezone.utc)
    later = ingest(observation("cam_hallway", "dept_transport_demo", "GJ99QA7777", now))
    earlier = ingest(observation(plate="GJ 99 QA 7777", time=now - timedelta(seconds=30)))
    headers = auth_headers()
    rows = client.get("/detections?plate=gj-99-qa-7777", headers=headers).json()
    assert [r["id"] for r in rows] == [earlier["id"], later["id"]]
    filtered = client.get("/detections?plate=GJ99QA7777&department=dept_home_demo", headers=headers).json()
    assert [r["id"] for r in filtered] == [earlier["id"]]
    path = client.get("/investigations/path?plate=GJ99QA7777", headers=headers).json()
    assert path["label"] == "Observed Camera Detection Path"
    assert [p["id"] for p in path["points"]] == [earlier["id"], later["id"]]


def test_empty_and_invalid_search_and_missing_detection():
    headers = auth_headers()
    assert client.get("/detections?plate=GJ99ZZ9999", headers=headers).json() == []
    assert client.get("/detections?plate=unreadable", headers=headers).json() == []
    assert client.get("/investigations/path?plate=unreadable", headers=headers).status_code == 422
    assert client.get("/detections/nonexistent", headers=headers).status_code == 404


def test_registered_coordinates_cannot_be_spoofed():
    payload = observation()
    payload.update(latitude=0, longitude=0)
    result = ingest(payload)
    camera = client.get("/cameras/cam_gate_1", headers=auth_headers()).json()
    assert result["latitude"] == camera["latitude"]
    assert result["longitude"] == camera["longitude"]


def test_missing_coordinates_are_explicit():
    headers = auth_headers()
    response = client.post("/cameras", headers=headers, json={"name": "No coordinates test", "department_id": "dept_home_demo", "district": "Ahmedabad", "is_demo": True})
    assert response.status_code == 201
    detection = ingest(observation(camera=response.json()["id"], plate="GJ99QA6666"))
    path = client.get("/investigations/path?plate=GJ99QA6666", headers=headers).json()
    assert path["points"] == []
    assert path["missing_coordinates"] == [detection["id"]]


def test_watchlist_scope_alert_dedup_and_audit():
    headers = auth_headers()
    watchlist = client.post("/watchlists", headers=headers, json={"department_id": "dept_home_demo", "name": "API contract test", "description": "Test fixture"}).json()
    entry = client.post(f"/watchlists/{watchlist['id']}/entries", headers=headers, json={"plate_text": "GJ99QA5555", "priority": "HIGH"}).json()
    other = ingest(observation("cam_hallway", "dept_transport_demo", "GJ99QA5555"))
    payload = observation(plate="GJ99QA5555")
    detection = ingest(payload)
    ingest(payload)
    alerts = client.get("/alerts", headers=headers).json()
    assert not any(a["detection_id"] == other["id"] for a in alerts)
    matches = [a for a in alerts if a["detection_id"] == detection["id"]]
    assert len(matches) == 1 and matches[0]["watchlist_entry_id"] == entry["id"]
    assert matches[0]["plate_text"] == detection["plate_text"]
    audit = client.get("/audit", headers=headers).json()
    assert any(a["action"] == "detection.ingest" and a["resource_id"] == detection["id"] for a in audit)
    assert any(a["action"] == "alert.generate" and a["resource_id"] == matches[0]["id"] for a in audit)
    with SessionLocal() as db:
        rows = read_after(db, "org_demo_school", None)
        assert rows
        last = rows[-1]
        assert read_after(db, "org_demo_school", (last.created_at, last.id)) == []


def test_other_organization_cannot_read_departments_detections_or_alerts():
    suffix = uuid.uuid4().hex
    with SessionLocal() as db:
        org = Organization(name="Other tenant", email=f"org-{suffix}@example.test")
        db.add(org)
        db.flush()
        user = User(org_id=org.id, first_name="Other", email=f"user-{suffix}@example.test", password_hash="not-used", role=Role.admin)
        db.add(user)
        db.flush()
        token = create_access_token(user.id)
        db.commit()
    headers = {"Authorization": f"Bearer {token}"}
    detection = ingest(observation())
    for path in ("/departments", "/detections", "/alerts", "/watchlists", "/audit"):
        assert client.get(path, headers=headers).json() == []
    assert client.get(f"/detections/{detection['id']}", headers=headers).status_code == 404
    assert client.get("/investigations/path?plate=GJ99QA8765", headers=headers).json()["points"] == []
    assert client.get("/alerts/stream?after=missing", headers=headers).status_code == 404


def test_sse_auth_and_health_validation():
    assert client.get("/alerts/stream").status_code in (401, 403)
    assert client.post("/registry/health/cam_gate_1", headers=machine_headers(), json={"health_status": "garbage"}).status_code == 422
    assert client.post("/registry/health/cam_gate_1", headers=machine_headers(), json={"measured_fps": -2}).status_code == 422
    result = client.post("/registry/health/cam_gate_1", headers=machine_headers(), json={"health_status": "ONLINE", "measured_fps": 23.976})
    assert result.status_code == 200
    camera = client.get("/cameras/cam_gate_1", headers=auth_headers())
    assert camera.status_code == 200 and camera.json()["fps"] == 24
