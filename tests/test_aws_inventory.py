"""Tests for RdsInventoryAdapter and registry rds entry.

TDD: this file is written before db_metrics/providers/aws/inventory.py exists,
so the initial run will be RED (ImportError / AssertionError).
"""

from __future__ import annotations

import pytest
from types import SimpleNamespace

from db_metrics.models import Target


# ---------------------------------------------------------------------------
# Fake data
# ---------------------------------------------------------------------------

FAKE_DB_INSTANCE = {
    "DBInstanceIdentifier": "mydb",
    "Engine": "postgres",
    "EngineVersion": "14.7",
    "DBInstanceClass": "db.t3.medium",
    "AllocatedStorage": 100,
    "Iops": 3000,
    "MultiAZ": True,
    "StorageType": "gp3",
    "DBInstanceStatus": "available",
    "AvailabilityZone": "us-east-1a",
    "StorageEncrypted": True,
    "BackupRetentionPeriod": 7,
    "EngineLifecycleSupport": "open-source-rds-extended-support",
    "DBParameterGroups": [{"DBParameterGroupName": "default.postgres14"}],
}

PARAM_PAGE_1 = {
    "Parameters": [
        {
            "ParameterName": "max_connections",
            "ParameterValue": "100",
            "Source": "user",
            "ApplyType": "static",
            "DataType": "integer",
            "IsModifiable": True,
            "Description": "Max connections",
        }
    ],
    "Marker": "next-page",
}

PARAM_PAGE_2 = {
    "Parameters": [
        {
            "ParameterName": "shared_buffers",
            "ParameterValue": "128MB",
            "Source": "system",
            "ApplyType": "static",
            "DataType": "string",
            "IsModifiable": False,
            "Description": "Shared buffers",
        }
    ],
    # No Marker — last page
}


# ---------------------------------------------------------------------------
# Fake RDS client
# ---------------------------------------------------------------------------


class FakeRdsClient:
    """Minimal boto3 rds client fake.

    - describe_db_instances: returns a single canned DBInstance.
    - describe_db_parameters: returns page 1 (with Marker) on the first call,
      page 2 (no Marker) on subsequent calls.  If error_on_params is True,
      raises on any describe_db_parameters call to exercise the fallback path.
    """

    def __init__(self, db_instance: dict | None = None, error_on_params: bool = False) -> None:
        self._db_instance = db_instance if db_instance is not None else FAKE_DB_INSTANCE
        self._error_on_params = error_on_params

    def describe_db_instances(self, DBInstanceIdentifier: str) -> dict:
        return {"DBInstances": [self._db_instance]}

    def describe_db_parameters(self, DBParameterGroupName: str, Marker: str | None = None) -> dict:
        if self._error_on_params:
            raise Exception("AccessDenied: describe_db_parameters not allowed")
        # First page has Marker, second page does not
        if Marker is None:
            return PARAM_PAGE_1
        return PARAM_PAGE_2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_target() -> Target:
    return Target(
        name="t",
        cloud="aws",
        service="rds",
        params={"profile": "p", "region": "r", "identifier": "mydb"},
    )


# ---------------------------------------------------------------------------
# RdsInventoryAdapter — metric_scope
# ---------------------------------------------------------------------------


def test_collect_returns_metric_scope_dimension_name():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    adapter = RdsInventoryAdapter(FakeRdsClient())
    result = adapter.collect(_make_target())
    assert result["metric_scope"]["dimension_name"] == "DBInstanceIdentifier"


def test_collect_returns_metric_scope_dimension_value():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    adapter = RdsInventoryAdapter(FakeRdsClient())
    result = adapter.collect(_make_target())
    assert result["metric_scope"]["dimension_value"] == "mydb"


# ---------------------------------------------------------------------------
# RdsInventoryAdapter — server field flattening
# ---------------------------------------------------------------------------


def test_collect_server_name_is_identifier():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    assert result["server"]["name"] == "mydb"


def test_collect_server_engine():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    assert result["server"]["engine"] == "postgres"


def test_collect_server_engine_version():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    assert result["server"]["engine_version"] == "14.7"


def test_collect_server_class():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    assert result["server"]["class"] == "db.t3.medium"


def test_collect_server_allocated_storage_gb():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    assert result["server"]["allocated_storage_gb"] == 100


def test_collect_server_iops():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    assert result["server"]["iops"] == 3000


def test_collect_server_multi_az():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    assert result["server"]["multi_az"] is True


def test_collect_server_storage_type():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    assert result["server"]["storage_type"] == "gp3"


def test_collect_server_instance_status():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    assert result["server"]["instance_status"] == "available"


def test_collect_server_availability_zone():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    assert result["server"]["availability_zone"] == "us-east-1a"


def test_collect_server_storage_encrypted():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    assert result["server"]["storage_encrypted"] is True


def test_collect_server_backup_retention_days():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    assert result["server"]["backup_retention_days"] == 7


def test_collect_server_engine_lifecycle():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    assert result["server"]["engine_lifecycle"] == "open-source-rds-extended-support"


# ---------------------------------------------------------------------------
# RdsInventoryAdapter — parameters pagination
# ---------------------------------------------------------------------------


def test_collect_paginates_parameters_across_both_pages():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    params = result["parameters"]
    names = [p["name"] for p in params]
    assert "max_connections" in names
    assert "shared_buffers" in names
    assert len(params) == 2


def test_collect_parameter_flattened_fields():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    max_conn = next(p for p in result["parameters"] if p["name"] == "max_connections")
    assert max_conn["value"] == "100"
    assert max_conn["source"] == "user"
    assert max_conn["apply_type"] == "static"
    assert max_conn["data_type"] == "integer"
    assert max_conn["is_modifiable"] is True
    assert max_conn["description"] == "Max connections"


# ---------------------------------------------------------------------------
# RdsInventoryAdapter — error tolerance
# ---------------------------------------------------------------------------


def test_collect_parameters_empty_on_describe_failure():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    adapter = RdsInventoryAdapter(FakeRdsClient(error_on_params=True))
    result = adapter.collect(_make_target())
    assert result["parameters"] == []


def test_collect_parameters_empty_when_no_param_groups():
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    instance_no_groups = {**FAKE_DB_INSTANCE, "DBParameterGroups": []}
    adapter = RdsInventoryAdapter(FakeRdsClient(db_instance=instance_no_groups))
    result = adapter.collect(_make_target())
    assert result["parameters"] == []


def test_collect_has_no_databases_key():
    """RDS instance API has no database listing — spec-correct absence."""
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    result = RdsInventoryAdapter(FakeRdsClient()).collect(_make_target())
    assert "databases" not in result


# ---------------------------------------------------------------------------
# Registry — rds entry
# ---------------------------------------------------------------------------


def test_rds_registered_in_services():
    from db_metrics.providers import registry

    assert "rds" in registry.SERVICES


def test_rds_registry_cloud_is_aws():
    from db_metrics.providers import registry

    assert registry.SERVICES["rds"]["cloud"] == "aws"


def test_rds_registry_required_params():
    from db_metrics.providers import registry

    # profile/region are optional (resolved from the default AWS profile or
    # AWS_REGION/AWS_DEFAULT_REGION); only the instance identifier is required.
    required = set(registry.SERVICES["rds"]["required_params"])
    assert required == {"identifier"}


def test_build_providers_rds_returns_cloudwatch_source():
    from db_metrics.providers import registry
    from db_metrics.providers.aws.cloudwatch import CloudWatchSource

    target = _make_target()
    credentials = SimpleNamespace(cloudwatch=SimpleNamespace(), rds=FakeRdsClient())
    source, _adapter = registry.build_providers(target, credentials)
    assert isinstance(source, CloudWatchSource)


def test_build_providers_rds_returns_rds_inventory_adapter():
    from db_metrics.providers import registry
    from db_metrics.providers.aws.inventory import RdsInventoryAdapter

    target = _make_target()
    credentials = SimpleNamespace(cloudwatch=SimpleNamespace(), rds=FakeRdsClient())
    _source, adapter = registry.build_providers(target, credentials)
    assert isinstance(adapter, RdsInventoryAdapter)


def test_build_providers_rds_sets_dimension_name():
    from db_metrics.providers import registry

    target = _make_target()
    credentials = SimpleNamespace(cloudwatch=SimpleNamespace(), rds=FakeRdsClient())
    registry.build_providers(target, credentials)
    assert target.params["dimension_name"] == "DBInstanceIdentifier"


def test_build_providers_rds_sets_dimension_value():
    from db_metrics.providers import registry

    target = _make_target()
    credentials = SimpleNamespace(cloudwatch=SimpleNamespace(), rds=FakeRdsClient())
    registry.build_providers(target, credentials)
    assert target.params["dimension_value"] == "mydb"


# ---------------------------------------------------------------------------
# Fake Aurora data
# ---------------------------------------------------------------------------

FAKE_AURORA_CLUSTER = {
    "DBClusterIdentifier": "myclu",
    "Engine": "aurora-postgresql",
    "EngineVersion": "14.5",
    "EngineMode": "provisioned",
    "Status": "available",
    "MultiAZ": True,
    "ServerlessV2ScalingConfiguration": {
        "MinCapacity": 0.5,
        "MaxCapacity": 16.0,
    },
    "DBClusterMembers": [
        {"DBInstanceIdentifier": "myclu-instance-1", "IsClusterWriter": True},
        {"DBInstanceIdentifier": "myclu-instance-2", "IsClusterWriter": False},
    ],
}

FAKE_AURORA_INSTANCES = {
    "myclu-instance-1": {
        "DBInstanceIdentifier": "myclu-instance-1",
        "DBInstanceClass": "db.r6g.large",
        "Engine": "aurora-postgresql",
        "EngineVersion": "14.5",
        "DBInstanceStatus": "available",
        "AvailabilityZone": "us-east-1a",
        "StorageType": "aurora",
    },
    "myclu-instance-2": {
        "DBInstanceIdentifier": "myclu-instance-2",
        "DBInstanceClass": "db.r6g.large",
        "Engine": "aurora-postgresql",
        "EngineVersion": "14.5",
        "DBInstanceStatus": "available",
        "AvailabilityZone": "us-east-1b",
        "StorageType": "aurora",
    },
}


class FakeAuroraRdsClient:
    """Minimal boto3 RDS client fake for Aurora cluster operations.

    - describe_db_clusters: returns a canned cluster dict.
    - describe_db_instances: returns member instance details by identifier,
      or raises if the identifier is in fail_instance_ids.
    """

    def __init__(
        self,
        cluster: dict | None = None,
        instances: dict | None = None,
        fail_instance_ids: set | None = None,
    ) -> None:
        self._cluster = cluster if cluster is not None else FAKE_AURORA_CLUSTER
        self._instances = instances if instances is not None else FAKE_AURORA_INSTANCES
        self._fail_instance_ids = fail_instance_ids or set()

    def describe_db_clusters(self, DBClusterIdentifier: str) -> dict:
        return {"DBClusters": [self._cluster]}

    def describe_db_instances(self, DBInstanceIdentifier: str) -> dict:
        if DBInstanceIdentifier in self._fail_instance_ids:
            raise Exception(f"DBInstance {DBInstanceIdentifier} not found")
        return {"DBInstances": [self._instances[DBInstanceIdentifier]]}


def _make_aurora_target() -> Target:
    return Target(
        name="t",
        cloud="aws",
        service="aurora",
        params={"profile": "p", "region": "r", "cluster_identifier": "myclu"},
    )


# ---------------------------------------------------------------------------
# AuroraInventoryAdapter — metric_scope and server fields
# ---------------------------------------------------------------------------


def test_aurora_collect_metric_scope():
    from db_metrics.providers.aws.inventory import AuroraInventoryAdapter

    result = AuroraInventoryAdapter(FakeAuroraRdsClient()).collect(_make_aurora_target())
    scope = result["metric_scope"]
    assert scope["dimension_name"] == "DBClusterIdentifier"
    assert scope["dimension_value"] == "myclu"


def test_aurora_collect_server_fields():
    from db_metrics.providers.aws.inventory import AuroraInventoryAdapter

    server = AuroraInventoryAdapter(FakeAuroraRdsClient()).collect(_make_aurora_target())["server"]
    assert server == {
        **{k: server[k] for k in server},  # snapshot
        "name": "myclu",
        "engine": "aurora-postgresql",
        "engine_version": "14.5",
        "engine_mode": "provisioned",
        "status": "available",
        "multi_az": True,
        "members": server["members"],
        "serverless_v2": {"min_acu": 0.5, "max_acu": 16.0},
    }


# ---------------------------------------------------------------------------
# AuroraInventoryAdapter — members enrichment
# ---------------------------------------------------------------------------


def test_aurora_collect_members_count_and_writer():
    from db_metrics.providers.aws.inventory import AuroraInventoryAdapter

    members = AuroraInventoryAdapter(FakeAuroraRdsClient()).collect(_make_aurora_target())["server"]["members"]
    assert len(members) == 2
    writers = [m for m in members if m["is_writer"]]
    readers = [m for m in members if not m["is_writer"]]
    assert len(writers) == 1
    assert len(readers) == 1
    assert writers[0]["identifier"] == "myclu-instance-1"


def test_aurora_collect_member_enrichment():
    from db_metrics.providers.aws.inventory import AuroraInventoryAdapter

    members = AuroraInventoryAdapter(FakeAuroraRdsClient()).collect(_make_aurora_target())["server"]["members"]
    writer = next(m for m in members if m["identifier"] == "myclu-instance-1")
    reader = next(m for m in members if m["identifier"] == "myclu-instance-2")
    # Writer fully enriched
    assert writer["class"] == "db.r6g.large"
    assert writer["instance_status"] == "available"
    assert writer["availability_zone"] == "us-east-1a"
    # Reader in different AZ
    assert reader["availability_zone"] == "us-east-1b"


# ---------------------------------------------------------------------------
# AuroraInventoryAdapter — serverless_v2 conditional
# ---------------------------------------------------------------------------


def test_aurora_collect_serverless_v2_present():
    from db_metrics.providers.aws.inventory import AuroraInventoryAdapter

    sv2 = AuroraInventoryAdapter(FakeAuroraRdsClient()).collect(_make_aurora_target())["server"]["serverless_v2"]
    assert sv2 == {"min_acu": 0.5, "max_acu": 16.0}


def test_aurora_collect_serverless_v2_absent():
    from db_metrics.providers.aws.inventory import AuroraInventoryAdapter

    cluster_no_sv2 = {k: v for k, v in FAKE_AURORA_CLUSTER.items() if k != "ServerlessV2ScalingConfiguration"}
    server = AuroraInventoryAdapter(FakeAuroraRdsClient(cluster=cluster_no_sv2)).collect(_make_aurora_target())["server"]
    assert "serverless_v2" not in server


# ---------------------------------------------------------------------------
# AuroraInventoryAdapter — parameters always empty, member failure tolerance
# ---------------------------------------------------------------------------


def test_aurora_collect_parameters_empty():
    from db_metrics.providers.aws.inventory import AuroraInventoryAdapter

    result = AuroraInventoryAdapter(FakeAuroraRdsClient()).collect(_make_aurora_target())
    assert result["parameters"] == []


def test_aurora_member_instance_failure_falls_back():
    from db_metrics.providers.aws.inventory import AuroraInventoryAdapter

    # instance-2 describe fails; collect should still return 2 members
    client = FakeAuroraRdsClient(fail_instance_ids={"myclu-instance-2"})
    members = AuroraInventoryAdapter(client).collect(_make_aurora_target())["server"]["members"]

    assert len(members) == 2
    failed = next(m for m in members if m["identifier"] == "myclu-instance-2")
    # Fallback: only base fields present
    assert set(failed.keys()) == {"identifier", "is_writer"}
    # Successful member is fully enriched
    ok = next(m for m in members if m["identifier"] == "myclu-instance-1")
    assert "class" in ok and "instance_status" in ok
