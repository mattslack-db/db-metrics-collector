# PowerShell Azure Exporter — User Guide

`Export-DbMetricsAzure.ps1` is a **PowerShell 7+** twin of
[`db-metrics-azure`](./db-metrics-azure.md). It collects the same Azure
control-plane metrics and configuration and emits the **identical JSON schema**,
so its output feeds [`db-metrics-recommend`](./db-metrics-recommend.md) exactly
like the Python collectors.

Use it when you'd rather not install the Python Azure SDK stack, or when
PowerShell is the available runtime. It **never connects to the database**.

---

## How it works (vs the Python tool)

- **Auth:** shells out to the **`az` CLI** for a token
  (`az account get-access-token --resource https://management.azure.com`) — it
  does **not** use the Az PowerShell modules.
- **Collection:** calls the **Azure REST API directly** via `Invoke-RestMethod`
  (Azure Monitor for metrics, Azure Resource Manager for inventory).
- **Dependency-light:** PowerShell 7+ and a logged-in `az` CLI are all you need —
  no `Az.*` modules, no Python.

## Prerequisites

- **PowerShell 7+** (`pwsh`):
  ```bash
  brew install powershell            # macOS
  sudo apt-get install -y powershell # Debian/Ubuntu
  pwsh --version
  ```
- **Azure CLI** logged in:
  ```bash
  az login
  # cross-tenant sandbox? note the tenant and pass -Tenant
  az account show --query tenantId -o tsv
  ```
- Pester 5.4+ (bundled with PowerShell 7) only if you want to run the tests.

## Supported services

All six Azure services, each with a dedicated flag (no config-only gaps):

| `-Service` | Identifier flag(s) |
|------------|--------------------|
| `postgres-flexible` | `-ServerName` |
| `mysql-flexible` | `-ServerName` |
| `sql-database` | `-ServerName -Database` |
| `sql-managed-instance` | `-InstanceName` |
| `cosmos-postgres` | `-ClusterName` |
| `single-server` | `-ServerName -SubEngine <postgresql\|mysql>` |

## Quick start (single target)

```powershell
./Export-DbMetricsAzure.ps1 `
  -Service postgres-flexible `
  -Subscription my-subscription `
  -ResourceGroup my-resource-group `
  -ServerName my-postgres-server `
  -Hours 168 -Interval PT1H
```

Run it from anywhere with an explicit path:

```bash
pwsh /path/to/powershell/Export-DbMetricsAzure.ps1 -Service postgres-flexible ...
```

For a cross-tenant subscription, add `-Tenant <TENANT_ID>`.

## Multi-target via `-Config`

Same config schema as the Python tools — you can reuse the exact same file:

```powershell
./Export-DbMetricsAzure.ps1 -Config targets.json -NoConsole
```

```json
{
  "defaults": { "cloud": "azure", "subscription": "<sub-id>", "hours": 168, "interval": "PT1H" },
  "targets": [
    { "name": "prod-pg", "service": "postgres-flexible",   "resource_group": "prod", "server_name": "prod-pg-01" },
    { "name": "prod-mi", "service": "sql-managed-instance", "resource_group": "prod", "instance_name": "prod-mi-01" }
  ]
}
```

`-Config` is mutually exclusive with the single-target flags.

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `-Service` | — | One of the six Azure services (required unless `-Config`) |
| `-Subscription` | — | Subscription GUID or display name |
| `-ResourceGroup` | — | Resource group name |
| `-ServerName` | — | Server name (flexible servers, SQL DB, single-server) |
| `-Database` | — | Database name (`sql-database`) |
| `-InstanceName` | — | Managed-instance name (`sql-managed-instance`) |
| `-ClusterName` | — | Cluster name (`cosmos-postgres`) |
| `-SubEngine` | — | `postgresql` or `mysql` (`single-server`) |
| `-Tenant` | auto | Entra tenant ID override |
| `-Hours` | `1` | Look-back window in hours |
| `-Interval` | `PT1M` | Granularity (ISO-8601 duration) |
| `-Out` | auto | Output JSON path (single target only) |
| `-NoConsole` | off | Suppress console summaries (JSON only) |
| `-Config` | — | Multi-target JSON config file |

## Output & exit codes

- **Per target:** `metrics_<name>_<yyyyMMdd_HHmmss>.json` (UTC).
- **Multi-target runs also write:** `summary_<yyyyMMdd_HHmmss>.json`.
- Files land in the current working directory; a console summary prints unless
  `-NoConsole`.
- Schema is byte-for-byte compatible with the Python collectors — verified
  end-to-end (identical recommender output on the same servers).

| Code | Meaning |
|------|---------|
| `0` | All targets collected successfully |
| `1` | At least one target failed (others still written) |
| `2` | Usage/validation error |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `az token failed` | `az login`; for a cross-tenant sub add `-Tenant <id>` |
| Metrics come back with an HTTP 4xx error field | Confirm the resource identifier flags match the `-Service`, and you have Reader/Monitoring Reader |
| `pwsh: command not found` | Install PowerShell 7+ (see Prerequisites) |

## Next step

Feed the JSON into the recommender (Python):

```bash
db-metrics-recommend . --report report.html
```

See the [`db-metrics-recommend` guide](./db-metrics-recommend.md) and the
[end-to-end workflow](../../README.md#workflow).
