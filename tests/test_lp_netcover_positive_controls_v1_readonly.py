"""TP-J FIX-J2 analytical positive/negative controls for the real gate path."""
from __future__ import annotations

import pytest

from scripts.lp_netcover_engine_v1_readonly import (
    NETCOVER_MODEL_CLMM,
    NETCOVER_SHADOW,
    apply_netcover_gate,
)


def _record(*, fee: float, capital: float = 100.0, gas: float = 0.0,
            entry: float = 0.0, exit: float = 0.0, slippage: float = 0.0,
            il: float = 0.0, latency: float = 0.0) -> dict[str, float | str]:
    """A complete scanner-shaped record; no NetCover logic is mocked."""
    return {
        "pool": "0xpositive-control", "capital_usd": capital,
        "protocol_type": "clmm", "netcover_model_path": NETCOVER_MODEL_CLMM,
        "fee_ev_usd": fee, "reward_ev_usd": 0.0, "il_ev_usd": il,
        "entry_cost_usd": entry, "exit_cost_usd": exit, "gas_usd": gas,
        "slippage_usd": slippage, "reward_conversion_cost_usd": 0.0,
        "exit_latency_loss_usd": latency, "reward_haircut": 0.5,
        "lvr_coefficient": 0.0,
    }


def test_strong_positive_real_gate_is_ten_cover_and_passes():
    # Total full-cost risk = $10 and realised fee EV = $100.
    out = apply_netcover_gate([_record(
        fee=100.0, gas=1.0, entry=2.0, exit=3.0, slippage=4.0,
    )])[0]
    assert out["netcover_ratio"] == pytest.approx(10.0)
    assert out["netcover_pass"] is True


def test_boundary_real_gate_is_one_and_uses_shadow_comparator():
    # Total risk = $10 exactly.  The assertion intentionally references the
    # protected threshold instead of duplicating a magic pass/fail value.
    out = apply_netcover_gate([_record(
        fee=10.0, gas=1.0, entry=2.0, exit=3.0, slippage=4.0,
    )])[0]
    assert out["netcover_ratio"] == pytest.approx(1.0)
    assert out["netcover_pass"] is (out["netcover_ratio"] >= NETCOVER_SHADOW)


def test_strong_negative_zero_fee_real_gate_fails():
    out = apply_netcover_gate([_record(
        fee=0.0, gas=1.0, entry=2.0, exit=3.0, slippage=4.0,
    )])[0]
    assert out["netcover_ratio"] == pytest.approx(0.0)
    assert out["netcover_pass"] is False


def test_unit_grid_monotonicity_and_size_ratio_match_fixed_cost_algebra():
    # income = position × hours × rate; cost = fixed gas + position × c.
    # Holding time is represented through fee EV, exactly as the gate receives
    # horizon-dollar inputs.  Every point drives apply_netcover_gate itself.
    positions = (5.0, 50.0, 500.0, 5000.0)
    hours = (168.0, 720.0, 2160.0)
    fee_rate_per_usd_hour = 0.0002
    fixed_gas = 1.0
    proportional_cost = 0.01 + 0.01 + 0.005
    grid: dict[tuple[float, float], float] = {}
    for position in positions:
        for horizon in hours:
            out = apply_netcover_gate([_record(
                fee=position * horizon * fee_rate_per_usd_hour,
                capital=position, gas=fixed_gas, entry=position * 0.01,
                exit=position * 0.01, slippage=position * 0.005,
            )])[0]
            grid[(position, horizon)] = float(out["netcover_ratio"])
    for horizon in hours:
        assert [grid[(position, horizon)] for position in positions] == sorted(
            grid[(position, horizon)] for position in positions
        )
    for position in positions:
        assert [grid[(position, horizon)] for horizon in hours] == sorted(
            grid[(position, horizon)] for horizon in hours
        )
    observed = grid[(5000.0, 720.0)] / grid[(5.0, 720.0)]
    exact = (5000.0 / (fixed_gas + 5000.0 * proportional_cost)) / (
        5.0 / (fixed_gas + 5.0 * proportional_cost)
    )
    # Floating point gate arithmetic should stay at the analytical value;
    # narrow bounds catch a unit regression without depending on a magic ratio.
    assert exact * 0.999999 <= observed <= exact * 1.000001
