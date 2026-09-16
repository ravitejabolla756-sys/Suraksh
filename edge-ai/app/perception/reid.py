"""Bounded, anonymous appearance features for short-term track association."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol

import numpy as np


class AppearanceEncoder(Protocol):
    def encode(self, crop: np.ndarray) -> np.ndarray:
        """Return a normalized, non-identifying short-term appearance vector."""


class ColorHistogramEncoder:
    """Small CPU baseline; deliberately not a face or biometric encoder."""

    def encode(self, crop: np.ndarray) -> np.ndarray:
        if crop.size == 0:
            raise ValueError("cannot encode an empty crop")
        hist = [np.histogram(crop[:, :, channel], bins=16, range=(0, 256))[0]
                for channel in range(min(3, crop.shape[2]))]
        vector = np.concatenate(hist).astype(np.float32)
        norm = float(np.linalg.norm(vector))
        return vector / max(norm, 1e-12)


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    if left.shape != right.shape:
        raise ValueError("appearance embeddings must have the same shape")
    return float(np.dot(left, right) / max(np.linalg.norm(left) * np.linalg.norm(right), 1e-12))


@dataclass(frozen=True, slots=True)
class ReIDConfig:
    reid_enabled: bool = False
    reid_weight: float = 0.0
    reid_distance_threshold: float = 0.3
    embedding_cache_size: int = 128

    def __post_init__(self) -> None:
        if not 0 <= self.reid_weight <= 1 or not 0 <= self.reid_distance_threshold <= 2:
            raise ValueError("invalid ReID thresholds")
        if self.reid_enabled and self.reid_weight <= 0:
            raise ValueError("reid_weight must be positive when ReID is enabled")
        if self.embedding_cache_size < 1:
            raise ValueError("embedding_cache_size must be positive")


class EmbeddingCache:
    """Camera-local bounded cache; keys are anonymous track IDs only."""

    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("cache capacity must be positive")
        self._items: OrderedDict[int, np.ndarray] = OrderedDict()
        self.capacity = capacity

    def put(self, track_id: int, embedding: np.ndarray) -> None:
        self._items.pop(track_id, None)
        self._items[track_id] = np.asarray(embedding, dtype=np.float32).copy()
        while len(self._items) > self.capacity:
            self._items.popitem(last=False)

    def get(self, track_id: int) -> np.ndarray | None:
        item = self._items.get(track_id)
        if item is not None:
            self._items.move_to_end(track_id)
        return item

    def __len__(self) -> int:
        return len(self._items)
