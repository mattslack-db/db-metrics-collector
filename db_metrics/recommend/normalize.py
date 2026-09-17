"""Map cloud-specific metric names to a common Signals shape. Pure."""

from __future__ import annotations

from dataclasses import dataclass

from .load import Report

BYTES_PER_GB = 1024 ** 3


@dataclass(frozen=True)
class Signals:
    cpu_avg: float | None = None
    cpu_peak: float | None = None
    mem_pct_avg: float | None = None
    mem_pct_peak: float | None = None
    mem_free_gb_avg: float | None = None
    mem_free_gb_min: float | None = None
    connections_peak: float | None = None
    max_connections: float | None = None
    iops_avg: float | None = None
    iops_peak: float | None = None
    storage_used_gb: float | None = None


def _summary(report: Report, *metric_names: str) -> dict | None:
    """Return the summary block for the first matching, non-errored metric.

    Accepts several candidate names so services that emit the same signal under
    a different Azure Monitor metric name (e.g. SQL Managed Instance's
    ``avg_cpu_percent`` vs flexible server's ``cpu_percent``) resolve too.
    """
    wanted = set(metric_names)
    for metric in report.data.get("metrics", []):
        if metric.get("name") not in wanted or metric.get("error"):
            continue
        series = metric.get("timeseries") or []
        if not series:
            return None
        primary = next((s for s in series if not s.get("dimensions")), series[0])
        return primary.get("summary") or None
    return None


def _stat(summary: dict | None, field: str, key: str) -> float | None:
    if not summary:
        return None
    block = summary.get(field)
    if not block or block.get(key) is None:
        return None
    return float(block[key])


def _avg(summary: dict | None) -> float | None:
    return _stat(summary, "average", "avg")


def _peak(summary: dict | None) -> float | None:
    val = _stat(summary, "maximum", "max")
    return val if val is not None else _stat(summary, "average", "max")


def _sum_opt(a: float | None, b: float | None) -> float | None:
    if a is None and b is None:
        return None
    return (a or 0.0) + (b or 0.0)


def _first(*vals: float | None) -> float | None:
    """Return first non-None value, or None if all are None. Preserves 0.0."""
    return next((v for v in vals if v is not None), None)


def _azure_storage_gb(report: Report) -> float | None:
    """Resolve peak storage-used to GB across the byte- and MB-named variants.

    Flexible/single servers emit ``storage_used`` in bytes; SQL Managed Instance
    emits ``storage_space_used_mb`` in MB. Unit differs, so convert explicitly.
    """
    bytes_peak = _peak(_summary(report, "storage_used", "storage"))
    if bytes_peak is not None:
        return bytes_peak / BYTES_PER_GB
    mb_peak = _peak(_summary(report, "storage_space_used_mb"))
    if mb_peak is not None:
        return mb_peak / 1024.0
    return None


def _azure(report: Report) -> Signals:
    # cpu_percent (flexible/SQL DB/Cosmos) and avg_cpu_percent (Managed Instance)
    # are the same %-CPU signal under different Azure Monitor metric names.
    cpu = _summary(report, "cpu_percent", "avg_cpu_percent")
    mem = _summary(report, "memory_percent")
    conns = _summary(report, "active_connections")
    maxc = _summary(report, "max_connections")
    iops = _summary(report, "iops")
    return Signals(
        cpu_avg=_avg(cpu), cpu_peak=_peak(cpu),
        mem_pct_avg=_avg(mem), mem_pct_peak=_peak(mem),
        connections_peak=_peak(conns),
        max_connections=_peak(maxc),
        iops_avg=_avg(iops), iops_peak=_peak(iops),
        storage_used_gb=_azure_storage_gb(report),
    )


def _aws(report: Report) -> Signals:
    cpu = _summary(report, "CPUUtilization")
    freemem = _summary(report, "FreeableMemory")
    conns = _summary(report, "DatabaseConnections")
    read = _summary(report, "ReadIOPS")
    write = _summary(report, "WriteIOPS")
    freestore = _summary(report, "FreeStorageSpace")
    free_avg = _avg(freemem)
    free_min = _first(_stat(freemem, "minimum", "min"), _stat(freemem, "average", "min"))
    alloc = ((report.data.get("inventory") or {}).get("server") or {}).get("allocated_storage_gb")
    free_store_min = _first(_stat(freestore, "minimum", "min"), _stat(freestore, "average", "min"))
    storage_used = None
    if alloc is not None and free_store_min is not None:
        storage_used = float(alloc) - free_store_min / BYTES_PER_GB
    return Signals(
        cpu_avg=_avg(cpu), cpu_peak=_peak(cpu),
        mem_free_gb_avg=(free_avg / BYTES_PER_GB) if free_avg is not None else None,
        mem_free_gb_min=(free_min / BYTES_PER_GB) if free_min is not None else None,
        connections_peak=_peak(conns),
        iops_avg=_sum_opt(_avg(read), _avg(write)),
        iops_peak=_sum_opt(_peak(read), _peak(write)),
        storage_used_gb=storage_used,
    )


def canonical_signals(report: Report) -> Signals:
    if report.cloud == "aws":
        return _aws(report)
    return _azure(report)
