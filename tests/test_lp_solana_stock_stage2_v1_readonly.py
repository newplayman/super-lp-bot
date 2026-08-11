import base64
import math

import pytest

from scripts.lp_solana_stock_stage2_v1_readonly import (
    _select_unique,
    _clmm_active_depth,
    _decode_raydium_pool_state,
    _replay_price_path,
    _stage2_failure_reason,
    assemble_clmm_stage2_netcover,
    assess,
    measure_solana_transaction_cost,
    read_solana_reward_evidence,
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


def test_replay_drops_dust_before_price_path_and_il_calculation():
    class DustRPC:
        def call(self, method, params):
            if method == "getSignaturesForAddress":
                return [{"signature": f"s{index}"} for index in range(43)]
            assert method == "getTransaction"
            index = int(params[0][1:])
            stock_delta, usdc_delta = (
                (1e-8, 5_000.0) if index == 0
                else (10.0, 3_090.0 + index)
            )
            return {
                "slot": index, "blockTime": 1_700_000_000 + index * 600,
                "transaction": {"message": {"accountKeys": ["va", "vb"]}},
                "meta": {"fee": 5_000, "logMessages": ["swap"],
                         "preTokenBalances": [
                             {"accountIndex": 0, "mint": "ma", "uiTokenAmount": {"amount": "0", "decimals": 8}},
                             {"accountIndex": 1, "mint": "mb", "uiTokenAmount": {"amount": "0", "decimals": 6}},
                         ], "postTokenBalances": [
                             {"accountIndex": 0, "mint": "ma", "uiTokenAmount": {"amount": str(round(stock_delta * 1e8)), "decimals": 8}},
                             {"accountIndex": 1, "mint": "mb", "uiTokenAmount": {"amount": str(round(usdc_delta * 1e6)), "decimals": 6}},
                         ]},
            }

    replay = replay_recent_swaps(
        {"pool_address": "pool", "vault_a": "va", "vault_b": "vb", "mint_a": "ma", "mint_b": "mb"},
        DustRPC(), signature_limit=60,
    )
    path = _replay_price_path(replay, require_sigma_sample=True)

    assert replay["dropped_dust_swaps"] == 1
    assert replay["dropped_price_outlier_swaps"] == 0
    assert replay["price_cleaning_passed"] is True
    assert replay["swap_count"] == 42
    assert path["price_ratio_worst"] < 2.0


def test_price_path_drops_median_outlier_and_fails_closed_when_prevalent():
    replay = {"swaps": [
        {"raw_ui_price_b_per_a": 309.0 + index, "block_time": 1_700_000_000 + index * 600}
        for index in range(42)
    ] + [{"raw_ui_price_b_per_a": 5e11, "block_time": 1_700_100_000}]}

    path = _replay_price_path(replay, require_sigma_sample=True)

    assert path["dropped_median_price_samples"] == 1
    assert path["price_ratio_worst"] < 2.0
    with pytest.raises(ValueError, match="PRICE_OUTLIER_DROP_RATE_EXCEEDED"):
        _replay_price_path({"swaps": [
            {"raw_ui_price_b_per_a": 309.0, "block_time": 1_700_000_000},
            {"raw_ui_price_b_per_a": 5e11, "block_time": 1_700_000_600},
            {"raw_ui_price_b_per_a": 5e11, "block_time": 1_700_001_200},
        ]})


def test_replay_paginates_until_the_configured_three_hour_span():
    class PagedRPC:
        def __init__(self):
            self.pages = 0

        def call(self, method, params):
            if method == "getSignaturesForAddress":
                page = self.pages
                self.pages += 1
                if page >= 2:
                    return []
                return [{"signature": f"s{index}"} for index in range(page * 10, page * 10 + 10)]
            assert method == "getTransaction"
            index = int(params[0][1:])
            return {
                "slot": index, "blockTime": 1_700_000_000 + index * 600,
                "transaction": {"message": {"accountKeys": ["va", "vb"]}},
                "meta": {"fee": 5_000, "logMessages": ["swap"],
                         "preTokenBalances": [
                             {"accountIndex": 0, "mint": "ma", "uiTokenAmount": {"amount": "1000", "decimals": 2}},
                             {"accountIndex": 1, "mint": "mb", "uiTokenAmount": {"amount": "2000", "decimals": 2}},
                         ], "postTokenBalances": [
                             {"accountIndex": 0, "mint": "ma", "uiTokenAmount": {"amount": "1100", "decimals": 2}},
                             {"accountIndex": 1, "mint": "mb", "uiTokenAmount": {"amount": "1800", "decimals": 2}},
                         ]},
            }

    result = replay_recent_swaps(
        {"pool_address": "pool", "vault_a": "va", "vault_b": "vb", "mint_a": "ma", "mint_b": "mb"},
        PagedRPC(), signature_limit=10, target_span_hours=3.0, max_pages=3,
    )
    assert result["pages_fetched"] == 2
    assert result["swap_count"] == 20
    assert result["actual_span_hours"] > 3.0
    assert result["replay_stop_reason"] == "TARGET_REACHED"


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
    # sigma_per_swap remains the raw audit number.  The range and NetCover use
    # fixed five-minute-bar daily volatility instead, so hourly moves are
    # spread across their twelve elapsed five-minute intervals.
    assert result["sigma_per_swap"] == pytest.approx(0.0324)
    assert result["sigma_pair"] == pytest.approx(result["sigma_daily"])
    assert result["sigma_daily"] > result["sigma_per_swap"]
    assert result["sigma_daily_sample_count"] == 288
    assert result["sigma_swap_count"] == 21
    assert result["sigma_sample_span_hours"] == pytest.approx(20.0)
    assert 20.0 < result["recommend_range_pct"] < 100.0


def test_fixed_five_minute_bar_sigma_daily_matches_analytic_value():
    """r per five-minute bar annualizes to r * sqrt(288) per day."""
    r = 0.01
    replay = {"swaps": [
        {"raw_ui_price_b_per_a": math.exp(r * index),
         "block_time": 1_700_000_000 + index * 300}
        for index in range(37)  # 36 returns == exactly three hours
    ]}

    path = _replay_price_path(replay, require_sigma_sample=True)

    assert path["sigma_per_swap"] == pytest.approx(r)
    assert path["sigma_daily"] == pytest.approx(r * math.sqrt(288))
    assert path["sigma_pair"] == pytest.approx(path["sigma_daily"])
    assert path["sigma_daily_sample_count"] == 288
    assert path["sigma_sample_span_hours"] == pytest.approx(3.0)


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
    assert netcover["inputs_complete"] is False
    assert netcover["netcover_pass"] is False
    assert "inputs" not in netcover


def test_stage2_failure_reason_reports_failed_netcover_not_economics_pass():
    reason = _stage2_failure_reason(
        {"passed": True, "reason": "PASS"},
        {"passed": True, "reason": "PASS"},
        {"swap_count": 50, "economic_price_complete": True, "reason": "PASS"},
        {"netcover_pass": False, "reason": "NETCOVER_INPUT_MISSING:gas_usd"},
    )
    assert reason == "NETCOVER_INPUT_MISSING:gas_usd"
    assert "FAIL_CLOSED:PASS" not in reason


def test_stage2_netcover_separates_complete_inputs_from_economic_gate(monkeypatch):
    import scripts.lp_solana_stock_stage2_v1_readonly as stage2

    # The shared gate receives every required input, but income is far below
    # the measured transaction cost.  Completeness must not become a pass.
    monkeypatch.setattr(stage2, "assemble_clmm_netcover_inputs", lambda *_args, **_kwargs: {
        "protocol_type": "clmm",
        "netcover_model_path": "clmm_vol_sized_range_v1",
        "fee_ev_usd": 0.009,
        "reward_ev_usd": 0.0,
        "il_ev_usd": 0.0,
        "entry_cost_usd": 0.0,
        "exit_cost_usd": 0.0,
        "gas_usd": 0.314,
        "slippage_usd": 0.0,
        "reward_conversion_cost_usd": 0.0,
        "exit_latency_loss_usd": 0.0,
    })

    result = assemble_clmm_stage2_netcover(
        {}, {}, {"passed": True, "recomputed_fee_apr_pct": 1.0},
    )

    assert result["inputs_complete"] is True
    assert result["inputs_reason"] == "PASS"
    assert result["netcover_ratio"] == pytest.approx(0.009 / 0.314)
    assert result["netcover_pass"] is False
    assert result["netcover_reason"] == "NETCOVER_BELOW_SHADOW"


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


def test_solana_cost_measurement_uses_public_rpc_components_and_unsigned_quote():
    class CostRPC:
        def call(self, method, _params):
            if method == "getRecentPrioritizationFees":
                return [{"prioritizationFee": 100}, {"prioritizationFee": 300}]
            if method == "getMinimumBalanceForRentExemption":
                return 2_000_000
            raise AssertionError(method)

    result = measure_solana_transaction_cost(
        {"pool_address": "pool"},
        {"swaps": [{"transaction_fee_lamports": 5_200},
                   {"transaction_fee_lamports": 5_400}]},
        CostRPC(),
        http=lambda _url: {"outAmount": "150000000"},
    )
    assert result["status"] == "PASS"
    assert result["signature_fee_lamports"] == 5_100
    assert result["priority_fee_lamports"] == 200
    assert result["rent_components"]["ata_count"] == 2
    assert result["operation_count"] == 2
    assert result["sol_usd"] == 150.0


def test_reward_reader_distinguishes_empty_infos_from_vault_read_failure():
    assert read_solana_reward_evidence({"reward_infos": []}, object()) == {
        "status": "NO_REWARDS", "reason": "ONCHAIN_REWARD_INFOS_EMPTY", "rewards": [],
    }
    failed = read_solana_reward_evidence({"reward_infos": [{
        "reward_mint": "mint", "reward_vault": "vault", "emissions_per_second_x64": 1,
    }]}, object())
    assert failed["status"] == "FAIL_CLOSED"
    assert failed["reason"].startswith("REWARD_VAULT_READ_FAILED:")
