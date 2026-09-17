from __future__ import annotations

import json
from datetime import datetime, timezone

from db_metrics import report
from db_metrics.models import Target
from db_metrics.providers.base import MetricSeries


def _sample_report():
    start = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    target = Target(name="s", cloud="azure", service="postgres-flexible")
    return report.build_report(
        target=target,
        resource_scope="/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg/providers/Microsoft.DBforPostgreSQL/flexibleServers/s",
        window=(start, end),
        interval="PT1M",
        inventory={
            "server": {"name": "s", "location": "eastus2", "version": "17",
                       "minor_version": "17.4", "state": "Ready",
                       "sku": {"name": "Standard_B2s", "tier": "Burstable"},
                       "storage": {"size_gb": 32, "iops": 120, "auto_grow": "Enabled"},
                       "high_availability": {"mode": "Disabled", "state": "NotEnabled"}},
            "parameters": [{"is_non_default": True}, {"is_non_default": False}],
            "parameters_non_default": [{"is_non_default": True}],
        },
        definitions=[],
        metrics=[
            {"name": "cpu_percent", "unit": "Percent",
             "timeseries": [{"dimensions": {}, "points": [],
                             "summary": {"average": {"latest": 12.5, "avg": 10.0, "max": 20.0}}}]},
            {"name": "broken", "error": "permission denied"},
        ],
    )


def test_build_report_requires_window():
    """window is mandatory: omitting it must fail clearly, not with an opaque
    'cannot unpack NoneType' from an unchecked default."""
    import pytest

    target = Target(name="s", cloud="azure", service="postgres-flexible")
    with pytest.raises(TypeError, match="window"):
        report.build_report(target=target, interval="PT1M")


def test_build_report_structure():
    result = _sample_report()
    assert result["window"]["interval"] == "PT1M"
    assert result["window"]["start"] == "2026-01-01T11:00:00+00:00"
    assert result["name"] == "s"
    assert result["cloud"] == "azure"


def test_write_json_roundtrip(tmp_path):
    path = tmp_path / "out.json"
    report.write_json(_sample_report(), str(path))
    loaded = json.loads(path.read_text())
    assert loaded["metrics"][0]["name"] == "cpu_percent"


def test_render_console_summary_contains_key_facts():
    text = report.render_console_summary(_sample_report())
    assert "Standard_B2s" in text
    assert "cpu_percent" in text
    assert "12.50" in text          # latest value formatted
    assert "1 non-default" in text
    assert "ERROR" in text          # errored metric surfaced


# ---------------------------------------------------------------------------
# _serialize_metric fallback (line 19): plain dict input
# ---------------------------------------------------------------------------


def test_serialize_metric_with_plain_dict():
    """_serialize_metric falls back to dict(m) for non-dataclass input."""
    payload = {"name": "cpu", "unit": "Percent", "timeseries": []}
    result = report._serialize_metric(payload)
    assert result == payload
    assert result is not payload  # dict() makes a copy


# ---------------------------------------------------------------------------
# _json_default: datetime serialization (lines 89-91)
# ---------------------------------------------------------------------------


def test_json_default_serializes_datetime():
    """_json_default converts datetime objects to ISO 8601 strings."""
    dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert report._json_default(dt) == "2026-01-01T00:00:00+00:00"


def test_json_default_falls_back_to_str_for_unknown_type():
    """_json_default converts unknown types via str()."""
    result = report._json_default(42)
    assert result == "42"


# ---------------------------------------------------------------------------
# _fmt: non-float, non-None branch (line 105)
# ---------------------------------------------------------------------------


def test_fmt_with_string_value():
    """_fmt returns str(value) for non-None, non-float input."""
    assert report._fmt("Ready") == "Ready"
    assert report._fmt(5) == "5"


# ---------------------------------------------------------------------------
# New-path tests (Task 8)
# ---------------------------------------------------------------------------

def _make_target() -> Target:
    return Target(name="prod", cloud="azure", service="sql-database")


def _make_new_path_report() -> dict:
    start = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    target = _make_target()
    metrics = [
        MetricSeries(
            name="cpu_percent",
            unit="Percent",
            granularity="PT1M",
            timeseries=[
                {
                    "dimensions": {},
                    "points": [],
                    "summary": {"average": {"latest": 5.0, "avg": 4.0, "max": 8.0}},
                }
            ],
        ),
        MetricSeries(name="x", unit=None, granularity=None, timeseries=[], error="boom"),
    ]
    return report.build_report(
        target=target,
        resource_scope="/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Sql/servers/s/databases/db",
        window=(start, end),
        interval="PT1M",
        inventory={"server": {"name": "s", "location": "eastus2", "version": "12", "state": "Online"}},
        definitions=[],
        metrics=metrics,
    )


def test_build_report_new_path_fields():
    """New path emits cloud/service/name/resource_scope and serialises MetricSeries."""
    result = _make_new_path_report()
    assert result["cloud"] == "azure"
    assert result["service"] == "sql-database"
    assert result["name"] == "prod"
    assert "databases/db" in result["resource_scope"]
    # legacy fields should NOT appear in new path
    assert "resource_id" not in result
    assert "engine" not in result


def test_build_report_new_path_metrics_serialised():
    """MetricSeries objects are converted to plain dicts in new path."""
    result = _make_new_path_report()
    m0 = result["metrics"][0]
    m1 = result["metrics"][1]
    assert isinstance(m0, dict)
    assert m0["name"] == "cpu_percent"
    assert isinstance(m1, dict)
    assert m1["error"] == "boom"


def test_build_summary_status_logic():
    """build_summary correctly classifies ok / partial / error targets."""
    ok_report = {
        "name": "target-ok",
        "cloud": "azure",
        "service": "sql-database",
        "metrics": [
            {"name": "cpu_percent", "unit": "Percent", "timeseries": []},
        ],
    }
    partial_report = {
        "name": "target-partial",
        "cloud": "gcp",
        "service": "cloud-sql",
        "metrics": [
            {"name": "cpu", "unit": "Percent", "timeseries": []},
            {"name": "mem", "error": "timeout"},
        ],
    }
    error_report = {
        "name": "target-error",
        "cloud": "aws",
        "service": "rds",
        "error": "Auth failed",
        "metrics": [],
    }

    summary = report.build_summary([ok_report, partial_report, error_report])

    by_name = {t["name"]: t for t in summary["targets"]}

    assert by_name["target-ok"]["status"] == "ok"
    assert by_name["target-ok"]["metric_count"] == 1
    assert by_name["target-ok"]["error_count"] == 0

    assert by_name["target-partial"]["status"] == "partial"
    assert by_name["target-partial"]["metric_count"] == 2
    assert by_name["target-partial"]["error_count"] == 1

    assert by_name["target-error"]["status"] == "error"
    assert by_name["target-error"]["metric_count"] == 0
    assert by_name["target-error"]["error_count"] == 0

    assert summary["target_count"] == 3
    assert summary["error_target_count"] == 2  # partial + error both != ok


def test_render_summary_table_contains_names():
    """render_summary_table lists every target name."""
    ok_report = {"name": "alpha", "cloud": "azure", "service": "sql-db", "metrics": []}
    err_report = {"name": "beta", "cloud": "gcp", "service": "cloud-sql", "error": "fail", "metrics": []}
    summary = report.build_summary([ok_report, err_report])
    table = report.render_summary_table(summary)
    assert "alpha" in table
    assert "beta" in table
    assert "ok" in table
    assert "error" in table


def test_render_console_summary_new_path_no_keyerror():
    """render_console_summary on a new-path sql-database report does not raise
    and includes the cloud·service header (not engine_label)."""
    result = _make_new_path_report()
    text = report.render_console_summary(result)
    assert "azure" in text
    assert "sql-database" in text
    # Must not raise even though sku/storage/high_availability are absent
