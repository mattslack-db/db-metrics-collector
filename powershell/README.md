# PowerShell Azure Exporter

A PowerShell 7+ twin of the Python `db-metrics-azure` tool that collects control-plane metrics and configuration for Azure databases, emitting the identical JSON schema to enable cross-tool parity verification.

**Supported services:** postgres-flexible, mysql-flexible, cosmos-postgres, sql-database, sql-managed-instance, single-server (PostgreSQL and MySQL variants).

## Prerequisites

### PowerShell 7+

Install [PowerShell 7+](https://github.com/PowerShell/PowerShell/releases) (`pwsh`):

```bash
# macOS
brew install powershell

# Linux (Ubuntu/Debian)
sudo apt-get install -y powershell

# Windows
# Download from https://github.com/PowerShell/PowerShell/releases
```

Verify:
```powershell
pwsh --version
```

### Azure CLI

Install the `az` CLI and authenticate:

```bash
# Install: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli

# Log in
az login

# For cross-tenant sandbox subscriptions, verify your tenant ID
az account show --query tenantId -o tsv
```

**Tenant pinning:** If your subscription is in a different Entra tenant (e.g., in a shared sandbox environment), pass `-Tenant <tenantId>` to the exporter. The tool retrieves tokens via `az account get-access-token --resource https://management.azure.com`, which supports tenant-pinned requests. See the [Usage](#usage-single-target) section.

### Pester (for running tests)

Pester 5.4+ is included in PowerShell 7+. To run tests:

```powershell
# Verify Pester is available
Get-Module -Name Pester -ListAvailable
```

## What It Is

The PowerShell Azure exporter:

- Collects **control-plane metrics and configuration** from Azure Monitor and Azure Resource Manager REST APIs.
- Queries **six Azure database services** with identical metric schema and field mapping to the Python `db-metrics-azure`.
- **Does NOT connect to databases** — all data comes from Azure Monitor and ARM configuration endpoints.
- Emits **per-target reports** as `metrics_<name>_<yyyyMMdd_HHmmss>.json` and **multi-target summaries** as `summary_<yyyyMMdd_HHmmss>.json` with the same JSON structure as the Python tool.
- Uses **one REST request per metric definition** with per-metric error isolation and retry-without-filter logic (matches Python behavior).

## Usage

### Single Target

Export metrics for a single database resource:

#### Postgres Flexible Server

```powershell
./Export-DbMetricsAzure.ps1 \
  -Service postgres-flexible \
  -Subscription <subscription-id-or-name> \
  -ResourceGroup <resource-group> \
  -ServerName <server-name> \
  -Tenant <tenant-id>
```

#### MySQL Flexible Server

```powershell
./Export-DbMetricsAzure.ps1 \
  -Service mysql-flexible \
  -Subscription <subscription-id-or-name> \
  -ResourceGroup <resource-group> \
  -ServerName <server-name>
```

#### Cosmos DB for PostgreSQL

```powershell
./Export-DbMetricsAzure.ps1 \
  -Service cosmos-postgres \
  -Subscription <subscription-id-or-name> \
  -ResourceGroup <resource-group> \
  -ClusterName <cluster-name>
```

#### SQL Database

```powershell
./Export-DbMetricsAzure.ps1 \
  -Service sql-database \
  -Subscription <subscription-id-or-name> \
  -ResourceGroup <resource-group> \
  -ServerName <sql-server-name> \
  -Database <database-name>
```

#### SQL Managed Instance

```powershell
./Export-DbMetricsAzure.ps1 \
  -Service sql-managed-instance \
  -Subscription <subscription-id-or-name> \
  -ResourceGroup <resource-group> \
  -InstanceName <instance-name>
```

#### Single-Server (PostgreSQL or MySQL)

```powershell
./Export-DbMetricsAzure.ps1 \
  -Service single-server \
  -Subscription <subscription-id-or-name> \
  -ResourceGroup <resource-group> \
  -ServerName <server-name> \
  -SubEngine postgresql
```

### Optional Single-Target Parameters

All single-target invocations accept:

```powershell
./Export-DbMetricsAzure.ps1 \
  -Service postgres-flexible \
  -Subscription <sub> \
  -ResourceGroup <rg> \
  -ServerName <name> \
  -Hours 24 \
  -Interval PT5M \
  -Out ~/reports/my-report.json \
  -NoConsole \
  -Tenant <tenant-id>
```

- `-Hours` (default: 1) — Look-back window in hours.
- `-Interval` (default: `PT1M`) — Metric granularity as ISO-8601 duration (e.g., `PT5M`, `PT1H`).
- `-Out` — Output JSON file path; default is `metrics_<name>_<yyyyMMdd_HHmmss>.json` in the current directory.
- `-NoConsole` — Suppress console summary; write JSON only.
- `-Tenant` — Entra tenant ID (required for cross-tenant subscriptions; optional for home tenant).

### Multi-Target via Config File

Export metrics for multiple databases from a JSON configuration file:

```powershell
./Export-DbMetricsAzure.ps1 -Config targets.json
```

#### Config File Format

```json
{
  "defaults": {
    "cloud": "azure",
    "hours": 1,
    "interval": "PT1M"
  },
  "targets": [
    {
      "name": "prod-postgres",
      "service": "postgres-flexible",
      "subscription": "<subscription-id>",
      "resource_group": "prod",
      "server_name": "prod-pg-01"
    },
    {
      "name": "prod-mysql",
      "service": "mysql-flexible",
      "subscription": "<subscription-id>",
      "resource_group": "prod",
      "server_name": "prod-mysql-01",
      "hours": 24
    },
    {
      "name": "prod-sql-db",
      "service": "sql-database",
      "subscription": "<subscription-id>",
      "resource_group": "prod",
      "server_name": "prod-sql-server",
      "database": "orders"
    }
  ]
}
```

**Config structure:**
- `defaults` (optional) — Key-value pairs merged into every target (target keys override).
- `targets` (required) — Non-empty list of target objects. Each target must include:
  - `name` — Human-readable identifier for console output and file naming.
  - `cloud` — Always `"azure"` for this tool.
  - `service` — One of the six supported services (postgres-flexible, mysql-flexible, cosmos-postgres, sql-database, sql-managed-instance, single-server).
  - Service-specific parameters (e.g., `subscription`, `resource_group`, `server_name`, `database`, `sub_engine`, `cluster_name`, `instance_name`; see Parameters table below).
  - `hours` (optional) — Look-back window; defaults to 1.
  - `interval` (optional) — Granularity; defaults to `PT1M`.

**Behavior:**
- For each target, generates a report file `metrics_<name>_<timestamp>.json`.
- Generates a multi-target summary file `summary_<timestamp>.json` containing status, error counts, and per-target statistics.
- Cannot combine `-Config` with any single-target flags (`-Service`, `-Subscription`, etc.); the tool exits with an error if both are present.

## Parameters

| Parameter | Description | Services |
|-----------|-------------|----------|
| `-Service` | Azure service name. Required when `-Config` is not specified. | All |
| `-Subscription` | Azure subscription GUID or display name. | All |
| `-ResourceGroup` | Azure resource group name. | All |
| `-ServerName` | Server/instance name (used for postgres-flexible, mysql-flexible, sql-database, single-server). | postgres-flexible, mysql-flexible, sql-database, single-server |
| `-Database` | Database name (sql-database only). | sql-database |
| `-SubEngine` | Sub-engine for single-server: `postgresql` or `mysql`. | single-server |
| `-ClusterName` | Cluster name (cosmos-postgres only). | cosmos-postgres |
| `-InstanceName` | Managed instance name (sql-managed-instance only). | sql-managed-instance |
| `-Tenant` | Entra tenant ID override (optional; required for cross-tenant subscriptions). | All |
| `-Hours` | Look-back window in hours (default: 1). | All |
| `-Interval` | Metric granularity as ISO-8601 duration (default: `PT1M`). | All |
| `-Out` | Output JSON path for single-target runs (default: `metrics_<name>_<timestamp>.json`). | All (single-target only) |
| `-NoConsole` | Suppress console summary; write JSON only. | All |
| `-Config` | Path to JSON configuration file for multi-target runs (mutually exclusive with single-target flags). | All (multi-target only) |

### Service-Specific Required Parameters

| Service | Required Parameters |
|---------|-------------------|
| postgres-flexible | subscription, resource_group, server_name |
| mysql-flexible | subscription, resource_group, server_name |
| cosmos-postgres | subscription, resource_group, cluster_name |
| sql-database | subscription, resource_group, server_name, database |
| sql-managed-instance | subscription, resource_group, instance_name |
| single-server | subscription, resource_group, server_name, sub_engine |

## Running Tests

Run the full Pester test suite:

```powershell
pwsh -NoProfile -Command "Invoke-Pester powershell/tests -Output Detailed"
```

Or with code coverage:

```powershell
pwsh -NoProfile -Command "Invoke-Pester powershell/tests -CodeCoverage powershell/DbMetrics/*.ps1 -Output Detailed"
```

Expected output includes test results for all modules (Auth, TimeWindow, Summarize, AzureMonitor, AzureInventory, Registry, Config, Report, Cli) with ≥80% code coverage.

## Output

### Per-Target Report

Each target produces a JSON report (`metrics_<name>_<yyyyMMdd_HHmmss>.json`) with the canonical schema:

```json
{
  "collected_at": "2026-01-15T10:30:45.123456Z",
  "name": "prod-postgres",
  "cloud": "azure",
  "service": "postgres-flexible",
  "resource_scope": "/subscriptions/.../resourceGroups/.../providers/...",
  "window": {
    "start": "2026-01-15T09:30:45Z",
    "end": "2026-01-15T10:30:45Z",
    "interval": "PT1M"
  },
  "inventory": {
    "resource_id": "...",
    "server": { ... },
    "parameters": [ ... ],
    "parameters_non_default": [ ... ],
    "databases": [ ... ]
  },
  "metric_definitions": [
    { "name": "cpu_percent", "unit": "Percent", "aggregations": [...], "dimensions": [...], "granularities": [...] }
  ],
  "metrics": [
    {
      "name": "cpu_percent",
      "unit": "Percent",
      "granularity": "PT1M",
      "timeseries": [
        {
          "dimensions": { "dimension_name": "value" },
          "points": [ { "timestamp": "2026-01-15T10:00:00Z", "average": 45.2 }, ... ],
          "summary": { "average": { "latest": 45.2, "min": 30.1, "max": 60.5, "avg": 45.23, "count": 60 } }
        }
      ],
      "error": null
    }
  ]
}
```

**Schema parity:** The JSON structure and field names are identical to the Python `db-metrics-azure` output, verified by a schema + value parity test.

### Multi-Target Summary

When running with `-Config` and multiple targets, a summary file (`summary_<yyyyMMdd_HHmmss>.json`) is generated:

```json
{
  "targets": [
    { "name": "prod-postgres", "cloud": "azure", "service": "postgres-flexible", "metric_count": 12, "error_count": 0, "status": "ok" },
    { "name": "prod-mysql", "cloud": "azure", "service": "mysql-flexible", "metric_count": 11, "error_count": 1, "status": "partial" }
  ],
  "target_count": 2,
  "error_target_count": 1
}
```

**Status codes:**
- `ok` — All metrics collected successfully.
- `partial` — Some metrics failed; at least one succeeded.
- `error` — All metrics failed or target-level error.

### Console Output

Each run prints a per-target summary (unless `-NoConsole`):

```
Name              CPU %        Min      Max      Avg      
cpu_percent       45.20        30.10    60.50    45.23    
dtu_consumption   25.00        20.00    30.00    24.50    

[+2 dimensions, +8 series]
```

For multi-target runs, a summary table is also printed:

```
Targets          Service     Metrics  Errors  Status   
prod-postgres    postgres...      12       0  ok       
prod-mysql       mysql-fl...      11       1  partial  
```

## Exit Codes

- `0` — All targets succeeded.
- `1` — At least one target failed (non-fatal; reports were written for successful targets).
- `2` — Usage/validation error (bad flags, missing required parameters, invalid ISO-8601 interval, non-positive hours, etc.).
