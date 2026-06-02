"""Tests for the BSC 10/20U probe dry-run builder artifacts (read-only).

The dry-run builder is data-only (no Python script under scripts/ for this
stage). This test suite asserts the shape and safety invariants of the
JSON artifacts produced by Phases B-J so the package can never silently
turn into an execution path.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DRY_RUN_DIR_PARENT = REPO_ROOT / "reports" / "lp_bsc_probe_dry_run_builder"


def _latest_run_dir() -> Path:
    runs = sorted(p for p in DRY_RUN_DIR_PARENT.iterdir() if p.is_dir())
    assert runs, f"no dry-run dirs under {DRY_RUN_DIR_PARENT}"
    return runs[-1]


def _read(rel: str) -> dict | None:
    p = _latest_run_dir() / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


ALLOWED_NEXT_STAGES = {
    "LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_V1",
    "LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}


# --- Final verdict ------------------------------------------------------

def test_final_verdict_exists_and_has_required_fields() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv is not None
    required = {
        "status", "stage", "candidate_pool", "candidate_pair", "candidate_fee_tier",
        "preferred_notional_usd", "max_notional_usd", "initial_hold_window",
        "pool_state_refreshed", "tick_range_proposed", "token_amounts_calculated",
        "unsigned_tx_package_built", "gas_estimate_feasibility_ready",
        "manual_approval_checkpoint_ready", "wallet_address_required_next",
        "wallet_loaded", "signer_created", "transaction_sent",
        "can_run_probe_now", "can_run_dry_run_with_wallet_address_next",
        "manual_approval_required", "edge_proven",
        "actual_fee_ready", "token_id_available", "tiny_canary_allowed",
        "wallet_or_tx_touched", "recommended_next_stage",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing: {missing}"


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["wallet_loaded"] is False
    assert fv["signer_created"] is False
    assert fv["transaction_sent"] is False
    assert fv["can_run_probe_now"] is False
    assert fv["manual_approval_required"] is True
    assert fv["edge_proven"] == "no"
    assert fv["actual_fee_ready"] is False
    assert fv["token_id_available"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["wallet_or_tx_touched"] is False


def test_recommended_next_stage_in_allowed_set() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_dry_run_only_when_builder_gates_complete() -> None:
    fv = _read("FINAL_VERDICT.json")
    if fv["recommended_next_stage"] == "LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_V1":
        for k in ["pool_state_refreshed", "tick_range_proposed",
                  "token_amounts_calculated", "unsigned_tx_package_built",
                  "gas_estimate_feasibility_ready", "manual_approval_checkpoint_ready"]:
            assert fv[k] is True, f"recommended dry-run but {k} not true"
        assert fv["can_run_dry_run_with_wallet_address_next"] is True


# --- Unsigned tx package: placeholders + ApproveExact -------------------

def test_unsigned_tx_package_uses_placeholders() -> None:
    pkg = _read("bsc_unsigned_tx_package.json")
    assert pkg is not None
    assert pkg["wallet_address_used_for_recipient"] == "PLACEHOLDER_USER_WALLET_NOT_SET"
    assert pkg["deadline_used"] == "PLACEHOLDER_MANUAL_SET"
    assert pkg["package_is_signed"] is False
    assert pkg["package_is_sent"] is False
    assert pkg["package_is_executable"] is False
    # And inside the mint param dicts:
    for k in ["params_for_10u", "params_for_20u"]:
        p = pkg["mint_or_increaseLiquidity_calldata_draft"][k]
        assert p["recipient"] == "PLACEHOLDER_USER_WALLET_NOT_SET"
        assert p["deadline"] == "PLACEHOLDER_MANUAL_SET"


def test_unsigned_tx_package_does_not_emit_full_bytes() -> None:
    pkg = _read("bsc_unsigned_tx_package.json")
    assert pkg["mint_or_increaseLiquidity_calldata_draft"]["full_abi_encoded_bytes_emitted"] is False
    for ap in pkg["approve_calldata_draft_per_token"]:
        assert ap["full_bytes_emitted"] is False
    for rv in pkg["post_exit_revoke_calldata_draft_per_token"]:
        assert rv["full_bytes_emitted"] is False


def test_unsigned_tx_package_uses_ApproveExact() -> None:
    pkg = _read("bsc_unsigned_tx_package.json")
    assert pkg["approval_needed_check"]["policy"].startswith("ApproveExact ONLY")
    assert "ApproveMax forbidden" in pkg["approval_needed_check"]["policy"]
    assert pkg["approval_needed_check"]["this_round_calls_approve"] is False
    # And the approve drafts each constrain value = amountXDesired exactly.
    for ap in pkg["approve_calldata_draft_per_token"]:
        assert "ApproveExact" in ap["params"]["_constraint"]


def test_unsigned_tx_package_requires_post_exit_revoke() -> None:
    pkg = _read("bsc_unsigned_tx_package.json")
    assert pkg["strict_constraints_satisfied"]["post_exit_revoke_required"] is True
    revokes = pkg["post_exit_revoke_calldata_draft_per_token"]
    assert {r["token"] for r in revokes} == {"USDT", "WBNB"}
    for r in revokes:
        assert r["params"]["value"] == "0"


# --- Token amount calculation -------------------------------------------

def test_token_amounts_contain_10u_and_20u() -> None:
    tc = _read("bsc_token_amount_calculation.json")
    assert tc is not None
    assert "10U" in tc["notional_calcs"]
    assert "20U" in tc["notional_calcs"]
    for k in ["10U", "20U"]:
        c = tc["notional_calcs"][k]
        assert int(c["amount0_desired_wei"]) > 0
        assert int(c["amount1_desired_wei"]) > 0
        # amount{0,1}Min must be STRICTLY less than amount{0,1}Desired (slippage > 0)
        assert int(c["amount0Min_wei_with_50bps_slippage"]) < int(c["amount0_desired_wei"])
        assert int(c["amount1Min_wei_with_50bps_slippage"]) < int(c["amount1_desired_wei"])


def test_token_amounts_total_matches_notional() -> None:
    tc = _read("bsc_token_amount_calculation.json")
    for label, expected in [("10U", 10), ("20U", 20)]:
        total = float(tc["notional_calcs"][label]["total_usd_check"])
        # within 0.5% of declared notional (the rounding in Decimal quantization)
        assert abs(total - expected) <= expected * 0.005, f"{label} total {total} not within 0.5% of {expected}"


def test_slippage_does_not_exceed_100_bps() -> None:
    tc = _read("bsc_token_amount_calculation.json")
    assert tc["slippage_algorithm"]["bps_used"] <= 100


# --- Tick range proposal ------------------------------------------------

def test_tick_range_has_three_tiers_and_a_recommendation() -> None:
    tr = _read("bsc_tick_range_proposal.json")
    assert tr is not None
    names = {r["name"] for r in tr["ranges"]}
    assert names == {"narrow", "medium", "wide"}
    assert tr["recommendation"]["selected_tier"] in {"narrow", "medium", "wide"}


def test_tick_range_tickLower_less_than_tickUpper() -> None:
    tr = _read("bsc_tick_range_proposal.json")
    for r in tr["ranges"]:
        assert r["tickLower"] < r["tickUpper"]
    rec = tr["recommendation"]
    assert rec["selected_tickLower"] < rec["selected_tickUpper"]


# --- Gas feasibility ----------------------------------------------------

def test_gas_estimate_was_not_called_this_round() -> None:
    gs = _read("bsc_dry_run_gas_estimate_feasibility.json")
    assert gs is not None
    assert gs["can_estimate_without_wallet"] is False
    assert gs["needs_wallet_address_for_reliable_estimate"] is True
    assert gs["this_round_calls_eth_estimateGas"] is False


def test_gas_feasibility_has_static_conservative_units() -> None:
    gs = _read("bsc_dry_run_gas_estimate_feasibility.json")
    for k in ["conservative_gas_units_mint", "conservative_gas_units_approve",
              "conservative_gas_units_decreaseLiquidity",
              "conservative_gas_units_collect"]:
        assert isinstance(gs[k], int) and gs[k] > 0


# --- Manual approval phrase ---------------------------------------------

def test_approval_phrase_template_and_regex_match() -> None:
    ck = _read("bsc_probe_manual_approval_checkpoint.json")
    assert ck is not None
    template = ck["approval_phrase_template"]
    rgx = ck["phrase_validation_regex"]
    # The example phrases must match the regex
    pattern = re.compile(rgx)
    for ex_key in ("approval_phrase_example_for_10u", "approval_phrase_example_for_20u"):
        ex = ck[ex_key]
        assert pattern.match(ex), f"{ex_key} doesn't match regex"
    # The template itself contains the placeholder structure (not a real address)
    assert "0x<your_wallet_address>" in template
    assert "<10|20>" in template


def test_forbidden_alternative_phrases_are_listed_and_excluded_by_regex() -> None:
    ck = _read("bsc_probe_manual_approval_checkpoint.json")
    rgx = re.compile(ck["phrase_validation_regex"])
    for phrase in ck["forbidden_alternative_phrases_must_be_rejected"]:
        # The catch-all entry is a description, not a phrase to test
        if phrase.startswith("ANY phrase"):
            continue
        assert not rgx.match(phrase), f"forbidden phrase {phrase!r} unexpectedly matches regex"


def test_approval_does_not_unlock_execution() -> None:
    ck = _read("bsc_probe_manual_approval_checkpoint.json")
    blocked = ck["what_approval_does_NOT_unlock"]
    # Must explicitly block execution-class operations
    must_block = [
        "Loading a private key",
        "Signing any transaction",
        "Sending any transaction",
    ]
    blocked_joined = "\n".join(blocked)
    for m in must_block:
        assert any(m.lower() in b.lower() for b in blocked), f"approval must block: {m!r}; not in list"


# --- Candidate freeze ---------------------------------------------------

def test_candidate_freeze_matches_brief() -> None:
    cf = _read("bsc_dry_run_candidate_freeze.json")
    assert cf is not None
    c = cf["candidate"]
    assert c["pool_address"] == "0x172fcd41e0913e95784454622d1c3724f546f849"
    assert c["pair"] == "USDT/WBNB"
    assert c["fee_tier_raw"] == 100
    assert cf["funds"]["max_notional_usd"] == 20
    assert cf["funds"]["preferred_notional_usd"] == 10
    assert cf["hold"]["initial_hold_window"] == "15m"
    assert cf["purpose_clarification"]["is_positive_ev_proof"] is False
    assert cf["this_round_executes_probe"] is False
    assert cf["this_round_loads_wallet"] is False
    assert cf["this_round_creates_signer"] is False
    assert cf["this_round_sends_any_tx"] is False


# --- Input audit --------------------------------------------------------

def test_input_audit_confirms_upstream_pass() -> None:
    ia = _read("input_evidence_audit.json")
    assert ia is not None
    assert ia["all_inputs_verified"] is True
    assert ia["all_upstream_gates_aligned"] is True
    assert ia["proceed_to_phase_C"] is True
    assert ia["upstream_preflight_review"]["status"] == "PASS"
    assert ia["upstream_preflight_review"]["gates"]["dry_run_builder_allowed_next"] is True
    assert ia["upstream_preflight_review"]["gates"]["can_run_probe_now"] is False


# --- Cross-doc consistency ----------------------------------------------

def test_candidate_pool_consistent_across_dry_run_docs() -> None:
    fv = _read("FINAL_VERDICT.json")
    cf = _read("bsc_dry_run_candidate_freeze.json")
    psr = _read("bsc_dry_run_pool_state_refresh.json")
    pkg = _read("bsc_unsigned_tx_package.json")
    pool = "0x172fcd41e0913e95784454622d1c3724f546f849"
    assert fv["candidate_pool"].lower() == pool
    assert cf["candidate"]["pool_address"].lower() == pool
    assert psr["pool_address"].lower() == pool
    # Mint params reference the right pair via token addresses
    p10 = pkg["mint_or_increaseLiquidity_calldata_draft"]["params_for_10u"]
    assert p10["token0"].lower() == "0x55d398326f99059ff775485246999027b3197955"  # USDT
    assert p10["token1"].lower() == "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"  # WBNB
    assert p10["fee"] == 100


# --- Sanity: no scripts/ file in this stage -----------------------------

def test_no_new_executable_scripts_in_this_stage() -> None:
    """The brief states this stage does not introduce new scripts/ executables.
    Verify nothing under scripts/ matches lp_bsc_10_20u_probe_dry_run*."""
    bad = list((REPO_ROOT / "scripts").glob("lp_bsc_10_20u_probe_dry_run*"))
    assert not bad, f"this stage should not add scripts; found: {bad}"
