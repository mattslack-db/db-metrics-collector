"""Tests for CloudWatchSource (db_metrics.providers.aws.cloudwatch).

Uses fake CW clients returning canned payloads — no real AWS calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from db_metrics.models import Target
from db_metrics.providers.aws.cloudwatch import CloudWatchSource

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


def _make_target(dim_name: str = "DBInstanceIdentifier", dim_value: str = "mydb") -> Target:
    return Target(
        name="test-db",
        cloud="aws",
        service="rds",
        params={"dimension_name": dim_name, "dimension_value": dim_value},
    )


class FakeListMetricsClient:
    """Fake CW client for discover() tests."""

    def __init__(self, pages: list[list[dict]]) -> None:
        # pages[i] is the list of Metrics in page i
        self._pages = pages
        self.calls: list[dict] = []

    def list_metrics(self, **kwargs: object) -> dict:
        self.calls.append(dict(kwargs))
        page_idx = len(self.calls) - 1
        if page_idx >= len(self._pages):
            return {"Metrics": []}
        has_next = page_idx < len(self._pages) - 1
        result: dict = {"Metrics": self._pages[page_idx]}
        if has_next:
            result["NextToken"] = f"tok-{page_idx}"
        return result


class FakeGetMetricDataClient:
    """Fake CW client for query() tests."""

    def __init__(self, results_by_id: dict[str, dict] | None = None) -> None:
        # results_by_id: mapping Id -> {"Timestamps": [...], "Values": [...]}
        self._results = results_by_id or {}
        self.calls: list[dict] = []

    def list_metrics(self, **kwargs: object) -> dict:
        # Not used in query tests but required for discover()
        return {"Metrics": []}

    def get_metric_data(self, **kwargs: object) -> dict:
        self.calls.append(dict(kwargs))
        queries: list[dict] = kwargs["MetricDataQueries"]
        results = []
        for q in queries:
            qid = q["Id"]
            canned = self._results.get(qid, {})
            results.append(
                {
                    "Id": qid,
                    "Label": qid,
                    "Timestamps": canned.get("Timestamps", []),
                    "Values": canned.get("Values", []),
                    "StatusCode": "Complete",
                }
            )
        return {"MetricDataResults": results}


# ---------------------------------------------------------------------------
# Test 1: discover deduplication + MetricDef shape
# ---------------------------------------------------------------------------


def test_discover_dedupes_and_builds_metricdefs() -> None:
    """Two entries for CPUUtilization (different dim combos) + one FreeableMemory.

    Expect 2 MetricDefs, deduped by MetricName, with correct aggregations/dims.
    """
    pages = [
        [
            {
                "Namespace": "AWS/RDS",
                "MetricName": "CPUUtilization",
                "Dimensions": [{"Name": "DBInstanceIdentifier", "Value": "db1"}],
            },
            {
                "Namespace": "AWS/RDS",
                "MetricName": "CPUUtilization",
                "Dimensions": [{"Name": "DBInstanceIdentifier", "Value": "db2"}],
            },
            {
                "Namespace": "AWS/RDS",
                "MetricName": "FreeableMemory",
                "Dimensions": [{"Name": "DBInstanceIdentifier", "Value": "db1"}],
            },
        ]
    ]
    client = FakeListMetricsClient(pages)
    source = CloudWatchSource(client)
    target = _make_target()

    defs = source.discover(target)

    assert len(defs) == 2
    names = [d.name for d in defs]
    assert "CPUUtilization" in names
    assert "FreeableMemory" in names

    for d in defs:
        assert d.unit is None
        assert d.aggregations == ["Average", "Maximum", "Minimum", "Sum"]
        assert d.dimensions == ["DBInstanceIdentifier"]


def test_discover_paginates_on_next_token() -> None:
    """Discover must follow NextToken until exhausted."""
    pages = [
        [
            {
                "Namespace": "AWS/RDS",
                "MetricName": "CPUUtilization",
                "Dimensions": [],
            }
        ],
        [
            {
                "Namespace": "AWS/RDS",
                "MetricName": "FreeableMemory",
                "Dimensions": [],
            }
        ],
    ]
    client = FakeListMetricsClient(pages)
    source = CloudWatchSource(client)
    target = _make_target()

    defs = source.discover(target)

    # Two pages fetched
    assert len(client.calls) == 2
    # Second call must carry the token from first response
    assert client.calls[1].get("NextToken") == "tok-0"
    # Both metrics discovered
    assert {d.name for d in defs} == {"CPUUtilization", "FreeableMemory"}


# ---------------------------------------------------------------------------
# Test 2: query honours Period and summarizes correctly
# ---------------------------------------------------------------------------


def test_query_summarizes_and_honors_period() -> None:
    """get_metric_data is called with Period matching granularity, summary is correct."""
    granularity = timedelta(minutes=5)
    period = int(granularity.total_seconds())  # 300

    t0 = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    t1 = datetime(2024, 1, 1, 12, 5, tzinfo=timezone.utc)

    # We need to know what IDs will be generated for CPUUtilization/Average.
    # discover returns defs sorted by name; CPUUtilization is first.
    # aggregations are ["Average","Maximum","Minimum","Sum"] so indices 0..3.
    # q0=Average, q1=Maximum, q2=Minimum, q3=Sum for CPUUtilization
    results_by_id = {
        "q0": {"Timestamps": [t0, t1], "Values": [20.0, 30.0]},
    }
    client = FakeGetMetricDataClient(results_by_id)
    source = CloudWatchSource(client)
    target = _make_target()

    from db_metrics.providers.base import MetricDef

    defs = [
        MetricDef(
            name="CPUUtilization",
            unit=None,
            aggregations=["Average", "Maximum", "Minimum", "Sum"],
            dimensions=["DBInstanceIdentifier"],
        )
    ]

    start = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)

    series = source.query(target, defs, start, end, granularity)

    assert len(series) == 1
    s = series[0]
    assert s.name == "CPUUtilization"
    assert s.error is None
    assert len(s.timeseries) == 1

    ts_entry = s.timeseries[0]
    assert ts_entry["dimensions"] == {"DBInstanceIdentifier": "mydb"}

    points = ts_entry["points"]
    assert len(points) == 2
    assert points[0]["average"] == 20.0
    assert points[1]["average"] == 30.0

    summary = ts_entry["summary"]
    assert "average" in summary
    assert summary["average"]["latest"] == 30.0
    assert summary["average"]["min"] == 20.0
    assert summary["average"]["max"] == 30.0

    # Period must match granularity
    recorded_call = client.calls[0]
    for q in recorded_call["MetricDataQueries"]:
        assert q["MetricStat"]["Period"] == period


# ---------------------------------------------------------------------------
# Test 3: Sum + Average both map to their correct field names end-to-end
# ---------------------------------------------------------------------------


def test_query_maps_sum_and_average_to_fields() -> None:
    """_STAT_TO_FIELD: 'Average'→'average', 'Sum'→'total' — verified end-to-end."""
    t0 = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    # CPUUtilization: q0=Average, q3=Sum
    results_by_id = {
        "q0": {"Timestamps": [t0], "Values": [50.0]},  # Average
        "q3": {"Timestamps": [t0], "Values": [1000.0]},  # Sum
    }
    client = FakeGetMetricDataClient(results_by_id)
    source = CloudWatchSource(client)
    target = _make_target()

    from db_metrics.providers.base import MetricDef

    defs = [
        MetricDef(
            name="CPUUtilization",
            unit=None,
            aggregations=["Average", "Maximum", "Minimum", "Sum"],
            dimensions=["DBInstanceIdentifier"],
        )
    ]

    series = source.query(
        target,
        defs,
        datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc),
        timedelta(minutes=5),
    )

    assert len(series) == 1
    ts_entry = series[0].timeseries[0]
    point = ts_entry["points"][0]

    # Average → 'average', Sum → 'total'
    assert point["average"] == 50.0
    assert point["total"] == 1000.0

    summary = ts_entry["summary"]
    assert summary["average"]["latest"] == 50.0
    assert summary["total"]["latest"] == 1000.0


# ---------------------------------------------------------------------------
# Test 4: query batches into chunks of ≤500
# ---------------------------------------------------------------------------


def test_query_batches_over_500() -> None:
    """200 MetricDefs × 4 stats = 800 queries → must call get_metric_data TWICE."""
    client = FakeGetMetricDataClient()
    source = CloudWatchSource(client)
    target = _make_target()

    from db_metrics.providers.base import MetricDef

    defs = [
        MetricDef(
            name=f"Metric{i:03d}",
            unit=None,
            aggregations=["Average", "Maximum", "Minimum", "Sum"],
            dimensions=["DBInstanceIdentifier"],
        )
        for i in range(200)
    ]

    series = source.query(
        target,
        defs,
        datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc),
        timedelta(minutes=5),
    )

    # 200 defs × 4 stats = 800 total queries, batched in chunks of ≤500
    assert len(client.calls) == 2
    total_queries = sum(len(c["MetricDataQueries"]) for c in client.calls)
    assert total_queries == 800

    # Each batch is ≤500
    for call in client.calls:
        assert len(call["MetricDataQueries"]) <= 500

    # All 200 metrics returned (even with no data)
    assert len(series) == 200
