"""Build a versioned, frame-indexed detection cache without altering source media."""
import json
import os
from pathlib import Path
import sys
import time

import cv2
import torch

try:
    _TORCHVISION_LIBRARY = torch.library.Library("torchvision", "DEF")
    _TORCHVISION_LIBRARY.define("nms(Tensor dets, Tensor scores, float iou_threshold) -> Tensor")
except Exception:
    _TORCHVISION_LIBRARY = None

from ultralytics import YOLO
from ultralytics.engine.results import Boxes
from ultralytics.utils.nms import TorchNMS

try:
    import torchvision
    torchvision.ops.nms = TorchNMS.nms
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.timestamp_tracker import TimestampAwareTracker, TrackerConfig


def batched_nms(boxes, scores, classes, threshold):
    """Portable class-aware NMS without depending on torchvision's native op."""
    keep = []
    for class_id in torch.unique(classes).tolist():
        indices = [int(index) for index in torch.where(classes == class_id)[0].tolist()]
        indices.sort(key=lambda index: float(scores[index]), reverse=True)
        while indices:
            current = indices.pop(0)
            keep.append(current)
            remaining = []
            for index in indices:
                first, second = boxes[current], boxes[index]
                x1, y1 = max(float(first[0]), float(second[0])), max(float(first[1]), float(second[1]))
                x2, y2 = min(float(first[2]), float(second[2])), min(float(first[3]), float(second[3]))
                intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
                area_first = max(0.0, float(first[2] - first[0])) * max(0.0, float(first[3] - first[1]))
                area_second = max(0.0, float(second[2] - second[0])) * max(0.0, float(second[3] - second[1]))
                overlap = intersection / max(area_first + area_second - intersection, 1e-6)
                if overlap < threshold:
                    remaining.append(index)
            indices = remaining
    return torch.tensor(keep, dtype=torch.long)


def main():
    source = ROOT / 'demo-media' / 'OP.mp4'
    output = ROOT / '.runtime' / 'op-replay'
    output.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(2)
    cv2.setNumThreads(1)
    model = YOLO(str(ROOT / 'yolo26n.pt'))
    tracker = TimestampAwareTracker(TrackerConfig(high_confidence=.35, low_confidence=.15,
                                                   new_track_confidence=.45,
                                                   max_lost_seconds=1.5))
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError('Cannot open OP.mp4')
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    # Evaluation replay should contain every decoded source frame. Runtime
    # realtime mode may sample, but it must never silently change this cache.
    step = max(1, int(os.environ.get("SURAKSH_OP_REPLAY_STEP", "1")))
    frames = []
    started = time.monotonic()
    try:
        index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if index % step == 0 or index == total - 1:
                height, width = frame.shape[:2]
                # Full view plus a magnified left road / station entrance pass.
                merged = []
                for crop, size in ((frame,1280),(frame[:, :round(width*.62)],960)):
                    result = model.predict(crop, imgsz=size, conf=.18,
                                           classes=[0,2,3,5,7], verbose=False)[0]
                    merged.append(result.boxes.data.cpu())
                data = torch.cat(merged)
                keep = batched_nms(data[:,:4],data[:,4],data[:,5],.45)
                boxes = Boxes(data[keep],(height,width)).numpy()
                candidates = [{'box': [float(value) for value in box],
                               'class_id': int(cls), 'confidence': float(confidence)}
                              for box, cls, confidence in zip(boxes.xyxy, boxes.cls, boxes.conf)]
                tracked = tracker.update(candidates, index / fps)
                objects = [{'id': int(item['id']), 'box': [round(float(v), 2) for v in item['box']],
                            'confidence': round(float(item['confidence']), 3),
                            'class_id': int(item['class_id'])}
                           for item in tracked['detections'] if item['id'] is not None]
                frames.append({'frame': index, 'source_timestamp': round(index / fps, 6), 'objects': objects,
                               'telemetry': tracked['telemetry']})
                if len(frames) % 30 == 0:
                    progress = {'status':'processing','frame':index,'total':total,
                                'percent':round(100*index/total,1)}
                    (output/'progress.json').write_text(json.dumps(progress))
                    print({**progress,'elapsed':round(time.monotonic()-started)},flush=True)
            index += 1
    finally:
        cap.release()
    if index != total:
        raise RuntimeError(f'Incomplete decode: {index}/{total}')
    stat = source.stat()
    payload = {'version':1,'source_size':stat.st_size,'source_mtime_ns':stat.st_mtime_ns,
               'model':'YOLO26n','tracker':'BoT-SORT','fps':fps,'width':width,'height':height,
               'total_frames':total,'step':step,'frames':frames,
               'mode':'Frame-complete evaluation replay; source timestamps; timestamp-aware tracking'}
    temp = output/'tracks.tmp.json'
    temp.write_text(json.dumps(payload,separators=(',',':')),encoding='utf-8')
    os.replace(temp,output/'tracks.json')
    print({'status':'ready','samples':len(frames),'seconds':round(time.monotonic()-started)},flush=True)


if __name__ == '__main__':
    main()
