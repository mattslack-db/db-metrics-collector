"""Pure time-window and ISO-8601 duration helpers (no SDK dependencies)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

# Common Azure Monitor granularities, for validation / help text.
DEFAULT_INTERVAL = "PT1M"

_ISO_DURATION_RE = re.compile(
    r"^P"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
    r")?$"
)


def parse_iso8601_duration(text: str) -> timedelta:
    """Parse a restricted ISO-8601 duration (e.g. 'PT1M', 'PT5M', 'PT1H', 'P1D').

    Supports days/hours/minutes/seconds. Raises ValueError on malformed input
    or a zero-length duration.
    """
    match = _ISO_DURATION_RE.match(text.strip())
    if not match:
        raise ValueError(f"Invalid ISO-8601 duration: {text!r}")
    parts = {k: int(v) for k, v in match.groupdict().items() if v}
    delta = timedelta(
        days=parts.get("days", 0),
        hours=parts.get("hours", 0),
        minutes=parts.get("minutes", 0),
        seconds=parts.get("seconds", 0),
    )
    if delta <= timedelta(0):
        raise ValueError(f"Duration must be non-zero: {text!r}")
    return delta


def build_window(hours: float, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return a (start, end) UTC window ending 'now' and spanning 'hours'.

    'now' is injectable for deterministic tests.
    """
    if hours <= 0:
        raise ValueError(f"hours must be positive, got {hours}")
    end = now or datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return end - timedelta(hours=hours), end
