"""Tests for the Base 10U probe armed runner v1 + readiness monitor v1.

Properties asserted:
  * armed runner v1 has the 6 expected modes
  * execute-armed mode hard-aborts with the right message and exit code 1
  * v1 imports v2 (not copy-paste); v2 still raises its hard-disable
  * armed runner defaults: no-send=true, dry-run-only=true
  * armed runner rejects wrong wallet/notional/hold in main()
  * monitor script has --finalize and rejects wrong wallet
  * v1 contains no signer/tx-construction call sites
  * FINAL_VERDICT can_run_probe_now/execution_allowed_now/tiny_canary_allowed
    are all locked to safe values
  * recommended_next_stage is WAIT_FOR_MONITOR_COMPLETION
  * allowed_next_stages contains the right four
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260602_193517"
REPORT_DIR = REPO_ROOT / "reports" / "lp_base_10u_probe_overnight_armed_runner" / RUN_ID

ARMED_V1 = REPO_ROOT / "scripts" / "lp_base_10u_probe_armed_runner_v1.py"
MONITOR_V1 = REPO_ROOT / "scripts" / "lp_base_10u_probe_readiness_monitor_v1.py"
V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"

ALLOWED_NEXT_STAGES = {
    "WAIT_FOR_MONITOR_COMPLETION",
    "LP_BASE_10U_PROBE_FINAL_OPERATOR_AUTHORIZATION_REVIEW_V1",
    "LP_BASE_10U_PROBE_ARMED_RUNNER_BUILD_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}
FORBIDDEN_NEXT_STAGES = {
    "EXECUTE_NOW",
    "FIRST_EXECUTION_RUN_V1",
    "MINT_NOW",
    "SEND_NOW",
    "LP_BASE_10U_PROBE_LIVE",
    "LP_BASE_10U_PROBE_CANARY",
    "LP_BASE_10U_PROBE_PAPER",
}


def _read_json(rel: str) -> dict | None:
    p = REPORT_DIR / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


# --- FINAL_VERDICT.json -----------------------------------------------

def test_final_verdict_exists() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv is not None
    assert fv["stage"] == "LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1"


def test_final_verdict_status_running_or_pass() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["status"] in ("RUNNING", "PASS")


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["execution_allowed_now"] is False
    assert fv["send_hard_disable_still_active"] is True
    assert fv["default_no_send"] is True
    assert fv["default_dry_run_only"] is True
    assert fv["execute_armed_cannot_send_this_stage"] is True
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["wallet_or_tx_touched"] is False


def test_final_verdict_armed_runner_built() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["armed_runner_built"] is True
    assert fv["armed_runner_file"] == "scripts/lp_base_10u_probe_armed_runner_v1.py"
    assert fv["v2_modified_by_this_stage"] is False


def test_final_verdict_monitor_started() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["monitor_started"] is True
    assert "readiness_monitor" in fv["monitor_session_name"]
    assert fv["monitor_first_checkpoint_seen"] is True


def test_final_verdict_recommended_next_stage_wait_for_monitor() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] == "WAIT_FOR_MONITOR_COMPLETION"


def test_final_verdict_recommended_next_stage_in_allowed_only() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_final_verdict_recommended_next_stage_is_not_execution() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    rns = fv["recommended_next_stage"]
    assert rns not in FORBIDDEN_NEXT_STAGES
    for sub in ["EXECUTE_NOW", "FIRST_EXECUTION_RUN", "MINT_NOW", "SEND_NOW",
                "LIVE", "CANARY", "PAPER"]:
        assert sub not in rns, f"recommended_next_stage {rns!r} contains forbidden substring {sub!r}"


def test_final_verdict_no_64hex_private_key_shape() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    fv_str = json.dumps(fv)
    m = re.search(r"0x[0-9a-fA-F]{64}", fv_str)
    assert not m


def test_final_verdict_signer_path_not_called() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["signer_path_not_called"] is True
    assert fv["wallet_client_not_created"] is True
    assert fv["private_key_loaded"] is False
    assert fv["mnemonic_loaded"] is False
    assert fv["keystore_loaded"] is False


def test_final_verdict_no_tx_called() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    for k in [
        "eth_sendTransaction_called",
        "eth_sendRawTransaction_called",
        "approve_executed", "mint_executed", "decrease_executed",
        "collect_executed", "burn_executed", "swap_executed",
    ]:
        assert fv[k] is False, f"final_verdict {k} is not False: {fv[k]!r}"


def test_final_verdict_no_live_canary_paper() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    for k in ["live_started", "canary_started", "paper_started"]:
        assert fv[k] is False
    assert fv["any_funds_spent"] is False
    assert fv["production_positions_written"] is False
    assert fv["shadow_tables_overwritten"] is False
    assert fv["strategy_execution_path_modified"] is False


# --- All artifacts present -------------------------------------------

@pytest.mark.parametrize("name", [
    "INPUT_EVIDENCE_AUDIT_CN.md", "input_evidence_audit.json",
    "ARMED_RUNNER_BUILD_CN.md", "armed_runner_build.json",
    "ARMED_RUNNER_GATE_AUDIT_CN.md", "armed_runner_gate_audit.json",
    "ARMED_RUNNER_PREFLIGHT_SMOKE_CN.md", "armed_runner_preflight_smoke.json",
    "MONITOR_START_HEALTHCHECK_CN.md", "monitor_start_healthcheck.json",
    "MONITOR_FINALIZE_FLOW_CN.md", "MONITOR_FINALIZE_SCHEMA_CN.md",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = REPORT_DIR / name
    assert p.is_file(), f"missing: {p}"
    assert p.stat().st_size > 0


# --- armed runner v1 source code assertions ---------------------------

def test_armed_runner_v1_file_exists() -> None:
    assert ARMED_V1.is_file()
    assert ARMED_V1.stat().st_size > 0


def test_armed_runner_v1_imports_v2() -> None:
    """v1 must import v2 (no copy-paste)."""
    src = ARMED_V1.read_text()
    assert "import lp_base_10u_probe_executor_v2 as v2" in src


def test_armed_runner_v1_six_modes() -> None:
    src = ARMED_V1.read_text()
    for mode in ["status", "preflight", "print-unsigned",
                 "validate-approval", "monitor-readonly", "execute-armed"]:
        assert f'"{mode}"' in src, f"mode {mode!r} not in armed runner v1"


def test_armed_runner_v1_execute_armed_hard_aborts() -> None:
    """execute-armed in this stage must hard-abort."""
    proc = subprocess.run(
        [sys.executable, str(ARMED_V1),
         "--mode", "execute-armed",
         "--run-id", RUN_ID,
         "--wallet", "0xb05b2872ace4564ff247555b6f7b097d31f3d835",
         "--notional", "10",
         "--hold", "15m"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 1, f"expected exit 1, got {proc.returncode}"
    assert "EXECUTION_NOT_AUTHORIZED_IN_OVERNIGHT_BUILD_STAGE" in proc.stderr


def test_armed_runner_v1_execute_armed_with_one_shot_phrase_still_aborts() -> None:
    """Even if user supplies the one-shot phrase, execute-armed must abort."""
    one_shot = (
        "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT "
        "wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 "
        "pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 "
        "notional=10 hold=15m"
    )
    proc = subprocess.run(
        [sys.executable, str(ARMED_V1),
         "--mode", "execute-armed",
         "--run-id", RUN_ID,
         "--wallet", "0xb05b2872ace4564ff247555b6f7b097d31f3d835",
         "--notional", "10",
         "--hold", "15m",
         "--approval-phrase", one_shot],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 1
    assert "EXECUTION_NOT_AUTHORIZED_IN_OVERNIGHT_BUILD_STAGE" in proc.stderr


def test_armed_runner_v1_status_mode_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(ARMED_V1),
         "--mode", "status",
         "--run-id", RUN_ID,
         "--wallet", "0xb05b2872ace4564ff247555b6f7b097d31f3d835",
         "--notional", "10",
         "--hold", "15m"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0
    j = json.loads(proc.stdout)
    assert j["armed_runner_built"] is True
    assert j["send_hard_disable_active"] is True
    assert j["v2_self_check"]["v2_unmodified_by_this_build"] is True
    assert j["v2_self_check"]["class_defined"] is True
    assert j["v2_self_check"]["raise_site_present"] is True


def test_armed_runner_v1_rejects_wrong_wallet() -> None:
    proc = subprocess.run(
        [sys.executable, str(ARMED_V1),
         "--mode", "status",
         "--run-id", RUN_ID,
         "--wallet", "0x0000000000000000000000000000000000000001",
         "--notional", "10",
         "--hold", "15m"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 2
    assert "REJECTED: wallet" in proc.stderr


def test_armed_runner_v1_rejects_wrong_notional() -> None:
    proc = subprocess.run(
        [sys.executable, str(ARMED_V1),
         "--mode", "status",
         "--run-id", RUN_ID,
         "--wallet", "0xb05b2872ace4564ff247555b6f7b097d31f3d835",
         "--notional", "20",
         "--hold", "15m"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 2
    assert "REJECTED: notional" in proc.stderr


def test_armed_runner_v1_rejects_wrong_hold() -> None:
    proc = subprocess.run(
        [sys.executable, str(ARMED_V1),
         "--mode", "status",
         "--run-id", RUN_ID,
         "--wallet", "0xb05b2872ace4564ff247555b6f7b097d31f3d835",
         "--notional", "10",
         "--hold", "30m"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 2
    assert "REJECTED: hold" in proc.stderr


def test_armed_runner_v1_no_signer_construction() -> None:
    """v1 source must not contain signer-construction call sites."""
    src = ARMED_V1.read_text()
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "Web3(", "sign_transaction(",
           "send_raw_transaction(", "send_transaction(",
           "eth.send_transaction(", "eth.send_raw_transaction("]
    for b in bad:
        assert b not in src, f"armed_runner_v1 contains suspicious call: {b!r}"


def test_armed_runner_v1_does_not_call_v2_main_execute_guarded() -> None:
    """v1 must not invoke v2.main() with --mode execute-guarded.

    The v1 file is allowed to mention "execute-guarded" inside string
    literals (e.g. when scanning v2's source as a string for the v2 self-
    check), but it must not actually call v2.main(...) with that mode.
    The check below runs the file as Python and verifies that no call
    to v2.main with --mode execute-guarded appears as an executable
    function call.
    """
    import ast
    src = ARMED_V1.read_text()
    tree = ast.parse(src)
    # Walk all function-call nodes and confirm none is v2.main(...)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "v2" and func.attr == "main":
                    pytest.fail(f"armed_runner_v1 calls v2.main(...) at line {node.lineno}")


def test_armed_runner_v1_default_no_send_true() -> None:
    src = ARMED_V1.read_text()
    # argparse default=True for both --no-send and --dry-run-only (allow line wrap)
    import re as _re
    assert _re.search(r'add_argument\(\s*"--no-send",\s*action="store_true",\s*default=True', src), (
        "armed_runner_v1 --no-send default not True"
    )
    assert _re.search(r'add_argument\(\s*"--dry-run-only",\s*action="store_true",\s*default=True', src), (
        "armed_runner_v1 --dry-run-only default not True"
    )
    assert _re.search(r'add_argument\(\s*"--i-understand-this-sends-real-transactions",\s*action="store_true",\s*default=False', src), (
        "armed_runner_v1 --i-understand default not False"
    )


# --- monitor v1 source code assertions --------------------------------

def test_monitor_v1_file_exists() -> None:
    assert MONITOR_V1.is_file()
    assert MONITOR_V1.stat().st_size > 0


def test_monitor_v1_imports_v2() -> None:
    src = MONITOR_V1.read_text()
    assert "import lp_base_10u_probe_executor_v2 as v2" in src


def test_monitor_v1_has_finalize_flag() -> None:
    src = MONITOR_V1.read_text()
    assert '"--finalize"' in src or "'--finalize'" in src
    assert "args.finalize" in src


def test_monitor_v1_no_signer_construction() -> None:
    src = MONITOR_V1.read_text()
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "Web3(", "sign_transaction(",
           "send_raw_transaction(", "send_transaction(",
           "eth.send_transaction(", "eth.send_raw_transaction(",
           "eth_sendRawTransaction", "eth_sendTransaction"]
    for b in bad:
        assert b not in src, f"monitor_v1 contains suspicious token: {b!r}"


def test_monitor_v1_rpc_methods_used_are_readonly() -> None:
    src = MONITOR_V1.read_text()
    assert "eth_sendTransaction" not in src
    assert "eth_sendRawTransaction" not in src
    # only read-only methods referenced
    for ok in ["eth_chainId", "eth_blockNumber", "eth_getBalance",
               "eth_call", "eth_gasPrice"]:
        assert ok in src


def test_monitor_v1_rejects_wrong_wallet() -> None:
    proc = subprocess.run(
        [sys.executable, str(MONITOR_V1),
         "--run-id", RUN_ID,
         "--wallet", "0x0000000000000000000000000000000000000001",
         "--pool", "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38",
         "--notional", "10",
         "--hold", "15m",
         "--output-dir", "/tmp/__monitor_reject_test"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 2
    assert "REJECTED: wallet" in proc.stderr


# --- v2 must be unchanged (still 992 lines) ---------------------------

def test_v2_line_count_unchanged() -> None:
    """v2 must remain at 992 lines (this stage does not modify v2)."""
    assert V2.is_file()
    with V2.open() as f:
        n = sum(1 for _ in f)
    assert n == 992, f"v2 line count changed: {n}"


# --- Sweep: safety invariants stay false everywhere ------------------

def test_can_run_probe_now_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "can_run_probe_now" in data:
            assert data["can_run_probe_now"] is False, (
                f"{jf.name} has can_run_probe_now={data['can_run_probe_now']!r}"
            )


def test_tiny_canary_allowed_no_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "tiny_canary_allowed" in data:
            assert data["tiny_canary_allowed"] == "no", (
                f"{jf.name} has tiny_canary_allowed={data['tiny_canary_allowed']!r}"
            )


def test_wallet_or_tx_touched_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "wallet_or_tx_touched" in data:
            assert data["wallet_or_tx_touched"] is False, (
                f"{jf.name} has wallet_or_tx_touched={data['wallet_or_tx_touched']!r}"
            )


def test_execution_allowed_now_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "execution_allowed_now" in data:
            assert data["execution_allowed_now"] is False, (
                f"{jf.name} has execution_allowed_now={data['execution_allowed_now']!r}"
            )


def test_hard_disable_still_active_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "hard_disable_still_active" in data:
            assert data["hard_disable_still_active"] is True, (
                f"{jf.name} has hard_disable_still_active={data['hard_disable_still_active']!r}"
            )


# --- No secret-shaped strings in artifacts ---------------------------

def test_no_64hex_private_key_shape_in_any_artifact() -> None:
    """Any 0x + 64-hex value in our JSON reports is a uint256 not a private key.
    Specifically exclude known read-only uint256 fields (pool_liquidity_raw,
    pool_slot0_raw, gas_price_wei, balances, allowances, etc.) — these are
    always public RPC returns and never a secret.

    We only flag a 64-hex value that is NOT under one of those field names.
    """
    safe_uint256_fields = {
        "pool_liquidity_raw", "pool_slot0_raw", "gas_price_wei",
        "wallet_eth_wei", "usdc_balance_raw", "weth_balance_raw",
        "usdc_allowance_raw", "weth_allowance_raw", "block_number",
    }
    pat = re.compile(r'"(0x[0-9a-fA-F]{64})"')
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for m in pat.finditer(txt):
            hex_val = m.group(1)
            # find the surrounding line; if it names a safe uint256 field, ok
            start = txt.rfind("\n", 0, m.start()) + 1
            end = txt.find("\n", m.end())
            if end < 0:
                end = len(txt)
            line = txt[start:end]
            if any(fld in line for fld in safe_uint256_fields):
                continue
            assert False, (
                f"{f.name} contains 64-hex value NOT in known-safe uint256 field. "
                f"value={hex_val!r} line={line.strip()!r}"
            )


def test_no_signer_construction_strings() -> None:
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "HTTPProvider(", "Web3(",
           "send_raw_transaction(", "sign_transaction(",
           "eth.send_transaction("]
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for b in bad:
            assert b not in txt, f"{f.name} contains suspicious call: {b!r}"


# --- v2 still raises its own hard-disable (defense in depth) ---------

def test_v2_raises_hard_disable_when_execute_guarded_called_directly() -> None:
    """Defense-in-depth: v2's own --mode execute-guarded still aborts.

    v2's hard-disable is signalled by exit code 1 plus the human message
    'EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE' (the class name
    itself is the same string with underscores vs camel case).
    """
    proc = subprocess.run(
        [sys.executable, str(V2),
         "--mode", "execute-guarded",
         "--run-id", RUN_ID,
         "--wallet", "0xb05b2872ace4564ff247555b6f7b097d31f3d835",
         "--notional", "10",
         "--hold", "15m",
         "--no-send",
         "--i-understand-this-sends-real-transactions"],
        capture_output=True, text=True, timeout=30,
    )
    # v2 must NOT succeed; it should raise / abort
    assert proc.returncode != 0, "v2 execute-guarded unexpectedly returned 0"
    combined = (proc.stdout or "") + (proc.stderr or "")
    # Either the class name or its SCREAMING_SNAKE_CASE human message is acceptable
    assert (
        "ExecutionSendDisabledInImplementationBuildStage" in combined
        or "EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE" in combined
    ), f"v2 did not signal hard-disable; output: {combined[:500]}"
