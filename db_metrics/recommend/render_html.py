"""Self-contained HTML report with embedded PNG charts for the Lakebase recommender."""

from __future__ import annotations

import base64
import html
import io

from .render_text import Row
from .usage_profile import hour_of_day_profile, metric_points


class ReportDependencyError(Exception):
    """Raised when a required optional dependency (matplotlib) is unavailable."""


# ---------------------------------------------------------------------------
# Internal chart builders — matplotlib is imported lazily by each builder so
# the module can be loaded even when matplotlib is not installed.
# ---------------------------------------------------------------------------


def _png_bytes(fig: object) -> bytes:
    """Render *fig* to a PNG byte string and close it."""
    import matplotlib.pyplot as plt  # noqa: PLC0415 – intentionally lazy

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=96, bbox_inches="tight")  # type: ignore[union-attr]
    plt.close(fig)  # type: ignore[arg-type]
    buf.seek(0)
    return buf.read()


def _img_tag(png: bytes) -> str:
    b64 = base64.b64encode(png).decode("ascii")
    return f'<img src="data:image/png;base64,{b64}" alt="chart" style="max-width:100%;height:auto">'


# Series plotted on a 0-100 percentage scale (a small headroom lets a 100% bar
# breathe). Absolute-valued series (IOPS, or raw "Mem (GB)" when RAM is unknown)
# must NOT share this ceiling — clamping them to 115 clips the bars flat.
_PERCENT_LABELS = frozenset({"CPU %", "Mem %", "Conns %"})


def _workload_ylim(labels: list[str]) -> tuple[float, float] | None:
    """Return a fixed (0, 115) y-limit only when every series is a percentage.

    When any absolute-valued series is present the axis must autoscale, so the
    IOPS / memory-GB bars render at their true height instead of being clipped
    against a percentage ceiling.
    """
    if labels and all(label in _PERCENT_LABELS for label in labels):
        return (0.0, 115.0)
    return None


def _workload_chart(row: Row) -> bytes | None:
    """Bar chart of avg vs peak for CPU %, memory %, IOPS, and connection-fill %.

    Returns None when none of those signals are present in the drivers dict.
    Backend must already be set to Agg by the caller (render_html).
    """
    import matplotlib.pyplot as plt  # noqa: PLC0415

    d = row.recommendation.drivers or {}
    labels: list[str] = []
    avg_vals: list[float] = []
    peak_vals: list[float] = []

    # CPU
    cpu_avg = d.get("cpu_avg")
    cpu_peak = d.get("cpu_peak")
    if cpu_avg is not None or cpu_peak is not None:
        labels.append("CPU %")
        avg_vals.append(float(cpu_avg) if cpu_avg is not None else 0.0)
        peak_vals.append(float(cpu_peak) if cpu_peak is not None else 0.0)

    # Memory — convert to % when RAM is known, else raw GB
    used_avg = d.get("used_gb_avg")
    used_peak = d.get("used_gb_peak")
    if used_avg is not None or used_peak is not None:
        ram_gb = row.capacity.ram_gb
        if ram_gb:
            labels.append("Mem %")
            avg_vals.append((float(used_avg) / ram_gb * 100) if used_avg is not None else 0.0)
            peak_vals.append((float(used_peak) / ram_gb * 100) if used_peak is not None else 0.0)
        else:
            labels.append("Mem (GB)")
            avg_vals.append(float(used_avg) if used_avg is not None else 0.0)
            peak_vals.append(float(used_peak) if used_peak is not None else 0.0)

    # IOPS
    iops_avg = d.get("iops_avg")
    iops_peak = d.get("iops_peak")
    if iops_avg is not None or iops_peak is not None:
        labels.append("IOPS")
        avg_vals.append(float(iops_avg) if iops_avg is not None else 0.0)
        peak_vals.append(float(iops_peak) if iops_peak is not None else 0.0)

    # Connection-fill (as % of max_connections) — peak-only series: no misleading 0 avg bar
    conns_peak = d.get("connections_peak")
    max_conns = d.get("max_connections")
    has_conns = conns_peak is not None and max_conns
    if has_conns:
        labels.append("Conns %")

    if not labels:
        return None

    x = list(range(len(labels)))
    # Number of avg/peak labels (before the connections-only label)
    n_paired = len(labels) - (1 if has_conns else 0)
    x_paired = list(range(n_paired))

    width = 0.35
    fig, ax = plt.subplots(figsize=(max(4, len(labels) * 1.5), 3))
    if x_paired:
        ax.bar([i - width / 2 for i in x_paired], avg_vals, width, label="Avg", color="#4C9BE8")
        ax.bar([i + width / 2 for i in x_paired], peak_vals, width, label="Peak", color="#E84C4C")
    if has_conns:
        conns_fill_pct = float(conns_peak) / float(max_conns) * 100  # type: ignore[arg-type]
        ax.bar([n_paired], [conns_fill_pct], width * 2, label="Peak" if not x_paired else None, color="#E84C4C")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ylim = _workload_ylim(labels)
    if ylim is not None:
        ax.set_ylim(*ylim)
    ax.set_ylabel("Value")
    ax.set_title("Workload Metrics — Avg vs Peak")
    ax.legend(loc="upper right")
    fig.tight_layout()
    return _png_bytes(fig)


def _storage_chart(row: Row) -> bytes | None:
    """Single-bar chart of storage used (GB). Returns None when the signal is absent.

    Backend must already be set to Agg by the caller (render_html).
    """
    import matplotlib.pyplot as plt  # noqa: PLC0415

    d = row.recommendation.drivers or {}
    storage_gb = d.get("storage_used_gb")
    if storage_gb is None:
        return None

    fig, ax = plt.subplots(figsize=(3, 3))
    ax.bar(["Storage"], [float(storage_gb)], color="#5DA88A")
    ax.set_ylabel("GB")
    ax.set_title("Storage Used")
    fig.tight_layout()
    return _png_bytes(fig)


def _usage_pattern_chart(row: Row) -> bytes | None:
    """Line chart of the typical daily usage pattern (avg by hour-of-day).

    Folds every collected sample into 24 hour-of-day buckets so the curve shows
    *when* load rises and falls across a day, using the full collection window.
    Returns None when the report carries no raw sample points (summary-only
    reports, e.g. the PowerShell exporter or older fixtures).
    Backend must already be set to Agg by the caller (render_html).
    """
    import matplotlib.pyplot as plt  # noqa: PLC0415

    data = row.report.data
    cpu_pts = metric_points(data, "cpu_percent", "avg_cpu_percent", "CPUUtilization")
    mem_pts = metric_points(data, "memory_percent")

    # (label, hourly values, color, linestyle) — all percentage-scaled series.
    candidates: list[tuple[str, list[float | None], str, str]] = []
    if cpu_pts:
        candidates.append(("CPU % avg", hour_of_day_profile(cpu_pts, "average"), "#4C9BE8", "-"))
        candidates.append(("CPU % peak", hour_of_day_profile(cpu_pts, "maximum"), "#E84C4C", "--"))
    if mem_pts:
        candidates.append(("Mem % avg", hour_of_day_profile(mem_pts, "average"), "#5DA88A", "-"))

    series = [s for s in candidates if any(v is not None for v in s[1])]
    if not series:
        return None

    hours = list(range(24))
    fig, ax = plt.subplots(figsize=(8, 3))
    for label, values, color, linestyle in series:
        # NaN gaps break the line at hours with no samples (rather than interpolating).
        ys = [v if v is not None else float("nan") for v in values]
        ax.plot(hours, ys, label=label, color=color, linestyle=linestyle, marker="o", markersize=3)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 3))
    ax.set_ylim(0, 105)
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("%")
    ax.set_title("Daily Usage Pattern — avg by hour")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    return _png_bytes(fig)


# ---------------------------------------------------------------------------
# Fleet-summary HTML block (no charts — pure text/table)
# ---------------------------------------------------------------------------


def _fleet_summary_html(rows: list[Row], skipped: list[tuple[str, str]]) -> str:
    total = len(rows)
    fixed_count = sum(
        1 for r in rows if not r.recommendation.dynamic and r.recommendation.fixed_cu is not None
    )
    unknown_sku_count = sum(1 for r in rows if not r.capacity.known)

    sum_min_cu: float = 0.0
    sum_max_cu: float = 0.0
    sum_cost_low: float = 0.0
    sum_cost_high: float = 0.0
    has_low = False
    has_high = False

    for r in rows:
        rec = r.recommendation
        cost = r.cost
        if rec.dynamic and rec.min_cu is not None and rec.max_cu is not None:
            sum_min_cu += rec.min_cu
            sum_max_cu += rec.max_cu
        if cost.low is not None:
            sum_cost_low += cost.low
            has_low = True
        if cost.high is not None:
            sum_cost_high += cost.high
            has_high = True

    cost_range = (
        f"${sum_cost_low:,.0f}&ndash;${sum_cost_high:,.0f}/mo"
        if has_low and has_high
        else "n/a"
    )

    skipped_html = ""
    if skipped:
        items = "".join(
            f"<li>{html.escape(p)}: {html.escape(reason)}</li>" for p, reason in skipped
        )
        skipped_html = f"<h3>Skipped Files</h3><ul>{items}</ul>"

    return (
        '<section class="fleet-summary">'
        "<h2>Fleet Summary</h2>"
        "<table>"
        f"<tr><th>Total servers</th><td>{total}</td></tr>"
        f"<tr><th>Fixed-tier servers</th><td>{fixed_count}</td></tr>"
        f"<tr><th>Unknown-SKU servers</th><td>{unknown_sku_count}</td></tr>"
        f"<tr><th>Skipped files</th><td>{len(skipped)}</td></tr>"
        f"<tr><th>Total min CU (dynamic)</th><td>{sum_min_cu:g}</td></tr>"
        f"<tr><th>Total max CU (dynamic)</th><td>{sum_max_cu:g}</td></tr>"
        f"<tr><th>Estimated cost range</th><td>{cost_range}</td></tr>"
        "</table>"
        f"{skipped_html}"
        "</section>"
    )


# ---------------------------------------------------------------------------
# Per-server HTML section
# ---------------------------------------------------------------------------


def _server_section(row: Row) -> str:
    rep = row.report
    rec = row.recommendation
    cap = row.capacity
    cost = row.cost
    d = rec.drivers or {}

    name = html.escape(rep.display_name)
    cloud = html.escape(rep.cloud)
    service = html.escape(rep.service)
    source_label = html.escape(cap.source_label)

    # Charts
    charts_parts: list[str] = []
    workload_png = _workload_chart(row)
    if workload_png:
        charts_parts.append(f'<div class="chart">{_img_tag(workload_png)}</div>')
    usage_png = _usage_pattern_chart(row)
    if usage_png:
        charts_parts.append(f'<div class="chart">{_img_tag(usage_png)}</div>')
    storage_png = _storage_chart(row)
    if storage_png:
        charts_parts.append(f'<div class="chart">{_img_tag(storage_png)}</div>')
    charts_html = f'<div class="charts">{"".join(charts_parts)}</div>' if charts_parts else ""

    # SKU row
    vcpu_str = f"{cap.vcpu:g}" if cap.vcpu is not None else "n/a"
    ram_str = f"{cap.ram_gb:.1f}&nbsp;GB" if cap.ram_gb is not None else "n/a"
    unknown_tag = " <em>(unknown SKU)</em>" if not cap.known else ""
    sku_cell = f"{source_label} [{vcpu_str} vCPU / {ram_str}]{unknown_tag}"

    # Observed load rows (only emit when data is present)
    observed_rows = ""
    cpu_avg = d.get("cpu_avg")
    cpu_peak = d.get("cpu_peak")
    if cpu_avg is not None or cpu_peak is not None:
        a = f"{cpu_avg:.1f}%" if cpu_avg is not None else "n/a"
        p = f"{cpu_peak:.1f}%" if cpu_peak is not None else "n/a"
        observed_rows += f"<tr><th>CPU avg&nbsp;/&nbsp;peak</th><td>{a} / {p}</td></tr>"
    used_avg = d.get("used_gb_avg")
    used_peak = d.get("used_gb_peak")
    if used_avg is not None or used_peak is not None:
        a = f"{used_avg:.1f}&nbsp;GB" if used_avg is not None else "n/a"
        p = f"{used_peak:.1f}&nbsp;GB" if used_peak is not None else "n/a"
        observed_rows += f"<tr><th>Mem avg&nbsp;/&nbsp;peak</th><td>{a} / {p}</td></tr>"
    storage_gb = d.get("storage_used_gb")
    if storage_gb is not None:
        observed_rows += (
            f"<tr><th>Storage used</th><td>{float(storage_gb):.1f}&nbsp;GB</td></tr>"
        )

    # Recommendation
    if rec.min_cu is not None and rec.max_cu is not None:
        rec_text = f"{rec.min_cu:g}&ndash;{rec.max_cu:g} CU (autoscaling)"
    elif rec.fixed_cu is not None:
        rec_text = f"fixed {rec.fixed_cu:g} CU (no autoscaling)"
    else:
        rec_text = "insufficient data &mdash; verify manually"

    # Cost
    if cost.fixed and cost.low is not None:
        cost_text = f"${cost.low:,.0f}/mo (fixed)"
    elif cost.low is not None and cost.high is not None:
        cost_text = f"${cost.low:,.0f}&ndash;${cost.high:,.0f}/mo"
    else:
        cost_text = "n/a"
    placeholder_tag = " <em>(placeholder rate)</em>" if cost.is_placeholder else ""

    # Advisory notes
    notes_html = ""
    if rec.notes:
        items = "".join(f"<li>{html.escape(n)}</li>" for n in rec.notes)
        notes_html = f'<ul class="notes">{items}</ul>'

    return (
        '<section class="server">'
        f"<h2>{name}</h2>"
        f'<p class="meta">{cloud} / {service}</p>'
        f"{charts_html}"
        "<table>"
        f"<tr><th>Source SKU</th><td>{sku_cell}</td></tr>"
        f"{observed_rows}"
        f"<tr><th>Recommendation</th><td>{rec_text}</td></tr>"
        f"<tr><th>Est. monthly cost</th><td>{cost_text}{placeholder_tag}</td></tr>"
        "</table>"
        f"{notes_html}"
        "</section>"
    )


# ---------------------------------------------------------------------------
# CSS (no external URLs — fully self-contained)
# ---------------------------------------------------------------------------

_CSS = """\
  body{font-family:system-ui,sans-serif;margin:2em;color:#222;background:#f7f8fa}
  h1{color:#1a1a2e;border-bottom:2px solid #4C9BE8;padding-bottom:.4em}
  h2{color:#333;border-bottom:1px solid #ccc;padding-bottom:.25em}
  h3{color:#555}
  section{background:#fff;border:1px solid #ddd;border-radius:6px;
          padding:1.5em;margin-bottom:2em;box-shadow:0 1px 3px rgba(0,0,0,.06)}
  section.fleet-summary{background:#eef3ff;border-color:#b0c4e8}
  table{border-collapse:collapse;width:100%;max-width:640px;margin:.5em 0}
  th{text-align:left;padding:.3em .8em .3em 0;color:#555;width:42%;
     font-weight:600;vertical-align:top}
  td{padding:.3em 0}
  .charts{display:flex;flex-wrap:wrap;gap:1em;margin:1em 0}
  .chart img{border:1px solid #eee;border-radius:4px}
  .meta{color:#666;margin-top:-.5em;font-size:.9em}
  ul.notes{color:#b44;margin:.5em 0;padding-left:1.4em}
  ul{padding-left:1.4em}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_html(rows: list[Row], skipped: list[tuple[str, str]], path: str) -> None:
    """Write a fully self-contained HTML file to *path*.

    Raises :class:`ReportDependencyError` when matplotlib is not installed.
    """
    try:
        import matplotlib  # noqa: PLC0415 – lazy import by design

        matplotlib.use("Agg")
    except ImportError as exc:
        raise ReportDependencyError(
            "matplotlib is required for HTML reports. "
            "Install it with:  pip install -e '.[report]'"
        ) from exc

    fleet_html = _fleet_summary_html(rows, skipped)
    server_sections = "".join(_server_section(row) for row in rows)

    doc = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        "<title>Lakebase Sizing Report</title>\n"
        f"<style>\n{_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        "<h1>Lakebase Sizing Report</h1>\n"
        f"{fleet_html}\n"
        f"{server_sections}\n"
        "</body>\n"
        "</html>\n"
    )

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
