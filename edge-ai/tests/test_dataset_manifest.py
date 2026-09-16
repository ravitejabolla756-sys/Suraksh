import json

import cv2
import numpy as np
import pytest

from app.perception.dataset import load_manifest


def make_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (16, 16))
    writer.write(np.zeros((16, 16, 3), dtype=np.uint8))
    writer.release()


def manifest(video):
    return {
        "name": "approved-test", "version": "1", "provenance": "test fixture",
        "license": "test-only", "intended_use_permitted": True,
        "frames": [{"video_path": video.name, "camera_id": "cam", "frame_index": 0,
                    "source_fps": 30, "objects": []}],
    }


def test_manifest_requires_provenance_and_explicit_permission(tmp_path):
    video = tmp_path / "sample.mp4"; make_video(video)
    data = manifest(video); data["provenance"] = ""
    path = tmp_path / "manifest.json"; path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="provenance"):
        load_manifest(path)


def test_manifest_rejects_incorrect_source_timestamp(tmp_path):
    video = tmp_path / "sample.mp4"; make_video(video)
    data = manifest(video); data["frames"][0].update(frame_index=30, source_timestamp=7)
    path = tmp_path / "manifest.json"; path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="conflicts"):
        load_manifest(path)
