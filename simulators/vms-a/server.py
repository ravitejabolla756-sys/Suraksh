import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer


DATA = {
    "system": "VMS_A",
    "cameras": [{"camera": "CAM_A_01", "name": "Relief Road North - DEMO", "stream": "http://localhost:8888/vms-a/index.m3u8", "status": "ONLINE", "last_heartbeat": datetime.now(timezone.utc).isoformat()}],
    "events": [{"camera": "CAM_A_01", "type": "vehicle", "seen_at": datetime.now(timezone.utc).isoformat(), "plate": "GJ01AB1234", "confidence": 0.94}],
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = DATA if self.path != "/health" else {"status": "CONNECTED", "source": "VMS_A", "demo": True}
        encoded = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_):
        return


HTTPServer(("0.0.0.0", 8091), Handler).serve_forever()
