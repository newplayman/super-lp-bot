import pytest

from scripts.lp_solana_tier_c_risk_evidence_v1_readonly import (
    counter_leg,
    holder_snapshot,
    token_age_evidence,
)


class RPC:
    def call(self, method, params):
        if method == "getAccountInfo":
            return {"value": {"data": {"parsed": {"info": {"supply": "1000"}}}}}
        if method == "getTokenLargestAccounts":
            return {"value": [
                {"address": "vault", "amount": "500"},
                {"address": "holder", "amount": "90"},
            ]}
        if method == "getSignaturesForAddress":
            return [{"blockTime": 1_000_000 - 8 * 86400}]
        raise AssertionError(method)


def test_counter_leg_uses_explicit_stock_identity_and_resolved_mints():
    row = {"pair_legs": ["SPYX", "SSX"], "underlying_tokens": ["stock", "other"],
           "stock_instruments": [{"pool_token_symbol": "SPYX"}]}
    assert counter_leg(row, {"mint_a": "stock", "vault_a": "sa",
                             "mint_b": "other", "vault_b": "ob"}) == ("other", "ob")


def test_holder_snapshot_excludes_only_verified_pool_vault():
    result = holder_snapshot(RPC(), "mint", "vault")
    assert result["largest_holder_pct"] == pytest.approx(9)
    assert result["pool_vaults_verified_and_excluded"] is True


def test_token_age_is_lower_bound_not_guessed_creation_time():
    result = token_age_evidence(RPC(), "mint", now_unix=1_000_000)
    assert result["passed"] is True
    assert result["counter_token_age_days"] == pytest.approx(8)
    assert "lower_bound" in result["semantics"]
