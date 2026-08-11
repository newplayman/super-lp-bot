import base64
import math

import pytest

from scripts.lp_solana_stock_stage2_v1_readonly import (
    _select_unique,
    _clmm_active_depth,
    _decode_raydium_pool_state,
    _replay_price_path,
    assemble_clmm_stage2_netcover,
    assess,
    recompute_clmm_economics,
    recompute_economics,
    replay_recent_swaps,
    v2_il,
    verify_onchain,
    solana_exit_and_sell_evidence,
)


def test_v2_il_known_values():
    assert v2_il(1) == 0
    assert v2_il(4) == pytest.approx(-0.2)
    assert v2_il(0.25) == pytest.approx(-0.2)


def test_unique_match_fails_closed_when_ambiguous_or_far():
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        _select_unique([{"tvl_usd": 100}, {"tvl_usd": 101}], 100)
    with pytest.raises(ValueError, match="NO_TVL_MATCH"):
        _select_unique([{"tvl_usd": 200}], 100)


def test_amm_recomputes_real_fee_and_il_but_clmm_needs_replay():
    pool = {
        "protocol_type": "amm_constant_product", "tvl_usd": 100_000,
        "fees_24h_usd": 100, "volume_24h_usd": 10_000, "fee_rate": 0.01,
        "price_min_24h": 100, "price_max_24h": 400,
    }
    result = recompute_economics(pool)
    assert result["passed"] is True
    assert result["recomputed_fee_apr_pct"] == pytest.approx(36.5)
    assert result["il_24h_worst"] == pytest.approx(-0.2)
    pool["protocol_type"] = "clmm"
    assert recompute_economics(pool)["passed"] is False


class _RPC:
    def __init__(self, values):
        self.values = values

    def call(self, method, params):
        assert method == "getMultipleAccounts"
        return {"context": {"slot": 1}, "value": self.values}


def test_chain_verification_checks_owner_executable_vaults_and_mints():
    pool = {
        "pool_address": "pool", "program_id": "program", "vault_a": "va", "vault_b": "vb",
        "mint_a": "ma", "mint_b": "mb",
        "mint_a_owner": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
        "mint_b_owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    }
    values = [
        {"owner": "program", "executable": False},
        {"owner": "BPFLoaderUpgradeab1e11111111111111111111111", "executable": True},
        {"owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "executable": False},
        {"owner": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "executable": False},
        {"owner": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "executable": False},
        {"owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "executable": False},
    ]
    assert verify_onchain(pool, _RPC(values))["passed"] is True
    values[0]["owner"] = "wrong"
    assert verify_onchain(pool, _RPC(values))["passed"] is False


class _ReplayRPC:
    def call(self, method, params):
        if method == "getSignaturesForAddress":
            return [{"signature": "sig"}]
        assert method == "getTransaction"
        return {
            "slot": 7, "blockTime": 8,
            "transaction": {"message": {"accountKeys": ["va", "vb"]}},
            "meta": {
                "logMessages": ["Program log: Instruction: SwapV2"],
                "preTokenBalances": [
                    {"accountIndex": 0, "mint": "ma", "uiTokenAmount": {"amount": "1000", "decimals": 2}},
                    {"accountIndex": 1, "mint": "mb", "uiTokenAmount": {"amount": "2000", "decimals": 2}},
                ],
                "postTokenBalances": [
                    {"accountIndex": 0, "mint": "ma", "uiTokenAmount": {"amount": "1100", "decimals": 2}},
                    {"accountIndex": 1, "mint": "mb", "uiTokenAmount": {"amount": "1800", "decimals": 2}},
                ],
            },
        }


def test_real_swap_replay_uses_vault_deltas_and_blocks_unscaled_token2022():
    pool = {"pool_address": "pool", "vault_a": "va", "vault_b": "vb",
            "mint_a": "ma", "mint_b": "mb", "mint_a_tags": [], "mint_b_tags": []}
    result = replay_recent_swaps(pool, _ReplayRPC(), signature_limit=1)
    assert result["swap_count"] == 1
    assert result["swaps"][0]["raw_ui_price_b_per_a"] == pytest.approx(2)
    assert result["economic_price_complete"] is True
    pool["mint_a_tags"] = ["scaledUiAmountConfig"]
    result = replay_recent_swaps(pool, _ReplayRPC(), signature_limit=1)
    assert result["economic_price_complete"] is False


def test_clmm_replay_economics_uses_active_stable_depth_and_raw_price_path():
    pool = {
        "mint_a": "stock", "mint_b": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "tvl_usd": 100_000, "fees_24h_usd": 100, "volume_24h_usd": 10_000,
        "fee_rate": 0.01,
    }
    state = {
        "active_liquidity_raw": 1_000_000_000_000,
        "sqrt_price_x64": 1 << 64, "decimals_a": 6, "decimals_b": 6,
    }
    replay = {"swaps": [
        {"raw_ui_price_b_per_a": math.exp(0.0324 * index),
         "block_time": 1_700_000_000 + index * 3600}
        for index in range(21)
    ]}

    result = recompute_clmm_economics(pool, state, replay)

    assert result["passed"] is True
    assert result["recomputed_fee_apr_pct"] == pytest.approx(36.5)
    assert result["exit_depth_usd"] > 0
    assert result["exit_slippage_bps"] > 0
    assert result["sigma_pair"] == pytest.approx(0.0324)
    assert result["sigma_swap_count"] == 21
    assert result["sigma_sample_span_hours"] == pytest.approx(20.0)
    assert 1.0 < result["recommend_range_pct"] < 20.0


def test_clmm_sigma_sample_insufficiency_cannot_produce_a_range():
    pool = {
        "mint_a": "stock", "mint_b": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "tvl_usd": 100_000, "fees_24h_usd": 100, "volume_24h_usd": 10_000,
        "fee_rate": 0.01,
    }
    state = {
        "active_liquidity_raw": 1_000_000_000_000,
        "sqrt_price_x64": 1 << 64, "decimals_a": 6, "decimals_b": 6,
    }
    replay = {"swaps": [
        {"raw_ui_price_b_per_a": 1.0 + index * 0.01,
         "block_time": 1_700_000_000 + index * 600}
        for index in range(3)
    ]}
    result = recompute_clmm_economics(pool, state, replay)
    assert result["passed"] is False
    assert result["reason"] == "SIGMA_SAMPLE_INSUFFICIENT:n=3,span=0.3h"
    assert "recommend_range_pct" not in result
    netcover = assemble_clmm_stage2_netcover(pool, state, result)
    assert netcover["passed"] is False
    assert "inputs" not in netcover


def test_clmm_depth_requires_an_onchain_stable_leg_anchor():
    with pytest.raises(ValueError, match="USD_ANCHOR"):
        _clmm_active_depth(
            {"mint_a": "stock-a", "mint_b": "stock-b"},
            {"active_liquidity_raw": 1_000_000, "sqrt_price_x64": 1 << 64,
             "decimals_a": 6, "decimals_b": 6},
        )


def test_protocol_type_mismatch_is_an_explicit_stage2_fail_closed(monkeypatch):
    import scripts.lp_solana_stock_stage2_v1_readonly as stage2

    monkeypatch.setattr(stage2, "resolve_pool", lambda *_: {
        "protocol_type": "clmm", "pool_address": "pool",
    })

    result = assess(
        {"pool_id": "id", "protocol_type": "amm_constant_product"}, object(),
        http=lambda _: {}, replay_limit=0,
    )

    assert result["stage2_pass"] is False
    assert result["reason"] == "PROTOCOL_TYPE_MISMATCH"
    assert result["protocol_type_mismatch_alert"] == "PROTOCOL_TYPE_MISMATCH"


def test_raydium_clmm_state_decodes_published_pool_layout_offsets():
    raw = bytearray(1544)
    raw[235:237] = (120).to_bytes(2, "little")
    raw[237:253] = (123_456_789).to_bytes(16, "little")
    raw[253:269] = (1 << 64).to_bytes(16, "little")
    raw[269:273] = (-120).to_bytes(4, "little", signed=True)
    response = {"value": {
        "owner": "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", "space": 1544,
        "data": [base64.b64encode(raw).decode("ascii"), "base64"],
    }}

    state = _decode_raydium_pool_state(response, decimals_a=8, decimals_b=6)

    assert state["tick_spacing"] == 120
    assert state["active_liquidity_raw"] == 123_456_789
    assert state["sqrt_price_x64"] == 1 << 64
    assert state["tick_current"] == -120


def test_solana_exit_and_sell_evidence_has_simulation_success_and_fail_closed_sides():
    replay = {"swaps": [
        {"raw_ui_price_b_per_a": 1.0}, {"raw_ui_price_b_per_a": 1.01},
    ]}
    economics = {"exit_slippage_bps": 10.0, "reason": "PASS"}
    success = solana_exit_and_sell_evidence(replay, economics, {"value": {"err": None}})
    assert success["exit_verdict"] == "EXITABLE_CLEAN"
    assert success["sell_simulation_ok"] is True
    assert success["known_honeypot"] is False and success["sell_tax_pct"] == 0
    failed = solana_exit_and_sell_evidence(replay, economics)
    assert failed["sell_simulation_ok"] is False
    assert failed["sell_simulation_reason"] == "FAIL_CLOSED_UNSIGNED_SELL_SIMULATION_UNAVAILABLE"
