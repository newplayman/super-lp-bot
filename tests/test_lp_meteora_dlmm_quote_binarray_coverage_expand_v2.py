"""Tests for LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V2 stage.

Properties asserted:
  * no keypair / no private key / no seed phrase anywhere
  * no signer / no sendTransaction / no wallet adapter
  * no swap tx builder call
  * coverage bounded to ≤ 15 arrays per spec ("不得超过 15 arrays")
  * single-account path does not use getProgramAccounts
  * quote blocked does NOT fake success (pool 1 honest 0/4 at 12+15)
  * final verdict allowed next stages only contains the 5 specific stages
  * can_run_probe_now / tiny_canary_allowed locked safe
  * v2 line count 992 unchanged
  * SDK install in /tmp isolated
  * can_enter_partial_survival_ev_preview = true (pool 2 only)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260603_150331"
REPORT_DIR = REPO_ROOT / "reports" / "lp_meteora_dlmm_quote_binarray_coverage_expand_v2" / RUN_ID

V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"
EXPAND_SCRIPT = REPO_ROOT / "scripts" / "lp_meteora_dlmm_binarray_coverage_expand_v2_readonly.js"

ALLOWED_NEXT_STAGES = {
    "LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1",
    "LP_SOLANA_PAID_RPC_SETUP_REQUIRED",
    "LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT",
    "LP_METEORA_DLMM_KNOWN_POOL_CONNECTOR_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}
FORBIDDEN_NEXT_STAGES = {
    "EXECUTE_NOW",
    "FIRST_EXECUTION_RUN_V1",
    "MINT_NOW",
    "SEND_NOW",
    "WAIT_FOR_MONITOR_COMPLETION",
    "LP_BASE_10U_PROBE_LIVE",
    "LP_BASE_10U_PROBE_CANARY",
    "LP_BASE_10U_PROBE_PAPER",
    "LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1",
    "PROBE_NOW",
    "LIVE_TRADE_NOW",
    "OPEN_LP_NOW",
    "CLOSE_LP_NOW",
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
    assert fv["stage"] == "LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V2"
    assert fv["status"] in ("PASS", "WARN", "FAIL")


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["execution_allowed_now"] is False
    assert fv["transaction_sent"] is False
    assert fv["wallet_or_tx_touched"] is False
    assert fv["solana_wallet_or_keypair_touched"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["send_hard_disable_still_active"] is True
    assert fv["v2_modified_by_this_task"] is False
    assert fv["v2_line_count_unchanged"] is True
    assert fv["manual_approval_required"] is True


def test_final_verdict_pda_12_15_sol_usdc() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["coverage_12_attempted"] is True
    assert fv["coverage_12_success_count"] == 12
    assert fv["coverage_15_attempted"] is True
    assert fv["coverage_15_success_count"] == 15


def test_final_verdict_pool_1_still_blocked() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["sol_usdc_10u_quote_success"] is False
    assert fv["sol_usdc_20u_quote_success"] is False


def test_final_verdict_pool_2_stable() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["x_usdc_quote_still_success"] is True


def test_final_verdict_partial_ev_preview_allowed() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_enter_full_survival_ev_preview"] is False
    assert fv["can_enter_partial_survival_ev_preview"] is True


def test_final_verdict_paid_rpc_required_true() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["paid_rpc_required"] is True


def test_final_verdict_min_coverage_15_arrays() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert "15" in fv["minimum_coverage_required"]


def test_final_verdict_recommended_next_stage_in_allowed() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_final_verdict_recommended_next_stage_not_in_forbidden() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    rns = fv["recommended_next_stage"]
    assert rns not in FORBIDDEN_NEXT_STAGES
    for sub in ["EXECUTE_NOW", "FIRST_EXECUTION_RUN", "MINT_NOW", "SEND_NOW",
                "LIVE", "CANARY", "PAPER", "MARKET_UNSAFE_WAIT",
                "PROBE_NOW", "OPEN_LP_NOW", "CLOSE_LP_NOW"]:
        assert sub not in rns


# --- All artifacts present -------------------------------------------

@pytest.mark.parametrize("name", [
    "INPUT_EVIDENCE_AUDIT_CN.md", "input_evidence_audit.json",
    "METEORA_BINARRAY_COVERAGE_12_15_PLAN_CN.md",
    "meteora_binarray_coverage_12_15_plan.json",
    "meteora_binarray_pda_12_15_derivation.csv",
    "meteora_binarray_pda_12_15_derivation.json",
    "meteora_single_account_read_12_15.csv",
    "meteora_single_account_read_12_15.json",
    "meteora_bin_liquidity_decode_12_15.csv",
    "meteora_bin_liquidity_decode_12_15.json",
    "meteora_sol_usdc_quote_smoke_v4.csv",
    "meteora_sol_usdc_quote_smoke_v4.json",
    "METEORA_COMBINED_QUOTE_READINESS_V2_CN.md",
    "meteora_combined_quote_readiness_v2.json",
    "METEORA_COVERAGE_EXPAND_V2_NEXT_STAGE_DECISION_CN.md",
    "meteora_coverage_expand_v2_next_stage_decision.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = REPORT_DIR / name
    assert p.is_file(), f"missing: {p}"
    assert p.stat().st_size > 0


# --- Stage C: 12/15 plan ------------------------------------------

def test_12_15_plan_max_15() -> None:
    j = _read_json("meteora_binarray_coverage_12_15_plan.json")
    assert j["policy"]["max_coverage_arrays"] == 15
    assert j["policy"]["no_infinite_expansion"] is True
    assert j["policy"]["must_checkpoint_at_12"] is True


# --- Stage D: PDA derivation ---------------------------------------

def test_pda_derivation_32_rows() -> None:
    j = _read_json("meteora_binarray_pda_12_15_derivation.json")
    assert len(j) == 32  # SOL/USDC: 12 + 15 = 27; X/USDC: 5; total 32
    for r in j:
        assert r["derivation_success"] is True
        assert r["bin_array_pubkey"] != ""
        assert r["coverage_arrays"] in (5, 12, 15)


def test_pda_derivation_sol_usdc_27_rows() -> None:
    j = _read_json("meteora_binarray_pda_12_15_derivation.json")
    sol_usdc = [r for r in j if r["pool_address"].startswith("5BKxfWMb")]
    assert len(sol_usdc) == 27  # 12 + 15
    for arr in [12, 15]:
        rows = [r for r in sol_usdc if r["coverage_arrays"] == arr]
        assert len(rows) == arr, f"expected {arr} rows, got {len(rows)}"


# --- Stage E: single-account read ---------------------------------

def test_single_account_read_no_403_no_410() -> None:
    j = _read_json("meteora_single_account_read_12_15.json")
    for r in j:
        assert r["rpc_error_type"] not in ("rpc_403_forbidden", "rpc_410_gone")


# --- Stage F: bin liquidity decode --------------------------------

def test_bin_liquidity_pool_1_zero_liquidity() -> None:
    """Pool 1 (SOL/USDC) has 0 bins with liquidity at 12+15 arrays."""
    j = _read_json("meteora_bin_liquidity_decode_12_15.json")
    sol_usdc_12_15 = [r for r in j if r["pool_address"].startswith("5BKxfWMb") and r["coverage_arrays"] in (12, 15)]
    withLiq = [r for r in sol_usdc_12_15 if r["liquidity_available"]]
    assert len(withLiq) == 0, f"pool 1 has {len(withLiq)} bins with liquidity (expected 0)"


# --- Stage G: SOL/USDC quote v4 ------------------------------------

def test_quote_4_rows_0_success() -> None:
    j = _read_json("meteora_sol_usdc_quote_smoke_v4.json")
    assert len(j) == 4
    success = [r for r in j if r["quote_success"]]
    assert len(success) == 0


def test_quote_blocked_does_not_fake_success() -> None:
    j = _read_json("meteora_sol_usdc_quote_smoke_v4.json")
    for r in j:
        if r["quote_success"]:
            assert r["amount_out_raw"] is not None
            assert r["coverage_sufficient"] == "yes"
        else:
            assert r["amount_out_raw"] is None
            assert r["coverage_sufficient"] == "no"
            assert "Insufficient" in r["invalid_reason"]


# --- Stage H: combined quote readiness ----------------------------

def test_combined_readiness_partial_ev_allowed() -> None:
    j = _read_json("meteora_combined_quote_readiness_v2.json")
    assert j["judgments"]["can_enter_partial_survival_ev_preview"] is True
    assert j["judgments"]["can_enter_full_survival_ev_preview"] is False


def test_combined_readiness_paid_rpc_required_true() -> None:
    j = _read_json("meteora_combined_quote_readiness_v2.json")
    val = j["judgments"]["paid_rpc_required"]
    assert val is True or (isinstance(val, str) and val.startswith("true")), f"got {val!r}"


# --- Stage I: next-stage decision ---------------------------------

def test_next_stage_decision_in_allowed() -> None:
    j = _read_json("meteora_coverage_expand_v2_next_stage_decision.json")
    assert j["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_next_stage_decision_is_survival_ev_preview() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    j = _read_json("meteora_coverage_expand_v2_next_stage_decision.json")
    assert j["recommended_next_stage"] == "LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1"
    assert fv["recommended_next_stage"] == "LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1"


def test_next_stage_decision_must_not_list() -> None:
    j = _read_json("meteora_coverage_expand_v2_next_stage_decision.json")
    must_not = j["next_stage_must_not"]
    must_haves = [
        "execute probe", "send any tx",
        "keypair",
        "bridge", "swap",
        "hard-disable",
        "can_run_probe_now to true",
        "tiny_canary_allowed to yes"
    ]
    for m in must_haves:
        assert any(m in line for line in must_not), f"missing must_not: {m!r}"


# --- v2 line count 992 unchanged ---------------------------------

def test_v2_line_count_unchanged() -> None:
    assert V2.is_file()
    with V2.open() as f:
        n = sum(1 for _ in f)
    assert n == 992, f"v2 line count changed: {n}"


# --- Repo root not polluted ---------------------------------------

def test_repo_node_modules_not_created() -> None:
    nm = REPO_ROOT / "node_modules"
    assert not nm.is_dir(), f"repo node_modules was created: {nm}"


# --- Coverage bounded to 15 arrays max ----------------------------

def test_coverage_bounded_to_15_arrays() -> None:
    """Per spec '不得超过 15 arrays': the script must not exceed 15 arrays in any tier."""
    src = EXPAND_SCRIPT.read_text()
    # Check for explicit 15-array cap
    assert "[12, 15]" in src or "coverage_15" in src
    # Check for any tier > 15
    import re
    func_match = re.search(r"function offsetsForCoverage\(arr\) \{(.+?)return null;", src, re.DOTALL)
    if func_match:
        body = func_match.group(1)
        nums = re.findall(r"arr === (\d+)", body)
        assert all(int(n) <= 15 for n in nums), f"tier > 15: {nums}"


def test_15_arrays_terminates_expansion() -> None:
    """V7 hit spec hard cap; spec says STOP if 15 still fails. Script logic should not auto-expand to 17, 19, etc."""
    src = EXPAND_SCRIPT.read_text()
    # Only 5, 12, 15 in offsetsForCoverage
    for n in [5, 12, 15]:
        assert f"arr === {n}" in src, f"coverage {n} missing"
    # No tier > 15
    for n in [16, 17, 19, 21, 25]:
        assert f"arr === {n}" not in src, f"tier {n} present (spec cap is 15)"


# --- Sweep: safety invariants stay false everywhere ------------

def test_can_run_probe_now_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "can_run_probe_now" in data:
            assert data["can_run_probe_now"] is False, (
                f"{jf.name} has can_run_probe_now={data['can_run_probe_now']!r}"
            )


def test_solana_wallet_or_keypair_touched_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "solana_wallet_or_keypair_touched" in data:
            assert data["solana_wallet_or_keypair_touched"] is False, (
                f"{jf.name} has solana_wallet_or_keypair_touched={data['solana_wallet_or_keypair_touched']!r}"
            )


def test_tiny_canary_allowed_no_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "tiny_canary_allowed" in data:
            assert data["tiny_canary_allowed"] == "no", (
                f"{jf.name} has tiny_canary_allowed={data['tiny_canary_allowed']!r}"
            )


# --- No secret-shaped strings in artifacts ---------------------

def test_no_64hex_private_key_shape_in_any_artifact() -> None:
    safe_uint256_fields = {
        "pool_liquidity_raw", "pool_slot0_raw", "gas_price_wei",
        "wallet_eth_wei", "usdc_balance_raw", "weth_balance_raw",
        "usdc_allowance_raw", "weth_allowance_raw", "block_number",
        "lamports",
    }
    pat = re.compile(r'"(0x[0-9a-fA-F]{64})"')
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for m in pat.finditer(txt):
            hex_val = m.group(1)
            start = txt.rfind("\n", 0, m.start()) + 1
            end = txt.find("\n", m.end())
            if end < 0:
                end = len(txt)
            line = txt[start:end]
            if any(fld in line for fld in safe_uint256_fields):
                continue
            assert False, f"{f.name} contains 64-hex NOT in safe field: {line!r}"


def test_no_signer_construction_strings() -> None:
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "HTTPProvider(", "Web3(",
           "send_raw_transaction(", "sign_transaction(",
           "eth.send_transaction(",
           "Keypair.from_secret_key(", "Keypair.generate(",
           "from_secret_key(", "from_seed(", "from_bytes(",
           "sendTransaction(", "sendRawTransaction(",
           "solana-keygen", "wallet add"]
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for b in bad:
            assert b not in txt, f"{f.name} contains suspicious call: {b!r}"


# --- Expand script: no GPA, no swap tx builder, no wallet adapter ---

def test_expand_v2_script_no_signer_no_tx_no_gpa() -> None:
    src = EXPAND_SCRIPT.read_text()
    bad = [
        "Keypair.from_secret_key(", "Keypair.generate(", "new Keypair()",
        "sendTransaction(", "sendRawTransaction(",
        "getProgramAccounts",
        "dlmmPool.swap(",
        "@solana/wallet-adapter",
        "initializePositionAndAddLiquidityByStrategy",
        "addLiquidityByStrategy",
        "removeLiquidity",
        "closePosition", "claimFee", "claimReward",
    ]
    for b in bad:
        assert b not in src, f"expand v2 script contains suspicious token: {b!r}"


def test_expand_v2_script_uses_single_account_path() -> None:
    src = EXPAND_SCRIPT.read_text()
    assert "getAccountInfo" in src
    assert "deriveBinArray" in src
    assert "binIdToBinArrayIndex" in src
    assert "swapQuote" in src
