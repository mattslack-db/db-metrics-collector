from datetime import timedelta

from db_metrics.summarize import (
    available_granularities,
    choose_granularity,
    duration_str,
    summarize_points,
    summarize_values,
)
from types import SimpleNamespace


def test_summarize_values():
    assert summarize_values([]) is None
    assert summarize_values([None, None]) is None
    result = summarize_values([1.0, 3.0, 2.0])
    assert result == {"latest": 2.0, "min": 1.0, "max": 3.0, "avg": 2.0, "count": 3}


def test_summarize_points_per_field():
    points = [
        {"average": 10.0, "maximum": 12.0},
        {"average": 20.0, "maximum": 25.0},
    ]
    summary = summarize_points(points)
    assert summary["average"]["avg"] == 15.0
    assert summary["maximum"]["max"] == 25.0
    assert "minimum" not in summary


def test_choose_granularity():
    m1, m5, m30, h1, h6 = (timedelta(minutes=1), timedelta(minutes=5),
                           timedelta(minutes=30), timedelta(hours=1), timedelta(hours=6))
    # no availability info -> honor request
    assert choose_granularity(m5, []) == m5
    # request supported -> use it
    assert choose_granularity(m5, [m1, m5, m30]) == m5
    # request finer than all supported -> finest supported >= request
    assert choose_granularity(m5, [m30, h1, h6]) == m30
    # request coarser than all supported -> coarsest available
    assert choose_granularity(h6, [m1, m5]) == m5


def test_available_granularities():
    defn = SimpleNamespace(metric_availabilities=[
        SimpleNamespace(granularity=timedelta(minutes=1)),
        SimpleNamespace(granularity=timedelta(minutes=30)),
        SimpleNamespace(granularity=None),
    ])
    assert available_granularities(defn) == [timedelta(minutes=1), timedelta(minutes=30)]


def test_duration_str_minutes():
    assert duration_str(timedelta(minutes=1)) == "PT1M"
    assert duration_str(timedelta(minutes=5)) == "PT5M"
    assert duration_str(timedelta(minutes=30)) == "PT30M"


def test_duration_str_hours():
    assert duration_str(timedelta(hours=1)) == "PT1H"
    assert duration_str(timedelta(hours=6)) == "PT6H"


def test_duration_str_days():
    assert duration_str(timedelta(days=1)) == "P1D"
    assert duration_str(timedelta(days=7)) == "P7D"


def test_duration_str_seconds():
    assert duration_str(timedelta(seconds=90)) == "PT90S"
