"""Tests for db_metrics.providers.registry.

Ruling A: assert only the two flexible services now registered;
the all-8 assertion is added in a later task.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from db_metrics.models import Target


def _make_target(service: str = "postgres-flexible") -> Target:
    return Target(
        name="t",
        cloud="azure",
        service=service,
        params={
            "subscription": "s",
            "resource_group": "rg",
            "server_name": "srv",
        },
    )


def _make_credentials():
    # MetricsQueryClient validates get_token at construction, so the fake
    # credential must expose that method even though no network call is made.
    fake_cred = SimpleNamespace(get_token=lambda *a, **kw: None)
    return SimpleNamespace(credential=fake_cred, subscription_id="sub-guid")


# ---------------------------------------------------------------------------
# SERVICES dict
# ---------------------------------------------------------------------------


def test_services_for_cloud_azure():
    from db_metrics.providers.registry import services_for_cloud

    azure = services_for_cloud("azure")
    assert set(azure) == {
        "postgres-flexible",
        "mysql-flexible",
        "cosmos-postgres",
        "sql-database",
        "sql-managed-instance",
        "single-server",
    }


def test_services_for_cloud_aws():
    from db_metrics.providers.registry import services_for_cloud

    assert services_for_cloud("aws") == ["aurora", "rds"]


def test_registry_contains_flexible_services():
    from db_metrics.providers import registry

    assert {"postgres-flexible", "mysql-flexible"} <= set(registry.SERVICES)


def test_registry_services_have_required_keys():
    from db_metrics.providers import registry

    for svc, meta in registry.SERVICES.items():
        assert "cloud" in meta, f"{svc} missing 'cloud'"
        assert "required_params" in meta, f"{svc} missing 'required_params'"
        assert "build" in meta, f"{svc} missing 'build'"


# ---------------------------------------------------------------------------
# build_providers happy path (offline construction)
# ---------------------------------------------------------------------------


def test_build_providers_returns_azure_provider_pair():
    from db_metrics.providers import registry
    from db_metrics.providers.azure.inventory import AzureInventoryAdapter
    from db_metrics.providers.azure.monitor import AzureMonitorSource

    target = _make_target("postgres-flexible")
    credentials = _make_credentials()

    source, adapter = registry.build_providers(target, credentials)

    assert isinstance(source, AzureMonitorSource)
    assert isinstance(adapter, AzureInventoryAdapter)


def test_build_providers_sets_resource_id_on_target_params():
    from db_metrics.providers import registry
    from db_metrics.providers.azure.inventory import azure_resource_id

    target = _make_target("postgres-flexible")
    credentials = _make_credentials()

    registry.build_providers(target, credentials)

    expected_rid = azure_resource_id(
        "postgres-flexible",
        credentials.subscription_id,
        target.params,
    )
    assert target.params["resource_id"] == expected_rid


def test_build_providers_mysql_flexible_returns_provider_pair():
    from db_metrics.providers import registry
    from db_metrics.providers.azure.inventory import AzureInventoryAdapter
    from db_metrics.providers.azure.monitor import AzureMonitorSource

    target = _make_target("mysql-flexible")
    credentials = _make_credentials()

    source, adapter = registry.build_providers(target, credentials)

    assert isinstance(source, AzureMonitorSource)
    assert isinstance(adapter, AzureInventoryAdapter)


# ---------------------------------------------------------------------------
# build_providers error cases
# ---------------------------------------------------------------------------


def test_build_providers_raises_on_unknown_service():
    from db_metrics.providers import registry

    target = _make_target("rds")  # not registered yet
    credentials = _make_credentials()

    with pytest.raises(ValueError, match="rds"):
        registry.build_providers(target, credentials)


def test_build_providers_error_message_lists_known_services():
    from db_metrics.providers import registry

    target = _make_target("unknown-db")
    credentials = _make_credentials()

    with pytest.raises(ValueError) as exc_info:
        registry.build_providers(target, credentials)

    msg = str(exc_info.value)
    assert "unknown-db" in msg
    # known services should be mentioned
    assert "postgres-flexible" in msg or "mysql-flexible" in msg


def test_build_providers_raises_on_missing_required_param():
    from db_metrics.providers import registry

    target = Target(
        name="t",
        cloud="azure",
        service="postgres-flexible",
        params={
            "subscription": "s",
            "resource_group": "rg",
            # server_name intentionally omitted
        },
    )
    credentials = _make_credentials()

    with pytest.raises(ValueError, match="server_name"):
        registry.build_providers(target, credentials)


def test_build_providers_raises_naming_target_on_missing_param():
    from db_metrics.providers import registry

    target = Target(
        name="my-server",
        cloud="azure",
        service="postgres-flexible",
        params={"subscription": "s"},  # resource_group and server_name missing
    )
    credentials = _make_credentials()

    with pytest.raises(ValueError) as exc_info:
        registry.build_providers(target, credentials)

    msg = str(exc_info.value)
    assert "my-server" in msg


# ---------------------------------------------------------------------------
# All-8 services assertion (Task 13)
# ---------------------------------------------------------------------------


def test_registry_lists_all_services():
    from db_metrics.providers import registry

    assert set(registry.SERVICES) == {
        "postgres-flexible",
        "mysql-flexible",
        "cosmos-postgres",
        "sql-database",
        "sql-managed-instance",
        "single-server",
        "rds",
        "aurora",
    }


# ---------------------------------------------------------------------------
# build_providers — aurora service (Task 13)
# ---------------------------------------------------------------------------


def _make_aws_aurora_target() -> Target:
    return Target(
        name="t",
        cloud="aws",
        service="aurora",
        params={"profile": "p", "region": "r", "cluster_identifier": "myclu"},
    )


def _make_aws_credentials():
    return SimpleNamespace(cloudwatch=SimpleNamespace(), rds=SimpleNamespace())


def test_build_providers_aurora_returns_cloudwatch_source():
    from db_metrics.providers import registry
    from db_metrics.providers.aws.cloudwatch import CloudWatchSource

    source, _ = registry.build_providers(_make_aws_aurora_target(), _make_aws_credentials())
    assert isinstance(source, CloudWatchSource)


def test_build_providers_aurora_returns_aurora_adapter():
    from db_metrics.providers import registry
    from db_metrics.providers.aws.inventory import AuroraInventoryAdapter

    _, adapter = registry.build_providers(_make_aws_aurora_target(), _make_aws_credentials())
    assert isinstance(adapter, AuroraInventoryAdapter)


def test_build_providers_aurora_sets_dimension_params():
    from db_metrics.providers import registry

    target = _make_aws_aurora_target()
    registry.build_providers(target, _make_aws_credentials())
    assert target.params["dimension_name"] == "DBClusterIdentifier"
    assert target.params["dimension_value"] == "myclu"


def test_build_providers_rds_allows_ambient_profile_and_region():
    """rds must not require profile/region: boto3 resolves them from the
    default profile or AWS_REGION/AWS_DEFAULT_REGION env vars."""
    from db_metrics.providers import registry
    from db_metrics.providers.aws.cloudwatch import CloudWatchSource
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    target = Target(
        name="t", cloud="aws", service="rds",
        params={"identifier": "mydb"},  # no profile, no region
    )
    credentials = SimpleNamespace(cloudwatch=SimpleNamespace(), rds=SimpleNamespace())
    source, adapter = registry.build_providers(target, credentials)
    assert isinstance(source, CloudWatchSource)
    assert isinstance(adapter, RdsInventoryAdapter)


def test_build_providers_aurora_allows_ambient_profile_and_region():
    from db_metrics.providers import registry
    from db_metrics.providers.aws.inventory import AuroraInventoryAdapter

    target = Target(
        name="t", cloud="aws", service="aurora",
        params={"cluster_identifier": "myclu"},  # no profile, no region
    )
    credentials = SimpleNamespace(cloudwatch=SimpleNamespace(), rds=SimpleNamespace())
    _, adapter = registry.build_providers(target, credentials)
    assert isinstance(adapter, AuroraInventoryAdapter)


def test_build_providers_rds_still_requires_identifier():
    from db_metrics.providers import registry

    target = Target(name="t", cloud="aws", service="rds", params={})
    credentials = SimpleNamespace(cloudwatch=SimpleNamespace(), rds=SimpleNamespace())
    with pytest.raises(ValueError, match="identifier"):
        registry.build_providers(target, credentials)


def test_build_providers_rds_regression():
    """Regression: rds still wires up RdsInventoryAdapter with DBInstanceIdentifier."""
    from db_metrics.providers import registry
    from db_metrics.providers.aws.cloudwatch import CloudWatchSource
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    target = Target(
        name="t", cloud="aws", service="rds",
        params={"profile": "p", "region": "r", "identifier": "mydb"},
    )
    credentials = SimpleNamespace(cloudwatch=SimpleNamespace(), rds=SimpleNamespace())
    source, adapter = registry.build_providers(target, credentials)
    assert isinstance(source, CloudWatchSource)
    assert isinstance(adapter, RdsInventoryAdapter)
    assert target.params["dimension_name"] == "DBInstanceIdentifier"
    assert target.params["dimension_value"] == "mydb"
