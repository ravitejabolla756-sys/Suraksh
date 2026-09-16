"""Leakage-safe, deterministic dataset split utilities."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib

from .dataset import AnnotatedFrame


@dataclass(frozen=True, slots=True)
class DatasetSplits:
    train: tuple[AnnotatedFrame, ...]
    val: tuple[AnnotatedFrame, ...]
    test: tuple[AnnotatedFrame, ...]


def split_by_source(frames: tuple[AnnotatedFrame, ...], train=.7, val=.15) -> DatasetSplits:
    """Split whole source videos/camera sessions, never individual frames."""
    if not 0 < train < 1 or not 0 <= val < 1 or train + val >= 1:
        raise ValueError("split ratios must leave a positive test split")
    groups: dict[tuple[str, str], list[AnnotatedFrame]] = defaultdict(list)
    for frame in frames:
        groups[(frame.camera_id, str(frame.video_path))].append(frame)
    ordered = sorted(groups, key=lambda key: hashlib.sha256("|".join(key).encode()).hexdigest())
    total = len(frames)
    targets = (total * train, total * (train + val))
    buckets: list[list[AnnotatedFrame]] = [[], [], []]
    for key in ordered:
        current = len(buckets[0]) + len(buckets[1])
        bucket = 0 if len(buckets[0]) + len(groups[key]) <= targets[0] else 1 if current + len(groups[key]) <= targets[1] else 2
        buckets[bucket].extend(groups[key])
    return DatasetSplits(*(tuple(sorted(bucket, key=lambda f: (f.camera_id, str(f.video_path), f.frame_index))) for bucket in buckets))


def assert_no_source_leakage(splits: DatasetSplits) -> None:
    ownership: dict[tuple[str, str], str] = {}
    for name, frames in (("train", splits.train), ("val", splits.val), ("test", splits.test)):
        for frame in frames:
            key = (frame.camera_id, str(frame.video_path))
            prior = ownership.setdefault(key, name)
            if prior != name:
                raise ValueError(f"source session appears in {prior} and {name}: {key}")
