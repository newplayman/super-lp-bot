import pytest

from scripts.lp_stock_tier_policy_v1_readonly import (
    evaluate_ab_gate,
    evaluate_c_gate,
    evaluate_position,
)


def _clean_c():
    return {
        "exit_verdict": "EXITABLE_CLEAN",
        "largest_holder_pct": 9.0,
        "pool_vaults_verified_and_excluded": True,
        "sell_simulation_ok": True,
        "known_honeypot": False,
        "sell_tax_pct": 0,
        "simulation_broadcast_count": 0,
        "yield_persistence_hours": 49,
        "yield_persistence_samples": 4,
        "yield_persistence_threshold_held": True,
        "counter_token_age_days": 8,
        "position_usd": 5,
        "exit_depth_usd": 300,
        "exit_slippage_bps": 190,
    }


def test_c_requires_all_seven_gates():
    result = evaluate_c_gate(_clean_c(), current_c_exposure_usd=15)
    assert result["passed"] is True
    assert result["terminal_conjunction_complete"] is True
    assert len(result["gates"]) == 7


@pytest.mark.parametrize("key", list(_clean_c()))
def test_c_missing_evidence_fails_closed(key):
    evidence = _clean_c()
    evidence.pop(key)
    assert evaluate_c_gate(evidence)["passed"] is False


def test_c_budget_and_slippage_are_hard_caps():
    evidence = _clean_c()
    evidence["position_usd"] = 5.01
    assert evaluate_c_gate(evidence)["gates"]["7_budget_caps"] is False
    evidence = _clean_c()
    evidence["exit_slippage_bps"] = 200.01
    assert evaluate_c_gate(evidence)["gates"]["6_position_vs_depth"] is False


def test_position_cap_keeps_005pct_and_absolute_profit_gate():
    out = evaluate_position(
        tier="A", tvl_usd=30_000, exit_depth_usd=100_000,
        expected_net_profit_usd=1.01, round_trip_cost_usd=0.1,
    )
    assert out.position_cap_usd == pytest.approx(15.0)
    assert out.candidate is True
    weak = evaluate_position(
        tier="A", tvl_usd=30_000, exit_depth_usd=100_000,
        expected_net_profit_usd=0.99, round_trip_cost_usd=0.1,
    )
    assert weak.candidate is False


def test_position_missing_depth_is_zero_not_a_tvl_guess():
    out = evaluate_position(
        tier="A", tvl_usd=30_000, exit_depth_usd=None,
        expected_net_profit_usd=2, round_trip_cost_usd=0.1,
    )
    assert out.position_cap_usd == 0
    assert out.candidate is False


def test_b_adds_dual_volatility_gate_without_replacing_existing_gates():
    evidence = {
        "existing_terminal_conjunction": True,
        "instrument_normalized": True,
        "absolute_profit_pass": True,
        "dual_volatility_tightened_pass": False,
    }
    assert evaluate_ab_gate("A", evidence)["passed"] is True
    assert evaluate_ab_gate("B", evidence)["passed"] is False
