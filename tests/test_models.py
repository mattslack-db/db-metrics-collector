from db_metrics.models import Target
from db_metrics.providers.base import MetricDef, MetricSeries


def test_target_defaults_and_params():
    t = Target(name="a", cloud="azure", service="postgres-flexible",
               hours=6.0, interval="PT5M", params={"server_name": "s"})
    assert t.params["server_name"] == "s"
    assert t.hours == 6.0


def test_metric_series_optional_error():
    s = MetricSeries(name="cpu", unit="Percent", granularity="PT1M", timeseries=[])
    assert s.error is None
    e = MetricSeries(name="x", unit=None, granularity=None, timeseries=[], error="boom")
    assert e.error == "boom"
