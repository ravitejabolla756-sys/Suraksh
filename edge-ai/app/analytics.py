"""Time-bucketed analytics aggregation for edge tracking sessions."""
from collections import Counter
from datetime import datetime, timedelta, timezone


def minute_bucket(timestamp: datetime) -> tuple[datetime, datetime]:
    timestamp = timestamp.astimezone(timezone.utc)
    start = timestamp.replace(second=0, microsecond=0)
    return start, start + timedelta(minutes=1)


class AnalyticsSession:
    """Keep frame metrics in memory and emit one record per minute bucket."""

    def __init__(self, camera_id: str, department_id: str, source_vms: str):
        self.camera_id = camera_id
        self.department_id = department_id
        self.source_vms = source_vms
        self.buckets: dict[datetime, dict] = {}

    def ingest(self, snapshot: dict, timestamp: datetime | None = None) -> dict:
        now = timestamp or datetime.now(timezone.utc)
        start, end = minute_bucket(now)
        bucket = self.buckets.setdefault(start, self._empty(start, end))
        visible = snapshot["visible"]
        unique = snapshot["unique_window"]
        bucket["people_visible_peak"] = max(bucket["people_visible_peak"], visible["people"])
        bucket["vehicle_visible_peak"] = max(bucket["vehicle_visible_peak"], visible["vehicles"])
        for field in ("people", "vehicles", "cars", "motorcycles", "buses", "trucks"):
            bucket[f"unique_{field}"] = max(bucket[f"unique_{field}"], unique[field])
        for crossing in snapshot.get("crossings", []):
            field = f"{crossing['class']}_crossed_{'a_to_b' if crossing['direction'] == 'A_TO_B' else 'b_to_a'}"
            bucket[field] += 1
        return bucket

    def _empty(self, start, end):
        data = {"camera_id": self.camera_id, "department_id": self.department_id,
                "source_vms": self.source_vms, "bucket_start": start.isoformat(),
                "bucket_end": end.isoformat(), "people_visible_peak": 0,
                "vehicle_visible_peak": 0}
        for field in ("people", "vehicles", "cars", "motorcycles", "buses", "trucks"):
            data[f"unique_{field}"] = 0
        for vehicle in ("cars", "motorcycles", "buses", "trucks"):
            data[f"{vehicle}_crossed_a_to_b"] = 0
            data[f"{vehicle}_crossed_b_to_a"] = 0
        return data
