"""Tests for render_text: Row dataclass, format_server, format_fleet."""

from __future__ import annotations

from db_metrics.recommend.load import Report
from db_metrics.recommend.skus import Capacity
from db_metrics.recommend.sizing import Recommendation
from db_metrics.recommend.cost import CostEstimate
from db_metrics.recommend.render_text import Row, format_server, format_fleet


def _row() -> Row:
    rep = Report("p.json", {"inventory": {}}, "prod-pg", "azure", "postgres-flexible")
    cap = Capacity(4, 16, "Standard_D4ds_v5", True)
    rec = Recommendation(
        5.5, 8.5, True, None, ("note one",),
        {"cpu_avg": 35.0, "cpu_peak": 70.0, "used_gb_avg": 9.0, "used_gb_peak": 13.0},
    )
    cost = CostEstimate(2000.0, 3000.0, 600.0, 0.35, True, 730, False)
    return Row(rep, cap, rec, cost)


# ---------------------------------------------------------------------------
# format_server
# ---------------------------------------------------------------------------


def test_format_server_contains_band_and_placeholder():
    out = format_server(_row())
    assert "prod-pg" in out
    assert "5.5" in out and "8.5" in out
    assert "placeholder" in out.lower()
    assert "note one" in out


def test_format_server_contains_display_name_and_cloud():
    out = format_server(_row())
    assert "azure" in out
    assert "postgres-flexible" in out


def test_format_server_contains_source_label():
    out = format_server(_row())
    assert "Standard_D4ds_v5" in out


def test_format_server_contains_cpu_and_mem_obs():
    out = format_server(_row())
    # CPU avg 35.0 and peak 70.0 should appear
    assert "35.0" in out or "35" in out
    assert "70.0" in out or "70" in out


def test_format_server_contains_cost_range():
    out = format_server(_row())
    # Cost range $2,000–$3,000/mo (formatter uses thousands-separator)
    assert "2,000" in out
    assert "3,000" in out


def test_format_server_insufficient_data_when_min_cu_none():
    rep = Report("q.json", {}, "test-server", "aws", "aurora")
    cap = Capacity(None, None, "unknown", False)
    rec = Recommendation(None, None, True, None, (), {
        "cpu_avg": None, "cpu_peak": None,
        "used_gb_avg": None, "used_gb_peak": None,
        "source_label": "unknown", "storage_used_gb": None,
        "connections_peak": None, "max_connections": None,
    })
    cost = CostEstimate(None, None, None, 0.35, True, 730, False)
    row = Row(rep, cap, rec, cost)
    out = format_server(row)
    assert "insufficient data" in out.lower()


def test_format_server_fixed_tier():
    rep = Report("r.json", {}, "big-server", "azure", "postgres-flexible")
    cap = Capacity(96, 384, "Standard_D96ds_v5", True)
    rec = Recommendation(None, None, False, 80.0, ("peak exceeds 64 CU dynamic range",), {
        "cpu_avg": 80.0, "cpu_peak": 95.0,
        "used_gb_avg": 200.0, "used_gb_peak": 300.0,
        "source_label": "Standard_D96ds_v5", "storage_used_gb": None,
        "connections_peak": None, "max_connections": None,
    })
    cost = CostEstimate(16352.0, 16352.0, None, 0.35, True, 730, True)
    row = Row(rep, cap, rec, cost)
    out = format_server(row)
    assert "no autoscaling" in out.lower() or "fixed" in out.lower()
    assert "80" in out


def test_format_server_none_cost_shows_na():
    rep = Report("s.json", {}, "no-cost-server", "azure", "postgres-flexible")
    cap = Capacity(4, 16, "Standard_D4ds_v5", True)
    rec = Recommendation(None, None, True, None, (), {
        "cpu_avg": None, "cpu_peak": None,
        "used_gb_avg": None, "used_gb_peak": None,
        "source_label": "Standard_D4ds_v5", "storage_used_gb": None,
        "connections_peak": None, "max_connections": None,
    })
    cost = CostEstimate(None, None, None, 0.35, True, 730, False)
    row = Row(rep, cap, rec, cost)
    out = format_server(row)
    assert "n/a" in out


# ---------------------------------------------------------------------------
# format_fleet
# ---------------------------------------------------------------------------


def test_format_fleet_totals_and_skips():
    out = format_fleet([_row()], skipped=[("bad.json", "missing keys: cloud")])
    assert "bad.json" in out
    assert "1" in out  # server count


def test_format_fleet_cu_totals():
    rows = [_row(), _row()]
    out = format_fleet(rows, skipped=[])
    # Two rows each with min=5.5, max=8.5 → sum min=11.0, sum max=17.0
    # _fmt_cu uses :g which strips trailing zeros, so 11.0 → "11"
    assert "11" in out
    assert "17" in out


def test_format_fleet_cost_totals():
    rows = [_row(), _row()]
    out = format_fleet(rows, skipped=[])
    # Two rows each with low=2000, high=3000 → 4000, 6000
    # formatter uses thousands-separator, so $4,000 and $6,000
    assert "4,000" in out
    assert "6,000" in out


def test_format_fleet_skipped_reason():
    out = format_fleet([_row()], skipped=[("bad.json", "missing keys: cloud")])
    assert "missing keys: cloud" in out


def test_format_fleet_unknown_sku_count():
    rep = Report("u.json", {}, "unknown-server", "azure", "postgres-flexible")
    cap = Capacity(None, None, "Custom_SKU", False)  # known=False
    rec = Recommendation(
        2.0, 4.0, True, None, (),
        {"cpu_avg": 10.0, "cpu_peak": 20.0, "used_gb_avg": None, "used_gb_peak": None,
         "source_label": "Custom_SKU", "storage_used_gb": None,
         "connections_peak": None, "max_connections": None},
    )
    cost = CostEstimate(506.1, 1012.2, None, 0.35, True, 730, False)
    row_known = _row()
    row_unknown = Row(rep, cap, rec, cost)
    out = format_fleet([row_known, row_unknown], skipped=[])
    # Should report 1 unknown-SKU server — pin the labeled count line
    assert "Unknown-SKU servers: 1" in out


def test_format_fleet_fixed_tier_count():
    rep = Report("f.json", {}, "fixed-server", "azure", "postgres-flexible")
    cap = Capacity(96, 384, "Standard_D96ds_v5", True)
    rec = Recommendation(None, None, False, 80.0, ("peak exceeds 64 CU",), {
        "cpu_avg": 80.0, "cpu_peak": 95.0,
        "used_gb_avg": 200.0, "used_gb_peak": 300.0,
        "source_label": "Standard_D96ds_v5", "storage_used_gb": None,
        "connections_peak": None, "max_connections": None,
    })
    cost = CostEstimate(16352.0, 16352.0, None, 0.35, True, 730, True)
    row_fixed = Row(rep, cap, rec, cost)
    out = format_fleet([_row(), row_fixed], skipped=[])
    # fixed tier row should be excluded from autoscaling CU sum — pin labeled count lines
    assert "Total servers      : 2" in out
    assert "Fixed-tier servers : 1" in out


def test_format_server_drivers_none_does_not_raise():
    """format_server must not crash when rec.drivers is None (defensive guard)."""
    rep = Report("n.json", {}, "null-drivers", "azure", "postgres-flexible")
    cap = Capacity(None, None, "unknown", False)
    rec = Recommendation(None, None, True, None, (), None)  # type: ignore[arg-type]
    cost = CostEstimate(None, None, None, 0.35, True, 730, False)
    row = Row(rep, cap, rec, cost)
    result = format_server(row)
    assert isinstance(result, str)
    assert "null-drivers" in result
