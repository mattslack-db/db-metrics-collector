"""Auth-behavior coverage relocated from the deleted legacy db_metrics.auth.

These tests were moved here (from tests/test_cli.py and tests/test_report.py)
in Task 9 when db_metrics/auth.py was removed. They now exercise the new
home of the auth helpers: db_metrics.providers.azure.auth.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from db_metrics.providers.azure import auth


def test_resolve_subscription_returns_guid_when_cli_absent(monkeypatch):
    guid = "11111111-2222-3333-4444-555555555555"
    monkeypatch.setattr(auth, "_az_account_show", lambda s: None)
    assert auth.resolve_subscription(guid) == (guid, None)


def test_resolve_subscription_uses_cli_for_name(monkeypatch):
    calls = {}

    def fake_run(cmd, capture_output, text, timeout):
        calls["cmd"] = cmd
        return SimpleNamespace(
            returncode=0,
            stdout='{"id": "resolved-guid", "tenantId": "tenant-y"}',
            stderr="",
        )

    monkeypatch.setattr(auth.subprocess, "run", fake_run)
    assert auth.resolve_subscription("my-subscription") == ("resolved-guid", "tenant-y")
    assert "my-subscription" in calls["cmd"]


def test_resolve_subscription_raises_on_unknown_name(monkeypatch):
    monkeypatch.setattr(auth, "_az_account_show", lambda s: None)
    with pytest.raises(RuntimeError):
        auth.resolve_subscription("no-such-sub")


def test_looks_like_subscription_id():
    assert auth.looks_like_subscription_id("00000000-0000-0000-0000-000000000000")
    assert not auth.looks_like_subscription_id("my-subscription")


# ---------------------------------------------------------------------------
# get_credential (lines 35-37 — never called in prior tests)
# ---------------------------------------------------------------------------


def test_get_credential_returns_default_credential_when_no_tenant():
    """get_credential() with no tenant returns a DefaultAzureCredential."""
    from azure.identity import DefaultAzureCredential

    cred = auth.get_credential()
    assert isinstance(cred, DefaultAzureCredential)


def test_get_credential_returns_cli_credential_with_tenant():
    """get_credential(tenant_id) pins to AzureCliCredential."""
    from azure.identity import AzureCliCredential

    cred = auth.get_credential("my-tenant-id")
    assert isinstance(cred, AzureCliCredential)


# ---------------------------------------------------------------------------
# _az_account_show error paths (lines 48-49, 51, 54-55)
# ---------------------------------------------------------------------------


def test_az_account_show_returns_none_on_file_not_found(monkeypatch):
    """_az_account_show returns None when az CLI is not installed."""

    def raise_file_not_found(*args, **kwargs):
        raise FileNotFoundError("az not found")

    monkeypatch.setattr(auth.subprocess, "run", raise_file_not_found)
    assert auth._az_account_show("some-sub") is None


def test_az_account_show_returns_none_on_nonzero_returncode(monkeypatch):
    """_az_account_show returns None when az exits with a non-zero code."""
    from types import SimpleNamespace

    monkeypatch.setattr(
        auth.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=1, stdout="", stderr="Error"),
    )
    assert auth._az_account_show("some-sub") is None


def test_az_account_show_returns_none_on_bad_json(monkeypatch):
    """_az_account_show returns None when az emits malformed JSON."""
    from types import SimpleNamespace

    monkeypatch.setattr(
        auth.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="not-valid-json", stderr=""),
    )
    assert auth._az_account_show("some-sub") is None
