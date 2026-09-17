"""Provider registry: maps (cloud, service) to a (MetricSource, InventoryAdapter) pair.

Task 5 registers exactly two services: postgres-flexible and mysql-flexible.
Additional services and clouds are added in later tasks.
"""

from __future__ import annotations

from db_metrics.models import Target


# --------------------------------------------------------------------------- #
# Azure builder                                                                #
# --------------------------------------------------------------------------- #


def _build_aws(target: Target, credentials) -> tuple:
    """Construct the AWS provider pair for an RDS or Aurora target.

    Branches on ``target.service`` to set the appropriate CloudWatch dimension
    and select the matching inventory adapter.  Sets target.params["dimension_name"]
    and ["dimension_value"] so that CloudWatchSource.discover / query can read them.
    """
    from db_metrics.providers.aws.cloudwatch import CloudWatchSource
    from db_metrics.providers.aws.inventory import (
        AuroraInventoryAdapter,
        RdsInventoryAdapter,
    )

    if target.service == "aurora":
        dim_name = "DBClusterIdentifier"
        dim_value = target.params["cluster_identifier"]
        adapter = AuroraInventoryAdapter(credentials.rds)
    else:  # rds
        dim_name = "DBInstanceIdentifier"
        dim_value = target.params["identifier"]
        adapter = RdsInventoryAdapter(credentials.rds)

    target.params["dimension_name"] = dim_name
    target.params["dimension_value"] = dim_value
    source = CloudWatchSource(credentials.cloudwatch)
    return source, adapter


def _build_azure(target: Target, credentials) -> tuple:
    """Construct the Azure provider pair for a flexible-server target.

    Sets target.params["resource_id"] so that AzureMonitorSource.discover
    has the ARM id it reads from target.params.
    """
    from azure.monitor.query import MetricsQueryClient

    from db_metrics.providers.azure.inventory import (
        AzureInventoryAdapter,
        azure_resource_id,
    )
    from db_metrics.providers.azure.monitor import AzureMonitorSource

    cred = credentials.credential
    sub = credentials.subscription_id
    target.params["resource_id"] = azure_resource_id(target.service, sub, target.params)
    source = AzureMonitorSource(MetricsQueryClient(cred))
    adapter = AzureInventoryAdapter(cred, target.service, sub)
    return source, adapter


def services_for_cloud(cloud: str) -> list[str]:
    """Return the sorted service ids registered for a cloud ('azure' | 'aws')."""
    return sorted(name for name, meta in SERVICES.items() if meta["cloud"] == cloud)


# --------------------------------------------------------------------------- #
# Service registry                                                             #
# --------------------------------------------------------------------------- #

SERVICES: dict[str, dict] = {
    "postgres-flexible": {
        "cloud": "azure",
        "required_params": ["subscription", "resource_group", "server_name"],
        "build": _build_azure,
    },
    "mysql-flexible": {
        "cloud": "azure",
        "required_params": ["subscription", "resource_group", "server_name"],
        "build": _build_azure,
    },
    "cosmos-postgres": {
        "cloud": "azure",
        "required_params": ["subscription", "resource_group", "cluster_name"],
        "build": _build_azure,
    },
    "sql-database": {
        "cloud": "azure",
        "required_params": ["subscription", "resource_group", "server_name", "database"],
        "build": _build_azure,
    },
    "sql-managed-instance": {
        "cloud": "azure",
        "required_params": ["subscription", "resource_group", "instance_name"],
        "build": _build_azure,
    },
    "single-server": {
        "cloud": "azure",
        "required_params": ["subscription", "resource_group", "server_name", "sub_engine"],
        "build": _build_azure,
    },
    # profile/region are optional: make_session(None, None) falls back to the
    # default AWS profile and AWS_REGION/AWS_DEFAULT_REGION ambient config.
    "rds": {
        "cloud": "aws",
        "required_params": ["identifier"],
        "build": _build_aws,
    },
    "aurora": {
        "cloud": "aws",
        "required_params": ["cluster_identifier"],
        "build": _build_aws,
    },
}


# --------------------------------------------------------------------------- #
# Public factory                                                               #
# --------------------------------------------------------------------------- #


def build_providers(
    target: Target,
    credentials,
) -> tuple:
    """Return a (MetricSource, InventoryAdapter) pair for the given target.

    Raises ValueError for unknown services or missing required params.
    """
    if target.service not in SERVICES:
        known = ", ".join(sorted(SERVICES))
        raise ValueError(
            f"Target '{target.name}': unknown service '{target.service}'. "
            f"Known services: {known}"
        )

    required = SERVICES[target.service]["required_params"]
    missing = [p for p in required if not target.params.get(p)]
    if missing:
        raise ValueError(
            f"Target '{target.name}': missing required param(s) for service "
            f"'{target.service}': {', '.join(missing)}"
        )

    return SERVICES[target.service]["build"](target, credentials)
