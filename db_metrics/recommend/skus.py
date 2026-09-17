"""Map a source SKU / instance class to (vCPU, RAM_GB). Pure data + lookup."""

from __future__ import annotations

from dataclasses import dataclass

ACU_GB = 2.0  # Aurora Serverless v2: ~2 GB RAM per ACU


@dataclass(frozen=True)
class Capacity:
    vcpu: float | None
    ram_gb: float | None
    source_label: str
    known: bool


# Azure Flexible Server families: Burstable (B), General Purpose (D), Memory Optimized (E).
_AZURE_SKUS: dict[str, tuple[float, float]] = {
    "Standard_B1ms": (1, 2), "Standard_B2s": (2, 4), "Standard_B2ms": (2, 8),
    "Standard_B4ms": (4, 16), "Standard_B8ms": (8, 32), "Standard_B12ms": (12, 48),
    "Standard_B16ms": (16, 64), "Standard_B20ms": (20, 80),
    "Standard_D2ds_v4": (2, 8), "Standard_D4ds_v4": (4, 16), "Standard_D8ds_v4": (8, 32),
    "Standard_D16ds_v4": (16, 64), "Standard_D32ds_v4": (32, 128), "Standard_D48ds_v4": (48, 192),
    "Standard_D64ds_v4": (64, 256),
    "Standard_D2ds_v5": (2, 8), "Standard_D4ds_v5": (4, 16), "Standard_D8ds_v5": (8, 32),
    "Standard_D16ds_v5": (16, 64), "Standard_D32ds_v5": (32, 128), "Standard_D48ds_v5": (48, 192),
    "Standard_D64ds_v5": (64, 256), "Standard_D96ds_v5": (96, 384),
    "Standard_E2ds_v4": (2, 16), "Standard_E4ds_v4": (4, 32), "Standard_E8ds_v4": (8, 64),
    "Standard_E16ds_v4": (16, 128), "Standard_E32ds_v4": (32, 256), "Standard_E48ds_v4": (48, 384),
    "Standard_E64ds_v4": (64, 512),
    "Standard_E2ds_v5": (2, 16), "Standard_E4ds_v5": (4, 32), "Standard_E8ds_v5": (8, 64),
    "Standard_E16ds_v5": (16, 128), "Standard_E32ds_v5": (32, 256), "Standard_E48ds_v5": (48, 384),
    "Standard_E64ds_v5": (64, 512), "Standard_E96ds_v5": (96, 672),
}

# AWS RDS/Aurora instance classes.
_AWS_CLASSES: dict[str, tuple[float, float]] = {
    "db.t3.micro": (2, 1), "db.t3.small": (2, 2), "db.t3.medium": (2, 4),
    "db.t3.large": (2, 8), "db.t3.xlarge": (4, 16), "db.t3.2xlarge": (8, 32),
    "db.t4g.micro": (2, 1), "db.t4g.small": (2, 2), "db.t4g.medium": (2, 4),
    "db.t4g.large": (2, 8), "db.t4g.xlarge": (4, 16), "db.t4g.2xlarge": (8, 32),
    "db.m5.large": (2, 8), "db.m5.xlarge": (4, 16), "db.m5.2xlarge": (8, 32),
    "db.m5.4xlarge": (16, 64), "db.m5.8xlarge": (32, 128),
    "db.m6i.large": (2, 8), "db.m6i.xlarge": (4, 16), "db.m6i.2xlarge": (8, 32),
    "db.m6i.4xlarge": (16, 64), "db.m6i.8xlarge": (32, 128),
    "db.m6g.large": (2, 8), "db.m6g.xlarge": (4, 16), "db.m6g.2xlarge": (8, 32),
    "db.r5.large": (2, 16), "db.r5.xlarge": (4, 32), "db.r5.2xlarge": (8, 64),
    "db.r5.4xlarge": (16, 128),
    "db.r6g.large": (2, 16), "db.r6g.xlarge": (4, 32), "db.r6g.2xlarge": (8, 64),
    "db.r6g.4xlarge": (16, 128), "db.r6g.8xlarge": (32, 256),
    "db.r6i.large": (2, 16), "db.r6i.xlarge": (4, 32), "db.r6i.2xlarge": (8, 64),
}


def _from_table(table: dict[str, tuple[float, float]], key: str | None) -> Capacity:
    if key and key in table:
        vcpu, ram = table[key]
        return Capacity(float(vcpu), float(ram), key, True)
    return Capacity(None, None, key or "unknown", False)


def _aurora_capacity(server: dict) -> Capacity:
    members = server.get("members") or []
    writer = next((m for m in members if m.get("is_writer")), None)
    chosen = writer or (members[0] if members else None)
    if chosen and chosen.get("class"):
        return _from_table(_AWS_CLASSES, chosen["class"])
    sv2 = server.get("serverless_v2")
    if sv2 and sv2.get("max_acu") is not None:
        max_acu = float(sv2["max_acu"])
        return Capacity(None, max_acu * ACU_GB, f"serverless-v2 maxACU={sv2['max_acu']}", True)
    return Capacity(None, None, "unknown", False)


def capacity_for(cloud: str, service: str, inventory: dict) -> Capacity:
    """Resolve source (vCPU, RAM_GB) from inventory; never raises."""
    server = (inventory or {}).get("server") or {}
    if cloud == "azure":
        name = (server.get("sku") or {}).get("name")
        return _from_table(_AZURE_SKUS, name)
    if cloud == "aws":
        if service == "aurora":
            return _aurora_capacity(server)
        return _from_table(_AWS_CLASSES, server.get("class"))
    return Capacity(None, None, f"{cloud}:unknown", False)
