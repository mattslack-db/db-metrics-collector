from __future__ import annotations

import json

import pytest

from db_metrics.config import load_targets


# ---------------------------------------------------------------------------
# Verbatim tests from brief
# ---------------------------------------------------------------------------


def test_load_targets_merges_defaults(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps(
            {
                "defaults": {"hours": 6, "interval": "PT5M"},
                "targets": [
                    {
                        "name": "a",
                        "cloud": "azure",
                        "service": "postgres-flexible",
                        "subscription": "s",
                        "resource_group": "rg",
                        "server_name": "srv",
                    }
                ],
            }
        )
    )
    ts = load_targets(str(p))
    assert ts[0].hours == 6 and ts[0].params["server_name"] == "srv"


def test_load_targets_rejects_unknown_service(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps({"targets": [{"name": "a", "cloud": "azure", "service": "nope"}]})
    )
    with pytest.raises(ValueError):
        load_targets(str(p))


def test_load_targets_rejects_missing_required_param(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "name": "a",
                        "cloud": "azure",
                        "service": "postgres-flexible",
                        "subscription": "s",
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError):
        load_targets(str(p))


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------


def test_unknown_service_error_names_target(tmp_path):
    """Error message must name the target."""
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps({"targets": [{"name": "my-target", "cloud": "azure", "service": "nope"}]})
    )
    with pytest.raises(ValueError, match="my-target"):
        load_targets(str(p))


def test_missing_required_param_error_names_param(tmp_path):
    """Error message must name the missing parameter."""
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "name": "srv-target",
                        "cloud": "azure",
                        "service": "postgres-flexible",
                        "subscription": "s",
                        # resource_group and server_name are missing
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="resource_group"):
        load_targets(str(p))


def test_target_overrides_default(tmp_path):
    """A per-target hours value beats the default."""
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps(
            {
                "defaults": {"hours": 6, "interval": "PT5M"},
                "targets": [
                    {
                        "name": "b",
                        "cloud": "azure",
                        "service": "postgres-flexible",
                        "subscription": "s",
                        "resource_group": "rg",
                        "server_name": "srv",
                        "hours": 3,
                    }
                ],
            }
        )
    )
    ts = load_targets(str(p))
    assert ts[0].hours == 3


def test_defaults_supply_shared_param_into_params(tmp_path):
    """A default 'subscription' ends up in target.params."""
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps(
            {
                "defaults": {"subscription": "shared-sub"},
                "targets": [
                    {
                        "name": "c",
                        "cloud": "azure",
                        "service": "postgres-flexible",
                        "resource_group": "rg",
                        "server_name": "srv",
                    }
                ],
            }
        )
    )
    ts = load_targets(str(p))
    assert ts[0].params["subscription"] == "shared-sub"


def test_cloud_mismatch_raises(tmp_path):
    """Specifying cloud='aws' for an azure-only service must raise ValueError."""
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "name": "d",
                        "cloud": "aws",
                        "service": "postgres-flexible",
                        "subscription": "s",
                        "resource_group": "rg",
                        "server_name": "srv",
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="cloud"):
        load_targets(str(p))


def test_missing_targets_key_raises(tmp_path):
    """A JSON file with no 'targets' key must raise ValueError."""
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"defaults": {}}))
    with pytest.raises(ValueError, match="targets"):
        load_targets(str(p))


def test_empty_targets_list_raises(tmp_path):
    """An empty targets list must raise ValueError."""
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"targets": []}))
    with pytest.raises(ValueError, match="targets"):
        load_targets(str(p))


def test_target_named_by_index_when_no_name(tmp_path):
    """When a target has no 'name', the error message identifies it by index."""
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps({"targets": [{"cloud": "azure", "service": "nope"}]})
    )
    with pytest.raises(ValueError, match="0"):
        load_targets(str(p))


def test_multiple_targets_returned(tmp_path):
    """Two valid targets produce a list of two Target objects."""
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps(
            {
                "defaults": {"subscription": "s", "resource_group": "rg"},
                "targets": [
                    {
                        "name": "t1",
                        "cloud": "azure",
                        "service": "postgres-flexible",
                        "server_name": "pg-1",
                    },
                    {
                        "name": "t2",
                        "cloud": "azure",
                        "service": "mysql-flexible",
                        "server_name": "my-1",
                    },
                ],
            }
        )
    )
    ts = load_targets(str(p))
    assert len(ts) == 2
    assert ts[0].name == "t1"
    assert ts[1].service == "mysql-flexible"


def test_dataclass_defaults_apply_when_omitted(tmp_path):
    """When hours and interval are absent from both defaults and target, dataclass defaults hold."""
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "name": "e",
                        "cloud": "azure",
                        "service": "postgres-flexible",
                        "subscription": "s",
                        "resource_group": "rg",
                        "server_name": "srv",
                    }
                ]
            }
        )
    )
    ts = load_targets(str(p))
    assert ts[0].hours == 1.0
    assert ts[0].interval == "PT1M"
