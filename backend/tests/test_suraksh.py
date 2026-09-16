from datetime import datetime, timezone

from app.services.plates import normalize_plate
from test_mvp import auth_headers, client, machine_headers


def test_plate_normalization_rejects_unreadable_text():
    assert normalize_plate("GJ 01-AB-1234") == "GJ01AB1234"
    assert normalize_plate("not a registration") is None


def test_registry_filters_and_gap_analysis_are_scoped():
    headers = auth_headers()
    departments = client.get("/departments", headers=headers)
    assert departments.status_code == 200
    assert len(departments.json()) >= 3

    cameras = client.get("/cameras?district=Ahmedabad", headers=headers)
    assert cameras.status_code == 200
    assert all(camera["district"] == "Ahmedabad" for camera in cameras.json())

    gap = client.get("/registry/summary", headers=headers)
    assert gap.status_code == 200
    assert "SYNTHETIC HACKATHON DEMO DATA" in gap.json()["synthetic_data_notice"]


def test_detection_ingest_normalizes_plate_and_creates_watchlist_alert():
    payload = {
        "camera_id": "cam_gate_1",
        "department_id": "dept_transport_demo",
        "source_system": "VMS_B",
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "vehicle_class": "car",
        "vehicle_confidence": 0.91,
        "plate_text": "GJ 01 AB 1234",
        "plate_confidence": 0.88,
        "metadata": {"source_notice": "DEMO"},
        "is_demo": True,
    }
    # CAM_A_01 is owned by Home DEMO, so first verify cross-department writes fail.
    rejected = client.post("/detections/ingest", json=payload, headers=machine_headers())
    assert rejected.status_code == 404

    payload["camera_id"] = "cam_hallway"
    created = client.post("/detections/ingest", json=payload, headers=machine_headers())
    assert created.status_code == 200
    assert created.json()["plate_text"] == "GJ01AB1234"

    alerts = client.get("/alerts", headers=auth_headers())
    assert alerts.status_code == 200
    assert any(alert["detection_id"] == created.json()["id"] for alert in alerts.json())


def test_vms_federation_exposes_both_demo_systems():
    response = client.get("/integrations/vms", headers=auth_headers())
    assert response.status_code == 200
    assert {item["vendor"] for item in response.json()} >= {"Federated Vendor A", "Federated Vendor B"}


def test_camera_csv_template_and_import():
    headers = auth_headers()
    template = client.get("/cameras/import/template", headers=headers)
    assert template.status_code == 200
    csv_data = "name,external_id,department_id,district,zone,latitude,longitude,camera_type,vendor,model,vms_system_id,protocol,stream_endpoint,storage_type,retention_days,is_demo\nCSV Camera,CAM_CSV_01,dept_municipal_demo,Rajkot,Station,22.3,70.8,fixed,CSV Vendor,CSV-1,,RTSP,rtsp://demo,VMS,30,true\n"
    imported = client.post("/cameras/import", files={"file": ("cameras.csv", csv_data, "text/csv")}, headers=headers)
    assert imported.status_code == 200
    assert imported.json()["created_count"] == 1
