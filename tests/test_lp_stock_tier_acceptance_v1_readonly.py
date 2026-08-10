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


def _complete_c_payload(pool_ids):
    universe = {"rows": [
        {"pool_id": pool_id, "symbol": f"STOCK{index}-USDC", "chain": "Solana",
         "project": "raydium-clmm", "issuer": "Backed", "tier": "C"}
        for index, pool_id in enumerate(pool_ids, start=1)
    ]}
    stage2 = {"results": [
        {"llama_pool_id": pool_id, "stage2_pass": True,
         "exit_verdict": "EXITABLE_CLEAN", "sell_simulation_ok": True,
         "known_honeypot": False, "sell_tax_pct": 0,
         "exit_slippage_bps": 100, "economics": {"exit_depth_usd": 500}}
        for pool_id in pool_ids
    ]}
    shadow = {"pools": [
        {"pool_id": pool_id, "span_hours": 48, "sample_count": 3,
         "eligible_48h": True}
        for pool_id in pool_ids
    ]}
    c_risk = {"results": [
        {"llama_pool_id": pool_id,
         "holder_snapshot": {"largest_holder_pct": 5,
                             "pool_vaults_verified_and_excluded": True},
         "token_age": {"counter_token_age_days": 7}}
        for pool_id in pool_ids
    ]}
    return universe, stage2, shadow, c_risk


def test_c_batch_accumulates_passed_exposure_and_rejects_fifth_candidate():
    pool_ids = [f"c-{index}" for index in range(1, 6)]
    universe, stage2, shadow, c_risk = _complete_c_payload(pool_ids)

    result = build_acceptance(universe, stage2, {"rows": []}, shadow, c_risk)

    decisions = result["decisions"]
    assert [row["decision"]["passed"] for row in decisions] == [True, True, True, True, False]
    assert decisions[4]["decision"]["passed"] is False
    assert "7_budget_caps" in decisions[4]["decision"]["failures"]
    assert result["terminal_pass_count"] == 4


def test_c_complete_evidence_has_a_real_positive_terminal_path():
    universe, stage2, shadow, c_risk = _complete_c_payload(["c-positive"])

    result = build_acceptance(universe, stage2, {"rows": []}, shadow, c_risk)

    assert result["decisions"][0]["decision"]["passed"] is True
    assert result["counts_are_real_chain_terminal_not_defillama_yield_claims"] is True
