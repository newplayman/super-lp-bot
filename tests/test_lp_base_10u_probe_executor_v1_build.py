"""Tests for the Base 10U probe executor skeleton (build stage).

This stage builds the executor SKELETON. The tests assert:
  - default mode cannot execute
  - --mode execute is rejected
  - --mode execute-disabled exits non-zero with EXECUTION_DISABLED_IN_BUILD_STAGE
  - no private key env names are used
  - no signer construction
  - no eth_sendTransaction / eth_sendRawTransaction
  - no approve/mint/collect/swap execution
  - approval phrase parser accepts only the canonical 10U/15m phrase
  - rejects 20U, 30m, wrong wallet, wrong pool, dangerous words
  - stubs raise EXECUTION_DISABLED_IN_BUILD_STAGE
  - preflight writes only local reports
  - final verdict allowed next stages only
  - can_run_probe_now remains false
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = REPO_ROOT / "reports" / "lp_base_10u_probe_execution_script_build" / "20260602_135824"
SCRIPT = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v1.py"


def _read(rel: str) -> dict | None:
    p = RUN_DIR / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


ALLOWED_NEXT = {
    "LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1",
    "LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}


# --- Import the script as a module to inspect internals ----------------

def _import_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import importlib
    mod_name = "lp_base_10u_probe_executor_v1"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _import_module()


# --- Final verdict ----------------------------------------------------

def test_final_verdict_exists_and_required_fields() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv is not None
    required = {
        "status", "stage", "previous_stage", "previous_run_id",
        "executor_script_built", "preflight_mode_built", "print_unsigned_mode_built",
        "approval_parser_built", "telemetry_writer_built", "stop_condition_engine_built",
        "execution_stubs_disabled", "self_check_ran",
        "candidate_chain", "candidate_pool", "candidate_pair", "wallet",
        "notional_usd", "hold_window",
        "can_run_probe_now", "can_execute_with_current_script",
        "execution_requires_fresh_user_approval",
        "edge_proven", "actual_fee_ready", "token_id_available",
        "tiny_canary_allowed", "wallet_or_tx_touched",
        "recommended_next_stage", "spec_phase_artifact_counts",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing fields: {missing}"


def test_final_verdict_status_pass() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["status"] == "PASS"


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["can_execute_with_current_script"] is False
    assert fv["edge_proven"] == "no"
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["actual_fee_ready"] is False
    assert fv["token_id_available"] is False
    assert fv["wallet_or_tx_touched"] is False
    assert fv["execution_requires_fresh_user_approval"] is True


def test_executor_built_but_will_not_run() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["executor_script_built"] is True
    # The script was built but the executor does NOT run this round
    assert fv["executor_will_run_this_round"] is False
    assert fv["approval_phrase_effective_this_round"] is False


def test_recommended_next_stage_in_allowed_set() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT


def test_recommended_next_stage_is_review_not_execute() -> None:
    fv = _read("FINAL_VERDICT.json")
    bad = {"LP_BASE_10U_LP_PROBE_EXECUTE", "probe_execution",
           "canary", "live", "paper", "GO", "SHIP_IT", "PROCEED"}
    assert fv["recommended_next_stage"] not in bad


def test_wallet_address_is_public_only() -> None:
    fv = _read("FINAL_VERDICT.json")
    wa = fv["wallet"]
    assert wa.startswith("0x") and len(wa) == 42
    assert all(c in "0123456789abcdefABCDEF" for c in wa[2:])
    # Ensure the wallet field itself is a pure address, not embedded in a "key" structure
    assert "0x" + wa[2:] == wa  # identity sanity
    # The artifact MAY mention these terms in prose about forbidden env names / safety,
    # but must NOT contain a literal private key (64 hex after 0x).
    # Check: scan for any 0x + 64-hex substring (a real key shape).
    fv_str = json.dumps(fv)
    key_shape = re.search(r"0x[0-9a-fA-F]{64}", fv_str)
    assert not key_shape, f"FINAL_VERDICT contains a 64-hex string that looks like a private key: {key_shape.group(0)}"


# --- Approval phrase parser (unit tests on imported function) ---------

VALID_PHRASE = "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m"


def test_phrase_parser_accepts_canonical_only(mod) -> None:
    r = mod.parse_approval_phrase(VALID_PHRASE)
    assert r["valid"] is True
    assert r["parsed"]["wallet"] == "0xb05b2872ace4564ff247555b6f7b097d31f3d835"
    assert r["parsed"]["pool"] == "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38"
    assert r["parsed"]["notional"] == 10
    assert r["parsed"]["hold"] == "15m"
    assert r.get("executes_now") is False


def test_phrase_parser_rejects_20u(mod) -> None:
    bad = VALID_PHRASE.replace(" notional=10 ", " notional=20 ")
    r = mod.parse_approval_phrase(bad)
    assert r["valid"] is False


def test_phrase_parser_rejects_30m(mod) -> None:
    bad = VALID_PHRASE.replace(" hold=15m", " hold=30m")
    r = mod.parse_approval_phrase(bad)
    assert r["valid"] is False
    assert "dangerous" in (r.get("reason") or "").lower() or "does not match" in (r.get("reason") or "").lower()


def test_phrase_parser_rejects_wrong_wallet(mod) -> None:
    bad = VALID_PHRASE.replace(
        "0xb05b2872ace4564ff247555b6f7b097d31f3d835",
        "0xABCDEF0123456789ABCDEF0123456789ABCDEF01",
    )
    r = mod.parse_approval_phrase(bad)
    assert r["valid"] is False


def test_phrase_parser_rejects_wrong_pool(mod) -> None:
    bad = VALID_PHRASE.replace(
        "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38",
        "0x9c087eb773291e50cf6c6a90ef0f4500e349b903",
    )
    r = mod.parse_approval_phrase(bad)
    assert r["valid"] is False


def test_phrase_parser_rejects_dangerous_words(mod) -> None:
    # "PROBE EXEC" (EXEC as a separate word) - should reject via dangerous word
    bad = "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT EXEC wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m"
    r = mod.parse_approval_phrase(bad)
    assert r["valid"] is False


def test_phrase_parser_rejects_placeholder(mod) -> None:
    bad = "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xUSER_PROVIDED_WALLET_ADDRESS pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m"
    r = mod.parse_approval_phrase(bad)
    assert r["valid"] is False


def test_phrase_parser_rejects_empty(mod) -> None:
    assert mod.parse_approval_phrase("")["valid"] is False
    assert mod.parse_approval_phrase("   ")["valid"] is False
    assert mod.parse_approval_phrase(None)["valid"] is False  # type: ignore


def test_phrase_parser_rejects_no_prefix(mod) -> None:
    r = mod.parse_approval_phrase("GO")
    assert r["valid"] is False


# --- Execution stubs raise --------------------------------------------

def test_approve_exact_usdc_raises(mod) -> None:
    with pytest.raises(mod.ExecutionDisabledInBuildStage) as e:
        mod.approve_exact_usdc()
    assert "EXECUTION_DISABLED_IN_BUILD_STAGE" in str(e.value)


def test_approve_exact_weth_raises(mod) -> None:
    with pytest.raises(mod.ExecutionDisabledInBuildStage):
        mod.approve_exact_weth()


def test_mint_position_raises(mod) -> None:
    with pytest.raises(mod.ExecutionDisabledInBuildStage):
        mod.mint_position()


def test_monitor_position_raises(mod) -> None:
    with pytest.raises(mod.ExecutionDisabledInBuildStage):
        mod.monitor_position()


def test_decrease_liquidity_raises(mod) -> None:
    with pytest.raises(mod.ExecutionDisabledInBuildStage):
        mod.decrease_liquidity()


def test_collect_fees_raises(mod) -> None:
    with pytest.raises(mod.ExecutionDisabledInBuildStage):
        mod.collect_fees()


def test_revoke_allowance_raises(mod) -> None:
    with pytest.raises(mod.ExecutionDisabledInBuildStage):
        mod.revoke_allowance()


# --- Forbid signing/sending via source inspection ----------------------

def test_script_source_has_no_eth_send_transaction() -> None:
    src = SCRIPT.read_text()
    # Allow "eth_sendTransaction" only inside error messages / documentation
    # but not as a function call.
    assert ".send_transaction(" not in src
    assert ".sendTransaction(" not in src
    assert ".send_raw_transaction(" not in src
    assert ".sendRawTransaction(" not in src


def test_script_source_has_no_signer_construction() -> None:
    src = SCRIPT.read_text()
    # Heuristic: no Account.from_key, no LocalAccount, no keystore loading
    for forbidden in ["Account.from_key", "LocalAccount", "load_keyfile", "load_keystore",
                      "from_key", "from_mnemonic", "from_seed"]:
        assert forbidden not in src, f"script contains forbidden term: {forbidden!r}"


def test_script_source_has_no_approve_execution_path() -> None:
    """The script may ENCODE approve as data (for print-unsigned), but it must
    never call .transact() or .build_transaction() on the approve contract.
    """
    src = SCRIPT.read_text()
    assert ".transact(" not in src
    assert ".build_transaction(" not in src
    assert "w3.eth.send" not in src


def test_script_source_has_no_private_key_env_lookup() -> None:
    src = SCRIPT.read_text()
    # Must not look up PRIVATE_KEY / MNEMONIC / SEED_PHRASE / KEYSTORE
    for forbidden in ["os.environ[\"PRIVATE_KEY\"]", "os.environ['PRIVATE_KEY'",
                      "os.environ[\"MNEMONIC\"]", "os.environ['MNEMONIC'",
                      "os.environ[\"SEED\"]", "os.environ['SEED'",
                      "os.environ[\"KEYSTORE\"]", "os.environ['KEYSTORE'",
                      "os.environ[\"DATABASE_URL\"]", "os.environ['DATABASE_URL'",
                      "os.environ[\"POSTGRES_DSN\"]", "os.environ['POSTGRES_DSN'"]:
        assert forbidden not in src, f"script looks up forbidden env: {forbidden!r}"


# --- Mode behavior via subprocess --------------------------------------

def _run(*args, env_extra=None):
    full_env = os.environ.copy()
    # Force-include a placeholder env var to ensure the safety check does not false-positive
    full_env.pop("ANTHROPIC_API_KEY", None)  # remove potential block
    if env_extra:
        full_env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=full_env, timeout=120,
    )


def test_subprocess_print_unsigned_works() -> None:
    r = _run("--mode", "print-unsigned", "--run-id", "20260602_test")
    assert r.returncode == 0
    d = json.loads(r.stdout)
    assert d["unsigned_only"] is True
    assert d["no_signature"] is True
    assert d["no_send"] is True
    assert d["execution_not_authorized"] is True


def test_subprocess_validate_approval_valid_works() -> None:
    r = _run("--mode", "validate-approval",
             "--approval", VALID_PHRASE,
             "--run-id", "20260602_test")
    assert r.returncode == 0
    d = json.loads(r.stdout)
    assert d["valid"] is True
    assert d["executes_now"] is False
    assert d["authorization_granted"] is False


def test_subprocess_execute_disabled_exits_nonzero() -> None:
    r = _run("--mode", "execute-disabled", "--run-id", "20260602_test")
    assert r.returncode != 0
    d = json.loads(r.stdout)
    assert d["execution_disabled_in_build_stage"] is True
    assert d["error"] == "EXECUTION_DISABLED_IN_BUILD_STAGE"


def test_subprocess_execute_rejected() -> None:
    r = _run("--mode", "execute", "--run-id", "20260602_test")
    # argparse rejects 'execute' as not in allowed choices
    assert r.returncode != 0
    assert "invalid choice: 'execute'" in r.stderr or "invalid choice" in r.stderr


def test_subprocess_execute_flag_rejected() -> None:
    r = _run("--mode", "preflight", "--execute", "--run-id", "20260602_test")
    assert r.returncode == 3  # custom REJECTED exit code


def test_subprocess_forbidden_env_var_refuses() -> None:
    r = _run("--mode", "preflight", "--run-id", "20260602_test",
             env_extra={"LPBOT_FAKE_WALLET_KEY": "0xdeadbeef"})
    # LPBOT_FAKE_WALLET_KEY matches ^.*WALLET_KEY$
    assert r.returncode == 4
    assert "REFUSING TO RUN" in r.stderr or "forbidden env var" in r.stderr


# --- Stop condition engine --------------------------------------------

def test_stop_engine_passes_for_healthy_preflight(mod) -> None:
    pre = {
        "chain_id": 8453,
        "eth_native_wei": 10**14,  # 1e-4 ETH
        "usdc_balance_raw": 50 * 10**6,
        "weth_balance_raw": 10**16,
        "usdc_allowance_raw": 0,
        "weth_allowance_raw": 0,
        "current_tick": -200443,
        "current_liquidity": 10**17,
        "mint_estimate_gas": 180000,
        "quoter_v2_weth_to_usdc_ok": True,
        "quoter_v2_usdc_to_weth_ok": True,
        "quote_slippage_pct_usdc_to_weth": 0.5,
        "rpc_instability_detected": False,
    }
    r = mod.evaluate_stop_conditions(pre)
    assert r["overall_status"] == "PASS"
    assert r["any_triggered"] is False


def test_stop_engine_fails_on_chain_id_mismatch(mod) -> None:
    pre = {"chain_id": 1, "eth_native_wei": 10**14, "usdc_balance_raw": 50 * 10**6,
           "weth_balance_raw": 0, "usdc_allowance_raw": 0, "weth_allowance_raw": 0,
           "current_tick": -200443, "current_liquidity": 10**17, "mint_estimate_gas": 180000,
           "quoter_v2_weth_to_usdc_ok": True, "quoter_v2_usdc_to_weth_ok": True,
           "quote_slippage_pct_usdc_to_weth": 0.5, "rpc_instability_detected": False}
    r = mod.evaluate_stop_conditions(pre)
    assert r["overall_status"] == "FAIL"
    assert r["stops"]["stop_chain_id_mismatch"]["triggered"] is True


def test_stop_engine_fails_on_low_gas(mod) -> None:
    pre = {"chain_id": 8453, "eth_native_wei": 1000, "usdc_balance_raw": 50 * 10**6,
           "weth_balance_raw": 0, "usdc_allowance_raw": 0, "weth_allowance_raw": 0,
           "current_tick": -200443, "current_liquidity": 10**17, "mint_estimate_gas": 180000,
           "quoter_v2_weth_to_usdc_ok": True, "quoter_v2_usdc_to_weth_ok": True,
           "quote_slippage_pct_usdc_to_weth": 0.5, "rpc_instability_detected": False}
    r = mod.evaluate_stop_conditions(pre)
    assert r["overall_status"] == "FAIL"
    assert r["stops"]["stop_gas_balance_below_threshold"]["triggered"] is True


def test_stop_engine_fails_on_low_liquidity(mod) -> None:
    pre = {"chain_id": 8453, "eth_native_wei": 10**14, "usdc_balance_raw": 50 * 10**6,
           "weth_balance_raw": 0, "usdc_allowance_raw": 0, "weth_allowance_raw": 0,
           "current_tick": -200443, "current_liquidity": 10**10, "mint_estimate_gas": 180000,
           "quoter_v2_weth_to_usdc_ok": True, "quoter_v2_usdc_to_weth_ok": True,
           "quote_slippage_pct_usdc_to_weth": 0.5, "rpc_instability_detected": False}
    r = mod.evaluate_stop_conditions(pre)
    assert r["overall_status"] == "FAIL"
    assert r["stops"]["stop_pool_liquidity_drop"]["triggered"] is True


# --- Cross-doc consistency -------------------------------------------

def test_input_audit_proceed() -> None:
    ia = _read("input_evidence_audit.json")
    assert ia is not None
    assert ia["proceed_to_phase_C"] is True
    must_not = "\n".join(ia["this_round_must_not"]).lower()
    for needle in ["private key", "signer", "eth_sendtransaction", "eth_sendrawtransaction",
                   "approve", "mint", "live", "canary", "paper", "auto-bridge", "auto-swap"]:
        assert needle in must_not


def test_candidate_freeze_consistent_with_final_verdict() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["candidate_pool"] == "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38"
    assert fv["notional_usd"] == 10
    assert fv["hold_window"] == "15m"
    assert fv["wallet"] == "0xb05b2872ace4564ff247555b6f7b097d31f3d835"


def test_executor_self_check_11_cases() -> None:
    sc = _read("executor_self_check.json")
    assert sc is not None
    assert sc["self_check_summary"]["all_4_modes_functional"] is True
    assert sc["self_check_summary"]["execute_rejected_at_argparse"] is True
    assert sc["self_check_summary"]["execute_disabled_exits_nonzero"] is True
    assert sc["self_check_summary"]["approval_parser_rejects_20U_30m_wrong_wallet_wrong_pool_placeholders_dangerous_words"] is True
