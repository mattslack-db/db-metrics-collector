"""AWS boto3 session and client factory.

Provides minimal helpers to construct boto3 sessions with specified profile
and region, and to instantiate CloudWatch and RDS clients.
"""

from __future__ import annotations

import boto3


def make_session(profile: str | None = None, region: str | None = None):
    """Create a boto3 session with optional profile and region.

    Args:
        profile: AWS profile name. Defaults to None (use default profile).
        region: AWS region name. Defaults to None (use environment default).

    Returns:
        A boto3.Session instance.
    """
    return boto3.Session(profile_name=profile, region_name=region)


def clients(session):
    """Create CloudWatch and RDS clients from a boto3 session.

    Args:
        session: A boto3.Session instance.

    Returns:
        A tuple of (cloudwatch_client, rds_client).
    """
    cloudwatch = session.client("cloudwatch")
    rds = session.client("rds")
    return (cloudwatch, rds)
