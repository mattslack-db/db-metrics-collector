from __future__ import annotations

from db_metrics.recommend.load import load_report
from db_metrics.recommend.normalize import canonical_signals


def test_azure_signals(fx):
    sig = canonical_signals(load_report(fx("azure_pg.json")))
    assert sig.mem_pct_avg == 58.0 and sig.mem_pct_peak == 78.0
    assert sig.cpu_peak is not None
    assert sig.connections_peak == 120.0
    assert sig.max_connections == 859.0


def test_aws_signals_memory_from_free(fx):
    sig = canonical_signals(load_report(fx("aws_rds.json")))
    # FreeableMemory avg ~4 GB, min ~1.5 GB -> peak usage driver is the min free
    assert round(sig.mem_free_gb_min, 1) == 1.5
    assert sig.cpu_avg is not None
    assert sig.iops_peak is not None  # Read+Write summed


def test_missing_metric_is_none(fx):
    sig = canonical_signals(load_report(fx("aws_aurora_serverless.json")))
    assert sig.iops_peak is None


def test_azure_managed_instance_alias_metric_names(fx):
    """SQL Managed Instance emits avg_cpu_percent / storage_space_used_mb (MB),
    which must normalize just like flexible-server cpu_percent / storage_used."""
    sig = canonical_signals(load_report(fx("azure_sql_mi.json")))
    assert sig.cpu_avg == 30.0
    assert sig.cpu_peak == 55.0
    # 51200 MB peak / 1024 = 50 GB
    assert sig.storage_used_gb == 50.0


def test_errored_metric_skipped_good_metric_resolved(fx):
    """An errored metric entry must be skipped; good metrics still yield signals."""
    sig = canonical_signals(load_report(fx("errored_metrics.json")))
    # cpu_percent has error="throttled" → should produce None
    assert sig.cpu_avg is None
    assert sig.cpu_peak is None
    # memory_percent is valid → should resolve
    assert sig.mem_pct_avg == 58.0
    assert sig.mem_pct_peak == 78.0
