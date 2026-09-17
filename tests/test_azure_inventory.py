"""Tests for db_metrics.providers.azure.inventory.

Monkeypatches the module-level create_mgmt_client so no live Azure
calls are made.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from db_metrics.models import Target


def _fake_client():
    """Return a SimpleNamespace mimicking a PG/MySQL management client."""
    server = SimpleNamespace(
        id="/rid",
        name="srv",
        location="eastus2",
        state="Ready",
        version="17",
        minor_version=None,
        fully_qualified_domain_name=None,
        administrator_login=None,
        availability_zone=None,
        sku=None,
        storage=None,
        high_availability=None,
        backup=None,
        network=None,
        maintenance_window=None,
    )
    return SimpleNamespace(
        servers=SimpleNamespace(get=lambda rg, n: server),
        configurations=SimpleNamespace(
            list_by_server=lambda rg, n: [
                SimpleNamespace(
                    name="work_mem",
                    value="8192",
                    default_value="4096",
                    source="user",
                    is_dynamic_config=True,
                    is_read_only=False,
                    unit="kb",
                    description="d",
                ),
            ]
        ),
        databases=SimpleNamespace(
            list_by_server=lambda rg, n: [SimpleNamespace(name="appdb")]
        ),
    )


def _make_target() -> Target:
    return Target(
        name="t",
        cloud="azure",
        service="postgres-flexible",
        params={"resource_group": "rg", "server_name": "srv"},
    )


# ---------------------------------------------------------------------------
# AzureInventoryAdapter.collect
# ---------------------------------------------------------------------------


def test_adapter_collect_flattens_server_and_parameters(monkeypatch):
    import db_metrics.providers.azure.inventory as inv_mod
    from db_metrics.providers.azure.inventory import AzureInventoryAdapter

    monkeypatch.setattr(inv_mod, "create_mgmt_client", lambda svc, cred, sub: _fake_client())

    adapter = AzureInventoryAdapter(object(), "postgres-flexible", "sub-guid")
    result = adapter.collect(_make_target())

    assert result["server"]["name"] == "srv"
    assert result["databases"] == ["appdb"]
    assert len(result["parameters_non_default"]) == 1
    assert result["parameters"][0]["name"] == "work_mem"


def test_adapter_collect_overrides_resource_id_with_arm_template(monkeypatch):
    """resource_id must be the computed ARM id, NOT the fake server's '/rid'."""
    import db_metrics.providers.azure.inventory as inv_mod
    from db_metrics.providers.azure.inventory import (
        AzureInventoryAdapter,
        azure_resource_id,
    )

    monkeypatch.setattr(inv_mod, "create_mgmt_client", lambda svc, cred, sub: _fake_client())

    target = _make_target()
    adapter = AzureInventoryAdapter(object(), "postgres-flexible", "sub-guid")
    result = adapter.collect(target)

    expected_rid = azure_resource_id("postgres-flexible", "sub-guid", target.params)
    assert result["resource_id"] == expected_rid
    # Must NOT be the fake server id
    assert result["resource_id"] != "/rid"


def test_arm_resource_id_postgres_flexible():
    from db_metrics.providers.azure.inventory import azure_resource_id

    rid = azure_resource_id(
        "postgres-flexible",
        "sub-123",
        {"resource_group": "my-rg", "server_name": "my-srv"},
    )
    assert rid == (
        "/subscriptions/sub-123/resourceGroups/my-rg"
        "/providers/Microsoft.DBforPostgreSQL/flexibleServers/my-srv"
    )


def test_arm_resource_id_mysql_flexible():
    from db_metrics.providers.azure.inventory import azure_resource_id

    rid = azure_resource_id(
        "mysql-flexible",
        "sub-456",
        {"resource_group": "rg2", "server_name": "mysql-srv"},
    )
    assert rid == (
        "/subscriptions/sub-456/resourceGroups/rg2"
        "/providers/Microsoft.DBforMySQL/flexibleServers/mysql-srv"
    )


def test_adapter_collect_uses_module_level_factory(monkeypatch):
    """create_mgmt_client (module-level) is called with the right arguments."""
    import db_metrics.providers.azure.inventory as inv_mod
    from db_metrics.providers.azure.inventory import AzureInventoryAdapter

    calls = {}

    def recording_factory(svc, cred, sub):
        calls["svc"] = svc
        calls["sub"] = sub
        return _fake_client()

    monkeypatch.setattr(inv_mod, "create_mgmt_client", recording_factory)

    cred = object()
    adapter = AzureInventoryAdapter(cred, "postgres-flexible", "my-sub")
    adapter.collect(_make_target())

    assert calls["svc"] == "postgres-flexible"
    assert calls["sub"] == "my-sub"


# ---------------------------------------------------------------------------
# Task 6: per-service RID builders
# ---------------------------------------------------------------------------


def test_arm_resource_id_cosmos_postgres():
    from db_metrics.providers.azure.inventory import azure_resource_id

    rid = azure_resource_id(
        "cosmos-postgres",
        "sub-789",
        {"resource_group": "rg3", "cluster_name": "my-cluster"},
    )
    assert rid == (
        "/subscriptions/sub-789/resourceGroups/rg3"
        "/providers/Microsoft.DBforPostgreSQL/serverGroupsv2/my-cluster"
    )


def test_arm_resource_id_sql_database():
    from db_metrics.providers.azure.inventory import azure_resource_id

    rid = azure_resource_id(
        "sql-database",
        "sub-001",
        {"resource_group": "rg4", "server_name": "sql-srv", "database": "mydb"},
    )
    assert rid == (
        "/subscriptions/sub-001/resourceGroups/rg4"
        "/providers/Microsoft.Sql/servers/sql-srv/databases/mydb"
    )


def test_arm_resource_id_sql_managed_instance():
    from db_metrics.providers.azure.inventory import azure_resource_id

    rid = azure_resource_id(
        "sql-managed-instance",
        "sub-002",
        {"resource_group": "rg5", "instance_name": "my-mi"},
    )
    assert rid == (
        "/subscriptions/sub-002/resourceGroups/rg5"
        "/providers/Microsoft.Sql/managedInstances/my-mi"
    )


def test_arm_resource_id_single_server_postgresql():
    from db_metrics.providers.azure.inventory import azure_resource_id

    rid = azure_resource_id(
        "single-server",
        "sub-003",
        {"resource_group": "rg6", "server_name": "pg-single", "sub_engine": "postgresql"},
    )
    assert rid == (
        "/subscriptions/sub-003/resourceGroups/rg6"
        "/providers/Microsoft.DBforPostgreSQL/servers/pg-single"
    )


def test_arm_resource_id_single_server_mysql():
    from db_metrics.providers.azure.inventory import azure_resource_id

    rid = azure_resource_id(
        "single-server",
        "sub-004",
        {"resource_group": "rg7", "server_name": "my-single", "sub_engine": "mysql"},
    )
    assert rid == (
        "/subscriptions/sub-004/resourceGroups/rg7"
        "/providers/Microsoft.DBforMySQL/servers/my-single"
    )


# ---------------------------------------------------------------------------
# Task 6: per-service adapter collect
# ---------------------------------------------------------------------------


def _fake_cosmos_client():
    """Return a SimpleNamespace mimicking a CosmosDB for PostgreSQL client."""
    cluster = SimpleNamespace(
        id="/cluster-rid",
        name="my-cluster",
        location="westeurope",
        state="Ready",
        postgresql_version="15",
        citus_version="12.1",
        enable_ha=True,
        coordinator_storage_quota_in_mb=131072,
        coordinator_v_cores=4,
        node_count=2,
        node_v_cores=4,
        node_storage_quota_in_mb=524288,
    )
    return SimpleNamespace(
        clusters=SimpleNamespace(get=lambda rg, name: cluster),
    )


def _fake_sql_db_client():
    """Return a SimpleNamespace mimicking a SQL management client for DB."""
    db = SimpleNamespace(
        id="/sql-db-rid",
        name="mydb",
        location="eastus",
        status="Online",
        max_size_bytes=107374182400,
        current_service_objective_name="S3",
        sku=SimpleNamespace(name="Standard", tier="Standard", capacity=100),
    )
    return SimpleNamespace(
        databases=SimpleNamespace(get=lambda rg, srv, db_name: db),
    )


def _fake_sql_mi_client():
    """Return a SimpleNamespace mimicking a SQL management client for MI."""
    mi = SimpleNamespace(
        id="/sql-mi-rid",
        name="my-mi",
        location="northeurope",
        state="Ready",
        v_cores=8,
        storage_size_in_gb=512,
        sku=SimpleNamespace(name="GP_Gen5_8", tier="GeneralPurpose"),
    )
    return SimpleNamespace(
        managed_instances=SimpleNamespace(get=lambda rg, name: mi),
    )


def _fake_single_server_client():
    """Return a SimpleNamespace mimicking an RDBMS single-server client."""
    storage = SimpleNamespace(
        storage_mb=51200,
        storage_autogrow="Enabled",
        backup_retention_days=7,
        geo_redundant_backup="Disabled",
    )
    server = SimpleNamespace(
        id="/single-srv-rid",
        name="pg-single",
        location="uksouth",
        user_visible_state="Ready",
        version="11",
        fully_qualified_domain_name="pg-single.postgres.database.azure.com",
        administrator_login="adminuser",
        sku=SimpleNamespace(name="GP_Gen5_4", tier="GeneralPurpose", capacity=4),
        storage_profile=storage,
    )
    configs = [
        SimpleNamespace(
            name="log_connections",
            value="on",
            default_value="off",
            source="user-override",
            is_dynamic_config=None,
            is_read_only=None,
            unit=None,
            description="Log connections",
        ),
    ]
    return SimpleNamespace(
        servers=SimpleNamespace(get=lambda rg, name: server),
        configurations=SimpleNamespace(list_by_server=lambda rg, name: configs),
    )


def test_adapter_collect_cosmos_postgres(monkeypatch):
    import db_metrics.providers.azure.inventory as inv_mod
    from db_metrics.providers.azure.inventory import AzureInventoryAdapter

    monkeypatch.setattr(inv_mod, "create_mgmt_client", lambda svc, cred, sub: _fake_cosmos_client())

    target = Target(
        name="t",
        cloud="azure",
        service="cosmos-postgres",
        params={"resource_group": "rg3", "cluster_name": "my-cluster"},
    )
    adapter = AzureInventoryAdapter(object(), "cosmos-postgres", "sub-789")
    result = adapter.collect(target)

    expected_rid = (
        "/subscriptions/sub-789/resourceGroups/rg3"
        "/providers/Microsoft.DBforPostgreSQL/serverGroupsv2/my-cluster"
    )
    assert result["resource_id"] == expected_rid
    assert result["server"]["name"] == "my-cluster"
    assert result["server"]["location"] == "westeurope"
    assert result["server"]["state"] == "Ready"
    assert result["server"]["postgresql_version"] == "15"
    assert result["server"]["coordinator_v_cores"] == 4
    assert result["parameters"] == []


def test_adapter_collect_sql_database(monkeypatch):
    import db_metrics.providers.azure.inventory as inv_mod
    from db_metrics.providers.azure.inventory import AzureInventoryAdapter

    monkeypatch.setattr(inv_mod, "create_mgmt_client", lambda svc, cred, sub: _fake_sql_db_client())

    target = Target(
        name="t",
        cloud="azure",
        service="sql-database",
        params={"resource_group": "rg4", "server_name": "sql-srv", "database": "mydb"},
    )
    adapter = AzureInventoryAdapter(object(), "sql-database", "sub-001")
    result = adapter.collect(target)

    expected_rid = (
        "/subscriptions/sub-001/resourceGroups/rg4"
        "/providers/Microsoft.Sql/servers/sql-srv/databases/mydb"
    )
    assert result["resource_id"] == expected_rid
    assert result["server"]["location"] == "eastus"
    assert result["server"]["status"] == "Online"
    assert result["server"]["max_size_bytes"] == 107374182400
    assert result["server"]["current_service_objective_name"] == "S3"
    assert result["server"]["sku"]["name"] == "Standard"
    assert result["server"]["sku"]["tier"] == "Standard"
    assert result["parameters"] == []


def test_adapter_collect_sql_managed_instance(monkeypatch):
    import db_metrics.providers.azure.inventory as inv_mod
    from db_metrics.providers.azure.inventory import AzureInventoryAdapter

    monkeypatch.setattr(inv_mod, "create_mgmt_client", lambda svc, cred, sub: _fake_sql_mi_client())

    target = Target(
        name="t",
        cloud="azure",
        service="sql-managed-instance",
        params={"resource_group": "rg5", "instance_name": "my-mi"},
    )
    adapter = AzureInventoryAdapter(object(), "sql-managed-instance", "sub-002")
    result = adapter.collect(target)

    expected_rid = (
        "/subscriptions/sub-002/resourceGroups/rg5"
        "/providers/Microsoft.Sql/managedInstances/my-mi"
    )
    assert result["resource_id"] == expected_rid
    assert result["server"]["v_cores"] == 8
    assert result["server"]["storage_size_in_gb"] == 512
    assert result["server"]["state"] == "Ready"
    assert result["server"]["sku"]["name"] == "GP_Gen5_8"
    assert result["parameters"] == []


def test_adapter_collect_single_server_postgresql(monkeypatch):
    import db_metrics.providers.azure.inventory as inv_mod
    from db_metrics.providers.azure.inventory import AzureInventoryAdapter

    calls = {}

    def recording_factory(svc, cred, sub, params=None):
        calls["params"] = params
        return _fake_single_server_client()

    monkeypatch.setattr(inv_mod, "create_mgmt_client", recording_factory)

    target = Target(
        name="t",
        cloud="azure",
        service="single-server",
        params={
            "resource_group": "rg6",
            "server_name": "pg-single",
            "sub_engine": "postgresql",
        },
    )
    adapter = AzureInventoryAdapter(object(), "single-server", "sub-003")
    result = adapter.collect(target)

    expected_rid = (
        "/subscriptions/sub-003/resourceGroups/rg6"
        "/providers/Microsoft.DBforPostgreSQL/servers/pg-single"
    )
    assert result["resource_id"] == expected_rid
    assert result["server"]["name"] == "pg-single"
    assert result["server"]["version"] == "11"
    assert result["server"]["state"] == "Ready"
    assert result["server"]["storage"]["storage_mb"] == 51200
    assert result["server"]["sku"]["tier"] == "GeneralPurpose"
    assert len(result["parameters"]) == 1
    assert result["parameters"][0]["name"] == "log_connections"
    assert result["parameters_non_default"][0]["name"] == "log_connections"
    # params kwarg was passed to create_mgmt_client for single-server
    assert calls["params"]["sub_engine"] == "postgresql"


def test_adapter_collect_single_server_mysql(monkeypatch):
    """single-server with sub_engine=mysql produces a MySQL RID."""
    import db_metrics.providers.azure.inventory as inv_mod
    from db_metrics.providers.azure.inventory import AzureInventoryAdapter

    monkeypatch.setattr(
        inv_mod,
        "create_mgmt_client",
        lambda svc, cred, sub, params=None: _fake_single_server_client(),
    )

    target = Target(
        name="t",
        cloud="azure",
        service="single-server",
        params={
            "resource_group": "rg7",
            "server_name": "my-single",
            "sub_engine": "mysql",
        },
    )
    adapter = AzureInventoryAdapter(object(), "single-server", "sub-004")
    result = adapter.collect(target)

    expected_rid = (
        "/subscriptions/sub-004/resourceGroups/rg7"
        "/providers/Microsoft.DBforMySQL/servers/my-single"
    )
    assert result["resource_id"] == expected_rid


# ---------------------------------------------------------------------------
# create_mgmt_client: single-server branch (lines 66-70)
# ---------------------------------------------------------------------------


def test_create_mgmt_client_single_server_dispatches_to_rdbms_client(monkeypatch):
    """create_mgmt_client selects the correct RDBMS client for single-server."""
    import db_metrics.providers.azure.inventory as inv_mod
    from db_metrics.providers.azure.inventory import create_mgmt_client

    created = {}

    def fake_pg_client(cred, sub):
        created["cred"] = cred
        created["sub"] = sub
        return SimpleNamespace(type="pg-rdbms")

    monkeypatch.setitem(inv_mod._RDBMS_CLIENTS, "postgresql", fake_pg_client)

    cred = object()
    result = create_mgmt_client(
        "single-server", cred, "sub-001", params={"sub_engine": "postgresql"}
    )
    assert created["sub"] == "sub-001"
    assert result.type == "pg-rdbms"


def test_create_mgmt_client_flexible_dispatches_to_mgmt_client(monkeypatch):
    """create_mgmt_client uses _MGMT_CLIENTS for flexible-server services."""
    import db_metrics.providers.azure.inventory as inv_mod
    from db_metrics.providers.azure.inventory import create_mgmt_client

    created = {}

    def fake_flex_client(cred, sub):
        created["sub"] = sub
        return SimpleNamespace(type="pg-flex")

    monkeypatch.setitem(inv_mod._MGMT_CLIENTS, "postgres-flexible", fake_flex_client)

    cred = object()
    result = create_mgmt_client("postgres-flexible", cred, "sub-002")
    assert created["sub"] == "sub-002"
    assert result.type == "pg-flex"


# ---------------------------------------------------------------------------
# azure_resource_id: unknown service guard (line 120)
# ---------------------------------------------------------------------------


def test_azure_resource_id_raises_on_unknown_service():
    """azure_resource_id raises ValueError for an unrecognised service."""
    from db_metrics.providers.azure.inventory import azure_resource_id

    with pytest.raises(ValueError, match="unknown service"):
        azure_resource_id("unknown-svc", "sub-001", {"resource_group": "rg"})


# ---------------------------------------------------------------------------
# collect_inventory: database listing exception path (lines 228-229)
# ---------------------------------------------------------------------------


def test_collect_inventory_handles_database_listing_exception():
    """databases field is an error dict when list_by_server raises."""
    from db_metrics.providers.azure.inventory import collect_inventory

    def raise_permission_error(rg, n):
        raise PermissionError("databases access denied")

    server = SimpleNamespace(
        id="/rid",
        name="srv",
        location="eastus2",
        state="Ready",
        version="17",
        minor_version=None,
        fully_qualified_domain_name=None,
        administrator_login=None,
        availability_zone=None,
        sku=None,
        storage=None,
        high_availability=None,
        backup=None,
        network=None,
        maintenance_window=None,
    )
    client = SimpleNamespace(
        servers=SimpleNamespace(get=lambda rg, n: server),
        configurations=SimpleNamespace(list_by_server=lambda rg, n: []),
        databases=SimpleNamespace(list_by_server=raise_permission_error),
    )
    result = collect_inventory(client, "rg", "srv")
    assert isinstance(result["databases"], dict)
    assert "error" in result["databases"]
    assert "denied" in result["databases"]["error"]


# ---------------------------------------------------------------------------
# AzureInventoryAdapter: unknown service guard (line 420)
# ---------------------------------------------------------------------------


def test_adapter_collect_raises_on_unknown_service(monkeypatch):
    """AzureInventoryAdapter.collect raises ValueError for an unknown service."""
    import db_metrics.providers.azure.inventory as inv_mod
    from db_metrics.providers.azure.inventory import AzureInventoryAdapter

    # Patch the factory so the collect method reaches the dispatch block.
    monkeypatch.setattr(inv_mod, "create_mgmt_client", lambda *a, **kw: SimpleNamespace())

    adapter = AzureInventoryAdapter(object(), "unknown-service", "sub")
    target = Target(
        name="t",
        cloud="azure",
        service="unknown-service",
        params={"resource_group": "rg", "server_name": "srv"},
    )
    with pytest.raises(ValueError, match="unknown service"):
        adapter.collect(target)
