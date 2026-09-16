import argparse
import os
import time

from app.client import CloudClient
from app.config import load_config
from app.detector import FrameDetector


def main() -> None:
    parser = argparse.ArgumentParser(description="SURAKSH Edge AI worker")
    parser.add_argument("--config", default="config/demo.yaml")
    parser.add_argument("--once", action="store_true", help="Generate one batch of demo events and exit")
    args = parser.parse_args()

    config = load_config(args.config)
    ingest_key = os.getenv("SURAKSH_EDGE_INGEST_KEY", config.ingest_key)
    if not ingest_key:
        raise RuntimeError("SURAKSH_EDGE_INGEST_KEY must be configured")
    client = CloudClient(config.backend_url, ingest_key)
    detector = FrameDetector(config)

    print(f"SURAKSH edge worker connected to {config.backend_url}")
    while True:
        client.flush_buffer()
        for detection in detector.next_detections():
            client.upload_detection(detection)
        for health in detector.health_updates():
            client.upload_health(health)
        if args.once:
            break
        time.sleep(config.poll_seconds)


if __name__ == "__main__":
    main()
