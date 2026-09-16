from pathlib import Path

import pytest

from app.perception.dataset import AnnotatedFrame
from app.perception.splits import DatasetSplits, assert_no_source_leakage, split_by_source


def frame(camera, video, index):
    return AnnotatedFrame(Path(video), camera, index, index / 30, 30, (), ())


def test_split_keeps_source_sessions_together():
    frames = tuple(frame("a", "a.mp4", index) for index in range(3)) + tuple(frame("b", "b.mp4", index) for index in range(3))
    splits = split_by_source(frames, train=.5, val=.25)
    assert_no_source_leakage(splits)
    assert len(splits.train) + len(splits.val) + len(splits.test) == 6


def test_split_rejects_source_leakage():
    item = frame("a", "a.mp4", 0)
    with pytest.raises(ValueError):
        assert_no_source_leakage(DatasetSplits((item,), (item,), ()))
