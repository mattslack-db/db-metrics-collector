"""Authentication and subscription/tenant resolution.

A subscription may live in a different Entra tenant than the credential's
default, so we resolve the subscription's home tenant (via the local az CLI
profile) and pin the credential to it. Without a tenant we fall back to
DefaultAzureCredential's own default.
"""

from __future__ import annotations

import json
import re
import subprocess

from azure.identity import AzureCliCredential, DefaultAzureCredential

_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def looks_like_subscription_id(value: str) -> bool:
    """True if value is a subscription GUID (vs a display name)."""
    return bool(_GUID_RE.match(value.strip()))


def get_credential(tenant_id: str | None = None):
    """Return a credential, pinned to tenant_id when one is known.

    With a tenant we use AzureCliCredential (the practical auth source when a
    subscription lives in a non-default tenant); without one we use
    DefaultAzureCredential so managed identity / env credentials still work.
    """
    if tenant_id:
        return AzureCliCredential(tenant_id=tenant_id)
    return DefaultAzureCredential()


def _az_account_show(subscription: str) -> dict | None:
    """Return {'id', 'tenantId'} for a subscription via az, or None on failure."""
    try:
        result = subprocess.run(
            ["az", "account", "show", "--subscription", subscription,
             "--query", "{id:id, tenantId:tenantId}", "--output", "json"],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def resolve_subscription(subscription: str) -> tuple[str, str | None]:
    """Resolve a subscription name-or-GUID to (subscription_id, tenant_id).

    tenant_id is None when it cannot be determined (e.g. a GUID passed with no
    working az CLI); the caller may still override it explicitly.
    """
    subscription = subscription.strip()
    info = _az_account_show(subscription)
    if info and info.get("id"):
        return info["id"], info.get("tenantId")
    if looks_like_subscription_id(subscription):
        return subscription, None
    raise RuntimeError(
        f"Could not resolve subscription '{subscription}'. Pass a subscription "
        "GUID, or ensure the Azure CLI (az) is installed and logged in."
    )
