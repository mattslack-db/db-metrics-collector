"""`python -m db_metrics` is ambiguous post-split: it must point users at the
two executables, exit with the usage code, and import neither cloud SDK."""

from __future__ import annotations

import subprocess
import sys


def test_module_entry_prints_usage_and_exits_2():
    out = subprocess.run([sys.executable, "-m", "db_metrics"],
                         capture_output=True, text=True)
    assert out.returncode == 2
    assert "db-metrics-azure" in out.stderr and "db-metrics-aws" in out.stderr


def test_module_entry_imports_no_cloud_sdk():
    code = ("import runpy, sys\n"
            "try:\n"
            "    runpy.run_module('db_metrics', run_name='__main__')\n"
            "except SystemExit:\n"
            "    pass\n"
            "roots = {m.split('.')[0] for m in sys.modules}\n"
            "assert 'boto3' not in roots and 'azure' not in roots, roots\n"
            "print('ok')\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_main_inprocess_exits_2_and_names_both_executables(capsys):
    """In-process call of main() must return 2 and print both executable names to stderr."""
    from db_metrics.__main__ import main  # noqa: PLC0415

    rc = main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "db-metrics-azure" in captured.err
    assert "db-metrics-aws" in captured.err
