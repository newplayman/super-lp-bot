"""Tests for the EVM wallet-address crosschain dry-run router (read-only).

The router is data-only (no Python script under scripts/ for this stage).
This suite asserts shape and safety invariants of the JSON artifacts so
the routing decision can never silently turn into execution.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_PARENT = REPO_ROOT / "reports" / "lp_evm_wallet_crosschain_dry_run_router"


def _latest() -> Path:
    runs = sorted(p for p in RUN_PARENT.iterdir() if p.is_dir())
    assert runs, f"no runs under {RUN_PARENT}"
    return runs[-1]


def _read(rel: str) -> dict | None:
    p = _latest() / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


ALLOWED_NEXT = {
    "LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1",
    "LP_BASE_CANDIDATE_REFRESH_FOR_PROBE_PREFLIGHT_V1",
    "LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_V1",
    "LP_WALLET_FUNDING_OR_CANDIDATE_REFRESH_REQUIRED",
    "STOP_LP_RESEARCH_NOW",
}


# --- Final verdict ------------------------------------------------------

def test_final_verdict_exists_and_required_fields() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv is not None
    required = {
        "status", "stage", "wallet_address_bound", "wallet_loaded",
        "signer_created", "transaction_sent", "wallet_address",
        "base_rpc_ready", "bsc_rpc_ready",
        "base_total_usd_proxy", "bsc_total_usd_proxy", "likely_funded_chain",
        "bsc_candidate_ready", "bsc_candidate_blocked_by_funds",
        "base_candidate_count", "base_dry_run_ready_candidate_count",
        "recommended_probe_chain", "can_run_probe_now",
        "can_run_wallet_address_dry_run_next",
        "manual_approval_required_for_any_execution",
        "edge_proven", "tiny_canary_allowed", "wallet_or_tx_touched",
        "recommended_next_stage",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing fields: {missing}"


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["wallet_loaded"] is False
    assert fv["signer_created"] is False
    assert fv["transaction_sent"] is False
    assert fv["can_run_probe_now"] is False
    assert fv["edge_proven"] == "no"
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["wallet_or_tx_touched"] is False
    assert fv["manual_approval_required_for_any_execution"] is True


def test_recommended_next_stage_in_allowed_set() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT


def test_recommended_next_stage_is_not_an_execution() -> None:
    fv = _read("FINAL_VERDICT.json")
    bad = {"LP_BSC_10_20U_PROBE_EXECUTE", "LP_BASE_10_20U_PROBE_EXECUTE",
           "probe_execution", "canary", "live", "paper"}
    assert fv["recommended_next_stage"] not in bad


def test_wallet_address_is_public_address_only() -> None:
    fv = _read("FINAL_VERDICT.json")
    wa = fv["wallet_address"]
    # 0x + 40 hex chars; never anything that looks like a key (64 hex)
    assert wa.startswith("0x") and len(wa) == 42
    assert all(c in "0123456789abcdefABCDEF" for c in wa[2:])
    # No keystore-shaped JSON, no "private" markers
    fv_str = json.dumps(fv)
    for token in ["private_key", "privateKey", "mnemonic", "seed", "keystore"]:
        assert token.lower() not in fv_str.lower(), f"FINAL_VERDICT must not mention {token}"


# --- Balance audit ------------------------------------------------------

def test_balance_audit_did_not_send_tx() -> None:
    ba = _read("evm_wallet_crosschain_balance_audit.json")
    assert ba is not None
    assert ba["wallet_or_tx_touched"] is False
    assert ba["can_run_probe_now"] is False
    # base_total > 0 ⇒ user funded on base (sanity, given the known wallet)
    assert Decimal(ba["base_total_usd_proxy"]) > Decimal(0)


def test_balance_audit_masks_wallet_address() -> None:
    ba = _read("evm_wallet_crosschain_balance_audit.json")
    masked = ba["wallet_address_masked"]
    assert "..." in masked and len(masked) <= 14


# --- Allowance audit ----------------------------------------------------

def test_allowance_audit_did_not_execute_approve() -> None:
    al = _read("evm_wallet_crosschain_allowance_audit.json")
    assert al is not None
    assert al["approve_executed_this_round"] is False
    assert al["wallet_or_tx_touched"] is False


def test_allowance_audit_uses_only_canonical_spenders() -> None:
    al = _read("evm_wallet_crosschain_allowance_audit.json")
    spenders = al["spenders_checked"]
    # The exact set we vetted in this stage
    expected = {"uni_v3_npm_base", "aero_slipstream_npm_base", "pcs_v3_npm_bsc"}
    assert set(spenders.keys()) == expected
    # Each spender is a checksummed-style address
    for k, v in spenders.items():
        assert v.startswith("0x") and len(v) == 42


# --- BSC readiness ------------------------------------------------------

def test_bsc_readiness_correctly_flags_no_funds() -> None:
    bw = _read("bsc_wallet_readiness_check.json")
    assert bw is not None
    assert bw["bsc_can_dry_run_10u"] is False
    assert bw["bsc_can_dry_run_20u"] is False
    assert bw["bsc_candidate_blocked_by_funds_on_other_chain"] is True
    assert bw["no_bridge_suggestion_made_by_this_stage"] is True
    assert bw["no_swap_suggestion_made_by_this_stage"] is True


# --- Base candidate discovery ------------------------------------------

def test_base_candidates_have_5_pools() -> None:
    bc = _read("base_candidate_from_existing_artifacts.json")
    assert bc is not None
    assert bc["cost_pools_count"] == 5
    assert bc["dry_run_ready_count"] >= 1


def test_base_candidate_status_values_are_allowed() -> None:
    bc = _read("base_candidate_from_existing_artifacts.json")
    allowed_statuses = {
        "BASE_DRY_RUN_READY",
        "BASE_NEEDS_FEE_REFRESH",
        "BASE_METADATA_MISSING",
        "REJECT",
        "REJECT_wallet_does_not_hold_either_pool_token",
    }
    for c in bc["candidates"]:
        assert c["candidate_status"] in allowed_statuses, f"bad status {c['candidate_status']!r}"


# --- Route decision -----------------------------------------------------

def test_route_decision_does_not_auto_bridge_or_swap() -> None:
    rd = _read("crosschain_dry_run_route_decision.json")
    assert rd is not None
    assert rd["no_automatic_bridge_suggestion"] is True
    assert rd["no_automatic_swap_suggestion"] is True
    assert rd["no_tx_executed_this_round"] is True
    assert rd["next_stage_is_read_only"] is True
    assert rd["next_stage_does_NOT_authorize_execution"] is True


def test_route_decision_next_stage_in_allowed_set() -> None:
    rd = _read("crosschain_dry_run_route_decision.json")
    assert rd["next_stage_only"] in ALLOWED_NEXT


# --- Next-stage spec ----------------------------------------------------

def test_next_stage_spec_does_not_allow_execution() -> None:
    sp = _read("base_10_20u_probe_preflight_review_next_spec.json")
    assert sp is not None
    must_not = sp["next_stage_must_not"]
    for needle in ["send any transaction", "load private key", "create signer",
                   "execute approve", "start lpbot-live", "auto-bridge", "auto-swap",
                   "flip can_run_probe_now"]:
        assert any(needle.lower() in n.lower() for n in must_not), f"missing constraint: {needle!r}"
    assert sp["approval_phrase_does_not_unlock_execution"] is True
    assert sp["wallet_or_tx_touched"] is False


# --- Input audit --------------------------------------------------------

def test_input_audit_confirms_proceed_and_no_unlock() -> None:
    ia = _read("input_evidence_audit.json")
    assert ia is not None
    assert ia["proceed_to_phase_C"] is True
    assert ia["this_round_scope"] == "crosschain_wallet_address_dry_run_routing_only"
    # All listed don'ts must include the cardinal forbidden actions
    must_not_joined = "\n".join(ia["this_round_must_not"]).lower()
    for needle in ["private key", "signer", "eth_sendtransaction", "eth_sendrawtransaction",
                   "approve", "mint", "live", "canary", "paper", "auto-bridge", "auto-swap"]:
        assert needle in must_not_joined, f"input_audit must_not missing: {needle!r}"


# --- No script side-effects --------------------------------------------

def test_no_new_executable_scripts_in_this_stage() -> None:
    """This stage is data-only; no scripts/ runner should be added."""
    bad = list((REPO_ROOT / "scripts").glob("lp_evm_*crosschain_dry_run_router*"))
    assert not bad, f"this stage should not add scripts; found: {bad}"


# --- Cross-doc consistency ---------------------------------------------

def test_likely_funded_chain_consistent_across_docs() -> None:
    fv = _read("FINAL_VERDICT.json")
    ba = _read("evm_wallet_crosschain_balance_audit.json")
    rd = _read("crosschain_dry_run_route_decision.json")
    assert fv["likely_funded_chain"] == ba["likely_funded_chain"]
    assert rd["wallet_balances_summary"]["likely_funded_chain"] == ba["likely_funded_chain"]


def test_base_dry_run_ready_count_matches_across_docs() -> None:
    fv = _read("FINAL_VERDICT.json")
    bc = _read("base_candidate_from_existing_artifacts.json")
    assert fv["base_dry_run_ready_candidate_count"] == bc["dry_run_ready_count"]
