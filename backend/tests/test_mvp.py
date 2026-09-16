import os

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def auth_headers():
    response = client.post(
        "/auth/login",
        json={"email": "admin@suraksh.demo", "password": "Suraksh123!"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def machine_headers():
    return {"X-Edge-Key": os.environ["SURAKSH_EDGE_INGEST_KEY"]}


def test_login_and_dashboard_data():
    headers = auth_headers()
    cameras = client.get("/cameras", headers=headers)
    assert cameras.status_code == 200
    assert len(cameras.json()) >= 3

    summary = client.get("/analytics/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["cameras_total"] >= 3


def test_admin_can_create_camera_and_it_appears_in_list():
    headers = auth_headers()
    created = client.post(
        "/cameras",
        json={
            "name": "Parking Gate",
            "department_id": "dept_home_demo",
            "district": "Ahmedabad",
            "zone": "Parking Area",
            "stream_endpoint": "rtsp://192.168.1.120/stream1",
            "vendor": "Demo Vendor",
            "external_id": "CAM_TEST_01",
        },
        headers=headers,
    )
    assert created.status_code == 201
    camera = created.json()
    assert camera["name"] == "Parking Gate"
    assert camera["source_url"] == "rtsp://192.168.1.120/stream1"

    listed = client.get("/cameras", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == camera["id"] for item in listed.json())


def test_event_ingest_creates_alert_and_dismisses():
    headers = auth_headers()
    payload = {
        "org_id": "org_demo_school",
        "camera_id": "cam_gate_1",
        "edge_server_id": "edge_demo_01",
        "zone_id": "zone_gate_entry",
        "type": "intrusion",
        "confidence": 0.88,
        "snapshot_url": "/demo/snapshots/intrusion.svg",
        "metadata": {"person_count": 1, "boundary_crossed": True},
    }
    ingest = client.post("/events/ingest", json=payload, headers=machine_headers())
    assert ingest.status_code == 200
    event = ingest.json()
    assert event["alert_sent"] is True

    dismiss = client.post(f"/events/{event['id']}/dismiss", json={"reason": "handled"}, headers=headers)
    assert dismiss.status_code == 200
    assert dismiss.json()["dismiss_reason"] == "handled"

    notifications = client.get("/notifications", headers=headers)
    assert notifications.status_code == 200
    matching = [log for log in notifications.json() if log["event_id"] == event["id"]]
    assert matching
    assert {log["channel"] for log in matching} >= {"whatsapp", "email"}
    assert all(log["status"] == "sent" for log in matching)


def test_notification_logs_require_auth():
    response = client.get("/notifications")
    assert response.status_code in {401, 403}


def test_event_ingestion_requires_machine_auth():
    response = client.post("/events/ingest", json={"org_id": "org_demo_school", "camera_id": "cam_gate_1", "type": "intrusion", "confidence": 0.8})
    assert response.status_code in {401, 403}


def test_admin_can_create_and_test_alert_rule():
    headers = auth_headers()
    created = client.post(
        "/alert-rules",
        json={
            "name": "High confidence crowd",
            "event_type": "crowd",
            "confidence_threshold": 0.7,
            "camera_id": "cam_hallway",
            "zone_id": None,
            "condition_type": "crowd_threshold",
            "condition_value": 35,
            "enabled": True,
            "notify_channels": ["whatsapp", "email"],
            "notify_user_ids": ["usr_principal", "usr_security"],
            "suppress_duration_sec": 120,
        },
        headers=headers,
    )
    assert created.status_code == 200
    rule = created.json()
    assert rule["name"] == "High confidence crowd"
    assert rule["event_type"] == "crowd"

    test_response = client.post(f"/alert-rules/{rule['id']}/test", headers=headers)
    assert test_response.status_code == 200
    assert test_response.json()["channels"] == ["whatsapp", "email"]
    assert "CROWD" in test_response.json()["message"]


def test_admin_can_list_and_invite_staff_user():
    headers = auth_headers()
    users = client.get("/users", headers=headers)
    assert users.status_code == 200
    assert any(user["email"] == "admin@suraksh.demo" for user in users.json())

    invite = client.post(
        "/users",
        json={
            "email": "new.operator@suraksh.demo",
            "first_name": "New",
            "last_name": "Operator",
            "phone": "+91 90000 00004",
            "role": "operator",
            "temporary_password": "Suraksh123!",
        },
        headers=headers,
    )
    assert invite.status_code == 201
    invited = invite.json()
    assert invited["email"] == "new.operator@suraksh.demo"
    assert invited["role"] == "operator"

    login = client.post(
        "/auth/login",
        json={"email": "new.operator@suraksh.demo", "password": "Suraksh123!"},
    )
    assert login.status_code == 200

    duplicate = client.post(
        "/users",
        json={
            "email": "new.operator@suraksh.demo",
            "first_name": "New",
            "last_name": "Operator",
            "role": "viewer",
            "temporary_password": "Suraksh123!",
        },
        headers=headers,
    )
    assert duplicate.status_code == 409


def test_staff_invite_requires_admin_auth():
    response = client.post(
        "/users",
        json={
            "email": "unauth@visionguard.test",
            "first_name": "No",
            "role": "viewer",
            "temporary_password": "Suraksh123!",
        },
    )
    assert response.status_code in {401, 403}


def test_public_signup_creates_pilot_lead():
    response = client.post(
        "/leads",
        json={
            "school_name": "Future Valley School",
            "email": "principal@futurevalley.edu",
            "phone": "+91 98765 43210",
            "city": "Hyderabad",
            "camera_count": "8",
            "source": "website_signup",
        },
    )
    assert response.status_code == 201
    lead = response.json()
    assert lead["school_name"] == "Future Valley School"
    assert lead["email"] == "principal@futurevalley.edu"
    assert lead["status"] == "new"
    assert lead["notes"] == ""


def test_public_signup_rejects_invalid_email():
    response = client.post(
        "/leads",
        json={
            "school_name": "Future Valley School",
            "email": "not-an-email",
            "phone": "+91 98765 43210",
            "city": "Hyderabad",
            "camera_count": "8",
        },
    )
    assert response.status_code == 422


def test_admin_can_list_and_update_pilot_leads():
    headers = auth_headers()
    created = client.post(
        "/leads",
        json={
            "school_name": "Pipeline School",
            "email": "pipeline@school.edu",
            "phone": "+91 98765 43211",
            "city": "Mumbai",
            "camera_count": "16",
            "source": "website_signup",
        },
    )
    assert created.status_code == 201
    lead_id = created.json()["id"]

    listed = client.get("/leads", headers=headers)
    assert listed.status_code == 200
    assert any(lead["id"] == lead_id for lead in listed.json())

    updated = client.patch(
        f"/leads/{lead_id}",
        json={"status": "pilot_scheduled", "notes": "Demo booked for Friday."},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "pilot_scheduled"
    assert updated.json()["notes"] == "Demo booked for Friday."


def test_lead_pipeline_requires_admin_auth():
    response = client.get("/leads")
    assert response.status_code in {401, 403}
