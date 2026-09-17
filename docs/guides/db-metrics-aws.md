# `db-metrics-aws` — User Guide

Collect control-plane performance metrics and configuration for **AWS** RDS and
Aurora databases. Reads only CloudWatch and the RDS management API — it **never
connects to the database** and never reads row-level data.

Output is one JSON report per target (plus a summary for multi-target runs), in
a schema shared with `db-metrics-azure` and the PowerShell exporter, ready to
feed into [`db-metrics-recommend`](./db-metrics-recommend.md).

---

## Prerequisites

- **Python 3.12+**
- The AWS extra installed:
  ```bash
  pip install -e '.[aws]'
  ```
  (or `.[azure,aws,report]` for everything)
- AWS credentials resolvable by **boto3** — see Authentication below.

## Authentication

The collector builds a standard boto3 session, so it uses the normal AWS
credential chain. Both profile and region are **optional**:

- **Profile:** `--profile <name>`, or omit to use `AWS_PROFILE` / the default profile.
- **Region:** `--region <region>`, or omit to use `AWS_REGION` / `AWS_DEFAULT_REGION`
  (or the profile's configured region).

```bash
# Explicit
db-metrics-aws --service rds --profile my-sso --region us-east-1 --identifier mydb

# Ambient (env vars / default profile already set)
export AWS_PROFILE=my-sso AWS_REGION=us-east-1
db-metrics-aws --service rds --identifier mydb
```

Required IAM permissions: `cloudwatch:GetMetricData` / `cloudwatch:ListMetrics`
and the relevant `rds:Describe*` calls (`DescribeDBInstances` for RDS,
`DescribeDBClusters` for Aurora).

## Supported services

| `--service` | AWS resource | Required identifier |
|-------------|--------------|---------------------|
| `rds` | RDS DB instance | `--identifier <db-instance-id>` |
| `aurora` | Aurora DB cluster | `--cluster-identifier <cluster-id>` |

`--profile` and `--region` are **not** required (resolved from the environment
when omitted).

## Quick start (single target)

RDS DB instance:

```bash
db-metrics-aws \
  --service rds \
  --identifier my-postgres-instance \
  --region us-east-1 \
  --hours 168 --interval PT1H
```

Aurora DB cluster:

```bash
db-metrics-aws \
  --service aurora \
  --cluster-identifier my-aurora-cluster \
  --region us-west-2
```

## Multi-target via `--config`

```bash
db-metrics-aws --config targets.json
```

```json
{
  "defaults": { "cloud": "aws", "region": "us-east-1", "hours": 168, "interval": "PT1H" },
  "targets": [
    { "name": "orders-db", "service": "rds",    "identifier": "orders-db" },
    { "name": "analytics", "service": "aurora", "cluster_identifier": "analytics-cluster", "region": "us-west-2" }
  ]
}
```

`defaults` is merged into every target (per-target keys win); anything that
isn't `name`/`cloud`/`service`/`hours`/`interval` becomes a resource parameter.
`--config` is mutually exclusive with the single-target flags.

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--service` | — | `rds` or `aurora` (required unless `--config`) |
| `--identifier` | — | RDS DB instance identifier (`--service rds`) |
| `--cluster-identifier` | — | Aurora DB cluster identifier (`--service aurora`) |
| `--profile` | ambient | AWS profile name (optional) |
| `--region` | ambient | AWS region (optional) |
| `--hours` | `1` | Look-back window in hours |
| `--interval` | `PT1M` | Granularity (ISO-8601 duration); auto-coarsened per metric when needed |
| `--out` | auto | Output JSON path (single target only) |
| `--no-console` | off | Suppress the console summary (write JSON only) |
| `--config` | — | Multi-target JSON config file |

> **Tip for sizing:** longer windows catch more peaks. A week at hourly grain
> (`--hours 168 --interval PT1H`) is a good default for a recommender run.

## Output

- **Per target:** `metrics_<name>_<timestamp>.json` (UTC) — inventory, metric
  definitions, and per-metric time-series with a latest/min/max/avg summary.
- **Multi-target runs also write:** `summary_<timestamp>.json`.
- Files land in the **current working directory** (single target: override with
  `--out`). A console summary prints unless `--no-console`.

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All targets collected successfully |
| `1` | At least one target failed (others still written; failure recorded in the summary) |
| `2` | Usage/validation error (bad flags, unknown service, missing required identifier) |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `AWS support is not installed` | `pip install -e '.[aws]'` |
| `NoCredentialsError` / `Unable to locate credentials` | Set `AWS_PROFILE`/`--profile` or configure the default profile (`aws configure` / SSO login) |
| `You must specify a region` | Pass `--region` or set `AWS_REGION`/`AWS_DEFAULT_REGION` |
| `missing required param(s): identifier` | RDS needs `--identifier`; Aurora needs `--cluster-identifier` |
| `AccessDenied` | Grant CloudWatch read + `rds:Describe*` to the principal |

## Next step

Feed the JSON into the recommender:

```bash
db-metrics-recommend . --report report.html
```

See the [`db-metrics-recommend` guide](./db-metrics-recommend.md) and the
[end-to-end workflow](../../README.md#workflow).
