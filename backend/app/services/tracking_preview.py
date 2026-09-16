"""Independent playback, detection and OCR workers for recorded CCTV."""
from __future__ import annotations

from collections import deque
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any

import cv2
import numpy as np
import torch

# Some Windows CPU environments ship a torchvision wheel without the compiled
# NMS operator. Ultralytics can use its own NMS path, but torchvision must still
# be importable during model warm-up. Define the operator schema before the
# package registers its fake implementation; no detector behavior is changed.
try:
    _TORCHVISION_LIBRARY = torch.library.Library("torchvision", "DEF")
    _TORCHVISION_LIBRARY.define("nms(Tensor dets, Tensor scores, float iou_threshold) -> Tensor")
except Exception:
    _TORCHVISION_LIBRARY = None

from ultralytics import YOLO
from ultralytics.trackers.bot_sort import BOTSORT
from ultralytics.utils.nms import TorchNMS
from ultralytics.utils import IterableSimpleNamespace, YAML
from ultralytics.utils.checks import check_yaml
from app.services.preview_ocr import PreviewOCR
from app.services.timestamp_tracker import TimestampAwareTracker, TrackerConfig

try:
    import torchvision
    # The wheel can import but its compiled extension is unavailable. Use the
    # pure TorchNMS implementation shipped by the same Ultralytics version.
    torchvision.ops.nms = TorchNMS.nms
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[3]
# Keep the deployed demo default unchanged until the detector/tracker benchmark
# has annotated Suraksh evidence. Candidate models are selected only by the
# isolated benchmark runner through explicit configuration.
MODEL_PATH = Path(os.environ.get("SURAKSH_YOLO_MODEL", str(ROOT / "yolo11n.pt")))
CLASS_NAMES = {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
COUNT_KEYS = {0: "people", 2: "cars", 3: "motorcycles", 5: "buses", 7: "trucks"}
CLASS_COLORS = {0: (52, 211, 153), 2: (59, 130, 246), 3: (245, 158, 11), 5: (168, 85, 247), 7: (239, 68, 68)}
CLASS_IDS = list(CLASS_NAMES)
PREVIEW_WIDTH = int(os.environ.get("SURAKSH_PREVIEW_WIDTH", "960"))
AI_FPS = max(1.0, float(os.environ.get("SURAKSH_AI_FPS", "5")))
INFERENCE_SIZE = int(os.environ.get("SURAKSH_INFERENCE_SIZE", "640"))
COUNT_TTL_SECONDS = 1.5
TRACKER_CONFIG = TrackerConfig(
    high_confidence=float(os.environ.get("SURAKSH_TRACK_HIGH_CONF", "0.35")),
    low_confidence=float(os.environ.get("SURAKSH_TRACK_LOW_CONF", "0.15")),
    new_track_confidence=float(os.environ.get("SURAKSH_NEW_TRACK_CONF", "0.45")),
    iou_threshold=float(os.environ.get("SURAKSH_TRACK_IOU", "0.05")),
    max_lost_seconds=float(os.environ.get("SURAKSH_TRACK_MAX_LOST_SECONDS", "1.5")),
    min_hits=max(1, int(os.environ.get("SURAKSH_TRACK_MIN_HITS", "2"))),
)
ROI_CONFIG = json.loads(os.environ.get("SURAKSH_ROI_JSON", "{}"))
log = logging.getLogger(__name__)


class PreviewTracker(BOTSORT):
    """Keep IDs monotonic across camera resets; updates share INFERENCE_LOCK."""

    def __init__(self, args: Any):
        # Keep the small unit-test fixture and older callers compatible with
        # BoT-SORT's additional configuration fields.
        defaults = {
            "gmc_method": "none",
            "proximity_thresh": 0.5,
            "appearance_thresh": 0.8,
            "with_reid": False,
            "model": "auto",
        }
        for name, value in defaults.items():
            if not hasattr(args, name):
                setattr(args, name, value)
        super().__init__(args)

    @staticmethod
    def reset_id() -> None:
        # BYTETracker's default reset changes a process-global counter, even
        # while another camera still holds active tracks with those IDs.
        return None


def _label(name: str, track_id: int | None, confidence: float) -> str:
    return name.upper() + (f" ID {track_id}" if track_id is not None else "") + f" {confidence:.0%}"


class TrackingPreviewWorker:
    def __init__(self, source: Path, camera_key: str):
        self.source, self.camera_key = source, camera_key
        self.lock = threading.Lock()
        self.inference_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.frame_processed = threading.Event()
        # The browser's prepared replay owns OP.mp4. If this endpoint is used
        # directly, it still follows the same bounded latest-frame realtime
        # contract instead of blocking decode behind inference.
        self.synchronized_replay = False
        self.threads: list[threading.Thread] = []
        self.jpeg = {(a, i): None for a in (True, False) for i in (True, False)}
        self.version = 0
        self.latest_frame = None
        self.latest_frame_index = -1
        self.source_timestamp = 0.0
        self.captured_at = 0.0
        self.epoch = 0
        self.analysis = None
        self.source_fps = 25.0
        self.preview_frames = 0
        self.ai_frames = 0
        self.frame_drops = 0
        self.playback_drops = 0
        self.ai_error = None
        self.roi = ROI_CONFIG.get(camera_key)
        # Elevated wide shots need more pixels to retain distant road users.
        self.inference_size = int(os.environ.get("SURAKSH_OP_INFERENCE_SIZE", "960")) if camera_key == "OP.mp4" else INFERENCE_SIZE
        self.preview_times: deque[float] = deque(maxlen=100)
        self.ai_times: deque[float] = deque(maxlen=30)
        self.ocr = PreviewOCR()
        self.snapshot = {"camera": camera_key, "frame": -1, "status": "STARTING",
                         "source_timestamp": None, "detection_frame": None}

    def start(self) -> None:
        if any(t.is_alive() for t in self.threads):
            return
        self.stop_event.clear()
        self.threads = [threading.Thread(target=target, name=f"{name}-{self.camera_key}", daemon=True)
                        for target, name in ((self._decode_loop, "decode"), (self._ai_loop, "detect"),
                                             (lambda: self.ocr.run(self.stop_event), "ocr"))]
        for thread in self.threads:
            thread.start()

    def latest(self, show_annotations=True, show_track_ids=True):
        with self.lock:
            return self.jpeg[(show_annotations, show_track_ids)], self.version, dict(self.snapshot)

    @staticmethod
    def _fps(times) -> float:
        return round((len(times)-1)/max(times[-1]-times[0], 0.001), 1) if len(times)>1 else 0.0

    def _decode_loop(self) -> None:
        cap = cv2.VideoCapture(str(self.source))
        if not cap.isOpened():
            with self.lock:
                self.snapshot["status"] = "DECODE_ERROR"
            return
        self.source_fps = max(float(cap.get(cv2.CAP_PROP_FPS) or 25), 1)
        duration = 1 / self.source_fps
        due = time.monotonic()
        try:
            while not self.stop_event.is_set():
                if self.stop_event.wait(max(0, due-time.monotonic())):
                    break
                # Catch up with the source clock, rather than slowing the recording.
                skipped = 0 if self.synchronized_replay else min(int(max(0, time.monotonic()-due)/duration), 100)
                for _ in range(skipped):
                    if not cap.grab():
                        break
                    self.playback_drops += 1
                    due += duration
                ok, frame = cap.read()
                if not ok:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    with self.lock:
                        self.epoch += 1
                        self.analysis = None
                        self.ocr.reset(self.epoch)
                    ok, frame = cap.read()
                    due = time.monotonic()
                if not ok:
                    break
                index = max(0, int(cap.get(cv2.CAP_PROP_POS_FRAMES))-1)
                position_ms = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
                source_timestamp = position_ms / 1000 if position_ms > 0 else index / self.source_fps
                self.frame_processed.clear()
                with self.lock:
                    self.latest_frame, self.latest_frame_index = frame, index
                    self.source_timestamp = source_timestamp
                    self.captured_at = time.monotonic()
                self.preview_frames += 1
                self.preview_times.append(time.monotonic())
                due += duration
        except Exception:
            log.exception("Preview failed for %s", self.camera_key)
            with self.lock:
                self.snapshot["status"] = "DECODE_ERROR"
        finally:
            cap.release()

    def _ai_loop(self) -> None:
        model = tracker = None
        processed = (-1, -1)
        observed, ocr_due = {}, {}
        due = 0.0
        device = "CUDA" if torch.cuda.is_available() else "CPU"
        while not self.stop_event.is_set():
            if self.stop_event.wait(max(0, due-time.monotonic())):
                break
            due = time.monotonic()+1/AI_FPS
            try:
                with self.inference_lock:
                    # Ultralytics also sets this during setup; cap it again after setup.
                    torch.set_num_threads(2)
                    if model is None:
                        model = YOLO(str(MODEL_PATH))
                    with self.lock:
                        if self.latest_frame is None:
                            continue
                        frame = self.latest_frame.copy()
                        index, epoch, captured = self.latest_frame_index, self.epoch, self.captured_at
                        source_timestamp = self.source_timestamp
                    if processed == (epoch, index):
                        continue
                    if processed[0] != epoch:
                        tracker = TimestampAwareTracker(TRACKER_CONFIG)
                        observed, ocr_due = {name:set() for name in CLASS_NAMES.values()}, {}
                    elif index > processed[1]:
                        self.frame_drops += max(0, index-processed[1]-1)
                    processed = (epoch, index)
                    xoff = yoff = 0
                    image = frame
                    if self.roi:
                        xoff,yoff,x2,y2 = map(int,self.roi)
                        image = frame[yoff:y2,xoff:x2]
                    started = time.monotonic()
                    prediction = model.predict(image, classes=CLASS_IDS, conf=TRACKER_CONFIG.low_confidence,
                                               imgsz=self.inference_size,
                                               device=0 if device=="CUDA" else "cpu", verbose=False)[0]
                    torch.set_num_threads(2)
                    boxes = prediction.boxes.cpu().numpy()
                    candidates = [{"box": [float(value) for value in box],
                                   "class_id": int(cls), "confidence": float(confidence)}
                                  for box, cls, confidence in zip(boxes.xyxy, boxes.cls, boxes.conf)
                                  if int(cls) in CLASS_NAMES]
                    tracker_result = tracker.update(candidates, source_timestamp)
                    ids = {index: item["id"] for index, item in enumerate(tracker_result["detections"])
                           if item["id"] is not None}
                    analysis = self._analysis(boxes,ids,index,observed,(xoff,yoff))
                    analysis.update(epoch=epoch,at=captured,source_timestamp=source_timestamp,
                                    inference_ms=(time.monotonic()-started)*1000,device=device,
                                    tracker=tracker_result["telemetry"])
                with self.lock:
                    if epoch != self.epoch:
                        continue
                    self.analysis = analysis
                    self.ai_error = None
                    self.ai_frames += 1
                    self.ai_times.append(time.monotonic())
                # The encoded image and analysis come from the same source
                # frame. Decode remains latest-only while inference may lag.
                self._publish(frame, index, analysis)
                self.frame_processed.set()
                # OCR submission copies one crop. OCR never executes in this loop.
                candidates = [d for d in analysis["detections"] if d["class_id"]!=0 and d["id"] is not None
                              and time.monotonic()-ocr_due.get(d["id"],0)>=1.5]
                candidates.sort(key=lambda d:(d["box"][2]-d["box"][0])*(d["box"][3]-d["box"][1]),reverse=True)
                if candidates:
                    d = candidates[0]
                    x1,y1,x2,y2 = d["box"]
                    crop = frame[max(0,y1):min(frame.shape[0],y2),max(0,x1):min(frame.shape[1],x2)]
                    if crop.size:
                        self.ocr.submit(crop,d["id"],index,epoch)
                        ocr_due[d["id"]] = time.monotonic()
            except Exception as exc:
                log.exception("Detector failed for %s",self.camera_key)
                with self.lock:
                    self.ai_error = type(exc).__name__
                    self.snapshot["status"] = "AI_ERROR"
                    self.snapshot["ai_error"] = self.ai_error
                processed = (-1, -1)
                self.stop_event.wait(0.5)

    @staticmethod
    def _analysis(boxes,ids,index,observed,offset=(0,0)) -> dict[str,Any]:
        counts = {k:0 for k in COUNT_KEYS.values()}
        detections = []
        for i,(box,cls,confidence) in enumerate(zip(boxes.xyxy,boxes.cls,boxes.conf)):
            cls = int(cls)
            if cls not in CLASS_NAMES:
                continue
            coords = (box+np.array([offset[0],offset[1],offset[0],offset[1]])).astype(int).tolist()
            track_id = ids.get(i)
            counts[COUNT_KEYS[cls]] += 1
            detections.append({"box":coords,"class_id":cls,"class":CLASS_NAMES[cls],
                               "id":track_id,"confidence":float(confidence)})
            if track_id is not None:
                observed[CLASS_NAMES[cls]].add(track_id)
        unique = {f"unique_{'people' if k=='person' else k}":len(v) for k,v in observed.items()}
        return {"frame":index,**counts,"vehicles":sum(counts[k] for k in ("cars","motorcycles","buses","trucks")),
                "detections":detections,"objects":[{k:d[k] for k in ("class","id","confidence")} for d in detections],
                "observed":unique}

    def _publish(self,frame,frame_index,analysis) -> None:
        age = time.monotonic()-analysis["at"] if analysis else None
        valid = analysis is not None and analysis["epoch"]==self.epoch
        fresh = valid and (analysis["frame"] == frame_index if self.synchronized_replay else age<=COUNT_TTL_SECONDS)
        status = "AI_ERROR" if self.ai_error else "TRACKING" if fresh else "STALE" if valid else "STARTING"
        # Unknown observations must not masquerade as a measured zero.
        counts = {key:analysis[key] if fresh else None for key in (*COUNT_KEYS.values(),"vehicles")}
        with self.lock:
            ai_fps = self._fps(self.ai_times)
        snapshot = {"camera":self.camera_key,"frame":frame_index,"epoch":self.epoch,
                    "detection_frame":analysis["frame"] if valid else None,
                    "source_timestamp":analysis.get("source_timestamp") if valid else None,
                    "detection_age_ms":round(age*1000) if valid else None,
                    **counts,"objects":analysis["objects"] if fresh else [],
                    **(analysis["observed"] if valid else {}),"status":status,
                    "synthetic_input":self.camera_key.startswith("anpr-"),"plates_blurred":False,
                    "source_fps":self.source_fps,"preview_fps":self._fps(self.preview_times),
                    "ai_fps":ai_fps,"ai_frames":self.ai_frames,
                    "inference_size":self.inference_size,"model":MODEL_PATH.stem,
                    "playback_mode":"analysis-paced replay" if self.synchronized_replay else "realtime replay",
                    "inference_ms":round(analysis["inference_ms"],1) if valid else None,
                    "device":analysis["device"] if valid else "CPU","frame_drops":self.frame_drops,
                    "playback_drops":self.playback_drops,"ai_error":self.ai_error,
                    "tracker":analysis.get("tracker", {}) if valid else {},**self.ocr.snapshot()}
        encoded = {}
        # Resize first: avoid rendering three full-resolution copies per frame.
        scale = min(1.0,PREVIEW_WIDTH/frame.shape[1])
        base = cv2.resize(frame,(round(frame.shape[1]*scale),round(frame.shape[0]*scale)))
        for annotations,ids in ((False,True),(True,True),(True,False)):
            image = base.copy()
            if annotations and fresh:
                for d in analysis["detections"]:
                    x1,y1,x2,y2 = [round(v*scale) for v in d["box"]]
                    color = CLASS_COLORS[d["class_id"]]
                    cv2.rectangle(image,(x1,y1),(x2,y2),color,2)
                    cv2.putText(image,_label(d["class"],d["id"] if ids else None,d["confidence"]),
                                (max(0,x1),max(12,y1-4)),cv2.FONT_HERSHEY_SIMPLEX,0.4,color,1,cv2.LINE_AA)
            label = f"{status} | VEHICLES {counts['vehicles'] if fresh else '--'} | FRAME {snapshot['detection_frame']}"
            cv2.putText(image,label,(8,16),cv2.FONT_HERSHEY_SIMPLEX,0.4,(255,255,255),1,cv2.LINE_AA)
            ok,data = cv2.imencode(".jpg",image,[cv2.IMWRITE_JPEG_QUALITY,90])
            if ok:
                encoded[(annotations,ids)] = data.tobytes()
        if len(encoded)==3:
            encoded[(False,False)] = encoded[(False,True)]
            with self.lock:
                self.jpeg,self.snapshot = encoded,snapshot
                self.version += 1


class TrackingPreviewManager:
    def __init__(self):
        self._workers = {}
        self._lock = threading.Lock()

    def worker(self,source:Path,camera_key:str) -> TrackingPreviewWorker:
        with self._lock:
            worker = self._workers.get(camera_key)
            if worker is None or worker.source!=source:
                if worker:
                    worker.stop_event.set()
                worker = TrackingPreviewWorker(source,camera_key)
                self._workers[camera_key] = worker
            worker.start()
            return worker


preview_manager = TrackingPreviewManager()
