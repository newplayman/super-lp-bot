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
from scripts.lp_v3_fee_share import position_liquidity_raw

POSITION_USD = Decimal("1000")
CAPITAL_USD = Decimal("10000")
HORIZON_HOURS = 8760
NOW = "2026-01-01T00:00:00Z"
# Real measured magnitude of feeGrowthGlobal (~4.5e40, 41 digits).
X0 = 45000000000000000000000000000000000000000
X1 = 45000000000000000000000000000000000000001
# RH-02ai: real-magnitude feeGrowth increments (measured on-chain over a 2985s
# window) plus the pool_meta / price the dimensional fee formula needs.  Tiny
# increments (d0=7, d1=3) are absorbed at 28-digit precision, so they must be
# replaced with these measured values for the fee to be visible in NAV.
DFG0 = 9365277615024075401537929281665916457
DFG1 = 21451527583324632536589703137
PRICE = Decimal("2484")
POOL_META = {
    "input_price_usd": 2484.0,
    "range_pct": 10.0,
    "dec0": 18,
    "dec1": 6,
    "attestation_status": "ATTESTED_SAME_BLOCK",
    "protocol": "v3",
}


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


def _run(conn, samples, *, episode="ep", target_mode="SHADOW_SCENARIO",
         pool_meta=None):
    return run_episode(
        conn, strategy_episode=episode, samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode=target_mode, now_fn=lambda: NOW,
        pool_meta=pool_meta,
    )


def _fresh_store(tmp_path):
    conn = open_store(tmp_path / "s.db")
    migrate(conn)
    return conn


def _expected_fee(d0, d1, price, *, pool_meta=None, position_usd=None):
    """Hand-computed dimensional fee for a single increment (the oracle).

    RH-02ai: multiply the position's raw liquidity L_pos by the feeGrowth
    increment, scale each leg to human units by its own decimals, then to USD
    by its own price.  Independent of the runner's code path."""
    pm = pool_meta if pool_meta is not None else POOL_META
    pos = position_usd if position_usd is not None else POSITION_USD
    l_pos = Decimal(str(position_liquidity_raw(
        float(pos), pm["input_price_usd"], pm["range_pct"],
        pm["dec0"], pm["dec1"])))
    tok0 = l_pos * Decimal(d0) / FEE_GROWTH_SCALE / (Decimal(10) ** pm["dec0"])
    tok1 = l_pos * Decimal(d1) / FEE_GROWTH_SCALE / (Decimal(10) ** pm["dec1"])
    return (tok0 * price + tok1) * Decimal("1")


def test_first_step_accrued_zero_nav_equals_capital(tmp_path):
    """fg X -> X+Δ: first step accrues 0, NAV == capital (no 133089 blob)."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, price=PRICE, fee_growth=(X0 + DFG0, X1 + DFG1))]
    steps = _run(conn, samples, pool_meta=POOL_META)
    # First step accrues 0 => NAV is exactly wallet + lp_principal = capital,
    # not the buggy capital + position*(X0+X1)/2**128 (~1.4e5).
    assert steps[0].nav == CAPITAL_USD


def test_second_step_accrued_reflects_only_delta(tmp_path):
    """nav_2 - nav_1 == the dimensional fee for the single increment
    (L_pos * Δfg / 2**128 / 10**dec * price), not the old
    position_usd * Δ_total / 2**128 (RH-02ai)."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, price=PRICE, fee_growth=(X0 + DFG0, X1 + DFG1))]
    steps = _run(conn, samples, pool_meta=POOL_META)
    expected = _expected_fee(DFG0, DFG1, PRICE)
    assert abs((steps[1].nav - steps[0].nav) - expected) \
        <= abs(expected) * Decimal("1e-20")


def test_first_step_nav_not_none(tmp_path):
    """accrued=0 is legal; the first step must still produce a NAV."""
    conn = _fresh_store(tmp_path)
    steps = _run(conn, [_passing_sample(0, fee_growth=(X0, X1))])
    assert steps[0].nav is not None
    assert steps[0].nav == CAPITAL_USD


def test_fg_zero_reading_treated_as_previous(tmp_path):
    """fg reading exactly 0 (fresh pool) is a real previous value, not 'none'."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(0, 0)),
               _passing_sample(1, price=PRICE, fee_growth=(DFG0, DFG1))]
    steps = _run(conn, samples, pool_meta=POOL_META)
    # Second step diffs from 0, so it accrues the full dimensional fee.
    expected = _expected_fee(DFG0, DFG1, PRICE)
    assert abs((steps[1].nav - steps[0].nav) - expected) \
        <= abs(expected) * Decimal("1e-20")
    assert steps[0].nav == CAPITAL_USD  # first step (fg=0) still accrues 0


def test_three_increasing_samples_accrued_monotonic(tmp_path):
    """Increasing fg over three samples -> NAV (hence accrued) non-decreasing."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, price=PRICE, fee_growth=(X0 + DFG0, X1 + DFG1)),
               _passing_sample(2, price=PRICE, fee_growth=(X0 + 3*DFG0, X1 + 3*DFG1))]
    navs = [s.nav for s in _run(conn, samples, pool_meta=POOL_META)]
    assert all(n is not None for n in navs)
    assert navs[0] <= navs[1] <= navs[2]
    assert navs[1] - navs[0] > 0 and navs[2] - navs[1] > 0


def test_fg_none_midway_no_pollution(tmp_path):
    """A None fg step has no NAV and must not pollute prev_fg; the next valid
    sample diffs against the last valid previous reading."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, fee_growth=None),
               _passing_sample(2, price=PRICE, fee_growth=(X0 + DFG0, X1))]
    steps = _run(conn, samples, pool_meta=POOL_META)
    assert steps[0].nav is not None and steps[1].nav is None
    assert steps[2].nav is not None
    # Step 2 diffs against step 0 (last valid), not the None step.
    expected = _expected_fee(DFG0, 0, PRICE)
    assert abs((steps[2].nav - steps[0].nav) - expected) \
        <= abs(expected) * Decimal("1e-20")


def test_steps_without_nav_counts_only_none(tmp_path):
    """Regression: steps_without_nav counts exactly the nav-is-None steps."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, fee_growth=None),
               _passing_sample(2, fee_growth=None),
               _passing_sample(3, price=PRICE, fee_growth=(X0 + DFG0, X1 + DFG1))]
    steps = _run(conn, samples, pool_meta=POOL_META)
    summary = episode_summary(steps)
    assert summary["steps_without_nav"] == 2
    assert summary["nav_start"] == steps[0].nav
    assert summary["nav_end"] == steps[3].nav


def test_net_pnl_is_nav_end_minus_nav_start(tmp_path):
    """Regression: net_pnl is still nav_end - nav_start (external flow 0)."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, price=PRICE, fee_growth=(X0 + DFG0, X1 + DFG1))]
    summary = episode_summary(_run(conn, samples, pool_meta=POOL_META))
    assert summary["net_pnl"] == summary["nav_end"] - summary["nav_start"]
    expected = _expected_fee(DFG0, DFG1, PRICE)
    assert abs(summary["net_pnl"] - expected) \
        <= abs(expected) * Decimal("1e-20")


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
               _passing_sample(1, price=p1, fee_growth=(X0 + DFG0, X1 + DFG1))]
    steps = _run(conn, samples, pool_meta=POOL_META)
    h0, h1 = _h(p0), _h(p1)
    assert episode_summary(steps)["hodl_delta"] == h1 - h0
    assert steps[0].hodl_value == h0 and steps[1].hodl_value == h1


def test_large_number_precision_delta_one(tmp_path):
    """RH-02ai rewrite: the old property 'Δ_total=1 -> increment equals
    1000/2**128' was an old-formula property (position_usd * Δ / 2**128).
    Under the new dimensional formula the equivalent property is: a large
    41-digit base feeGrowth plus a real-magnitude single-leg (token0)
    increment yields the hand-computed dimensional fee for that leg, i.e. the
    large base does not corrupt the delta at 28-digit precision.  A delta of 1
    is no longer visible (L_pos*1/2**128/10**18 ~ 6e-42, below precision
    relative to capital), so the real-magnitude DFG0 is used instead."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, price=PRICE, fee_growth=(X0 + DFG0, X1))]
    steps = _run(conn, samples, pool_meta=POOL_META)
    a = steps[1].nav - steps[0].nav
    b = _expected_fee(DFG0, 0, PRICE)
    assert abs(a - b) <= abs(b) * Decimal("1e-20")


def test_fg_decreasing_no_exception_nav_available(tmp_path):
    """fg decreasing (should not happen) must not raise; NAV stays available.
    Observed: the negative difference accrues as-is, so NAV drops below
    capital.  We pin only "no exception and NAV is a Decimal"; source unchanged."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, price=PRICE, fee_growth=(X0 - DFG0, X1))]
    steps = _run(conn, samples, pool_meta=POOL_META)  # must not raise
    assert steps[1].nav is not None and isinstance(steps[1].nav, Decimal)
    assert steps[1].nav < CAPITAL_USD  # documented: negative increment


def test_end_to_end_nav_start_magnitude(tmp_path):
    """run_episode over 3 fg samples: nav_start is capital-scale, not ~143047."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, price=PRICE, fee_growth=(X0 + DFG0, X1 + DFG1)),
               _passing_sample(2, price=PRICE,
                               fee_growth=(X0 + 2*DFG0, X1 + 2*DFG1))]
    steps = _run(conn, samples, pool_meta=POOL_META)
    nav_start = episode_summary(steps)["nav_start"]
    assert nav_start is not None
    assert abs(nav_start - CAPITAL_USD) <= POSITION_USD  # not the ~143047 blob
    assert all(isinstance(s, ShadowStep) for s in steps)
