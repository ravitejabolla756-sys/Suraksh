import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer


DATA = {
    "system": "VMS_B",
    "devices": [{"deviceId": "B-100", "label": "Ring Road East - DEMO", "hlsUrl": "http://localhost:8888/vms-b/index.m3u8", "health": "ONLINE", "lastSeen": datetime.now(timezone.utc).isoformat()}],
    "records": [{"deviceId": "B-100", "eventCode": "VEHICLE_DETECTED", "timestamp": datetime.now(timezone.utc).isoformat(), "metadata": {"registrationNumber": "GJ 05 XY 7788", "confidence": 0.91}}],
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = DATA if self.path != "/health" else {"status": "CONNECTED", "source": "VMS_B", "demo": True}
        encoded = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_):
        return


HTTPServer(("0.0.0.0", 8092), Handler).serve_forever()
