"""ANPR orchestration. Consumes tracked frames without changing their identities."""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import time

from .contracts import (ANPRConfig, NumberPlateDetector, OCRReader, OCRObservation,
                        PlateDetection, PlateRecognitionResult, VehicleTrack)
from .association import associate, continuous, relative_position
from .fusion import Sample, TemporalFusion
from .quality import PREPROCESSING_VERSION, assess, enhance
from .validation import PlateValidator


@dataclass(frozen=True)
class RecognizedEvidence:
    result: PlateRecognitionResult
    original_frame: object
    plate_crop: object


class ANPRPipeline:
    """One instance per camera worker. Call from a single consumer thread."""

    def __init__(self, detector: NumberPlateDetector, ocr: OCRReader, config: ANPRConfig = ANPRConfig(),
                 bundle_version: str = "unregistered"):
        self.detector, self.ocr, self.config = detector, ocr, config
        self.bundle_version = bundle_version
        self.validator = PlateValidator(config.region, config.validation_rule_version, config.validation_patterns)
        self.fusion = TemporalFusion(config)
        self.tracks: dict[tuple, VehicleTrack] = {}
        self.positions: dict[tuple, tuple[float, float]] = {}
        self.sampled: dict[tuple, float] = {}
        self.touched: dict[tuple, float] = {}
        self.last_detection: dict[tuple, float] = {}

    @property
    def versions(self) -> dict[str, str]:
        return {"bundle": self.bundle_version, "plate_detector": self.detector.model_version,
                "ocr": self.ocr.model_version, "preprocessing": PREPROCESSING_VERSION + ("-enhanced" if self.config.enhancement else "-original"),
                "validation": self.config.validation_rule_version}

    def _clear(self, key: tuple) -> None:
        self.fusion.clear(key)
        for table in (self.tracks, self.positions, self.sampled, self.touched):
            table.pop(key, None)

    def clear_track(self, camera_id: str, vehicle_track_id: int, organization_id: str | None = None) -> None:
        for key in list(self.touched):
            if key[1] == camera_id and key[3] == vehicle_track_id and (organization_id is None or key[0] == organization_id):
                self._clear(key)

    def expire(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        for key, touched in list(self.touched.items()):
            if now-touched > self.config.retention_seconds:
                self._clear(key)

    def add_observation(self, organization_id: str, camera_id: str, vehicle_track_id: int, observation: OCRObservation,
                        detection_confidence: float, quality_score: float, evidence_reference: str | None = None,
                        *, tracker_session_id: str = "legacy", observed_at: datetime | None = None,
                        vehicle_class: str = "vehicle") -> PlateRecognitionResult | None:
        """Adapter/test entry point; durable storage additionally requires both images."""
        if not self.config.enabled:
            return None
        self.expire()
        key = (organization_id, camera_id, tracker_session_id, vehicle_track_id)
        if key not in self.touched and len(self.touched) >= self.config.max_tracks:
            self._clear(min(self.touched, key=self.touched.get))
        self.touched[key] = time.monotonic()
        validation = self.validator.validate(observation.raw_text)
        if (not validation.valid or observation.confidence < self.config.minimum_ocr_confidence
                or not self.config.minimum_detector_confidence <= detection_confidence <= 1 or not 0 < quality_score <= 1):
            self.fusion.reject(key)
            return None
        observation = replace(observation, normalized_text=validation.normalized_text)
        sample = Sample(observation, observed_at or datetime.now(timezone.utc), detection_confidence,
                        quality_score, evidence_reference or "", validation.rule)
        consensus = self.fusion.add(key, sample)
        if consensus is None or not evidence_reference:
            return None
        matching = consensus.matching
        return PlateRecognitionResult(
            consensus.result_id, organization_id, camera_id, vehicle_track_id, observation.raw_text,
            consensus.text, round(consensus.stability * min(consensus.ocr_confidence, detection_confidence, quality_score), 4),
            detection_confidence, consensus.ocr_confidence, quality_score, matching[0].observed_at,
            matching[-1].observed_at, observation.source_frame_index, observation.source_timestamp,
            evidence_reference, self.bundle_version, "valid", tracker_session_id, vehicle_class,
            f"anpr:{consensus.result_id}:crop", f"{camera_id}/{tracker_session_id}/{vehicle_track_id}",
            self.versions, len(matching), validation.rule)

    def process(self, frame, tracks: list[VehicleTrack]) -> list[RecognizedEvidence]:
        if not self.config.enabled or not tracks:
            return []
        cfg = self.config
        self.expire()
        scope = {(t.organization_id, t.camera_id, t.tracker_session_id, t.source_frame_index, t.source_timestamp) for t in tracks}
        if len(scope) != 1 or len({t.key for t in tracks}) != len(tracks):
            raise ValueError("ANPR needs distinct tracks from one scoped source frame")
        tracks = [t for t in tracks if t.vehicle_class in {"car", "truck", "bus", "motorcycle", "vehicle"}]
        eligible = []
        for track in tracks:
            key = track.key
            previous = self.tracks.get(key)
            if previous and (track.source_frame_index <= previous.source_frame_index or track.source_timestamp <= previous.source_timestamp):
                continue
            if previous and not continuous(previous, track, cfg.continuity_gap_seconds):
                self._clear(key)
            if key not in self.touched and len(self.touched) >= cfg.max_tracks:
                self._clear(min(self.touched, key=self.touched.get))
            self.tracks[key], self.touched[key] = track, time.monotonic()
            interval = cfg.confirmed_interval_seconds if key in self.fusion.confirmed else cfg.sample_interval_seconds
            if track.source_timestamp-self.sampled.get(key, -1e9) >= interval:
                eligible.append(track)
        if not eligible:
            return []
        first = eligible[0]
        camera_scope = first.key[:3]
        if first.source_timestamp-self.last_detection.get(camera_scope, -1e9) < cfg.sample_interval_seconds:
            return []
        self.last_detection = {camera_scope: first.source_timestamp}
        plates = self.detector.detect(frame.copy(), first.source_frame_index, first.source_timestamp)
        proposals: dict[tuple, list[PlateDetection]] = {}
        due = {t.key: t for t in eligible}
        for plate in plates:
            track = associate(plate, tracks, self.positions)
            if track and track.key in due:
                proposals.setdefault(track.key, []).append(plate)
        results = []
        for track in sorted(eligible, key=lambda t: self.sampled.get(t.key, -1e9))[:cfg.max_ocr_per_frame]:
            self.sampled[track.key] = track.source_timestamp
            candidates = proposals.get(track.key, [])
            if len(candidates) != 1:
                self.fusion.reject(track.key)
                continue
            plate = candidates[0]
            crop, quality = assess(frame, plate, cfg)
            if not quality.usable:
                self.fusion.reject(track.key)
                continue
            observation = self.ocr.read(enhance(crop, plate, cfg), track.source_frame_index, track.source_timestamp)
            if (observation.source_frame_index != track.source_frame_index
                    or observation.source_timestamp != track.source_timestamp):
                raise ValueError("OCR provider changed source identity")
            self.positions[track.key] = relative_position(plate, track)
            result = self.add_observation(track.organization_id, track.camera_id, track.track_id, observation,
                plate.confidence, quality.score, f"source:{track.camera_id}:{track.tracker_session_id}:{track.source_frame_index}",
                tracker_session_id=track.tracker_session_id, observed_at=track.observed_at, vehicle_class=track.vehicle_class)
            if result:
                results.append(RecognizedEvidence(result, frame.copy(), crop.copy()))
        return results
