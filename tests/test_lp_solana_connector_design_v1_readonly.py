"""Tests for LP_SOLANA_LP_CONNECTOR_DESIGN_V1 stage.

Properties asserted:
  * no Solana private key / keypair / signer anywhere
  * no sendTransaction / sendRawTransaction
  * no wallet import
  * protocols include Meteora DLMM / Orca / Raydium
  * schema proposal exists
  * survival EV adaptation exists
  * FINAL_VERDICT allowed_next_stages only contains the 4 specific stages
  * can_run_probe_now / execution_allowed_now / tiny_canary_allowed locked safe
  * v2 line count 992 unchanged
  * no EVM executor modification
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260603_080347"
REPORT_DIR = REPO_ROOT / "reports" / "lp_solana_connector_design" / RUN_ID

V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"

ALLOWED_NEXT_STAGES = {
    "LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1",
    "LP_METEORA_DLMM_READONLY_CONNECTOR_V1",
    "LP_SOLANA_LP_CONNECTOR_DESIGN_FIX_REPEAT",
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
    "WAIT_FOR_MONITOR_COMPLETION",
    "LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1",  # not allowed in this stage
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
    assert fv["stage"] == "LP_SOLANA_LP_CONNECTOR_DESIGN_V1"
    assert fv["status"] in ("PASS", "WARN", "FAIL")


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["execution_allowed_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["wallet_or_tx_touched"] is False
    assert fv["solana_wallet_or_keypair_touched"] is False
    assert fv["send_hard_disable_still_active"] is True
    assert fv["v2_modified_by_this_task"] is False
    assert fv["v2_line_count_unchanged"] is True
    assert fv["manual_approval_required"] is True


def test_final_verdict_protocol_coverage() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["target_protocol_count"] >= 4
    assert fv["p0_protocol"] == "Meteora DLMM"
    assert "Orca Whirlpools" in fv["p1_protocols"]
    assert "Meteora DAMM v2" in fv["p1_protocols"]


def test_final_verdict_design_complete() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["solana_connector_design_complete"] is True
    assert fv["schema_proposal_ready"] is True
    assert fv["survival_ev_adaptation_ready"] is True
    assert fv["probe_preflight_design_ready"] is True
    assert fv["implementation_roadmap_ready"] is True


def test_final_verdict_evm_v3_path_paused() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["evm_v3_path_paused"] is True


def test_final_verdict_recommended_next_stage_in_allowed() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_final_verdict_recommended_next_stage_not_in_forbidden() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    rns = fv["recommended_next_stage"]
    assert rns not in FORBIDDEN_NEXT_STAGES
    for sub in ["EXECUTE_NOW", "FIRST_EXECUTION_RUN", "MINT_NOW", "SEND_NOW",
                "LIVE", "CANARY", "PAPER", "MARKET_UNSAFE_WAIT"]:
        assert sub not in rns, f"recommended_next_stage {rns!r} contains forbidden substring {sub!r}"


def test_final_verdict_no_64hex_private_key_shape() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    fv_str = json.dumps(fv)
    safe_uint256_fields = {
        "pool_liquidity_raw", "pool_slot0_raw", "gas_price_wei",
        "wallet_eth_wei", "usdc_balance_raw", "weth_balance_raw",
        "usdc_allowance_raw", "weth_allowance_raw", "block_number",
    }
    pat = re.compile(r'"(0x[0-9a-fA-F]{64})"')
    for m in pat.finditer(fv_str):
        hex_val = m.group(1)
        start = fv_str.rfind("\n", 0, m.start()) + 1
        end = fv_str.find("\n", m.end())
        if end < 0:
            end = len(fv_str)
        line = fv_str[start:end]
        if any(fld in line for fld in safe_uint256_fields):
            continue
        assert False, f"FINAL_VERDICT contains 64-hex NOT in safe uint256 field: {line!r}"


def test_final_verdict_did_not_list() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    did_not = fv["this_stage_did_not"]
    must_haves = [
        "implement any Solana connector code",
        "run any Solana RPC",
        "load any Solana wallet / keypair / private key",
        "sign any transaction",
        "send any transaction",
        "construct any signer",
        "open or close any LP position",
        "collect any fee",
        "swap any token",
        "bridge any asset",
        "start live/canary/paper",
        "modify EVM executor v2 source",
        "release v2 hard-disable",
        "set can_run_probe_now to true",
        "set tiny_canary_allowed to yes",
    ]
    for m in must_haves:
        assert any(m in line for line in did_not), f"missing did_not: {m!r}"


# --- All artifacts present -------------------------------------------

@pytest.mark.parametrize("name", [
    "STAGE_A_WORKSPACE_SAFETY.md",
    "INPUT_EVIDENCE_AUDIT_CN.md", "input_evidence_audit.json",
    "SOLANA_LP_PROTOCOL_TARGET_MATRIX_CN.md",
    "solana_lp_protocol_target_matrix.json",
    "solana_lp_protocol_target_matrix.csv",
    "SOLANA_DATA_SOURCE_FEASIBILITY_CN.md",
    "solana_data_source_feasibility.json",
    "METEORA_DLMM_CONNECTOR_DESIGN_CN.md",
    "meteora_dlmm_connector_design.json",
    "ORCA_WHIRLPOOL_CONNECTOR_DESIGN_CN.md",
    "orca_whirlpool_connector_design.json",
    "RAYDIUM_CONNECTOR_DESIGN_CN.md",
    "raydium_connector_design.json",
    "SOLANA_LP_SCHEMA_PROPOSAL_CN.md",
    "solana_lp_schema_proposal.json",
    "SOLANA_SURVIVAL_EV_MODEL_ADAPTATION_CN.md",
    "solana_survival_ev_model_adaptation.json",
    "SOLANA_10_20U_PROBE_PREFLIGHT_DESIGN_CN.md",
    "solana_10_20u_probe_preflight_design.json",
    "SOLANA_CONNECTOR_IMPLEMENTATION_ROADMAP_CN.md",
    "solana_connector_implementation_roadmap.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = REPORT_DIR / name
    assert p.is_file(), f"missing: {p}"
    assert p.stat().st_size > 0


# --- Protocol matrix -----------------------------------------------

def test_protocol_matrix_includes_required_protocols() -> None:
    j = _read_json("solana_lp_protocol_target_matrix.json")
    protocols = {p["protocol"] for p in j["target_protocols"]}
    for required in ["Meteora DLMM", "Orca Whirlpools", "Raydium CLMM"]:
        assert required in protocols, f"missing protocol {required!r}"


def test_protocol_matrix_p0_is_meteora_dlmm() -> None:
    j = _read_json("solana_lp_protocol_target_matrix.json")
    p0 = [p for p in j["target_protocols"] if p["priority"] == "P0"]
    assert len(p0) == 1
    assert p0[0]["protocol"] == "Meteora DLMM"


def test_protocol_matrix_has_position_model_field() -> None:
    j = _read_json("solana_lp_protocol_target_matrix.json")
    for p in j["target_protocols"]:
        assert "position_model" in p
        assert "fee_model" in p
        assert "il_control_model" in p
        assert "quote_method" in p


# --- Data source feasibility --------------------------------------

def test_data_source_rpc_methods_read_only() -> None:
    j = _read_json("solana_data_source_feasibility.json")
    bad = ["sendTransaction", "sendRawTransaction", "sign"]
    for method in j["rpc_methods_read_only"]:
        for b in bad:
            assert b not in method, f"RPC method {method!r} contains {b!r}"


def test_data_source_no_wallet_required() -> None:
    j = _read_json("solana_data_source_feasibility.json")
    assert j["wallet_or_keypair_required"] is False
    assert j["this_stage_runs_rpc"] is False


# --- Meteora DLMM design -------------------------------------------

def test_meteora_dlmm_preflight_has_balance_check() -> None:
    j = _read_json("meteora_dlmm_connector_design.json")
    pf = j["10_20u_probe_preflight"]
    assert "balance_check" in pf
    assert "token_balance" in pf


def test_meteora_dlmm_no_signer_call() -> None:
    j = _read_json("meteora_dlmm_connector_design.json")
    s = json.dumps(j)
    bad = ["Keypair(", "from_secret_key", "sign(", "send_transaction",
           "from_mnemonic", "Account.from_key", "send_raw_transaction",
           "solana-keygen", "wallet import"]
    for b in bad:
        assert b not in s, f"meteora_dlmm design contains suspicious token: {b!r}"


# --- Orca Whirlpool design ----------------------------------------

def test_orca_whirlpool_position_is_nft() -> None:
    j = _read_json("orca_whirlpool_connector_design.json")
    assert "NFT" in j["position_model"]["type"]


def test_orca_whirlpool_no_signer_call() -> None:
    j = _read_json("orca_whirlpool_connector_design.json")
    s = json.dumps(j)
    bad = ["Keypair(", "from_secret_key", "sign(", "send_transaction",
           "from_mnemonic", "Account.from_key", "send_raw_transaction",
           "solana-keygen", "wallet import"]
    for b in bad:
        assert b not in s, f"orca_whirlpool design contains suspicious token: {b!r}"


# --- Raydium design -----------------------------------------------

def test_raydium_clmm_and_cpmm_both_present() -> None:
    j = _read_json("raydium_connector_design.json")
    assert "raydium_clmm" in j
    assert "raydium_cpmm" in j


def test_raydium_no_signer_call() -> None:
    j = _read_json("raydium_connector_design.json")
    s = json.dumps(j)
    bad = ["Keypair(", "from_secret_key", "sign(", "send_transaction",
           "from_mnemonic", "Account.from_key", "send_raw_transaction",
           "solana-keygen", "wallet import"]
    for b in bad:
        assert b not in s, f"raydium design contains suspicious token: {b!r}"


# --- Schema proposal ---------------------------------------------

def test_schema_proposal_has_7_tables() -> None:
    j = _read_json("solana_lp_schema_proposal.json")
    assert len(j["tables"]) == 7
    table_names = {t["name"] for t in j["tables"]}
    expected = {
        "solana_lp_pool_universe_v1",
        "solana_lp_pool_metadata_v1",
        "solana_lp_liquidity_snapshot_v1",
        "solana_lp_fee_velocity_v1",
        "solana_lp_quote_snapshot_v1",
        "solana_lp_virtual_position_preview_v1",
        "solana_lp_probe_preflight_v1",
    }
    assert table_names == expected


def test_schema_proposal_covers_all_20_spec_fields() -> None:
    j = _read_json("solana_lp_schema_proposal.json")
    assert j["spec_required_core_fields_all_covered"] is True


# --- Survival EV adaptation --------------------------------------

def test_survival_ev_adaptation_does_not_reuse_evm_gas() -> None:
    j = _read_json("solana_survival_ev_model_adaptation.json")
    not_reused = j["evm_v3_components_NOT_reused"]
    assert "evm_gas_model" in not_reused
    assert "quoter_v2" in not_reused


def test_survival_ev_adaptation_includes_solana_specific() -> None:
    j = _read_json("solana_survival_ev_model_adaptation.json")
    sol = j["solana_specific_components"]
    assert "rent_required_sol_per_account" in sol
    assert "priority_fee_formula" in sol
    assert "rent_recovery_sol_per_closed_account" in sol


# --- Probe preflight design -------------------------------------

def test_probe_preflight_has_12_gates() -> None:
    j = _read_json("solana_10_20u_probe_preflight_design.json")
    assert len(j["preflight_gates"]) == 12


def test_probe_preflight_no_sign_no_send() -> None:
    j = _read_json("solana_10_20u_probe_preflight_design.json")
    assert j["this_stage_does_not_sign"] is True
    assert j["this_stage_does_not_send"] is True
    assert j["this_stage_does_not_load_keypair"] is True
    assert j["this_stage_does_not_execute"] is True
    assert j["this_stage_does_not_run_rpc"] is True


# --- Implementation roadmap -------------------------------------

def test_roadmap_has_6_phases() -> None:
    j = _read_json("solana_connector_implementation_roadmap.json")
    assert len(j["phases"]) == 6


def test_roadmap_recommends_phase_1_first() -> None:
    j = _read_json("solana_connector_implementation_roadmap.json")
    assert j["next_stage_recommendation"] == "LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1"
    assert j["next_stage_recommendation_rationale"]


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


def test_tiny_canary_allowed_no_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "tiny_canary_allowed" in data:
            assert data["tiny_canary_allowed"] == "no", (
                f"{jf.name} has tiny_canary_allowed={data['tiny_canary_allowed']!r}"
            )


def test_solana_wallet_or_keypair_touched_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "solana_wallet_or_keypair_touched" in data:
            assert data["solana_wallet_or_keypair_touched"] is False, (
                f"{jf.name} has solana_wallet_or_keypair_touched={data['solana_wallet_or_keypair_touched']!r}"
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
            assert False, (
                f"{f.name} contains 64-hex NOT in safe uint256 field. "
                f"line={line.strip()!r}"
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


def test_no_solana_signer_construction_strings() -> None:
    """Solana-specific: no Keypair / from_secret_key / send_transaction."""
    bad = ["Keypair.from_secret_key(", "Keypair.generate(",
           "from_secret_key(", "from_bytes(", "from_seed(",
           "send_transaction(", "send_raw_transaction(",
           "sendTransaction(", "sendRawTransaction(",
           "solana-keygen", "wallet import", "wallet add"]
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for b in bad:
            assert b not in txt, f"{f.name} contains suspicious Solana call: {b!r}"
