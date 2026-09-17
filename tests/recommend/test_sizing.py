# tests/recommend/test_sizing.py
from db_metrics.recommend.skus import Capacity
from db_metrics.recommend.normalize import Signals
from db_metrics.recommend.sizing import recommend, SizingOpts, _snap_cu_up

CAP = Capacity(vcpu=4, ram_gb=16, source_label="Standard_D4ds_v5", known=True)


def _is_settable_cu(cu: float) -> bool:
    """Lakebase autoscaling CU: 0.5, then whole integers (1, 2, 3, ...)."""
    return cu == 0.5 or (cu >= 1 and float(cu).is_integer())


def test_ram_bound_band():
    # avg 50% of 16GB = 8GB -> 4 CU; peak 80% = 12.8GB -> 6.4 CU; +30% headroom
    sig = Signals(mem_pct_avg=50.0, mem_pct_peak=80.0, cpu_avg=20.0, cpu_peak=40.0)
    rec = recommend(CAP, sig)
    assert rec.dynamic is True
    assert rec.min_cu == 6.0   # ceil(4*1.3=5.2) -> 6 (0.5-then-integers)
    assert rec.max_cu == 9.0   # ceil(6.4*1.3=8.32) -> 9


def test_snap_cu_up_settable_values():
    assert _snap_cu_up(0.3) == 0.5
    assert _snap_cu_up(0.5) == 0.5
    assert _snap_cu_up(0.6) == 1.0   # nothing settable between 0.5 and 1
    assert _snap_cu_up(5.2) == 6.0
    assert _snap_cu_up(6.5) == 7.0   # the reported bug: 6.5 is not settable
    assert _snap_cu_up(8.0) == 8.0


def test_recommended_band_endpoints_are_settable():
    """Every emitted min/max CU must be a value the Lakebase API/UI accepts."""
    for sig in (
        Signals(mem_pct_avg=50.0, mem_pct_peak=80.0, cpu_avg=20.0, cpu_peak=40.0),
        Signals(mem_pct_avg=10.0, mem_pct_peak=15.0, cpu_avg=50.0, cpu_peak=90.0),
        Signals(mem_pct_avg=33.0, mem_pct_peak=41.0),
    ):
        rec = recommend(CAP, sig)
        assert _is_settable_cu(rec.min_cu), rec.min_cu
        assert _is_settable_cu(rec.max_cu), rec.max_cu

def test_cpu_bound_when_cpu_higher():
    # low mem, very high cpu: 90% of 4 vcpu = 3.6 CU peak drives it
    sig = Signals(mem_pct_avg=10.0, mem_pct_peak=15.0, cpu_avg=50.0, cpu_peak=90.0)
    rec = recommend(CAP, sig)
    assert rec.max_cu >= 4.5

def test_band_span_clamped_to_16():
    # avg: 2% of 48 GB = 0.96 GB -> 0.48 CU; peak: 100% of 48 GB = 48 GB -> 24 CU
    # +30% headroom: min=ceil(0.624)=1.0, max=ceil(31.2)=32.0 (clamped to dynamic ceiling)
    # 32.0 - 1.0 = 31.0 > 16.0 → min raised to 32.0 - 16.0 = 16.0
    cap = Capacity(vcpu=24, ram_gb=48, source_label="x", known=True)
    sig = Signals(mem_pct_avg=2.0, mem_pct_peak=100.0)
    rec = recommend(cap, sig)
    assert rec.dynamic is True
    assert rec.min_cu == 16.0
    assert rec.max_cu == 32.0
    assert rec.max_cu - rec.min_cu <= 16.0
    assert any("min raised to keep autoscaling band within 16.0 CU" in n for n in rec.notes)

def test_fixed_tier_escalation():
    big = Capacity(vcpu=96, ram_gb=384, source_label="huge", known=True)
    sig = Signals(mem_pct_avg=80.0, mem_pct_peak=95.0)  # >64 CU → fixed size
    rec = recommend(big, sig)
    # A huge peak escalates to a fixed size, capped at the max (112).
    assert rec.dynamic is False
    assert rec.fixed_cu == 112.0
    assert float(rec.fixed_cu).is_integer() and 65 <= rec.fixed_cu <= 112


def test_fixed_size_is_smallest_settable_integer_above_ceiling():
    """A peak just over the dynamic ceiling picks the smallest fixed integer (>=65)."""
    # 26 vCPU, 132 GB RAM, ~near-full peak → ~65-66 CU need before headroom lands >64.
    cap = Capacity(vcpu=64, ram_gb=130, source_label="x", known=True)
    sig = Signals(mem_pct_avg=50.0, mem_pct_peak=80.0)  # peak 104 GB -> 52 CU *1.3 = 67.6 -> 68
    rec = recommend(cap, sig)
    assert rec.dynamic is False
    assert rec.fixed_cu == 68.0  # ceil(67.6), within [65, 112]


def test_fixed_tier_note_reflects_default_dynamic_ceiling():
    big = Capacity(vcpu=96, ram_gb=384, source_label="huge", known=True)
    sig = Signals(mem_pct_avg=80.0, mem_pct_peak=95.0)  # >64 CU
    rec = recommend(big, sig)
    assert any("64 CU dynamic range" in n for n in rec.notes)


def test_fixed_tier_note_reflects_custom_dynamic_ceiling():
    """The advisory string must track opts.max_cu_dynamic, not a hardcoded 32."""
    big = Capacity(vcpu=96, ram_gb=384, source_label="huge", known=True)
    sig = Signals(mem_pct_avg=80.0, mem_pct_peak=95.0)  # >48 CU too
    rec = recommend(big, sig, SizingOpts(max_cu_dynamic=48.0))
    assert rec.dynamic is False
    assert any("48 CU dynamic range" in n for n in rec.notes)
    assert not any("32 CU dynamic range" in n for n in rec.notes)

def test_unknown_sku_insufficient_data():
    cap = Capacity(None, None, "Standard_ZZ99", False)
    rec = recommend(cap, Signals(mem_pct_avg=50.0, mem_pct_peak=70.0))
    assert rec.min_cu is None and any("insufficient" in n for n in rec.notes)

def test_headroom_override():
    sig = Signals(mem_pct_avg=50.0, mem_pct_peak=50.0)
    rec = recommend(CAP, sig, SizingOpts(headroom=0.0))
    assert rec.min_cu == 4.0 and rec.max_cu == 4.0


def test_iops_included_in_drivers():
    """recommend() must propagate iops_avg/iops_peak from Signals into drivers."""
    sig = Signals(mem_pct_avg=50.0, mem_pct_peak=80.0, iops_avg=1200.0, iops_peak=3500.0)
    rec = recommend(CAP, sig)
    assert rec.drivers["iops_avg"] == 1200.0
    assert rec.drivers["iops_peak"] == 3500.0
