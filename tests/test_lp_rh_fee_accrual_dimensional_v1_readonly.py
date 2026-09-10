"""RH-02ai: dimensional fee-accrual regression lock.

The old formula `position_usd * (d0 + d1) / 2**128` treated feeGrowthGlobal
as a USD-per-USD quantity and added two different tokens' raw integers
(18-dec + 6-dec), overstating fees by ~1022x.  The correct formula multiplies
the position's raw liquidity L_pos by the feeGrowth increment, scales each leg
to human units by its own decimals, then to USD by its own price.  No network,
no wallet, no broadcast.
"""
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from decimal import Decimal

# RH-02bd: The previous relaxing of NAV_DIFF_REL_TOL from 1e-20 to 1e-12 was based
# on a misdiagnosis ("Decimal 28-digit precision unreachable").
# The true root cause of the ~1.11e-15 error was using float-based position_liquidity_raw
# in the test oracle while the runner uses Decimal-based inventory_for_position.
# When the test oracle uses inventory_for_position directly (matching Decimal arithmetic),
# the relative difference is ~1.83e-22, making the original 1e-20 tolerance fully reachable.
NAV_DIFF_REL_TOL = Decimal("1e-20")

from scripts.lp_rh_shadow_runner_v1_readonly import (
    FEE_GROWTH_SCALE,
    run_episode,
)
from scripts.lp_rh_v3_inventory_v1_readonly import inventory_for_position
from scripts.lp_rh_store_v1_readonly import migrate, open_store

POSITION_USD = Decimal("1000")
CAPITAL_USD = Decimal("10000")
HORIZON_HOURS = 8760
NOW = "2026-01-01T00:00:00Z"

# Real measured feeGrowth increments over a 2985s window (on-chain data).
DFG0 = 9365277615024075401537929281665916457
DFG1 = 21451527583324632536589703137

# Real pool_meta values (reports/lp_rh/pool_meta.json).
POOL_META = {
    "input_price_usd": 2484.0,
    "range_pct": 10.0,
    "dec0": 18,
    "dec1": 6,
    "quote_usd_per_token1": 1.0,
    "attestation_status": "ATTESTED_SAME_BLOCK",
    "protocol": "v3",
}

# A large base feeGrowth value (41 digits, matching real magnitude).
X0 = 45000000000000000000000000000000000000000
X1 = X0 + 1

PRICE = Decimal("2484")


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
        "sqrt_price_x96": 4_340_000_000_000_000_000_000_000_000_000_000_000,
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
         pool_meta=None, allow_bare_quote=True):
    return run_episode(
        conn, strategy_episode=episode, samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode=target_mode, now_fn=lambda: NOW,
        pool_meta=pool_meta, allow_bare_quote=allow_bare_quote,
    )


def _fresh_store(tmp_path):
    conn = open_store(tmp_path / "s.db")
    migrate(conn)
    return conn


def _expected_fee(d0, d1, price, *, pool_meta=None, position_usd=None):
    """Hand-computed dimensional fee for a single increment, independent of
    the runner's code path (the regression-lock oracle).

    Uses Decimal-based inventory_for_position to obtain l_pos."""
    pm = pool_meta if pool_meta is not None else POOL_META
    pos = position_usd if position_usd is not None else POSITION_USD
    inv = inventory_for_position(
        position_usd=Decimal(str(pos)),
        entry_price=Decimal(str(pm.get("input_price_usd", price))),
        range_pct=Decimal(str(pm["range_pct"])),
        dec0=int(pm["dec0"]),
        dec1=int(pm["dec1"]),
        quote_usd_per_token1=Decimal(str(pm.get("quote_usd_per_token1", 1))),
    )
    l_pos = inv.liquidity_raw
    tok0 = l_pos * Decimal(d0) / FEE_GROWTH_SCALE / (Decimal(10) ** pm["dec0"])
    tok1 = l_pos * Decimal(d1) / FEE_GROWTH_SCALE / (Decimal(10) ** pm["dec1"])
    return (tok0 * price + tok1) * Decimal("1")


def test_accrued_equals_hand_computed_formula(tmp_path):
    """(a) Given a feeGrowth increment between two steps, accrued equals the
    hand-computed dimensional formula value."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, price=PRICE, fee_growth=(X0 + DFG0, X1 + DFG1))]
    steps = _run(conn, samples, pool_meta=POOL_META)
    expected_fee = _expected_fee(DFG0, DFG1, PRICE)
    # nav = capital + accrued; accrued after step 1 is the single increment.
    assert abs((steps[1].nav - CAPITAL_USD) - expected_fee) \
        <= abs(expected_fee) * NAV_DIFF_REL_TOL
    conn.close()


def test_first_step_accrued_zero(tmp_path):
    """(b) First step accrued is still 0 (RH-02af semantics, no regression)."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, price=PRICE, fee_growth=(X0 + DFG0, X1 + DFG1))]
    steps = _run(conn, samples, pool_meta=POOL_META)
    assert steps[0].nav == CAPITAL_USD  # accrued = 0 on first step
    conn.close()


def test_pool_meta_missing_range_pct_nav_none(tmp_path):
    """(c) pool_meta missing range_pct -> no step gets a nav (fail-close).

    This assertion changed with RH-02al.  Under RH-02ai the NAV was
    wallet + a constant position_usd + accrued, so the opening step -- where
    accrued is 0 by definition -- still produced nav == capital_usd without
    needing any pool geometry.  RH-02al marks the position to market, so NAV
    now needs the range to value the legs at all, and a pool_meta without
    range_pct yields no NAV on any step, opening one included.  Failing
    closed on every step is the stronger behaviour: the old one reported a
    number for a position it could not value."""
    conn = _fresh_store(tmp_path)
    bad_meta = {k: v for k, v in POOL_META.items() if k != "range_pct"}
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, price=PRICE, fee_growth=(X0 + DFG0, X1 + DFG1))]
    steps = _run(conn, samples, pool_meta=bad_meta)
    assert steps[0].nav is None
    assert steps[1].nav is None
    assert all(s.hodl_value is None for s in steps)
    conn.close()


def test_fg_none_midway_prev_not_reset(tmp_path):
    """(d) A mid-way sample with fg=None then recovery: prev_fg is NOT reset;
    the post-recovery increment spans the gap (regression lock)."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, price=PRICE, fee_growth=None),  # gap
               _passing_sample(2, price=PRICE, fee_growth=(X0 + DFG0, X1 + DFG1))]
    steps = _run(conn, samples, pool_meta=POOL_META)
    assert steps[0].nav == CAPITAL_USD  # first step: accrued = 0
    assert steps[1].nav is None         # gap step: fg is None -> no nav
    # Step 2: increment spans from step 0 (prev_fg not reset by the None step).
    expected_fee = _expected_fee(DFG0, DFG1, PRICE)
    assert abs((steps[2].nav - CAPITAL_USD) - expected_fee) \
        <= abs(expected_fee) * NAV_DIFF_REL_TOL
    conn.close()


def test_price_none_nav_none(tmp_path):
    """Fail-close: a fee-increment step with price=None -> nav is None."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, fee_growth=(X0 + DFG0, X1 + DFG1))]  # no price
    steps = _run(conn, samples, pool_meta=POOL_META)
    assert steps[0].nav == CAPITAL_USD
    assert steps[1].nav is None  # price is None -> fail-close
    conn.close()


def test_dimensional_regression_lock_ratio_gt_100(tmp_path):
    """Dimensional regression lock: old-formula / new-formula > 100 under the
    same inputs.  The old formula overstated fees by ~1022x."""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, price=PRICE, fee_growth=(X0, X1)),
               _passing_sample(1, price=PRICE, fee_growth=(X0 + DFG0, X1 + DFG1))]
    steps = _run(conn, samples, pool_meta=POOL_META)
    new_fee = steps[1].nav - CAPITAL_USD
    old_fee = POSITION_USD * (Decimal(DFG0) + Decimal(DFG1)) / FEE_GROWTH_SCALE
    ratio = old_fee / new_fee
    assert ratio > 100
    conn.close()
