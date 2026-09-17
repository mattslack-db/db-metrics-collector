"""Tests for AzureMonitorSource (providers/azure/monitor.py)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from db_metrics.models import Target
from db_metrics.providers.azure.monitor import AzureMonitorSource


class _FakeClient:
    def list_metric_definitions(self, rid):
        return [SimpleNamespace(name="cpu_percent", unit="Percent",
                supported_aggregation_types=["Average"], dimensions=[],
                namespace="ns", primary_aggregation_type="Average",
                dimension_required=False, metric_availabilities=[
                    SimpleNamespace(granularity=timedelta(minutes=1))])]

    def query_resource(self, rid, *, metric_names, timespan, granularity, aggregations, filter=None):
        ts = SimpleNamespace(metadata_values=[], data=[SimpleNamespace(
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), average=5.0,
            maximum=None, minimum=None, total=None, count=None)])
        return SimpleNamespace(metrics=[SimpleNamespace(name=metric_names[0], unit="Percent", timeseries=[ts])])


def test_azure_source_discovers_and_queries():
    src = AzureMonitorSource(_FakeClient())
    t = Target(name="a", cloud="azure", service="postgres-flexible",
               params={"resource_id": "/rid"})
    defs = src.discover(t)
    assert defs[0].name == "cpu_percent"
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    series = src.query(t, defs, start, start + timedelta(hours=1), timedelta(minutes=1))
    assert series[0].name == "cpu_percent"
    assert series[0].timeseries[0]["summary"]["average"]["latest"] == 5.0


class _FakeClientWithError:
    """Client that always raises on first call, then succeeds on retry with filter=None."""

    def list_metric_definitions(self, rid):
        return [SimpleNamespace(name="disk_iops", unit="CountPerSecond",
                supported_aggregation_types=["Average"], dimensions=[
                    SimpleNamespace(value="DataDisk")],
                namespace="ns", primary_aggregation_type="Average",
                dimension_required=True, metric_availabilities=[
                    SimpleNamespace(granularity=timedelta(minutes=5))])]

    def query_resource(self, rid, *, metric_names, timespan, granularity, aggregations, filter=None):
        if filter is not None:
            raise RuntimeError("dimension filter rejected")
        ts = SimpleNamespace(metadata_values=[], data=[SimpleNamespace(
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), average=100.0,
            maximum=None, minimum=None, total=None, count=None)])
        return SimpleNamespace(metrics=[SimpleNamespace(name=metric_names[0], unit="CountPerSecond", timeseries=[ts])])


def test_azure_source_query_fallback_on_dimension_filter_error():
    """When the dimension-filter query fails, the source retries with filter=None."""
    src = AzureMonitorSource(_FakeClientWithError())
    t = Target(name="b", cloud="azure", service="postgres-flexible",
               params={"resource_id": "/rid2"})
    defs = src.discover(t)
    assert defs[0].name == "disk_iops"
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    series = src.query(t, defs, start, start + timedelta(hours=1), timedelta(minutes=5))
    assert series[0].name == "disk_iops"
    assert series[0].error is None
    assert series[0].timeseries[0]["summary"]["average"]["latest"] == 100.0


class _FakeClientAllFail:
    """Client that always raises regardless of filter."""

    def list_metric_definitions(self, rid):
        return [SimpleNamespace(name="bad_metric", unit="Percent",
                supported_aggregation_types=["Average"], dimensions=[],
                namespace="ns", primary_aggregation_type="Average",
                dimension_required=False, metric_availabilities=[
                    SimpleNamespace(granularity=timedelta(minutes=1))])]

    def query_resource(self, rid, *, metric_names, timespan, granularity, aggregations, filter=None):
        raise RuntimeError("always fails")


def test_azure_source_records_error_when_both_queries_fail():
    """When both the filtered and unfiltered queries fail, the series records an error."""
    src = AzureMonitorSource(_FakeClientAllFail())
    t = Target(name="c", cloud="azure", service="postgres-flexible",
               params={"resource_id": "/rid3"})
    defs = src.discover(t)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    series = src.query(t, defs, start, start + timedelta(hours=1), timedelta(minutes=1))
    assert series[0].name == "bad_metric"
    assert series[0].error == "always fails"
    assert series[0].timeseries == []
