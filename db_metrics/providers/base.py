from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from db_metrics.models import Target


@dataclass
class MetricDef:
    name: str
    unit: str | None
    aggregations: list[str]
    dimensions: list[str] = field(default_factory=list)
    granularities: list[str] = field(default_factory=list)


@dataclass
class MetricSeries:
    name: str
    unit: str | None
    granularity: str | None
    timeseries: list[dict]
    error: str | None = None


class MetricSource(Protocol):
    def discover(self, target: Target) -> list[MetricDef]:
        ...

    def query(
        self,
        target: Target,
        defs: list[MetricDef],
        start: datetime,
        end: datetime,
        granularity: timedelta,
    ) -> list[MetricSeries]:
        ...


class InventoryAdapter(Protocol):
    def collect(self, target: Target) -> dict:
        ...
