"""Pure summarization helpers and granularity utilities.

These functions are provider-agnostic: they operate on plain Python data
structures and require no SDK or network access.
"""

from __future__ import annotations

from datetime import timedelta

# Value fields present on a provider MetricValue (e.g. Azure Monitor).
_VALUE_FIELDS = ("average", "minimum", "maximum", "total", "count")


def duration_str(delta: timedelta) -> str:
    """Render a timedelta as an ISO-8601 duration (best effort)."""
    seconds = int(delta.total_seconds())
    if seconds % 86400 == 0:
        return f"P{seconds // 86400}D"
    if seconds % 3600 == 0:
        return f"PT{seconds // 3600}H"
    if seconds % 60 == 0:
        return f"PT{seconds // 60}M"
    return f"PT{seconds}S"


def summarize_values(values: list[float]) -> dict | None:
    """Return latest/min/max/avg/count for a list of numeric values."""
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return {
        "latest": nums[-1],
        "min": min(nums),
        "max": max(nums),
        "avg": round(sum(nums) / len(nums), 4),
        "count": len(nums),
    }


def summarize_points(points: list[dict]) -> dict:
    """Summarize a list of per-timestamp value dicts, per value field."""
    summary: dict[str, dict] = {}
    for field in _VALUE_FIELDS:
        column = [p[field] for p in points if p.get(field) is not None]
        if column:
            field_summary = summarize_values(column)
            if field_summary:
                summary[field] = field_summary
    return summary


def available_granularities(definition: object) -> list[timedelta]:
    """Timedeltas a metric can be queried at, from its metric_availabilities."""
    grains = []
    for avail in (getattr(definition, "metric_availabilities", None) or []):
        gran = getattr(avail, "granularity", None)
        if isinstance(gran, timedelta):
            grains.append(gran)
    return grains


def choose_granularity(requested: timedelta, available: list[timedelta]) -> timedelta:
    """Pick the finest supported grain that still honors the request.

    - No availability info -> use the request as-is.
    - Request supported -> use it.
    - Otherwise -> smallest grain >= request (finest that Azure accepts), or the
      coarsest available if the request is finer than everything on offer.
    """
    if not available:
        return requested
    if requested in available:
        return requested
    not_finer = sorted(g for g in available if g >= requested)
    return not_finer[0] if not_finer else max(available)
