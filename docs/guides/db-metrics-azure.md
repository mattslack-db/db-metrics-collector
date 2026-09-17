# `db-metrics-azure` — User Guide

Collect control-plane performance metrics and configuration for **Azure**
databases. Reads only the Azure Monitor and Azure Resource Manager APIs — it
**never connects to the database** and never reads row-level data.

The output is one JSON report per target (plus a summary for multi-target runs),
in a schema shared with `db-metrics-aws` and the PowerShell exporter, ready to
feed into [`db-metrics-recommend`](./db-metrics-recommend.md).

---

## Prerequisites

- **Python 3.12+**
- The Azure extra installed:
  ```bash
  pip install -e '.[azure]'
  ```
  (or `.[azure,aws,report]` for everything)
- **Azure CLI** (`az`) installed and logged in — see Authentication below.

## Authentication

The collector authenticates through your `az` CLI session:

```bash
az login
```

- It calls `az account show` to resolve the subscription's **home tenant**, then
  pins `AzureCliCredential` to it — so **cross-tenant sandbox subscriptions work
  without extra flags**. If no tenant is resolved it falls back to
  `DefaultAzureCredential` (env vars / managed identity).
- Override the tenant explicitly with `--tenant <TENANT_ID>` when needed.

You need at least **Reader** on the target resource (Monitoring Reader is enough
for metrics; Reader for the inventory/configuration calls).

## Supported services

| `--service` | Azure resource | Single-target flags | Config-only params |
|-------------|----------------|---------------------|--------------------|
| `postgres-flexible` | PostgreSQL Flexible Server | `--server-name` | — |
| `mysql-flexible` | MySQL Flexible Server | `--server-name` | — |
| `sql-database` | Azure SQL Database | `--server-name --database` | — |
| `cosmos-postgres` | Cosmos DB for PostgreSQL | *(none — use `--config`)* | `cluster_name` |
| `sql-managed-instance` | Azure SQL Managed Instance | *(none — use `--config`)* | `instance_name` |
| `single-server` | PostgreSQL/MySQL Single Server | *(none — use `--config`)* | `server_name`, `sub_engine` |

> **Note:** the single-target CLI only exposes `--server-name` and `--database`
> identifiers. `cosmos-postgres`, `sql-managed-instance`, and `single-server`
> need identifiers (`cluster_name`, `instance_name`, `sub_engine`) that are only
> settable through a `--config` file (see below). The PowerShell exporter has
> dedicated flags for all six services if you prefer flags.

## Quick start (single target)

PostgreSQL Flexible Server, last 6 hours at 5-minute grain:

```bash
db-metrics-azure \
  --service postgres-flexible \
  --subscription my-subscription \
  --resource-group my-resource-group \
  --server-name my-postgres-server \
  --hours 6 --interval PT5M
```

Azure SQL Database (needs `--database`):

```bash
db-metrics-azure \
  --service sql-database \
  --subscription <SUB> --resource-group <RG> \
  --server-name <SQL_SERVER> --database <DB_NAME>
```

## Multi-target via `--config`

Point at one JSON file describing many targets. `defaults` is merged into every
target (per-target keys win). Any key that isn't `name`/`cloud`/`service`/
`hours`/`interval` becomes a resource identifier parameter.

```bash
db-metrics-azure --config targets.json
```

```json
{
  "defaults": { "cloud": "azure", "subscription": "<sub-id>", "hours": 168, "interval": "PT1H" },
  "targets": [
    { "name": "prod-pg",  "service": "postgres-flexible",    "resource_group": "prod", "server_name": "prod-pg-01" },
    { "name": "prod-my",  "service": "mysql-flexible",        "resource_group": "prod", "server_name": "prod-my-01", "hours": 24 },
    { "name": "prod-mi",  "service": "sql-managed-instance",  "resource_group": "prod", "instance_name": "prod-mi-01" },
    { "name": "citus",    "service": "cosmos-postgres",       "resource_group": "prod", "cluster_name": "citus-01" }
  ]
}
```

`--config` is mutually exclusive with the single-target flags.

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--service` | — | One of the six Azure services (required unless `--config`) |
| `--subscription` | — | Subscription GUID or display name |
| `--resource-group` | — | Resource group name |
| `--server-name` | — | Server/instance name (flexible servers, SQL DB, single-server) |
| `--database` | — | Database name (`sql-database` only) |
| `--tenant` | auto | Entra tenant ID override (default: subscription's home tenant) |
| `--hours` | `1` | Look-back window in hours |
| `--interval` | `PT1M` | Granularity (ISO-8601 duration); auto-coarsened per metric when needed |
| `--out` | auto | Output JSON path (single target only) |
| `--no-console` | off | Suppress the console summary (write JSON only) |
| `--config` | — | Multi-target JSON config file |

> **Tip for sizing:** the recommender sizes from observed peaks, so a longer
> window catches more of them. A week at hourly grain (`--hours 168 --interval PT1H`)
> is a good default; a single hour at `PT1M` is fine for a quick spot check.

## Output

- **Per target:** `metrics_<name>_<timestamp>.json` (UTC timestamp) — inventory,
  metric definitions, and per-metric time-series with a latest/min/max/avg summary.
- **Multi-target runs also write:** `summary_<timestamp>.json` — per-target
  status and metric/error counts.
- Files land in the **current working directory** (single target: override with
  `--out`). A console summary prints unless `--no-console`.

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All targets collected successfully |
| `1` | At least one target failed (others still written; failure recorded in the summary) |
| `2` | Usage/validation error (bad flags, unknown service, bad interval, missing required params) |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Azure support is not installed` | `pip install -e '.[azure]'` |
| `cannot configure default credentials` / auth errors | `az login`; for a cross-tenant subscription add `--tenant <id>` |
| `missing required param(s)` | Provide the identifier the service needs (see the table); use `--config` for `cluster_name`/`instance_name`/`sub_engine` |
| Empty/partial metrics | Confirm you have Monitoring Reader on the resource and the window overlaps live data |

## Next step

Feed the JSON into the recommender:

```bash
db-metrics-recommend . --report report.html
```

See the [`db-metrics-recommend` guide](./db-metrics-recommend.md) and the
[end-to-end workflow](../../README.md#workflow).
