"""AWS entry point: cloud-scoped parser, per-(profile,region) session caching
via make_session/clients, --service-required, offline run, azure-free import."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from db_metrics import cli_aws, cli_core
from db_metrics.models import Target


class _FakeSource:
    def discover(self, target): return []
    def query(self, target, defs, start, end, granularity): return []


class _FakeAdapter:
    def collect(self, target):
        return {"server": {"name": "db1"}, "parameters": []}


def test_parser_service_choices_are_aws_only():
    args = cli_aws.build_parser().parse_args(
        ["--service", "rds", "--profile", "p", "--region", "r", "--identifier", "db1"])
    assert args.service == "rds"


def test_parser_has_no_engine_flag():
    import pytest
    with pytest.raises(SystemExit):
        cli_aws.build_parser().parse_args(["--engine", "postgres"])


def test_resolve_credentials_caches_per_profile_region(monkeypatch):
    sessions = []
    monkeypatch.setattr(cli_aws, "make_session",
                        lambda profile=None, region=None: sessions.append((profile, region)) or object())
    monkeypatch.setattr(cli_aws, "clients", lambda s: ("cw", "rds"))
    cache = {}
    t = Target(name="a", cloud="aws", service="rds",
               params={"profile": "p", "region": "r", "identifier": "db1"})
    c1 = cli_aws.resolve_credentials(t, cache)
    c2 = cli_aws.resolve_credentials(t, cache)
    assert c1 is c2 and c1.cloudwatch == "cw" and c1.rds == "rds"
    assert len(sessions) == 1  # one session for the same (profile, region)


def test_run_without_service_is_usage(monkeypatch):
    assert cli_aws.main(["--profile", "p", "--region", "r"]) == cli_core.EXIT_USAGE


def test_run_happy_path(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_core, "build_providers",
                        lambda target, creds: (_FakeSource(), _FakeAdapter()))
    monkeypatch.setattr(cli_aws, "make_session", lambda profile=None, region=None: object())
    monkeypatch.setattr(cli_aws, "clients", lambda s: ("cw", "rds"))
    out = tmp_path / "r.json"
    rc = cli_aws.main(["--service", "rds", "--profile", "p", "--region", "r",
                       "--identifier", "db1", "--out", str(out), "--no-console"])
    assert rc == cli_core.EXIT_OK
    assert json.loads(out.read_text())["service"] == "rds"


def test_run_rejects_azure_config_target(tmp_path):
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"targets": [
        {"name": "x", "cloud": "azure", "service": "postgres-flexible",
         "subscription": "s", "resource_group": "rg", "server_name": "srv"}]}))
    assert cli_aws.main(["--config", str(cfg)]) == cli_core.EXIT_USAGE


def test_main_returns_usage_when_aws_not_available(monkeypatch, capsys):
    monkeypatch.setattr(cli_aws, "_AWS_AVAILABLE", False)
    rc = cli_aws.main(["--service", "rds", "--profile", "p", "--region", "r",
                       "--identifier", "db1"])
    assert rc == cli_core.EXIT_USAGE
    captured = capsys.readouterr()
    assert "pip install 'db-metrics[aws]'" in captured.err


def test_import_does_not_pull_azure():
    code = ("import db_metrics.cli_aws, sys\n"
            "leaked = [m for m in sys.modules if m == 'azure' or m.startswith('azure.')]\n"
            "assert not leaked, f'azure leaked into aws exec: {leaked}'\n"
            "print('ok')\n")
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    )
    assert out.returncode == 0, out.stderr
