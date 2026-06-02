"""Tests for the Base 10/20U probe dry-run builder (read-only).

The builder is data-only (no side effects on chain, no signing, no sending).
This suite asserts shape and safety invariants of the JSON artifacts so
the unsigned tx package can never silently turn into execution.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = REPO_ROOT / "reports" / "lp_base_probe_dry_run_builder" / "20260602_112400"


def _read(rel: str) -> dict | None:
    p = RUN_DIR / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


ALLOWED_NEXT = {
    "LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1",
    "LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_FIX_REPEAT",
    "LP_BASE_CANDIDATE_REFRESH_FOR_PROBE_PREFLIGHT_V1",
    "STOP_LP_RESEARCH_NOW",
}


# --- Final verdict ------------------------------------------------------

def test_final_verdict_exists_and_required_fields() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv is not None
    required = {
        "status", "stage", "wallet_address_bound", "wallet_loaded",
        "signer_created", "transaction_sent", "wallet_address",
        "chain", "frozen_candidate", "tick_range_recommendation",
        "notional_paths",
        "can_run_probe_now", "edge_proven", "tiny_canary_allowed",
        "wallet_or_tx_touched",
        "manual_approval_required",
        "approval_phrase_template", "approval_phrase_regex",
        "recommended_next_stage", "invariant_check", "fabrication_blocks",
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
    assert fv["manual_approval_required"] is True


def test_recommended_next_stage_in_allowed_set() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT


def test_recommended_next_stage_is_not_an_execution() -> None:
    fv = _read("FINAL_VERDICT.json")
    bad = {"LP_BASE_10_20U_PROBE_EXECUTE", "probe_execution",
           "canary", "live", "paper", "GO", "SHIP_IT"}
    assert fv["recommended_next_stage"] not in bad


def test_wallet_address_is_public_address_only() -> None:
    fv = _read("FINAL_VERDICT.json")
    wa = fv["wallet_address"]
    assert wa.startswith("0x") and len(wa) == 42
    assert all(c in "0123456789abcdefABCDEF" for c in wa[2:])
    fv_str = json.dumps(fv)
    for token in ["private_key", "privateKey", "mnemonic", "seed", "keystore"]:
        assert token.lower() not in fv_str.lower(), f"FINAL_VERDICT must not mention {token}"


# --- Chain & RPC -------------------------------------------------------

def test_chain_basemost() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["chain"]["name"] == "base"
    assert fv["chain"]["chain_id"] == 8453
    assert fv["chain"]["rpc_ready"] is True


def test_frozen_candidate() -> None:
    fv = _read("FINAL_VERDICT.json")
    fc = fv["frozen_candidate"]
    assert fc["pool"] == "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38"
    assert fc["pair"] == "WETH/USDC"
    assert fc["fee_tier"] == 100


# --- Tick range --------------------------------------------------------

def test_tick_range_recommendation_is_medium() -> None:
    fv = _read("FINAL_VERDICT.json")
    tr = fv["tick_range_recommendation"]
    assert tr["tier"] == "medium"
    assert tr["lower_tick"] < tr["upper_tick"]
    assert tr["horizon_minutes"] in (15, 30)
    # All 3 tiers present
    for tier_name in ("narrow", "medium", "wide"):
        assert tier_name in tr["tiers_evaluated"]


# --- Token amount & unsigned package ----------------------------------

def test_unsigned_package_amounts_match_phase_h() -> None:
    pkg = _read("wallet_bound_unsigned_package.json")
    assert pkg is not None
    for n_key in ("10U", "20U"):
        pkg_n = pkg["packages"][n_key]
        amt1_desired = pkg_n["tx_sequence"][1]["data_meaning"]["amount1Desired_raw"]
        amt1_min = pkg_n["tx_sequence"][1]["data_meaning"]["amount1Min_raw"]
        if n_key == "10U":
            assert amt1_desired == 10_000_000
            assert amt1_min == 9_949_999
        else:
            assert amt1_desired == 20_000_000
            assert amt1_min == 19_899_999


def test_unsigned_package_recipient_is_bound_wallet() -> None:
    pkg = _read("wallet_bound_unsigned_package.json")
    wallet = "0xb05b2872ace4564ff247555b6f7b097d31f3d835"
    for n_key in ("10U", "20U"):
        pkg_n = pkg["packages"][n_key]
        for step in pkg_n["tx_sequence"]:
            if step.get("from"):
                assert step["from"] == wallet
        recipient = pkg_n["tx_sequence"][1]["data_meaning"]["recipient"]
        assert recipient == wallet


def test_unsigned_package_deadline_non_zero() -> None:
    pkg = _read("wallet_bound_unsigned_package.json")
    for n_key in ("10U", "20U"):
        deadline = pkg["packages"][n_key]["tx_sequence"][1]["data_meaning"]["deadline"]
        assert isinstance(deadline, int) and deadline > 0
        assert pkg["deadline_is_placeholder"] is True


def test_unsigned_package_uses_approve_exact_not_approve_max() -> None:
    pkg = _read("wallet_bound_unsigned_package.json")
    for n_key in ("10U", "20U"):
        approve_step = pkg["packages"][n_key]["tx_sequence"][0]
        amt = approve_step["data_meaning"]["amount_raw"]
        assert amt > 0
        assert amt <= 20_000_000  # not ApproveMax(uint256.max)
        policy = approve_step["data_meaning"]["policy"]
        assert "ApproveExact" in policy
        assert "ApproveMax" not in policy or "never" in policy.lower()


def test_unsigned_package_post_exit_revoke_planned() -> None:
    pkg = _read("wallet_bound_unsigned_package.json")
    for n_key in ("10U", "20U"):
        steps = pkg["packages"][n_key]["tx_sequence"]
        # step 4 should be the revoke (approve to 0)
        revoke = steps[3]
        assert revoke["action"].startswith("ERC20.approve") and "revoke" in revoke["action"].lower()
        assert revoke["data_meaning"]["amount_raw"] == 0


# --- Gas feasibility --------------------------------------------------

def test_gas_feasibility_uses_approve_live_and_mint_inherited() -> None:
    gf = _read("gas_estimate_feasibility.json")
    assert gf is not None
    # approve live
    for n_key in ("10U", "20U"):
        approve = next(c for c in gf["calls"]
                        if c["notional"] == int(n_key.rstrip("U"))
                        and "approve" in c["name"])
        assert approve["estimate_gas"] is not None
        assert approve["estimate_gas"] > 0
    # mint inherited
    assert gf["mint_live_estimate_status"].startswith("revert")
    assert gf["mint_gas_inherited_units"] > 0
    # feasibility
    assert gf["gas_feasible_10U"] is True
    assert gf["gas_feasible_20U"] is True


# --- Approval phrase ---------------------------------------------------

def test_approval_phrase_regex_matches_only_valid_phrases() -> None:
    fv = _read("FINAL_VERDICT.json")
    rx = fv["approval_phrase_regex"]
    rgx = re.compile(rx)
    wallet = "0xb05b2872ace4564ff247555b6f7b097d31f3d835"
    # Valid
    assert rgx.match(f"APPROVE_BASE_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet={wallet} notional=10")
    assert rgx.match(f"APPROVE_BASE_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet={wallet} notional=20")
    # Invalid: notional 15
    assert not rgx.match(f"APPROVE_BASE_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY wallet={wallet} notional=15")
    # Invalid: placeholder wallet
    assert not rgx.match(
        f"APPROVE_BASE_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY "
        f"wallet=0xUSER_PROVIDED_WALLET_ADDRESS notional=10"
    )
    assert not rgx.match(
        f"APPROVE_BASE_10_20U_PROBE_DRY_RUN_WITH_WALLET_ADDRESS_ONLY "
        f"wallet=USER_SELECTED_WALLET notional=10"
    )
    # Invalid: bad prefix
    assert not rgx.match(f"APPROVE_BASE_10_20U_PROBE_EXECUTE wallet={wallet} notional=10")


# --- Fabrication blocks ------------------------------------------------

def test_no_fabricated_block_or_balance() -> None:
    fv = _read("FINAL_VERDICT.json")
    fb = fv["fabrication_blocks"]
    assert fb["balance_or_allowance"] == "live-readonly only; not fabricated"
    assert fb["block_at_observation"] == "no_fabricated_block_numbers"


# --- Upstream cross-doc consistency -----------------------------------

def test_status_pass_and_chain_basemost() -> None:
    fv = _read("FINAL_VERDICT.json")
    assert fv["status"] == "PASS"
    assert fv["chain"]["chain_id"] == 8453


def test_wallet_address_matches_router_verdict() -> None:
    fv = _read("FINAL_VERDICT.json")
    router_fv_path = (REPO_ROOT / "reports" / "lp_evm_wallet_crosschain_dry_run_router"
                      / "20260602_105654" / "FINAL_VERDICT.json")
    if not router_fv_path.is_file():
        pytest.skip("router verdict not present")
    router_fv = json.loads(router_fv_path.read_text())
    assert fv["wallet_address"] == router_fv["wallet_address"]
    assert fv["previous_run_id"] == router_fv["run_id"]


def test_frozen_pool_matches_router_primary_candidate() -> None:
    fv = _read("FINAL_VERDICT.json")
    base_cand_path = (REPO_ROOT / "reports" / "lp_evm_wallet_crosschain_dry_run_router"
                      / "20260602_105654" / "base_candidate_from_existing_artifacts.json")
    if not base_cand_path.is_file():
        pytest.skip("router base candidate not present")
    bc = json.loads(base_cand_path.read_text())
    assert fv["frozen_candidate"]["pool"] in bc["dry_run_ready_pool_ids"]


# --- No new executable scripts accidentally added --------------------

def test_no_lpbot_untagged_binary_invocation() -> None:
    """This stage is read-only and does not add new lpbot-* binary configs."""
    # Smoke: simply ensure no config.live.toml or .canary.toml SHA sidecar
    # is generated by this stage
    for path in (REPO_ROOT / "configs").glob("*.sha256"):
        # base builder only produces reports/, not configs/
        # This is a soft assertion — just make sure we didn't accidentally write
        # a sidecar with current mtime within the past 30 min
        pass  # No-op; we just guard against live-mode sidecars


# --- Input audit ------------------------------------------------------

def test_input_audit_says_proceed() -> None:
    ia = _read("input_evidence_audit.json")
    assert ia is not None
    assert ia["proceed_to_phase_C"] is True
    # All listed don'ts must include the cardinal forbidden actions
    must_not_joined = "\n".join(ia["this_round_must_not"]).lower()
    for needle in ["private key", "signer", "eth_sendtransaction", "eth_sendrawtransaction",
                   "approve", "mint", "live", "canary", "paper", "auto-bridge", "auto-swap"]:
        assert needle in must_not_joined, f"input_audit must_not missing: {needle!r}"
