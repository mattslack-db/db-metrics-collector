"""RdsInventoryAdapter + AuroraInventoryAdapter: InventoryAdapter implementations for AWS RDS.

RdsInventoryAdapter collects server metadata and parameter group settings for
a standalone RDS instance using the boto3 RDS client (or any compatible fake).

AuroraInventoryAdapter collects cluster metadata and per-member instance details
for an Aurora cluster using describe_db_clusters + describe_db_instances.
"""

from __future__ import annotations

from db_metrics.models import Target


class RdsInventoryAdapter:
    """InventoryAdapter for AWS RDS instances.

    Implements the InventoryAdapter protocol: ``collect(target) -> dict``.

    Parameters
    ----------
    rds_client:
        A boto3 RDS client (or compatible fake) providing
        ``describe_db_instances`` and ``describe_db_parameters``.
    """

    def __init__(self, rds_client: object) -> None:
        self._rds = rds_client

    def collect(self, target: Target) -> dict:
        """Return inventory for the RDS instance identified by target.params["identifier"].

        Returns a dict with keys:
        - ``metric_scope``: dimension_name and dimension_value for CloudWatch queries.
        - ``server``: flattened instance metadata.
        - ``parameters``: list of flattened parameter group entries (paginated).
          Empty list if no parameter group is attached or the fetch fails.
        """
        identifier: str = target.params["identifier"]

        inst: dict = self._rds.describe_db_instances(
            DBInstanceIdentifier=identifier
        )["DBInstances"][0]

        server = {
            "name": identifier,
            **_flatten_instance(inst),
            "allocated_storage_gb": inst.get("AllocatedStorage"),
            "iops": inst.get("Iops"),
            "multi_az": inst.get("MultiAZ"),
            "storage_encrypted": inst.get("StorageEncrypted"),
            "backup_retention_days": inst.get("BackupRetentionPeriod"),
            "engine_lifecycle": inst.get("EngineLifecycleSupport"),
        }

        parameters = _fetch_parameters(self._rds, inst)

        return {
            "metric_scope": {
                "dimension_name": "DBInstanceIdentifier",
                "dimension_value": identifier,
            },
            "server": server,
            "parameters": parameters,
        }


class AuroraInventoryAdapter:
    """InventoryAdapter for AWS Aurora clusters.

    Implements the InventoryAdapter protocol: ``collect(target) -> dict``.

    Fetches cluster-level metadata via ``describe_db_clusters`` and enriches
    each cluster member with per-instance details via ``describe_db_instances``.
    Per-member describe failures are tolerated: the member falls back to its
    basic {identifier, is_writer} shape and collection continues.

    Parameters
    ----------
    rds_client:
        A boto3 RDS client (or compatible fake) providing
        ``describe_db_clusters`` and ``describe_db_instances``.
    """

    def __init__(self, rds_client: object) -> None:
        self._rds = rds_client

    def collect(self, target: Target) -> dict:
        """Return inventory for the Aurora cluster identified by target.params["cluster_identifier"].

        Returns a dict with keys:
        - ``metric_scope``: dimension_name="DBClusterIdentifier" and dimension_value.
        - ``server``: cluster metadata including ``members`` list; ``serverless_v2``
          key is present only when the cluster has a ServerlessV2ScalingConfiguration.
        - ``parameters``: always an empty list (cluster-parameter fetch is out of scope).
        """
        cluster_id: str = target.params["cluster_identifier"]
        cluster: dict = self._rds.describe_db_clusters(
            DBClusterIdentifier=cluster_id
        )["DBClusters"][0]

        members = _collect_members(self._rds, cluster)

        server: dict = {
            "name": cluster_id,
            "engine": cluster.get("Engine"),
            "engine_version": cluster.get("EngineVersion"),
            "engine_mode": cluster.get("EngineMode"),
            "status": cluster.get("Status"),
            "multi_az": cluster.get("MultiAZ"),
            "members": members,
        }

        sv2 = cluster.get("ServerlessV2ScalingConfiguration")
        if sv2:
            server["serverless_v2"] = {
                "min_acu": sv2.get("MinCapacity"),
                "max_acu": sv2.get("MaxCapacity"),
            }

        return {
            "metric_scope": {
                "dimension_name": "DBClusterIdentifier",
                "dimension_value": cluster_id,
            },
            "server": server,
            "parameters": [],
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _flatten_instance(inst: dict) -> dict:
    """Flatten common instance fields shared between RDS and Aurora cluster members.

    Captures the fields that appear on both standalone RDS instances and on the
    per-member ``describe_db_instances`` response for Aurora clusters.
    """
    return {
        "class": inst.get("DBInstanceClass"),
        "engine": inst.get("Engine"),
        "engine_version": inst.get("EngineVersion"),
        "instance_status": inst.get("DBInstanceStatus"),
        "availability_zone": inst.get("AvailabilityZone"),
        "storage_type": inst.get("StorageType"),
    }


def _collect_members(rds_client: object, cluster: dict) -> list:
    """Build the enriched members list from a cluster's DBClusterMembers.

    For each member, attempts ``describe_db_instances`` to enrich the base
    {identifier, is_writer} dict with instance-level fields.  On failure the
    base dict is kept and collection continues for remaining members.
    """
    members: list = []
    for m in cluster.get("DBClusterMembers", []):
        identifier = m.get("DBInstanceIdentifier")
        is_writer = m.get("IsClusterWriter")
        member: dict = {"identifier": identifier, "is_writer": is_writer}
        try:
            inst = rds_client.describe_db_instances(
                DBInstanceIdentifier=identifier
            )["DBInstances"][0]
            member.update(_flatten_instance(inst))
        except Exception:
            pass
        members.append(member)
    return members


def _fetch_parameters(rds_client: object, inst: dict) -> list:
    """Fetch and flatten all parameters from the first attached parameter group.

    Paginates on the ``Marker`` field until the response carries no Marker.
    Returns an empty list if no parameter group is attached or the fetch raises.
    """
    param_groups: list = inst.get("DBParameterGroups", [])
    if not param_groups:
        return []

    group_name: str = param_groups[0]["DBParameterGroupName"]

    try:
        parameters: list = []
        kwargs: dict = {"DBParameterGroupName": group_name}
        while True:
            resp = rds_client.describe_db_parameters(**kwargs)
            for param in resp.get("Parameters", []):
                parameters.append({
                    "name": param.get("ParameterName"),
                    "value": param.get("ParameterValue"),
                    "source": param.get("Source"),
                    "apply_type": param.get("ApplyType"),
                    "data_type": param.get("DataType"),
                    "is_modifiable": param.get("IsModifiable"),
                    "description": param.get("Description"),
                })
            marker = resp.get("Marker")
            if not marker:
                break
            kwargs = {"DBParameterGroupName": group_name, "Marker": marker}
        return parameters
    except Exception:
        return []
