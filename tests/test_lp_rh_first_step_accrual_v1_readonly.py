"""RH-02af: first-step fee-accrual must not treat the whole pool history as
this step's increment.  feeGrowthGlobal is a monotonic cumulative; with no
previous reading the increment is "unknown" (0 accrued), never the pool's
entire fees.  No network, no wallet, no broadcast.
"""
import json
import sqlite3
import sys
from datetime import datetime
from decimal import Decimal

# RH-02bd: The previous relaxing of NAV_DIFF_REL_TOL from 1e-20 to 1e-12 was based
# on a misdiagnosis ("Decimal 28-digit precision unreachable").
# The true root cause of the ~1.11e-15 error was using float-based position_liquidity_raw
# in the test oracle while the runner uses Decimal-based inventory_for_position.
# When the test oracle uses inventory_for_position directly (matching Decimal arithmetic),
# the relative difference is ~1.83e-22, making the original 1e-20 tolerance fully reachable.
NAV_DIFF_REL_TOL = Decimal("1e-20")

# At the default 28-digit Decimal context the smallest representable relative
# error is around 1e-28, so a 1e-40 tolerance cannot be met by any arithmetic
# -- it asserts nothing achievable.  Measured open-step error is ~6e-29.
OPEN_STEP_REL_TOL = Decimal("1e-25")
from pathlib import Path

sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from scripts.lp_rh_shadow_runner_v1_readonly import (
    DEFAULT_POOL,
    FEE_GROWTH_SCALE,
    ShadowStep,
    episode_summary,
    load_samples_from_db,
    run_episode,
)
from scripts.lp_rh_pnl_v1_readonly import hodl_benchmark
from scripts.lp_rh_store_v1_readonly import migrate, open_store
from scripts.lp_rh_v3_inventory_v1_readonly import (
    inventory_for_position,
    position_value_at,
)
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
    "quote_usd_per_token1": 1.0,
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
         pool_meta=None, allow_bare_quote=True):
    return run_episode(
        conn, strategy_episode=episode, samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode=target_mode, now_fn=lambda: NOW,
        pool_meta=pool_meta, allow_bare_quote=allow_bare_quote,
    )


def _fresh_store(tmp_path, name="s.db"):
    """A store per episode.  run_episode reserves inside a transaction, so
    two episodes on one connection collide with "cannot start a transaction
    within a transaction"; callers that run several scenarios pass distinct
    names."""
    conn = open_store(tmp_path / name)
    migrate(conn)
    return conn


def _expected_fee(d0, d1, price, *, pool_meta=None, position_usd=None):
    """Hand-computed dimensional fee for a single increment (the oracle).

    RH-02ai / RH-02bd: multiply the position's raw liquidity L_pos by the feeGrowth
    increment, scale each leg to human units by its own decimals, then to USD
    by its own price. Independent of the runner's code path.
    Uses Decimal inventory_for_position to avoid float precision loss."""
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
        <= abs(expected) * NAV_DIFF_REL_TOL


def test_first_step_nav_not_none(tmp_path):
    """accrued=0 is legal; the first step must still produce a NAV."""
    conn = _fresh_store(tmp_path)
    steps = _run(conn, [_passing_sample(0, price=PRICE, fee_growth=(X0, X1))],
                 pool_meta=POOL_META)
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
        <= abs(expected) * NAV_DIFF_REL_TOL
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
        <= abs(expected) * NAV_DIFF_REL_TOL


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
        <= abs(expected) * NAV_DIFF_REL_TOL


def test_hodl_delta_unaffected(tmp_path):
    """Regression: hodl_delta is still hodls[-1] - hodls[0], independent of fg."""
    conn = _fresh_store(tmp_path)
    p0, p1 = Decimal("2"), Decimal("3")
    inv = inventory_for_position(
        position_usd=POSITION_USD, entry_price=p0, range_pct=Decimal("10.0"),
        dec0=18, dec1=6, quote_usd_per_token1=Decimal("1"))

    def _h(px):
        return inv.amount0_human * px + inv.amount1_human
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
    assert abs(a - b) <= abs(b) * NAV_DIFF_REL_TOL


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


def test_rh02al_open_step_self_consistent(tmp_path):
    """Criterion 1: Open step self-consistency:
    lp_value == position_usd (relative error < OPEN_STEP_REL_TOL),
    hodl == position_usd exact,
    nav == capital_usd exact."""
    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, price=PRICE, fee_growth=(X0, X1))
    steps = _run(conn, [sample], pool_meta=POOL_META)
    assert len(steps) == 1
    step = steps[0]
    mark = conn.execute(
        "SELECT reference_nav, accrued_fee FROM rh_position_marks WHERE position_id = 'rh-shadow-ep'"
    ).fetchone()
    # Compare numerically: NAV now flows through the position mark, so it
    # carries trailing zeros ("10000.00000000000000000000000") that str()
    # of a plain Decimal("10000") does not.  Same number, different text.
    assert Decimal(mark[0]) == CAPITAL_USD
    assert mark[1] == "0"
    # hodl == position_usd exact
    assert step.hodl_value is not None
    rel_err_hodl = abs(step.hodl_value - POSITION_USD) / POSITION_USD
    assert rel_err_hodl < OPEN_STEP_REL_TOL
    assert step.hodl_value == POSITION_USD
    # nav == capital_usd exact
    assert step.nav is not None
    assert step.nav == CAPITAL_USD
    # lp_value at open: verify directly via position_value_at
    inv = inventory_for_position(
        position_usd=POSITION_USD, entry_price=PRICE,
        range_pct=Decimal(str(POOL_META["range_pct"])),
        dec0=POOL_META["dec0"], dec1=POOL_META["dec1"],
        quote_usd_per_token1=Decimal("1"),
    )
    scale = (Decimal(10) ** POOL_META["dec0"] * Decimal(10) ** POOL_META["dec1"]).sqrt()
    lp_val = position_value_at(
        price=PRICE, liquidity_human=inv.liquidity_raw / scale,
        entry_price=PRICE, range_pct=Decimal(str(POOL_META["range_pct"])),
        quote_usd_per_token1=Decimal("1"),
    )
    rel_err_lp = abs(lp_val.value_usd - POSITION_USD) / POSITION_USD
    assert rel_err_lp < OPEN_STEP_REL_TOL


def test_rh02al_net_pnl_can_be_negative(tmp_path):
    """Criterion 2: net_pnl can be negative when price falls."""
    conn = _fresh_store(tmp_path)
    price_open = Decimal("2484")
    price_drop = Decimal("2300")
    samples = [
        _passing_sample(0, price=price_open, fee_growth=(X0, X1)),
        _passing_sample(1, price=price_drop, fee_growth=(X0 + 10, X1 + 10)),
    ]
    steps = _run(conn, samples, pool_meta=POOL_META)
    summary = episode_summary(steps)
    assert summary["net_pnl"] is not None
    assert summary["net_pnl"] < Decimal("0"), f"Expected net_pnl < 0, got {summary['net_pnl']}"


def test_rh02al_window_alignment_equal_timestamps(tmp_path):
    """Criterion 3: Window alignment when an intermediate step has price but fee_growth is None."""
    conn = _fresh_store(tmp_path)
    samples = [
        _passing_sample(0, sample_time="2026-01-01T00:00:00Z", price=PRICE, fee_growth=(X0, X1)),
        _passing_sample(1, sample_time="2026-01-01T00:01:00Z", price=PRICE, fee_growth=None),
        _passing_sample(2, sample_time="2026-01-01T00:02:00Z", price=PRICE, fee_growth=(X0 + DFG0, X1 + DFG1)),
    ]
    steps = _run(conn, samples, pool_meta=POOL_META)
    summary = episode_summary(steps)
    assert summary["window_start_time"] == "2026-01-01T00:00:00Z"
    assert summary["window_end_time"] == "2026-01-01T00:02:00Z"
    assert summary["net_pnl"] == steps[2].nav - steps[0].nav
    assert summary["hodl_delta"] == steps[2].hodl_value - steps[0].hodl_value


def test_rh02al_fail_closed_missing_inputs(tmp_path):
    """Criterion: Fail-closed behavior on missing range_pct, open price, or invalid quote."""
    # Each scenario needs its own store: run_episode reserves inside a
    # transaction, and reusing one connection across three episodes hits
    # "cannot start a transaction within a transaction" on the second.
    meta_no_range = dict(POOL_META)
    del meta_no_range["range_pct"]
    conn1 = _fresh_store(tmp_path, "no_range.db")
    steps1 = _run(conn1, [_passing_sample(0, price=PRICE, fee_growth=(X0, X1))], pool_meta=meta_no_range)
    assert steps1[0].nav is None and steps1[0].hodl_value is None
    conn1.close()

    conn2 = _fresh_store(tmp_path, "no_price.db")
    steps2 = _run(conn2, [_passing_sample(0, price=None, fee_growth=(X0, X1))], pool_meta=POOL_META)
    assert steps2[0].nav is None and steps2[0].hodl_value is None
    conn2.close()

    conn3 = _fresh_store(tmp_path, "bad_quote.db")
    s_bad_quote = _passing_sample(0, price=PRICE, fee_growth=(X0, X1), quote_usd_per_token1=Decimal("0"))
    steps3 = _run(conn3, [s_bad_quote], pool_meta=POOL_META)
    assert steps3[0].nav is None and steps3[0].hodl_value is None
    conn3.close()

    # RH-02bd: Missing quote (not in pool_meta and not in sample) -> fails closed (no silent 1.0 default)
    meta_no_quote = dict(POOL_META)
    del meta_no_quote["quote_usd_per_token1"]
    conn4 = _fresh_store(tmp_path, "no_quote.db")
    steps4 = _run(conn4, [_passing_sample(0, price=PRICE, fee_growth=(X0, X1))], pool_meta=meta_no_quote)
    assert steps4[0].nav is None and steps4[0].hodl_value is None
    conn4.close()

    # RH-02bd: Missing dec0 / dec1 -> fails closed (no silent 18/6 default).
    # The lookup falls back pool_meta -> sample, and _passing_sample carries
    # dec0/dec1 of its own, so removing it from pool_meta alone still resolves
    # and the case never reaches the fail-close branch.  Both sources have to
    # be empty for this to test what it claims to.
    meta_no_dec = dict(POOL_META)
    del meta_no_dec["dec0"]
    sample_no_dec = dict(_passing_sample(0, price=PRICE, fee_growth=(X0, X1)))
    sample_no_dec.pop("dec0", None)
    conn5 = _fresh_store(tmp_path, "no_dec0.db")
    steps5 = _run(conn5, [sample_no_dec], pool_meta=meta_no_dec)
    assert steps5[0].nav is None and steps5[0].hodl_value is None
    conn5.close()



def test_rh02al_real_pool_meta_and_db_sanity(tmp_path):
    """Criterion 4: Real database sanity check with actual pool_meta.json fixture.

    RH-02bd: Under fail-close rules, if the production pool_meta.json has not yet been
    backfilled with quote_usd_per_token1 and samples do not carry it, open_valid is False
    and nav is None (no silent 1.0 fallback). When quote_usd_per_token1 is present,
    it computes properly."""
    real_meta_path = Path("/opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh/pool_meta.json")
    real_db_path = Path("/opt/lpbot/lp-bot-v3-origin-check/reports/lp_rh/scanner.db")
    if not real_meta_path.exists() or not real_db_path.exists():
        return
    with open(real_meta_path, "r", encoding="utf-8") as fh:
        real_meta = json.load(fh)

    src = sqlite3.connect(f"file:{real_db_path}?mode=ro", uri=True)
    try:
        samples, _ = load_samples_from_db(src, pool=DEFAULT_POOL, limit=200)
    finally:
        src.close()

    if len(samples) < 2:
        return

    # Case A: Real pool_meta without quote_usd_per_token1 -> fail-closed (nav is None)
    conn_raw = _fresh_store(tmp_path, "real_raw.db")
    steps_raw = run_episode(
        conn_raw, strategy_episode="sanity_raw", samples=samples,
        position_usd=POSITION_USD, horizon_hours=720.0, capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO", now_fn=lambda: NOW, pool_meta=real_meta,
    )
    # Since reports/lp_rh/pool_meta.json currently lacks quote_usd_per_token1, open_valid fails closed:
    if "quote_usd_per_token1" not in real_meta and not any("quote_usd_per_token1" in s for s in samples):
        assert all(s.nav is None for s in steps_raw)
    conn_raw.close()

    # Case B: When quote_usd_per_token1 is provided (as will be once production config is updated)
    meta_with_quote = dict(real_meta)
    meta_with_quote["quote_usd_per_token1"] = 1.0
    conn = _fresh_store(tmp_path, "real_quote.db")
    steps = run_episode(
        conn, strategy_episode="sanity", samples=samples,
        position_usd=POSITION_USD, horizon_hours=720.0, capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO", now_fn=lambda: NOW, pool_meta=meta_with_quote,
        allow_bare_quote=True,
    )
    s = episode_summary(steps)
    assert s["nav_start"] == CAPITAL_USD

    # Do NOT annualise net_pnl. Since RH-02al it carries the position's mark
    # to market, so annualising it extrapolates one price move over a year:
    # a 1% move across a 50-minute window reads as several thousand percent.
    # That is arithmetic, not a defect. The quantity that is meaningful
    # annualised is the fee accrual alone, which is what this pins.
    if steps and s["window_start_time"] and s["window_end_time"]:
        t0 = datetime.fromisoformat(s["window_start_time"].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(s["window_end_time"].replace("Z", "+00:00"))
        duration_secs = (t1 - t0).total_seconds()
        accrued = [x.accrued_fee for x in steps if getattr(x, "accrued_fee", None) is not None]
        if duration_secs > 0 and accrued:
            fee_apr = (
                float(accrued[-1]) / float(POSITION_USD)
                * (365 * 24 * 3600 / duration_secs) * 100.0
            )
            # The scanner's independent fee_apr_pct estimate for this pool is
            # ~27%.  A dimensional error of the kind RH-02ai fixed put this at
            # 29076%, so the band is wide enough to be robust and narrow enough
            # to catch that class of mistake.
            assert 1.0 <= fee_apr <= 200.0, f"fee APR {fee_apr}% outside [1, 200]"
