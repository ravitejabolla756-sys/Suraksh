"""Bounded temporal evidence references shared by safety event consumers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class EvidenceFrameReference:
    """Pointer to existing recording/evidence storage; no pixels are retained here."""

    camera_id: str
    sequence: int
    timestamp: datetime
    recording_id: str | None = None
    frame_uri: str | None = None
    offset_seconds: float | None = None
    sha256: str | None = None

    def public_payload(self) -> dict:
        """Return an API-safe reference; never expose local filesystem paths."""
        return {"camera_id": self.camera_id, "sequence": self.sequence,
                "timestamp": self.timestamp.isoformat(), "recording_id": self.recording_id,
                "frame_uri": self.frame_uri if self.frame_uri and not self.frame_uri.startswith(("/", "\\", "file:")) and ":\\" not in self.frame_uri else None,
                "offset_seconds": self.offset_seconds, "sha256": self.sha256}


class EvidenceAccessPolicy:
    """Tenant/camera authorization gate for evidence references."""
    def __init__(self, camera_organizations: Mapping[str, str]):
        self.camera_organizations = dict(camera_organizations)

    def authorize(self, organization_id: str, reference: EvidenceFrameReference) -> bool:
        return self.camera_organizations.get(reference.camera_id) == organization_id

    def filter(self, organization_id: str, references: Iterable[EvidenceFrameReference]) -> tuple[EvidenceFrameReference, ...]:
        return tuple(reference for reference in references if self.authorize(organization_id, reference))


@dataclass(frozen=True, slots=True)
class TrackHistoryPoint:
    sequence: int
    timestamp: datetime
    track_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TemporalEvidenceSample:
    """One frame's reference and tracker snapshot."""

    reference: EvidenceFrameReference
    track_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.reference.camera_id != self.camera_id:
            raise ValueError("sample camera_id must match its evidence reference")

    @property
    def camera_id(self) -> str:
        return self.reference.camera_id

    @property
    def timestamp(self) -> datetime:
        return self.reference.timestamp


@dataclass(frozen=True, slots=True)
class EventCandidate:
    event_type: str
    camera_id: str
    timestamp: datetime
    track_ids: tuple[int, ...] = ()
    confidence: float = 0.0
    candidate_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True, slots=True)
class TemporalEvidenceConfig:
    pre_event_seconds: float = 10.0
    event_context_before_seconds: float = 2.0
    event_context_after_seconds: float = 2.0
    post_event_seconds: float = 10.0
    max_buffer_seconds: float = 30.0
    max_samples: int = 512
    max_evidence_frames: int = 8
    deduplication_seconds: float = 30.0
    stale_event_grace_seconds: float = 30.0

    def __post_init__(self) -> None:
        values = (self.pre_event_seconds, self.event_context_before_seconds, self.event_context_after_seconds, self.post_event_seconds, self.max_buffer_seconds, self.deduplication_seconds, self.stale_event_grace_seconds)
        if any(value < 0 for value in values) or self.max_samples < 1 or self.max_evidence_frames < 1:
            raise ValueError("temporal evidence limits must be non-negative and buffer sizes positive")
        if self.max_buffer_seconds < self.pre_event_seconds + self.post_event_seconds:
            raise ValueError("max_buffer_seconds must cover the configured event window")


@dataclass(frozen=True, slots=True)
class TemporalEvidence:
    event: EventCandidate
    temporal_window: tuple[datetime, datetime]
    pre_event: tuple[EvidenceFrameReference, ...]
    event_evidence: tuple[EvidenceFrameReference, ...]
    post_event: tuple[EvidenceFrameReference, ...]
    track_history: tuple[TrackHistoryPoint, ...]

    @property
    def evidence(self) -> tuple[EvidenceFrameReference, ...]:
        return self.pre_event + self.event_evidence + self.post_event


@dataclass
class _CameraState:
    samples: deque[TemporalEvidenceSample]
    pending: dict[str, EventCandidate]
    completed: deque[tuple[tuple[str, tuple[int, ...]], datetime]]


class TemporalEvidenceEngine:
    """Camera-isolated rolling evidence engine with bounded memory.

    Consumers submit references to an existing recorder plus track IDs. The
    engine never owns decoded pixel buffers or writes video files.
    """

    def __init__(self, config: TemporalEvidenceConfig | None = None):
        self.config = config or TemporalEvidenceConfig()
        self._cameras: dict[str, _CameraState] = {}

    def _state(self, camera_id: str) -> _CameraState:
        return self._cameras.setdefault(camera_id, _CameraState(deque(maxlen=self.config.max_samples), {}, deque()))

    def ingest(self, sample: TemporalEvidenceSample) -> tuple[TemporalEvidence, ...]:
        state = self._state(sample.camera_id)
        if state.samples and sample.timestamp < state.samples[-1].timestamp:
            raise ValueError("evidence samples must arrive in timestamp order per camera")
        state.samples.append(sample)
        self._purge_buffer(state, sample.timestamp)
        return self.poll(sample.camera_id, sample.timestamp)

    def trigger(self, candidate: EventCandidate) -> bool:
        state = self._state(candidate.camera_id)
        self._purge_buffer(state, candidate.timestamp)
        key = self._dedup_key(candidate)
        self._purge_completed(state, candidate.timestamp)
        if key in {completed_key for completed_key, _ in state.completed}:
            return False
        if any(self._dedup_key(existing) == key for existing in state.pending.values()):
            return False
        state.pending[candidate.candidate_id] = candidate
        return True

    def resolve(self, candidate_id: str, now: datetime | None = None) -> tuple[TemporalEvidence, ...]:
        """Resolve a pending candidate using available evidence without storage side effects."""
        for camera_id, state in self._cameras.items():
            candidate = state.pending.get(candidate_id)
            if candidate is not None:
                return self.poll(camera_id, now or candidate.timestamp + timedelta(seconds=self.config.post_event_seconds))
        return ()

    def poll(self, camera_id: str, now: datetime | None = None) -> tuple[TemporalEvidence, ...]:
        state = self._state(camera_id)
        current = now or datetime.now(timezone.utc)
        ready = [candidate for candidate in state.pending.values() if current >= candidate.timestamp + timedelta(seconds=self.config.post_event_seconds)]
        results = tuple(self._extract(state, candidate) for candidate in ready)
        for candidate in ready:
            state.pending.pop(candidate.candidate_id, None)
            state.completed.append((self._dedup_key(candidate), candidate.timestamp))
        self._purge_completed(state, current)
        self._purge_buffer(state, current)
        return results

    def cleanup(self, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        for camera_id, state in list(self._cameras.items()):
            stale_before = current - timedelta(seconds=self.config.post_event_seconds + self.config.stale_event_grace_seconds)
            for candidate_id, candidate in list(state.pending.items()):
                if candidate.timestamp < stale_before:
                    state.pending.pop(candidate_id, None)
            self._purge_completed(state, current)
            self._purge_buffer(state, current)
            if not state.samples and not state.pending and not state.completed:
                self._cameras.pop(camera_id, None)

    def pending_count(self, camera_id: str | None = None) -> int:
        if camera_id is None:
            return sum(len(state.pending) for state in self._cameras.values())
        return len(self._state(camera_id).pending)

    def buffer_size(self, camera_id: str) -> int:
        return len(self._state(camera_id).samples)

    def _extract(self, state: _CameraState, candidate: EventCandidate) -> TemporalEvidence:
        cfg = self.config
        start = candidate.timestamp - timedelta(seconds=cfg.pre_event_seconds)
        end = candidate.timestamp + timedelta(seconds=cfg.post_event_seconds)
        event_start = candidate.timestamp - timedelta(seconds=cfg.event_context_before_seconds)
        event_end = candidate.timestamp + timedelta(seconds=cfg.event_context_after_seconds)
        samples = list(state.samples)
        pre = self._select([sample.reference for sample in samples if start <= sample.timestamp < event_start])
        event = self._select([sample.reference for sample in samples if event_start <= sample.timestamp <= event_end])
        post = self._select([sample.reference for sample in samples if event_end < sample.timestamp <= end])
        history = tuple(TrackHistoryPoint(sample.reference.sequence, sample.timestamp, sample.track_ids) for sample in samples if start <= sample.timestamp <= end)
        return TemporalEvidence(candidate, (start, end), pre, event, post, history)

    def _select(self, references: list[EvidenceFrameReference]) -> tuple[EvidenceFrameReference, ...]:
        if len(references) <= self.config.max_evidence_frames:
            return tuple(references)
        indices = [round(index * (len(references) - 1) / (self.config.max_evidence_frames - 1)) for index in range(self.config.max_evidence_frames)]
        return tuple(references[index] for index in indices)

    def _purge_buffer(self, state: _CameraState, now: datetime) -> None:
        cutoff = now - timedelta(seconds=self.config.max_buffer_seconds)
        while state.samples and state.samples[0].timestamp < cutoff:
            state.samples.popleft()

    def _dedup_key(self, candidate: EventCandidate) -> tuple[str, tuple[int, ...]]:
        return candidate.event_type, tuple(sorted(set(candidate.track_ids)))

    def _purge_completed(self, state: _CameraState, now: datetime) -> None:
        cutoff = now - timedelta(seconds=self.config.deduplication_seconds)
        while state.completed and state.completed[0][1] < cutoff:
            state.completed.popleft()
