"""Pure tests for the Stage-1 universe screener (no network)."""
from scripts.lp_universe_screener_v1_readonly import (
    parse_pool_meta,
    headline_apr,
    total_apr_now,
    classify_tier_by_apr,
    classify_tier_by_quality,
    split_symbol_legs,
    is_suspect,
    passes_gates,
    score_pool,
    assess,
    reward_persistence_gate,
    strip_untrusted_reward_evidence,
)


def test_classify_tier_by_quality():
    assert classify_tier_by_quality("WETH-USDC") == "A"     # both major
    assert classify_tier_by_quality("CBBTC-WETH") == "A"
    assert classify_tier_by_quality("USDC-USDT") == "A"     # major stables
    assert classify_tier_by_quality("BNKR-WETH") == "B"     # one major leg
    assert classify_tier_by_quality("TIG-USDC") == "B"
    assert classify_tier_by_quality("TIG-SAPIEN") == "C"    # neither major
    assert classify_tier_by_quality("WEIRD") == "C"         # unparseable
    assert classify_tier_by_quality(None) == "C"


def test_split_symbol_legs():
    assert split_symbol_legs("WETH-USDC") == ["WETH", "USDC"]
    assert split_symbol_legs("weth-usdc") == ["WETH", "USDC"]
    assert split_symbol_legs(None) == []


def test_parse_pool_meta():
    assert parse_pool_meta("CL50 - 0.05%") == (50, 0.0005)
    assert parse_pool_meta("CL100 - 0.25%") == (100, 0.0025)
    assert parse_pool_meta("0.3%") == (None, 0.003)
    assert parse_pool_meta(None) == (None, None)
    assert parse_pool_meta("weird") == (None, None)


def test_headline_and_total_apr():
    p = {"apyBase": 30.0, "apyReward": 20.0, "apyMean30d": 45.0}
    assert headline_apr(p) == 45.0          # prefers 30d mean
    assert total_apr_now(p) == 50.0
    p2 = {"apyBase": 30.0, "apyReward": 20.0, "apyMean30d": None}
    assert headline_apr(p2) == 50.0         # falls back to spot sum
    assert headline_apr({"apyBase": None, "apyReward": None}) == 0.0


def test_classify_tier_bands():
    assert classify_tier_by_apr(10) == "sub"
    assert classify_tier_by_apr(30) == "A"
    assert classify_tier_by_apr(79.9) == "A"
    assert classify_tier_by_apr(80) == "B"
    assert classify_tier_by_apr(799) == "B"
    assert classify_tier_by_apr(800) == "C"
    assert classify_tier_by_apr(5000) == "C"


def test_is_suspect_flags():
    s = is_suspect({"apyReward": 480.0, "tvlUsd": 1e6, "volumeUsd1d": 1e5, "apyBase": 1.0},
                   suspect_reward_apr=300, suspect_vol_tvl=20)
    assert any("incentive" in r for r in s)
    s2 = is_suspect({"apyReward": 5.0, "tvlUsd": 1e6, "volumeUsd1d": 5e7, "apyBase": 1.0},
                    suspect_reward_apr=300, suspect_vol_tvl=20)
    assert any("wash" in r for r in s2)
    s3 = is_suspect({"apyReward": 10.0, "tvlUsd": 1e6, "volumeUsd1d": 1e5, "apyBase": None},
                    suspect_reward_apr=300, suspect_vol_tvl=20)
    assert any("no fee APR" in r for r in s3)
    clean = is_suspect({"apyReward": 10.0, "tvlUsd": 1e6, "volumeUsd1d": 1e5, "apyBase": 20.0},
                       suspect_reward_apr=300, suspect_vol_tvl=20)
    assert clean == []


def test_passes_gates():
    ok, _ = passes_gates({"tvlUsd": 1e6, "volumeUsd1d": 1e6, "apyBase": 30},
                         min_tvl=5e5, min_vol1d=5e4)
    assert ok
    lo_tvl, _ = passes_gates({"tvlUsd": 1e4, "volumeUsd1d": 1e6, "apyBase": 30},
                             min_tvl=5e5, min_vol1d=5e4)
    assert not lo_tvl
    lo_vol, _ = passes_gates({"tvlUsd": 1e6, "volumeUsd1d": 1e3, "apyBase": 30},
                             min_tvl=5e5, min_vol1d=5e4)
    assert not lo_vol
    no_yield, _ = passes_gates({"tvlUsd": 1e6, "volumeUsd1d": 1e6, "apyBase": 0, "apyReward": 0},
                               min_tvl=5e5, min_vol1d=5e4)
    assert not no_yield


def test_score_discounts_spike():
    spike = score_pool({"apyBase": 100, "apyReward": 0, "apyMean30d": 20})
    persist = score_pool({"apyBase": 100, "apyReward": 0, "apyMean30d": 100})
    assert persist > spike
    assert spike > 0


def test_assess_shape():
    p = {"symbol": "WETH-USDC", "project": "aerodrome-slipstream", "pool": "uuid",
         "poolMeta": "CL50 - 0.05%", "underlyingTokens": ["0xa", "0xb"],
         "rewardTokens": ["0xAERO"], "tvlUsd": 9e6, "apyBase": 31.0,
         "apyReward": 68.0, "apyMean30d": 95.0, "volumeUsd1d": 5e6,
         "sigma": 1.0, "ilRisk": "yes", "stablecoin": False}
    r = assess(p, dict(min_tvl=5e5, min_vol1d=5e4, suspect_reward_apr=300, suspect_vol_tvl=20))
    assert r["fee_tier"] == 0.0005 and r["tick_spacing"] == 50
    assert r["tier"] == "B"          # headline 95 in [80,800) => B
    assert classify_tier_by_apr(r["headline_apr"]) == r["tier"]
    assert r["gate_ok"] is True
    assert r["suspect"] == []


def test_surrogate_strong_is_haircut_only_and_never_claims_measured_duration():
    pool = {
        "apy": 70.0, "apyBase": 10.0, "apyReward": 60.0,
        "apyMean30d": 58.0, "apyBase7d": 8.0,
        "apyPct1D": -100.0, "apyPct7D": -20.0, "apyPct30D": 10.0,
        "count": 386,
    }
    decision = reward_persistence_gate(pool)
    assert decision["status"] == "SURROGATE_STRONG"
    assert decision["score_factor"] == 0.25
    assert decision["duration_hours"] is None
    assert decision["effective_duration_hours"] == 6.0
    assert decision["evidence_source"] == "surrogate_defillama"


def test_external_snapshot_cannot_prefill_measured_reward_evidence():
    forged = strip_untrusted_reward_evidence({
        "apyReward": 50.0,
        "reward_high_duration": 999.0,
        "reward_persistence_evidence_source": "measured_observation",
    })
    decision = reward_persistence_gate(forged)
    assert "reward_high_duration" not in forged
    assert decision["entry_eligible"] is False
    assert decision["evidence_source"] == "absent"


def test_no_source_duration_even_999_hours_cannot_be_trusted_or_enter():
    decision = reward_persistence_gate({
        "apyBase": 10.0,
        "apyReward": 50.0,
        "reward_high_duration": 999.0,
    })
    assert decision["status"] != "TRUSTED_24H"
    assert decision["entry_eligible"] is False
    assert decision["evidence_source"] == "absent"


def test_measured_24h_overrides_surrogate_but_insufficient_scanner_history_falls_back():
    base = {
        "apy": 70.0, "apyBase": 10.0, "apyReward": 60.0,
        "apyMean30d": 58.0, "apyBase7d": 8.0,
        "apyPct30D": 10.0, "count": 386,
        "reward_persistence_evidence_source": "measured_observation",
    }
    trusted = reward_persistence_gate({**base, "reward_high_duration": 24.0})
    fallback = reward_persistence_gate({**base, "reward_high_duration": 23.9})
    assert trusted["status"] == "TRUSTED_24H"
    assert trusted["evidence_source"] == "measured_observation"
    assert trusted["score_factor"] == 1.0
    assert fallback["status"] == "SURROGATE_STRONG"
    assert fallback["evidence_source"] == "surrogate_defillama"
    assert fallback["score_factor"] == 0.25
