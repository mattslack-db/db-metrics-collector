"""The split's core guarantee: importing a cloud-agnostic module (or, later,
a cloud entry point) must not drag in the other cloud's SDK. Each check runs in
a fresh interpreter so one test's imports never pollute another's."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _import_and_report(module: str) -> set[str]:
    """Import `module` in a fresh interpreter; return the top-level SDK roots
    present in sys.modules afterwards ('boto3' and/or 'azure')."""
    code = (
        f"import {module}, sys, json\n"
        "roots = set()\n"
        "for m in sys.modules:\n"
        "    root = m.split('.')[0]\n"
        "    if root in ('boto3', 'azure'):\n"
        "        roots.add(root)\n"
        "print(json.dumps(sorted(roots)))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
    )
    return set(json.loads(out.stdout.strip().splitlines()[-1]))


def test_registry_imports_no_cloud_sdk():
    assert _import_and_report("db_metrics.providers.registry") == set()


def test_config_imports_no_cloud_sdk():
    assert _import_and_report("db_metrics.config") == set()
