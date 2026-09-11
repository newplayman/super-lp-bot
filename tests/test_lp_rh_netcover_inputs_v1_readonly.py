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


def test_fee_apr_zero_int_is_known_zero():
    """fee_apr_pct=0 (int) is a legitimate zero, not unknown.

    Guards against a "defensive" `if not value: return None` added to
    `_to_float`, which would silently turn a real fee=0 into a missing
    input and change the economics while every existing test stays green.
    """
    out = assemble_rh_clmm_inputs(_evidence(fee_apr_pct=0), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["fee_ev_usd"] == 0.0
    assert not _has_missing(out, "fee_apr_pct", "EXTERNAL_DATA_UNAVAILABLE")


def test_fee_apr_zero_float_is_known_zero():
    """fee_apr_pct=0.0 (float) is a legitimate zero, not unknown.

    Same regression guard as the int case: a falsy-check in `_to_float`
    would misclassify a real zero fee as EXTERNAL_DATA_UNAVAILABLE.
    """
    out = assemble_rh_clmm_inputs(_evidence(fee_apr_pct=0.0), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["fee_ev_usd"] == 0.0
    assert not _has_missing(out, "fee_apr_pct", "EXTERNAL_DATA_UNAVAILABLE")


def test_fee_apr_zero_string_is_known_zero():
    """fee_apr_pct="0" (string) parses to a legitimate zero, not unknown.

    Guards the string path of `_to_float`: a falsy-check would drop a
    real "0" fee into missing_inputs.
    """
    out = assemble_rh_clmm_inputs(_evidence(fee_apr_pct="0"), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["fee_ev_usd"] == 0.0
    assert not _has_missing(out, "fee_apr_pct", "EXTERNAL_DATA_UNAVAILABLE")


def test_fee_apr_zero_string_float_is_known_zero():
    """fee_apr_pct="0.0" (string) parses to a legitimate zero, not unknown.

    Guards the string path of `_to_float` for the "0.0" spelling.
    """
    out = assemble_rh_clmm_inputs(_evidence(fee_apr_pct="0.0"), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["fee_ev_usd"] == 0.0
    assert not _has_missing(out, "fee_apr_pct", "EXTERNAL_DATA_UNAVAILABLE")


def test_fee_apr_empty_string_is_unknown():
    """fee_apr_pct="" (empty string) is unknown, not a zero.

    Pins the empty-string half of T32: it must land in missing_inputs as
    EXTERNAL_DATA_UNAVAILABLE, exactly like None.
    """
    out = assemble_rh_clmm_inputs(_evidence(fee_apr_pct=""), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["fee_ev_usd"] is None
    assert _has_missing(out, "fee_apr_pct", "EXTERNAL_DATA_UNAVAILABLE")


def test_fee_apr_unknown_string_is_unknown():
    """fee_apr_pct="unknown" is unknown, not a zero.

    Pins the non-numeric-string half of T32: a placeholder string must
    land in missing_inputs, not be coerced to a number.
    """
    out = assemble_rh_clmm_inputs(_evidence(fee_apr_pct="unknown"), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["fee_ev_usd"] is None
    assert _has_missing(out, "fee_apr_pct", "EXTERNAL_DATA_UNAVAILABLE")


def test_t32_zero_fee_distinct_from_unknown_fee():
    """T32 (PRD L1024): a legal fee=0 must be distinguished from fee unknown.

    Runs both calls in one test and asserts they diverge: the zero call
    yields fee_ev_usd == 0.0 with no missing entry, while the None call
    yields fee_ev_usd is None with a missing entry. The standalone
    fee_apr_pct=None case is already pinned by
    test_missing_fee_apr_marks_input_unavailable; this test adds the
    zero-vs-None divergence in a single assertion. A regression that
    collapses the two would fail here.
    """
    out_zero = assemble_rh_clmm_inputs(_evidence(fee_apr_pct=0), position_usd=Decimal("1000"), horizon_hours=24.0)
    out_none = assemble_rh_clmm_inputs(_evidence(fee_apr_pct=None), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out_zero["fee_ev_usd"] == 0.0
    assert out_none["fee_ev_usd"] is None
    assert not _has_missing(out_zero, "fee_apr_pct", "EXTERNAL_DATA_UNAVAILABLE")
    assert _has_missing(out_none, "fee_apr_pct", "EXTERNAL_DATA_UNAVAILABLE")


# --- RH-02cg: observed gas vs static estimate -------------------------------

def test_evidence_with_observed_gas_usd_prefers_it_and_sets_source():
    # 7. evidence 带 observed_gas_usd -> gas_usd 用它，gas_usd_source == "observed"
    ev = _evidence(observed_gas_usd=0.25, gas_usd_estimate=0.40)
    out = assemble_rh_clmm_inputs(ev, position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["gas_usd"] == 0.25
    assert out["gas_usd_source"] == "observed"
    # apply_netcover_gate preserves gas_usd_source
    gated = apply_netcover_gate([out])[0]
    assert gated.get("gas_usd_source") == "observed"


def test_evidence_without_observed_gas_usd_falls_back_to_static_estimate():
    # 8. evidence 不带 -> 用 gas_usd_estimate，gas_usd_source == "static_pool_meta"
    ev = _evidence(gas_usd_estimate=0.40)
    out = assemble_rh_clmm_inputs(ev, position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["gas_usd"] == 0.40
    assert out["gas_usd_source"] == "static_pool_meta"
    gated = apply_netcover_gate([out])[0]
    assert gated.get("gas_usd_source") == "static_pool_meta"


def test_evidence_with_neither_gas_estimate_fails_closed():
    # 9. 两者都没有 -> gas_usd is None，missing 含 gas_usd_estimate，gas_usd_source is None
    ev = _evidence(gas_usd_estimate=None)
    out = assemble_rh_clmm_inputs(ev, position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["gas_usd"] is None
    assert out["gas_usd_source"] is None
    assert _has_missing(out, "gas_usd_estimate", "CHAIN_DATA_UNAVAILABLE")
    gated = apply_netcover_gate([out])[0]
    assert gated.get("gas_usd_source") is None


# --- RH-03 / T35: CLMM two-leg conversion actual fraction ---------------------

def test_t35_known_leg_fraction_scales_entry_exit_costs_proportionally():
    # 1. 给定一个已知比例（例如 0.3）-> entry/exit 成本恰好是全额的 0.3 倍
    sqrt_price_x96 = int(10 * (2 ** 96))  # price = 100.0 for dec0=6, dec1=6
    ev_full = _evidence(liquidity_raw=1e25, sqrt_price_x96=sqrt_price_x96, dec0=6, dec1=6, fee=3000)
    ev_30 = _evidence(liquidity_raw=1e25, sqrt_price_x96=sqrt_price_x96, dec0=6, dec1=6, fee=3000, leg_fraction=0.3)
    out_full = assemble_rh_clmm_inputs(ev_full, position_usd=Decimal("1000"), horizon_hours=24.0)
    out_30 = assemble_rh_clmm_inputs(ev_30, position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out_30["leg_fraction"] == 0.3
    assert out_30["leg_fraction_status"] == "COMPUTED"
    assert out_30["entry_cost_usd"] == pytest.approx(out_full["entry_cost_usd"] * 0.3)
    assert out_30["exit_cost_usd"] == pytest.approx(out_full["exit_cost_usd"] * 0.3)


def test_t35_missing_leg_fraction_inputs_falls_back_to_full_position():
    # 2. 比例算不出（输入缺失）-> 回退 1.0，成本与修改前完全一致，且 leg_fraction_status 为 FALLBACK_FULL_POSITION:*
    ev_missing = _evidence()  # Default evidence lacks range_pct and leg_fraction
    assert "range_pct" not in ev_missing
    out = assemble_rh_clmm_inputs(ev_missing, position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["leg_fraction"] == 1.0
    assert out["leg_fraction_status"].startswith("FALLBACK_FULL_POSITION:")
    assert out["leg_fraction_status"] == "FALLBACK_FULL_POSITION:RANGE_PCT_MISSING"
    # Cost matches full position calculation (1000U position)
    ev_full = _evidence(leg_fraction=1.0)
    out_full = assemble_rh_clmm_inputs(ev_full, position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["entry_cost_usd"] == out_full["entry_cost_usd"]
    assert out["exit_cost_usd"] == out_full["exit_cost_usd"]


@pytest.mark.parametrize("invalid_frac,expected_reason_prefix", [
    (None, "FALLBACK_FULL_POSITION:NONE"),
    (0, "FALLBACK_FULL_POSITION:ZERO"),
    (0.0, "FALLBACK_FULL_POSITION:ZERO"),
    (1.5, "FALLBACK_FULL_POSITION:EXCEEDS_ONE"),
    (-0.5, "FALLBACK_FULL_POSITION:NEGATIVE"),
])
def test_t35_invalid_leg_fractions_fall_back_to_full_position_and_flag(invalid_frac, expected_reason_prefix):
    # 3. 比例为 None / 0 / 1.5 -> 三种都回退 1.0 并标记（注意 0 也要拒绝：零换腿意味着零成本，那是结论不是输入）
    ev = _evidence(leg_fraction=invalid_frac)
    out = assemble_rh_clmm_inputs(ev, position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["leg_fraction"] == 1.0
    assert out["leg_fraction_status"].startswith("FALLBACK_FULL_POSITION:")
    assert out["leg_fraction_status"] == expected_reason_prefix
    # Costs are full-position costs
    out_full = assemble_rh_clmm_inputs(_evidence(leg_fraction=1.0), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["entry_cost_usd"] == out_full["entry_cost_usd"]
    assert out["exit_cost_usd"] == out_full["exit_cost_usd"]


def test_t35_leg_fraction_one_point_zero_is_computed_status():
    # 4. 比例 = 1.0（真的需要全额换腿）-> 结果与修改前一致，status 为 COMPUTED
    ev = _evidence(leg_fraction=1.0)
    out = assemble_rh_clmm_inputs(ev, position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["leg_fraction"] == 1.0
    assert out["leg_fraction_status"] == "COMPUTED"
    # Matches baseline full-position costs
    out_default = assemble_rh_clmm_inputs(_evidence(), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["entry_cost_usd"] == out_default["entry_cost_usd"]
    assert out["exit_cost_usd"] == out_default["exit_cost_usd"]


def test_t35_leg_fraction_and_status_present_in_all_cost_records():
    # 5. leg_fraction 与 leg_fraction_status 都出现在返回的成本分项里
    # 5a. Successful computed fraction via range_pct
    out_comp = assemble_rh_clmm_inputs(_evidence(range_pct=20.0), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert "leg_fraction" in out_comp
    assert "leg_fraction_status" in out_comp
    assert out_comp["leg_fraction_status"] == "COMPUTED"
    assert 0.0 < out_comp["leg_fraction"] < 1.0

    # 5b. Fallback when range_pct missing
    out_fallback = assemble_rh_clmm_inputs(_evidence(), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert "leg_fraction" in out_fallback
    assert "leg_fraction_status" in out_fallback
    assert out_fallback["leg_fraction"] == 1.0
    assert out_fallback["leg_fraction_status"] == "FALLBACK_FULL_POSITION:RANGE_PCT_MISSING"

    # 5c. Missing cost inputs
    out_no_cost = assemble_rh_clmm_inputs(_evidence(liquidity_raw=None), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert "leg_fraction" in out_no_cost
    assert "leg_fraction_status" in out_no_cost
    assert out_no_cost["leg_fraction"] == 1.0
    assert out_no_cost["leg_fraction_status"] == "FALLBACK_FULL_POSITION:CHAIN_DATA_UNAVAILABLE"

    # 5d. Fail closed (e.g. chain_id mismatch)
    out_fc = assemble_rh_clmm_inputs(_evidence(chain_id=1), position_usd=Decimal("1000"), horizon_hours=24.0)
    assert "leg_fraction" in out_fc
    assert "leg_fraction_status" in out_fc
    assert out_fc["leg_fraction"] == 1.0
    assert out_fc["leg_fraction_status"] == "FALLBACK_FULL_POSITION:RH_CHAIN_ID_MISMATCH"


def test_t35_regression_other_cost_components_invariant_under_fraction():
    # 6. 回归保护：NetCover 的其他成本分项（il_ev / lvr_ev / gas / exit_latency）数值不变
    out_full = assemble_rh_clmm_inputs(_evidence(), position_usd=Decimal("1000"), horizon_hours=24.0)
    out_fraction = assemble_rh_clmm_inputs(_evidence(range_pct=20.0), position_usd=Decimal("1000"), horizon_hours=24.0)

    invariant_keys = ("il_ev_usd", "gas_usd", "exit_latency_loss_usd", "reward_conversion_cost_usd", "fee_ev_usd", "reward_ev_usd")
    for key in invariant_keys:
        assert out_fraction[key] == out_full[key], f"{key} should be invariant under leg_fraction changes"


def test_t35_range_pct_invokes_clmm_token0_value_fraction():
    # 真实计算：range_pct 调用 clmm_token0_value_fraction
    ev = _evidence(range_pct=20.0)
    out = assemble_rh_clmm_inputs(ev, position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["leg_fraction_status"] == "COMPUTED"
    d0, d1 = ev["dec0"], ev["dec1"]
    price = ((ev["sqrt_price_x96"] / 2.0 ** 96) ** 2) * (10 ** d0) / (10 ** d1)
    from scripts.lp_swap_cost_model_v1_readonly import clmm_token0_value_fraction
    expected_fraction = clmm_token0_value_fraction(price, 20.0)
    assert out["leg_fraction"] == pytest.approx(expected_fraction)
    assert 0.0 < out["leg_fraction"] < 1.0


def test_t35_range_pct_calculation_error_falls_back():
    # 越界计算：range_pct >= 100 报错回退
    ev = _evidence(range_pct=150.0)
    out = assemble_rh_clmm_inputs(ev, position_usd=Decimal("1000"), horizon_hours=24.0)
    assert out["leg_fraction"] == 1.0
    assert out["leg_fraction_status"].startswith("FALLBACK_FULL_POSITION:CALCULATION_ERROR:")


