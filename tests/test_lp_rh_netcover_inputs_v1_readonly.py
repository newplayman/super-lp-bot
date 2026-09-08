"""Contracts for the RH NetCover input assembler (pure, no network)."""
from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.lp_netcover_engine_v1_readonly import apply_netcover_gate, netcover_model_path
from scripts.lp_netcover_inputs_v1_readonly import LVR_COEFFICIENT_MODEL
from scripts.lp_rh_netcover_inputs_v1_readonly import (
    REQUIRED_ENGINE_KEYS,
    assemble_rh_clmm_inputs,
    classify_zero_candidate,
    position_cap_for_rh,
)


def _evidence(**updates):
    """Complete RH evidence that passes all gates."""
    rec = {
        "chain_id": 4663,
        "attestation_status": "ATTESTED_SAME_BLOCK",
        "protocol": "v3",
        "block_hash": "0xabc123",
        "fee_apr_pct": 12.0,
        "reward_apr_pct": 5.0,
        "reward_verified": True,
        "sigma_daily": 0.03,
        "liquidity_raw": 2_641_450_665_466_979_248,
        "sqrt_price_x96": 4_000_000_000_000_000_000,
        "fee": 500,
        "dec0": 18,
        "dec1": 6,
        "gas_usd_estimate": 0.08,
        "tvl_usd": 1_000_000.0,
        "active_liquidity_notional_usd": 500_000.0,
    }
    rec.update(updates)
    return rec


def test_all_nine_keys_populated_on_complete_evidence():
    out = assemble_rh_clmm_inputs(_evidence(), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["protocol_type"] == "clmm"
    assert out["netcover_model_path"] == netcover_model_path("clmm")
    assert out["lvr_coefficient"] == LVR_COEFFICIENT_MODEL
    assert out["capital_usd"] == 1000.0
    assert out["holding_horizon_hours"] == 24.0
    assert out["rh_evidence_block_hash"] == "0xabc123"
    assert out["missing_inputs"] == []
    for key in REQUIRED_ENGINE_KEYS:
        assert out[key] is not None, f"{key} should be populated"
    assert out["fee_ev_usd"] > 0
    assert out["reward_ev_usd"] > 0
    assert out["il_ev_usd"] > 0
    assert out["entry_cost_usd"] > 0
    assert out["exit_cost_usd"] > 0
    assert out["gas_usd"] == 0.08
    assert out["reward_conversion_cost_usd"] == 0.0
    assert out["exit_latency_loss_usd"] > 0


def test_fee_ev_formula():
    out = assemble_rh_clmm_inputs(_evidence(fee_apr_pct=10.0), position_usd=Decimal("1000"), horizon_hours=24.0)
    expected = 1000.0 * 10.0 / 100.0 * 24.0 / 8760.0
    assert out["fee_ev_usd"] == pytest.approx(expected, rel=1e-9)


def test_reward_unverified_zeroes_reward_ev():
    out = assemble_rh_clmm_inputs(_evidence(reward_verified=False), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["reward_ev_usd"] == 0.0
    assert out["reward_unverified_reason"] == "reward_unverified_or_missing"


def test_reward_missing_zeroes_reward_ev():
    out = assemble_rh_clmm_inputs(_evidence(reward_apr_pct=None), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["reward_ev_usd"] == 0.0
    assert out["reward_unverified_reason"] == "reward_unverified_or_missing"


def test_chain_id_mismatch_fail_closed():
    out = assemble_rh_clmm_inputs(_evidence(chain_id=1), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["permanent_fail_closed_reason"] == "RH_CHAIN_ID_MISMATCH"
    for key in REQUIRED_ENGINE_KEYS:
        assert out[key] is None


def test_not_attested_fail_closed():
    out = assemble_rh_clmm_inputs(_evidence(attestation_status="DISCOVERED_NOT_ATTESTED"),
                                  position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["permanent_fail_closed_reason"] == "DISCOVERED_NOT_ATTESTED"
    for key in REQUIRED_ENGINE_KEYS:
        assert out[key] is None


def test_unsupported_protocol_fail_closed():
    out = assemble_rh_clmm_inputs(_evidence(protocol="v4"), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["permanent_fail_closed_reason"] == "UNSUPPORTED_PROTOCOL"
    for key in REQUIRED_ENGINE_KEYS:
        assert out[key] is None


def _has_missing(out, field, reason):
    return {"field": field, "reason": reason} in out["missing_inputs"]


def test_missing_fee_apr_marks_input_unavailable():
    out = assemble_rh_clmm_inputs(_evidence(fee_apr_pct=None), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["fee_ev_usd"] is None
    assert _has_missing(out, "fee_apr_pct", "EXTERNAL_DATA_UNAVAILABLE")


def test_missing_sigma_marks_input_unavailable():
    out = assemble_rh_clmm_inputs(_evidence(sigma_daily=None), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["il_ev_usd"] is None
    assert _has_missing(out, "sigma_daily", "EXTERNAL_DATA_UNAVAILABLE")


def test_missing_cost_fields_zeroes_costs():
    out = assemble_rh_clmm_inputs(_evidence(liquidity_raw=None), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["entry_cost_usd"] is None
    assert out["exit_cost_usd"] is None
    assert out["slippage_usd"] is None
    assert _has_missing(out, "liquidity_raw", "CHAIN_DATA_UNAVAILABLE")


def test_missing_gas_marks_input_unavailable():
    out = assemble_rh_clmm_inputs(_evidence(gas_usd_estimate=None), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["gas_usd"] is None
    assert _has_missing(out, "gas_usd_estimate", "CHAIN_DATA_UNAVAILABLE")


def test_il_ev_formula():
    out = assemble_rh_clmm_inputs(_evidence(sigma_daily=0.04), position_usd=Decimal("1000"), horizon_hours=24.0)
    expected = 1000.0 * 0.04 ** 2 * (24.0 / 24.0) / 8.0
    assert out["il_ev_usd"] == pytest.approx(expected, rel=1e-9)


def test_assembled_record_passes_engine_model_path_check():
    out = assemble_rh_clmm_inputs(_evidence(), position_usd=Decimal("1000"), horizon_hours=24.0)
    gate = apply_netcover_gate([out])[0]
    rej = gate.get("rejection_reason") or ""
    assert "NETCOVER_MODEL_PATH_MISMATCH" not in rej
    assert "NETCOVER_INPUT_MISSING" not in rej
    assert gate.get("netcover") is not None and math.isfinite(gate["netcover"])


def test_position_cap_valid_tvl():
    out = position_cap_for_rh(_evidence(), tier_configured_max=Decimal("10000"))
    assert out["position_cap_pass"] is True
    assert out["position_cap_usd"] is not None
    assert out["position_cap_reason"] is None


def test_position_cap_missing_tvl():
    out = position_cap_for_rh(_evidence(tvl_usd=None), tier_configured_max=Decimal("10000"))
    assert out["position_cap_pass"] is False
    assert out["position_cap_usd"] is None
    assert out["position_cap_reason"] == "INV-TVLSHARE-01_INPUT_MISSING_OR_INVALID"


def test_position_cap_zero_tvl():
    out = position_cap_for_rh(_evidence(tvl_usd=0), tier_configured_max=Decimal("10000"))
    assert out["position_cap_pass"] is False
    assert out["position_cap_usd"] is None


def test_classify_unsupported():
    rec = {"permanent_fail_closed_reason": "UNSUPPORTED_PROTOCOL"}
    assert classify_zero_candidate(rec) == "UNSUPPORTED"


def test_classify_inputs_unavailable():
    rec = {"missing_inputs": [{"field": "x", "reason": "y"}], "netcover_pass": None}
    assert classify_zero_candidate(rec) == "INPUTS_UNAVAILABLE"


def test_classify_computed_pass():
    rec = {"missing_inputs": [], "netcover_pass": True}
    for k in REQUIRED_ENGINE_KEYS:
        rec[k] = 1.0
    assert classify_zero_candidate(rec) == "COMPUTED_PASS"


def test_classify_computed_fail():
    rec = {"missing_inputs": [], "netcover_pass": False, "netcover": 0.5}
    for k in REQUIRED_ENGINE_KEYS:
        rec[k] = 1.0
    assert classify_zero_candidate(rec) == "COMPUTED_FAIL"


def test_classify_computed_fail_requires_finite_netcover():
    rec = {"missing_inputs": [], "netcover_pass": False, "netcover": None}
    for k in REQUIRED_ENGINE_KEYS:
        rec[k] = 1.0
    assert classify_zero_candidate(rec) == "INPUTS_UNAVAILABLE"


@pytest.mark.parametrize("prefix,status", [
    ("NETCOVER_MODEL_PATH_MISMATCH:", "UNSUPPORTED"),
    ("NETCOVER_PROTOCOL_TYPE_INVALID:", "UNSUPPORTED"),
    ("NETCOVER_INPUT_MISSING:", "INPUTS_UNAVAILABLE"),
    ("NETCOVER_INPUT_INVALID:", "INPUTS_UNAVAILABLE"),
])
def test_classify_rejection_prefix_maps_to_status(prefix, status):
    rec = {"rejection_reason": prefix + "x", "netcover_pass": False, "netcover": 0.5}
    for k in REQUIRED_ENGINE_KEYS:
        rec[k] = 1.0
    assert classify_zero_candidate(rec) == status


def test_classify_default_inputs_unavailable():
    rec = {"missing_inputs": [], "netcover_pass": None}
    for k in REQUIRED_ENGINE_KEYS:
        rec[k] = 1.0
    assert classify_zero_candidate(rec) == "INPUTS_UNAVAILABLE"


def test_cli_end_to_end(tmp_path):
    from scripts.lp_rh_netcover_inputs_v1_readonly import main
    evidence_file = tmp_path / "evidence.json"
    out_file = tmp_path / "out.json"
    evidence_file.write_text(json.dumps([_evidence()]))
    rc = main(["--evidence-json", str(evidence_file), "--out", str(out_file),
               "--position-usd", "1000", "--horizon-hours", "24"])
    assert rc == 0
    data = json.loads(out_file.read_text())
    assert data["count"] == 1
    rec = data["results"][0]
    assert rec["primary_status"] in ("COMPUTED_PASS", "COMPUTED_FAIL", "INPUTS_UNAVAILABLE")
    assert "netcover_pass" in rec
