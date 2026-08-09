"""Pure tests for the multi-pool LP paper-shadow runner (no network)."""
import inspect
import json
import sqlite3

import pytest

from scripts.lp_portfolio_paper_runner_v1_readonly import (
    LEDGER_SCHEMA_VERSION,
    _record_gate_observation,
    attribution_ledger,
    init_state,
    update_position,
    mark_position,
    accrue_reward,
    run,
)
from scripts.lp_exit_policy_v1_readonly import QuoteResult
from scripts.lp_shadow_gate_v1_readonly import GateStore

DEC = 18
FEE = 0.003
R = 10.0
L = 10 ** 24       # deep pool (human_L = 1e6): realistic, low-slippage
AMT1 = 10 ** 18    # 1.0 token1 raw


def test_shadow_runner_defaults_to_low_rate_base_polling():
    params = inspect.signature(run).parameters
    assert params["poll_secs"].default == 1800
    assert params["chain"].default == "base"


def _state(cap=1000.0, anchor=1.0):
    return init_state(capital=cap, anchor=anchor, range_pct=R,
                      fee_tier=FEE, dec0=DEC, dec1=DEC, last_block=0)


def test_in_range_swaps_accrue_fees_anchor_unchanged():
    st = _state()
    swaps = [
        {"block": 1, "price": 1.00, "liquidity": L, "amount1": AMT1},
        {"block": 2, "price": 1.03, "liquidity": L, "amount1": AMT1},
    ]
    update_position(st, swaps, now_block=2)
    assert st["fees_quote"] > 0
    assert st["breaches"] == []
    assert st["anchor"] == 1.0          # passive: anchor never moves
    assert st["last_block"] == 2
    assert st["in_range_now"] is True


def test_net_rises_with_fees():
    st = _state()
    before = mark_position(st, 1.0)["net_quote"]
    update_position(st, [{"block": 1, "price": 1.0, "liquidity": L, "amount1": AMT1}], now_block=1)
    after = mark_position(st, 1.0)["net_quote"]
    assert after > before


def test_out_of_range_swap_no_fee_records_breach_no_rebalance():
    st = _state()
    update_position(st, [{"block": 1, "price": 1.0, "liquidity": L, "amount1": AMT1}], now_block=1)
    fees_in = st["fees_quote"]
    update_position(st, [{"block": 2, "price": 1.5, "liquidity": L, "amount1": AMT1}], now_block=2)
    assert st["fees_quote"] == fees_in          # out-of-range accrues nothing
    assert len(st["breaches"]) == 1
    assert st["anchor"] == 1.0                   # no rebalance
    assert st["in_range_now"] is False


def test_breach_logged_once_per_crossing():
    st = _state()
    swaps = [
        {"block": 1, "price": 1.5, "liquidity": L, "amount1": AMT1},   # cross out
        {"block": 2, "price": 1.6, "liquidity": L, "amount1": AMT1},   # still out -> no new breach
        {"block": 3, "price": 1.0, "liquidity": L, "amount1": AMT1},   # back in
        {"block": 4, "price": 1.5, "liquidity": L, "amount1": AMT1},   # cross out again
    ]
    update_position(st, swaps, now_block=4)
    assert len(st["breaches"]) == 2             # two crossings, not four out-ticks


def test_swaps_at_or_before_last_block_ignored():
    st = _state()
    st["last_block"] = 5
    update_position(st, [{"block": 5, "price": 1.0, "liquidity": L, "amount1": AMT1}], now_block=6)
    assert st["fees_quote"] == 0.0              # block 5 not > last_block 5


def test_mark_position_roundtrip_il_zero_move_negative():
    st = _state()
    mk0 = mark_position(st, 1.0)
    assert abs(mk0["il_quote"]) < 1e-6          # at anchor IL ~ 0
    mk1 = mark_position(st, 1.2)
    assert mk1["il_quote"] < 0                  # price move => IL < 0


def test_mark_position_net_pct_consistent():
    st = _state(cap=2000.0)
    st["fees_quote"] = 20.0
    mk = mark_position(st, 1.0)
    assert abs(mk["net_quote"] - 20.0) < 1e-6   # value==cap at anchor, +fees
    assert abs(mk["net_pct"] - 1.0) < 1e-9      # 20/2000 = 1%


def test_accrue_reward_linear_and_zero_at_zero():
    assert accrue_reward(1000.0, 50.0, 0) == 0.0
    full = accrue_reward(1000.0, 50.0, 365 * 86400)
    assert abs(full - 500.0) < 1e-6             # 50% APR, 1y, 1000 => 500
    half = accrue_reward(1000.0, 50.0, 365 * 86400 / 2)
    assert abs(half * 2 - full) < 1e-9          # linear in time
    assert abs(accrue_reward(2000.0, 50.0, 365 * 86400) - 1000.0) < 1e-6  # linear in capital


def test_init_state_shape():
    st = _state()
    for k in ("capital", "anchor", "range_pct", "fee_tier", "dec0", "dec1",
              "l_pos_raw", "fees_quote", "reward_quote", "last_block",
              "breaches", "in_range_now", "exit_on_breach", "exit_cost_bps", "exited"):
        assert k in st
    assert st["l_pos_raw"] > 0
    assert st["breaches"] == [] and st["in_range_now"] is True
    assert st["exit_on_breach"] is False and st["exited"] is None


# --- Tier-B auto-exit on breach -------------------------------------------

def _state_b(cap=1000.0, anchor=1.0, exit_cost_bps=None):
    return init_state(capital=cap, anchor=anchor, range_pct=R, fee_tier=FEE,
                      dec0=DEC, dec1=DEC, last_block=0,
                      exit_on_breach=True, exit_cost_bps=exit_cost_bps)


def test_default_exit_cost_bps_is_fee_plus_slippage():
    st = _state_b()
    assert st["exit_cost_bps"] == round(FEE * 1e4) + 10.0   # 0.003 -> 30 + 10 = 40


def test_breach_triggers_exit_and_stops_accrual():
    st = _state_b()
    update_position(st, [{"block": 1, "price": 1.0, "liquidity": L, "amount1": AMT1}], now_block=1)
    assert st["exited"] is None                       # still in range
    fees_in = st["fees_quote"]
    assert fees_in > 0
    update_position(st, [{"block": 2, "price": 1.5, "liquidity": L, "amount1": AMT1}], now_block=2)
    assert st["exited"] is not None                   # breach closed it
    ex = st["exited"]
    assert ex["price"] == 1.5 and ex["block"] == 2
    assert ex["exit_cost_quote"] > 0                  # paid conversion cost
    assert ex["realized_quote"] == ex["lp_value_quote"] + ex["fees_quote"] - ex["exit_cost_quote"]
    # any further swaps accrue nothing (holds base cash)
    update_position(st, [{"block": 3, "price": 1.0, "liquidity": L, "amount1": AMT1}], now_block=3)
    assert st["fees_quote"] == fees_in


def test_exit_stops_at_first_out_swap_not_processing_rest():
    st = _state_b()
    fee0 = st["fees_quote"]
    swaps = [
        {"block": 1, "price": 1.5, "liquidity": L, "amount1": AMT1},   # breach -> exit here
        {"block": 2, "price": 1.0, "liquidity": L, "amount1": AMT1},   # must NOT be processed
    ]
    update_position(st, swaps, now_block=2)
    assert st["exited"]["price"] == 1.5
    assert st["fees_quote"] == fee0                  # the later in-range swap was skipped


def test_mark_position_exited_ignores_current_price():
    st = _state_b()
    update_position(st, [{"block": 1, "price": 1.5, "liquidity": L, "amount1": AMT1}], now_block=1)
    mk_a = mark_position(st, 0.5)
    mk_b = mark_position(st, 5.0)
    assert mk_a["exited"] is True
    assert mk_a["net_quote"] == mk_b["net_quote"]    # frozen; price ignored
    assert mk_a["lp_value_quote"] == st["exited"]["realized_quote"]


def test_flat_exit_cost_used_when_liquidity_absent():
    # breach swap with NO liquidity field -> flat exit_cost_bps path
    cheap = _state_b(exit_cost_bps=10.0)
    pricey = _state_b(exit_cost_bps=200.0)
    for st in (cheap, pricey):
        update_position(st, [{"block": 1, "price": 1.5, "amount1": AMT1}], now_block=1)
    assert cheap["exited"]["exit_cost_quote"] < pricey["exited"]["exit_cost_quote"]
    assert cheap["exited"]["realized_quote"] > pricey["exited"]["realized_quote"]


def test_model_exit_cost_used_when_liquidity_present_and_depth_matters():
    # with liquidity present, the depth model sizes the cost; deeper pool = cheaper
    shallow = _state_b()
    deep = _state_b()
    update_position(shallow, [{"block": 1, "price": 1.5, "liquidity": 10 ** 22, "amount1": AMT1}], now_block=1)
    update_position(deep, [{"block": 1, "price": 1.5, "liquidity": 10 ** 26, "amount1": AMT1}], now_block=1)
    assert shallow["exited"]["exit_cost_quote"] > deep["exited"]["exit_cost_quote"]
    # model path ignores the flat exit_cost_bps placeholder
    assert deep["exited"]["exit_cost_quote"] > 0


def test_tier_a_default_does_not_exit():
    st = _state()  # exit_on_breach defaults False
    update_position(st, [{"block": 1, "price": 1.5, "liquidity": L, "amount1": AMT1}], now_block=1)
    assert st["exited"] is None                       # Tier-A holds passive
    assert len(st["breaches"]) == 1                   # but still logs the breach


# --- WP-03 directional exit-policy integration ----------------------------

def _policy_state(**overrides):
    kwargs = {
        "capital": 1000.0,
        "anchor": 1.0,
        "range_pct": R,
        "fee_tier": FEE,
        "dec0": DEC,
        "dec1": DEC,
        "last_block": 0,
        "exit_policy_enabled": True,
        "profile": "MAJORS",
        "risky_token_side": "token0:ETH",
        "stable_token_side": "token1:USDC",
        "risky_inventory_target": 0.25,
        "max_exit_slippage_bps": 75.0,
    }
    kwargs.update(overrides)
    return init_state(**kwargs)


def test_policy_context_is_saved_and_missing_policy_defaults_record_only():
    default = _state()
    assert default["exit_policy_context"]["enabled"] is False
    assert default["exit_policy_context"]["state"] == "HEALTHY"
    strict = _policy_state()
    ctx = strict["exit_policy_context"]
    assert ctx["enabled"] is True
    assert ctx["profile"] == "MAJORS"
    assert ctx["risky_token_side"] == "token0:ETH"
    assert ctx["stable_token_side"] == "token1:USDC"
    assert ctx["risky_inventory_target"] == 0.25


@pytest.mark.parametrize(
    "hard_signal",
    [
        "rug_risk",
        "honeypot_risk",
        "data_corruption",
        "contract_risk",
        "kill_switch",
    ],
)
def test_disabled_policy_hard_risk_executes_paper_exit_and_records_gate(
    hard_signal, tmp_path
):
    st = _policy_state(exit_policy_enabled=False)
    swap = {
        "block": 1,
        "price": 0.80,
        "liquidity": 10 ** 27,
        "amount1": AMT1,
        "risk_signals": {hard_signal: True},
    }

    update_position(st, [swap], now_block=1)

    assert st["exit_policy_context"]["enabled"] is False
    assert st["exit_policy_context"]["state"] == "COOLDOWN"
    assert st["exited"] is not None
    assert st["exited"]["exit_mode"] == "PANIC_EXIT"
    assert st["exited"]["paper_only"] is True
    event = st["breaches"][0]
    for field in (
        "breach_direction",
        "post_remove_inventory_ratio",
        "post_remove_delta_usd",
        "recommended_exit_mode",
        "expected_swap_cost",
    ):
        assert field in event
    assert event["hard_risk_override"] is True
    assert event["exit_cost_basis"] == "depth_model"

    mark = mark_position(st, swap["price"])
    ledger = attribution_ledger(st, mark)
    assert ledger["exit_cost_basis"] == "depth_model"
    heartbeat = {
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "ts_utc": "2026-08-09T00:00:00+00:00",
        "rpc_health": "NORMAL",
        "portfolio_nav_usd": ledger["entry_capital_usd"] + ledger["pnl_vs_usdc"],
        "by_pool": [
            {
                "pool": f"fix-r1-{hard_signal}",
                "fee_prediction_usd": 1.0,
                **ledger,
            }
        ],
    }
    gate_db = tmp_path / "scanner.db"
    _record_gate_observation(GateStore(gate_db), "fix-r1", 0, heartbeat)
    with sqlite3.connect(gate_db) as connection:
        row = connection.execute(
            "SELECT current_position_count, evidence_json "
            "FROM shadow_gate_observations WHERE source_run=? AND tick=?",
            ("fix-r1", 0),
        ).fetchone()
    assert row is not None
    assert row[0] == 1
    assert json.loads(row[1])["position_identities"] == [f"fix-r1-{hard_signal}"]


def test_disabled_policy_soft_combination_remains_record_only():
    st = _policy_state(exit_policy_enabled=False)
    swap = {
        "block": 1,
        "price": 0.80,
        "liquidity": 10 ** 27,
        "amount1": AMT1,
        "risk_signals": {"trend_continuation": True, "netcover_forward": 0.8},
    }

    update_position(st, [swap], now_block=1)

    assert st["exited"] is None
    assert st["exit_policy_context"]["state"] == "HEALTHY"
    event = st["breaches"][0]
    assert event["hard_risk_override"] is False
    assert "action_plan" not in event


def test_strict_policy_single_lower_breach_records_five_fields_but_does_not_exit():
    st = _policy_state()
    update_position(st, [{"block": 1, "price": 0.80, "liquidity": L, "amount1": AMT1}], now_block=1)
    assert st["exited"] is None
    assert st["exit_policy_context"]["state"] == "WATCH"
    event = st["breaches"][0]
    for field in (
        "breach_direction",
        "post_remove_inventory_ratio",
        "post_remove_delta_usd",
        "recommended_exit_mode",
        "expected_swap_cost",
    ):
        assert field in event
    assert event["breach_direction"] == "LOWER"
    assert event["post_remove_inventory_ratio"] > 0.80


def test_strict_lower_combination_quotes_then_simulates_remove_to_stable():
    st = _policy_state()
    swap = {
        "block": 1,
        "price": 0.80,
        "liquidity": 10 ** 27,
        "amount1": AMT1,
        "risk_signals": {"trend_continuation": True, "netcover_forward": 0.8},
    }
    update_position(st, [swap], now_block=1)
    event = st["breaches"][0]
    assert event["recommended_exit_mode"] == "REMOVE_TO_STABLE"
    assert event["action_plan"]["quote_required"] is True
    assert event["action_plan"]["swap_allowed"] is True
    assert event["action_plan"]["paper_only"] is True
    assert st["exit_policy_context"]["state"] == "COOLDOWN"
    assert st["exited"]["exit_mode"] == "REMOVE_TO_STABLE"


def test_strict_upper_stable_inventory_remove_only_never_swaps():
    st = _policy_state()
    swap = {
        "block": 1,
        "price": 1.20,
        "liquidity": L,
        "amount1": AMT1,
        "risk_signals": {"structural_risk_worsening": True},
    }
    update_position(st, [swap], now_block=1)
    event = st["breaches"][0]
    assert event["breach_direction"] == "UPPER"
    assert event["recommended_exit_mode"] == "REMOVE_ONLY"
    assert event["action_plan"]["swap_requested"] is False
    assert event["action_plan"]["swap_allowed"] is False
    assert st["exited"]["exit_cost_quote"] == 0.0


def test_strict_quote_failure_stages_without_swap_or_cooldown():
    st = _policy_state()
    swap = {
        "block": 1,
        "price": 0.80,
        "liquidity": L,
        "amount1": AMT1,
        "risk_signals": {"trend_continuation": True, "netcover_forward": 0.8},
        "exit_quote": QuoteResult.failed("unavailable"),
    }
    update_position(st, [swap], now_block=1)
    plan = st["breaches"][0]["action_plan"]
    assert plan["swap_allowed"] is False
    assert plan["substate"] == "staged/limit_exit"
    assert plan["alert"] is True
    assert st["exit_policy_context"]["state"] == "EXITING"
    assert st["exited"]["risk_off_complete"] is False


def test_staged_remove_inventory_keeps_marking_risk_and_state_stays_exiting():
    st = _policy_state()
    swap = {
        "block": 1,
        "price": 0.80,
        "liquidity": L,
        "amount1": AMT1,
        "risk_signals": {"trend_continuation": True, "netcover_forward": 0.8},
        "exit_quote": QuoteResult.failed("unavailable"),
    }
    update_position(st, [swap], now_block=1)
    holdings = st["exited"]["inventory_holdings"]
    assert holdings["q0"] > 0.0
    assert st["exit_policy_context"]["state"] == "EXITING"

    low_mark = mark_position(st, 0.70)
    high_mark = mark_position(st, 0.90)
    assert low_mark["lp_value_quote"] < high_mark["lp_value_quote"]
    assert low_mark["net_quote"] < high_mark["net_quote"]
    assert st["exit_policy_context"]["state"] == "EXITING"
    assert st["exited"]["risk_off_complete"] is False


def test_explicit_legacy_exit_flag_isolated_from_missing_field_default():
    # Explicit old flag remains compatible; allocations with the field missing
    # no longer infer exit behavior merely from tier.
    explicit = _state_b()
    assert explicit["exit_policy_context"]["legacy_operator_confirmed"] is True
