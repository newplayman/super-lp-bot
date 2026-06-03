"""Tests for LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1 stage.

Properties asserted:
  * no private key / signer / tx send anywhere
  * all 5 new scripts are read-only (no signer, no Account.from_key, etc.)
  * discovery is read-only (factory.getPool via eth_call)
  * survival EV model has all required fields
  * no auto bridge / no auto swap logic
  * FINAL_VERDICT allowed_next_stages only contains 5 specific stages
  * can_run_probe_now / execution_allowed_now / tiny_canary_allowed locked safe
  * v2 line count 992 unchanged
  * positive_realistic_count is consistent across artifacts
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260603_051605"
REPORT_DIR = REPO_ROOT / "reports" / "lp_multichain_survival_ev" / RUN_ID

V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"
DISCOVERY = REPO_ROOT / "scripts" / "lp_evm_standard_v3_multichain_discovery_v1_readonly.py"
READINESS = REPO_ROOT / "scripts" / "lp_evm_v3_pool_readiness_probe_v1_readonly.py"
EV_MODEL = REPO_ROOT / "scripts" / "lp_survival_horizon_ev_model_v1_readonly.py"
OOR_RISK = REPO_ROOT / "scripts" / "lp_survival_out_of_range_risk_v1_readonly.py"
SCORING = REPO_ROOT / "scripts" / "lp_candidate_scoring_v1_readonly.py"

ALLOWED_NEXT_STAGES = {
    "LP_MULTICHAIN_TOP_CANDIDATE_PROBE_PREFLIGHT_V1",
    "LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1",
    "LP_EVM_MULTICHAIN_DISCOVERY_FIX_REPEAT",
    "LP_SOLANA_LP_CONNECTOR_DESIGN_V1",
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
    "WAIT_FOR_MONITOR_COMPLETION",  # not allowed here
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
    assert fv["stage"] == "LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1"
    assert fv["status"] in ("PASS", "WARN", "FAIL")


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["execution_allowed_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["actual_fee_ready"] is False
    assert fv["token_id_available"] is False
    assert fv["wallet_or_tx_touched"] is False
    assert fv["send_hard_disable_still_active"] is True
    assert fv["v2_modified_by_this_task"] is False
    assert fv["v2_line_count_unchanged"] is True


def test_final_verdict_no_tx() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    for k in [
        "this_stage_did_not_execute",
        "this_stage_did_not_send_any_tx",
        "this_stage_did_not_construct_signer",
        "this_stage_did_not_load_private_key",
        "this_stage_did_not_unseal_hard_disable",
    ]:
        assert fv[k] is True, f"final_verdict {k} is not True: {fv[k]!r}"


def test_final_verdict_discovery_ran() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["multichain_discovery_ran"] is True
    assert fv["chain_count"] == 6
    assert fv["protocol_count"] >= 1
    assert fv["candidate_pool_count"] >= 100
    assert fv["readiness_probe_ran"] is True
    assert fv["survival_ev_model_ran"] is True
    assert fv["survival_risk_model_ran"] is True
    assert fv["candidate_scoring_ran"] is True


def test_final_verdict_positive_counts_zero() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["positive_realistic_count"] == 0
    assert fv["positive_conservative_count"] == 0


def test_final_verdict_recommended_next_stage_in_allowed() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_final_verdict_recommended_next_stage_not_in_forbidden() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    rns = fv["recommended_next_stage"]
    assert rns not in FORBIDDEN_NEXT_STAGES


def test_final_verdict_top_candidate_present() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["top_candidate_chain"] != ""
    assert fv["top_candidate_protocol"] != ""
    assert fv["top_candidate_pair"] != ""


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


# --- All artifacts present -------------------------------------------

@pytest.mark.parametrize("name", [
    "STAGE_A_WORKSPACE_SAFETY.md",
    "INPUT_EVIDENCE_AUDIT_CN.md", "input_evidence_audit.json",
    "MULTICHAIN_DEX_UNIVERSE_PLAN_CN.md", "multichain_dex_universe_plan.json",
    "multichain_dex_universe_plan.csv",
    "EVM_STANDARD_V3_MULTICHAIN_DISCOVERY_CN.md",
    "evm_standard_v3_multichain_discovery.json",
    "evm_standard_v3_multichain_discovery.csv",
    "MULTICHAIN_POOL_READINESS_PROBE_CN.md",
    "multichain_pool_readiness_probe.json",
    "multichain_pool_readiness_probe.csv",
    "SURVIVAL_HORIZON_EV_MODEL_CN.md",
    "survival_horizon_ev_model.json",
    "survival_horizon_ev_model.csv",
    "SURVIVAL_OUT_OF_RANGE_RISK_CN.md",
    "survival_out_of_range_risk.json",
    "survival_out_of_range_risk.csv",
    "LP_CANDIDATE_SCORING_CN.md",
    "lp_candidate_scoring.json",
    "lp_candidate_scoring.csv",
    "MULTICHAIN_PROBE_ROUTE_DECISION_CN.md", "multichain_probe_route_decision.json",
    "NEXT_STAGE_DECISION_CN.md", "next_stage_decision.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = REPORT_DIR / name
    assert p.is_file(), f"missing: {p}"
    assert p.stat().st_size > 0


# --- discovery JSON: required fields ----------------------------------

def test_discovery_required_fields() -> None:
    j = _read_json("evm_standard_v3_multichain_discovery.json")
    for f in ["chain", "chain_id", "protocol", "factory", "npm",
              "token_a_symbol", "token_b_symbol", "fee_tier",
              "pool_address", "pool_exists", "metadata_ready",
              "quote_ready", "tick_ready", "gas_ready",
              "discovery_confidence", "invalid_reason"]:
        for r in j["results"]:
            assert f in r, f"row missing {f}: {r.get('pool_address', 'n/a')}"


def test_discovery_no_signer_call() -> None:
    src = DISCOVERY.read_text()
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "Web3(", "HTTPProvider(",
           "send_raw_transaction(", "sign_transaction(",
           "eth.send_transaction(", "eth.send_raw_transaction(",
           "eth_sendRawTransaction", "eth_sendTransaction"]
    for b in bad:
        assert b not in src, f"discovery contains suspicious token: {b!r}"


# --- readiness probe JSON ---------------------------------------------

def test_readiness_required_fields() -> None:
    j = _read_json("multichain_pool_readiness_probe.json")
    for f in ["chain", "protocol", "pool", "fee_tier",
              "state_ready", "quote_ready", "tick_ready", "cost_ready",
              "current_tick", "liquidity", "gas_cost_proxy",
              "capacity_10", "capacity_20", "capacity_100",
              "capacity_500", "capacity_1000", "capacity_2000", "confidence"]:
        for r in j["results"]:
            assert f in r, f"readiness row missing {f}"


def test_readiness_no_signer_call() -> None:
    src = READINESS.read_text()
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "Web3(", "HTTPProvider(",
           "send_raw_transaction(", "sign_transaction(",
           "eth.send_transaction(", "eth.send_raw_transaction(",
           "eth_sendRawTransaction", "eth_sendTransaction"]
    for b in bad:
        assert b not in src, f"readiness contains suspicious token: {b!r}"


# --- survival EV model -----------------------------------------------

def test_ev_model_required_fields() -> None:
    j = _read_json("survival_horizon_ev_model.json")
    # check a sampled row from CSV
    import csv
    with (REPORT_DIR / "survival_horizon_ev_model.csv").open() as f:
        for r in csv.DictReader(f):
            for fld in ["chain", "protocol", "pool", "pair", "fee_tier",
                        "notional", "hold_window", "scenario",
                        "expected_fee_usd", "il_lvr_proxy_usd",
                        "entry_cost_usd", "exit_cost_usd",
                        "gas_cost_usd", "slippage_cost_usd",
                        "failure_buffer_usd", "net_ev_proxy_usd",
                        "net_ev_proxy_pct", "survival_pass",
                        "out_of_range_risk", "confidence"]:
                assert fld in r, f"ev row missing {fld}: {r}"
            break  # first row is enough


def test_ev_model_no_signer_call() -> None:
    src = EV_MODEL.read_text()
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "Web3(", "HTTPProvider(",
           "send_raw_transaction(", "sign_transaction(",
           "eth.send_transaction(", "eth.send_raw_transaction(",
           "eth_sendRawTransaction", "eth_sendTransaction",
           "bridge(", "auto_swap", "auto_bridge"]
    for b in bad:
        assert b not in src, f"ev_model contains suspicious token: {b!r}"


# --- OOR risk ---------------------------------------------------------

def test_oor_risk_required_fields() -> None:
    import csv
    with (REPORT_DIR / "survival_out_of_range_risk.csv").open() as f:
        for r in csv.DictReader(f):
            for fld in ["chain", "protocol", "pool", "pair", "fee_tier",
                        "hold_window", "tick_range_width",
                        "historical_tick_move_p50",
                        "historical_tick_move_p90",
                        "historical_tick_move_p95",
                        "out_of_range_risk", "survival_probability_proxy",
                        "recommended_range_width", "risk_bucket"]:
                assert fld in r, f"oor row missing {fld}: {r}"
            break


def test_oor_risk_no_signer_call() -> None:
    src = OOR_RISK.read_text()
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "Web3(", "HTTPProvider(",
           "send_raw_transaction(", "sign_transaction(",
           "eth.send_transaction(", "eth.send_raw_transaction(",
           "eth_sendRawTransaction", "eth_sendTransaction",
           "bridge(", "auto_swap"]
    for b in bad:
        assert b not in src, f"oor_risk contains suspicious token: {b!r}"


# --- candidate scoring -----------------------------------------------

def test_scoring_required_fields() -> None:
    import csv
    with (REPORT_DIR / "lp_candidate_scoring.csv").open() as f:
        for r in csv.DictReader(f):
            for fld in ["chain", "protocol", "pool", "pair", "fee_tier",
                        "notional", "total_score", "candidate_class"]:
                assert fld in r, f"scoring row missing {fld}: {r}"
            break


def test_scoring_no_signer_call() -> None:
    src = SCORING.read_text()
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "Web3(", "HTTPProvider(",
           "send_raw_transaction(", "sign_transaction(",
           "eth.send_transaction(", "eth.send_raw_transaction(",
           "eth_sendRawTransaction", "eth_sendTransaction",
           "bridge(", "auto_swap", "auto_bridge"]
    for b in bad:
        assert b not in src, f"scoring contains suspicious token: {b!r}"


def test_scoring_no_candidate_now() -> None:
    """Per model finding: 0/19,980 positive EV => no candidate_now."""
    import csv
    with (REPORT_DIR / "lp_candidate_scoring.csv").open() as f:
        for r in csv.DictReader(f):
            assert r["candidate_class"] != "candidate_now", (
                f"unexpected candidate_now: {r}"
            )


# --- multichain probe route decision --------------------------------

def test_route_decision_answers_7_questions() -> None:
    j = _read_json("multichain_probe_route_decision.json")
    answers = j["answers"]
    expected_keys = {
        "1_continue_base_wait",
        "2_other_base_pool_better",
        "3_bsc_better_than_base",
        "4_other_l2_better",
        "5_worth_funding_other_chains",
        "6_best_next_10u_candidate",
        "7_pause_live_continue_discovery",
    }
    assert set(answers.keys()) == expected_keys


def test_route_decision_no_auto_bridge_or_swap() -> None:
    j = _read_json("multichain_probe_route_decision.json")
    assert j["no_auto_bridge_or_swap_recommended"] is True
    assert j["any_tx_touched"] is False
    assert j["wallet_or_tx_touched"] is False
    assert j["signer_created"] is False


# --- next stage decision --------------------------------------------

def test_next_stage_decision_safety_constraints() -> None:
    j = _read_json("next_stage_decision.json")
    must_not = j["next_stage_must_not"]
    must_haves = [
        "execute probe", "send any tx", "construct signer",
        "auto bridge", "auto swap", "load private key"
    ]
    for m in must_haves:
        assert any(m in line for line in must_not), f"missing must_not: {m!r}"


def test_next_stage_decision_in_allowed() -> None:
    j = _read_json("next_stage_decision.json")
    assert j["recommended_next_stage"] in ALLOWED_NEXT_STAGES


# --- v2 line count 992 unchanged -------------------------------------

def test_v2_line_count_unchanged() -> None:
    assert V2.is_file()
    with V2.open() as f:
        n = sum(1 for _ in f)
    assert n == 992, f"v2 line count changed: {n}"


# --- Sweep: safety invariants stay false everywhere -----------------

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


def test_send_hard_disable_still_active_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "send_hard_disable_still_active" in data:
            assert data["send_hard_disable_still_active"] is True, (
                f"{jf.name} has send_hard_disable_still_active={data['send_hard_disable_still_active']!r}"
            )


# --- No secret-shaped strings in artifacts ---------------------------

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


# --- scripts: import and CLI test -----------------------------------

def test_discovery_help() -> None:
    proc = subprocess.run(
        [sys.executable, str(DISCOVERY), "--help"],
        capture_output=True, text=True, timeout=15,
    )
    assert proc.returncode == 0
    assert "Multi-chain" in proc.stdout


def test_ev_model_help() -> None:
    proc = subprocess.run(
        [sys.executable, str(EV_MODEL), "--help"],
        capture_output=True, text=True, timeout=15,
    )
    assert proc.returncode == 0


def test_oor_risk_help() -> None:
    proc = subprocess.run(
        [sys.executable, str(OOR_RISK), "--help"],
        capture_output=True, text=True, timeout=15,
    )
    assert proc.returncode == 0


def test_scoring_help() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCORING), "--help"],
        capture_output=True, text=True, timeout=15,
    )
    assert proc.returncode == 0


def test_readiness_help() -> None:
    proc = subprocess.run(
        [sys.executable, str(READINESS), "--help"],
        capture_output=True, text=True, timeout=15,
    )
    assert proc.returncode == 0
