"""Estimate monthly Lakebase cost from a CU recommendation. Pure."""

from __future__ import annotations

from dataclasses import dataclass

from .sizing import Recommendation

HOURS_PER_MONTH = 730.0

# NOTE: placeholder $/CU-hour. NOT authoritative Lakebase pricing — override
# with --cu-rate or the rate table. Output flags when this default is in use.
PLACEHOLDER_RATE = 0.35

DEFAULT_RATES: dict[str, float] = {
    # cloud -> $/CU-hour. Seeded with the placeholder; edit per contract/region.
    "azure": PLACEHOLDER_RATE,
    "aws": PLACEHOLDER_RATE,
}


@dataclass(frozen=True)
class CostEstimate:
    low: float | None
    high: float | None
    scale_to_zero_low: float | None
    rate: float
    is_placeholder: bool
    hours_per_month: float
    fixed: bool


def rate_for(cloud: str, override: float | None) -> tuple[float, bool]:
    """Resolve the ($/CU-hour, is_placeholder) rate for a cloud.

    Precedence: an explicit ``override`` wins; otherwise a per-cloud entry in
    ``DEFAULT_RATES`` that has been edited away from the placeholder is used
    (dormant until the table is customized); otherwise the flagged placeholder.
    """
    if override is not None:
        return float(override), False
    if cloud in DEFAULT_RATES and DEFAULT_RATES[cloud] != PLACEHOLDER_RATE:
        return DEFAULT_RATES[cloud], False
    return PLACEHOLDER_RATE, True


def estimate(
    rec: Recommendation,
    rate: float,
    is_placeholder: bool,
    hours_per_month: float = HOURS_PER_MONTH,
    active_fraction: float = 0.3,
) -> CostEstimate:
    if not rec.dynamic and rec.fixed_cu is not None:
        cost = rec.fixed_cu * hours_per_month * rate
        return CostEstimate(cost, cost, None, rate, is_placeholder, hours_per_month, True)
    if rec.min_cu is None or rec.max_cu is None:
        return CostEstimate(None, None, None, rate, is_placeholder, hours_per_month, False)
    low = rec.min_cu * hours_per_month * rate
    high = rec.max_cu * hours_per_month * rate
    stz = rec.min_cu * hours_per_month * active_fraction * rate
    return CostEstimate(low, high, stz, rate, is_placeholder, hours_per_month, False)
