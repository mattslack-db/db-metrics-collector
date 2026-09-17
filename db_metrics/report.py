"""Report assembly, console rendering, and JSON output."""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from typing import Any


def _serialize_metric(m: Any) -> dict:
    """Convert a metric entry to a plain dict.

    Accepts either a MetricSeries dataclass (or any dataclass) or a pre-formed
    dict and returns a JSON-serializable dict.
    """
    if dataclasses.is_dataclass(m) and not isinstance(m, type):
        return dataclasses.asdict(m)
    return dict(m)


def build_report(
    *,
    target: Any,
    window: tuple[datetime, datetime],
    resource_scope: str | None = None,
    interval: str = "",
    inventory: dict | None = None,
    definitions: list | None = None,
    metrics: list | None = None,
) -> dict:
    """Assemble the full JSON-serializable report.

    Emits ``collected_at``, ``name``, ``cloud``, ``service``,
    ``resource_scope``, ``window``, ``inventory``, ``metric_definitions``,
    ``metrics``.  Each metric entry is serialized to a plain dict via
    :func:`_serialize_metric`.
    """
    inventory = inventory or {}
    definitions = definitions or []
    metrics = metrics or []

    start, end = window
    window_dict = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "interval": interval,
    }

    serialized_metrics = [_serialize_metric(m) for m in metrics]
    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "name": target.name,
        "cloud": target.cloud,
        "service": target.service,
        "resource_scope": resource_scope,
        "window": window_dict,
        "inventory": inventory,
        "metric_definitions": definitions,
        "metrics": serialized_metrics,
    }


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def write_json(report: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, default=_json_default)
        handle.write("\n")


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def render_console_summary(report: dict) -> str:
    """Return a human-readable summary of inventory + per-metric stats."""
    lines: list[str] = []
    server = report["inventory"].get("server", {})

    # Tolerate new-path reports: derive header from cloud·service when engine_label absent.
    label = report.get("engine_label") or f"{report.get('cloud', '?')} · {report.get('service', '?')}"

    # Guard optional flexible-server fields.
    sku = server.get("sku") or {}
    storage = server.get("storage") or {}
    ha = server.get("high_availability") or {}

    lines.append("=" * 70)
    lines.append(f"  {label} — {server.get('name')}")
    lines.append("=" * 70)
    lines.append(f"  Location   : {server.get('location')}")
    lines.append(f"  Version    : {server.get('version')} (minor {server.get('minor_version')})")
    lines.append(f"  SKU / tier : {sku.get('name')} / {sku.get('tier')}")
    lines.append(
        f"  Storage    : {storage.get('size_gb')} GB, {storage.get('iops')} IOPS, autogrow={storage.get('auto_grow')}"
    )
    lines.append(f"  HA         : mode={ha.get('mode')} state={ha.get('state')}")
    lines.append(f"  State      : {server.get('state')}")
    non_default = report["inventory"].get("parameters_non_default") or []
    parameters = report["inventory"].get("parameters") or []
    lines.append(f"  Parameters : {len(parameters)} total, {len(non_default)} non-default")
    lines.append("")

    win = report["window"]
    lines.append(f"  Metrics window: {win['start']} → {win['end']} @ {win['interval']}")
    lines.append("-" * 70)
    lines.append(f"  {'METRIC':<42}{'UNIT':<12}{'LATEST':>7} {'AVG':>7} {'MAX':>7}")
    lines.append("-" * 70)

    for metric in sorted(report.get("metrics", []), key=lambda m: m.get("name") or ""):
        name = metric.get("name") or "?"
        if "error" in metric and metric["error"]:
            lines.append(f"  {name:<42}{'ERROR':<12}{str(metric['error'])[:20]}")
            continue
        unit = metric.get("unit") or ""
        series = metric.get("timeseries") or []
        summary = (series[0].get("summary") if series else {}) or {}
        primary = (
            summary.get("average")
            or summary.get("total")
            or summary.get("maximum")
            or summary.get("count")
            or summary.get("minimum")
            or {}
        )
        suffix = f"  (+{len(series) - 1} dim series)" if len(series) > 1 else ""
        lines.append(
            f"  {name:<42}{unit:<12}"
            f"{_fmt(primary.get('latest')):>7} {_fmt(primary.get('avg')):>7} {_fmt(primary.get('max')):>7}{suffix}"
        )

    lines.append("=" * 70)
    return "\n".join(lines)


def build_summary(reports: list[dict]) -> dict:
    """Produce a multi-target summary dict.

    Each target entry contains:
    - ``name`` — from report (may be None for legacy reports)
    - ``cloud``, ``service`` — from report (fall back to "?")
    - ``metric_count`` — number of entries in ``report["metrics"]``
    - ``error_count`` — metrics entries with a truthy "error" key
    - ``status`` — "error" | "partial" | "ok"
      - "error"   : report has a truthy top-level "error" key
      - "partial" : at least one metric entry has a truthy "error" key
      - "ok"      : no errors anywhere
    """
    targets = []
    for rep in reports:
        metrics = rep.get("metrics") or []
        metric_count = len(metrics)
        error_count = sum(1 for m in metrics if m.get("error"))

        if rep.get("error"):
            status = "error"
        elif error_count > 0:
            status = "partial"
        else:
            status = "ok"

        targets.append(
            {
                "name": rep.get("name"),
                "cloud": rep.get("cloud") or "?",
                "service": rep.get("service") or "?",
                "metric_count": metric_count,
                "error_count": error_count,
                "status": status,
            }
        )

    error_target_count = sum(1 for t in targets if t["status"] != "ok")
    return {
        "targets": targets,
        "target_count": len(targets),
        "error_target_count": error_target_count,
    }


def render_summary_table(summary: dict) -> str:
    """Return a human-readable table of per-target summary rows."""
    col_name = 30
    col_cloud = 8
    col_service = 16
    col_metrics = 8
    col_errors = 7
    col_status = 8

    header = (
        f"  {'NAME':<{col_name}}"
        f"{'CLOUD':<{col_cloud}}"
        f"{'SERVICE':<{col_service}}"
        f"{'METRICS':>{col_metrics}}"
        f"{'ERRORS':>{col_errors}}"
        f"  {'STATUS':<{col_status}}"
    )
    sep = "-" * len(header)

    lines: list[str] = ["", sep, header, sep]
    for t in summary.get("targets", []):
        name = t.get("name") or "(unnamed)"
        line = (
            f"  {name:<{col_name}}"
            f"{t.get('cloud', '?'):<{col_cloud}}"
            f"{t.get('service', '?'):<{col_service}}"
            f"{t.get('metric_count', 0):>{col_metrics}}"
            f"{t.get('error_count', 0):>{col_errors}}"
            f"  {t.get('status', '?'):<{col_status}}"
        )
        lines.append(line)

    lines.append(sep)
    lines.append(
        f"  Targets: {summary.get('target_count', 0)}  |  "
        f"Not OK: {summary.get('error_target_count', 0)}"
    )
    lines.append("")
    return "\n".join(lines)
