"""CLI orchestrator for the Lakebase recommender.

Entry point: ``db-metrics-recommend <dir-or-files> [options]``.

Exit codes:
  0  — all reports processed successfully
  1  — some reports skipped but at least one succeeded
  2  — usage error / no valid reports found / matplotlib missing for --report
"""

from __future__ import annotations

import argparse
import sys

from .cost import estimate, rate_for
from .load import ReportError, discover_reports, load_report
from .normalize import canonical_signals
from .render_html import ReportDependencyError, render_html
from .render_text import Row, format_fleet, format_server
from .sizing import SizingOpts, recommend
from .skus import capacity_for


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="db-metrics-recommend",
        description="Generate Lakebase sizing recommendations from collector reports.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="Paths to report files or directories containing metrics_*.json files.",
    )
    parser.add_argument(
        "--report",
        metavar="PATH",
        default=None,
        help="Write a self-contained HTML report to this path (requires matplotlib).",
    )
    parser.add_argument(
        "--headroom",
        type=float,
        default=0.30,
        metavar="FLOAT",
        help="Fractional headroom added on top of observed peak (default: 0.30).",
    )
    parser.add_argument(
        "--cu-rate",
        type=float,
        default=None,
        metavar="FLOAT",
        dest="cu_rate",
        help="Override $/CU-hour cost rate (bypasses placeholder default).",
    )
    parser.add_argument(
        "--region",
        metavar="NAME",
        default=None,
        help="Cloud region name (currently reserved for future region-aware pricing).",
    )
    parser.add_argument(
        "--hours-per-month",
        type=float,
        default=730.0,
        metavar="FLOAT",
        dest="hours_per_month",
        help="Hours per month for cost estimation (default: 730).",
    )
    parser.add_argument(
        "--active-fraction",
        type=float,
        default=0.3,
        metavar="FLOAT",
        dest="active_fraction",
        help="Active fraction for scale-to-zero cost estimate (default: 0.3).",
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        default=None,
        help="Write the text output to this file in addition to stdout.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        dest="no_color",
        help="Suppress ANSI colour codes in output (no-op when output is plain text).",
    )
    return parser


def _validate_opts(args: argparse.Namespace) -> str | None:
    """Return an error message for any out-of-range numeric option, else None.

    Guards the sizing/cost math from nonsensical inputs (negative headroom,
    zero hours, out-of-range fractions, negative rates) that would otherwise
    produce silently wrong CU bands and costs.
    """
    if args.headroom < 0:
        return f"--headroom must be >= 0, got {args.headroom}"
    if args.hours_per_month <= 0:
        return f"--hours-per-month must be > 0, got {args.hours_per_month}"
    if not 0 <= args.active_fraction <= 1:
        return f"--active-fraction must be between 0 and 1, got {args.active_fraction}"
    if args.cu_rate is not None and args.cu_rate <= 0:
        return f"--cu-rate must be > 0, got {args.cu_rate}"
    return None


def main(argv: list[str] | None = None) -> int:
    """Run the recommender CLI.

    Parameters
    ----------
    argv:
        Argument list (``sys.argv[1:]`` when *None*).

    Returns
    -------
    int
        Exit code (0 / 1 / 2).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    opts_error = _validate_opts(args)
    if opts_error is not None:
        print(f"error: {opts_error}", file=sys.stderr)
        return 2

    # Discover all candidate paths.
    discovered = discover_reports(args.paths)

    # Load each report; collect successes and failures separately.
    rows: list[Row] = []
    skipped: list[tuple[str, str]] = []

    sizing_opts = SizingOpts(headroom=args.headroom)

    for path in discovered:
        # The whole per-report pipeline (load + normalize + size + cost) is guarded:
        # a malformed-but-loadable report must be skipped, never abort the run.
        try:
            report = load_report(path)
            capacity = capacity_for(
                report.cloud, report.service, report.data.get("inventory") or {}
            )
            signals = canonical_signals(report)
            rec = recommend(capacity, signals, sizing_opts)
            rate, is_placeholder = rate_for(report.cloud, args.cu_rate)
            cost = estimate(
                rec,
                rate,
                is_placeholder,
                hours_per_month=args.hours_per_month,
                active_fraction=args.active_fraction,
            )
        except ReportError as exc:
            skipped.append((exc.path, exc.reason))
            continue
        except Exception as exc:  # noqa: BLE001 – safety net: surface as skip, never abort
            skipped.append((path, f"unexpected error: {exc}"))
            continue

        rows.append(Row(report=report, capacity=capacity, recommendation=rec, cost=cost))

    # Build text output.
    text_parts: list[str] = []
    for row in rows:
        server_text = format_server(row)
        print(server_text)
        text_parts.append(server_text)

    fleet_text = format_fleet(rows, skipped)
    print(fleet_text)
    text_parts.append(fleet_text)

    # Write text to --out when requested.
    if args.out:
        full_text = "\n".join(text_parts)
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(full_text)
        except OSError as exc:
            print(f"warning: could not write --out file: {exc}", file=sys.stderr)

    # Determine exit code (check before writing HTML to avoid empty reports).
    if not rows:
        return 2

    # Write HTML report when --report is given.
    if args.report:
        try:
            render_html(rows, skipped, args.report)
        except ReportDependencyError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if skipped:
        return 1
    return 0
