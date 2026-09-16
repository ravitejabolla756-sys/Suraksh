"""Optional detector adapters sharing the Suraksh benchmark contract."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from .contracts import (
    Detection, DetectorInput, DetectorResult, DetectorUnavailable,
    PersonVehicleDetector, TimingBreakdown,
)


TARGET_NAMES = {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
TARGET_IDS = {name: class_id for class_id, name in TARGET_NAMES.items()}
RFDETR_COCO_IDS = {1: "person", 3: "car", 4: "motorcycle", 6: "bus", 8: "truck"}


def _ensure_ultralytics_nms_compatibility() -> None:
    """Use Ultralytics' pure-Torch NMS when this host lacks torchvision C++ ops."""
    try:
        import torchvision
        from ultralytics.utils import nms as ultralytics_nms
        torchvision.ops.nms
        ultralytics_nms.TORCHVISION_AVAILABLE = True
    except (ImportError, AttributeError, RuntimeError):
        from ultralytics.utils import nms as ultralytics_nms
        ultralytics_nms.TORCHVISION_AVAILABLE = False


class UltralyticsDetector(PersonVehicleDetector):
    license_status = "AGPL-3.0-or-later; enterprise license review required for proprietary deployment"

    def __init__(self, detector_id: str, model_path: Path, resolution: int, confidence: float = .15):
        self.detector_id = detector_id
        self.model_version = model_path.name
        self.model_path = model_path
        self.resolution = resolution
        self.confidence = confidence
        self.model: Any = None

    def load(self) -> None:
        if not self.model_path.is_file():
            raise DetectorUnavailable(f"missing local weights: {self.model_path}")
        try:
            from ultralytics import YOLO
            _ensure_ultralytics_nms_compatibility()
            self.model = YOLO(str(self.model_path))
        except Exception as exc:
            raise DetectorUnavailable(f"Ultralytics load failed: {type(exc).__name__}: {exc}") from exc

    def detect(self, item: DetectorInput) -> DetectorResult:
        if self.model is None:
            self.load()
        started = time.perf_counter()
        result = self.model.predict(item.frame, classes=list(TARGET_NAMES), conf=self.confidence,
                                    imgsz=self.resolution, verbose=False, device="cpu")[0]
        completed = time.perf_counter()
        speed = getattr(result, "speed", {}) or {}
        detections = []
        boxes = getattr(result, "boxes", None)
        if boxes is not None:
            for box, class_id, confidence in zip(boxes.xyxy, boxes.cls, boxes.conf):
                class_id = int(class_id)
                if class_id not in TARGET_NAMES:
                    continue
                coords = tuple(float(value) for value in box.tolist())
                detections.append(Detection(class_id, TARGET_NAMES[class_id], float(confidence), coords,
                                            item.source_frame_index, item.source_timestamp))
        timing = TimingBreakdown(speed.get("preprocess"), speed.get("inference"), speed.get("postprocess"),
                                 (completed - started) * 1000, completed,
                                 max(0.0, (completed - item.capture_timestamp) * 1000))
        return DetectorResult(self.detector_id, self.model_version, item, tuple(detections), timing,
                              {"resolution": self.resolution, "license": self.license_status})


class RFDETRDetector(PersonVehicleDetector):
    license_status = "Apache-2.0 for RF-DETR Nano through Large code and designated weights"
    _variants = {"nano": "RFDETRNano", "small": "RFDETRSmall", "medium": "RFDETRMedium"}

    def __init__(self, variant: str, resolution: int | None = None, confidence: float = .15):
        if variant not in self._variants:
            raise ValueError(f"unsupported RF-DETR variant: {variant}")
        self.variant = variant
        self.detector_id = f"rf-detr-{variant}"
        self.model_version = f"rf-detr-{variant}.pth"
        self.resolution = resolution
        self.confidence = confidence
        self.model: Any = None

    def load(self) -> None:
        try:
            import rfdetr
            model_class = getattr(rfdetr, self._variants[self.variant])
            kwargs = {"resolution": self.resolution} if self.resolution else {}
            self.model = model_class(**kwargs)
        except ImportError as exc:
            raise DetectorUnavailable("optional package 'rfdetr' is not installed") from exc
        except Exception as exc:
            raise DetectorUnavailable(f"RF-DETR load failed: {type(exc).__name__}: {exc}") from exc

    def detect(self, item: DetectorInput) -> DetectorResult:
        if self.model is None:
            self.load()
        started = time.perf_counter()
        prediction = self.model.predict(item.frame[:, :, ::-1].copy(), threshold=self.confidence,
                                        include_source_image=False)
        completed = time.perf_counter()
        detections = []
        names = getattr(prediction, "data", {}).get("class_name", [])
        for index, (box, confidence, raw_class_id) in enumerate(
                zip(prediction.xyxy, prediction.confidence, prediction.class_id)):
            fallback_name = RFDETR_COCO_IDS.get(int(raw_class_id))
            name = str(names[index]).lower() if index < len(names) else fallback_name
            if name in TARGET_IDS:
                detections.append(Detection(TARGET_IDS[name], name, float(confidence),
                                            tuple(float(value) for value in box),
                                            item.source_frame_index, item.source_timestamp))
        timing = TimingBreakdown(None, None, None, (completed - started) * 1000, completed,
                                 max(0.0, (completed - item.capture_timestamp) * 1000))
        return DetectorResult(self.detector_id, self.model_version, item, tuple(detections), timing,
                              {"resolution": self.resolution, "license": self.license_status})


class RTDETRv2Detector(PersonVehicleDetector):
    license_status = "Apache-2.0 implementation; checkpoint model card must be reviewed before deployment"

    def __init__(self, model_id: str, detector_id: str, confidence: float = .15):
        self.model_id = model_id
        self.detector_id = detector_id
        self.model_version = model_id
        self.confidence = confidence
        self.processor: Any = None
        self.model: Any = None

    def load(self) -> None:
        try:
            from transformers import RTDetrImageProcessor, RTDetrV2ForObjectDetection
            self.processor = RTDetrImageProcessor.from_pretrained(self.model_id)
            self.model = RTDetrV2ForObjectDetection.from_pretrained(self.model_id).eval()
        except ImportError as exc:
            raise DetectorUnavailable("optional package 'transformers' is not installed") from exc
        except Exception as exc:
            raise DetectorUnavailable(f"RT-DETRv2 load failed: {type(exc).__name__}: {exc}") from exc

    def detect(self, item: DetectorInput) -> DetectorResult:
        if self.model is None or self.processor is None:
            self.load()
        import torch
        preprocess_start = time.perf_counter()
        inputs = self.processor(images=item.frame[:, :, ::-1].copy(), return_tensors="pt")
        inference_start = time.perf_counter()
        with torch.no_grad():
            outputs = self.model(**inputs)
        postprocess_start = time.perf_counter()
        height, width = item.frame.shape[:2]
        result = self.processor.post_process_object_detection(
            outputs, target_sizes=torch.tensor([[height, width]]), threshold=self.confidence)[0]
        completed = time.perf_counter()
        detections = []
        id2label = self.model.config.id2label
        for box, confidence, class_id in zip(result["boxes"], result["scores"], result["labels"]):
            class_id = int(class_id)
            name = str(id2label.get(class_id, class_id)).lower()
            if name not in TARGET_NAMES.values():
                continue
            canonical_id = next(key for key, value in TARGET_NAMES.items() if value == name)
            detections.append(Detection(canonical_id, name, float(confidence),
                                        tuple(float(value) for value in box.tolist()),
                                        item.source_frame_index, item.source_timestamp))
        timing = TimingBreakdown((inference_start - preprocess_start) * 1000,
                                 (postprocess_start - inference_start) * 1000,
                                 (completed - postprocess_start) * 1000,
                                 (completed - preprocess_start) * 1000, completed,
                                 max(0.0, (completed - item.capture_timestamp) * 1000))
        return DetectorResult(self.detector_id, self.model_version, item, tuple(detections), timing,
                              {"license": self.license_status})


def candidate_detectors(root: Path) -> list[PersonVehicleDetector]:
    candidates: list[PersonVehicleDetector] = []
    for model, label in (("yolo11n.pt", "current-yolo11n"), ("yolo26n.pt", "yolo26n"),
                         ("yolo26s.pt", "yolo26s")):
        for resolution in (640, 960):
            candidates.append(UltralyticsDetector(f"{label}-{resolution}", root / model, resolution))
    candidates.extend(RFDETRDetector(variant) for variant in ("nano", "small", "medium"))
    candidates.extend([
        RTDETRv2Detector("PekingU/rtdetr_v2_r18vd", "rtdetrv2-r18"),
        RTDETRv2Detector("PekingU/rtdetr_v2_r34vd", "rtdetrv2-r34"),
    ])
    return candidates
