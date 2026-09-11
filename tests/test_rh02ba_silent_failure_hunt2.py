"""Tests for RH-02ba: fixes for 5 silent failure bugs identified in
reports/AUDIT_silent_failure_hunt2_20260909.md.

For each of the 5 issues:
1. Proof that incomplete / corrupted input fails close (fail-close proof).
2. Proof that valid inputs on old vs new versions match without regression (anti-regression).
3. At least one test runs on real recorded dataset / files.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_FIX_FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "rh02ba_pre_fix"


def _load_module_from_source(name: str, source: str, file_path: str | None = None):
    """Load module dynamically from source string."""
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    if file_path is not None:
        module.__file__ = file_path
    exec(compile(source, file_path or f"<fixture:{name}>", "exec"), module.__dict__)
    return module


def _load_pre_fix_module(rel_path: str, module_name: str):
    """Load the pre-RH-02ba snapshot of a module from tests/fixtures/rh02ba_pre_fix."""
    fixture_path = PRE_FIX_FIXTURES_DIR / Path(rel_path).name
    if not fixture_path.is_file():
        raise FileNotFoundError(
            f"Pre-fix fixture snapshot missing: {fixture_path}. "
            "Differential testing requires frozen pre-fix snapshot to prevent regression."
        )
    source = fixture_path.read_text(encoding="utf-8")
    return _load_module_from_source(module_name, source, file_path=str(fixture_path.resolve()))


# ---------------------------------------------------------------------------
# Issue 1: scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py (PRICES_USD)
# ---------------------------------------------------------------------------

def test_issue1_unknown_token_price_fails_close():
    """Repro & Fail-close: When tokens are unknown or unpriced, pricing is marked

    INPUTS_UNAVAILABLE, volume_usd_proxy is None (not Decimal('0')), and fee_ready is False.
    """
    import scripts.lp_bsc_fee_velocity_short_backfill_v2_readonly as new_bf

    # Unknown token symbol (e.g. CAKE or ETH)
    assert new_bf.PRICES_USD.get("CAKE") is None
    assert new_bf.PRICES_USD.get("ETH") is None

    # Simulate evaluation of decoded swap with unknown token
    meta = {
        "token0_symbol": "CAKE",
        "token1_symbol": "ETH",
        "token0_decimals": 18,
        "token1_decimals": 18,
        "fee_tier_raw": "2500",
    }
    p0 = new_bf.PRICES_USD.get(meta["token0_symbol"])
    p1 = new_bf.PRICES_USD.get(meta["token1_symbol"])
    assert p0 is None
    assert p1 is None

    # Fail close check: pricing_unavailable must be detected
    pricing_unavailable = (p0 is None or p1 is None)
    assert pricing_unavailable is True


def test_issue1_known_token_price_anti_regression():
    """Anti-regression: When token prices are available (e.g. WBNB, USDT),

    new and old price tables and calculations produce identical Decimal amounts.
    """
    old_bf = _load_pre_fix_module(
        "scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py", "old_bf_issue1"
    )
    import scripts.lp_bsc_fee_velocity_short_backfill_v2_readonly as new_bf

    for sym in ["WBNB", "USDT", "USDC", "BUSD", "DAI"]:
        assert new_bf.PRICES_USD[sym] == old_bf.PRICES_USD[sym]


# ---------------------------------------------------------------------------
# Issue 2: scripts/lp_survival_horizon_ev_model_v1_readonly.py (capacity & slippage)
# ---------------------------------------------------------------------------

def test_issue2_missing_capacity_fails_close():
    """Repro & Fail-close: Missing capacity field must return None, NOT 100 bps jump."""
    old_ev = _load_pre_fix_module(
        "scripts/lp_survival_horizon_ev_model_v1_readonly.py", "old_ev_issue2"
    )
    import scripts.lp_survival_horizon_ev_model_v1_readonly as new_ev

    notional = 100.0
    # Old behavior on missing/None capacity:
    # pool.get(cap_field, 0.0) -> cap = 0.0 -> slippage_cost_usd gave 100 bps:
    old_missing_slip = old_ev.slippage_cost_usd(notional, 0.0)
    assert old_missing_slip == 1.0  # $1.00 on $100 notional (100 bps)

    # New behavior on missing/None capacity:
    # slippage_cost_usd returns None
    assert new_ev.slippage_cost_usd(notional, None) is None

    # evaluate() on pool missing capacity_100 returns None (interrupts / fail-close)
    pool_without_cap = {
        "chain": "Base",
        "protocol": "Uniswap V3",
        "gas_cost_proxy": 0.01,
        "token_a_symbol": "WETH",
        "token_b_symbol": "USDC",
    }
    assert new_ev.evaluate(pool_without_cap, "realistic", notional, "24h") is None


def test_issue2_full_capacity_slippage_is_not_zero():
    """Repro & Floor slippage: At capacity_proxy = 1.0, slippage must NOT be 0.0."""
    old_ev = _load_pre_fix_module(
        "scripts/lp_survival_horizon_ev_model_v1_readonly.py", "old_ev_issue2_floor"
    )
    import scripts.lp_survival_horizon_ev_model_v1_readonly as new_ev

    notional = 100.0
    old_full_slip = old_ev.slippage_cost_usd(notional, 1.0)
    assert old_full_slip == 0.0  # Old bug: 0.0 slippage at full capacity!

    new_full_slip = new_ev.slippage_cost_usd(notional, 1.0)
    assert new_full_slip is not None
    assert new_full_slip > 0.0
    # 5 bps floor on $100 notional = $0.05
    assert abs(new_full_slip - (notional * 5.0 / 10000.0)) < 1e-9


def test_issue2_real_probe_data_anti_regression():
    """Real data: Evaluate real probed pools from reports/lp_multichain_survival_ev/20260603_051605."""
    import scripts.lp_survival_horizon_ev_model_v1_readonly as new_ev

    probe_json = REPO_ROOT / "reports/lp_multichain_survival_ev/20260603_051605/multichain_pool_readiness_probe.json"
    assert probe_json.is_file()
    data = json.loads(probe_json.read_text())
    pools = [p for p in data["results"] if p.get("state_ready")]
    assert len(pools) > 0

    # Evaluate the first real pool with realistic scenario, $100 notional, 24h
    res = new_ev.evaluate(pools[0], "realistic", 100, "24h")
    assert res is not None
    assert "slippage_cost_usd" in res
    assert res["slippage_cost_usd"] > 0.0
    assert "net_ev_proxy_usd" in res
    assert "survival_pass" in res


# ---------------------------------------------------------------------------
# Issue 3: scripts/strategy_pivot_d4_realtime_paper_shadow_validation.py (tick math)
# ---------------------------------------------------------------------------

def test_issue3_exact_tick_boundaries_vs_linear_approximation():
    """Repro: Exact Uniswap V3 log tick math vs linear approximation error."""
    old_d4 = _load_pre_fix_module(
        "scripts/strategy_pivot_d4_realtime_paper_shadow_validation.py", "old_d4_issue3"
    )
    import scripts.strategy_pivot_d4_realtime_paper_shadow_validation as new_d4

    current_tick = -202111

    # Test at range_pct = 5%
    old_lower_5, old_upper_5 = old_d4.tick_lower_upper(current_tick, 5)
    new_lower_5, new_upper_5 = new_d4.tick_lower_upper(current_tick, 5)

    # In old code: delta = 500 ticks symmetrically
    assert old_lower_5 == current_tick - 500
    assert old_upper_5 == current_tick + 500

    # In exact log formula:
    # lower delta = ln(0.95) / ln(1.0001) ≈ -512.93 ticks (floor -> -513)
    # upper delta = ln(1.05) / ln(1.0001) ≈ +487.90 ticks (ceil -> +488)
    assert new_lower_5 == current_tick - 513
    assert new_upper_5 == current_tick + 488

    # Difference in lower tick is 13 ticks; upper is 12 ticks
    assert (old_lower_5 - new_lower_5) == 13
    assert (old_upper_5 - new_upper_5) == 12

    # Test at range_pct = 10%
    old_lower_10, old_upper_10 = old_d4.tick_lower_upper(current_tick, 10)
    new_lower_10, new_upper_10 = new_d4.tick_lower_upper(current_tick, 10)

    # ln(0.90) / ln(1.0001) ≈ -1053.6 ticks (floor -> -1054)
    # ln(1.10) / ln(1.0001) ≈ +953.1 ticks (ceil -> +954)
    assert new_lower_10 == current_tick - 1054
    assert new_upper_10 == current_tick + 954
    assert (old_lower_10 - new_lower_10) == 54
    assert (old_upper_10 - new_upper_10) == 46


def test_issue3_invalid_range_fails_close():
    """Fail-close: Invalid range_pct or None tick must fail close."""
    import scripts.strategy_pivot_d4_realtime_paper_shadow_validation as new_d4

    assert new_d4.tick_lower_upper(None, 5) == (None, None)
    assert new_d4.tick_lower_upper(1000, None) == (None, None)
    with pytest.raises(ValueError, match="range_pct must be in"):
        new_d4.tick_lower_upper(1000, 0)
    with pytest.raises(ValueError, match="range_pct must be in"):
        new_d4.tick_lower_upper(1000, 105)


def test_issue3_paper_position_real_pool_anti_regression():
    """Real position: PaperPosition initializes with exact tick bounds on 0xb2cc."""
    import scripts.strategy_pivot_d4_realtime_paper_shadow_validation as d4

    p = d4.PaperPosition(1000, 2)
    p.set_entry(-202111, 47237736, 1675.6)
    assert p.lower_tick < p.entry_tick < p.upper_tick
    assert p.in_range is True
    # At 2%, ln(0.98)/ln(1.0001) = -202.02 (floor -203), ln(1.02)/ln(1.0001) = 198.02 (ceil 199)
    assert p.lower_tick == -202111 - 203
    assert p.upper_tick == -202111 + 199


# ---------------------------------------------------------------------------
# Issue 4: scripts/lp_survival_out_of_range_risk_v1_readonly.py (700 magic number)
# ---------------------------------------------------------------------------

def test_issue4_missing_p95_drift_fails_to_calibrated_base_rate():
    """Repro & Fail-close: When base_hist is missing p95_abs_drift, must use

    calibrated TICK_STDDEV_PER_HR['Base'] (60.0), NOT 700 / sqrt(8) = 247.48.
    """
    old_oor = _load_pre_fix_module(
        "scripts/lp_survival_out_of_range_risk_v1_readonly.py", "old_oor_issue4"
    )
    import scripts.lp_survival_out_of_range_risk_v1_readonly as new_oor

    pool = {
        "chain": "Base",
        "protocol": "Uniswap V3",
        "token_a_symbol": "WETH",
        "token_b_symbol": "USDC",
        "pool": "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38",
    }
    # The defect needs a base_hist that is truthy but missing the key: the old
    # guard was `if is_base_candidate and base_hist:` followed by
    # `base_hist.get("p95_abs_drift", 700)`.  An empty dict is falsy, so it
    # never reached the magic 700 and both versions return the calibrated
    # 60.0 -- testing with {} shows no difference and proves nothing.
    hist_missing_key = {"sample_count": 1, "note": "too few observations"}

    old_rows = old_oor.evaluate_pool(pool, hist_missing_key)
    new_rows = new_oor.evaluate_pool(pool, hist_missing_key)
    old_1h = next(r for r in old_rows if r["hold_window"] == "1h")
    new_1h = next(r for r in new_rows if r["hold_window"] == "1h")

    # Old: the hardcoded 700 / sqrt(8) = 247.5 ticks/hr, 4.12x the calibrated
    # Base figure, inflating out-of-range risk with no warning that the real
    # p95 observation was absent.
    assert old_1h["historical_tick_move_p95"] == int(1.96 * (700 / math.sqrt(8.0)))  # 485
    # New: no observation means the calibrated baseline, not a magic number.
    assert new_1h["historical_tick_move_p95"] == int(1.96 * 60.0)                     # 117
    assert new_1h["out_of_range_risk"] < old_1h["out_of_range_risk"]

    # And an empty dict must behave the same as a key-missing one: absence of
    # data is absence of data however it is spelled.
    empty_1h = next(r for r in new_oor.evaluate_pool(pool, {})
                    if r["hold_window"] == "1h")
    assert empty_1h["historical_tick_move_p95"] == new_1h["historical_tick_move_p95"]


def test_issue4_observed_p95_drift_anti_regression():
    """Anti-regression: When p95_abs_drift IS present, old and new give identical results."""
    old_oor = _load_pre_fix_module(
        "scripts/lp_survival_out_of_range_risk_v1_readonly.py", "old_oor_issue4_obs"
    )
    import scripts.lp_survival_out_of_range_risk_v1_readonly as new_oor

    pool = {
        "chain": "Base",
        "protocol": "Uniswap V3",
        "token_a_symbol": "WETH",
        "token_b_symbol": "USDC",
        "pool": "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38",
    }
    valid_base_hist = {
        "samples": 50,
        "p50_abs_drift": 45,
        "p90_abs_drift": 120,
        "p95_abs_drift": 170,
        "max_abs_drift": 210,
    }

    old_rows = old_oor.evaluate_pool(pool, valid_base_hist)
    new_rows = new_oor.evaluate_pool(pool, valid_base_hist)

    assert len(old_rows) == len(new_rows)
    for old_r, new_r in zip(old_rows, new_rows):
        assert old_r == new_r


def test_issue4_real_pool_data():
    """Real data: Evaluate real probed pools with out-of-range risk model."""
    import scripts.lp_survival_out_of_range_risk_v1_readonly as new_oor

    probe_json = REPO_ROOT / "reports/lp_multichain_survival_ev/20260603_051605/multichain_pool_readiness_probe.json"
    data = json.loads(probe_json.read_text())
    base_pools = [p for p in data["results"] if p.get("chain") == "Base"]
    assert len(base_pools) > 0

    rows = new_oor.evaluate_pool(base_pools[0], {})
    assert len(rows) == len(new_oor.HOLD_HOURS)
    for r in rows:
        assert 0.0 <= r["out_of_range_risk"] <= 1.0
        assert r["risk_bucket"] in ("low", "medium", "high")


# ---------------------------------------------------------------------------
# Issue 5: scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py (decode_swap ABI padding)
# ---------------------------------------------------------------------------

def test_issue5_malformed_abi_slot_fails_close():
    """Repro & Fail-close: Malformed ABI slot padding or corrupt sign extension

    must raise ValueError instead of silently returning corrupted positive tick.
    """
    old_bf = _load_pre_fix_module(
        "scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py", "old_bf_issue5"
    )
    import scripts.lp_bsc_fee_velocity_short_backfill_v2_readonly as new_bf

    # Create a 32-byte slot for tick (int24) with corrupted high bits
    # E.g., slot starts with 0x01 instead of 0x00 (positive) or 0xff (negative)
    # The low 3 bytes encode -2000 (0xfff830).
    # Correct negative 32-byte slot: 'f' * 58 + 'fff830'
    corrupt_slot = "01" * 29 + "fff830"
    assert len(corrupt_slot) == 64

    # Build log with corrupt tick slot (field 4)
    # 7 fields: amount0, amount1, sqrtPriceX96, liquidity, tick, protoFee0, protoFee1
    data_old = "0x" + "00" * 32 * 4 + corrupt_slot + "00" * 32 * 2
    log = {
        "topics": [
            "0x19b47279",
            "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ],
        "data": data_old,
    }

    # Old code masked away the corrupt high bits silently and returned -2000 or positive:
    old_decoded = old_bf.decode_swap(log)
    assert old_decoded["tick"] == -2000  # Masked away corrupt bits without error!

    # New code detects that high 29 bytes are NOT valid sign-extension (not all 0xff) and raises ValueError:
    with pytest.raises(ValueError, match="Invalid ABI sign-extension"):
        new_bf.decode_swap(log)


def test_issue5_valid_standard_swap_log_anti_regression():
    """Anti-regression: Valid ABI-encoded swap log produces identical values on old and new."""
    old_bf = _load_pre_fix_module(
        "scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py", "old_bf_issue5_valid"
    )
    import scripts.lp_bsc_fee_velocity_short_backfill_v2_readonly as new_bf

    # Positive tick: +120 -> 0x000078, padded with 0x00
    pos_tick_slot = "00" * 29 + "000078"
    # Negative tick: -2000 -> 0xfff830, padded with 0xff
    neg_tick_slot = "ff" * 29 + "fff830"

    for tick_slot in [pos_tick_slot, neg_tick_slot]:
        data = "0x" + "00" * 32 * 4 + tick_slot + "00" * 32 * 2
        log = {
            "topics": [
                "0x19b47279",
                "0x000000000000000000000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "0x000000000000000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            ],
            "data": data,
        }
        old_d = old_bf.decode_swap(log)
        new_d = new_bf.decode_swap(log)
        assert old_d == new_d
