"""Tests for the self-contained HTML report renderer."""

from __future__ import annotations

import builtins

import pytest

from db_metrics.recommend.render_text import Row
from db_metrics.recommend.load import Report, load_report
from db_metrics.recommend.skus import Capacity, capacity_for
from db_metrics.recommend.sizing import Recommendation, recommend
from db_metrics.recommend.normalize import canonical_signals
from db_metrics.recommend.cost import CostEstimate, estimate, rate_for
from db_metrics.recommend import render_html as rh


def _row() -> Row:
    rep = Report("p.json", {"metrics": [], "inventory": {}}, "prod-pg", "azure", "postgres-flexible")
    return Row(
        rep,
        Capacity(4, 16, "Standard_D4ds_v5", True),
        Recommendation(5.5, 8.5, True, None, (), {"cpu_avg": 35.0, "cpu_peak": 70.0}),
        CostEstimate(2000.0, 3000.0, 600.0, 0.35, True, 730, False),
    )


def test_renders_self_contained_html(tmp_path: pytest.TempPathFactory) -> None:
    pytest.importorskip("matplotlib")
    out = tmp_path / "r.html"
    rh.render_html([_row()], [], str(out))
    html = out.read_text()
    assert "prod-pg" in html
    assert "data:image/png;base64," in html
    assert "http://" not in html and "https://" not in html  # self-contained


def test_iops_signals_produce_chart_without_error(tmp_path: pytest.TempPathFactory, fx) -> None:
    """IOPS from a real report flows through recommend() into drivers and renders in the chart."""
    pytest.importorskip("matplotlib")
    import os
    report = load_report(fx("azure_pg.json"))
    cap = capacity_for(report.cloud, report.service, report.data.get("inventory") or {})
    signals = canonical_signals(report)
    rec = recommend(cap, signals)
    # azure_pg.json carries iops data — verify it reached drivers via the real path
    assert rec.drivers.get("iops_peak") is not None, "iops_peak missing from drivers"
    rate, is_ph = rate_for(report.cloud, None)
    cost = estimate(rec, rate, is_ph)
    row = Row(report, cap, rec, cost)
    out = tmp_path / "iops.html"
    rh.render_html([row], [], str(out))
    content = out.read_text()
    assert report.display_name in content
    assert "data:image/png;base64," in content


def test_workload_ylim_clamps_only_for_all_percent_series() -> None:
    """A 0-115% axis is valid only when every plotted series is a percentage."""
    assert rh._workload_ylim(["CPU %", "Mem %", "Conns %"]) == (0.0, 115.0)


def test_workload_ylim_autoscales_when_absolute_series_present() -> None:
    """IOPS and raw 'Mem (GB)' are absolute; clamping to 115 would clip them."""
    assert rh._workload_ylim(["CPU %", "IOPS"]) is None
    assert rh._workload_ylim(["Mem (GB)"]) is None
    assert rh._workload_ylim([]) is None


def _row_with_points() -> Row:
    """A Row whose report carries raw hourly CPU/memory points."""
    metrics = [
        {"name": "cpu_percent", "timeseries": [{"dimensions": {}, "points": [
            {"timestamp": "2026-09-07T09:00:00+00:00", "average": 10.0, "maximum": 40.0},
            {"timestamp": "2026-09-07T14:00:00+00:00", "average": 30.0, "maximum": 95.0},
        ]}]},
        {"name": "memory_percent", "timeseries": [{"dimensions": {}, "points": [
            {"timestamp": "2026-09-07T09:00:00+00:00", "average": 55.0},
            {"timestamp": "2026-09-07T14:00:00+00:00", "average": 60.0},
        ]}]},
    ]
    rep = Report("p.json", {"metrics": metrics, "inventory": {}}, "prod-pg", "azure", "postgres-flexible")
    return Row(
        rep,
        Capacity(4, 16, "Standard_D4ds_v5", True),
        Recommendation(5.5, 8.5, True, None, (), {"cpu_avg": 20.0, "cpu_peak": 95.0}),
        CostEstimate(2000.0, 3000.0, 600.0, 0.35, True, 730, False),
    )


def test_usage_pattern_chart_returns_bytes_when_points_present() -> None:
    pytest.importorskip("matplotlib")
    png = rh._usage_pattern_chart(_row_with_points())
    assert png is not None and png[:8] == b"\x89PNG\r\n\x1a\n"


def test_usage_pattern_chart_none_when_no_points() -> None:
    """Reports with only summary data (no raw points) produce no usage chart."""
    pytest.importorskip("matplotlib")
    assert rh._usage_pattern_chart(_row()) is None


def test_usage_pattern_chart_rendered_into_report(tmp_path: pytest.TempPathFactory) -> None:
    pytest.importorskip("matplotlib")
    # With raw points: workload + usage-pattern charts. Without points: workload only.
    with_points = tmp_path / "with.html"
    without_points = tmp_path / "without.html"
    rh.render_html([_row_with_points()], [], str(with_points))
    rh.render_html([_row()], [], str(without_points))
    n_with = with_points.read_text().count("data:image/png;base64,")
    n_without = without_points.read_text().count("data:image/png;base64,")
    assert n_with == n_without + 1  # exactly one extra chart: the usage pattern


def test_missing_matplotlib_raises_dependency_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *a: object, **k: object) -> object:
        if name.startswith("matplotlib"):
            raise ImportError("no matplotlib")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(rh.ReportDependencyError):
        rh.render_html([_row()], [], str(tmp_path / "r.html"))
