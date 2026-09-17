# Metrics collector — platform coverage & extension candidates

This tool has two planes:

- **Metrics plane** — *engine/service-agnostic*. It discovers whatever metrics a
  resource emits and queries them; no metric list is hardcoded.
- **Inventory plane** — *service-specific*. A management client fetches the
  server/instance configuration and parameters.

Adding a new platform therefore means adding an inventory client and a metric
source; the querying/summarization/reporting code is reused as-is. This document
catalogs the OLTP database platforms the same approach covers and the **key
metrics** each exposes.

> **Scope:** relational / OLTP databases only. Caching layers (Azure Cache for
> Redis, AWS ElastiCache, MemoryDB) are **intentionally excluded for now**.
>
> **Metric lists below are the notable ones**, not exhaustive. The tool
> discovers the *complete* live set at run time (Azure Monitor
> `list_metric_definitions`; CloudWatch `list_metrics`). Counts marked
> "verified" come from real runs; others are representative of the documented
> metric set.

## How the approach maps across clouds

| Plane | Azure | AWS |
|-------|-------|-----|
| Metric discovery | `azure-monitor-query` → `list_metric_definitions` | CloudWatch → `list_metrics` |
| Metric query | `azure-monitor-query` → `query_resource` | CloudWatch → `get_metric_data` / `get_metric_statistics` |
| Inventory | `azure-mgmt-*` (e.g. `…postgresqlflexibleservers`) | boto3 `rds` → `describe_db_instances` / `describe_db_clusters` / `describe_db_parameters` |
| Richer in-DB counters (optional) | Query Store / `pg_stat_*` via a DB connection | **Performance Insights** (`pi` client) — DB load, top SQL, waits |
| Auth | `DefaultAzureCredential` (+ per-subscription tenant) | boto3 session / IAM role / profile |

**Status legend:** ✅ implemented · 🟢 same approach, drop-in inventory client · 🟡 legacy / retiring

---

## Azure

| Platform | Status | Metric namespace | Inventory client |
|----------|--------|------------------|------------------|
| PostgreSQL – Flexible Server | ✅ | `Microsoft.DBforPostgreSQL/flexibleServers` | `azure-mgmt-postgresqlflexibleservers` |
| MySQL – Flexible Server | ✅ | `Microsoft.DBforMySQL/flexibleServers` | `azure-mgmt-mysqlflexibleservers` |
| Cosmos DB for PostgreSQL (Citus) | 🟢 | `Microsoft.DBforPostgreSQL/serverGroupsv2` | `azure-mgmt-cosmosdbforpostgresql` |
| Azure SQL Database | 🟢 | `Microsoft.Sql/servers/databases` | `azure-mgmt-sql` |
| Azure SQL Managed Instance | 🟢 | `Microsoft.Sql/managedInstances` | `azure-mgmt-sql` |
| PostgreSQL / MySQL – Single Server | 🟡 | `…/servers` (`azure-mgmt-rdbms`) | `azure-mgmt-rdbms` |

> There is **no MariaDB Flexible Server** — Azure Database for MariaDB never had a
> Flexible tier and the service was retired (Sept 2025). PostgreSQL and MySQL are
> the complete Flexible Server set.

### PostgreSQL – Flexible Server ✅ (verified: 73 metric definitions)
- **Compute/memory:** `cpu_percent`, `memory_percent`, `cpu_credits_consumed`, `cpu_credits_remaining`
- **Storage:** `storage_percent`, `storage_used`, `storage_free`, `txlogs_storage_used`, `backup_storage_used`
- **IO:** `iops`, `read_iops`, `write_iops`, `read_throughput`, `write_throughput`, `disk_queue_depth`, `disk_iops_consumed_percentage`, `disk_bandwidth_consumed_percentage`
- **Connections:** `active_connections`, `connections_succeeded`, `connections_failed`
- **Network:** `network_bytes_ingress`, `network_bytes_egress`
- **Health/HA:** `is_db_alive`, `physical_replication_delay_in_bytes`/`_in_seconds`, `logical_replication_delay_in_bytes`, `maximum_used_transactionIDs`
- **Enhanced (opt-in server params):** `blks_hit`, `blks_read`, `tup_*`, `xact_commit`/`xact_rollback`, `deadlocks`, `temp_bytes`/`temp_files`, `sessions_by_state`, `sessions_by_wait_event_type`, `longest_transaction_time_sec`, `numbackends`, `tps`

### MySQL – Flexible Server ✅ (verified: 55 metric definitions)
- **Compute/memory/IO:** `cpu_percent`, `memory_percent`, `io_consumption_percent`, `cpu_credits_consumed`/`_remaining`
- **Storage:** `storage_percent`, `data_storage_used`, `binlog_storage_used`, `ibdata1_storage_used`, `backup_storage_used`
- **Connections/threads:** `active_connections`, `aborted_connections`, `Threads_running`, `Uptime`
- **Workload (Com_* statement counters):** `Com_select`, `Com_insert`, `Com_update`, `Com_delete`, `Com_create_table`, `Com_alter_table`, `Com_drop_table`, `Queries`, `Slow_queries`
- **InnoDB:** `Innodb_buffer_pool_reads`, `Innodb_buffer_pool_read_requests`, `Innodb_buffer_pool_pages_data`/`_dirty`/`_free`/`_flushed`, `Innodb_data_writes`, `Innodb_row_lock_time`, `Innodb_row_lock_waits`, `lock_deadlocks`
- **HA/replication:** `HA_IO_status`, `HA_SQL_status`, `HA_replication_lag`, `Replica_IO_Running`, `Replica_SQL_Running`, `active_transactions`, `Sort_merge_passes`

### Cosmos DB for PostgreSQL (Citus) 🟢
- **Per-node (split by `ServerName`/role dimension):** `cpu_percent`, `memory_percent`, `storage_percent`, `iops`, `active_connections`
- **Cluster:** `network_bytes_ingress`/`_egress`, per-node disk usage
- Coordinator vs worker nodes are distinguished via metric dimensions.

### Azure SQL Database 🟢
- **DTU model:** `dtu_consumption_percent`, `cpu_percent`, `physical_data_read_percent`, `log_write_percent`
- **vCore model:** `cpu_percent`, `sqlserver_process_core_percent`, `sqlserver_process_memory_percent`
- **Storage:** `storage`, `storage_percent`, `allocated_data_storage`, `tempdb_data_size`, `tempdb_log_used_percent`
- **Concurrency:** `workers_percent`, `sessions_percent`, `sessions_count`, `deadlock`, `blocked_by_firewall`
- **Connections:** `connection_successful`, `connection_failed`, `connection_failed_user_error`

### Azure SQL Managed Instance 🟢
- `avg_cpu_percent`, `virtual_core_count`, `storage_space_used_mb`, `reserved_storage_mb`, `io_bytes_read`, `io_bytes_written`, `io_requests`

### PostgreSQL / MySQL – Single Server 🟡 (legacy, retiring)
- `cpu_percent`, `memory_percent`, `io_consumption_percent`, `storage_percent`, `storage_used`, `storage_limit`, `active_connections`, `connections_failed`, `network_bytes_ingress`/`_egress`, `backup_storage_used`, `serverlog_storage_percent`; MySQL adds `replica_lag`, `seconds_behind_master`.
- Same approach via `azure-mgmt-rdbms`; low priority given retirement.

---

## AWS equivalents

AWS is a clean parallel: **CloudWatch** replaces Azure Monitor, and **boto3 `rds`**
replaces the Azure management SDK. Metric discovery is
`cloudwatch.list_metrics(Namespace="AWS/RDS", Dimensions=[…DBInstanceIdentifier…])`;
querying is `get_metric_data`. Inventory is `describe_db_instances` /
`describe_db_clusters` / `describe_db_parameters`.

| Platform | Azure counterpart | Metric namespace | Inventory (boto3) |
|----------|-------------------|------------------|-------------------|
| RDS for PostgreSQL | PG Flexible Server | `AWS/RDS` | `rds.describe_db_instances` |
| RDS for MySQL / MariaDB | MySQL Flexible Server | `AWS/RDS` | `rds.describe_db_instances` |
| Aurora PostgreSQL | (scale-out PG) | `AWS/RDS` | `rds.describe_db_clusters` + instances |
| Aurora MySQL | (scale-out MySQL) | `AWS/RDS` | `rds.describe_db_clusters` + instances |
| RDS for SQL Server / Oracle | Azure SQL / (Oracle) | `AWS/RDS` | `rds.describe_db_instances` |
| Optional richer counters | Query Store / pg_stat | Performance Insights (`pi` client) | `pi.get_resource_metrics` |

> **Auth/approach note:** the metric layer stays generic — only the inventory
> client and the CloudWatch dimension key (`DBInstanceIdentifier` vs
> `DBClusterIdentifier`) change per service.

### RDS for PostgreSQL / MySQL / MariaDB (CloudWatch `AWS/RDS`)
- **Compute/memory:** `CPUUtilization`, `FreeableMemory`, `SwapUsage`, `CPUCreditUsage`, `CPUCreditBalance` (t-class)
- **IO:** `ReadIOPS`, `WriteIOPS`, `ReadThroughput`, `WriteThroughput`, `ReadLatency`, `WriteLatency`, `DiskQueueDepth`, `EBSIOBalance%`, `EBSByteBalance%`
- **Storage:** `FreeStorageSpace`, `BurstBalance` (gp2)
- **Connections/network:** `DatabaseConnections`, `NetworkReceiveThroughput`, `NetworkTransmitThroughput`
- **Replication:** `ReplicaLag`, `OldestReplicationSlotLag`, `ReplicationSlotDiskUsage` (PostgreSQL), `BinLogDiskUsage` (MySQL)
- **PostgreSQL-specific:** `MaximumUsedTransactionIDs`, `TransactionLogsDiskUsage`, `TransactionLogsGeneration`
- **OS-level (Enhanced Monitoring, opt-in):** per-process/CPU/memory/filesystem via the `RDSOSMetrics` CloudWatch Logs group

### Aurora PostgreSQL / MySQL (CloudWatch `AWS/RDS`, cluster + instance)
- **Latency/throughput (per op):** `CommitLatency`, `CommitThroughput`, `SelectLatency`/`SelectThroughput`, `InsertLatency`, `UpdateLatency`, `DeleteLatency`, `DDLLatency`, `DMLLatency`
- **Cache/engine:** `BufferCacheHitRatio`, `ResultSetCacheHitRatio`, `Deadlocks`, `BlockedTransactions`, `LoginFailures`
- **Replication:** `AuroraReplicaLag`, `AuroraReplicaLagMaximum`, `AuroraReplicaLagMinimum`, `AuroraBinlogReplicaLag` (MySQL)
- **Storage volume:** `VolumeBytesUsed`, `VolumeReadIOPs`, `VolumeWriteIOPs`
- **Standard:** `CPUUtilization`, `FreeableMemory`, `DatabaseConnections`
- **Serverless v2:** `ServerlessDatabaseCapacity`, `ACUUtilization`

### RDS for SQL Server / Oracle (CloudWatch `AWS/RDS`)
- Shares the core `AWS/RDS` set (`CPUUtilization`, `FreeableMemory`, `FreeStorageSpace`, `ReadIOPS`/`WriteIOPS`, `ReadLatency`/`WriteLatency`, `DatabaseConnections`, `DiskQueueDepth`).
- Engine-specific depth is best obtained via **Performance Insights** (`pi` client): DB load in Average Active Sessions (AAS), top SQL, top waits.

### Performance Insights (optional, both RDS & Aurora)
- `pi.get_resource_metrics` exposes `db.load.avg` (AAS) plus dimensioned counters:
  `db.sql`, `db.wait_event`, `db.user`, `db.host` — the AWS analogue of the
  in-DB detail we'd get from Query Store / `pg_stat_statements`.

---

## Cross-candidate common metrics (and Lakebase sizing relevance)

These are the dimensions that exist — under different names — across **all**
candidates, so a single normalized model can be built on top of them. The last
column flags whether the metric is an input to sizing an equivalent **Databricks
Lakebase Autoscaling** instance (see the method below).

| Dimension | Azure name(s) | AWS name(s) | On all candidates? | Lakebase sizing input |
|-----------|---------------|-------------|--------------------|-----------------------|
| **CPU utilization** | `cpu_percent` | `CPUUtilization` | ✅ Yes | ★ Primary — CU provides vCPU; peak CPU sets the autoscale ceiling |
| **Memory utilization** | `memory_percent` (Flexible/Cosmos/MI); vCore SQL: `sqlserver_process_memory_percent` | `FreeableMemory` (derive used = RAM − free) | ✅ Yes (DTU-model SQL DB only indirectly) | ★ Primary — CU ≈ **2 GB RAM/CU**, so peak working-set sets the **minimum** CU floor |
| **Active connections** | `active_connections` | `DatabaseConnections` | ✅ Yes | ★ Peak concurrency → pooling need and endpoint sizing |
| **Storage used** | `storage_used` / `storage_percent` | `FreeStorageSpace`; Aurora `VolumeBytesUsed` | ✅ Yes | ★ Starting storage + growth trend (Lakebase storage autoscales separately from CU) |
| **Read IOPS / Write IOPS** | `read_iops` / `write_iops` (Flexible/Cosmos) | `ReadIOPS` / `WriteIOPS` | ⚠️ Flexible + RDS/Aurora (SQL DB exposes `physical_data_read_percent` / `log_write_percent` instead) | ★ IOPS headroom check; the read/write split drives read-replica need |
| **Read / Write throughput** | `read_throughput` / `write_throughput` | `ReadThroughput` / `WriteThroughput` | ⚠️ Flexible + RDS/Aurora | Bandwidth headroom; secondary to CU |
| **Replication lag** | `physical_replication_delay_in_seconds` | `ReplicaLag`, `AuroraReplicaLag` | ⚠️ Only where replicas exist | ★ Existing replica count → number of Lakebase secondaries / read-only endpoints |
| **Network throughput** | `network_bytes_ingress` / `_egress` | `NetworkReceiveThroughput` / `NetworkTransmitThroughput` | ⚠️ Azure + AWS RDS (not SQL DB cleanly) | Sanity / egress only — not a CU driver |

★ = used directly for Lakebase sizing.

**Universal core** (present everywhere, the safe common denominator): **CPU %,
memory utilization, active connections, storage used.** IOPS/throughput and
replication lag are present on the engine families that matter most for a
Lakebase migration (PostgreSQL/MySQL Flexible Server and RDS/Aurora) but are
abstracted away on DTU-model Azure SQL Database.

## Sizing a Lakebase Autoscaling instance from these metrics

Lakebase Autoscaling bills in **compute units (CU)**, each ≈ **2 GB RAM** with
proportional vCPU. Range: **0.5–64 CU** dynamic (autoscaling window, where
max − min ≤ 16 CU) and **65–112 CU** fixed. It supports **scale-to-zero**
(default 5 min idle), and **1 primary + 1–3 secondaries** plus read replicas.
Sizing is therefore about picking a **min/max CU band**, **storage**,
**replicas**, and **scale-to-zero** — all derivable from the universal metrics:

| Lakebase decision | Driven by | Rule of thumb |
|-------------------|-----------|---------------|
| **Minimum CU** | Peak memory working set | `min_CU ≈ ceil(peak_used_GB / 2)`, floor 0.5. Keeps the hot set in RAM. |
| **Maximum CU** | Peak CPU **and** peak memory | Size to the busiest window; ensure `max − min ≤ 16` (else use a fixed tier). |
| **Storage** | `storage_used` + growth trend | Start at current DB size; storage autoscales independently of CU. |
| **Read replicas / secondaries** | Read/write ratio + existing replica count | Read-heavy (`reads ≫ writes`) or existing read replicas → add read-only endpoints (1–3). |
| **Scale-to-zero** | Idle windows in CPU + `active_connections` | Sustained idle periods (dev/test, spiky apps) → enable; steady 24×7 load → disable. |
| **HA secondaries** | Source HA / sync-replica config + replication lag | Source running HA → provision 1–3 secondaries for automatic failover. |

**Method:** use **peak (max)** values — not averages — for the CU ceiling and
storage, and **idle/percentile-low** values for the min-CU floor and
scale-to-zero decision. Peak memory is the dominant input because CU is
RAM-denominated; CPU and IOPS then confirm the band is wide enough. This mirrors
the TCO inputs the companion PostgreSQL assessment collector already captures
(`db_size_gb`, `read_write_ratio`, `read_replica_count`).

> **Caveat:** source `cpu_percent` / `memory_percent` are relative to the
> *source* SKU, so convert to absolute (× source vCPU / RAM) before mapping to
> CU — a metric snapshot alone isn't enough without the instance's SKU, which the
> inventory half of this tool already collects.

---

## Summary

| | Azure | AWS |
|--|-------|-----|
| **Implemented** | PostgreSQL + MySQL Flexible Server | — |
| **Drop-in (same approach)** | Cosmos DB for PostgreSQL, SQL Database, SQL Managed Instance, Single Server (legacy) | RDS (PostgreSQL/MySQL/MariaDB/SQL Server/Oracle), Aurora (PostgreSQL/MySQL) |
| **Metric source** | Azure Monitor (dynamic discovery) | CloudWatch (dynamic discovery) |
| **Inventory** | `azure-mgmt-*` | boto3 `rds` |
| **Deeper in-DB detail** | Query Store / `pg_stat_*` | Performance Insights |
| **Excluded (for now)** | Azure Cache for Redis | ElastiCache, MemoryDB |

The consistent shape across all of these — *generic metric discovery + a small
per-service inventory client* — means each additional platform is a contained
addition, not a rewrite.
