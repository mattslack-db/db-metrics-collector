# db_metrics/recommend/load.py
"""Discover, parse, and validate collector report JSON. Input boundary."""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass

_REQUIRED_KEYS = ("cloud", "service", "inventory", "metrics", "window")


class ReportError(Exception):
    """A report file could not be read or is not a valid collector report."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")


@dataclass(frozen=True)
class Report:
    path: str
    data: dict
    display_name: str
    cloud: str
    service: str


def discover_reports(paths: list[str]) -> list[str]:
    """Expand paths: files kept as-is; dirs globbed for metrics_*.json."""
    found: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            found.extend(glob.glob(os.path.join(p, "metrics_*.json")))
        else:
            found.append(p)
    return sorted(set(found))


def load_report(path: str) -> Report:
    """Parse and validate a single report file, or raise ReportError."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(path, f"could not read JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ReportError(path, "top-level JSON is not an object")
    missing = [k for k in _REQUIRED_KEYS if k not in data]
    if missing:
        raise ReportError(path, f"missing keys: {', '.join(missing)}")
    if not isinstance(data["inventory"], dict):
        raise ReportError(path, "inventory must be a JSON object (dict)")
    if not isinstance(data["metrics"], list):
        raise ReportError(path, "metrics must be a JSON array (list)")
    server = (data.get("inventory") or {}).get("server") or {}
    name = data.get("name") or server.get("name") or data.get("resource_scope") or os.path.basename(path)
    return Report(
        path=path,
        data=data,
        display_name=str(name),
        cloud=str(data["cloud"]),
        service=str(data["service"]),
    )
