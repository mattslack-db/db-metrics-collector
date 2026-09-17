from db_metrics.recommend.sizing import Recommendation
from db_metrics.recommend.cost import estimate, rate_for, PLACEHOLDER_RATE

def _rec(mn, mx, fixed=None, dynamic=True):
    return Recommendation(mn, mx, dynamic, fixed, (), {})

def test_rate_precedence():
    assert rate_for("azure", 0.5) == (0.5, False)
    r, ph = rate_for("azure", None)
    assert isinstance(r, float)

def test_rate_placeholder_flagged_for_unknown_cloud():
    r, ph = rate_for("gcp", None)
    assert r == PLACEHOLDER_RATE and ph is True

def test_dynamic_cost_range():
    est = estimate(_rec(4.0, 8.0), rate=0.5, is_placeholder=False, hours_per_month=730)
    assert est.low == 4.0 * 730 * 0.5
    assert est.high == 8.0 * 730 * 0.5
    assert est.scale_to_zero_low < est.low

def test_fixed_cost():
    est = estimate(_rec(None, None, fixed=36.0, dynamic=False), rate=0.5, is_placeholder=True)
    assert est.low == est.high == 36.0 * 730 * 0.5
    assert est.scale_to_zero_low is None and est.is_placeholder is True

def test_insufficient_data_no_cost():
    est = estimate(_rec(None, None), rate=0.5, is_placeholder=False)
    assert est.low is None and est.high is None
