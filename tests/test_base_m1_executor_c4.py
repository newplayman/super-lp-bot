from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from execution.base_m1_executor_v1 import (
    AERODROME_SLIPSTREAM_NPMS,
    LIVE_CONFIRMATION,
    UNISWAP_V3_NPM,
    Action,
    Broadcaster,
    CastKeystoreSigner,
    ExecutionPolicy,
    ExecutionState,
    Intent,
    IntentValidator,
    Ledger,
    LiveTradingLocked,
    LiveUnlock,
    PolicyRejected,
    Preflight,
    Protocol,
    UINT256_MAX,
    build_transaction,
    decode_revert_data,
    dry_run,
    encode_approve,
    encode_burn,
    encode_decrease,
    encode_slipstream_mint,
    encode_uniswap_mint,
    verify_keystore_permissions,
    wait_for_final_receipt,
)


WALLET = "0x1111111111111111111111111111111111111111"
TOKEN0 = "0x4200000000000000000000000000000000000006"
TOKEN1 = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
POOL = "0xd0b53D9277642d899DF5C87A3966A349A798F224"


def intent(action: Action = Action.MINT, **overrides):
    values = dict(
        protocol=Protocol.UNISWAP_V3, npm=UNISWAP_V3_NPM, action=action,
        wallet=WALLET, strategy_decision_id="decision-1", risk_verdict_id="risk-1",
        idempotency_key=f"key-{action.value}", notional_usd=50, slippage_bps=50,
        deadline=int(time.time()) + 600, token0=TOKEN0, token1=TOKEN1, fee=100,
        pool=POOL,
        tick_lower=-200500, tick_upper=-200300, amount0_desired=10**15,
        amount1_desired=25_000_000, amount0_min=990_000_000_000_000,
        amount1_min=24_750_000,
    )
    values.update(overrides)
    return Intent(**values)


def preflight(**overrides):
    values = dict(simulate_ok=True, quote_ok=True, basis_ok=True, rpc_health_ok=True,
                  wallet_balance_ok=True, simulation={"ok": True}, quote={"ok": True},
                  basis={"ok": True}, rpc_health={"ok": True}, wallet_balance={"ok": True})
    values.update(overrides)
    return Preflight(**values)


class FakeRpc:
    def __init__(self):
        self.sends = []

    def simulate(self, _tx): return "0x"
    def estimate_gas(self, _tx): return 100_000
    def eip1559_fees(self): return (2_000_000, 1_000_000)
    def broadcast_raw(self, raw):
        self.sends.append(raw)
        return "0xhash"


def test_abi_selectors_match_official_npm_interfaces():
    assert encode_uniswap_mint(TOKEN0, TOKEN1, 100, -10, 10, 1, 2, 1, 1, WALLET, 1).startswith("0x88316456")
    assert encode_slipstream_mint(TOKEN0, TOKEN1, 1, -10, 10, 1, 2, 1, 1, WALLET, 1).startswith("0xb5007d1f")
    assert encode_decrease(1, 2, 0, 0, 3).startswith("0x0c49ccbe")
    assert encode_burn(1).startswith("0x42966c68")


def test_approve_exact_and_exit_revoke_never_approve_max():
    approve = intent(Action.APPROVE_EXACT, token=TOKEN1, spender=UNISWAP_V3_NPM,
                     amount=50_000_000, idempotency_key="approve")
    revoke = intent(Action.REVOKE, token=TOKEN1, spender=UNISWAP_V3_NPM,
                    amount=UINT256_MAX, idempotency_key="revoke")
    assert build_transaction(approve).data == encode_approve(UNISWAP_V3_NPM, 50_000_000)
    assert build_transaction(revoke).data == encode_approve(UNISWAP_V3_NPM, 0)
    with pytest.raises(PolicyRejected, match="ApproveMax"):
        encode_approve(UNISWAP_V3_NPM, UINT256_MAX)


@pytest.mark.parametrize("environment,confirmation", [({}, ""), ({"LIVE_TRADING": "true"}, ""), ({}, LIVE_CONFIRMATION)])
def test_broadcast_raises_unless_both_process_start_gates_open(environment, confirmation):
    rpc = FakeRpc()
    broadcaster = Broadcaster(rpc, LiveUnlock.from_process_start(confirmation, environment))
    with pytest.raises(LiveTradingLocked):
        broadcaster.broadcast("0xsigned")
    assert broadcaster.broadcast_count == 0
    assert rpc.sends == []


def test_dual_unlock_can_reach_injected_fake_transport_only():
    rpc = FakeRpc()
    broadcaster = Broadcaster(rpc, LiveUnlock.from_process_start(LIVE_CONFIRMATION, {"LIVE_TRADING": "true"}))
    assert broadcaster.broadcast("0xtest-only") == "0xhash"
    assert broadcaster.broadcast_count == 1


@pytest.mark.parametrize("failed", ["simulate_ok", "quote_ok", "basis_ok", "rpc_health_ok", "wallet_balance_ok"])
def test_each_of_five_preflight_checks_fails_closed(failed):
    with pytest.raises(PolicyRejected, match=failed):
        preflight(**{failed: False}).require_all()


def test_whitelist_caps_ids_deadline_and_exit_only(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    validator = IntentValidator(ExecutionPolicy(allowed_pools=frozenset({POOL})), ledger)
    validator.validate(intent(), ExecutionState.NORMAL)
    with pytest.raises(PolicyRejected, match="EXIT_ONLY"):
        validator.validate(intent(), ExecutionState.EXIT_ONLY)
    exit_intent = intent(Action.BURN, token_id=1, notional_usd=0, idempotency_key="burn")
    validator.validate(exit_intent, ExecutionState.EXIT_ONLY)
    with pytest.raises(PolicyRejected, match="not allowlisted"):
        validator.validate(intent(npm="0x2222222222222222222222222222222222222222"), ExecutionState.NORMAL)
    with pytest.raises(PolicyRejected, match="notional cap"):
        validator.validate(intent(notional_usd=61), ExecutionState.NORMAL)
    with pytest.raises(PolicyRejected, match="slippage"):
        validator.validate(intent(slippage_bps=76), ExecutionState.NORMAL)
    with pytest.raises(PolicyRejected, match="identifiers"):
        validator.validate(intent(risk_verdict_id=""), ExecutionState.NORMAL)


def test_all_official_slipstream_npm_deployments_are_allowlisted(tmp_path):
    policy = ExecutionPolicy()
    assert len(AERODROME_SLIPSTREAM_NPMS) == 3
    assert all(policy.npm_allowed(Protocol.AERODROME_SLIPSTREAM, npm) for npm in AERODROME_SLIPSTREAM_NPMS)


def test_idempotency_and_daily_cap_use_confirmed_ledger_rows(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = Ledger(path)
    day = time.strftime("%Y-%m-%d", time.gmtime())
    ledger.append({"idempotency_key": "taken", "status": "confirmed", "utc_day": day, "notional_usd": 20})
    validator = IntentValidator(ExecutionPolicy(daily_cap_usd=60, allowed_pools=frozenset({POOL})), ledger)
    with pytest.raises(PolicyRejected, match="duplicate"):
        validator.validate(intent(idempotency_key="taken"), ExecutionState.NORMAL)
    with pytest.raises(PolicyRejected, match="daily"):
        validator.validate(intent(idempotency_key="new", notional_usd=50), ExecutionState.NORMAL)


def test_keystore_and_password_permissions_fail_closed(tmp_path):
    key = tmp_path / "key.json"
    key.write_text(json.dumps({"crypto": {}}))
    os.chmod(key, 0o600)
    verify_keystore_permissions(key, os.getuid())
    os.chmod(key, 0o640)
    with pytest.raises(PermissionError, match="group/other"):
        verify_keystore_permissions(key)


def test_keystore_signer_uses_cast_without_secret_environment(tmp_path):
    key, password = tmp_path / "key.json", tmp_path / "password"
    key.write_text("{}")
    password.write_text("test-only")
    os.chmod(key, 0o600)
    os.chmod(password, 0o600)
    captured = {}
    def run(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="0xdeadbeef\n", stderr="")
    signer = CastKeystoreSigner(key, password, "http://127.0.0.1:8545", os.getuid(), run)
    raw = signer.sign(build_transaction(intent()), 7, 120_000, 2_000_000, 1_000_000)
    assert raw == "0xdeadbeef"
    assert "--keystore" in captured["command"] and "--password-file" in captured["command"]
    assert captured["command"][3] == build_transaction(intent()).data
    assert "--data" not in captured["command"]
    assert captured["kwargs"]["env"] == {"PATH": os.environ["PATH"]}
    assert all("private" not in item.lower() and "mnemonic" not in item.lower() for item in captured["command"])


def test_dry_run_never_signs_or_broadcasts(tmp_path):
    result = dry_run(intent(), preflight(), FakeRpc(), ExecutionPolicy(allowed_pools=frozenset({POOL})), Ledger(tmp_path / "ledger"))
    assert result["broadcast_count"] == 0
    assert result["signed"] is False
    assert result["raw_transaction"] is None


def test_receipt_parser_requires_success_and_stable_confirmations():
    class ReceiptRpc:
        def receipt(self, _tx_hash):
            return {"status": "0x1", "blockHash": "0xaaa", "blockNumber": "0xa"}
        def block_number(self): return 12
    receipt = wait_for_final_receipt(ReceiptRpc(), "0xtx", confirmations=3, poll_seconds=0)
    assert receipt["blockHash"] == "0xaaa"


def test_revert_reason_decoder_handles_error_and_panic():
    message = "too little received".encode().hex().ljust(64, "0")
    error = "0x08c379a0" + f"{32:064x}" + f"{19:064x}" + message
    assert decode_revert_data(error) == "Error(too little received)"
    assert decode_revert_data("0x4e487b71" + f"{17:064x}") == "Panic(0x11)"
