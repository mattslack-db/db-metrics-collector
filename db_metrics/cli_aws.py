"""AWS metrics exporter entry point (console script: db-metrics-aws).

Imports the aws auth module at top level — the only place boto3 is pulled into
the AWS process. Never imports azure.*.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from . import cli_core
from .providers.registry import services_for_cloud

try:
    from .providers.aws.auth import clients, make_session
    _AWS_AVAILABLE = True
except ModuleNotFoundError:
    _AWS_AVAILABLE = False


@dataclass
class _AwsCreds:
    cloudwatch: object
    rds: object


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="db-metrics-aws",
        description="Collect AWS RDS/Aurora performance metrics and configuration "
                    "for one target (via flags) or many (via --config).")
    cli_core.add_common_arguments(parser)
    parser.add_argument("--service", default=None, choices=services_for_cloud("aws"),
                        help="AWS service: rds or aurora.")
    parser.add_argument("--profile", default=None, help="AWS profile name.")
    parser.add_argument("--region", default=None, help="AWS region.")
    parser.add_argument("--identifier", default=None,
                        help="RDS DB instance identifier (service rds).")
    parser.add_argument("--cluster-identifier", default=None,
                        help="Aurora DB cluster identifier (service aurora).")
    return parser


def resolve_credentials(target, cache: dict) -> _AwsCreds:
    profile = target.params.get("profile")
    region = target.params.get("region")
    key = (profile, region)
    if key not in cache:
        session = make_session(profile, region)
        cloudwatch, rds = clients(session)
        cache[key] = _AwsCreds(cloudwatch=cloudwatch, rds=rds)
    return cache[key]


def main(argv: list[str] | None = None) -> int:
    if not _AWS_AVAILABLE:
        print("Error: AWS support is not installed. Run: pip install 'db-metrics[aws]'",
              file=sys.stderr)
        return cli_core.EXIT_USAGE
    args = build_parser().parse_args(argv)
    return cli_core.run(args, cloud="aws", engine_map=None,
                        resolve_credentials=resolve_credentials)


if __name__ == "__main__":
    sys.exit(main())
