"""FIX-E2 contracts for protocol-dispatched full-range AMM NetCover."""
from __future__ import annotations

import pytest

from scripts.lp_netcover_engine_v1_readonly import apply_netcover_gate
from scripts.lp_netcover_inputs_v1_readonly import (
    AMM_HOLDING_HORIZON_MAX_HOURS,
    assemble_amm_netcover_inputs,
    assemble_clmm_netcover_inputs,
    assemble_netcover_inputs,
    constant_product_il_fraction,
)


def _amm(**updates):
    record = {
        "pool": "amm-pool-1",
        "chain": "Base",
        "project": "raydium-amm",
        "protocol_type": "amm_constant_product",
        "holding_horizon_hours": 24.0,
        "is_new_pool": False,
        "fee_apr_24h": 12.0,
        "fee_apr_7d": 10.0,
        "reward_apr": 0.0,
        "tvlUsd": 1_000_000.0,
        "fee_tier": 0.0025,
        "amm_price_ratio": 4.0,
        "amm_price_ratio_source": "measured:test_horizon_endpoints",
    }
    record.update(updates)
    return record


@pytest.mark.parametrize(
    ("price_ratio", "expected"),
    [(1.0, 0.0), (4.0, -0.2), (0.25, -0.2)],
)
def test_constant_product_il_known_analytic_values(price_ratio, expected):
    assert constant_product_il_fraction(price_ratio) == pytest.approx(expected)


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_constant_product_il_invalid_ratio_fails_closed(bad):
    with pytest.raises(ValueError):
        constant_product_il_fraction(bad)


def test_protocol_type_dispatches_to_exclusive_model_paths():
    amm = assemble_netcover_inputs(_amm())
    clmm = assemble_netcover_inputs({
        "pool": "clmm-pool-1",
        "protocol_type": "clmm",
        "project": "uniswap-v3",
        "profile": "PASSIVE",
        "holding_horizon_hours": 168.0,
    })

    assert amm["netcover_model_path"] == "amm_constant_product_v1"
    assert amm["amm_no_range_model"] is True
    assert clmm["netcover_model_path"] == "clmm_vol_sized_range_v1"


def test_same_pool_cross_model_misuse_and_forged_path_fail_closed():
    source = _amm()
    with pytest.raises(ValueError, match="protocol_type=clmm"):
        assemble_clmm_netcover_inputs(source)
    with pytest.raises(ValueError, match="protocol_type=amm_constant_product"):
        assemble_amm_netcover_inputs({**source, "protocol_type": "clmm"})

    forged = assemble_amm_netcover_inputs(source)
    forged["netcover_model_path"] = "clmm_vol_sized_range_v1"
    gated = apply_netcover_gate([forged])[0]
    assert gated["netcover_pass"] is False
    assert gated["netcover_ratio"] is None
    assert gated["rejection_reason"].startswith("NETCOVER_MODEL_PATH_MISMATCH:")


def test_unknown_protocol_type_is_not_inferred_from_project_name():
    assembled = assemble_netcover_inputs(_amm(protocol_type=None))
    gated = apply_netcover_gate([assembled])[0]

    assert assembled["netcover_model_path"] is None
    assert assembled["permanent_fail_closed_reason"] == "NETCOVER_PROTOCOL_TYPE_INVALID"
    assert gated["netcover_pass"] is False
    assert gated["rejection_reason"].startswith("NETCOVER_PROTOCOL_TYPE_INVALID:")


def test_amm_fee_ev_has_whole_pool_dilution_but_no_clmm_share_ratio():
    # Forged CLMM metadata must not influence the AMM result.
    assembled = assemble_amm_netcover_inputs(_amm(
        sigma_pair=999.0,
        fee_capture_share_ratio=1e-12,
        range_pct=0.01,
    ))
    dilution = 1_000_000.0 / (1_000_000.0 + 50.0)
    expected = 50.0 * 10.0 / 100.0 * 0.65 * (24.0 / 8760.0) * dilution

    assert assembled["fee_ev_usd"] == pytest.approx(expected)
    assert assembled["amm_position_dilution_factor"] == pytest.approx(dilution)
    assert assembled["fee_capture_share_ratio"] is None
    assert assembled["fee_capture_target_range_pct"] is None
    assert assembled["il_ev_usd"] == pytest.approx(50.0 * 0.2)


def test_amm_horizon_cap_is_720h_and_excess_is_fail_closed():
    at_cap = assemble_amm_netcover_inputs(
        _amm(holding_horizon_hours=AMM_HOLDING_HORIZON_MAX_HOURS)
    )
    over = assemble_amm_netcover_inputs(_amm(holding_horizon_hours=720.01))
    gated = apply_netcover_gate([over])[0]

    assert at_cap["holding_horizon_hours"] == 720.0
    assert at_cap["amm_horizon_cap_reason"] == "PASS"
    assert over["holding_horizon_hours"] is None
    assert over["amm_horizon_cap_reason"] == "AMM_HORIZON_EXCEEDS_720H"
    assert over["fee_ev_usd"] is None
    assert over["il_ev_usd"] is None
    assert gated["netcover_pass"] is False
    assert gated["rejection_reason"].startswith("NETCOVER_INPUT_MISSING:")


def test_amm_netcover_increases_with_h_for_fixed_price_path_below_cap():
    short = apply_netcover_gate([
        assemble_amm_netcover_inputs(_amm(holding_horizon_hours=24.0))
    ])[0]
    long = apply_netcover_gate([
        assemble_amm_netcover_inputs(_amm(holding_horizon_hours=720.0))
    ])[0]

    assert short["netcover_ratio"] is not None
    assert long["netcover_ratio"] > short["netcover_ratio"]
