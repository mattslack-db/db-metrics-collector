"""Cloud-agnostic core: targets_from_args (with an injected cloud/engine_map),
foreign-cloud rejection, and a fully offline run() driven by an injected
resolve_credentials callback + a monkeypatched build_providers."""

from __future__ import annotations

import argparse
import json

import pytest

from db_metrics import cli_core
from db_metrics.models import Target
from db_metrics.providers.base import MetricDef, MetricSeries


class _FakeSource:
    def discover(self, target):
        return [MetricDef(name="cpu", unit="Percent", aggregations=["Average"],
                          dimensions=[], granularities=["PT1M"])]

    def query(self, target, defs, start, end, granularity):
        assert all(isinstance(d, MetricDef) for d in defs)
        return [MetricSeries(name="cpu", unit="Percent", granularity="PT1M",
                             timeseries=[{"dimensions": {}, "points": [],
                                          "summary": {"average": {"latest": 1.0}}}])]


class _FakeAdapter:
    def __init__(self, raises=False):
        self._raises = raises

    def collect(self, target):
        if self._raises:
            raise RuntimeError("403 Forbidden")
        return {"server": {"name": "srv"}, "parameters": [], "resource_id": "/rid"}


def _azure_parser():
    p = argparse.ArgumentParser()
    cli_core.add_common_arguments(p)
    p.add_argument("--service", default=None)
    for f in ("--subscription", "--resource-group", "--server-name", "--database"):
        p.add_argument(f, default=None)
    p.add_argument("--engine", choices=["postgres", "mysql"], default="postgres")
    return p


def _aws_parser():
    p = argparse.ArgumentParser()
    cli_core.add_common_arguments(p)
    p.add_argument("--service", default=None)
    for f in ("--profile", "--region", "--identifier", "--cluster-identifier"):
        p.add_argument(f, default=None)
    return p


_ENGINE_MAP = {"postgres": "postgres-flexible", "mysql": "mysql-flexible"}


def _install(monkeypatch, adapter=None):
    monkeypatch.setattr(cli_core, "build_providers",
                        lambda target, creds: (_FakeSource(), adapter or _FakeAdapter()))


# targets_from_args -------------------------------------------------------- #

def test_azure_legacy_engine_maps_to_service():
    args = _azure_parser().parse_args(
        ["--engine", "mysql", "--subscription", "s", "--resource-group", "rg",
         "--server-name", "srv"])
    t = cli_core.targets_from_args(args, cloud="azure", engine_map=_ENGINE_MAP)[0]
    assert t.cloud == "azure" and t.service == "mysql-flexible"
    assert t.params == {"subscription": "s", "resource_group": "rg", "server_name": "srv"}


def test_azure_default_engine_is_postgres():
    args = _azure_parser().parse_args(
        ["--subscription", "s", "--resource-group", "rg", "--server-name", "srv"])
    assert cli_core.targets_from_args(args, cloud="azure", engine_map=_ENGINE_MAP)[0].service \
        == "postgres-flexible"


def test_aws_single_target_rds():
    args = _aws_parser().parse_args(
        ["--service", "rds", "--profile", "p", "--region", "r", "--identifier", "db1"])
    t = cli_core.targets_from_args(args, cloud="aws", engine_map=None)[0]
    assert t.cloud == "aws" and t.service == "rds"
    assert t.params == {"profile": "p", "region": "r", "identifier": "db1"}


def test_aws_without_service_is_usage_error():
    args = _aws_parser().parse_args(["--profile", "p", "--region", "r"])
    with pytest.raises(ValueError):
        cli_core.targets_from_args(args, cloud="aws", engine_map=None)


def test_config_plus_single_flag_rejected(tmp_path):
    cfg = tmp_path / "c.json"; cfg.write_text("{}")
    args = _azure_parser().parse_args(["--config", str(cfg), "--subscription", "s"])
    with pytest.raises(ValueError):
        cli_core.targets_from_args(args, cloud="azure", engine_map=_ENGINE_MAP)


# reject_foreign_targets --------------------------------------------------- #

def test_reject_foreign_targets_names_offender():
    targets = [Target(name="a", cloud="azure", service="postgres-flexible"),
               Target(name="b", cloud="aws", service="rds")]
    msg = cli_core.reject_foreign_targets(targets, "azure")
    assert msg is not None and "b" in msg


def test_reject_foreign_targets_all_match_returns_none():
    targets = [Target(name="a", cloud="aws", service="rds")]
    assert cli_core.reject_foreign_targets(targets, "aws") is None


# run ---------------------------------------------------------------------- #

def test_run_happy_path_writes_json(monkeypatch, tmp_path):
    _install(monkeypatch)
    out = tmp_path / "r.json"
    args = _aws_parser().parse_args(
        ["--service", "rds", "--profile", "p", "--region", "r",
         "--identifier", "db1", "--out", str(out), "--no-console"])
    rc = cli_core.run(args, cloud="aws", engine_map=None,
                      resolve_credentials=lambda t, c: object())
    assert rc == cli_core.EXIT_OK
    assert json.loads(out.read_text())["service"] == "rds"


def test_run_bad_interval_is_usage(monkeypatch):
    _install(monkeypatch)
    args = _aws_parser().parse_args(
        ["--service", "rds", "--profile", "p", "--region", "r",
         "--identifier", "db1", "--interval", "banana"])
    assert cli_core.run(args, cloud="aws", engine_map=None,
                        resolve_credentials=lambda t, c: object()) == cli_core.EXIT_USAGE


def test_run_foreign_config_target_is_usage(monkeypatch, tmp_path):
    _install(monkeypatch)
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"targets": [
        {"name": "x", "cloud": "aws", "service": "rds",
         "profile": "p", "region": "r", "identifier": "db1"}]}))
    args = _azure_parser().parse_args(["--config", str(cfg)])
    rc = cli_core.run(args, cloud="azure", engine_map=_ENGINE_MAP,
                      resolve_credentials=lambda t, c: object())
    assert rc == cli_core.EXIT_USAGE


def test_run_inventory_failure_is_error(monkeypatch):
    _install(monkeypatch, adapter=_FakeAdapter(raises=True))
    args = _aws_parser().parse_args(
        ["--service", "rds", "--profile", "p", "--region", "r",
         "--identifier", "db1", "--no-console"])
    assert cli_core.run(args, cloud="aws", engine_map=None,
                        resolve_credentials=lambda t, c: object()) == cli_core.EXIT_ERROR


# default_out_path ------------------------------------------------------------ #

def test_default_out_path_format():
    """default_out_path returns a timestamped JSON filename for the given name."""
    path = cli_core.default_out_path("my-server")
    assert path.startswith("metrics_my-server_")
    assert path.endswith(".json")
    # Timestamp segment should be present (16-char YYYYMMDD_HHMMSS)
    stem = path[len("metrics_my-server_"):-len(".json")]
    assert len(stem) == 15  # YYYYmmdd_HHMMSS


# _explicit_single_flags — service branch (line 62) -------------------------- #

def test_config_plus_service_flag_rejected(tmp_path):
    """--config combined with --service must raise ValueError (service branch of _explicit_single_flags)."""
    cfg = tmp_path / "c.json"
    cfg.write_text('{"targets": []}')
    args = _azure_parser().parse_args(
        ["--config", str(cfg), "--service", "postgres-flexible"])
    with pytest.raises(ValueError, match="mutually exclusive"):
        cli_core.targets_from_args(args, cloud="azure", engine_map=_ENGINE_MAP)


# _validate_windows — negative hours (line 119) ------------------------------ #

def test_run_negative_hours_is_usage(monkeypatch, tmp_path):
    """hours <= 0 in a config target must produce EXIT_USAGE."""
    _install(monkeypatch)
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"targets": [{
        "name": "db1", "cloud": "aws", "service": "rds",
        "profile": "p", "region": "us-east-1", "identifier": "db1",
        "hours": -1,
    }]}))
    args = _aws_parser().parse_args(["--config", str(cfg)])
    rc = cli_core.run(args, cloud="aws", engine_map=None,
                      resolve_credentials=lambda t, c: object())
    assert rc == cli_core.EXIT_USAGE


# reject_foreign_targets — error message content (line 105-107) --------------- #

def test_reject_foreign_targets_message_names_correct_tool():
    """Error message must name the right sibling executable for each allowed cloud."""
    targets = [Target(name="srv", cloud="aws", service="rds")]
    msg_azure = cli_core.reject_foreign_targets(targets, allowed_cloud="azure")
    assert msg_azure is not None and "db-metrics-aws" in msg_azure

    targets2 = [Target(name="srv", cloud="azure", service="postgres-flexible")]
    msg_aws = cli_core.reject_foreign_targets(targets2, allowed_cloud="aws")
    assert msg_aws is not None and "db-metrics-azure" in msg_aws


# _validate_params — single-target missing required param → EXIT_USAGE ---------- #

def test_run_single_target_missing_subscription_is_usage(monkeypatch, capsys):
    """Single-target azure run missing --subscription must return EXIT_USAGE (not EXIT_ERROR)."""
    _install(monkeypatch)
    args = _azure_parser().parse_args(
        ["--service", "postgres-flexible", "--resource-group", "rg", "--server-name", "srv"])
    rc = cli_core.run(args, cloud="azure", engine_map=_ENGINE_MAP,
                      resolve_credentials=lambda t, c: object())
    assert rc == cli_core.EXIT_USAGE
    captured = capsys.readouterr()
    assert "subscription" in captured.err


# multi-target run — summary branch + console output (lines 54-55, 168, 177-182) #

def test_run_multi_target_writes_summary(monkeypatch, tmp_path, capsys):
    """Carry-forward from Task 5: two-target run writes per-target + summary files
    and prints both per-target and summary console output."""
    _install(monkeypatch)
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"targets": [
        {"name": "db1", "cloud": "aws", "service": "rds",
         "profile": "p", "region": "us-east-1", "identifier": "db1"},
        {"name": "db2", "cloud": "aws", "service": "rds",
         "profile": "p", "region": "us-east-1", "identifier": "db2"},
    ]}))
    monkeypatch.chdir(tmp_path)
    # No --no-console so render_console_summary (line 168) and
    # render_summary_table (line 181) are both exercised.
    args = _aws_parser().parse_args(["--config", str(cfg)])
    rc = cli_core.run(args, cloud="aws", engine_map=None,
                      resolve_credentials=lambda t, c: object())

    assert rc == cli_core.EXIT_OK

    metrics_files = sorted(tmp_path.glob("metrics_*.json"))
    summary_files = list(tmp_path.glob("summary_*.json"))
    assert len(metrics_files) == 2, f"expected 2 metrics files, found: {metrics_files}"
    assert len(summary_files) == 1, f"expected 1 summary file, found: {summary_files}"

    # Summary JSON is well-formed with two targets
    summary = json.loads(summary_files[0].read_text())
    assert summary["target_count"] == 2
    assert summary["error_target_count"] == 0

    # Console output was printed (per-target summary + multi-target table)
    captured = capsys.readouterr()
    assert "Targets: 2" in captured.out  # from render_summary_table
