"""Tests for LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1 stage.

Properties asserted:
  * no keypair / no private key / no seed phrase anywhere
  * no signer / no sendTransaction / no wallet adapter
  * no swap tx builder call
  * coverage bounded to ≤ 9 arrays per spec ("不得无限扩展")
  * single-account path does not use getProgramAccounts
  * quote blocked does NOT fake success (pool 1 honest 0/6)
  * final verdict allowed next stages only contains the 5 specific stages
  * can_run_probe_now / tiny_canary_allowed locked safe
  * v2 line count 992 unchanged
  * SDK install in /tmp isolated
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260603_143729"
REPORT_DIR = REPO_ROOT / "reports" / "lp_meteora_dlmm_quote_binarray_coverage_expand" / RUN_ID

V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"
EXPAND_SCRIPT = REPO_ROOT / "scripts" / "lp_meteora_dlmm_binarray_coverage_expand_v1_readonly.js"

ALLOWED_NEXT_STAGES = {
    "LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1",
    "LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT",
    "LP_SOLANA_PAID_RPC_SETUP_REQUIRED",
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
    assert fv["stage"] == "LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1"
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


def test_final_verdict_pda_42_of_42() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["coverage_plan_ready"] is True
    assert fv["expanded_pda_derivation_ran"] is True
    assert fv["expanded_pda_success_count"] == 42
    assert fv["expanded_pda_total_count"] == 42


def test_final_verdict_single_account_33_of_42() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["expanded_single_account_read_ran"] is True
    assert fv["expanded_single_account_success_count"] == 33
    assert fv["expanded_single_account_total_count"] == 42
    assert fv["expanded_single_account_403_count"] == 0
    assert fv["expanded_single_account_410_count"] == 0


def test_final_verdict_bin_liquidity_2310_decoded() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["expanded_bin_liquidity_decode_success_count"] == 2310


def test_final_verdict_quote_6_of_12_honest() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["quote_smoke_v3_ran"] is True
    assert fv["quote_smoke_attempt_count"] == 12
    assert fv["quote_smoke_success_count"] == 6
    assert fv["sol_usdc_quote_success"] is False
    assert fv["x_usdc_quote_success"] is True


def test_final_verdict_paid_rpc_partial() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["paid_rpc_required"] == "partial"


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
    "METEORA_BINARRAY_COVERAGE_PLAN_CN.md",
    "meteora_binarray_coverage_plan.json",
    "METEORA_EXPANDED_BINARRAY_PDA_DERIVATION_CN.md",
    "meteora_expanded_binarray_pda_derivation.csv",
    "meteora_expanded_binarray_pda_derivation.json",
    "METEORA_EXPANDED_SINGLE_ACCOUNT_READ_CN.md",
    "meteora_expanded_single_account_read.csv",
    "meteora_expanded_single_account_read.json",
    "METEORA_EXPANDED_BIN_LIQUIDITY_DECODE_CN.md",
    "meteora_expanded_bin_liquidity_decode.csv",
    "meteora_expanded_bin_liquidity_decode.json",
    "METEORA_QUOTE_SMOKE_V3_BY_COVERAGE_CN.md",
    "meteora_quote_smoke_v3_by_coverage.csv",
    "meteora_quote_smoke_v3_by_coverage.json",
    "METEORA_QUOTE_READINESS_UPDATE_CN.md",
    "meteora_quote_readiness_update.json",
    "METEORA_COVERAGE_EXPAND_NEXT_STAGE_DECISION_CN.md",
    "meteora_coverage_expand_next_stage_decision.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = REPORT_DIR / name
    assert p.is_file(), f"missing: {p}"
    assert p.stat().st_size > 0


# --- Stage C: coverage plan ----------------------------------------

def test_coverage_plan_3_tiers() -> None:
    j = _read_json("meteora_binarray_coverage_plan.json")
    tiers = [t["tier_id"] for t in j["coverage_tiers"]]
    assert "coverage_3_arrays" in tiers
    assert "coverage_5_arrays" in tiers
    assert "coverage_7_arrays" in tiers
    assert "coverage_9_arrays" in tiers


def test_coverage_plan_max_9_arrays() -> None:
    """Per spec '不得无限扩展', max must be 9 arrays."""
    j = _read_json("meteora_binarray_coverage_plan.json")
    assert j["policy"]["max_coverage_arrays"] == 9
    assert j["policy"]["no_infinite_expansion"] is True


# --- Stage D: expanded PDA derivation -----------------------------

def test_pda_derivation_42_rows() -> None:
    j = _read_json("meteora_expanded_binarray_pda_derivation.json")
    assert len(j) == 42
    for r in j:
        assert r["derivation_success"] is True
        assert r["bin_array_pubkey"] != ""
        assert r["coverage_arrays"] in (5, 7, 9)


def test_pda_derivation_per_coverage() -> None:
    j = _read_json("meteora_expanded_binarray_pda_derivation.json")
    for arr in [5, 7, 9]:
        rows = [r for r in j if r["coverage_arrays"] == arr]
        # 2 pools × arr offsets
        expected = 2 * arr
        assert len(rows) == expected, f"coverage {arr}: expected {expected} rows, got {len(rows)}"


# --- Stage E: expanded single-account read -----------------------

def test_single_account_read_33_success_9_account_null() -> None:
    j = _read_json("meteora_expanded_single_account_read.json")
    assert len(j) == 42
    success = [r for r in j if r["getAccountInfo_success"]]
    null = [r for r in j if r["rpc_error_type"] == "account_null"]
    assert len(success) == 33
    assert len(null) == 9
    # 0 RPC errors
    for r in j:
        assert r["rpc_error_type"] not in ("rpc_403_forbidden", "rpc_410_gone")


def test_single_account_read_does_not_use_gpa() -> None:
    """The expand script must NOT call getProgramAccounts."""
    src = EXPAND_SCRIPT.read_text()
    assert "getProgramAccounts" not in src, "expand script uses getProgramAccounts"


# --- Stage F: expanded bin liquidity decode ----------------------

def test_bin_liquidity_2310_rows() -> None:
    j = _read_json("meteora_expanded_bin_liquidity_decode.json")
    assert len(j) == 2310


def test_bin_liquidity_per_coverage() -> None:
    j = _read_json("meteora_expanded_bin_liquidity_decode.json")
    # Just check that 5_arrays <= 7_arrays <= 9_arrays (each tier adds more)
    c5 = sum(1 for r in j if r["coverage_arrays"] == 5)
    c7 = sum(1 for r in j if r["coverage_arrays"] == 7)
    c9 = sum(1 for r in j if r["coverage_arrays"] == 9)
    assert c5 >= 100, f"5_arrays only {c5}"
    assert c7 >= c5, f"7_arrays {c7} < 5_arrays {c5}"
    assert c9 >= c7, f"9_arrays {c9} < 7_arrays {c7}"


def test_bin_liquidity_with_liquidity_count() -> None:
    j = _read_json("meteora_expanded_bin_liquidity_decode.json")
    withLiq = [r for r in j if r["liquidity_available"]]
    assert len(withLiq) >= 200, f"only {len(withLiq)} bins with liquidity"


# --- Stage G: quote smoke v3 --------------------------------------

def test_quote_12_rows_6_success() -> None:
    j = _read_json("meteora_quote_smoke_v3_by_coverage.json")
    assert len(j) == 12
    success = [r for r in j if r["quote_success"]]
    assert len(success) == 6


def test_quote_blocked_does_not_fake_success() -> None:
    j = _read_json("meteora_quote_smoke_v3_by_coverage.json")
    for r in j:
        if r["quote_success"]:
            assert r["amount_out_raw"] is not None
            assert r["invalid_reason"] == ""
            assert r["coverage_sufficient"] == "yes"
        else:
            assert r["amount_out_raw"] is None
            assert r["invalid_reason"] != ""
            assert r["coverage_sufficient"] == "no"


def test_quote_uses_swapquote_no_tx_builder() -> None:
    src = EXPAND_SCRIPT.read_text()
    assert "swapQuote" in src
    bad = [
        "dlmmPool.swap(",
        "sendTransaction(",
        "createTransaction",
    ]
    for b in bad:
        assert b not in src


def test_quote_pool_2_real_data() -> None:
    """Pool 2 quotes are real: 10U → 941005, 20U → 1882010."""
    j = _read_json("meteora_quote_smoke_v3_by_coverage.json")
    pool2 = [r for r in j if r["pool_address"].startswith("9DiruRpj") and r["quote_success"]]
    assert len(pool2) >= 2
    for r in pool2:
        if r["notional_usd"] == "10U":
            assert r["amount_out_raw"] == "941005"
        elif r["notional_usd"] == "20U":
            assert r["amount_out_raw"] == "1882010"


def test_quote_pool_1_blocked_at_all_tiers() -> None:
    """Pool 1 quote blocked at 5/7/9 arrays (honest finding)."""
    j = _read_json("meteora_quote_smoke_v3_by_coverage.json")
    pool1 = [r for r in j if r["pool_address"].startswith("5BKxfWMb")]
    assert len(pool1) == 6  # 3 tiers × 2 notionals
    for r in pool1:
        assert r["quote_success"] is False
        assert r["coverage_sufficient"] == "no"
        assert "Insufficient" in r["invalid_reason"]


# --- Stage H: quote readiness --------------------------------------

def test_readiness_3_ready_3_partial() -> None:
    j = _read_json("meteora_quote_readiness_update.json")
    rt = j["6_table_readiness_update"]
    assert "ready" in rt["meteora_dlmm_known_pool_universe_v1"]
    assert "ready" in rt["meteora_dlmm_pool_snapshot_v1"]
    assert "ready" in rt["meteora_dlmm_fee_snapshot_v1"]
    assert rt["meteora_dlmm_bin_liquidity_snapshot_v1"].startswith("now_ready") or "partial" in rt["meteora_dlmm_bin_liquidity_snapshot_v1"]
    assert "partial" in rt["meteora_dlmm_quote_snapshot_v1"]
    assert "partial" in rt["meteora_dlmm_survival_ev_preview_v1"]


def test_readiness_paid_rpc_partial() -> None:
    j = _read_json("meteora_quote_readiness_update.json")
    assert j["judgments"]["paid_rpc_required"].startswith("partial")


# --- Stage I: next-stage decision -----------------------------------

def test_next_stage_decision_in_allowed() -> None:
    j = _read_json("meteora_coverage_expand_next_stage_decision.json")
    assert j["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_next_stage_decision_is_quote_binarray_fix_repeat() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    j = _read_json("meteora_coverage_expand_next_stage_decision.json")
    assert j["recommended_next_stage"] == "LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT"
    assert fv["recommended_next_stage"] == "LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT"


def test_next_stage_decision_must_not_list() -> None:
    j = _read_json("meteora_coverage_expand_next_stage_decision.json")
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


def test_repo_package_json_not_modified() -> None:
    pj = REPO_ROOT / "package.json"
    if pj.is_file():
        j = json.loads(pj.read_text())
        deps_str = json.dumps(j.get("dependencies", {})) + json.dumps(j.get("devDependencies", {}))
        assert "meteora-ag" not in deps_str, "package.json mentions meteora-ag"


# --- Coverage bounded to 9 arrays max ----------------------------

def test_coverage_bounded_to_9_arrays() -> None:
    """Per spec '不得无限扩展': the script must not exceed 9 arrays in any tier."""
    src = EXPAND_SCRIPT.read_text()
    # Check for explicit 9-array cap
    assert "[5, 7, 9]" in src or "coverage_9" in src
    # Check for any tier > 9 (e.g. [5, 7, 9, 11, 13])
    import re
    # Look for any 2-digit array counts in offsetsForCoverage function
    func_match = re.search(r"function offsetsForCoverage\(arr\) \{(.+?)return null;", src, re.DOTALL)
    if func_match:
        body = func_match.group(1)
        # Extract all "if (arr === N)" conditions
        nums = re.findall(r"arr === (\d+)", body)
        assert all(int(n) <= 9 for n in nums), f"tier > 9: {nums}"


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

def test_expand_script_no_signer_no_tx_no_gpa() -> None:
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
        assert b not in src, f"expand script contains suspicious token: {b!r}"


def test_expand_script_uses_single_account_path() -> None:
    src = EXPAND_SCRIPT.read_text()
    assert "getAccountInfo" in src
    assert "deriveBinArray" in src
    assert "binIdToBinArrayIndex" in src
    assert "swapQuote" in src
