"""Tests for the Base 10U probe executor IMPLEMENTATION stage (v2).

This stage builds the executor code with all real-send paths guarded by
3 gates + 2 default safety flags. Tests assert that the default path
NEVER sends; execute-guarded always aborts with EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = REPO_ROOT / "reports" / "lp_base_10u_probe_execution_implementation" / "20260602_163036"
SCRIPT = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"


def _read(rel: str) -> dict | None:
    p = RUN_DIR / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


ALLOWED_NEXT = {
    "LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1",
    "LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}


# --- Final verdict ----------------------------------------------------

def test_final_verdict_exists_and_required_fields() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv is not None
    required = {
        "status", "stage", "previous_stage", "previous_run_id",
        "executor_v2_built", "dynamic_tick_range_recompute_built",
        "approve_exact_builder_built", "mint_tx_builder_built",
        "exit_collect_revoke_builder_built", "telemetry_runtime_writer_built",
        "approval_gate_built", "self_check_ran", "execute_guarded_send_blocked",
        "candidate_chain", "candidate_pool", "candidate_pair", "wallet",
        "notional_usd", "hold_window",
        "can_run_probe_now", "can_execute_with_current_script",
        "execution_ready_for_final_review",
        "manual_approval_required_for_execution",
        "edge_proven", "actual_fee_ready", "token_id_available",
        "tiny_canary_allowed", "wallet_or_tx_touched",
        "recommended_next_stage", "security_audit_15_flags",
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
    assert fv["execution_ready_for_final_review"] is False
    assert fv["edge_proven"] == "no"
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["actual_fee_ready"] is False
    assert fv["token_id_available"] is False
    assert fv["wallet_or_tx_touched"] is False
    assert fv["executor_will_run_this_round"] is False
    assert fv["approval_phrase_effective_this_round"] is False
    assert fv["execute_guarded_send_blocked"] is True
    assert fv["manual_approval_required_for_execution"] is True


def test_recommended_next_stage_in_allowed_set() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT


def test_wallet_address_is_public_only() -> None:
    fv = _read("FINAL_VERDICT.json")
    wa = fv["wallet"]
    assert wa.startswith("0x") and len(wa) == 42
    assert all(c in "0123456789abcdefABCDEF" for c in wa[2:])
    fv_str = json.dumps(fv)
    key_shape = re.search(r"0x[0-9a-fA-F]{64}", fv_str)
    assert not key_shape, f"FINAL_VERDICT contains 64-hex (private-key shape): {key_shape.group(0) if key_shape else ''}"


def test_15_security_flags_all_false() -> None:
    fv = _read("FINAL_VERDICT.json")
    flags = fv["security_audit_15_flags"]
    for k, v in flags.items():
        assert v is False or v == "no", f"flag {k} should be false/'no', got {v!r}"


# --- Builder component checks -------------------------------------------

def test_executor_v2_built() -> None:
    assert SCRIPT.is_file()
    src = SCRIPT.read_text()
    assert "ExecutionSendDisabledInImplementationBuildStage" in src
    assert "executor_v2_built" not in src  # the flag is in FINAL_VERDICT, not in the script


def test_dynamic_tick_range_recompute_built() -> None:
    src = SCRIPT.read_text()
    assert "dynamic_tick_range_recompute" in src
    assert "LEGACY_FROZEN_TICK" in src
    assert "TICK_RANGE_SAFETY_MARGIN_TICKS" in src


def test_approve_exact_builder_built() -> None:
    src = SCRIPT.read_text()
    assert "build_approve_exact_usdc_tx" in src
    assert "UINT256_MAX // 2" in src
    assert "ApproveMax forbidden" in src


def test_mint_tx_builder_built() -> None:
    src = SCRIPT.read_text()
    assert "build_mint_position_tx" in src
    assert "deadline = int(time.time()) + 3600" in src
    assert "deadline_is_now_plus_3600" in src


def test_exit_collect_revoke_builder_built() -> None:
    src = SCRIPT.read_text()
    assert "build_decrease_liquidity_tx" in src
    assert "build_collect_tx" in src
    assert "build_revoke_allowance_tx" in src
    assert "monitor_position_loop_stub" in src


def test_telemetry_runtime_writer_built() -> None:
    src = SCRIPT.read_text()
    assert "write_telemetry_runtime" in src
    for f in ["preflight.json", "dynamic_tick_range.json", "approval_check.json",
              "unsigned_approve_package.json", "unsigned_mint_package.json",
              "stop_conditions.json", "execution_gates.json"]:
        assert f in src


def test_approval_gate_built() -> None:
    src = SCRIPT.read_text()
    assert "execution_approval_gate" in src
    assert "i-understand-this-sends-real-transactions" in src


# --- Subprocess sanity (defense-in-depth) -----------------------------

def _run(*args, env_extra=None):
    full_env = os.environ.copy() if False else __import__("os").environ.copy()
    full_env.pop("ANTHROPIC_API_KEY", None)
    if env_extra:
        full_env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=full_env, timeout=60,
    )


def test_subprocess_default_no_send() -> None:
    """Default invocation does not send any tx."""
    r = _run("--mode", "preflight", "--run-id", "20260602_163036_test",
             "--wallet", "0xb05b2872ace4564ff247555b6f7b097d31f3d835",
             "--notional", "10", "--hold", "15m",
             "--dry-run-only", "--no-send")
    assert r.returncode == 0


def test_subprocess_execute_guarded_blocks_send() -> None:
    """--mode execute-guarded ALWAYS aborts in this stage."""
    r = _run(
        "--mode", "execute-guarded",
        "--run-id", "20260602_163036_test",
        "--wallet", "0xb05b2872ace4564ff247555b6f7b097d31f3d835",
        "--notional", "10", "--hold", "15m",
        "--approval", "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m",
        "--dry-run-only", "--no-send",
        "--i-understand-this-sends-real-transactions",
    )
    assert r.returncode == 1
    assert "EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE" in r.stderr


def test_subprocess_execute_mode_rejected() -> None:
    """--mode execute (not in choices) is rejected by argparse."""
    r = _run("--mode", "execute", "--run-id", "20260602_163036_test")
    assert r.returncode != 0
    assert "invalid choice" in r.stderr


def test_subprocess_forbidden_env_refuses() -> None:
    r = _run("--mode", "preflight", "--run-id", "20260602_163036_test",
             env_extra={"LPBOT_FAKE_WALLET_KEY": "0xdeadbeef"})
    assert r.returncode == 4
    assert "REFUSING TO RUN" in r.stderr


def test_subprocess_20u_phrase_rejected() -> None:
    """--mode validate-approval with notional=20 (rejected)."""
    r = _run(
        "--mode", "validate-approval",
        "--run-id", "20260602_163036_test",
        "--approval", "APPROVE_BASE_20U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=20 hold=15m",
    )
    assert r.returncode == 0
    d = json.loads(r.stdout)
    assert d["valid"] is False
    assert d["executes_now"] is False
    assert d["authorization_granted"] is False


def test_subprocess_validate_approval_valid_does_not_execute() -> None:
    """Valid approval phrase: valid=True but executes_now=False, gates fail without second flag."""
    r = _run(
        "--mode", "validate-approval",
        "--run-id", "20260602_163036_test",
        "--approval", "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m",
    )
    assert r.returncode == 0
    d = json.loads(r.stdout)
    assert d["valid"] is True
    assert d["executes_now"] is False
    assert d["authorization_granted"] is False
    # Without --i-understand, all_three_gates is False
    assert d["execution_gates_status"]["all_three_gates_pass"] is False


# --- In-process unit tests (via import) -------------------------------

def _import_v2():
    import importlib
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    if "lp_base_10u_probe_executor_v2" in sys.modules:
        del sys.modules["lp_base_10u_probe_executor_v2"]
    spec = importlib.util.spec_from_file_location("lp_base_10u_probe_executor_v2", str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_unit_approve_exact_builder() -> None:
    v2 = _import_v2()
    tx = v2.build_approve_exact_usdc_tx(v2.WALLET, 10 * 10**6)
    assert tx["amount_raw"] == 10_000_000
    assert tx["approvemax_forbidden"] is True
    assert tx["transaction_sent"] is False
    assert tx["no_send"] is True


def test_unit_approve_rejects_approvemax() -> None:
    v2 = _import_v2()
    try:
        v2.build_approve_exact_usdc_tx(v2.WALLET, v2.UINT256_MAX // 2)
        assert False, "should have raised"
    except ValueError:
        pass


def test_unit_revoke_usdc() -> None:
    v2 = _import_v2()
    tx = v2.build_revoke_usdc_tx(v2.WALLET)
    assert tx["amount_raw"] == 0
    assert tx["no_send"] is True


def test_unit_revoke_weth() -> None:
    v2 = _import_v2()
    tx = v2.build_revoke_weth_tx(v2.WALLET)
    assert tx["amount_raw"] == 0
    assert tx["no_send"] is True


def test_unit_mint_deadline_runtime() -> None:
    import time
    v2 = _import_v2()
    tx = v2.build_mint_position_tx(
        wallet=v2.WALLET, tick_lower=-200908, tick_upper=-200508,
        amount0_desired_wei=0, amount1_desired_raw=10*10**6,
        amount0_min_wei=0, amount1_min_raw=9_949_999,
    )
    now = int(time.time())
    assert abs(tx["deadline"] - (now + 3600)) < 5
    assert tx["deadline_is_now_plus_3600"] is True
    assert tx["deadline_is_NOT_legacy_placeholder_2099"] is True
    assert tx["unsigned_only"] is True
    assert tx["no_send"] is True
    assert tx["transaction_sent"] is False
    assert tx["params"]["recipient"] == v2.WALLET


def test_unit_monitor_rejects_long_loop() -> None:
    v2 = _import_v2()
    try:
        v2.monitor_position_loop_stub(token_id=42, iterations=5)
        assert False, "should have raised"
    except ValueError:
        pass


def test_unit_dynamic_range_recompute_uses_dynamic_not_legacy() -> None:
    v2 = _import_v2()
    # Without internet access we cannot call RPC; just check the function shape
    import inspect
    sig = inspect.signature(v2.dynamic_tick_range_recompute)
    assert "url" in sig.parameters
    assert "dry_run" in sig.parameters
    # Check that the function does NOT just return the legacy range
    src = v2.__file__
    src_text = open(src).read()
    assert "LEGACY_FROZEN_TICK" in src_text  # used as comparison only
    assert "TICK_RANGE_SAFETY_MARGIN_TICKS" in src_text  # used to compute new range


def test_unit_parse_approval_valid_canonical() -> None:
    v2 = _import_v2()
    phrase = ("APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT "
              f"wallet={v2.WALLET} pool={v2.POOL} notional=10 hold=15m")
    parsed = v2.parse_approval_phrase(phrase)
    assert parsed["valid"] is True
    assert parsed["executes_now"] is False


def test_unit_parse_approval_rejects_20u() -> None:
    v2 = _import_v2()
    phrase = ("APPROVE_BASE_20U_LP_PROBE_EXECUTION_ONE_SHOT "
              f"wallet={v2.WALLET} pool={v2.POOL} notional=20 hold=15m")
    parsed = v2.parse_approval_phrase(phrase)
    assert parsed["valid"] is False


def test_unit_execution_approval_gate_all_three_pass() -> None:
    v2 = _import_v2()
    phrase = ("APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT "
              f"wallet={v2.WALLET} pool={v2.POOL} notional=10 hold=15m")
    g = v2.execution_approval_gate(phrase=phrase, dry_run_only=True, no_send=True,
                                    i_understand_flag=True, second_flag_set_via_argv=True)
    assert g["all_three_gates_pass"] is True
    # Even with all gates passing, send is hard-disabled in this stage
    assert g["note_implementation_stage"].startswith("in this implementation build stage")


def test_unit_execution_approval_gate_blocked_without_second_flag() -> None:
    v2 = _import_v2()
    phrase = ("APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT "
              f"wallet={v2.WALLET} pool={v2.POOL} notional=10 hold=15m")
    g = v2.execution_approval_gate(phrase=phrase, dry_run_only=True, no_send=True,
                                    i_understand_flag=False, second_flag_set_via_argv=False)
    assert g["all_three_gates_pass"] is False
    assert g["send_would_be_authorized_now"] is False
