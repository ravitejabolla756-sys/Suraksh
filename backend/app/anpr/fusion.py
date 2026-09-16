"""Bounded distinct-frame OCR consensus with conservative character voting."""
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from .contracts import ANPRConfig, OCRObservation


@dataclass(frozen=True, slots=True)
class Sample:
    observation: OCRObservation
    observed_at: datetime
    detection_confidence: float
    quality_score: float
    evidence_reference: str
    validation_rule: str


@dataclass(frozen=True, slots=True)
class Consensus:
    result_id: str
    text: str
    stability: float
    ocr_confidence: float
    matching: tuple[Sample, ...]


class TemporalFusion:
    def __init__(self, config: ANPRConfig):
        self.config = config
        self.history: dict[tuple, deque[Sample]] = {}
        self.confirmed: dict[tuple, tuple[str, str]] = {}
        self.last_source: dict[tuple, tuple[int, float]] = {}

    def clear(self, key: tuple) -> None:
        self.history.pop(key, None)
        self.confirmed.pop(key, None)
        self.last_source.pop(key, None)

    def reject(self, key: tuple) -> None:
        self.confirmed.pop(key, None)

    def add(self, key: tuple, sample: Sample) -> Consensus | None:
        cfg, observation = self.config, sample.observation
        previous = self.last_source.get(key)
        if previous and (observation.source_frame_index <= previous[0] or observation.source_timestamp <= previous[1]):
            return None
        if key not in self.history and len(self.history) >= cfg.max_tracks:
            self.clear(next(iter(self.history)))
        self.last_source[key] = (observation.source_frame_index, observation.source_timestamp)
        history = self.history.setdefault(key, deque(maxlen=cfg.max_observations))
        cutoff = observation.source_timestamp - cfg.temporal_window_seconds
        while history and history[0].observation.source_timestamp < cutoff:
            history.popleft()
        history.append(sample)
        if len(history) < cfg.minimum_observations:
            self.reject(key)
            return None
        scores: dict[str, float] = defaultdict(float)
        for item in history:
            obs = item.observation
            scores[obs.normalized_text] += obs.confidence if cfg.confidence_weighting else 1.
        winner = max(scores, key=scores.get)
        if cfg.character_voting:
            lengths: dict[int, float] = defaultdict(float)
            for text, score in scores.items():
                lengths[len(text)] += score
            length = max(lengths, key=lengths.get)
            characters = []
            for index in range(length):
                votes: dict[str, float] = defaultdict(float)
                for item in history:
                    obs = item.observation
                    if len(obs.normalized_text) != length:
                        continue
                    weight = obs.confidence if cfg.confidence_weighting else 1.
                    if cfg.confidence_weighting and len(obs.character_confidence) == length:
                        weight *= obs.character_confidence[index]
                    votes[obs.normalized_text[index]] += weight
                characters.append(max(votes, key=votes.get))
            character_winner = "".join(characters)
            if character_winner not in scores:
                self.reject(key)
                return None
            winner = character_winner
        matching = tuple(s for s in history if s.observation.normalized_text == winner)
        stability = scores[winner] / max(sum(scores.values()), 1e-9)
        if (len(matching) < cfg.minimum_observations or len(history)-len(matching) > cfg.maximum_disagreement
                or stability < cfg.plate_stability_requirement or observation.normalized_text != winner):
            self.reject(key)
            return None
        old = self.confirmed.get(key)
        result_id = old[1] if old and old[0] == winner else str(uuid4())
        self.confirmed[key] = (winner, result_id)
        return Consensus(result_id, winner, stability,
                         sum(s.observation.confidence for s in matching)/len(matching), matching)
