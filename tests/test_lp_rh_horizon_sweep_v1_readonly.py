#!/usr/bin/env python3
"""Tests for lp_rh_horizon_sweep_v1_readonly (RH-04d: horizon sweep + conversion audit).

Offline: the evidence fixture is constructed in-memory (no network, no wallets,
no chain writes).  Money amounts are Decimal.  One test (fixed_cost_share
constancy) is written to FAIL honestly when the cost model treats the full
principal as the leg-swap amount, per the spec's explicit instruction.
"""
from __future__ import annotations

import math
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_horizon_sweep_v1_readonly import (
    HORIZONS_HOURS,
    conversion_cost_audit,
    fixed_cost_share,
    sweep_horizons,
)


def _evidence(fee_apr_pct: float = 900.0, **overrides) -> dict:
    """In-memory evidence reproducing the RH-04b first closed-loop pool."""
    price = 3000.0
    sqrt_p = math.sqrt(price)
    l_raw = int((532.14 / sqrt_p) * 10 ** 12)
    ev = {
        "chain_id": 4663,
        "attestation_status": "ATTESTED_SAME_BLOCK",
        "protocol": "v3",
        "block_hash": "0xabc",
        "fee_apr_pct": fee_apr_pct,
        "reward_apr_pct": 0.0,
        "reward_verified": False,
        "sigma_daily": 0.03,
        "liquidity_raw": l_raw,
        "sqrt_price_x96": int(sqrt_p * 2 ** 96),
        "fee": 100,
        "dec0": 18,
        "dec1": 6,
        "gas_usd_estimate": 0.02,
    }
    ev.update(overrides)
    return ev


POS = Decimal("50")


def test_sweep_returns_expected_keys():
    rows = sweep_horizons(_evidence(), position_usd=POS)
    assert len(rows) == 4
    for row in rows:
        assert set(row) == {"horizon_hours", "fee_ev_usd", "fixed_cost_usd",
                            "netcover", "netcover_pass", "required_fee_apr_pct"}


def test_fixed_cost_exact_equal_across_horizons():
    rows = sweep_horizons(_evidence(), position_usd=POS)
    costs = [r["fixed_cost_usd"] for r in rows]
    assert all(isinstance(c, Decimal) for c in costs)
    assert all(c == costs[0] for c in costs), (
        "fixed cost must be horizon-invariant (Decimal exact equality)")


def test_fee_ev_monotonic_increasing():
    rows = sweep_horizons(_evidence(), position_usd=POS)
    fees = [r["fee_ev_usd"] for r in rows]
    assert all(fees[i] < fees[i + 1] for i in range(len(fees) - 1)), (
        "fee EV must grow with horizon")


def test_fee_ev_approximately_linear():
    rows = sweep_horizons(_evidence(), position_usd=POS)
    by_h = {r["horizon_hours"]: r["fee_ev_usd"] for r in rows}
    ratio = by_h[720] / by_h[168]
    expected = Decimal(720) / Decimal(168)
    assert abs(ratio - expected) / expected < Decimal("0.05"), (
        f"fee EV should be ~linear in horizon (ratio {float(ratio)})")


def test_required_fee_apr_monotonic_decreasing():
    rows = sweep_horizons(_evidence(), position_usd=POS)
    reqs = [r["required_fee_apr_pct"] for r in rows]
    assert all(r is not None for r in reqs)
    assert all(reqs[i] > reqs[i + 1] for i in range(len(reqs) - 1)), (
        "required fee APR must fall as the horizon lengthens")


def test_regression_netcover_at_fee_apr_900():
    row = sweep_horizons(_evidence(fee_apr_pct=900.0), position_usd=POS,
                         horizons=(168,))[0]
    # Baseline updated 2026-09-08 after the 940x conversion-cost overstatement was
    # fixed (COST_MODEL_PRICE_SCALE_BUG.md). The old 0.909 encoded the bug's output.
    assert 85.0 <= row["netcover"] <= 100.0, (
        f"netcover at fee_apr=900 should be ~91.9 post-fix, got {row['netcover']}")


def test_regression_netcover_pass_at_fee_apr_5000():
    row = sweep_horizons(_evidence(fee_apr_pct=5000.0), position_usd=POS,
                         horizons=(168,))[0]
    assert row["netcover_pass"] is True, (
        f"netcover should pass at fee_apr=5000, got {row['netcover']}")


def test_netcover_pass_consistent_with_netcover():
    for h in HORIZONS_HOURS:
        row = sweep_horizons(_evidence(), position_usd=POS, horizons=(h,))[0]
        assert row["netcover_pass"] == (
            row["netcover"] is not None and row["netcover"] >= 1.0)


def test_fixed_cost_share_constancy():
    """Fixed cost must scale with position, not super-linearly (PRD 11.3, B1 9.5).

    Absolute USD cost necessarily grows with size because larger swaps move price;
    the commander measured 0.001/0.102/1.029 bps of impact at 50/5k/50k USD on 661
    live ticks. What must stay bounded is cost AS A SHARE of position. A model that
    treated the full principal as the swap notional would show that share exploding,
    which is exactly what the 940x price-scale bug did (18.85% -> 1039.70%).
    """
    rows = fixed_cost_share(_evidence(), position_usds=(50, 500, 5000, 50000))
    shares = [Decimal(str(r["fixed_cost_pct_of_position"])) for r in rows]
    assert all(isinstance(Decimal(str(r["fixed_cost_usd"])), Decimal) for r in rows)
    # every share stays well under 1% of position
    assert max(shares) < Decimal("1.0"), f"fixed cost share too high: {shares}"
    # and the spread across two orders of magnitude stays within a factor of 5,
    # which admits real price impact but not principal-as-notional
    assert max(shares) / min(shares) < Decimal("5"), (
        "fixed cost share grows too fast with position size; the cost model may be "
        f"treating the full principal as the swap notional (PRD 11.3): {shares}")



def test_fixed_cost_share_returns_expected_keys():
    rows = fixed_cost_share(_evidence())
    assert [r["position_usd"] for r in rows] == [50, 500, 5000]
    for row in rows:
        assert set(row) == {"position_usd", "fixed_cost_usd",
                            "fixed_cost_pct_of_position"}


def test_conversion_token0_fraction_decreases_from_half():
    rows = conversion_cost_audit(_evidence(), position_usd=POS)
    fracs = [r["token0_value_fraction"] for r in rows]
    assert all(f is not None for f in fracs)
    assert fracs[0] > 0.49, f"narrow-range fraction should be ~0.5, got {fracs[0]}"
    assert all(fracs[i] > fracs[i + 1] for i in range(len(fracs) - 1)), (
        "token0 fraction should decrease as the range widens (more balanced legs)")


def test_conversion_entry_cost_differs_across_range():
    rows = conversion_cost_audit(_evidence(), position_usd=POS)
    by_r = {r["range_pct"]: r["entry_cost_usd"] for r in rows}
    narrow, wide = by_r[1], by_r[50]
    assert abs(narrow - wide) / narrow > 0.2, (
        f"entry cost should differ significantly between range=1 and range=50 "
        f"({narrow} vs {wide})")


def test_conversion_audit_returns_expected_keys():
    rows = conversion_cost_audit(_evidence(), position_usd=POS)
    assert [r["range_pct"] for r in rows] == [1, 5, 10, 20, 50]
    for row in rows:
        assert set(row) == {"range_pct", "token0_value_fraction",
                            "implied_swap_notional_usd", "entry_cost_usd"}


def test_missing_fee_apr_gives_none_not_zero():
    ev = _evidence()
    del ev["fee_apr_pct"]
    row = sweep_horizons(ev, position_usd=POS, horizons=(168,))[0]
    assert row["fee_ev_usd"] is None, "fee EV must be None when fee_apr is missing"
    assert row["netcover"] is None, "netcover must be None when fee_apr is missing"
    assert row["required_fee_apr_pct"] is None, (
        "required APR must be None when fee_apr is missing")
    assert row["fee_ev_usd"] != 0, "a missing input must not be filled with 0"


def test_missing_gas_gives_none_not_zero():
    ev = _evidence()
    del ev["gas_usd_estimate"]
    row = sweep_horizons(ev, position_usd=POS, horizons=(168,))[0]
    assert row["fixed_cost_usd"] is None, "fixed cost must be None when gas is missing"
    assert row["netcover"] is None, "netcover must be None when gas is missing"
    assert row["required_fee_apr_pct"] is None, (
        "required APR must be None when gas is missing")


def test_backsolve_self_consistency():
    row = sweep_horizons(_evidence(fee_apr_pct=900.0), position_usd=POS,
                         horizons=(168,))[0]
    req = row["required_fee_apr_pct"]
    assert req is not None
    row2 = sweep_horizons(_evidence(fee_apr_pct=req), position_usd=POS,
                          horizons=(168,))[0]
    assert abs(row2["netcover"] - 1.0) <= 0.01, (
        f"back-substituted netcover should be ~1.0, got {row2['netcover']}")
