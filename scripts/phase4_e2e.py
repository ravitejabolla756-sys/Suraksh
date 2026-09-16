"""API-only persistence proof using fresh YOLO/Tesseract observations, not fixtures."""
import argparse
import json
from pathlib import Path
import threading
import uuid

import httpx

from anpr_runtime import ROOT, RuntimeANPR
from local_runtime import environment


class AlertListener:
    def __init__(self, base: str, headers: dict):
        self.base, self.headers = base, headers
        self.ready, self.done = threading.Event(), threading.Event()
        self.events, self.error = [], None

    def listen(self):
        try:
            with httpx.Client(timeout=90) as client:
                with client.stream("GET", self.base + "/alerts/stream", headers=self.headers) as response:
                    response.raise_for_status()
                    event = ""
                    for line in response.iter_lines():
                        if line.startswith("event:"):
                            event = line[6:].strip()
                        elif line.startswith("data:"):
                            if event == "ready":
                                self.ready.set()
                            elif event == "alert":
                                self.events.append(json.loads(line[5:]))
                                return
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.done.set()


def run(base: str, trigger_only: bool = False):
    run_id = str(uuid.uuid4())
    output = ROOT / ".runtime" / "phase4" / run_id
    output.mkdir(parents=True)
    report = {"run_id": run_id, "checks": [], "observations": [], "success": False}
    client = httpx.Client(base_url=base, timeout=30)
    tracking_a = json.loads((ROOT / ".runtime" / "anpr" / "target-tracking-vms-a.json").read_text())
    tracking_b = json.loads((ROOT / ".runtime" / "anpr" / "target-tracking-vms-b.json").read_text())
    a_probe = next(r["frame"] for r in tracking_a["rendered_frames"] if r["frame"] >= 381)
    b_probe = next(r["frame"] for r in tracking_b["rendered_frames"] if r["frame"] >= 71)
    trigger_frame = next(r["frame"] for r in tracking_a["rendered_frames"] if r["frame"] > a_probe)

    def save():
        (output / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    def check(label, passed):
        report["checks"].append({"label": label, "pass": bool(passed)})
        print(f"{'PASS' if passed else 'FAIL'}: {label}", flush=True)
        save()
        if not passed:
            raise AssertionError(label)

    def request(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    try:
        env = environment()
        machine = {"X-Edge-Key": env["SURAKSH_EDGE_INGEST_KEY"]}
        check("Backend reachable", request("GET", "/health")["status"] == "ok")
        token = request("POST", "/auth/login", json={"email": "admin@suraksh.demo", "password": "Suraksh123!"})["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        departments = request("GET", "/departments", headers=auth)
        systems = request("GET", "/integrations/vms", headers=auth)
        cameras = request("GET", "/cameras", headers=auth)
        selected = {}
        for source, dept_name, coordinates in (("A", "Home", (23.0225, 72.5714)), ("B", "Transport", (23.0345, 72.5860))):
            department = next(d for d in departments if dept_name in d["name"])
            vms = next(v for v in systems if v["department_id"] == department["id"])
            external = "AHM-DEMO-01" if source == "A" else "AHM-DEMO-02"
            camera = next((c for c in cameras if c["external_id"] == external), None)
            if camera is None:
                camera = request("POST", "/cameras", headers=auth, json={
                    "name": f"{external} — DEMO / SYNTHETIC", "external_id": external,
                    "department_id": department["id"], "vms_system_id": vms["id"],
                    "district": "Ahmedabad", "zone": f"Synthetic test location {source}",
                    "latitude": coordinates[0], "longitude": coordinates[1], "protocol": "MP4",
                    "stream_endpoint": f"{base}/demo-media/anpr-vms-{source.lower()}.mp4",
                    "vendor": vms["vendor"], "model": "Recorded CCTV demo", "is_demo": True})
            selected[source] = camera
            check(f"VMS-{source} camera exists and is marked DEMO", camera["is_demo"])
        check("Different cameras, VMS and coordinates", selected["A"]["id"] != selected["B"]["id"] and selected["A"]["vms_system_id"] != selected["B"]["vms_system_id"] and selected["A"]["latitude"] != selected["B"]["latitude"])
        runtime = RuntimeANPR()
        check("Local YOLO11n and Tesseract load", bool(runtime.model and runtime.version))

        def ingest(source: str, frame: int, tag: str):
            evidence = output / tag
            observation = runtime.observe(source, frame, evidence)
            check(f"{tag}: real video decoded / YOLO / OCR executed", observation["frames_decoded"] > 0 and observation["vehicle_detections"] > 0 and observation["ocr_attempts"] > 0)
            # Test oracle only: never feeds the extractor, payload or normalization.
            check(f"{tag}: genuine ANPR", observation["normalized_text"] == "GJ01AB1234")
            camera = selected[source]
            payload = {"request_id": str(uuid.uuid5(uuid.UUID(run_id), tag)),
                       "camera_id": camera["id"], "department_id": camera["department_id"],
                       "source_system": observation["source_system"], "detected_at": observation["detected_at"],
                       "vehicle_class": observation["vehicle_class"], "vehicle_confidence": observation["vehicle_confidence"],
                       "plate_text": observation["normalized_text"], "plate_confidence": observation["confidence"],
                       "evidence_url": str(evidence / "source-frame.png"),
                       "metadata": {**observation, "raw_ocr": observation["raw_text"], "run_id": run_id}, "is_demo": True}
            detection = request("POST", "/detections/ingest", headers=machine, json=payload)
            check(f"{tag}: authenticated ingestion", bool(detection["id"]))
            stored = request("GET", f"/detections/{detection['id']}", headers=auth)
            check(f"{tag}: exact ID persisted", stored["plate_text"] == observation["normalized_text"] and stored["metadata"]["raw_ocr"] == observation["raw_text"])
            replay = request("POST", "/detections/ingest", headers=machine, json=payload)
            check(f"{tag}: retry deduplicated", replay["id"] == detection["id"])
            request("POST", f"/registry/health/{camera['id']}", headers=machine, json={
                "health_status": "ONLINE", "stream_status": "RECORDED FILE READABLE", "stream_reachable": True,
                "failure_count": 0, "measured_fps": observation["fps"], "codec": "mp4v"})
            report["observations"].append({"tag": tag, **detection})
            save()
            return detection

        if trigger_only:
            probe = runtime.observe("A", a_probe, output / "watchlist-plate-probe")
            plate = probe["normalized_text"]
        else:
            a, b = ingest("A", a_probe, "vms-a"), ingest("B", b_probe, "vms-b")
            plate = a["plate_text"]
            check("Both cameras independently OCR the same plate", plate == b["plate_text"])
            search = request("GET", "/detections", headers=auth, params={"plate": plate})
            ids = {row["id"] for row in search}
            check("Cross-camera search contains both detections", {a["id"], b["id"]} <= ids)
            check("Search is chronological", [r["detected_at"] for r in search] == sorted(r["detected_at"] for r in search))
            path = request("GET", "/investigations/path", headers=auth, params={"plate": plate})
            check("Observed path has both camera coordinates", {a["id"], b["id"]} <= {p["id"] for p in path["points"]})
            report.update(search=search, path=path)
        lists = request("GET", "/watchlists", headers=auth)
        watchlist = next((w for w in lists if w["name"] == "Hackathon Demo Watchlist" and w["department_id"] == selected["A"]["department_id"]), None)
        if watchlist is None:
            watchlist = request("POST", "/watchlists", headers=auth, json={"department_id": selected["A"]["department_id"], "name": "Hackathon Demo Watchlist", "description": "DEMO / SYNTHETIC INPUT"})
        entry = next((e for e in watchlist["entries"] if e["plate_text"] == plate and e["active"]), None)
        if entry is None:
            entry = request("POST", f"/watchlists/{watchlist['id']}/entries", headers=auth, json={"plate_text": plate, "priority": "HIGH", "reason": "Synthetic hackathon vehicle-of-interest demonstration"})
        report.update(watchlist_id=watchlist["id"], entry_id=entry["id"])
        check("Watchlist and entry persisted through API", bool(entry["id"]))
        listener = AlertListener(base, auth)
        threading.Thread(target=listener.listen, daemon=True).start()
        check("Authenticated SSE connected before trigger", listener.ready.wait(10))
        trigger = ingest("A", trigger_frame, "trigger")
        check("SSE delivered new persisted alert", listener.done.wait(25) and not listener.error and any(e["detection_id"] == trigger["id"] and e["watchlist_entry_id"] == entry["id"] for e in listener.events))
        alerts = request("GET", "/alerts", headers=auth)
        alert = next(a for a in alerts if a["detection_id"] == trigger["id"] and a["watchlist_entry_id"] == entry["id"])
        check("Alert persisted and retrievable", alert["id"] in {e["id"] for e in listener.events})
        audit = request("GET", "/audit", headers=auth)
        check("Real action audit records exist", {"camera.onboard", "watchlist.create", "detection.ingest", "alert.generate"} <= {a["action"] for a in audit})
        report.update(trigger_frame=trigger_frame, trigger_detection_id=trigger["id"], alert_id=alert["id"], realtime_events=listener.events, success=True)
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        save()
        client.close()
        print(f"Evidence: {output / 'result.json'}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--trigger-only", action="store_true")
    args = parser.parse_args()
    run(args.backend.rstrip("/"), args.trigger_only)
