import pytest

from scripts.lp_solana_stock_stage2_v1_readonly import (
    _select_unique,
    recompute_economics,
    replay_recent_swaps,
    v2_il,
    verify_onchain,
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
