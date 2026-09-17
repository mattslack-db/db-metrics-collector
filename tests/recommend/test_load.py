import json
import os
import pytest
from db_metrics.recommend.load import discover_reports, load_report, Report, ReportError

def test_discover_globs_metrics_and_excludes_summary(tmp_path):
    (tmp_path / "metrics_a.json").write_text("{}")
    (tmp_path / "metrics_b.json").write_text("{}")
    (tmp_path / "summary_x.json").write_text("{}")
    found = discover_reports([str(tmp_path)])
    names = [os.path.basename(p) for p in found]
    assert names == ["metrics_a.json", "metrics_b.json"]

def test_discover_keeps_explicit_files_and_dedupes(tmp_path):
    f = tmp_path / "metrics_a.json"
    f.write_text("{}")
    found = discover_reports([str(f), str(f)])
    assert found == [str(f)]

def test_load_valid_report(fx):
    rep = load_report(fx("azure_pg.json"))
    assert isinstance(rep, Report)
    assert rep.cloud == "azure"
    assert rep.service == "postgres-flexible"
    assert rep.display_name == "prod-pg"

def test_load_invalid_raises_report_error(fx):
    with pytest.raises(ReportError) as exc:
        load_report(fx("invalid.json"))
    assert "missing keys" in exc.value.reason

def test_load_unreadable_json_raises(tmp_path):
    bad = tmp_path / "metrics_bad.json"
    bad.write_text("{not json")
    with pytest.raises(ReportError):
        load_report(str(bad))


def test_load_metrics_wrong_type_raises_report_error(tmp_path):
    """metrics must be a list — a string value must raise ReportError, not AttributeError."""
    bad = tmp_path / "metrics_string.json"
    bad.write_text(
        '{"cloud": "azure", "service": "pg", "inventory": {}, "metrics": "oops", "window": {}}'
    )
    with pytest.raises(ReportError) as exc:
        load_report(str(bad))
    assert "metrics" in exc.value.reason.lower()


def test_load_inventory_wrong_type_raises_report_error(tmp_path):
    """inventory must be a dict — a list value must raise ReportError."""
    bad = tmp_path / "metrics_inv_list.json"
    bad.write_text(
        '{"cloud": "azure", "service": "pg", "inventory": [1, 2], "metrics": [], "window": {}}'
    )
    with pytest.raises(ReportError) as exc:
        load_report(str(bad))
    assert "inventory" in exc.value.reason.lower()
