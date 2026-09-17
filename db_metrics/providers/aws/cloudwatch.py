"""CloudWatchSource: MetricSource implementation for AWS CloudWatch.

Implements the MetricSource protocol (db_metrics.providers.base) by
wrapping a boto3 CloudWatch client (or any compatible fake).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from db_metrics.models import Target
from db_metrics.providers.base import MetricDef, MetricSeries
from db_metrics.summarize import duration_str, summarize_points

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STATS = ["Average", "Maximum", "Minimum", "Sum"]

_STAT_TO_FIELD = {
    "Average": "average",
    "Maximum": "maximum",
    "Minimum": "minimum",
    "Sum": "total",
}

_MAX_QUERIES = 500


# ---------------------------------------------------------------------------
# CloudWatchSource
# ---------------------------------------------------------------------------


class CloudWatchSource:
    """MetricSource backed by an AWS CloudWatch client.

    Parameters
    ----------
    cw_client:
        A boto3 CloudWatch client (or compatible fake) providing
        ``list_metrics`` and ``get_metric_data``.
    """

    def __init__(self, cw_client: object) -> None:
        self._cw = cw_client

    # ---------------------------------------------------------------------- #
    # MetricSource protocol                                                    #
    # ---------------------------------------------------------------------- #

    def discover(self, target: Target) -> list[MetricDef]:
        """Return deduplicated MetricDef objects for every RDS metric available.

        Paginates list_metrics until NextToken is exhausted, then dedupes by
        MetricName (a metric can appear under multiple dimension combos).
        """
        dim_name: str = target.params["dimension_name"]
        dim_value: str = target.params["dimension_value"]

        seen: dict[str, MetricDef] = {}

        kwargs: dict = {
            "Namespace": "AWS/RDS",
            "Dimensions": [{"Name": dim_name, "Value": dim_value}],
        }

        while True:
            resp = self._cw.list_metrics(**kwargs)
            for metric in resp.get("Metrics", []):
                metric_name: str = metric["MetricName"]
                if metric_name not in seen:
                    seen[metric_name] = MetricDef(
                        name=metric_name,
                        unit=None,
                        aggregations=list(_STATS),
                        dimensions=[dim_name],
                    )
            next_token = resp.get("NextToken")
            if not next_token:
                break
            kwargs = {
                "Namespace": "AWS/RDS",
                "Dimensions": [{"Name": dim_name, "Value": dim_value}],
                "NextToken": next_token,
            }

        return list(seen.values())

    def query(
        self,
        target: Target,
        defs: list[MetricDef],
        start: datetime,
        end: datetime,
        granularity: timedelta,
    ) -> list[MetricSeries]:
        """Query CloudWatch for all defs and return one MetricSeries per metric.

        Builds one MetricDataQuery per (def, stat), batches them into chunks of
        _MAX_QUERIES, and paginates each chunk call until NextToken is exhausted.
        """
        dim_name: str = target.params["dimension_name"]
        dim_value: str = target.params["dimension_value"]
        period = int(granularity.total_seconds())

        # Build all queries and maintain an id→(metric_name, stat) map
        all_queries: list[dict] = []
        id_to_metric_stat: dict[str, tuple[str, str]] = {}

        idx = 0
        for d in defs:
            for stat in d.aggregations:
                qid = f"q{idx}"
                all_queries.append(
                    {
                        "Id": qid,
                        "MetricStat": {
                            "Metric": {
                                "Namespace": "AWS/RDS",
                                "MetricName": d.name,
                                "Dimensions": [{"Name": dim_name, "Value": dim_value}],
                            },
                            "Period": period,
                            "Stat": stat,
                        },
                        "ReturnData": True,
                    }
                )
                id_to_metric_stat[qid] = (d.name, stat)
                idx += 1

        # Accumulate per-metric, per-timestamp dicts
        # points_by_metric[metric_name][timestamp] = {field: value, "timestamp": ts}
        points_by_metric: dict[str, dict[datetime, dict]] = {d.name: {} for d in defs}

        # Batch into chunks of ≤ _MAX_QUERIES
        for chunk_start in range(0, len(all_queries), _MAX_QUERIES):
            chunk = all_queries[chunk_start : chunk_start + _MAX_QUERIES]
            call_kwargs: dict = {
                "MetricDataQueries": chunk,
                "StartTime": start,
                "EndTime": end,
            }
            while True:
                resp = self._cw.get_metric_data(**call_kwargs)
                for result in resp.get("MetricDataResults", []):
                    qid = result["Id"]
                    metric_name, stat = id_to_metric_stat[qid]
                    field = _STAT_TO_FIELD[stat]
                    for ts, val in zip(result["Timestamps"], result["Values"]):
                        ts_map = points_by_metric[metric_name]
                        if ts not in ts_map:
                            ts_map[ts] = {"timestamp": ts}
                        ts_map[ts][field] = val
                next_token = resp.get("NextToken")
                if not next_token:
                    break
                call_kwargs = {
                    "MetricDataQueries": chunk,
                    "StartTime": start,
                    "EndTime": end,
                    "NextToken": next_token,
                }

        # Build MetricSeries in the order of defs
        results: list[MetricSeries] = []
        for d in defs:
            ts_map = points_by_metric[d.name]
            points = sorted(ts_map.values(), key=lambda p: p["timestamp"])
            results.append(
                MetricSeries(
                    name=d.name,
                    unit=None,
                    granularity=duration_str(granularity),
                    timeseries=[
                        {
                            "dimensions": {dim_name: dim_value},
                            "points": points,
                            "summary": summarize_points(points),
                        }
                    ],
                    error=None,
                )
            )

        return results
