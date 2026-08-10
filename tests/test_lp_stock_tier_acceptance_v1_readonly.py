from scripts.lp_stock_tier_acceptance_v1_readonly import build_acceptance


def test_no_stage2_or_48h_evidence_means_zero_terminal_passes():
    universe = {"rows": [
        {"pool_id": "a", "symbol": "INTCX-USDC", "chain": "Solana",
         "project": "raydium-amm", "issuer": "Backed", "tier": "A"},
        {"pool_id": "c", "symbol": "SPYX-SSX", "chain": "Solana",
         "project": "raydium-amm", "issuer": "Backed", "tier": "C"},
    ]}
    e5 = {"rows": [{"llama_pool_id": "a", "absolute_profit_pass": True}]}
    shadow = {"pools": [{"pool_id": "c", "span_hours": 0,
                           "sample_count": 1, "eligible_48h": False}]}
    result = build_acceptance(universe, {"results": []}, e5, shadow)
    assert result["terminal_pass_count"] == 0
    c = next(row for row in result["decisions"] if row["tier"] == "C")
    assert len(c["decision"]["gates"]) == 7
    assert c["decision"]["terminal_conjunction_complete"] is True
    assert result["broadcast_count"] == 0
