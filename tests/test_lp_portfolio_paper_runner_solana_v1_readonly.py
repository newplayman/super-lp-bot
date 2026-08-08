"""Offline contract tests for the Solana Orca paper-runner path."""
from __future__ import annotations

import base64
import json
import math
import sqlite3

import pytest

from scripts import lp_portfolio_paper_runner_v1_readonly as runner


POOL = "Fae5dWVntUt6zbWu2voXxioDpMii7SqQwtsxBmoVCsHR"
PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
SQRT_PRICE_X64 = 51_432_574_656_936_991_057
LIQUIDITY = 432_759_360_845


def _account_value(
    *,
    owner=PROGRAM,
    space=653,
    encoding="base64",
    discriminator=bytes.fromhex("3f95d10ce1806309"),
    sqrt_price_x64=SQRT_PRICE_X64,
    liquidity=LIQUIDITY,
):
    raw = bytearray(653)
    raw[:8] = discriminator
    raw[49:65] = int(liquidity).to_bytes(16, "little")
    raw[65:81] = int(sqrt_price_x64).to_bytes(16, "little")
    return {
        "context": {"slot": 438_044_949},
        "value": {
            "data": [base64.b64encode(raw).decode("ascii"), encoding],
            "executable": False,
            "lamports": 10_000_000,
            "owner": owner,
            "rentEpoch": 0,
            "space": space,
        },
    }


def _allocation(**overrides):
    allocation = {
        "symbol": "SPYx-USDC",
        "project": "orca-whirlpool",
        "protocol": "orca_whirlpool",
        "solana_adapter": "orca_whirlpool_account_v1",
        "pool": POOL,
        "tier": "B",
        "usd": 100.0,
        "range_pct": 10.0,
        "fee_tier": 0.0002,
        "dec0": 8,
        "dec1": 6,
        "reward_apr": 0.0,
        "fee_apr_onchain": 1.0,
    }
    allocation.update(overrides)
    return allocation


def test_orca_layout_and_decimal_direction_match_live_spyx_usdc_vector():
    decoded = runner._decode_orca_whirlpool_account(
        _account_value(), decimals_a=8, decimals_b=6
    )

    assert decoded["owner"] == PROGRAM
    assert decoded["space"] == 653
    assert decoded["sqrt_price_x64"] == SQRT_PRICE_X64
    assert decoded["liquidity"] == LIQUIDITY
    assert decoded["price_direction"] == "token_b_per_token_a"
    assert decoded["price"] == pytest.approx(777.386662664190, rel=1e-12)


@pytest.mark.parametrize(
    ("account", "decimals_a", "decimals_b", "error"),
    [
        (_account_value(owner="11111111111111111111111111111111"), 8, 6, "owner"),
        (_account_value(space=652), 8, 6, "space"),
        (_account_value(encoding="base58"), 8, 6, "base64"),
        (_account_value(discriminator=b"notorca!"), 8, 6, "discriminator"),
        (_account_value(sqrt_price_x64=0), 8, 6, "sqrt_price"),
        (_account_value(liquidity=0), 8, 6, "liquidity"),
        (_account_value(), 400, 0, "finite"),
    ],
)
def test_orca_account_validation_fails_closed(
    account, decimals_a, decimals_b, error
):
    with pytest.raises(ValueError, match=error):
        runner._decode_orca_whirlpool_account(
            account, decimals_a=decimals_a, decimals_b=decimals_b
        )


def test_solana_observation_routes_get_account_info_with_base64_only():
    calls = []

    def rpc_call(method, params):
        calls.append((method, params))
        assert method == "getAccountInfo"
        return _account_value()

    observation = runner._solana_whirlpool_observation(
        POOL, decimals_a=8, decimals_b=6, rpc_call=rpc_call
    )

    assert calls == [(
        "getAccountInfo",
        [POOL, {"encoding": "base64", "commitment": "confirmed"}],
    )]
    assert observation["block"] == 438_044_949
    assert observation["amount1"] == 0
    assert observation["observation_kind"] == "account_state"


def test_solana_latest_position_routes_get_slot_not_evm(monkeypatch):
    calls = []

    class Pool:
        chain = "solana"

        def call(self, method, params):
            calls.append((method, params))
            assert not method.startswith("eth_")
            return 438_044_949

    monkeypatch.setattr(runner, "_POOL", Pool())
    assert runner._latest_block() == 438_044_949
    assert calls == [("getSlot", [])]


@pytest.mark.parametrize("missing", ["protocol", "solana_adapter"])
def test_solana_allocation_requires_explicit_protocol_and_adapter(
    monkeypatch, missing
):
    allocation = _allocation()
    allocation.pop(missing)
    monkeypatch.setattr(
        runner,
        "_rpc",
        lambda: lambda *_args, **_kwargs: pytest.fail("RPC must not run"),
    )

    with pytest.raises(ValueError, match=missing):
        runner._init_book(
            [allocation], entry_window_blocks=4000, latest=438_044_949,
            chain="solana",
        )


def test_solana_runner_init_and_one_tick_emit_ledger_without_evm_calls(
    tmp_path, monkeypatch
):
    calls = []

    class Pool:
        chain = "solana"
        _endpoints = [object()] * 6

        def __init__(self, chain):
            assert chain == "solana"

        def call(self, method, params):
            calls.append((method, params))
            assert not method.startswith("eth_")
            if method == "getSlot":
                return 438_044_949
            if method == "getAccountInfo":
                return _account_value()
            pytest.fail(f"unexpected method: {method}")

        def health_snapshot(self):
            return {"state": "NORMAL"}

    monkeypatch.setattr(runner, "RpcPool", Pool)
    monkeypatch.setattr(
        runner,
        "fetch_pool_swaps",
        lambda *_args, **_kwargs: pytest.fail("EVM swap reader must not run"),
    )
    monkeypatch.setattr(runner.time, "sleep", lambda _secs: None)

    allocation_path = tmp_path / "allocation.json"
    allocation_path.write_text(json.dumps({"allocations": [_allocation()]}))
    out = tmp_path / "solana_runner"
    gate_db = tmp_path / "scanner.db"

    runner.run(
        allocation_path,
        poll_secs=0,
        max_ticks=1,
        out=str(out),
        chain="solana",
        gate_db=gate_db,
    )

    heartbeat = json.loads((out / "heartbeat.jsonl").read_text().splitlines()[0])
    final = json.loads((out / "final_state.json").read_text())
    pool = heartbeat["by_pool"][0]

    assert [method for method, _params in calls] == [
        "getSlot", "getAccountInfo", "getSlot", "getAccountInfo"
    ]
    assert heartbeat["block"] == 438_044_949
    assert heartbeat["rpc_health"] == "NORMAL"
    assert pool["protocol"] == "orca_whirlpool"
    assert pool["solana_adapter"] == "orca_whirlpool_account_v1"
    assert pool["observation_kind"] == "account_state"
    assert pool["fees"] == 0.0
    assert pool["n_swaps"] == 0
    assert math.isfinite(pool["current_total_nav"])
    assert all(field in pool for field in runner.ATTRIBUTION_FIELDS)
    assert len(runner.ATTRIBUTION_FIELDS) == 23
    assert final["final_tick"] == 1
    assert final["pools"][0]["protocol"] == "orca_whirlpool"
    assert gate_db.exists()
    with sqlite3.connect(gate_db) as conn:
        gate_row = conn.execute(
            "SELECT current_position_count, actual_fee_usd, rpc_health, "
            "evidence_status FROM shadow_gate_observations"
        ).fetchone()
    assert gate_row == (1, 0.0, "NORMAL", "COMPLETE")
