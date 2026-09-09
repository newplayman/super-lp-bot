"""RH-02af: first-step fee-accrual must not treat the whole pool history as
this step's increment.  feeGrowthGlobal is a monotonic cumulative; with no
previous reading the increment is "unknown" (0 accrued), never the pool's
entire fees.  No network, no wallet, no broadcast.
"""
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from decimal import Decimal

from scripts.lp_rh_shadow_runner_v1_readonly import (
    FEE_GROWTH_SCALE,
    ShadowStep,
    episode_summary,
    run_episode,
)
from scripts.lp_rh_pnl_v1_readonly import hodl_benchmark
from scripts.lp_rh_store_v1_readonly import migrate, open_store

POSITION_USD = Decimal("1000")
CAPITAL_USD = Decimal("10000")
HORIZON_HOURS = 8760
NOW = "2026-01-01T00:00:00Z"
# Real measured magnitude of feeGrowthGlobal (~4.5e40, 41 digits).
X0 = 45000000000000000000000000000000000000000
X1 = 45000000000000000000000000000000000000001


def _passing_sample(idx, *, price=None, fee_growth=None, **overrides):
    """A synthetic sample that passes every RH layer (COMPUTED_PASS)."""
    s = {
        "candidate_key": f"pool-{idx}",
        "sample_time": f"2026-01-01T00:{idx:02d}:00Z",
        "chain_id": 4663,
        "attestation_status": "ATTESTED_SAME_BLOCK",
        "protocol": "v3",
        "fee_apr_pct": 100.0,
        "sigma_daily": 0.0,
        "liquidity_raw": 1e20,
        "sqrt_price_x96": 4_340_000_000_000_000_000_000_000_000_000_000,
        "fee": 500,
        "dec0": 18,
        "dec1": 6,
        "gas_usd_estimate": 0.01,
        "legacy_required_conjunction": True,
        "identity_verified": True,
        "protocol_capabilities_sufficient": True,
        "data_complete_and_fresh": True,
        "profile_policy_pass": True,
        "market_and_chain_risk_pass": True,
        "absolute_profit_pass": True,
        "position_and_exit_depth_pass": True,
        "capital_policy_pass": True,
    }
    if price is not None:
        s["reference_mid"] = price
    if fee_growth is not None:
        s["fee_growth_global_0"], s["fee_growth_global_1"] = fee_growth
    s.update(overrides)
    return s


def _run(conn, samples, *, episode="ep", target_mode="SHADOW_SCENARIO"):
    return run_episode(
        conn, strategy_episode=episode, samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode=target_mode, now_fn=lambda: NOW,
    )


def _fresh_store(tmp_path):
    conn = open_store(tmp_path / "s.db")
    migrate(conn)
    return conn


def test_first_step_accrued_zero_nav_equals_capital(tmp_path):
    """fg X -> X+Δ: first step accrues 0, NAV == capital (no 133089 blob)."""
    conn = _fresh_store(tmp_path)
    d0, d1 = 7, 3
    samples = [_passing_sample(0, fee_growth=(X0, X1)),
               _passing_sample(1, fee_growth=(X0 + d0, X1 + d1))]
    steps = _run(conn, samples)
    # First step accrues 0 => NAV is exactly wallet + lp_principal = capital,
    # not the buggy capital + position*(X0+X1)/2**128 (~1.4e5).
    assert steps[0].nav == CAPITAL_USD


def test_second_step_accrued_reflects_only_delta(tmp_path):
    """nav_2 - nav_1 == position * Δ_total / 2**128, exactly (Decimal)."""
    conn = _fresh_store(tmp_path)
    d0, d1 = 7, 3
    samples = [_passing_sample(0, fee_growth=(X0, X1)),
               _passing_sample(1, fee_growth=(X0 + d0, X1 + d1))]
    steps = _run(conn, samples)
    expected = POSITION_USD * (Decimal(d0) + Decimal(d1)) / FEE_GROWTH_SCALE
    assert abs((steps[1].nav - steps[0].nav) - expected) <= abs(expected) * Decimal("1e-25")


def test_first_step_nav_not_none(tmp_path):
    """accrued=0 is legal; the first step must still produce a NAV."""
    conn = _fresh_store(tmp_path)
    steps = _run(conn, [_passing_sample(0, fee_growth=(X0, X1))])
    assert steps[0].nav is not None
    assert steps[0].nav == CAPITAL_USD


def test_fg_zero_reading_treated_as_previous(tmp_path):
    """fg reading exactly 0 (fresh pool) is a real previous value, not 'none'."""
    conn = _fresh_store(tmp_path)
    d0, d1 = 5, 2
    samples = [_passing_sample(0, fee_growth=(0, 0)),
               _passing_sample(1, fee_growth=(d0, d1))]
    steps = _run(conn, samples)
    # Second step diffs from 0, so it accrues the full d0+d1.
    expected = POSITION_USD * (Decimal(d0) + Decimal(d1)) / FEE_GROWTH_SCALE
    assert abs((steps[1].nav - steps[0].nav) - expected) <= abs(expected) * Decimal("1e-25")
    assert steps[0].nav == CAPITAL_USD  # first step (fg=0) still accrues 0


def test_three_increasing_samples_accrued_monotonic(tmp_path):
    """Increasing fg over three samples -> NAV (hence accrued) non-decreasing."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, fee_growth=(X0, X1)),
               _passing_sample(1, fee_growth=(X0 + 10, X1 + 10)),
               _passing_sample(2, fee_growth=(X0 + 25, X1 + 25))]
    navs = [s.nav for s in _run(conn, samples)]
    assert all(n is not None for n in navs)
    assert navs[0] <= navs[1] <= navs[2]
    assert navs[1] - navs[0] > 0 and navs[2] - navs[1] > 0


def test_fg_none_midway_no_pollution(tmp_path):
    """A None fg step has no NAV and must not pollute prev_fg; the next valid
    sample diffs against the last valid previous reading."""
    conn = _fresh_store(tmp_path)
    d0 = 9
    samples = [_passing_sample(0, fee_growth=(X0, X1)),
               _passing_sample(1, fee_growth=None),
               _passing_sample(2, fee_growth=(X0 + d0, X1))]
    steps = _run(conn, samples)
    assert steps[0].nav is not None and steps[1].nav is None
    assert steps[2].nav is not None
    # Step 2 diffs against step 0 (last valid), not the None step.
    expected = POSITION_USD * Decimal(d0) / FEE_GROWTH_SCALE
    assert abs((steps[2].nav - steps[0].nav) - expected) <= abs(expected) * Decimal("1e-25")


def test_steps_without_nav_counts_only_none(tmp_path):
    """Regression: steps_without_nav counts exactly the nav-is-None steps."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, fee_growth=(X0, X1)),
               _passing_sample(1, fee_growth=None),
               _passing_sample(2, fee_growth=None),
               _passing_sample(3, fee_growth=(X0 + 4, X1 + 4))]
    steps = _run(conn, samples)
    summary = episode_summary(steps)
    assert summary["steps_without_nav"] == 2
    assert summary["nav_start"] == steps[0].nav
    assert summary["nav_end"] == steps[3].nav


def test_net_pnl_is_nav_end_minus_nav_start(tmp_path):
    """Regression: net_pnl is still nav_end - nav_start (external flow 0)."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, fee_growth=(X0, X1)),
               _passing_sample(1, fee_growth=(X0 + 6, X1 + 6))]
    summary = episode_summary(_run(conn, samples))
    assert summary["net_pnl"] == summary["nav_end"] - summary["nav_start"]
    expected = POSITION_USD * Decimal(12) / FEE_GROWTH_SCALE
    assert abs(summary["net_pnl"] - expected) <= abs(expected) * Decimal("1e-25")


def test_hodl_delta_unaffected(tmp_path):
    """Regression: hodl_delta is still hodls[-1] - hodls[0], independent of fg."""
    conn = _fresh_store(tmp_path)
    p0, p1 = Decimal("2"), Decimal("3")

    def _h(px):
        return hodl_benchmark(initial_token0_raw=Decimal("1000000000000000000"),
                              initial_token1_raw=Decimal("1000000"), dec0=18,
                              dec1=6, price_t1_token1_per_token0=px,
                              quote_usd_per_token1=Decimal("1"))
    samples = [_passing_sample(0, price=p0, fee_growth=(X0, X1)),
               _passing_sample(1, price=p1, fee_growth=(X0 + 6, X1 + 6))]
    steps = _run(conn, samples)
    h0, h1 = _h(p0), _h(p1)
    assert episode_summary(steps)["hodl_delta"] == h1 - h0
    assert steps[0].hodl_value == h0 and steps[1].hodl_value == h1


def test_large_number_precision_delta_one(tmp_path):
    """Δ_total=1: increment equals 1000/2**128 within 1e-25 relative.  Do NOT
    assert (nav_2-nav_1)*2**128 == 1000: 1000/2**128 is not exactly
    representable at 28-digit precision, so that equality has no solution."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, fee_growth=(X0, X1)),
               _passing_sample(1, fee_growth=(X0 + 1, X1))]
    steps = _run(conn, samples)
    a = steps[1].nav - steps[0].nav
    b = Decimal(1000) / FEE_GROWTH_SCALE
    assert abs(a - b) <= abs(b) * Decimal("1e-25")


def test_fg_decreasing_no_exception_nav_available(tmp_path):
    """fg decreasing (should not happen) must not raise; NAV stays available.
    Observed: the negative difference accrues as-is, so NAV drops below
    capital.  We pin only "no exception and NAV is a Decimal"; source unchanged."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, fee_growth=(X0, X1)),
               _passing_sample(1, fee_growth=(X0 - 5, X1))]
    steps = _run(conn, samples)  # must not raise
    assert steps[1].nav is not None and isinstance(steps[1].nav, Decimal)
    assert steps[1].nav < CAPITAL_USD  # documented: negative increment


def test_end_to_end_nav_start_magnitude(tmp_path):
    """run_episode over 3 fg samples: nav_start is capital-scale, not ~143047."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, fee_growth=(X0, X1)),
               _passing_sample(1, fee_growth=(X0 + 100, X1 + 100)),
               _passing_sample(2, fee_growth=(X0 + 200, X1 + 200))]
    steps = _run(conn, samples)
    nav_start = episode_summary(steps)["nav_start"]
    assert nav_start is not None
    assert abs(nav_start - CAPITAL_USD) <= POSITION_USD  # not the ~143047 blob
    assert all(isinstance(s, ShadowStep) for s in steps)
