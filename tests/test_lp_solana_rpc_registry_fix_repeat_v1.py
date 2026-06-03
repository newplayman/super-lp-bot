"""Tests for LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1 stage.

Properties asserted:
  * no keypair / no private key / no seed phrase anywhere
  * no signer / no sendTransaction / no wallet adapter
  * only officially sourced program id can be getAccountInfo verified
  * program id unknown not verified
  * GPA smoke bounded (dataSlice, timeout)
  * FINAL_VERDICT allowed_next_stages only contains the 5 specific stages
  * can_run_probe_now / execution_allowed_now / tiny_canary_allowed locked safe
  * v2 line count 992 unchanged
  * Stage E on-chain verification only runs on officially_sourced=True
  * Stage F GPA smoke skipped for not_verified pids
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260603_093136"
REPORT_DIR = REPO_ROOT / "reports" / "lp_solana_rpc_registry_fix" / RUN_ID

V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"
VERIFIER = REPO_ROOT / "scripts" / "lp_solana_program_id_onchain_verifier_v1.py"

ALLOWED_NEXT_STAGES = {
    "LP_METEORA_DLMM_READONLY_CONNECTOR_V1",
    "LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1",
    "LP_SOLANA_RPC_REGISTRY_FIX_REPEAT",
    "LP_SOLANA_RPC_SETUP_REQUIRED",
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
    assert fv["stage"] == "LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1"
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


def test_final_verdict_source_counts() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["oficial_source_discovery_ran"] is True
    assert fv["oficial_program_id_count"] == 5
    assert len(fv["oficially_sourced_protocols"]) == 5
    assert "Lifinity" in fv["still_unknown_protocols"]


def test_final_verdict_verified_counts() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["verified_program_count"] == 4
    assert "Meteora DLMM" in fv["verified_protocols"]
    assert "Orca Whirlpools" in fv["verified_protocols"]
    assert "Raydium CLMM" in fv["verified_protocols"]


def test_final_verdict_readiness_all_false() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    for k in ["meteora_dlmm_registry_ready", "orca_registry_ready",
              "damm_v2_registry_ready", "raydium_registry_ready",
              "lifinity_registry_ready"]:
        assert fv[k] is False, f"{k} should be false in this round"


def test_final_verdict_recommended_next_stage_in_allowed() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_final_verdict_recommended_next_stage_not_in_forbidden() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    rns = fv["recommended_next_stage"]
    assert rns not in FORBIDDEN_NEXT_STAGES
    for sub in ["EXECUTE_NOW", "FIRST_EXECUTION_RUN", "MINT_NOW", "SEND_NOW",
                "LIVE", "CANARY", "PAPER", "MARKET_UNSAFE_WAIT"]:
        assert sub not in rns


# --- All artifacts present -------------------------------------------

@pytest.mark.parametrize("name", [
    "STAGE_A_WORKSPACE_SAFETY.md",
    "INPUT_EVIDENCE_AUDIT_CN.md", "input_evidence_audit.json",
    "SOLANA_PROGRAM_ID_OFFICIAL_SOURCE_DISCOVERY_CN.md",
    "solana_program_id_official_source_discovery.csv",
    "solana_program_id_official_source_discovery.json",
    "solana_program_id_registry_v2.csv",
    "solana_program_id_registry_v2.json",
    "SOLANA_PROGRAM_ID_ONCHAIN_VERIFICATION_V2_CN.md",
    "solana_program_id_onchain_verification_v2.csv",
    "solana_program_id_onchain_verification_v2.json",
    "SOLANA_GPA_SMOKE_V2_CN.md",
    "solana_gpa_smoke_v2.csv", "solana_gpa_smoke_v2.json",
    "METEORA_DLMM_REGISTRY_READINESS_V2_CN.md",
    "meteora_dlmm_registry_readiness_v2.json",
    "SOLANA_P1_P2_REGISTRY_READINESS_V2_CN.md",
    "solana_p1_p2_registry_readiness_v2.json",
    "SOLANA_RPC_REGISTRY_FIX_NEXT_STAGE_DECISION_CN.md",
    "solana_rpc_registry_fix_next_stage_decision.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = REPORT_DIR / name
    assert p.is_file(), f"missing: {p}"
    assert p.stat().st_size > 0


# --- oficial source discovery -----------------------------------------

def test_discovery_5_protocols_sourced() -> None:
    j = _read_json("solana_program_id_official_source_discovery.json")
    assert j["verified_count"] == 5
    assert j["unknown_count"] == 1
    protocols = {r["protocol"] for r in j["results"] if r["oficial_source_verified"]}
    assert protocols == {"Meteora DLMM", "Meteora DAMM v2", "Orca Whirlpools",
                        "Raydium CLMM", "Raydium CPMM"}


def test_discovery_lifinity_still_unknown() -> None:
    j = _read_json("solana_program_id_official_source_discovery.json")
    lifinity = next(r for r in j["results"] if r["protocol"] == "Lifinity")
    assert lifinity["oficial_source_verified"] is False
    assert lifinity["source_type"] == "unknown"
    assert lifinity["primary_program_id"] is None


# --- registry v2 --------------------------------------------------------

def test_registry_v2_5_with_pids_1_without() -> None:
    j = _read_json("solana_program_id_registry_v2.json")
    for entry in j["registry"]:
        if entry["protocol"] == "Lifinity":
            assert entry["program_id"] is None
            assert entry["selected_for_onchain_verification"] is False
        else:
            assert entry["program_id"] is not None
            assert entry["oficial_source_verified"] is True
            assert entry["selected_for_onchain_verification"] is True


# --- onchain verification v2 -------------------------------------------

def test_verification_4_verified_1_not_found() -> None:
    j = _read_json("solana_program_id_onchain_verification_v2.json")
    statuses = {r["protocol"]: r["verification_status"] for r in j["results"]}
    assert statuses["Meteora DLMM"] == "verified"
    assert statuses["Meteora DAMM v2"] == "verified"
    assert statuses["Orca Whirlpools"] == "verified"
    assert statuses["Raydium CLMM"] == "verified"
    assert statuses["Raydium CPMM"] == "not_found"  # real finding
    assert statuses["Lifinity"] == "skipped_unknown"


def test_verification_no_signer_call_in_results() -> None:
    j = _read_json("solana_program_id_onchain_verification_v2.json")
    s = json.dumps(j)
    bad = ["Keypair.from_secret_key(", "Account.from_key(",
           "sendTransaction(", "sendRawTransaction(",
           "from_seed(", "from_mnemonic("]
    for b in bad:
        assert b not in s


# --- GPA smoke v2 ------------------------------------------------------

def test_gpa_bounded() -> None:
    j = _read_json("solana_gpa_smoke_v2.json")
    for r in j["results"]:
        # all attempted GPAs use dataSlice (per script default)
        assert r["data_slice_used"] is True
        assert r["timeout_sec"] == 8.0 or r["timeout_sec"] == 0.0  # 0 if not attempted


def test_gpa_skipped_for_not_verified() -> None:
    j = _read_json("solana_gpa_smoke_v2.json")
    attempted = {r["protocol"] for r in j["results"] if r["gpa_attempted"]}
    # only 4 verified attempted; CPMM (not_found) and Lifinity (skipped) NOT attempted
    assert attempted == {"Meteora DLMM", "Meteora DAMM v2",
                         "Orca Whirlpools", "Raydium CLMM"}


def test_gpa_no_signer_call_in_results() -> None:
    j = _read_json("solana_gpa_smoke_v2.json")
    s = json.dumps(j)
    for b in ["Keypair.from_secret_key(", "from_secret_key(",
              "sendTransaction(", "sendRawTransaction("]:
        assert b not in s


# --- Meteora DLMM readiness v2 ----------------------------------------

def test_meteora_dlmm_readiness_v2_partial() -> None:
    j = _read_json("meteora_dlmm_registry_readiness_v2.json")
    assert j["readiness_answers_v2"]["Q1_program_id_officially_sourced"] == "yes"
    assert j["readiness_answers_v2"]["Q2_program_verified_onchain"] == "yes"
    # GPA is the blocker
    assert j["readiness_answers_v2"]["Q3_gpa_smoke_feasible"].startswith("no")
    # ready_for_readonly_connector should be false
    assert j["readiness_answers_v2"]["Q5_ready_for_readonly_connector"].startswith("no")


# --- P1/P2 readiness v2 ----------------------------------------------

def test_p1_p2_readiness_5_protocols() -> None:
    j = _read_json("solana_p1_p2_registry_readiness_v2.json")
    protocols = {p["protocol"] for p in j["p1_protocols"]}
    protocols.update(p["protocol"] for p in j["p2_protocols"])
    for required in ["Meteora DAMM v2", "Orca Whirlpools", "Raydium CLMM",
                     "Raydium CPMM", "Lifinity"]:
        assert required in protocols


# --- next stage decision ----------------------------------------------

def test_next_stage_decision_in_allowed() -> None:
    j = _read_json("solana_rpc_registry_fix_next_stage_decision.json")
    assert j["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_next_stage_decision_must_not_list() -> None:
    j = _read_json("solana_rpc_registry_fix_next_stage_decision.json")
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


# --- only officially_sourced can be onchain_verified ----------------

def test_only_oficially_sourced_can_be_onchain_verified() -> None:
    """Per spec: 'only oficial_source_verified = yes can enter on-chain verify'."""
    j_reg = _read_json("solana_program_id_registry_v2.json")
    j_ver = _read_json("solana_program_id_onchain_verification_v2.json")

    verified_map = {r["protocol"]: r for r in j_ver["results"]}
    for entry in j_reg["registry"]:
        if entry["oficial_source_verified"] and entry["program_id"]:
            # this entry could/should have been verified
            assert entry["protocol"] in verified_map, (
                f"{entry['protocol']} is officially_sourced but missing from verification"
            )
        elif not entry["oficial_source_verified"]:
            # this entry should have been skipped
            v = verified_map[entry["protocol"]]
            assert v["verification_status"].startswith("skipped"), (
                f"{entry['protocol']} is not officially_sourced but verification_status={v['verification_status']}"
            )


# --- verifier script: no keypair / no signer / CLI test --------

def test_verifier_script_no_signer_call() -> None:
    src = VERIFIER.read_text()
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "Web3(", "Keypair.from_secret_key(",
           "send_transaction(", "send_raw_transaction(",
           "sign_transaction(", "from_secret_key(", "from_seed(",
           "sendTransaction(", "sendRawTransaction(",
           "solana-keygen", "wallet import", "wallet add"]
    for b in bad:
        assert b not in src, f"verifier script contains suspicious token: {b!r}"


def test_verifier_help() -> None:
    proc = subprocess.run(
        [sys.executable, str(VERIFIER), "--help"],
        capture_output=True, text=True, timeout=15,
    )
    assert proc.returncode == 0
    assert "Solana" in proc.stdout
