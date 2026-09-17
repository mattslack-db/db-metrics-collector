"""Azure metrics exporter entry point (console script: db-metrics-azure).

Imports the azure auth module at top level — this is the only place azure.* is
pulled into the Azure process. Never imports boto3.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from . import cli_core
from .providers.registry import services_for_cloud

try:
    from .providers.azure.auth import get_credential, resolve_subscription
    _AZURE_AVAILABLE = True
except ModuleNotFoundError:
    _AZURE_AVAILABLE = False

_ENGINE_TO_SERVICE = {"postgres": "postgres-flexible", "mysql": "mysql-flexible"}


@dataclass
class _AzureCreds:
    credential: object
    subscription_id: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="db-metrics-azure",
        description="Collect Azure database performance metrics and configuration "
                    "for one target (via flags) or many (via --config).")
    cli_core.add_common_arguments(parser)
    parser.add_argument("--service", default=None, choices=services_for_cloud("azure"),
                        help="Azure service, e.g. postgres-flexible, sql-database.")
    parser.add_argument("--subscription", default=None,
                        help="Azure subscription GUID or display name.")
    parser.add_argument("--resource-group", default=None, help="Azure resource group name.")
    parser.add_argument("--server-name", default=None, help="Azure server / instance name.")
    parser.add_argument("--database", default=None, help="Database name (sql-database).")
    parser.add_argument("--tenant", default=None,
                        help="Entra tenant ID override (default: subscription home tenant).")
    parser.add_argument("--engine", choices=["postgres", "mysql"], default="postgres",
                        help="LEGACY: Flexible Server engine when neither --service nor "
                             "--config is used (default: postgres).")
    return parser


def resolve_credentials(target, cache: dict, tenant_override: str | None) -> _AzureCreds:
    subscription = target.params.get("subscription")
    key = str(subscription)
    if key not in cache:
        subscription_id, detected_tenant = resolve_subscription(subscription)
        credential = get_credential(tenant_override or detected_tenant)
        cache[key] = _AzureCreds(credential=credential, subscription_id=subscription_id)
    return cache[key]


def main(argv: list[str] | None = None) -> int:
    if not _AZURE_AVAILABLE:
        print("Error: Azure support is not installed. Run: pip install 'db-metrics[azure]'",
              file=sys.stderr)
        return cli_core.EXIT_USAGE
    args = build_parser().parse_args(argv)
    return cli_core.run(
        args, cloud="azure", engine_map=_ENGINE_TO_SERVICE,
        resolve_credentials=lambda t, c: resolve_credentials(t, c, args.tenant))


if __name__ == "__main__":
    sys.exit(main())
