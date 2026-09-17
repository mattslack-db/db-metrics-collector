"""Azure inventory adapter for multiple Azure DB services.

Supports: postgres-flexible, mysql-flexible, cosmos-postgres,
          sql-database, sql-managed-instance, single-server.

Self-contained: pure helpers are ported verbatim from db_metrics.inventory
so this module survives Task 9's deletion of that legacy module without
importing from it.

The module-level ``create_mgmt_client`` factory is the monkeypatch seam for
tests, mirroring the shape of db_metrics.engines.create_mgmt_client.
"""

from __future__ import annotations

from typing import Any

from azure.mgmt.cosmosdbforpostgresql import CosmosdbForPostgresqlMgmtClient
from azure.mgmt.mysqlflexibleservers import MySQLManagementClient
from azure.mgmt.postgresqlflexibleservers import PostgreSQLManagementClient
from azure.mgmt.rdbms.mysql import MySQLManagementClient as RdbmsMySQLManagementClient
from azure.mgmt.rdbms.postgresql import PostgreSQLManagementClient as RdbmsPGManagementClient
from azure.mgmt.sql import SqlManagementClient

from db_metrics.models import Target

# --------------------------------------------------------------------------- #
# Per-service constants                                                        #
# --------------------------------------------------------------------------- #

_MGMT_CLIENTS: dict[str, Any] = {
    "postgres-flexible": PostgreSQLManagementClient,
    "mysql-flexible": MySQLManagementClient,
    "cosmos-postgres": CosmosdbForPostgresqlMgmtClient,
    "sql-database": SqlManagementClient,
    "sql-managed-instance": SqlManagementClient,
    # single-server is resolved dynamically via params["sub_engine"]
}

_RDBMS_CLIENTS: dict[str, Any] = {
    "postgresql": RdbmsPGManagementClient,
    "mysql": RdbmsMySQLManagementClient,
}

# --------------------------------------------------------------------------- #
# Module-level factory (monkeypatch seam)                                      #
# --------------------------------------------------------------------------- #


def create_mgmt_client(
    service: str,
    credential: Any,
    subscription_id: str,
    params: Any = None,
) -> Any:
    """Instantiate the management client for the given service.

    This is a module-level function so tests can patch it via monkeypatch,
    mirroring how tests/test_cli.py patches cli.engines.create_mgmt_client.

    The flexible, cosmos-postgres, sql-database, and sql-managed-instance
    paths are callable as ``create_mgmt_client(service, credential, sub)``
    (no params arg) so Task-5 tests remain unchanged.  single-server passes
    ``params=target.params`` so the correct rdbms client is selected.
    """
    if service == "single-server":
        engine = params["sub_engine"]
        cls = _RDBMS_CLIENTS[engine]
        return cls(credential, subscription_id)
    return _MGMT_CLIENTS[service](credential, subscription_id)


# --------------------------------------------------------------------------- #
# ARM resource-id builder (per-service dispatch)                               #
# --------------------------------------------------------------------------- #


def azure_resource_id(service: str, subscription_id: str, params: dict) -> str:
    """Build the ARM resource id for the given Azure DB service target.

    The flexible-service strings are identical to the Task-5 implementation so
    all existing ``test_arm_resource_id_*`` tests remain green.
    """
    sub = subscription_id
    rg = params["resource_group"]

    if service == "postgres-flexible":
        return (
            f"/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.DBforPostgreSQL/flexibleServers/{params['server_name']}"
        )
    if service == "mysql-flexible":
        return (
            f"/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.DBforMySQL/flexibleServers/{params['server_name']}"
        )
    if service == "cosmos-postgres":
        return (
            f"/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.DBforPostgreSQL/serverGroupsv2/{params['cluster_name']}"
        )
    if service == "sql-database":
        return (
            f"/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.Sql/servers/{params['server_name']}"
            f"/databases/{params['database']}"
        )
    if service == "sql-managed-instance":
        return (
            f"/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.Sql/managedInstances/{params['instance_name']}"
        )
    if service == "single-server":
        engine = params["sub_engine"]
        ns = "Microsoft.DBforPostgreSQL" if engine == "postgresql" else "Microsoft.DBforMySQL"
        return (
            f"/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/{ns}/servers/{params['server_name']}"
        )
    raise ValueError(f"azure_resource_id: unknown service '{service}'")


# --------------------------------------------------------------------------- #
# Pure helpers — ported verbatim from db_metrics.inventory                    #
# --------------------------------------------------------------------------- #


def _get(obj: Any, *names: str) -> Any:
    """Return the first present, non-None attribute from names (else None)."""
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def server_to_dict(server: Any) -> dict:
    """Flatten a Server model into a plain, JSON-serializable dict."""
    sku = getattr(server, "sku", None)
    storage = getattr(server, "storage", None)
    ha = getattr(server, "high_availability", None)
    backup = getattr(server, "backup", None)
    network = getattr(server, "network", None)
    maint = getattr(server, "maintenance_window", None)

    return {
        "id": getattr(server, "id", None),
        "name": getattr(server, "name", None),
        "location": getattr(server, "location", None),
        "state": getattr(server, "state", None),
        "version": getattr(server, "version", None),
        "minor_version": getattr(server, "minor_version", None),
        "fully_qualified_domain_name": getattr(server, "fully_qualified_domain_name", None),
        "administrator_login": getattr(server, "administrator_login", None),
        "availability_zone": getattr(server, "availability_zone", None),
        "sku": {
            "name": _get(sku, "name"),
            "tier": _get(sku, "tier"),
        } if sku else None,
        "storage": {
            "size_gb": _get(storage, "storage_size_gb"),
            "tier": _get(storage, "tier"),
            "iops": _get(storage, "iops"),
            "auto_grow": _get(storage, "auto_grow"),
            "auto_io_scaling": _get(storage, "auto_io_scaling"),  # MySQL
            "type": _get(storage, "type"),
        } if storage else None,
        "high_availability": {
            "mode": _get(ha, "mode"),
            "state": _get(ha, "state"),
            "standby_availability_zone": _get(ha, "standby_availability_zone"),
        } if ha else None,
        "backup": {
            "retention_days": _get(backup, "backup_retention_days"),
            "geo_redundant_backup": _get(backup, "geo_redundant_backup"),
            "earliest_restore_date": _get(backup, "earliest_restore_date"),
        } if backup else None,
        "network": {
            "public_network_access": _get(network, "public_network_access"),
            "delegated_subnet_resource_id": _get(network, "delegated_subnet_resource_id"),
            "private_dns_zone_resource_id": _get(network, "private_dns_zone_arm_resource_id"),
        } if network else None,
        "maintenance_window": {
            "custom_window": _get(maint, "custom_window"),
            "day_of_week": _get(maint, "day_of_week"),
            "start_hour": _get(maint, "start_hour"),
            "start_minute": _get(maint, "start_minute"),
        } if maint else None,
    }


def configuration_to_dict(config: Any) -> dict:
    """Flatten a server-parameter (Configuration) model into a dict."""
    value = _get(config, "value")
    default = _get(config, "default_value")
    return {
        "name": getattr(config, "name", None),
        "value": value,
        "default_value": default,
        "source": _get(config, "source"),
        "is_dynamic_config": _get(config, "is_dynamic_config"),
        "is_read_only": _get(config, "is_read_only"),
        "is_non_default": value is not None and default is not None and value != default,
        "unit": _get(config, "unit"),
        "description": _get(config, "description"),
    }


def collect_inventory(client: Any, resource_group: str, server_name: str) -> dict:
    """Fetch server properties, parameters, and databases (live SDK calls).

    ``client`` is a PostgreSQL or MySQL flexible-server management client; both
    expose the same operation shape.
    """
    server = client.servers.get(resource_group, server_name)
    server_dict = server_to_dict(server)

    parameters = [
        configuration_to_dict(c)
        for c in client.configurations.list_by_server(resource_group, server_name)
    ]

    try:
        databases = [
            getattr(d, "name", None)
            for d in client.databases.list_by_server(resource_group, server_name)
        ]
    except Exception as exc:  # databases listing can be denied independently
        databases = {"error": str(exc)}

    return {
        "resource_id": server_dict["id"],
        "server": server_dict,
        "parameters": parameters,
        "parameters_non_default": [p for p in parameters if p["is_non_default"]],
        "databases": databases,
    }


# --------------------------------------------------------------------------- #
# Per-service inventory collectors (Task 6)                                   #
# --------------------------------------------------------------------------- #


def _collect_cosmos_postgres(client: Any, params: dict) -> dict:
    """Collect inventory for a Cosmos DB for PostgreSQL cluster."""
    rg = params["resource_group"]
    cluster_name = params["cluster_name"]
    cluster = client.clusters.get(rg, cluster_name)
    server = {
        "id": getattr(cluster, "id", None),
        "name": getattr(cluster, "name", None),
        "location": getattr(cluster, "location", None),
        "state": getattr(cluster, "state", None),
        "postgresql_version": getattr(cluster, "postgresql_version", None),
        "citus_version": getattr(cluster, "citus_version", None),
        "enable_ha": getattr(cluster, "enable_ha", None),
        "coordinator_storage_quota_in_mb": getattr(cluster, "coordinator_storage_quota_in_mb", None),
        "coordinator_v_cores": getattr(cluster, "coordinator_v_cores", None),
        "node_count": getattr(cluster, "node_count", None),
        "node_v_cores": getattr(cluster, "node_v_cores", None),
        "node_storage_quota_in_mb": getattr(cluster, "node_storage_quota_in_mb", None),
    }
    return {
        "resource_id": None,
        "server": server,
        "parameters": [],
        "parameters_non_default": [],
    }


def _collect_sql_database(client: Any, params: dict) -> dict:
    """Collect inventory for an Azure SQL Database."""
    rg = params["resource_group"]
    server_name = params["server_name"]
    database = params["database"]
    db = client.databases.get(rg, server_name, database)
    sku = getattr(db, "sku", None)
    server = {
        "id": getattr(db, "id", None),
        "name": getattr(db, "name", None),
        "location": getattr(db, "location", None),
        "status": getattr(db, "status", None),
        "max_size_bytes": getattr(db, "max_size_bytes", None),
        "current_service_objective_name": getattr(db, "current_service_objective_name", None),
        "sku": {
            "name": _get(sku, "name"),
            "tier": _get(sku, "tier"),
            "capacity": _get(sku, "capacity"),
        } if sku else None,
    }
    return {
        "resource_id": None,
        "server": server,
        "parameters": [],
        "parameters_non_default": [],
    }


def _collect_sql_managed_instance(client: Any, params: dict) -> dict:
    """Collect inventory for an Azure SQL Managed Instance."""
    rg = params["resource_group"]
    instance_name = params["instance_name"]
    mi = client.managed_instances.get(rg, instance_name)
    sku = getattr(mi, "sku", None)
    server = {
        "id": getattr(mi, "id", None),
        "name": getattr(mi, "name", None),
        "location": getattr(mi, "location", None),
        "state": getattr(mi, "state", None),
        "v_cores": getattr(mi, "v_cores", None),
        "storage_size_in_gb": getattr(mi, "storage_size_in_gb", None),
        "sku": {
            "name": _get(sku, "name"),
            "tier": _get(sku, "tier"),
        } if sku else None,
    }
    return {
        "resource_id": None,
        "server": server,
        "parameters": [],
        "parameters_non_default": [],
    }


def _single_server_to_dict(server: Any) -> dict:
    """Flatten an RDBMS single-server Server model into a plain dict."""
    sku = getattr(server, "sku", None)
    storage = getattr(server, "storage_profile", None)
    return {
        "id": getattr(server, "id", None),
        "name": getattr(server, "name", None),
        "location": getattr(server, "location", None),
        "state": getattr(server, "user_visible_state", None),
        "version": getattr(server, "version", None),
        "fully_qualified_domain_name": getattr(server, "fully_qualified_domain_name", None),
        "administrator_login": getattr(server, "administrator_login", None),
        "sku": {
            "name": _get(sku, "name"),
            "tier": _get(sku, "tier"),
            "capacity": _get(sku, "capacity"),
        } if sku else None,
        "storage": {
            "storage_mb": _get(storage, "storage_mb"),
            "auto_grow": _get(storage, "storage_autogrow"),
            "backup_retention_days": _get(storage, "backup_retention_days"),
            "geo_redundant_backup": _get(storage, "geo_redundant_backup"),
        } if storage else None,
    }


def _collect_single_server(client: Any, params: dict) -> dict:
    """Collect inventory for an Azure Database for PostgreSQL/MySQL single server."""
    rg = params["resource_group"]
    server_name = params["server_name"]
    server_obj = client.servers.get(rg, server_name)
    server_dict = _single_server_to_dict(server_obj)

    parameters = [
        configuration_to_dict(c)
        for c in client.configurations.list_by_server(rg, server_name)
    ]

    return {
        "resource_id": server_dict["id"],
        "server": server_dict,
        "parameters": parameters,
        "parameters_non_default": [p for p in parameters if p["is_non_default"]],
    }


# --------------------------------------------------------------------------- #
# AzureInventoryAdapter                                                        #
# --------------------------------------------------------------------------- #


class AzureInventoryAdapter:
    """InventoryAdapter for Azure DB services.

    Implements the InventoryAdapter protocol: ``collect(target) -> dict``.

    Supported services: postgres-flexible, mysql-flexible, cosmos-postgres,
    sql-database, sql-managed-instance, single-server.
    """

    def __init__(self, credential: Any, service: str, subscription_id: str) -> None:
        self._credential = credential
        self._service = service
        self._subscription_id = subscription_id

    def collect(self, target: Target) -> dict:
        """Collect inventory for the target, overriding resource_id with ARM id."""
        # single-server requires params to select the correct rdbms client;
        # all other services use the 3-arg form so T5 monkeypatches stay green.
        if self._service == "single-server":
            client = create_mgmt_client(
                self._service,
                self._credential,
                self._subscription_id,
                params=target.params,
            )
        else:
            client = create_mgmt_client(
                self._service, self._credential, self._subscription_id
            )

        if self._service in ("postgres-flexible", "mysql-flexible"):
            rg = target.params["resource_group"]
            name = target.params["server_name"]
            result = collect_inventory(client, rg, name)
        elif self._service == "cosmos-postgres":
            result = _collect_cosmos_postgres(client, target.params)
        elif self._service == "sql-database":
            result = _collect_sql_database(client, target.params)
        elif self._service == "sql-managed-instance":
            result = _collect_sql_managed_instance(client, target.params)
        elif self._service == "single-server":
            result = _collect_single_server(client, target.params)
        else:
            raise ValueError(f"AzureInventoryAdapter: unknown service '{self._service}'")

        result["resource_id"] = azure_resource_id(
            self._service, self._subscription_id, target.params
        )
        return result
