from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from decimal import Decimal

import pytest

from execution.solana_m1_sidecar_v1 import (
    BPF_LOADERS,
    COMPUTE_BUDGET_PROGRAM,
    LIVE_CONFIRMATION,
    ORCA_WHIRLPOOL_PROGRAM,
    RAYDIUM_AMM_V4_PROGRAM,
    RAYDIUM_CLMM_PROGRAM,
    TOKEN_2022_PROGRAM,
    TOKEN_PROGRAM,
    AccountMeta,
    Action,
    Broadcaster,
    EncryptedKeystoreSigner,
    ExecutionPolicy,
    ExecutionState,
    Instruction,
    Intent,
    IntentValidator,
    Ledger,
    LiveTradingLocked,
    LiveUnlock,
    PolicyRejected,
    Preflight,
    Protocol,
    SolanaM1Sidecar,
    build_unsigned_legacy_transaction,
    dry_run,
    read_mint_semantics,
    verify_program_on_chain,
    verify_transaction_programs,
    wait_for_final_signature,
)
from scripts.lp_solana_m1_dry_run_v1_readonly import run as run_dry_run_report


NOW = 1_787_000_000
WALLET = "11111111111111111111111111111111"
POOL = RAYDIUM_AMM_V4_PROGRAM
MINT = TOKEN_PROGRAM
BLOCKHASH = "11111111111111111111111111111111"


def test_official_token2022_and_orca_program_ids_are_not_aliases():
    assert TOKEN_2022_PROGRAM == "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
    assert ORCA_WHIRLPOOL_PROGRAM == "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"


class FakeRpc:
    def __init__(self):
        self.simulate_calls = 0
        self.send_calls = 0
        self.account_responses = {}

    def account_info(self, address):
        if address in self.account_responses:
            return self.account_responses[address]
        return {
            "context": {"slot": 456},
            "value": {
                "executable": True,
                "owner": "BPFLoaderUpgradeab1e11111111111111111111111",
            },
        }

    def simulate(self, _tx):
        self.simulate_calls += 1
        return {"context": {"slot": 457}, "value": {"err": None, "logs": ["ok"], "unitsConsumed": 1}}

    def send_transaction(self, _signed):
        self.send_calls += 1
        return "signature-test-only"

    def signature_status(self, _signature):
        return {"slot": 458, "confirmations": None, "err": None, "confirmationStatus": "finalized"}


class FakeSigner:
    def __init__(self):
        self.calls = 0

    def sign(self, _unsigned):
        self.calls += 1
        return "signed-test-only"


def intent(action=Action.OPEN, **overrides):
    fields = dict(
        protocol=Protocol.RAYDIUM_AMM,
        action=action,
        wallet=WALLET,
        pool=POOL,
        token_mints=(MINT,),
        strategy_decision_id="decision-e3",
        risk_verdict_id="risk-e3",
        idempotency_key=f"e3-{action.value}",
        notional_usd=5.0,
        slippage_bps=75,
        deadline_unix=NOW + 120,
        reduces_risk=False,
    )
    fields.update(overrides)
    return Intent(**fields)


def instruction(action=Action.OPEN, program=RAYDIUM_AMM_V4_PROGRAM):
    return Instruction(program, (AccountMeta(POOL, False, True),), b"\x01\x02", action)


def preflight(**overrides):
    fields = dict(
        simulate_ok=True,
        quote_ok=True,
        basis_ok=True,
        rpc_health_ok=True,
        wallet_balance_ok=True,
        simulation={"slot": 1},
        quote={"source": "test"},
        basis={"source": "test"},
        rpc_health={"health": "ok"},
        wallet_balance={"lamports": 1},
    )
    fields.update(overrides)
    return Preflight(**fields)


def policy():
    return ExecutionPolicy(allowed_pools=frozenset({POOL}), allowed_mints=frozenset({MINT}))


def test_action_and_program_allowlists_are_exact():
    assert {item.value for item in Action} == {"open", "increase", "decrease", "collect", "close", "swap"}
    assert {
        RAYDIUM_AMM_V4_PROGRAM,
        RAYDIUM_CLMM_PROGRAM,
        ORCA_WHIRLPOOL_PROGRAM,
    }.issubset(ExecutionPolicy().allowed_programs)


def test_unsigned_builder_contains_zero_signatures_and_never_accepts_secret_material():
    built = build_unsigned_legacy_transaction(
        fee_payer=WALLET,
        recent_blockhash=BLOCKHASH,
        last_valid_block_height=120,
        instructions=[instruction()],
    )
    raw = base64.b64decode(built.transaction_base64)
    assert built.required_signatures == 1
    assert raw[0] == 1 and raw[1:65] == bytes(64)
    assert base64.b64decode(built.message_base64) == raw[65:]


@pytest.mark.parametrize(
    "env,confirmation",
    [({}, ""), ({"LIVE_TRADING": "true"}, ""), ({}, LIVE_CONFIRMATION)],
)
def test_broadcast_dual_gate_is_checked_before_transport(env, confirmation):
    rpc = FakeRpc()
    broadcaster = Broadcaster(rpc, LiveUnlock.from_process_start(confirmation, env))
    with pytest.raises(LiveTradingLocked):
        broadcaster.broadcast("not-a-real-transaction")
    assert rpc.send_calls == 0


def test_raw_private_key_and_mnemonic_environment_is_forbidden():
    with pytest.raises(PolicyRejected, match="raw secret"):
        LiveUnlock.from_process_start("", {"SOLANA_PRIVATE_KEY": "forbidden"})
    with pytest.raises(PolicyRejected, match="raw secret"):
        LiveUnlock.from_process_start("", {"MNEMONIC": "forbidden"})


@pytest.mark.parametrize("failed", ["simulate_ok", "quote_ok", "basis_ok", "rpc_health_ok", "wallet_balance_ok"])
def test_each_preflight_check_fails_closed(failed):
    with pytest.raises(PolicyRejected, match=failed):
        preflight(**{failed: False}).require_all()


def test_program_requires_both_allowlist_and_runtime_executable_evidence():
    rpc = FakeRpc()
    evidence = verify_program_on_chain(rpc, RAYDIUM_AMM_V4_PROGRAM, policy().allowed_programs)
    assert evidence.executable and evidence.owner in BPF_LOADERS and evidence.slot == 456
    rpc.account_responses[RAYDIUM_AMM_V4_PROGRAM] = {
        "context": {"slot": 1},
        "value": {"executable": False, "owner": "BPFLoaderUpgradeab1e11111111111111111111111"},
    }
    with pytest.raises(PolicyRejected, match="not an executable"):
        verify_program_on_chain(rpc, RAYDIUM_AMM_V4_PROGRAM, policy().allowed_programs)
    with pytest.raises(PolicyRejected, match="not allowlisted"):
        verify_program_on_chain(rpc, "Vote111111111111111111111111111111111111111", policy().allowed_programs)


def test_protocol_program_and_semantic_action_must_match():
    rpc = FakeRpc()
    with pytest.raises(PolicyRejected, match="official DEX"):
        verify_transaction_programs(rpc, intent(), [instruction(program=RAYDIUM_CLMM_PROGRAM)], policy())
    with pytest.raises(PolicyRejected, match="action"):
        verify_transaction_programs(rpc, intent(), [instruction(Action.CLOSE)], policy())


def test_support_instruction_must_also_be_allowlisted_and_verified():
    rpc = FakeRpc()
    rows = verify_transaction_programs(
        rpc,
        intent(),
        [instruction(), Instruction(COMPUTE_BUDGET_PROGRAM, (), b"", None)],
        policy(),
    )
    assert {row.program_id for row in rows} == {RAYDIUM_AMM_V4_PROGRAM, COMPUTE_BUDGET_PROGRAM}


def test_exit_only_allows_only_reduce_risk_and_explicit_reduce_swap(tmp_path):
    validator = IntentValidator(policy(), Ledger(tmp_path / "ledger.jsonl"), now=lambda: NOW)
    with pytest.raises(PolicyRejected, match="EXIT_ONLY"):
        validator.validate(intent(), ExecutionState.EXIT_ONLY, 100, 120)
    validator.validate(
        intent(Action.CLOSE, notional_usd=0, idempotency_key="close"),
        ExecutionState.EXIT_ONLY,
        100,
        120,
    )
    validator.validate(
        intent(Action.SWAP, reduces_risk=True, idempotency_key="swap-exit"),
        ExecutionState.EXIT_ONLY,
        100,
        120,
    )


def test_caps_ids_deadline_and_blockhash_are_fail_closed(tmp_path):
    validator = IntentValidator(policy(), Ledger(tmp_path / "ledger.jsonl"), now=lambda: NOW)
    with pytest.raises(PolicyRejected, match="notional"):
        validator.validate(intent(notional_usd=51), ExecutionState.NORMAL, 100, 120)
    with pytest.raises(PolicyRejected, match="slippage"):
        validator.validate(intent(slippage_bps=201), ExecutionState.NORMAL, 100, 120)
    with pytest.raises(PolicyRejected, match="identifiers"):
        validator.validate(intent(risk_verdict_id=""), ExecutionState.NORMAL, 100, 120)
    with pytest.raises(PolicyRejected, match="deadline"):
        validator.validate(intent(deadline_unix=NOW), ExecutionState.NORMAL, 100, 120)
    with pytest.raises(PolicyRejected, match="blockhash"):
        validator.validate(intent(), ExecutionState.NORMAL, 121, 120)
    with pytest.raises(PolicyRejected, match="unbounded"):
        validator.validate(intent(), ExecutionState.NORMAL, 100, 251)


def test_ledger_reservation_enforces_idempotency_and_counts_inflight_daily_cap(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.reserve(intent(notional_usd=40), 60, NOW)
    with pytest.raises(PolicyRejected, match="duplicate"):
        ledger.reserve(intent(notional_usd=1), 60, NOW)
    with pytest.raises(PolicyRejected, match="daily"):
        ledger.reserve(intent(idempotency_key="other", notional_usd=21), 60, NOW)


def test_daily_cap_counts_one_latest_lifecycle_row_per_idempotency_key(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    first = intent(idempotency_key="first", notional_usd=40)
    ledger.reserve(first, 60, NOW)
    day = time.strftime("%Y-%m-%d", time.gmtime(NOW))
    ledger.append({"status": "submitted", "utc_day": day, "idempotency_key": "first", "notional_usd": 40})
    ledger.append({"status": "confirmed", "utc_day": day, "idempotency_key": "first", "notional_usd": 40})
    ledger.reserve(intent(idempotency_key="second", notional_usd=20), 60, NOW)
    with pytest.raises(PolicyRejected, match="daily"):
        ledger.reserve(intent(idempotency_key="third", notional_usd=1), 60, NOW)


def _mint_response(owner, decimals=6, extensions=None):
    return {
        "context": {"slot": 1},
        "value": {
            "owner": owner,
            "executable": False,
            "data": {"parsed": {"type": "mint", "info": {"decimals": decimals, "extensions": extensions or []}}},
        },
    }


def test_token_2022_scaled_ui_amount_keeps_raw_accounting_and_ui_semantics_separate():
    rpc = FakeRpc()
    rpc.account_responses[MINT] = _mint_response(
        TOKEN_2022_PROGRAM,
        extensions=[
            {
                "extension": "scaledUiAmountConfig",
                "state": {
                    "multiplier": "0.5",
                    "newMultiplier": "0.25",
                    "newMultiplierEffectiveTimestamp": NOW + 100,
                },
            }
        ],
    )
    semantics = read_mint_semantics(rpc, MINT, NOW)
    assert semantics.accounting_amount(2_000_000) == Decimal("2")
    assert semantics.ui_amount(2_000_000) == Decimal("1.0")
    assert semantics.notional(2_000_000, "100", "per_ui_unit") == Decimal("100.0")
    assert semantics.notional(2_000_000, "100", "per_accounting_unit") == Decimal("200")
    assert semantics.raw_from_ui_exact("1") == 2_000_000
    with pytest.raises(PolicyRejected, match="price semantics"):
        semantics.notional(2_000_000, "100", "unknown")


def test_scaled_ui_scheduled_multiplier_activates_by_timestamp():
    rpc = FakeRpc()
    rpc.account_responses[MINT] = _mint_response(
        TOKEN_2022_PROGRAM,
        extensions=[
            {
                "extensionType": "scaledUiAmountConfig",
                "state": {
                    "currentMultiplier": "0.5",
                    "newMultiplier": "0.25",
                    "newMultiplierEffectiveTime": NOW - 1,
                },
            }
        ],
    )
    semantics = read_mint_semantics(rpc, MINT, NOW)
    assert semantics.scaled_ui_multiplier == Decimal("0.25")
    assert semantics.multiplier_effective_at == NOW - 1


def test_legacy_spl_mint_has_identity_ui_multiplier_and_wrong_owner_rejected():
    rpc = FakeRpc()
    rpc.account_responses[MINT] = _mint_response(TOKEN_PROGRAM, decimals=9)
    semantics = read_mint_semantics(rpc, MINT, NOW)
    assert semantics.ui_amount(1_000_000_000) == Decimal(1)
    rpc.account_responses[MINT] = _mint_response(WALLET)
    with pytest.raises(PolicyRejected, match="not SPL Token"):
        read_mint_semantics(rpc, MINT, NOW)


def test_dry_run_builds_and_simulates_without_signing_broadcast_or_ledger_write(tmp_path):
    rpc = FakeRpc()
    ledger = Ledger(tmp_path / "ledger.jsonl")
    report = dry_run(
        intent=intent(),
        preflight=preflight(),
        instructions=[instruction()],
        recent_blockhash=BLOCKHASH,
        last_valid_block_height=120,
        current_block_height=100,
        rpc=rpc,
        policy=policy(),
        ledger=ledger,
        now=lambda: NOW,
    )
    assert report["stage"] == "E3_SOLANA_DRY_RUN"
    assert report["preflight_all_pass"] is True
    assert report["signed"] is False and report["broadcast_count"] == 0
    assert report["raw_transaction"] is None and report["keystore_loaded"] is False
    assert rpc.simulate_calls == 1 and rpc.send_calls == 0
    assert not ledger.path.exists()


def test_simulation_error_rejects_dry_run(tmp_path):
    rpc = FakeRpc()
    rpc.simulate = lambda _tx: {"value": {"err": {"InstructionError": [0, "Invalid"]}}}
    with pytest.raises(PolicyRejected, match="simulateTransaction"):
        dry_run(
            intent=intent(), preflight=preflight(), instructions=[instruction()],
            recent_blockhash=BLOCKHASH, last_valid_block_height=120, current_block_height=100,
            rpc=rpc, policy=policy(), ledger=Ledger(tmp_path / "ledger"), now=lambda: NOW,
        )


def test_locked_sidecar_never_calls_signer_even_after_successful_simulation(tmp_path, monkeypatch):
    monkeypatch.delenv("PRIVATE_KEY", raising=False)
    monkeypatch.delenv("SOLANA_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("SOLANA_SECRET_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("MNEMONIC", raising=False)
    monkeypatch.delenv("SEED_PHRASE", raising=False)
    rpc, signer = FakeRpc(), FakeSigner()
    sidecar = SolanaM1Sidecar(
        rpc=rpc,
        signer=signer,
        broadcaster=Broadcaster(rpc, LiveUnlock(False, False)),
        policy=policy(),
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        now=lambda: NOW,
    )
    with pytest.raises(LiveTradingLocked):
        sidecar.execute(
            intent=intent(), preflight=preflight(), instructions=[instruction()],
            recent_blockhash=BLOCKHASH, last_valid_block_height=120, current_block_height=100,
        )
    assert signer.calls == 0 and rpc.send_calls == 0
    assert not sidecar.ledger.path.exists()


def test_unlocked_fake_transport_confirms_and_forces_result_to_ledger(tmp_path, monkeypatch):
    for key in ("PRIVATE_KEY", "SOLANA_PRIVATE_KEY", "SOLANA_SECRET_KEY", "SECRET_KEY", "MNEMONIC", "SEED_PHRASE"):
        monkeypatch.delenv(key, raising=False)
    rpc, signer = FakeRpc(), FakeSigner()
    ledger = Ledger(tmp_path / "ledger.jsonl")
    sidecar = SolanaM1Sidecar(
        rpc=rpc,
        signer=signer,
        broadcaster=Broadcaster(rpc, LiveUnlock(True, True)),
        policy=policy(),
        ledger=ledger,
        now=lambda: NOW,
    )
    row = sidecar.execute(
        intent=intent(), preflight=preflight(), instructions=[instruction()],
        recent_blockhash=BLOCKHASH, last_valid_block_height=120, current_block_height=100,
    )
    assert row["status"] == "confirmed" and row["confirmation"]["confirmationStatus"] == "finalized"
    assert signer.calls == 1 and rpc.send_calls == 1
    statuses = [json.loads(line)["status"] for line in ledger.path.read_text().splitlines()]
    assert statuses == ["prepared", "submitted", "confirmed"]


def test_signature_failure_is_rejected_and_never_marked_confirmed():
    rpc = FakeRpc()
    rpc.signature_status = lambda _signature: {
        "slot": 1, "err": {"InstructionError": [0, "Custom"]}, "confirmationStatus": "finalized"
    }
    with pytest.raises(RuntimeError, match="transaction failed"):
        wait_for_final_signature(rpc, "fixture", timeout_seconds=1, poll_seconds=0)


def test_kill_switch_is_durable_and_blocks_open(tmp_path, monkeypatch):
    for key in ("PRIVATE_KEY", "SOLANA_PRIVATE_KEY", "SOLANA_SECRET_KEY", "SECRET_KEY", "MNEMONIC", "SEED_PHRASE"):
        monkeypatch.delenv(key, raising=False)
    rpc = FakeRpc()
    ledger = Ledger(tmp_path / "ledger.jsonl")
    sidecar = SolanaM1Sidecar(
        rpc=rpc, signer=FakeSigner(), broadcaster=Broadcaster(rpc, LiveUnlock(False, False)),
        policy=policy(), ledger=ledger, now=lambda: NOW,
    )
    sidecar.trigger_kill_switch("rpc health")
    with pytest.raises(PolicyRejected, match="EXIT_ONLY"):
        sidecar.execute(
            intent=intent(), preflight=preflight(), instructions=[instruction()],
            recent_blockhash=BLOCKHASH, last_valid_block_height=120, current_block_height=100,
        )
    assert json.loads(ledger.path.read_text().splitlines()[0])["state"] == "EXIT_ONLY"


def test_encrypted_keystore_permissions_and_external_signer_boundary(tmp_path):
    key, password = tmp_path / "keystore.enc.json", tmp_path / "password"
    key.write_text(json.dumps({"version": 1, "crypto": {"cipher": "aes", "ciphertext": "00", "kdf": "scrypt", "mac": "00"}}))
    password.write_text("test-only")
    os.chmod(key, 0o600)
    os.chmod(password, 0o600)
    captured = {}

    def run(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="signed-fixture\n", stderr="")

    signer = EncryptedKeystoreSigner(key, password, os.getuid(), run)
    assert signer.sign("unsigned-fixture") == "signed-fixture"
    assert captured["kwargs"]["input"] == "unsigned-fixture"
    assert captured["kwargs"]["env"] == {"PATH": os.environ.get("PATH", "")}
    assert "--keystore" in captured["command"] and "--password-file" in captured["command"]
    assert all("private" not in part.lower() and "mnemonic" not in part.lower() for part in captured["command"])
    os.chmod(password, 0o640)
    with pytest.raises(PermissionError, match="0600"):
        EncryptedKeystoreSigner(key, password, os.getuid(), run)


def test_cli_runner_produces_c5_shaped_report_with_only_read_and_simulate_rpc(tmp_path):
    class RunnerRpc(FakeRpc):
        def __init__(self):
            super().__init__()
            self.methods = []

        def call(self, method, _params):
            self.methods.append(method)
            if method == "getGenesisHash":
                return "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
            if method == "getLatestBlockhash":
                return {"context": {"slot": 1}, "value": {"blockhash": BLOCKHASH, "lastValidBlockHeight": 120}}
            if method == "getBlockHeight":
                return 100
            if method == "getBalance":
                return {"value": 1}
            if method == "getTokenAccountBalance":
                return {"value": {"amount": "1"}}
            raise AssertionError(f"unexpected RPC method {method}")

        def account_info(self, address):
            self.methods.append("getAccountInfo")
            if address == MINT:
                return _mint_response(TOKEN_PROGRAM)
            if address == WALLET:
                return {
                    "context": {"slot": 2},
                    "value": {
                        "owner": RAYDIUM_AMM_V4_PROGRAM, "executable": False,
                        "data": ["pool-state-fixture", "base64"],
                    },
                }
            return super().account_info(address)

        def simulate(self, tx):
            self.methods.append("simulateTransaction")
            self.simulate_calls += 1
            return {
                "context": {"slot": 457},
                "value": {
                    "err": None, "logs": ["ok"], "unitsConsumed": 1,
                    "returnData": {"programId": RAYDIUM_AMM_V4_PROGRAM,
                                   "data": [base64.b64encode((1).to_bytes(8, "little")).decode(), "base64"]},
                },
            }

    plan = {
        "intent": {
            "protocol": "raydium_amm", "action": "open", "wallet": WALLET,
            "pool": WALLET, "token_mints": [MINT], "strategy_decision_id": "decision-e3",
            "risk_verdict_id": "risk-e3", "idempotency_key": "report-e3",
            "notional_usd": 5, "slippage_bps": 75, "deadline_unix": NOW + 120,
        },
        "instructions": [{
            "program_id": RAYDIUM_AMM_V4_PROGRAM,
            "accounts": [{"pubkey": POOL, "is_writable": True}],
            "data_base64": base64.b64encode(b"\x01\x02").decode(),
            "semantic_action": "open",
        }],
        "preflight": {
            "quote_ok": True, "quote": {"amount_out": 1},
            "basis_ok": True, "basis": {"bps": 1},
            "wallet_balance_ok": True, "wallet_balance": {"lamports": 1},
            "token_accounts": [MINT],
        },
    }
    rpc = RunnerRpc()
    out = tmp_path / "SOLANA_OPEN_DRY_RUN.json"
    report = run_dry_run_report(plan, out, rpc, now_unix=NOW)
    assert out.exists() and report["signed"] is False and report["broadcast_count"] == 0
    assert report["preflight_all_pass"] is True and report["mint_semantics"][0]["decimals"] == 6
    assert rpc.methods.count("simulateTransaction") == 2
    assert {"getBalance", "getTokenAccountBalance"}.issubset(rpc.methods)
    assert "sendTransaction" not in rpc.methods


def test_cli_runner_rejects_plan_claimed_wallet_balance_when_rpc_reports_zero(tmp_path):
    class ZeroBalanceRpc(FakeRpc):
        def call(self, method, _params):
            if method == "getGenesisHash":
                return "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
            if method == "getLatestBlockhash":
                return {"value": {"blockhash": BLOCKHASH, "lastValidBlockHeight": 120}}
            if method == "getBlockHeight":
                return 100
            if method == "getBalance":
                return {"value": 0}
            raise AssertionError(method)

        def account_info(self, address):
            if address == MINT:
                return _mint_response(TOKEN_PROGRAM)
            if address == WALLET:
                return {"context": {"slot": 1}, "value": {
                    "owner": RAYDIUM_AMM_V4_PROGRAM, "executable": False, "data": ["state", "base64"],
                }}
            return super().account_info(address)

        def simulate(self, _tx):
            return {"value": {"err": None, "returnData": {
                "data": [base64.b64encode((1).to_bytes(8, "little")).decode(), "base64"],
            }}}

    plan = {
        "intent": {"protocol": "raydium_amm", "action": "open", "wallet": WALLET, "pool": WALLET,
                   "token_mints": [MINT], "strategy_decision_id": "d", "risk_verdict_id": "r",
                   "idempotency_key": "zero-balance", "notional_usd": 5, "slippage_bps": 1,
                   "deadline_unix": NOW + 120},
        "instructions": [{"program_id": RAYDIUM_AMM_V4_PROGRAM, "accounts": [],
                          "data_base64": base64.b64encode(b"x").decode(), "semantic_action": "open"}],
        # This assertion is intentionally ignored by the runner.
        "preflight": {"wallet_balance_ok": True, "wallet_balance": {"lamports": 999}},
    }
    report = run_dry_run_report(plan, tmp_path / "zero.json", ZeroBalanceRpc(), now_unix=NOW)
    assert report["preflight"]["wallet_balance"] is False
    assert report["preflight_all_pass"] is False
    assert report["signed"] is False and report["broadcast_count"] == 0


def test_exit_only_rejects_self_reported_reducing_swap_when_actual_direction_adds_exposure(tmp_path):
    source_account = "So11111111111111111111111111111111111111112"
    destination_account = "SysvarRent111111111111111111111111111111111"
    accounts = tuple([AccountMeta(WALLET)] * 15 + [
        AccountMeta(source_account), AccountMeta(destination_account),
    ])
    swap = Instruction(RAYDIUM_AMM_V4_PROGRAM, accounts, b"\x09", Action.SWAP)
    rpc = FakeRpc()
    rpc.account_responses[source_account] = {"value": {"data": {"parsed": {
        "type": "account", "info": {"mint": TOKEN_2022_PROGRAM},
    }}}}
    rpc.account_responses[destination_account] = {"value": {"data": {"parsed": {
        "type": "account", "info": {"mint": MINT},
    }}}}
    increasing = intent(
        Action.SWAP, reduces_risk=True, position_mint=MINT,
        token_mints=(MINT, TOKEN_2022_PROGRAM), idempotency_key="direction-adds",
    )
    with pytest.raises(PolicyRejected, match="direction increases"):
        dry_run(
            intent=increasing, preflight=preflight(), instructions=[swap], recent_blockhash=BLOCKHASH,
            last_valid_block_height=120, current_block_height=100, rpc=rpc,
            policy=ExecutionPolicy(allowed_pools=frozenset({POOL}),
                                   allowed_mints=frozenset({MINT, TOKEN_2022_PROGRAM})),
            ledger=Ledger(tmp_path / "ledger.jsonl"), state=ExecutionState.EXIT_ONLY, now=lambda: NOW,
        )
