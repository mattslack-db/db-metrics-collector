"""`python -m db_metrics` disambiguation stub.

The tool ships two executables — one per cloud — so a bare module invocation is
ambiguous. Point the user at both and exit with the usage code. Imports no cloud
SDK on purpose.
"""

import sys

_USAGE = (
    "db_metrics has two executables — pick the one for your cloud:\n"
    "  db-metrics-azure   (or: python -m db_metrics.cli_azure)\n"
    "  db-metrics-aws     (or: python -m db_metrics.cli_aws)\n"
)


def main() -> int:
    sys.stderr.write(_USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
