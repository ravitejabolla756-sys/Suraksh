import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.services.preview_ocr import PreviewOCR
from app.services.tracking_preview import CLASS_NAMES, PreviewTracker, TrackingPreviewWorker
from ultralytics.trackers.basetrack import BaseTrack
from ultralytics.utils import IterableSimpleNamespace, YAML
from ultralytics.utils.checks import check_yaml


def test_camera_reset_does_not_reuse_another_cameras_track_ids():
    args = IterableSimpleNamespace(**YAML.load(check_yaml('bytetrack.yaml')))
    first = BaseTrack.next_id()
    tracker = PreviewTracker(args)
    second = BaseTrack.next_id()
    tracker.reset()
    third = BaseTrack.next_id()
    assert first < second < third


def observation(count=2):
    boxes = SimpleNamespace(xyxy=np.array([[5,20,60,60]]*count),
                            cls=np.array([2]*count), conf=np.array([0.8]*count))
    observed = {name:set() for name in CLASS_NAMES.values()}
    return TrackingPreviewWorker._analysis(boxes,{},10,observed)


def test_unconfirmed_detections_are_counted():
    result = observation()
    assert result['vehicles'] == 2
    assert all(d['id'] is None for d in result['detections'])
    assert result['observed']['unique_people'] == 0


def test_realtime_preview_publishes_frame_matched_analysis():
    worker = TrackingPreviewWorker(Path('unused.mp4'), 'OP.mp4')
    frame = np.zeros((80,120,3), np.uint8)
    result = observation()
    result.update(at=time.monotonic(), epoch=0, inference_ms=10, device='CPU')
    worker._publish(frame,10,result)
    assert worker.latest()[2]['vehicles'] == 2
    assert worker.latest()[2]['playback_mode'] == 'realtime replay'
    assert worker.latest()[2]['detection_frame'] == 10


def test_empty_scene_is_zero_and_stale_scene_is_unknown():
    worker = TrackingPreviewWorker(Path('unused.mp4'),'unit')
    frame = np.zeros((80,120,3),np.uint8)
    for count in (2,0):
        result = observation(count)
        result.update(at=time.monotonic(),epoch=0,inference_ms=10,device='CPU')
        worker._publish(frame,10,result)
        assert worker.latest()[2]['vehicles'] == count
    result['at'] -= 3
    worker._publish(frame,12,result)
    assert worker.latest()[2]['status'] == 'STALE'
    assert worker.latest()[2]['vehicles'] is None
    worker.epoch = 1
    worker._publish(frame,0,result)
    assert worker.latest()[2]['detection_frame'] is None


def test_blocked_ocr_does_not_block_detector_or_leak_across_replay(monkeypatch):
    entered,release,stop = threading.Event(),threading.Event(),threading.Event()
    def slow_read(self,crop):
        entered.set()
        release.wait(3)
        return {'text':'KA01AB1234','confidence':0.9}
    monkeypatch.setattr('app.services.preview_ocr.PlateOCR.read',slow_read)
    reader = PreviewOCR()
    thread = threading.Thread(target=reader.run,args=(stop,),daemon=True)
    thread.start()
    try:
        reader.submit(np.zeros((30,60,3),np.uint8),1,10,0)
        assert entered.wait(2)
        # Detector analysis/publication completes while OCR is deliberately blocked.
        worker = TrackingPreviewWorker(Path('unused.mp4'),'unit')
        worker.ocr = reader
        result = observation()
        result.update(at=time.monotonic(),epoch=0,inference_ms=10,device='CPU')
        worker._publish(np.zeros((80,120,3),np.uint8),10,result)
        assert worker.latest()[2]['vehicles'] == 2
        reader.reset(1)
        release.set()
    finally:
        stop.set()
        release.set()
        thread.join(3)
    assert reader.snapshot()['plates'] == []
