"""Tests for LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V2 stage.

Properties asserted:
  * no keypair / no private key / no seed phrase anywhere
  * no signer / no sendTransaction / no wallet adapter
  * SDK path identified for Meteora DLMM (Stage C)
  * minimal smoke succeeded (Stage E; known-pool read verified)
  * Raydium CPMM unknown does not block Meteora
  * Lifinity deferred does not block P0/P1
  * final verdict allowed next stages only contains the 5 specific stages
  * can_run_probe_now / tiny_canary_allowed locked safe
  * recommended_next_stage is in allowed set
  * Stage E used stdlib-only Python (no SDK install)
  * Stage E did not use paid RPC
  * Stage D discovery path decided
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260603_102657"
REPORT_DIR = REPO_ROOT / "reports" / "lp_solana_rpc_registry_fix_v2" / RUN_ID

V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"

ALLOWED_NEXT_STAGES = {
    "LP_METEORA_DLMM_READONLY_CONNECTOR_V1",
    "LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT",
    "LP_SOLANA_PAID_RPC_SETUP_REQUIRED",
    "LP_SOLANA_RPC_REGISTRY_FIX_REPEAT",
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
    assert fv["stage"] == "LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V2"
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
    assert fv["official_program_id_count"] == 5
    assert fv["verified_program_count"] == 4
    assert fv["not_found_count"] == 1
    assert fv["deferred_count"] == 1


def test_final_verdict_sdk_api_discovery_ran() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["meteora_dlmm_sdk_api_source_discovery_ran"] is True


def test_final_verdict_discovery_path_decided() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["meteora_dlmm_discovery_path_decided"] is True
    assert fv["recommended_discovery_path"] in {
        "public_rpc_gpa",
        "paid_rpc_gpa",
        "official_sdk_api",
        "blocked",
    }
    assert fv["recommended_discovery_path"] == "paid_rpc_gpa"


def test_final_verdict_minimal_smoke_ran_and_succeeded() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["meteora_dlmm_minimal_smoke_ran"] is True
    assert fv["meteora_dlmm_minimal_smoke_success"] is True


def test_final_verdict_raydium_cpmm_not_fixed() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["raydium_cpmm_pid_fixed"] is False


def test_final_verdict_lifinity_deferred() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["lifinity_status"] == "deferred"


def test_final_verdict_meteora_dlmm_connector_not_ready() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["meteora_dlmm_connector_ready"] is False


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
    "METEORA_DLMM_SDK_API_SOURCE_DISCOVERY_CN.md",
    "meteora_dlmm_sdk_api_source_discovery.json",
    "METEORA_DLMM_READONLY_DISCOVERY_PATH_DECISION_CN.md",
    "meteora_dlmm_readonly_discovery_path_decision.json",
    "METEORA_DLMM_MINIMAL_READONLY_SMOKE_CN.md",
    "meteora_dlmm_minimal_readonly_smoke.json",
    "meteora_dlmm_minimal_readonly_smoke.csv",
    "RAYDIUM_CPMM_MAINNET_PID_FIX_CN.md",
    "raydium_cpmm_mainnet_pid_fix.json",
    "LIFINITY_PID_DECISION_CN.md",
    "lifinity_pid_decision.json",
    "SOLANA_PROGRAM_ID_REGISTRY_V3_CN.md",
    "solana_program_id_registry_v3.csv",
    "solana_program_id_registry_v3.json",
    "SOLANA_RPC_REGISTRY_FIX_V2_NEXT_STAGE_DECISION_CN.md",
    "solana_rpc_registry_fix_v2_next_stage_decision.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = REPORT_DIR / name
    assert p.is_file(), f"missing: {p}"
    assert p.stat().st_size > 0


# --- Stage C: SDK / API source discovery ----------------------------

def test_sdk_package_identified() -> None:
    j = _read_json("meteora_dlmm_sdk_api_source_discovery.json")
    sources = j["results"]
    sdk_pkg = next((s for s in sources if s.get("name") == "@meteora-ag/dlmm (npm)"), None)
    assert sdk_pkg is not None
    assert sdk_pkg["oficial_source_verified"] is True
    assert sdk_pkg["package_name"] == "@meteora-ag/dlmm"
    assert sdk_pkg["package_version"] == "1.9.10"


def test_api_endpoint_404_documented() -> None:
    j = _read_json("meteora_dlmm_sdk_api_source_discovery.json")
    api = next((s for s in j["results"] if "Meteora DLMM REST API" in s["name"]), None)
    assert api is not None
    assert api["fetch_success"] is False
    assert api["oficial_source_verified"] is False
    # Either "404" in invalid_reason or evidence_excerpt mentions 404
    assert ("404" in api["invalid_reason"]) or ("404" in api.get("evidence_excerpt", ""))


def test_sdk_does_not_bypass_gpa() -> None:
    """Stage C honesty: SDK's getLbPairs uses GPA under the hood."""
    j = _read_json("meteora_dlmm_sdk_api_source_discovery.json")
    txt = json.dumps(j)
    # The text should mention that getLbPairs uses GPA / Anchor program.account.lbPair.all
    assert "program.account.lbPair.all" in txt or "GPA" in txt
    # And field_coverage.sdk_blocker should say GPA
    assert "GPA" in j["field_coverage"]["sdk_blocker"]


# --- Stage D: discovery path decision --------------------------------

def test_discovery_paths_evaluated() -> None:
    j = _read_json("meteora_dlmm_readonly_discovery_path_decision.json")
    paths = {p["path_id"] for p in j["paths_evaluated"]}
    assert paths == {"public_rpc_gpa", "paid_rpc_gpa", "official_sdk_api"}


def test_recommended_path_is_paid_rpc_or_sdk_api() -> None:
    j = _read_json("meteora_dlmm_readonly_discovery_path_decision.json")
    assert j["recommended_discovery_path"] == "paid_rpc_gpa"
    assert j["fallback_path"].startswith("official_sdk_api")


def test_connector_not_ready_without_paid_rpc() -> None:
    j = _read_json("meteora_dlmm_readonly_discovery_path_decision.json")
    val = j["connector_ready_if_path_available"]
    assert val is False or (isinstance(val, str) and val.startswith("no"))


# --- Stage E: minimal smoke -----------------------------------------

def test_smoke_path_is_known_pool_not_gpa() -> None:
    j = _read_json("meteora_dlmm_minimal_readonly_smoke.json")
    assert j["gpa_used"] is False
    assert j["paid_rpc_used"] is False
    assert j["sdk_installed"] is False
    assert j["discovery_path_used"].startswith("known_pool")


def test_smoke_first_pool_verified() -> None:
    j = _read_json("meteora_dlmm_minimal_readonly_smoke.json")
    pv = j["pool_account_verification"]
    assert pv["address"] == "5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF"
    assert pv["owner_is_meteora_dlmm_program"] is True
    assert pv["data_len_bytes"] == 904
    assert pv["data_len_matches_lbpair_struct"] is True


def test_smoke_no_signer_call_in_results() -> None:
    j = _read_json("meteora_dlmm_minimal_readonly_smoke.json")
    s = json.dumps(j)
    bad = ["Keypair.from_secret_key(", "Account.from_key(",
           "sendTransaction(", "sendRawTransaction(",
           "from_seed(", "from_mnemonic("]
    for b in bad:
        assert b not in s


# --- Stage F: Raydium CPMM pid fix ----------------------------------

def test_raydium_cpmm_v2_re_verified_both_pids_null() -> None:
    j = _read_json("raydium_cpmm_mainnet_pid_fix.json")
    ver = j["onchain_verification"]
    assert ver["candidate_pid_mainnet"]["result_mainnet"] == "null (account does not exist)"
    assert ver["candidate_pid_mainnet"]["result_devnet"] == "null (account does not exist)"
    assert ver["candidate_pid_devnet"]["result_mainnet"] == "null (account does not exist)"
    assert ver["candidate_pid_devnet"]["result_devnet"] == "null (account does not exist)"


def test_raydium_cpmm_v1_pid_char_by_char_check() -> None:
    j = _read_json("raydium_cpmm_mainnet_pid_fix.json")
    check = j["v2_pid_char_by_char_check"]
    assert check["equal"] is True
    assert check["len"] == 45


def test_raydium_cpmm_does_not_block_meteora_dlmm() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    j = _read_json("raydium_cpmm_mainnet_pid_fix.json")
    # Meteora DLMM (P0) is verified; Raydium CPMM deferred status must not block it
    q1 = fv["meteora_dlmm_sub_conditions"]["Q1_source_verified"]
    assert q1.startswith("yes")
    assert j["does_not_block_meteora_dlmm"] is True


# --- Stage G: Lifinity pid decision ---------------------------------

def test_lifinity_status_deferred() -> None:
    j = _read_json("lifinity_pid_decision.json")
    assert j["decision"]["lifinity_status"] == "deferred"
    assert j["decision"]["reason"] == "official_source_unavailable"
    assert j["decision"]["does_not_block_p0_p1"] is True


def test_lifinity_v2_corrected_v1_finding() -> None:
    j = _read_json("lifinity_pid_decision.json")
    # V2 found docs.lifinity.io is 200 (not 404) but is a SPA
    assert j["v2_correction"]  # exists
    # And no machine-readable program id
    assert j["v2_probes"]["docs_lifinity_io_root"]["machine_readable_program_id_in_html"] is False


# --- Stage H: registry v3 -------------------------------------------

def test_registry_v3_4_verified_1_not_found_1_deferred() -> None:
    j = _read_json("solana_program_id_registry_v3.json")
    s = j["summary_v3"]
    assert s["verified_count"] == 4
    assert s["not_found_count"] == 1
    assert s["deferred_count"] == 1
    assert s["registry_count"] == 6


def test_registry_v3_meteora_dlmm_q4_q5_upgraded() -> None:
    j = _read_json("solana_program_id_registry_v3.json")
    meteora = next(r for r in j["registry"] if r["protocol"] == "Meteora DLMM")
    assert meteora["v2_sdk_path_identified"] is True
    assert meteora["v2_minimal_smoke_success"] is True
    assert "blocked_by_paid_rpc" in meteora["connector_readiness"]


# --- Stage I: next-stage decision -----------------------------------

def test_next_stage_decision_in_allowed() -> None:
    j = _read_json("solana_rpc_registry_fix_v2_next_stage_decision.json")
    assert j["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_next_stage_decision_is_sdk_api_fix_repeat() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    j = _read_json("solana_rpc_registry_fix_v2_next_stage_decision.json")
    assert j["recommended_next_stage"] == "LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT"
    assert fv["recommended_next_stage"] == "LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT"


def test_next_stage_decision_must_not_list() -> None:
    j = _read_json("solana_rpc_registry_fix_v2_next_stage_decision.json")
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


# --- No paid RPC keys in any artifact ---------------------

def test_no_paid_rpc_keys_in_artifacts() -> None:
    """No paid RPC URLs or keys (Helius / Triton / QuickNode) should be embedded."""
    bad_patterns = [
        "helius_rpc", "triton_rpc", "quicknode_rpc",
        "helius-key", "triton-key", "quicknode-key",
        "rpc_key=", "rpc_key:", "RPC_KEY=",
    ]
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore").lower()
        for b in bad_patterns:
            assert b not in txt, f"{f.name} contains paid RPC key pattern: {b!r}"


# --- No SDK install or import in any artifact -----------------

def test_no_sdk_install_or_import_in_artifacts() -> None:
    """Stage E used stdlib-only Python; the recommendation to install SDK in a future stage is OK,
    but the artifacts should not contain any command that *was* run (only the recommendation text)."""
    # The Stage E CN md contains a 'recommendation' for next stage: `npm install @meteora-ag/dlmm`
    # This is a forward-looking statement, not an executed action. We assert that no json file
    # has a "commands_executed" field with npm install.
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        for key in ["commands_executed", "executed_actions", "npm_install_run"]:
            if key in data:
                assert "@meteora-ag" not in str(data[key]) or "recommendation" in str(data[key]).lower(), (
                    f"{jf.name}.{key} contains an executed npm install"
                )
    # And no Python script or shell script in scripts/ or tests/ contains npm install @meteora-ag
    for base in [REPO_ROOT / "scripts", REPO_ROOT / "tests"]:
        if not base.is_dir():
            continue
        for f in base.iterdir():
            if not f.is_file():
                continue
            if f.suffix not in {".py", ".sh"}:
                continue
            # skip the test file itself (this assertion's docstring + test name mention the string)
            if f.name == "test_lp_solana_rpc_registry_fix_repeat_v2.py":
                continue
            txt = f.read_text(errors="ignore")
            assert "npm install @meteora-ag" not in txt, (
                f"{f} contains npm install @meteora-ag (Stage E was stdlib-only)"
            )


# --- Next stage must not be in forbidden list ----------------

def test_next_stage_decision_must_not_be_probe_or_canary() -> None:
    j = _read_json("solana_rpc_registry_fix_v2_next_stage_decision.json")
    fv = _read_json("FINAL_VERDICT.json")
    for stage_name, _stage in [
        ("decision", j["recommended_next_stage"]),
        ("final_verdict", fv["recommended_next_stage"]),
    ]:
        for forbidden in ["PROBE", "LIVE", "CANARY", "PAPER", "EXECUTE",
                          "MINT", "SEND_NOW", "OPEN_LP", "CLOSE_LP"]:
            assert forbidden not in stage_name.upper() or forbidden not in _stage.upper(), (
                f"{stage_name} contains forbidden token in {_stage!r}"
            )
        # and direct test
        assert "PROBE" not in _stage, f"recommended_next_stage contains PROBE: {_stage!r}"
        assert "EXECUTE" not in _stage, f"recommended_next_stage contains EXECUTE: {_stage!r}"
