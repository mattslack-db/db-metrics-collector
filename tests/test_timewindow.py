from datetime import datetime, timedelta, timezone

import pytest

from db_metrics.timewindow import build_window, parse_iso8601_duration


@pytest.mark.parametrize("text,expected", [
    ("PT1M", timedelta(minutes=1)),
    ("PT5M", timedelta(minutes=5)),
    ("PT15M", timedelta(minutes=15)),
    ("PT1H", timedelta(hours=1)),
    ("P1D", timedelta(days=1)),
    ("PT30S", timedelta(seconds=30)),
    ("P1DT2H30M", timedelta(days=1, hours=2, minutes=30)),
])
def test_parse_iso8601_duration_valid(text, expected):
    assert parse_iso8601_duration(text) == expected


@pytest.mark.parametrize("text", ["", "1M", "PT", "P", "PT0M0S", "banana", "PTM"])
def test_parse_iso8601_duration_invalid(text):
    with pytest.raises(ValueError):
        parse_iso8601_duration(text)


def test_build_window_spans_hours():
    now = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    start, end = build_window(2, now=now)
    assert end == now
    assert start == now - timedelta(hours=2)


def test_build_window_adds_utc_to_naive_now():
    start, end = build_window(1, now=datetime(2026, 1, 2, 12, 0))
    assert end.tzinfo == timezone.utc
    assert (end - start) == timedelta(hours=1)


def test_build_window_rejects_non_positive():
    with pytest.raises(ValueError):
        build_window(0)
    with pytest.raises(ValueError):
        build_window(-3)
