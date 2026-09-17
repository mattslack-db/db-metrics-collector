"""Azure entry point: cloud-scoped parser, per-subscription credential caching,
legacy --engine back-compat, an offline run, and the boto3-free import guarantee."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from db_metrics import cli_azure, cli_core
from db_metrics.models import Target


class _FakeSource:
    def discover(self, target): return []
    def query(self, target, defs, start, end, granularity): return []


class _FakeAdapter:
    def collect(self, target):
        return {"server": {"name": "srv"}, "parameters": [], "resource_id": "/rid"}


def test_parser_has_engine_and_azure_flags():
    args = cli_azure.build_parser().parse_args(
        ["--engine", "mysql", "--subscription", "s", "--resource-group", "rg",
         "--server-name", "srv", "--tenant", "t"])
    assert args.engine == "mysql" and args.tenant == "t"


def test_parser_service_choices_are_azure_only():
    p = cli_azure.build_parser()
    args = p.parse_args(["--service", "sql-database", "--subscription", "s",
                         "--resource-group", "rg", "--server-name", "srv", "--database", "db"])
    assert args.service == "sql-database"


def test_resolve_credentials_caches_per_subscription(monkeypatch):
    calls = []
    monkeypatch.setattr(cli_azure, "resolve_subscription",
                        lambda s: (calls.append(s) or ("sub-id", "tenant-x")))
    monkeypatch.setattr(cli_azure, "get_credential", lambda tenant_id=None: object())
    cache = {}
    t = Target(name="a", cloud="azure", service="postgres-flexible",
               params={"subscription": "s"})
    c1 = cli_azure.resolve_credentials(t, cache, None)
    c2 = cli_azure.resolve_credentials(t, cache, None)
    assert c1 is c2 and c1.subscription_id == "sub-id"
    assert len(calls) == 1  # resolved once, then cached


def test_run_happy_path(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_core, "build_providers",
                        lambda target, creds: (_FakeSource(), _FakeAdapter()))
    monkeypatch.setattr(cli_azure, "resolve_subscription", lambda s: ("sub", "ten"))
    monkeypatch.setattr(cli_azure, "get_credential", lambda tenant_id=None: object())
    out = tmp_path / "r.json"
    rc = cli_azure.main(["--engine", "mysql", "--subscription", "s",
                         "--resource-group", "rg", "--server-name", "srv",
                         "--out", str(out), "--no-console"])
    assert rc == cli_core.EXIT_OK
    assert json.loads(out.read_text())["service"] == "mysql-flexible"


def test_run_rejects_aws_config_target(monkeypatch, tmp_path):
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"targets": [
        {"name": "x", "cloud": "aws", "service": "rds",
         "profile": "p", "region": "r", "identifier": "db1"}]}))
    assert cli_azure.main(["--config", str(cfg)]) == cli_core.EXIT_USAGE


def test_main_returns_usage_when_azure_not_available(monkeypatch, capsys):
    monkeypatch.setattr(cli_azure, "_AZURE_AVAILABLE", False)
    rc = cli_azure.main(["--subscription", "s", "--resource-group", "rg",
                         "--server-name", "srv"])
    assert rc == cli_core.EXIT_USAGE
    captured = capsys.readouterr()
    assert "pip install 'db-metrics[azure]'" in captured.err


def test_import_does_not_pull_boto3():
    code = ("import db_metrics.cli_azure, sys\n"
            "assert 'boto3' not in sys.modules, 'boto3 leaked into azure exec'\n"
            "print('ok')\n")
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    )
    assert out.returncode == 0, out.stderr
