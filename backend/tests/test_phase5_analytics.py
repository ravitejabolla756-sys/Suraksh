import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

EDGE = Path(__file__).resolve().parents[2] / "edge-ai" / "app"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


AnalyticsSession = load_module("suraksh_edge_analytics", EDGE / "analytics.py").AnalyticsSession
AnonymousTracker = load_module("suraksh_edge_tracking", EDGE / "tracking.py").AnonymousTracker
from test_mvp import auth_headers, client, machine_headers  # noqa: E402


def test_track_ids_are_deduplicated_and_classes_grouped():
    tracker = AnonymousTracker("cam")
    first = tracker.update([{"track_id": 7, "object_class": "car", "centroid": (10, 10), "confidence": 0.9}, {"track_id": 9, "object_class": "person", "centroid": (20, 10), "confidence": 0.8}])
    second = tracker.update([{"track_id": 7, "object_class": "car", "centroid": (12, 11), "confidence": 0.9}])
    assert first["visible"]["vehicles"] == 1
    assert second["visible"]["vehicles"] == 1
    assert second["unique_window"] == {"people": 1, "vehicles": 1, "cars": 1, "motorcycles": 0, "buses": 0, "trucks": 0}


def test_total_vehicles_is_type_sum_and_crossing_is_debounced():
    tracker = AnonymousTracker("cam", ((0, 50), (100, 50)))
    tracker.update([{"track_id": 1, "object_class": "car", "centroid": (10, 40), "confidence": 0.9}])
    tracker.update([{"track_id": 1, "object_class": "car", "centroid": (10, 60), "confidence": 0.9}])
    tracker.update([{"track_id": 1, "object_class": "car", "centroid": (10, 40), "confidence": 0.9}])
    tracker.update([{"track_id": 1, "object_class": "car", "centroid": (10, 60), "confidence": 0.9}])
    assert len(tracker.crossings) == 2
    assert {item["direction"] for item in tracker.crossings} == {"A_TO_B", "B_TO_A"}


def test_minute_bucket_upsert_prevents_frame_row_explosion():
    session = AnalyticsSession("cam", "dept_home_demo", "VMS-A")
    timestamp = datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc)
    snapshot = {"visible": {"people": 2, "vehicles": 3, "cars": 3, "motorcycles": 0, "buses": 0, "trucks": 0}, "unique_window": {"people": 2, "vehicles": 3, "cars": 3, "motorcycles": 0, "buses": 0, "trucks": 0}, "crossings": []}
    session.ingest(snapshot, timestamp)
    session.ingest(snapshot, timestamp + timedelta(seconds=10))
    assert len(session.buckets) == 1
    assert session.buckets[next(iter(session.buckets))]["vehicle_visible_peak"] == 3


def test_analytics_api_requires_machine_auth_and_upserts_one_bucket():
    payload = {"camera_id": "cam_gate_1", "department_id": "dept_home_demo", "source_vms": "VMS-A", "bucket_start": "2026-09-10T15:00:00Z", "bucket_end": "2026-09-10T15:01:00Z", "people_visible_peak": 2, "vehicle_visible_peak": 4, "unique_people": 2, "unique_vehicles": 4, "unique_cars": 4}
    assert client.post("/analytics/ingest", json=payload).status_code in {401, 403}
    first = client.post("/analytics/ingest", json=payload, headers=machine_headers())
    second = client.post("/analytics/ingest", json={**payload, "vehicle_visible_peak": 6}, headers=machine_headers())
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    rows = client.get("/analytics/timeseries", headers=auth_headers()).json()["buckets"]
    assert len([row for row in rows if row["camera_id"] == "cam_gate_1" and row["bucket_start"].startswith("2026-09-10T15:00")]) == 1
