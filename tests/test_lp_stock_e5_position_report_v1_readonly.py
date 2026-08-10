from scripts.lp_stock_e5_position_report_v1_readonly import build_report


def test_unresolved_pool_gets_zero_not_guessed_size():
    universe = [{"pool": "x", "symbol": "INTCX-USDC", "chain": "Solana",
                 "project": "raydium-amm", "tier": "A", "tvlUsd": 30_000}]
    report = build_report(universe, {"results": []})
    assert report["rows"][0]["position_cap_usd"] == 0
    assert report["candidate_count"] == 0


def test_verified_amm_is_sized_at_005pct_then_absolute_profit_checked():
    universe = [{"pool": "x", "symbol": "INTCX-USDC", "chain": "Solana",
                 "project": "raydium-amm", "tier": "A", "tvlUsd": 30_000}]
    stage2 = {"results": [{
        "llama_pool_id": "x", "stage2_pass": True,
        "resolved": {"fee_rate": 0.001},
        "economics": {"passed": True, "exit_depth_usd": 15_000,
                      "recomputed_fee_apr_pct": 500, "il_24h_worst": -0.001},
    }]}
    report = build_report(universe, stage2)
    row = report["rows"][0]
    assert row["position_cap_usd"] == 15
    assert row["absolute_profit_pass"] is True
    assert report["rules"]["regular_and_hard_tvl_shares_changed"] is False
