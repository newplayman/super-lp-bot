"""WP-08 attribution-ledger and staged-inventory contracts (pure, no RPC)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import scripts.lp_portfolio_paper_runner_v1_readonly as runner
from scripts.lp_exit_policy_v1_readonly import QuoteResult


FIELDS = (
    "entry_capital_usd",
    "hodl_nav",
    "lp_nav_ex_fee",
    "il_vs_hodl_usd",
    "il_vs_hodl_pct",
    "swap_fee_income",
    "reward_income_marked",
    "reward_income_realized",
    "reward_price_pnl",
    "gas_cost",
    "priority_fee",
    "entry_swap_cost",
    "exit_swap_cost",
    "slippage",
    "price_impact",
    "lvr_estimate",
    "exit_latency_loss",
    "switching_cost",
    "realized_net_pnl",
    "alpha_vs_hodl",
    "pnl_vs_usdc",
    "capital_time_weighted",
    "ACE",
)

DEC = 18
LIQUIDITY = 10**27
AMOUNT1 = 10**18


def _state(**overrides):
    kwargs = dict(
        capital=1_000.0,
        anchor=1.0,
        range_pct=10.0,
        fee_tier=0.003,
        dec0=DEC,
        dec1=DEC,
        last_block=0,
    )
    kwargs.update(overrides)
    return runner.init_state(**kwargs)


def _pool(state, **overrides):
    value = {
        "symbol": "TEST/USDC",
        "project": "test",
        "tier": "B",
        "pool": "0x0000000000000000000000000000000000000001",
        "reward_apr": 36.5,
        "reward_price_usd": 2.0,
        "last_price": 1.0,
        "state": state,
    }
    value.update(overrides)
    return value


def _assert_v2_position(record):
    assert record["ledger_schema_version"] == 2
    assert tuple(field for field in FIELDS if field in record) == FIELDS
    for field in FIELDS:
        assert isinstance(record[field], float), field
    semantics = record["attribution_semantics"]
    assert semantics["currency"] == "USD"
    assert semantics["reward_income_realized"] == "paper_simulated_claim_not_onchain"
    assert "model" in semantics["lvr_estimate"]
    assert "model" in semantics["exit_latency_loss"]
    assert semantics["capital_time_weighted"] == "USD_seconds_in_range"
    assert semantics["ACE"] == "swap_fee_income_USD_per_USD_second_in_range"


def test_heartbeat_and_final_state_each_expose_all_23_typed_fields(monkeypatch, tmp_path):
    state = _state(entry_swap_cost=1.25)
    book = [_pool(state)]
    monkeypatch.setattr(runner, "_latest_block", lambda: 1)
    monkeypatch.setattr(
        runner,
        "fetch_pool_swaps",
        lambda *args, **kwargs: [
            {"block": 1, "price": 1.0, "liquidity": LIQUIDITY, "amount1": AMOUNT1}
        ],
    )
    monkeypatch.setattr(runner, "_now_utc", lambda: datetime(2026, 8, 8, tzinfo=timezone.utc))

    rec, _ = runner._tick(
        book,
        last_ts=datetime(2026, 8, 7, 23, 59, 50, tzinfo=timezone.utc),
    )
    assert rec["ledger_schema_version"] == 2
    _assert_v2_position(rec["by_pool"][0])

    runner._flush_state(str(tmp_path), book, 1)
    final = json.loads((tmp_path / "final_state.json").read_text())
    assert final["ledger_schema_version"] == 2
    _assert_v2_position(final["pools"][0])


def test_reward_linear_mark_claim_and_price_pnl_are_separate_paper_semantics():
    state = _state()
    runner.accrue_reward_ledger(state, 10.0, reward_token_price_usd=2.0)
    marked = runner.attribution_ledger(state, runner.mark_position(state, 1.0))
    assert marked["reward_income_marked"] == pytest.approx(10.0)
    assert marked["reward_income_realized"] == 0.0
    assert marked["reward_price_pnl"] == 0.0

    runner.mark_reward_price(state, reward_token_price_usd=3.0)
    repriced = runner.attribution_ledger(state, runner.mark_position(state, 1.0))
    assert repriced["reward_income_marked"] == pytest.approx(10.0)
    assert repriced["reward_price_pnl"] == pytest.approx(5.0)

    runner.simulate_reward_claim(state)
    claimed = runner.attribution_ledger(state, runner.mark_position(state, 1.0))
    assert claimed["reward_income_marked"] == 0.0
    assert claimed["reward_income_realized"] == pytest.approx(10.0)
    assert claimed["reward_price_pnl"] == pytest.approx(5.0)
    assert state["reward_quote"] == pytest.approx(15.0)


def test_ace_uses_usd_seconds_in_range_and_is_zero_safe():
    state = _state()
    empty = runner.attribution_ledger(state, runner.mark_position(state, 1.0))
    assert empty["capital_time_weighted"] == 0.0
    assert empty["ACE"] == 0.0

    state["fees_quote"] = 2.0
    runner.accrue_capital_time(state, 20.0)
    ledger = runner.attribution_ledger(state, runner.mark_position(state, 1.0))
    assert ledger["capital_time_weighted"] == pytest.approx(20_000.0)
    assert ledger["ACE"] == pytest.approx(2.0 / 20_000.0)


@pytest.mark.parametrize(
    ("swap", "basis", "fallback"),
    [
        ({"liquidity": LIQUIDITY}, "depth_model", None),
        ({}, "flat_placeholder", "missing_liquidity"),
    ],
)
def test_every_exit_records_cost_basis_and_missing_depth_fallback(swap, basis, fallback):
    state = _state(exit_on_breach=True)
    runner.update_position(
        state,
        [{"block": 1, "price": 1.5, "amount1": AMOUNT1, **swap}],
        now_block=1,
    )
    assert state["exited"]["exit_cost_basis"] == basis
    assert state["exited"]["exit_cost_fallback_reason"] == fallback
    ledger = runner.attribution_ledger(state, runner.mark_position(state, 1.5))
    assert ledger["exit_swap_cost"] == pytest.approx(state["exited"]["exit_cost_quote"])


@pytest.mark.parametrize(
    ("price", "signals", "expected_mode"),
    [
        (1.2, {"structural_risk_worsening": True}, "REMOVE_ONLY"),
        (0.8, {"tvl_worsening": True}, "REMOVE_TO_TARGET"),
        (0.8, {"trend_continuation": True, "netcover_forward": 0.8}, "REMOVE_TO_STABLE"),
        (0.8, {"kill_switch": True}, "PANIC_EXIT"),
    ],
)
def test_all_exit_modes_leave_an_explicit_allowed_cost_basis(price, signals, expected_mode):
    state = _state(
        exit_policy_enabled=True,
        risky_token_side="token0:TEST",
        stable_token_side="token1:USDC",
        risky_inventory_target=0.25,
    )
    runner.update_position(
        state,
        [
            {
                "block": 1,
                "price": price,
                "liquidity": LIQUIDITY,
                "amount1": AMOUNT1,
                "risk_signals": signals,
            }
        ],
        now_block=1,
    )
    assert state["exited"]["exit_mode"] == expected_mode
    assert state["exited"]["exit_cost_basis"] in {"depth_model", "flat_placeholder"}
    if expected_mode == "REMOVE_ONLY":
        assert state["exited"]["exit_cost_quote"] == 0.0
        assert state["exited"]["exit_cost_fallback_reason"] is None


def test_staged_remove_does_not_simulate_reward_claim_before_risk_off_complete():
    state = _state(
        exit_policy_enabled=True,
        risky_token_side="token0:TEST",
        stable_token_side="token1:USDC",
        risky_inventory_target=0.25,
    )
    runner.accrue_reward_ledger(state, 10.0, reward_token_price_usd=2.0)
    runner.update_position(
        state,
        [
            {
                "block": 1,
                "price": 0.8,
                "liquidity": LIQUIDITY,
                "amount1": AMOUNT1,
                "risk_signals": {"trend_continuation": True, "netcover_forward": 0.8},
                "exit_quote": QuoteResult.failed("unavailable"),
            }
        ],
        now_block=1,
    )
    ledger = runner.attribution_ledger(state, runner.mark_position(state, 0.8))
    assert state["exited"]["risk_off_complete"] is False
    assert ledger["reward_income_marked"] == 10.0
    assert ledger["reward_income_realized"] == 0.0
    assert state["reward_accounting"]["simulated_claim_count"] == 0


def test_staged_remove_tick_keeps_readonly_price_monitoring_without_lp_accrual(monkeypatch):
    state = _state(
        exit_policy_enabled=True,
        risky_token_side="token0:TEST",
        stable_token_side="token1:USDC",
        risky_inventory_target=0.25,
    )
    runner.update_position(
        state,
        [
            {
                "block": 1,
                "price": 0.8,
                "liquidity": LIQUIDITY,
                "amount1": AMOUNT1,
                "risk_signals": {"trend_continuation": True, "netcover_forward": 0.8},
                "exit_quote": QuoteResult.failed("unavailable"),
            }
        ],
        now_block=1,
    )
    assert state["exited"]["risk_off_complete"] is False
    assert state["exit_policy_context"]["state"] == "EXITING"
    fees_before = state["fees_quote"]
    rewards_before = state["reward_quote"]
    book = [_pool(state, last_price=0.8)]
    calls = []
    monkeypatch.setattr(runner, "_latest_block", lambda: 2)
    monkeypatch.setattr(runner, "_now_utc", lambda: datetime(2026, 8, 8, tzinfo=timezone.utc))

    def swaps(*args, **kwargs):
        calls.append((args, kwargs))
        return [{"block": 2, "price": 0.6, "liquidity": LIQUIDITY, "amount1": AMOUNT1}]

    monkeypatch.setattr(runner, "fetch_pool_swaps", swaps)
    rec, _ = runner._tick(
        book,
        last_ts=datetime(2026, 8, 7, 23, 59, tzinfo=timezone.utc),
    )
    assert calls
    assert book[0]["last_price"] == 0.6
    assert rec["by_pool"][0]["lp_value"] < runner.mark_position(state, 0.8)["lp_value_quote"]
    assert state["fees_quote"] == fees_before
    assert state["reward_quote"] == rewards_before
    assert state["exit_policy_context"]["state"] == "EXITING"
    assert state["exited"]["risk_off_complete"] is False


def test_legacy_v1_heartbeat_remains_readable(tmp_path):
    path = tmp_path / "heartbeat.jsonl"
    path.write_text(
        json.dumps(
            {
                "tick": 0,
                "ts_utc": "2026-08-08T00:00:00+00:00",
                "portfolio_net_usd": 1.0,
                "by_pool": [{"new_breach": False, "exited": False, "in_range": True}],
            }
        )
        + "\n"
    )
    summary = runner.read_heartbeat_compatible(path)
    assert summary["ledger_schema_version"] == 1
    assert summary["ticks"] == 1
    assert summary["last_pool_count"] == 1
