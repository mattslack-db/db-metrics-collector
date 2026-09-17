"""Tests for db_metrics.recommend.cli — CLI orchestration and exit codes."""

from __future__ import annotations

import json
import os
import shutil

from db_metrics.recommend.cli import main

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _copy(tmp_path: object, *names: str) -> str:
    """Copy named fixtures into tmp_path with a metrics_<n>_<name> prefix."""
    for i, n in enumerate(names):
        shutil.copy(os.path.join(FIX, n), tmp_path / f"metrics_{i}_{n}")  # type: ignore[operator]
    return str(tmp_path)


# ---------------------------------------------------------------------------
# Exit code tests
# ---------------------------------------------------------------------------


def test_all_valid_exit_zero(tmp_path, capsys):
    """All valid reports → exit 0 and both server names appear in output."""
    d = _copy(tmp_path, "azure_pg.json", "aws_rds.json")
    rc = main([d])
    out = capsys.readouterr().out
    assert rc == 0
    assert "prod-pg" in out and "prod-rds" in out


def test_partial_when_one_invalid(tmp_path, capsys):
    """One valid + one invalid → exit 1; invalid filename shown in output."""
    d = _copy(tmp_path, "azure_pg.json", "invalid.json")
    rc = main([d])
    assert rc == 1
    assert "invalid" in capsys.readouterr().out.lower()


def test_no_valid_reports_exit_two(tmp_path):
    """Only invalid reports → exit 2."""
    d = _copy(tmp_path, "invalid.json")
    assert main([d]) == 2


# ---------------------------------------------------------------------------
# HTML report test
# ---------------------------------------------------------------------------


def test_writes_html_report(tmp_path):
    """--report writes an HTML file containing an embedded PNG image."""
    import pytest

    pytest.importorskip("matplotlib")
    d = _copy(tmp_path, "azure_pg.json")
    out_html = tmp_path / "report.html"
    rc = main([d, "--report", str(out_html)])
    assert rc == 0
    assert out_html.exists()
    assert "data:image/png;base64," in out_html.read_text()


# ---------------------------------------------------------------------------
# Rate override test
# ---------------------------------------------------------------------------


def test_cu_rate_override_no_placeholder(tmp_path, capsys):
    """--cu-rate override → 'placeholder' does not appear in output."""
    d = _copy(tmp_path, "azure_pg.json")
    main([d, "--cu-rate", "0.5"])
    assert "placeholder" not in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# I1: malformed-but-key-present reports are skipped, not crash the run
# ---------------------------------------------------------------------------


def test_malformed_metrics_skipped_good_server_still_printed(tmp_path, capsys):
    """Good report + malformed (metrics=string) → exit 1, good server printed, bad file listed."""
    # Create the good fixture copy
    shutil.copy(os.path.join(FIX, "azure_pg.json"), tmp_path / "metrics_0_azure_pg.json")
    # Create the malformed fixture inline
    bad = {
        "cloud": "azure",
        "service": "postgres-flexible",
        "inventory": {},
        "metrics": "oops",
        "window": {},
    }
    (tmp_path / "metrics_1_malformed.json").write_text(json.dumps(bad))
    rc = main([str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "prod-pg" in out
    assert "metrics_1_malformed.json" in out


def test_malformed_inventory_skipped_good_server_still_printed(tmp_path, capsys):
    """Good report + malformed (inventory=list) → exit 1, good server printed, bad file listed."""
    shutil.copy(os.path.join(FIX, "azure_pg.json"), tmp_path / "metrics_0_azure_pg.json")
    bad = {
        "cloud": "azure",
        "service": "postgres-flexible",
        "inventory": [1, 2],
        "metrics": [],
        "window": {},
    }
    (tmp_path / "metrics_1_inv_list.json").write_text(json.dumps(bad))
    rc = main([str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "prod-pg" in out
    assert "metrics_1_inv_list.json" in out


# ---------------------------------------------------------------------------
# Numeric-flag boundary validation (reject nonsensical values before math)
# ---------------------------------------------------------------------------


def test_negative_headroom_rejected(tmp_path, capsys):
    d = _copy(tmp_path, "azure_pg.json")
    rc = main([d, "--headroom", "-1"])
    assert rc == 2
    assert "headroom" in capsys.readouterr().err.lower()


def test_negative_cu_rate_rejected(tmp_path, capsys):
    d = _copy(tmp_path, "azure_pg.json")
    rc = main([d, "--cu-rate", "-0.5"])
    assert rc == 2
    assert "cu-rate" in capsys.readouterr().err.lower()


def test_zero_hours_per_month_rejected(tmp_path, capsys):
    d = _copy(tmp_path, "azure_pg.json")
    rc = main([d, "--hours-per-month", "0"])
    assert rc == 2
    assert "hours-per-month" in capsys.readouterr().err.lower()


def test_active_fraction_out_of_range_rejected(tmp_path, capsys):
    d = _copy(tmp_path, "azure_pg.json")
    rc = main([d, "--active-fraction", "1.5"])
    assert rc == 2
    assert "active-fraction" in capsys.readouterr().err.lower()


def test_valid_boundaries_accepted(tmp_path):
    """Zero headroom and a zero active-fraction are legitimate."""
    d = _copy(tmp_path, "azure_pg.json")
    assert main([d, "--headroom", "0", "--active-fraction", "0"]) == 0


def test_processing_error_skipped_not_fatal(tmp_path, capsys):
    """A report that passes load validation but blows up during normalize/sizing
    (e.g. metrics entries are lists, not dicts) must be skipped, not crash the run."""
    shutil.copy(os.path.join(FIX, "azure_pg.json"), tmp_path / "metrics_0_azure_pg.json")
    bad = {
        "cloud": "azure",
        "service": "postgres-flexible",
        "inventory": {},
        "metrics": [["not", "a", "dict"]],  # list is a valid 'metrics', entries are not
        "window": {},
    }
    (tmp_path / "metrics_1_badentries.json").write_text(json.dumps(bad))
    rc = main([str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "prod-pg" in out                      # good server still processed
    assert "metrics_1_badentries.json" in out    # bad one reported as skipped


# ---------------------------------------------------------------------------
# M4: no spurious HTML when all reports are invalid
# ---------------------------------------------------------------------------


def test_no_html_written_when_all_invalid(tmp_path):
    """With --report, an all-invalid run (exit 2) must NOT write the HTML file."""
    pytest = __import__("pytest")
    pytest.importorskip("matplotlib")
    _copy(tmp_path, "invalid.json")
    out_html = tmp_path / "should_not_exist.html"
    rc = main([str(tmp_path), "--report", str(out_html)])
    assert rc == 2
    assert not out_html.exists()
