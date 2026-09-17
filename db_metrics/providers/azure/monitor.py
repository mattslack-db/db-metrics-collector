"""AzureMonitorSource: MetricSource implementation for Azure Monitor.

Implements the MetricSource protocol (db_metrics.providers.base) by
wrapping a MetricsQueryClient (or any compatible fake).

SDK-shaped helpers (_agg_name, aggregations_for, _dimension_filter,
_metric_value_to_dict, _timeseries_to_dict) are ported directly from the
legacy db_metrics.metrics module so that this module survives Task 9's
deletion of metrics.py without any import from that module.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from db_metrics.models import Target
from db_metrics.providers.base import MetricDef, MetricSeries
from db_metrics.summarize import (
    available_granularities,
    choose_granularity,
    duration_str,
    summarize_points,
)
from db_metrics.timewindow import parse_iso8601_duration

# --------------------------------------------------------------------------- #
# SDK-shaped private helpers (ported from metrics.py — no import from there)  #
# --------------------------------------------------------------------------- #

_SKIP_AGGREGATIONS = {"None", "NONE", "none", None}

_VALUE_FIELDS = ("average", "minimum", "maximum", "total", "count")


def _agg_name(agg: Any) -> str:
    """Normalize an aggregation enum/str to its string name."""
    return getattr(agg, "value", None) or str(agg)


def _aggregations_for(definition: Any) -> list[str]:
    """Supported aggregation names for a metric definition, minus NONE."""
    supported = getattr(definition, "supported_aggregation_types", None) or []
    names = [_agg_name(a) for a in supported]
    result = [n for n in names if n not in _SKIP_AGGREGATIONS]
    return result or ["Average"]


def _dimension_filter(dimension_names: list[str]) -> str | None:
    """Build a '<dim> eq '*'' filter string, or None when no dimensions."""
    names = [n for n in dimension_names if n]
    if not names:
        return None
    return " and ".join(f"{n} eq '*'" for n in names)


def _metric_value_to_dict(value: Any) -> dict:
    out: dict[str, Any] = {"timestamp": getattr(value, "timestamp", None)}
    for field in _VALUE_FIELDS:
        val = getattr(value, field, None)
        if val is not None:
            out[field] = val
    return out


def _timeseries_to_dict(element: Any) -> dict:
    metadata = {
        getattr(m, "name", None): getattr(m, "value", None)
        for m in (getattr(element, "metadata_values", None) or [])
    }
    points = [_metric_value_to_dict(v) for v in (getattr(element, "data", None) or [])]
    return {
        "dimensions": metadata,
        "points": points,
        "summary": summarize_points(points),
    }


# --------------------------------------------------------------------------- #
# AzureMonitorSource                                                           #
# --------------------------------------------------------------------------- #


class AzureMonitorSource:
    """MetricSource backed by an Azure Monitor MetricsQueryClient.

    The constructor accepts a MetricsQueryClient instance (or any compatible
    fake) as its single positional argument and stores it as ``self._client``.
    """

    def __init__(self, credential_or_client: Any) -> None:
        self._client = credential_or_client

    # ---------------------------------------------------------------------- #
    # MetricSource protocol                                                    #
    # ---------------------------------------------------------------------- #

    def discover(self, target: Target) -> list[MetricDef]:
        """Return MetricDef objects for every metric available on the resource."""
        rid = target.params["resource_id"]
        defs: list[MetricDef] = []
        for raw in self._client.list_metric_definitions(rid):
            granularity_tds = available_granularities(raw)
            defs.append(MetricDef(
                name=raw.name,
                unit=_agg_name(raw.unit),
                aggregations=_aggregations_for(raw),
                dimensions=[
                    getattr(d, "value", None) or str(d)
                    for d in (getattr(raw, "dimensions", None) or [])
                ],
                granularities=[duration_str(g) for g in granularity_tds],
            ))
        return defs

    def query(
        self,
        target: Target,
        defs: list[MetricDef],
        start: datetime,
        end: datetime,
        granularity: timedelta,
    ) -> list[MetricSeries]:
        """Query each MetricDef and return a MetricSeries per returned metric."""
        rid = target.params["resource_id"]
        results: list[MetricSeries] = []

        for d in defs:
            aggregations = d.aggregations
            dim_filter = _dimension_filter(d.dimensions)
            avail = [parse_iso8601_duration(s) for s in d.granularities]
            grain = choose_granularity(granularity, avail)

            try:
                response = self._client.query_resource(
                    rid,
                    metric_names=[d.name],
                    timespan=(start, end),
                    granularity=grain,
                    aggregations=aggregations,
                    filter=dim_filter,
                )
            except Exception:
                try:
                    response = self._client.query_resource(
                        rid,
                        metric_names=[d.name],
                        timespan=(start, end),
                        granularity=grain,
                        aggregations=aggregations,
                        filter=None,
                    )
                except Exception as exc:
                    results.append(MetricSeries(
                        name=d.name,
                        unit=None,
                        granularity=None,
                        timeseries=[],
                        error=str(exc),
                    ))
                    continue

            for metric in (getattr(response, "metrics", None) or []):
                metric_name = getattr(metric, "name", d.name)
                results.append(MetricSeries(
                    name=metric_name,
                    unit=_agg_name(getattr(metric, "unit", None)),
                    granularity=duration_str(grain),
                    timeseries=[
                        _timeseries_to_dict(ts)
                        for ts in (getattr(metric, "timeseries", None) or [])
                    ],
                    error=None,
                ))

        return results
