"""Tests for the BSC 10/20U probe wallet-address dry-run REJECTION record.

This stage was halted at Phase A because the user-supplied approval phrase
contained literal template placeholders ('USER_PROVIDED_WALLET_ADDRESS' /
'USER_SELECTED_NOTIONAL') instead of real values. Per the brief, the
stage MUST stop, write APPROVAL_PHRASE_REJECTED_CN.md, and not perform
any on-chain reads.

These tests assert:
  - The validation regex (frozen in the upstream dry-run-builder's
    manual_approval_checkpoint) correctly rejects the received phrase.
  - The validation regex correctly accepts well-formed phrases.
  - The rejection record exists, has the right shape, and confirms no
    chain reads / wallet / signer / tx-submission occurred.
  - The FINAL_VERDICT.json is FAIL, all gates locked, and the recommended
    next stage is the documented FIX_REPEAT.
  - No new scripts under scripts/ were added this round (data-only stage).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_PARENT = REPO_ROOT / "reports" / "lp_bsc_probe_wallet_address_dry_run"
UPSTREAM_CKPT = (
    REPO_ROOT / "reports" / "lp_bsc_probe_dry_run_builder" /
    "20260602_094727" / "bsc_probe_manual_approval_checkpoint.json"
)


def _latest_run_dir() -> Path:
    runs = sorted(p for p in RUN_PARENT.iterdir() if p.is_dir())
    assert runs, f"no run dirs under {RUN_PARENT}"
    return runs[-1]


def _read(rel: str) -> dict | None:
    p = _latest_run_dir() / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


ALLOWED_NEXT_STAGES = {
    "LP_BSC_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1",
    "LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}


# --- Validation regex tests (frozen from upstream) ----------------------

def _frozen_regex() -> str:
    ckpt = json.loads(UPSTREAM_CKPT.read_text())
    return ckpt["phrase_validation_regex"]


def test_validation_regex_is_frozen_by_upstream_checkpoint() -> None:
    rgx = _frozen_regex()
    # The regex is the contract; assert its literal content so future drift trips this test.
    # NOTE: the character class uses `[0-9a-fA-F]` (digits first) as frozen by the
    # upstream LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1 stage. The current stage's
    # brief textually showed `[a-fA-F0-9]`; the two are equivalent as character
    # classes but different as literal strings. The contract is the upstream one.
    assert rgx == "^APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0x[0-9a-fA-F]{40} notional=(10|20)$"


def test_received_phrase_with_template_placeholders_is_rejected() -> None:
    rgx = re.compile(_frozen_regex())
    received = (
        "APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY "
        "wallet=USER_PROVIDED_WALLET_ADDRESS notional=USER_SELECTED_NOTIONAL"
    )
    assert not rgx.match(received), "template-placeholder phrase MUST be rejected"


@pytest.mark.parametrize("good_phrase", [
    "APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY "
    "wallet=0xABCDEF0123456789ABCDEF0123456789ABCDEF01 notional=10",
    "APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY "
    "wallet=0xabcdef0123456789abcdef0123456789abcdef01 notional=20",
])
def test_well_formed_phrase_matches_regex(good_phrase: str) -> None:
    rgx = re.compile(_frozen_regex())
    assert rgx.match(good_phrase) is not None


@pytest.mark.parametrize("bad_phrase", [
    # missing notional value
    "APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0x" + "a"*40,
    # notional must be 10 or 20
    "APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0x" + "a"*40 + " notional=5",
    "APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0x" + "a"*40 + " notional=50",
    # wallet must be exactly 40 hex after 0x
    "APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0x" + "a"*39 + " notional=10",
    "APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=0x" + "a"*41 + " notional=10",
    # wallet must start with 0x
    "APPROVE_BSC_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet=" + "a"*40 + " notional=10",
    # an execution-class phrase masquerading as the approval
    "APPROVE_BSC_10_20U_PROBE_EXECUTE wallet=0x" + "a"*40 + " notional=10",
    "APPROVE_BSC_10_20U_PROBE_NOW",
    "GO",
    "SHIP_IT",
])
def test_malformed_or_dangerous_phrases_are_rejected(bad_phrase: str) -> None:
    rgx = re.compile(_frozen_regex())
    assert rgx.match(bad_phrase) is None, f"unexpectedly matched: {bad_phrase!r}"


# --- Rejection record shape --------------------------------------------

def test_rejection_record_exists_with_expected_shape() -> None:
    rec = _read("approval_phrase_rejected.json")
    assert rec is not None, "approval_phrase_rejected.json missing"
    assert rec["status"] == "REJECTED"
    assert rec["stage"] == "LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_V1"
    assert rec["phase"] == "A_approval_phrase_validation"
    assert rec["regex_match"] is False
    assert rec["validation_regex"] == _frozen_regex()
    # Both fields must be flagged invalid in the diagnostic
    assert rec["field_diagnostics"]["wallet"]["valid"] is False
    assert rec["field_diagnostics"]["notional"]["valid"] is False


def test_rejection_record_lists_actions_NOT_taken() -> None:
    rec = _read("approval_phrase_rejected.json")
    not_taken = "\n".join(rec["actions_explicitly_NOT_taken"]).lower()
    must_have_negations = [
        "did not call eth_getbalance",
        "did not call erc20.balanceof",
        "did not call erc20.allowance",
        "did not call eth_estimategas",
        "did not load any private key",
        "did not construct any signer",
        "did not call eth_sendtransaction",
        "did not call eth_sendrawtransaction",
        "did not execute approve",
    ]
    for needle in must_have_negations:
        assert needle in not_taken, f"missing negation: {needle!r}"


def test_rejection_record_safety_locks_intact() -> None:
    rec = _read("approval_phrase_rejected.json")
    assert rec["wallet_or_tx_touched"] is False
    assert rec["can_run_probe_now"] is False
    assert rec["manual_approval_required_for_probe"] is True
    assert rec["tiny_canary_allowed"] == "no"
    assert rec["edge_proven"] == "no"


# --- FINAL_VERDICT shape -----------------------------------------------

def test_final_verdict_is_FAIL_with_required_fields() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv is not None
    assert fv["status"] == "FAIL"
    assert fv["stage"] == "LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_V1"
    # The brief lists these fields; all should be present.
    required = {
        "status", "stage", "wallet_address_bound", "wallet_loaded", "signer_created",
        "transaction_sent", "selected_notional_usd", "candidate_pool", "candidate_pair",
        "candidate_fee_tier", "balance_sufficient", "approval_needed_usdt",
        "approval_needed_wbnb", "gas_estimate_success", "market_safe_for_dry_run",
        "wallet_bound_unsigned_package_built", "can_run_probe_now",
        "can_prepare_probe_execution_spec_next", "manual_approval_required_for_execution",
        "edge_proven", "actual_fee_ready", "token_id_available", "tiny_canary_allowed",
        "wallet_or_tx_touched", "recommended_next_stage",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing: {missing}"


def test_final_verdict_all_unlock_flags_are_false() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["wallet_address_bound"] is False  # never bound (phrase rejected)
    assert fv["wallet_loaded"] is False
    assert fv["signer_created"] is False
    assert fv["transaction_sent"] is False
    assert fv["balance_sufficient"] is False
    assert fv["gas_estimate_success"] is False
    assert fv["market_safe_for_dry_run"] is False
    assert fv["wallet_bound_unsigned_package_built"] is False
    assert fv["can_run_probe_now"] is False
    assert fv["can_prepare_probe_execution_spec_next"] is False
    assert fv["manual_approval_required_for_execution"] is True
    assert fv["edge_proven"] == "no"
    assert fv["actual_fee_ready"] is False
    assert fv["token_id_available"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["wallet_or_tx_touched"] is False


def test_recommended_next_stage_in_allowed_set_and_is_fix_repeat() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES
    # A rejected approval phrase logically routes to FIX_REPEAT (not execution spec review).
    assert fv["recommended_next_stage"] == "LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_FIX_REPEAT"
    assert fv["selected_notional_usd"] is None  # never extracted


# --- No script side effects --------------------------------------------

def test_no_new_executable_scripts_in_this_stage() -> None:
    """Rejection-only stage must not introduce a new scripts/* runner."""
    bad = list((REPO_ROOT / "scripts").glob("lp_bsc_*wallet_address_dry_run*"))
    assert not bad, f"this stage should not add scripts; found: {bad}"
