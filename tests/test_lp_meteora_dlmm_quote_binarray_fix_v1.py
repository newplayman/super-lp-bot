"""Tests for LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1 stage.

Properties asserted:
  * no keypair / no private key / no seed phrase anywhere
  * no signer / no sendTransaction / no wallet adapter
  * no swap tx builder call
  * single-account path does not use getProgramAccounts
  * SDK bin array helper audit ran
  * PDA derivation: 6/6 success (deterministic; no RPC)
  * single-account getAccountInfo: 6/6 success (V4 multi-account blocker bypassed)
  * bin liquidity decode: 420 bins
  * quote smoke: 2/4 success (V1-V4 all 0; V5 first real quote)
  * paid_rpc_required = partial (NOT true; single-account path works)
  * quote blocked does NOT fake success (V5 pool 1 honest)
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
RUN_ID = "20260603_140707"
REPORT_DIR = REPO_ROOT / "reports" / "lp_meteora_dlmm_quote_binarray_fix" / RUN_ID

V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"
PROBE_SCRIPT = REPO_ROOT / "scripts" / "lp_meteora_dlmm_binarray_single_account_probe_v1_readonly.js"

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
    assert fv["stage"] == "LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1"
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


def test_final_verdict_pda_derivation_6_of_6() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["binarray_helper_audit_ran"] is True
    assert fv["binarray_pda_derivation_ran"] is True
    assert fv["binarray_pda_success_count"] == 6
    assert fv["binarray_pda_total_count"] == 6


def test_final_verdict_single_account_smoke_6_of_6() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["single_account_smoke_ran"] is True
    assert fv["single_account_smoke_success_count"] == 6
    assert fv["single_account_smoke_403_count"] == 0
    assert fv["single_account_smoke_410_count"] == 0


def test_final_verdict_bin_liquidity_420_decoded() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["bin_liquidity_decode_success_count"] == 420


def test_final_verdict_quote_2_of_4_honest() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["quote_smoke_ran"] is True
    assert fv["quote_smoke_success_count"] == 2
    assert fv["quote_smoke_blocked_count"] == 2


def test_final_verdict_paid_rpc_partial_not_true() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    pr = fv["paid_rpc_required"]
    assert pr == "partial", f"paid_rpc_required should be 'partial', got {pr!r}"


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
    "METEORA_BINARRAY_SDK_HELPER_AUDIT_CN.md",
    "meteora_binarray_sdk_helper_audit.json",
    "METEORA_BINARRAY_PDA_DERIVATION_CN.md",
    "meteora_binarray_pda_derivation.csv",
    "meteora_binarray_pda_derivation.json",
    "METEORA_BINARRAY_SINGLE_ACCOUNT_SMOKE_CN.md",
    "meteora_binarray_single_account_smoke.csv",
    "meteora_binarray_single_account_smoke.json",
    "METEORA_BIN_LIQUIDITY_DECODE_CN.md",
    "meteora_bin_liquidity_decode.csv",
    "meteora_bin_liquidity_decode.json",
    "METEORA_QUOTE_SMOKE_V2_CN.md",
    "meteora_quote_smoke_v2.csv",
    "meteora_quote_smoke_v2.json",
    "METEORA_PAID_RPC_REQUIREMENT_DECISION_CN.md",
    "meteora_paid_rpc_requirement_decision.json",
    "METEORA_QUOTE_BINARRAY_FIX_NEXT_STAGE_DECISION_CN.md",
    "meteora_quote_binarray_fix_next_stage_decision.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = REPORT_DIR / name
    assert p.is_file(), f"missing: {p}"
    assert p.stat().st_size > 0


# --- Stage C: SDK helper audit ---------------------------------------

def test_helper_audit_12_helpers() -> None:
    j = _read_json("meteora_binarray_sdk_helper_audit.json")
    assert len(j["helpers"]) == 12


def test_helper_audit_single_account_path_identified() -> None:
    j = _read_json("meteora_binarray_sdk_helper_audit.json")
    # At least 8 helpers usable for single-account path
    usable = sum(1 for h in j["helpers"] if h.get("usable_for_single_account_path"))
    assert usable >= 8, f"only {usable} helpers usable; expected >= 8"


# --- Stage D: PDA derivation ----------------------------------------

def test_pda_derivation_6_rows() -> None:
    j = _read_json("meteora_binarray_pda_derivation.json")
    assert len(j) == 6
    for r in j:
        assert r["derivation_success"] is True
        assert r["bin_array_pubkey"] != ""
        assert r["confidence"] >= 0.9


def test_pda_derivation_full_addresses_from_v4_artifact() -> None:
    j = _read_json("meteora_binarray_pda_derivation.json")
    pool_addrs = {r["pool_address"] for r in j}
    assert "5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF" in pool_addrs
    assert "9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad" in pool_addrs


def test_pda_derivation_no_rpc_required() -> None:
    """PDA derivation must be pure math; no RPC."""
    j = _read_json("meteora_binarray_pda_derivation.json")
    for r in j:
        # If derivation succeeded, no RPC was needed
        assert r["invalid_reason"] == ""


# --- Stage E: single-account smoke ---------------------------------

def test_single_account_smoke_6_rows_6_success() -> None:
    j = _read_json("meteora_binarray_single_account_smoke.json")
    assert len(j) == 6
    for r in j:
        assert r["getAccountInfo_attempted"] is True
        assert r["getAccountInfo_success"] is True
        assert r["owner"] == "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
        assert r["data_len"] == 10136


def test_single_account_smoke_no_403_no_410() -> None:
    j = _read_json("meteora_binarray_single_account_smoke.json")
    for r in j:
        assert r["rpc_error_type"] not in ("rpc_403_forbidden", "rpc_410_gone")


def test_single_account_smoke_does_not_use_gpa() -> None:
    """The probe script must NOT call getProgramAccounts."""
    src = PROBE_SCRIPT.read_text()
    assert "getProgramAccounts" not in src, "probe script uses getProgramAccounts"


# --- Stage G: bin liquidity decode --------------------------------

def test_bin_liquidity_420_rows() -> None:
    j = _read_json("meteora_bin_liquidity_decode.json")
    assert len(j) == 420
    success = [r for r in j if r["decode_success"]]
    assert len(success) == 420


def test_bin_liquidity_per_pool() -> None:
    """Each pool has 3 bin arrays × 70 bins = 210 rows."""
    j = _read_json("meteora_bin_liquidity_decode.json")
    pools = {}
    for r in j:
        pools.setdefault(r["pool_address"], 0)
        pools[r["pool_address"]] += 1
    for p, n in pools.items():
        assert n == 210, f"pool {p} has {n} rows; expected 210 (3 arrays × 70 bins)"


# --- Stage H: quote smoke v2 --------------------------------------

def test_quote_4_rows_2_success_2_blocked_honestly() -> None:
    j = _read_json("meteora_quote_smoke_v2.json")
    assert len(j) == 4
    success = [r for r in j if r["quote_success"]]
    blocked = [r for r in j if not r["quote_success"]]
    assert len(success) == 2
    assert len(blocked) == 2


def test_quote_blocked_does_not_fake_success() -> None:
    j = _read_json("meteora_quote_smoke_v2.json")
    for r in j:
        if r["quote_success"]:
            assert r["amount_out_raw"] is not None
            assert r["invalid_reason"] == ""
        else:
            assert r["amount_out_raw"] is None
            assert r["invalid_reason"] != ""


def test_quote_uses_swapquote_no_tx_builder() -> None:
    src = PROBE_SCRIPT.read_text()
    assert "swapQuote" in src
    bad = [
        "dlmmPool.swap(",  # tx builder
        "sendTransaction(",
        "createTransaction",
    ]
    for b in bad:
        assert b not in src


def test_quote_real_data_pool_2() -> None:
    """Pool 2 quotes are real: 10U → 941005, 20U → 1882010 (linear)."""
    j = _read_json("meteora_quote_smoke_v2.json")
    pool2 = [r for r in j if r["pool_address"].startswith("9DiruRpj")]
    assert len(pool2) == 2
    for r in pool2:
        assert r["quote_success"] is True
        assert r["amount_out_raw"] is not None
        # 10U = 941005; 20U = 1882010 (linear: 2x)
        if r["notional_usd"] == "10U":
            assert r["amount_out_raw"] == "941005"
        elif r["notional_usd"] == "20U":
            assert r["amount_out_raw"] == "1882010"


# --- Stage I: paid_rpc decision -------------------------------------

def test_paid_rpc_decision_partial() -> None:
    j = _read_json("meteora_paid_rpc_requirement_decision.json")
    assert j["decision"]["paid_rpc_required"] == "partial"
    assert j["decision"]["single_account_path_proven"] is True


# --- Stage J: next-stage decision -----------------------------------

def test_next_stage_decision_in_allowed() -> None:
    j = _read_json("meteora_quote_binarray_fix_next_stage_decision.json")
    assert j["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_next_stage_decision_is_quote_binarray_fix_repeat() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    j = _read_json("meteora_quote_binarray_fix_next_stage_decision.json")
    assert j["recommended_next_stage"] == "LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT"
    assert fv["recommended_next_stage"] == "LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT"


def test_next_stage_decision_must_not_list() -> None:
    j = _read_json("meteora_quote_binarray_fix_next_stage_decision.json")
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


# --- SDK install isolation ---------------------

def test_sdk_install_dir_is_isolated_tmp() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    # SDK is reused from V3 / V4 install in /tmp; V5 itself doesn't install
    assert fv.get("repo_node_modules_created") is not True  # was true in V3, but we never created it
    nm = REPO_ROOT / "node_modules"
    assert not nm.is_dir()


# --- Probe script: no GPA, no swap tx builder, no wallet adapter ---

def test_probe_script_no_signer_no_tx_no_gpa() -> None:
    src = PROBE_SCRIPT.read_text()
    bad = [
        "Keypair.from_secret_key(", "Keypair.generate(", "new Keypair()",
        "sendTransaction(", "sendRawTransaction(",
        "getProgramAccounts",  # critical: no GPA
        "dlmmPool.swap(",  # tx builder
        "@solana/wallet-adapter",
        "initializePositionAndAddLiquidityByStrategy",
        "addLiquidityByStrategy",
        "removeLiquidity",
        "closePosition", "claimFee", "claimReward",
    ]
    for b in bad:
        assert b not in src, f"probe script contains suspicious token: {b!r}"


def test_probe_script_uses_single_account_path() -> None:
    src = PROBE_SCRIPT.read_text()
    # Must use the single-account path
    assert "getAccountInfo" in src
    assert "deriveBinArray" in src
    assert "binIdToBinArrayIndex" in src
