"""Tests for the pure hour-of-day usage-profile aggregation."""

from __future__ import annotations

from db_metrics.recommend.usage_profile import hour_of_day_profile, metric_points


def _pt(ts: str, **vals: float) -> dict:
    return {"timestamp": ts, **vals}


def test_profile_buckets_and_averages_by_hour():
    points = [
        _pt("2026-09-07T09:00:00+00:00", average=10.0),
        _pt("2026-09-08T09:30:00+00:00", average=20.0),  # same hour-of-day, next day
        _pt("2026-09-07T14:00:00+00:00", average=50.0),
    ]
    prof = hour_of_day_profile(points, "average")
    assert len(prof) == 24
    assert prof[9] == 15.0   # mean(10, 20)
    assert prof[14] == 50.0
    assert prof[0] is None   # no data for this hour


def test_profile_skips_points_missing_value_or_timestamp():
    points = [
        _pt("2026-09-07T09:00:00+00:00", average=10.0),
        _pt("2026-09-07T09:00:00+00:00"),                 # no value → skipped
        {"average": 99.0},                                # no timestamp → skipped
    ]
    assert hour_of_day_profile(points, "average")[9] == 10.0


def test_profile_reads_requested_value_key():
    points = [_pt("2026-09-07T09:00:00+00:00", average=10.0, maximum=80.0)]
    assert hour_of_day_profile(points, "maximum")[9] == 80.0


def test_profile_empty_when_no_points():
    assert hour_of_day_profile([], "average") == [None] * 24


def test_metric_points_returns_primary_series_for_first_matching_name():
    data = {
        "metrics": [
            {"name": "cpu_percent", "timeseries": [
                {"dimensions": {"x": "1"}, "points": [{"timestamp": "t", "average": 1.0}]},
                {"dimensions": {}, "points": [{"timestamp": "t", "average": 2.0}]},
            ]},
        ]
    }
    pts = metric_points(data, "cpu_percent")
    assert pts == [{"timestamp": "t", "average": 2.0}]  # no-dimension series preferred


def test_metric_points_skips_errored_and_supports_aliases():
    data = {
        "metrics": [
            {"name": "cpu_percent", "error": "throttled", "timeseries": []},
            {"name": "avg_cpu_percent", "timeseries": [
                {"dimensions": {}, "points": [{"timestamp": "t", "average": 5.0}]},
            ]},
        ]
    }
    assert metric_points(data, "cpu_percent", "avg_cpu_percent") == [
        {"timestamp": "t", "average": 5.0}
    ]


def test_metric_points_absent_returns_empty():
    assert metric_points({"metrics": []}, "cpu_percent") == []
