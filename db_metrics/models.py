from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Target:
    name: str
    cloud: str
    service: str
    hours: float = 1.0
    interval: str = "PT1M"
    params: dict = field(default_factory=dict)
