import pytest

from app.perception.counting import Direction, LineCrossingCounter, TrackPoint, count_error


def p(track, x, t, cls="person"):
    return TrackPoint(track, cls, x, 0, t)


def test_line_crossing_uses_track_trajectory_and_debounce():
    counter = LineCrossingCounter(((0, -10), (0, 10)), deadband=2, debounce_seconds=1)
    assert counter.update(p(1, -5, 0)) is None
    assert counter.update(p(1, -1, .1)) is None
    assert counter.update(p(1, 3, .2)) == Direction.A_TO_B
    assert counter.update(p(1, -3, .3)) is None
    assert counter.update(p(1, 3, 2)) == Direction.A_TO_B
    assert counter.counts[Direction.A_TO_B] == 2


def test_boundary_and_class_do_not_create_detection_based_duplicates():
    counter = LineCrossingCounter(((0, -10), (0, 10)))
    assert counter.update(p(7, 0, 0)) is None
    assert counter.update(p(7, 5, 2, "car")) is None
    assert counter.update(p(7, 8, 3, "car")) is None


def test_reactivated_track_keeps_identity_and_can_cross_after_debounce():
    counter = LineCrossingCounter(((0, -10), (0, 10)), debounce_seconds=0)
    counter.update(p(4, -5, 0))
    assert counter.update(p(4, 5, 1)) == Direction.A_TO_B
    assert counter.update(p(4, -5, 2)) == Direction.B_TO_A


def test_count_error_is_explicit():
    assert count_error(8, 6).absolute_error == 2
