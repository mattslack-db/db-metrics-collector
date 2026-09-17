# db_metrics/recommend/sizing.py
"""Translate source capacity + observed load into a Lakebase CU band. Pure core."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .normalize import Signals
from .skus import Capacity


@dataclass(frozen=True)
class SizingOpts:
    headroom: float = 0.30
    gb_per_cu: float = 2.0
    vcpu_per_cu: float = 1.0
    min_cu: float = 0.5
    max_cu_dynamic: float = 64.0
    band_span_max: float = 16.0
    # Fixed-size computes (no autoscaling) accept any integer CU in this range.
    fixed_cu_min: float = 65.0
    fixed_cu_max: float = 112.0


@dataclass(frozen=True)
class Recommendation:
    min_cu: float | None
    max_cu: float | None
    dynamic: bool
    fixed_cu: float | None
    notes: tuple[str, ...]
    drivers: dict


def _snap_cu_up(cu: float) -> float:
    """Round *cu* up to the nearest CU value settable on a Lakebase autoscaling
    endpoint.

    The API/UI accept ``0.5`` and then whole integers (``1, 2, 3, ...``) — there
    are no fractional CU above 1 (so e.g. 6.5 CU cannot be set; it becomes 7).
    Snapping up keeps the recommended capacity at or above the computed need.
    """
    if cu <= 0.5:
        return 0.5
    return float(math.ceil(cu))


def _used_gb(signals: Signals, ram_gb: float | None) -> tuple[float | None, float | None]:
    """Return (avg_used_gb, peak_used_gb) or (None, None) if not derivable."""
    if signals.mem_pct_avg is not None and ram_gb is not None:
        avg = signals.mem_pct_avg / 100.0 * ram_gb
        peak_pct = signals.mem_pct_peak if signals.mem_pct_peak is not None else signals.mem_pct_avg
        return avg, peak_pct / 100.0 * ram_gb
    if signals.mem_free_gb_avg is not None and ram_gb is not None:
        avg = max(ram_gb - signals.mem_free_gb_avg, 0.0)
        free_min = signals.mem_free_gb_min if signals.mem_free_gb_min is not None else signals.mem_free_gb_avg
        return avg, max(ram_gb - free_min, 0.0)
    return None, None


def _cpu_cu(cpu_pct: float | None, vcpu: float | None, vcpu_per_cu: float) -> float | None:
    if cpu_pct is None or vcpu is None:
        return None
    return cpu_pct / 100.0 * vcpu / vcpu_per_cu


def _max_opt(*vals: float | None) -> float | None:
    present = [v for v in vals if v is not None]
    return max(present) if present else None


def recommend(capacity: Capacity, signals: Signals, opts: SizingOpts = SizingOpts()) -> Recommendation:
    used_avg, used_peak = _used_gb(signals, capacity.ram_gb)
    cu_ram_avg = used_avg / opts.gb_per_cu if used_avg is not None else None
    cu_ram_peak = used_peak / opts.gb_per_cu if used_peak is not None else None
    cu_cpu_avg = _cpu_cu(signals.cpu_avg, capacity.vcpu, opts.vcpu_per_cu)
    cu_cpu_peak = _cpu_cu(signals.cpu_peak, capacity.vcpu, opts.vcpu_per_cu)

    min_need = _max_opt(cu_ram_avg, cu_cpu_avg)
    max_need = _max_opt(cu_ram_peak, cu_cpu_peak)

    drivers = {
        "source_label": capacity.source_label,
        "used_gb_avg": used_avg, "used_gb_peak": used_peak,
        "cpu_avg": signals.cpu_avg, "cpu_peak": signals.cpu_peak,
        "iops_avg": signals.iops_avg, "iops_peak": signals.iops_peak,
        "storage_used_gb": signals.storage_used_gb,
        "connections_peak": signals.connections_peak,
        "max_connections": signals.max_connections,
    }

    if min_need is None or max_need is None:
        return Recommendation(
            None, None, True, None,
            ("insufficient data: unknown SKU and no absolute-usage signal — verify manually",),
            drivers,
        )

    notes: list[str] = []
    if not capacity.known:
        notes.append(f"unknown SKU ({capacity.source_label}); sizing used available signals only")

    min_cu = _snap_cu_up(min_need * (1 + opts.headroom))
    max_cu = _snap_cu_up(max_need * (1 + opts.headroom))

    # Fixed-size escalation when the peak exceeds the dynamic range. Fixed
    # computes accept any integer CU in [fixed_cu_min, fixed_cu_max]; max_cu is
    # already snapped to an integer here, so clamp it into that range.
    if max_cu > opts.max_cu_dynamic:
        fixed = min(max(max_cu, opts.fixed_cu_min), opts.fixed_cu_max)
        if max_cu > opts.fixed_cu_max:
            notes.append(
                f"peak need {max_cu:g} CU exceeds max fixed size; capped at {opts.fixed_cu_max:g}"
            )
        notes.append(
            f"peak exceeds {opts.max_cu_dynamic:g} CU dynamic range; "
            "recommending a fixed size (no autoscaling)"
        )
        return Recommendation(None, None, False, fixed, tuple(notes), drivers)

    min_cu = min(max(min_cu, opts.min_cu), opts.max_cu_dynamic)
    max_cu = min(max(max_cu, min_cu), opts.max_cu_dynamic)

    if max_cu - min_cu > opts.band_span_max:
        min_cu = max(max_cu - opts.band_span_max, opts.min_cu)
        notes.append(f"min raised to keep autoscaling band within {opts.band_span_max} CU")

    conns, limit = signals.connections_peak, signals.max_connections
    if conns is not None and limit and limit > 0 and conns / limit > 0.8:
        notes.append(f"connections near limit ({conns:.0f}/{limit:.0f}); verify Lakebase connection budget")

    return Recommendation(min_cu, max_cu, True, None, tuple(notes), drivers)
