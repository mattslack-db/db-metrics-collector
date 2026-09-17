from __future__ import annotations

import json

from db_metrics.models import Target
from db_metrics.providers.registry import SERVICES

# Fields that belong directly on Target (not in params)
_KNOWN_FIELDS = {"name", "cloud", "service", "hours", "interval"}


def load_targets(path: str) -> list[Target]:
    """Parse a JSON config file and return a validated list of Targets.

    Top-level structure::

        {
            "defaults": {...},   # optional; merged into every target (target keys win)
            "targets": [...]     # required; non-empty list of target dicts
        }

    Raises ValueError for structural problems or invalid target definitions.
    """
    with open(path) as fh:
        raw = json.load(fh)

    defaults: dict = raw.get("defaults", {})
    targets_raw = raw.get("targets")

    if not targets_raw or not isinstance(targets_raw, list):
        raise ValueError(
            "'targets' must be a non-empty list in the config file"
        )

    results: list[Target] = []
    for idx, target_dict in enumerate(targets_raw):
        _validate_and_build(idx, target_dict, defaults, results)

    return results


def _validate_and_build(
    idx: int,
    target_dict: dict,
    defaults: dict,
    results: list[Target],
) -> None:
    # Merge: target keys win over defaults
    merged: dict = {**defaults, **target_dict}

    # Determine a human-readable identifier for error messages
    target_id = merged.get("name", str(idx))

    # Validate presence of required identity fields
    for field in ("name", "cloud", "service"):
        if field not in merged:
            raise ValueError(
                f"Target {target_id!r}: missing required field '{field}'"
            )

    name: str = merged["name"]
    cloud: str = merged["cloud"]
    service: str = merged["service"]

    # Validate service is known
    if service not in SERVICES:
        known = ", ".join(sorted(SERVICES))
        raise ValueError(
            f"Target {name!r}: unknown service '{service}'; known: {known}"
        )

    svc_def = SERVICES[service]

    # Validate cloud matches service definition
    expected_cloud = svc_def["cloud"]
    if cloud != expected_cloud:
        raise ValueError(
            f"Target {name!r}: cloud mismatch — service '{service}' requires "
            f"cloud '{expected_cloud}', got '{cloud}'"
        )

    # Split known fields from params
    params: dict = {k: v for k, v in merged.items() if k not in _KNOWN_FIELDS}

    # Validate required params are present
    missing = [p for p in svc_def["required_params"] if p not in params]
    if missing:
        raise ValueError(
            f"Target {name!r} (service '{service}') missing required param(s): "
            + ", ".join(missing)
        )

    # Build Target — only pass hours/interval when explicitly provided
    kwargs: dict = {"name": name, "cloud": cloud, "service": service, "params": params}
    if "hours" in merged:
        kwargs["hours"] = merged["hours"]
    if "interval" in merged:
        kwargs["interval"] = merged["interval"]

    results.append(Target(**kwargs))
