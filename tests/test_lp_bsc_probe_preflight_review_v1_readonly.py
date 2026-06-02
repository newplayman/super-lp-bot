"""Tests for the BSC 10/20U probe preflight review artifacts (read-only).

The review is data-only (no Python script under scripts/). This test
suite asserts the shape and safety invariants of the JSON artifacts
produced by Phases B-H so that future agents cannot accidentally
weaken them.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEW_DIR_GLOB = REPO_ROOT / "reports" / "lp_bsc_probe_preflight_review"


def _latest_run_dir() -> Path:
    runs = sorted(p for p in REVIEW_DIR_GLOB.iterdir() if p.is_dir())
    assert runs, f"no review run dirs under {REVIEW_DIR_GLOB}"
    return runs[-1]


def _read(rel_path: str) -> dict | None:
    p = _latest_run_dir() / rel_path
    if not p.is_file():
        return None
    return json.loads(p.read_text())


ALLOWED_NEXT_STAGES = {
    "LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1",
    "LP_BSC_10_20U_PROBE_PREFLIGHT_FIX_REPEAT",
    "LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1",
    "STOP_LP_RESEARCH_NOW",
}


# --- Final verdict invariants -------------------------------------------

def test_final_verdict_exists_and_has_required_fields() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv is not None, "FINAL_VERDICT.json missing"
    required = {
        "status", "stage", "candidate_pool", "candidate_pair",
        "candidate_fee_tier", "candidate_notional_usd", "candidate_hold_window",
        "fee_ready", "quote_ready", "tick_ready", "cost_ready",
        "realistic_positive_ev", "near_break_even",
        "actual_fee_ready", "token_id_available",
        "probe_preflight_review_complete", "dry_run_builder_allowed_next",
        "can_run_probe_now", "manual_approval_required_for_probe",
        "edge_proven", "tiny_canary_allowed", "wallet_or_tx_touched",
        "recommended_next_stage",
    }
    missing = required - set(fv.keys())
    assert not missing, f"FINAL_VERDICT missing fields: {missing}"


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False, "can_run_probe_now MUST be false"
    assert fv["manual_approval_required_for_probe"] is True
    assert fv["edge_proven"] == "no"
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["wallet_or_tx_touched"] is False
    assert fv["realistic_positive_ev"] is False  # honest about EV status
    assert fv["actual_fee_ready"] is False       # only a probe can flip this
    assert fv["token_id_available"] is False     # only a probe can flip this


def test_final_verdict_stage_matches_review() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["stage"] == "LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1"


def test_final_verdict_recommended_next_stage_in_allowed_set() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_dry_run_builder_only_when_gates_complete() -> None:
    fv = _read("FINAL_VERDICT.json")
    if fv["recommended_next_stage"] == "LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1":
        for gate in ["fee_ready", "quote_ready", "tick_ready", "cost_ready",
                     "probe_preflight_review_complete"]:
            assert fv[gate] is True, f"dry_run_builder recommended but {gate} not true"
        assert fv["dry_run_builder_allowed_next"] is True


# --- Approval packet invariants -----------------------------------------

def test_approval_packet_default_is_safe() -> None:
    ap = _read("bsc_10_20u_probe_approval_packet.json")
    assert ap is not None
    assert ap["default_one_line_conclusion"] == "DO_NOT_EXECUTE_PROBE_YET"
    assert "APPROVE_DRY_RUN_BUILDER" in ap["one_line_conclusion_alternatives"]
    assert "DO_NOT_EXECUTE_PROBE_YET" in ap["one_line_conclusion_alternatives"]
    assert ap["can_run_probe_now"] is False
    assert ap["manual_approval_required_for_probe"] is True


def test_approval_packet_does_not_authorize_execution() -> None:
    ap = _read("bsc_10_20u_probe_approval_packet.json")
    # one_line_conclusion may be APPROVE_DRY_RUN_BUILDER but that DOES NOT
    # mean execution is authorized. The semantics must say so explicitly.
    semantics = ap.get("conclusion_means", "").lower()
    must_contain_any_of = [
        "does not unlock execution",
        "does not authorize",
        "do not execute",
        "not unlock execution",
    ]
    assert any(s in semantics for s in must_contain_any_of), (
        f"conclusion_means must clarify execution is not authorized; got: {semantics!r}"
    )
    # And the hard gates must still be locked at the verdict level.
    assert ap["can_run_probe_now"] is False
    assert ap["manual_approval_required_for_probe"] is True


# --- Risk-limits invariants ---------------------------------------------

def test_risk_limits_cap_funds_at_20_usd() -> None:
    rl = _read("bsc_10_20u_probe_risk_limits.json")
    assert rl is not None
    assert rl["fund_limits"]["max_total_funds_usd"] == 20
    assert rl["fund_limits"]["max_single_pool_count"] == 1
    assert rl["fund_limits"]["no_auto_repeat"] is True
    assert rl["fund_limits"]["no_multi_pool"] is True


def test_risk_limits_have_all_required_stop_conditions() -> None:
    rl = _read("bsc_10_20u_probe_risk_limits.json")
    stop_ids = {s["id"] for s in rl["stop_conditions"]}
    must_have = {"S1_quote_drift", "S2_gas_spike", "S3_tick_out_of_range",
                 "S4_pool_liquidity_collapse", "S5_fee_velocity_stale",
                 "S6_rpc_unstable", "S7_token_approval_unexpected",
                 "S8_position_tokenId_not_detected",
                 "S9_exit_quote_unavailable", "S10_negative_mark_to_market"}
    missing = must_have - stop_ids
    assert not missing, f"missing stop conditions: {missing}"


def test_risk_limits_forbid_approve_max() -> None:
    rl = _read("bsc_10_20u_probe_risk_limits.json")
    assert rl["approval_policy"]["approve_strategy"] == "ApproveExact"
    assert rl["approval_policy"]["approve_max_forbidden"] is True
    assert rl["approval_policy"]["post_exit_revoke_required"] is True


# --- Dry-run builder spec invariants ------------------------------------

def test_dry_run_builder_forbids_signing_and_sending() -> None:
    ds = _read("bsc_probe_dry_run_builder_spec.json")
    assert ds is not None
    forbidden = ds["dry_run_builder_forbidden_operations"]
    # The exact operations that must be in the forbidden list.
    must_forbid = [
        "eth_sendTransaction",
        "eth_sendRawTransaction",
        "personal_sign",
        "personal_signTransaction",
        "eth_sign",
        "eth_signTransaction",
        "load private key from disk, env, keystore, or KMS",
        "construct any signer object",
    ]
    for op in must_forbid:
        assert op in forbidden, f"dry-run builder MUST forbid: {op!r}"


def test_dry_run_builder_does_not_write_chain_state() -> None:
    ds = _read("bsc_probe_dry_run_builder_spec.json")
    assert ds["dry_run_builder_writes_to_db"] is False
    assert ds["dry_run_builder_modifies_any_chain_state"] is False
    assert ds["post_emit_manual_approval_required"] is True
    assert ds["post_approval_execution_is_a_separate_future_stage"] is True


# --- Telemetry / DB schema invariants -----------------------------------

def test_telemetry_does_not_create_production_tables() -> None:
    t = _read("bsc_probe_required_telemetry.json")
    assert t is not None
    assert t["tables_created_this_round"] is False
    assert t["tables_must_be_separate_from_production_lpbot"] is True
    proposed = {tbl["name"] for tbl in t["db_schema_proposals"]["tables"]}
    must_have_tables = {
        "lp_probe_preflight_review_v1",
        "lp_probe_execution_ledger_v1",
        "lp_probe_position_fee_trace_v1",
        "lp_probe_exit_trace_v1",
    }
    missing = must_have_tables - proposed
    assert not missing, f"missing schema proposals: {missing}"


# --- Candidate-review honesty -------------------------------------------

def test_candidate_review_is_honest_about_negative_ev() -> None:
    cr = _read("bsc_probe_candidate_review.json")
    assert cr is not None
    assert cr["ev_status_realistic"]["realistic_positive_ev"] is False
    # The best realistic EV at 20U/15m must be strictly negative.
    best_ev = Decimal(cr["ev_status_realistic"]["20u_15m"])
    assert best_ev < 0, f"expected negative EV at realistic 20U/15m, got {best_ev}"


# --- Input audit ---------------------------------------------------------

def test_input_audit_confirms_upstream_pass() -> None:
    ia = _read("input_evidence_audit.json")
    assert ia is not None
    assert ia["previous_stage_pass"] is True
    assert ia["can_run_probe_now"] is False
    assert ia["manual_approval_required_for_probe"] is True
    assert all(ia["inputs_read"].values()), f"some inputs missing: {ia['inputs_read']}"


# --- Cross-doc consistency ----------------------------------------------

def test_candidate_pool_consistent_across_docs() -> None:
    fv = _read("FINAL_VERDICT.json")
    ap = _read("bsc_10_20u_probe_approval_packet.json")
    cr = _read("bsc_probe_candidate_review.json")
    assert fv["candidate_pool"] == ap["candidate"]["pool_address"] == cr["candidate"]["pool_address"]
    assert fv["candidate_pair"] == "USDT/WBNB"
    assert fv["candidate_fee_tier"] == 100
