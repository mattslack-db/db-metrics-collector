"""pyproject declares two console scripts and two cloud extras; the script
targets import and are callable."""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _cfg():
    with _PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def test_console_scripts_declared():
    scripts = _cfg()["project"]["scripts"]
    assert scripts["db-metrics-azure"] == "db_metrics.cli_azure:main"
    assert scripts["db-metrics-aws"] == "db_metrics.cli_aws:main"


def test_optional_extras_declared():
    extras = _cfg()["project"]["optional-dependencies"]
    assert any("boto3" in dep for dep in extras["aws"])
    azure_deps = " ".join(extras["azure"])
    assert "azure-monitor-query" in azure_deps and "azure-identity" in azure_deps


def test_script_targets_are_callable():
    for module_name, func in (("db_metrics.cli_azure", "main"),
                              ("db_metrics.cli_aws", "main")):
        mod = importlib.import_module(module_name)
        assert callable(getattr(mod, func))


def test_requirements_txt_removed():
    assert not (_PYPROJECT.parent / "requirements.txt").exists()
