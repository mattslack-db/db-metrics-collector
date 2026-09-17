"""Aggregate raw metric timeseries into an hour-of-day usage profile. Pure.

The collector stores per-point samples (timestamp + average/minimum/maximum).
These helpers fold those points into a 24-slot diurnal profile so the report
can show the typical daily usage pattern, independent of how many days were
collected.
"""

from __future__ import annotations

from datetime import datetime

HOURS_PER_DAY = 24


def _hour_of(timestamp: object) -> int | None:
    """Return the hour-of-day (0–23) for an ISO-8601 timestamp, or None."""
    try:
        return datetime.fromisoformat(str(timestamp)).hour
    except (ValueError, TypeError):
        return None


def hour_of_day_profile(points: list[dict], value_key: str) -> list[float | None]:
    """Fold *points* into a 24-element list of mean ``point[value_key]`` by hour.

    Hours with no data are ``None``. Points missing a timestamp or the requested
    value key are skipped (the collector omits a value field when it is null).
    """
    sums = [0.0] * HOURS_PER_DAY
    counts = [0] * HOURS_PER_DAY
    for point in points:
        value = point.get(value_key)
        hour = _hour_of(point.get("timestamp"))
        if value is None or hour is None:
            continue
        sums[hour] += float(value)
        counts[hour] += 1
    return [(sums[h] / counts[h]) if counts[h] else None for h in range(HOURS_PER_DAY)]


def metric_points(report_data: dict, *names: str) -> list[dict]:
    """Return the raw points of the first matching, non-errored metric.

    Accepts several candidate names (as :func:`normalize._summary` does) and
    prefers the primary (no-dimension) timeseries.
    """
    wanted = set(names)
    for metric in report_data.get("metrics", []):
        if metric.get("name") not in wanted or metric.get("error"):
            continue
        series = metric.get("timeseries") or []
        if not series:
            return []
        primary = next((s for s in series if not s.get("dimensions")), series[0])
        return primary.get("points") or []
    return []
