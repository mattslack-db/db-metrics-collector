"""Plain-text rendering for per-server and fleet Lakebase sizing summaries."""

from __future__ import annotations

from dataclasses import dataclass

from .cost import CostEstimate
from .load import Report
from .sizing import Recommendation
from .skus import Capacity


@dataclass(frozen=True)
class Row:
    """Per-server bundle consumed by both text and HTML renderers."""

    report: Report
    capacity: Capacity
    recommendation: Recommendation
    cost: CostEstimate


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fmt_cu(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:g}"


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.0f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}%"


def _fmt_gb(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f} GB"


# ---------------------------------------------------------------------------
# Per-server renderer
# ---------------------------------------------------------------------------


def format_server(row: Row) -> str:
    """Render a single server's sizing summary as a human-readable string."""
    rep = row.report
    cap = row.capacity
    rec = row.recommendation
    cost = row.cost
    d = rec.drivers or {}

    lines: list[str] = []

    # Header
    lines.append(f"{'─' * 60}")
    lines.append(f"  Server : {rep.display_name}")
    lines.append(f"  Cloud  : {rep.cloud} / {rep.service}")

    # Source SKU
    vcpu_str = _fmt_cu(cap.vcpu)
    ram_str = _fmt_gb(cap.ram_gb)
    known_tag = "" if cap.known else " (unknown SKU)"
    lines.append(f"  Source : {cap.source_label}{known_tag}  [{vcpu_str} vCPU / {ram_str}]")

    # Observed load
    lines.append(f"  Observed:")
    lines.append(f"    CPU  avg={_fmt_pct(d.get('cpu_avg'))}  peak={_fmt_pct(d.get('cpu_peak'))}")
    mem_avg = d.get("used_gb_avg")
    mem_peak = d.get("used_gb_peak")
    lines.append(f"    Mem  avg={_fmt_gb(mem_avg)}  peak={_fmt_gb(mem_peak)}")

    # Recommendation
    lines.append(f"  Recommendation:")
    if rec.min_cu is not None and rec.max_cu is not None:
        lines.append(f"    {_fmt_cu(rec.min_cu)}–{_fmt_cu(rec.max_cu)} CU (autoscaling)")
    elif rec.fixed_cu is not None:
        lines.append(f"    fixed {_fmt_cu(rec.fixed_cu)} CU (no autoscaling)")
    else:
        lines.append("    insufficient data — verify manually")

    # Cost
    cost_range: str
    if cost.fixed and cost.low is not None:
        cost_range = f"{_fmt_money(cost.low)}/mo (fixed)"
    elif cost.low is not None and cost.high is not None:
        cost_range = f"{_fmt_money(cost.low)}–{_fmt_money(cost.high)}/mo"
    else:
        cost_range = "n/a"

    placeholder_tag = "  (placeholder rate)" if cost.is_placeholder else ""
    lines.append(f"  Cost   : {cost_range}{placeholder_tag}")

    # Advisory notes
    for note in rec.notes:
        lines.append(f"    ! {note}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fleet roll-up renderer
# ---------------------------------------------------------------------------


def format_fleet(rows: list[Row], skipped: list[tuple[str, str]]) -> str:
    """Render a fleet-level summary: totals, counts, and skipped files."""
    total = len(rows)
    fixed_count = 0
    unknown_sku_count = 0
    excluded_from_cu = 0

    sum_min_cu: float = 0.0
    sum_max_cu: float = 0.0
    sum_cost_low: float = 0.0
    sum_cost_high: float = 0.0
    has_cost_low = False
    has_cost_high = False

    for row in rows:
        rec = row.recommendation
        cap = row.capacity
        cost = row.cost

        if not cap.known:
            unknown_sku_count += 1
        if not rec.dynamic and rec.fixed_cu is not None:
            fixed_count += 1

        # Include in CU sum only dynamic autoscaling rows with valid bands
        if rec.min_cu is not None and rec.max_cu is not None and rec.dynamic:
            sum_min_cu += rec.min_cu
            sum_max_cu += rec.max_cu
        else:
            excluded_from_cu += 1

        if cost.low is not None:
            sum_cost_low += cost.low
            has_cost_low = True
        if cost.high is not None:
            sum_cost_high += cost.high
            has_cost_high = True

    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  FLEET SUMMARY")
    lines.append("=" * 60)

    # Counts
    lines.append(f"  Total servers      : {total}")
    lines.append(f"  Fixed-tier servers : {fixed_count}")
    lines.append(f"  Unknown-SKU servers: {unknown_sku_count}")
    lines.append(f"  Skipped files      : {len(skipped)}")

    # CU totals
    lines.append("")
    lines.append("  Autoscaling CU band totals (dynamic rows only):")
    lines.append(f"    Min CU sum : {_fmt_cu(sum_min_cu)}")
    lines.append(f"    Max CU sum : {_fmt_cu(sum_max_cu)}")
    if excluded_from_cu:
        lines.append(f"    * {excluded_from_cu} server(s) excluded (fixed-tier or insufficient data)")

    # Cost totals
    lines.append("")
    lines.append("  Estimated monthly cost totals:")
    low_str = _fmt_money(sum_cost_low) if has_cost_low else "n/a"
    high_str = _fmt_money(sum_cost_high) if has_cost_high else "n/a"
    lines.append(f"    Cost range : {low_str}–{high_str}/mo")

    # Skipped files
    if skipped:
        lines.append("")
        lines.append("  Skipped files:")
        for path, reason in skipped:
            lines.append(f"    {path}: {reason}")

    lines.append("=" * 60)
    return "\n".join(lines)
