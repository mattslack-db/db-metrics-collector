"""Cloud-agnostic run engine shared by the two cloud entry points.

Imports NO cloud SDK and NO cloud `auth` module at load time. Each entry point
supplies its cloud, its optional legacy engine map, and a `resolve_credentials`
callback; this module owns the parser scaffold, target building, foreign-cloud
rejection, per-target collection, output, and exit codes.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from datetime import datetime, timezone

from . import config, report
from .models import Target
from .providers.registry import SERVICES, build_providers
from .timewindow import DEFAULT_INTERVAL, build_window, parse_iso8601_duration

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_ERROR = 1

_AZURE_ID_FLAGS = ("subscription", "resource_group", "server_name", "database")
_AWS_ID_FLAGS = ("profile", "region", "identifier", "cluster_identifier")
_ID_FLAGS_BY_CLOUD = {"azure": _AZURE_ID_FLAGS, "aws": _AWS_ID_FLAGS}
_ALL_ID_FLAGS = _AZURE_ID_FLAGS + _AWS_ID_FLAGS

_TIMESTAMP_FMT = "%Y%m%d_%H%M%S"


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=None,
                        help="JSON config file describing a list of targets "
                             "(mutually exclusive with single-target flags).")
    parser.add_argument("--hours", type=float, default=1.0,
                        help="Look-back window in hours (default: 1).")
    parser.add_argument("--interval", default=DEFAULT_INTERVAL,
                        help="Granularity as ISO-8601 duration (default: PT1M).")
    parser.add_argument("--out", default=None,
                        help="Output JSON path for a single target "
                             "(default: metrics_<name>_<timestamp>.json).")
    parser.add_argument("--no-console", action="store_true",
                        help="Suppress console summaries (JSON only).")


def default_out_path(name: str) -> str:
    stamp = datetime.now(timezone.utc).strftime(_TIMESTAMP_FMT)
    return f"metrics_{name}_{stamp}.json"


def _summary_out_path() -> str:
    stamp = datetime.now(timezone.utc).strftime(_TIMESTAMP_FMT)
    return f"summary_{stamp}.json"


# --- target construction (pure) ------------------------------------------- #

def _explicit_single_flags(args) -> bool:
    if getattr(args, "service", None) is not None:
        return True
    return any(getattr(args, flag, None) is not None for flag in _ALL_ID_FLAGS)


def _params_for(args, flags) -> dict:
    return {flag: getattr(args, flag) for flag in flags
            if getattr(args, flag, None) is not None}


def _single_target_name(args, service: str) -> str:
    return (getattr(args, "server_name", None) or getattr(args, "identifier", None)
            or getattr(args, "cluster_identifier", None) or getattr(args, "database", None)
            or service)


def targets_from_args(args, *, cloud: str, engine_map: dict | None = None) -> list[Target]:
    """Build the target list. Pure (may read the config file); raises ValueError
    on invalid flag combinations, which run() maps to EXIT_USAGE."""
    if args.config:
        if _explicit_single_flags(args):
            raise ValueError(
                "--config is mutually exclusive with single-target flags.")
        return config.load_targets(args.config)

    if getattr(args, "service", None) is not None:
        service = args.service
    elif engine_map is not None:
        service = engine_map[args.engine]
    else:
        raise ValueError("--service is required (no legacy engine default for this cloud).")

    params = _params_for(args, _ID_FLAGS_BY_CLOUD[cloud])
    target = Target(name=_single_target_name(args, service), cloud=cloud,
                    service=service, hours=args.hours, interval=args.interval, params=params)
    return [target]


def reject_foreign_targets(targets: list[Target], allowed_cloud: str) -> str | None:
    """Return an error naming every target whose cloud != allowed_cloud, else None."""
    foreign = [t for t in targets if t.cloud != allowed_cloud]
    if not foreign:
        return None
    names = ", ".join(f"'{t.name}' (cloud '{t.cloud}')" for t in foreign)
    other = "db-metrics-aws" if allowed_cloud == "azure" else "db-metrics-azure"
    return (f"This is the {allowed_cloud} exporter; it cannot collect these "
            f"targets: {names}. Use {other} for those.")


# --- execution ------------------------------------------------------------ #

def _validate_params(targets: list[Target]) -> str | None:
    """Return an error message if any target has an unknown service or missing
    required params, else None.  Mirrors the checks in build_providers so that
    single-target flag errors surface as EXIT_USAGE instead of EXIT_ERROR."""
    for target in targets:
        if target.service not in SERVICES:
            known = ", ".join(sorted(SERVICES))
            return (f"Target '{target.name}': unknown service '{target.service}'. "
                    f"Known services: {known}")
        required = SERVICES[target.service]["required_params"]
        missing = [p for p in required if not target.params.get(p)]
        if missing:
            return (f"Target '{target.name}': missing required param(s) for service "
                    f"'{target.service}': {', '.join(missing)}")
    return None


def _validate_windows(targets: list[Target]) -> str | None:
    for target in targets:
        try:
            parse_iso8601_duration(target.interval)
        except ValueError as exc:
            return f"Target '{target.name}': {exc}"
        if target.hours <= 0:
            return f"Target '{target.name}': hours must be positive, got {target.hours}"
    return None


def _collect_target(target: Target, creds, single: bool, out_override: str | None):
    source, adapter = build_providers(target, creds)
    inventory = adapter.collect(target)
    defs = source.discover(target)
    serialized_defs = [dataclasses.asdict(d) for d in defs]
    window = build_window(target.hours)
    grain = parse_iso8601_duration(target.interval)
    series = source.query(target, defs, window[0], window[1], grain)
    rep = report.build_report(
        target=target, resource_scope=target.params.get("resource_id"),
        inventory=inventory, definitions=serialized_defs, metrics=series,
        window=window, interval=target.interval)
    path = (out_override or default_out_path(target.name)) if single else default_out_path(target.name)
    report.write_json(rep, path)
    return rep, path


def run(args, *, cloud: str, engine_map: dict | None, resolve_credentials) -> int:
    try:
        targets = targets_from_args(args, cloud=cloud, engine_map=engine_map)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    foreign = reject_foreign_targets(targets, cloud)
    if foreign:
        print(f"Error: {foreign}", file=sys.stderr)
        return EXIT_USAGE

    window_error = _validate_windows(targets)
    if window_error:
        print(f"Error: {window_error}", file=sys.stderr)
        return EXIT_USAGE

    params_error = _validate_params(targets)
    if params_error:
        print(f"Error: {params_error}", file=sys.stderr)
        return EXIT_USAGE

    single = len(targets) == 1
    creds_cache: dict = {}
    results: list[dict] = []
    had_error = False

    for target in targets:
        try:
            creds = resolve_credentials(target, creds_cache)
            rep, path = _collect_target(target, creds, single, args.out)
            results.append(rep)
            if not args.no_console:
                print(report.render_console_summary(rep))
            print(f"Report written to: {path}", file=sys.stderr)
        except Exception as exc:  # a failing target is recorded, not fatal
            had_error = True
            results.append({"name": target.name, "cloud": target.cloud,
                            "service": target.service, "error": str(exc)})
            print(f"Target '{target.name}' failed: {exc}", file=sys.stderr)

    if len(targets) > 1:
        summary = report.build_summary(results)
        summary_path = _summary_out_path()
        report.write_json(summary, summary_path)
        if not args.no_console:
            print(report.render_summary_table(summary))
        print(f"Summary written to: {summary_path}", file=sys.stderr)

    return EXIT_ERROR if had_error else EXIT_OK
