"""AWS boto3 session and client factory tests.

These tests ensure that the AWS auth module correctly constructs boto3
sessions with the specified profile and region, and that clients for
CloudWatch and RDS are properly instantiated.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from db_metrics.providers.aws import auth as aws_auth


def test_make_session_with_profile_and_region(monkeypatch):
    """Test make_session passes profile_name and region_name through."""
    session_calls = {}

    def fake_session_class(**kwargs):
        session_calls.update(kwargs)
        return SimpleNamespace(client=lambda svc: None)

    monkeypatch.setattr(aws_auth.boto3, "Session", fake_session_class)
    session = aws_auth.make_session("my-profile", "eu-central-1")

    assert session_calls["profile_name"] == "my-profile"
    assert session_calls["region_name"] == "eu-central-1"


def test_make_session_with_none_profile_and_region(monkeypatch):
    """Test make_session passes None for profile and region when not specified."""
    session_calls = {}

    def fake_session_class(**kwargs):
        session_calls.update(kwargs)
        return SimpleNamespace(client=lambda svc: None)

    monkeypatch.setattr(aws_auth.boto3, "Session", fake_session_class)
    session = aws_auth.make_session()

    assert session_calls.get("profile_name") is None
    assert session_calls.get("region_name") is None


def test_clients_returns_cloudwatch_and_rds(monkeypatch):
    """Test clients returns (cloudwatch_client, rds_client) tuple in order."""
    client_calls = []

    fake_session = SimpleNamespace(
        client=lambda svc: (client_calls.append(svc), f"{svc}-client")[1]
    )

    cloudwatch, rds = aws_auth.clients(fake_session)

    assert client_calls == ["cloudwatch", "rds"]
    assert cloudwatch == "cloudwatch-client"
    assert rds == "rds-client"
