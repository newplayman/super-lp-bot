"""Contracts for the M0F zero-RPC Stage-1 NetCover proxy."""
from __future__ import annotations

import pytest

from scripts.lp_funnel_rerank_v1_readonly import (
    DEFAULT_PROXY_HORIZON_HOURS,
    MIN_CORRELATION_PAIRS,
    PROXY_VALID_SPEARMAN_MIN,
    build_rpc_budget,
    correlate_proxy_with_netcover,
    proxy_netcover,
    rank_stage1,
)
from scripts.lp_funnel_rerank_evaluation_v1_readonly import (
    TARGET_SYMBOLS,
    ProxyEvidenceStages,
    enforce_research_only_nonproduction,
    target_evidence,
    terminal_accepted,
    terminal_outcome,
)


AERO = "0x940181a94A35A4569E4529A3CDfB74e38FD98631"


def _pool(**changes):
    row = {
        "llama_pool_id": "pool-1",
        "chain": "Base",
        "project": "aerodrome-slipstream",
        "symbol": "WETH-USDC",
        "fee_tier": 0.0005,
        "apyBase": 20.0,
        "apyReward": 40.0,
        "rewardTokens": [AERO],
        "tvlUsd": 2_000_000.0,
        "volumeUsd1d": 500_000.0,
        "sigma": 1.5,
        "ilRisk": "yes",
        "stablecoin": False,
        "score": 60.0,
    }
    row.update(changes)
    return row


def test_proxy_is_terminal_shape_with_existing_haircuts_and_fixed_m1_cost():
    out = proxy_netcover(_pool())
    assert out["proxy_status"] == "CALCULABLE"
    assert out["proxy_fee_income_apr_pct"] == pytest.approx(20.0 * 0.65)
    assert out["proxy_reward_haircut"] == pytest.approx(0.50)
    assert out["proxy_reward_income_apr_pct"] == pytest.approx(40.0 * 0.50)
    assert out["proxy_lvr_apr_pct"] == pytest.approx(out["proxy_il_apr_pct"] * 0.50)
    expected_drag = ((2 * 0.0005 * 50.0 + 0.0795) / 50.0) * (
        8760.0 / DEFAULT_PROXY_HORIZON_HOURS
    ) * 100.0
    assert out["proxy_fixed_drag_apr_pct"] == pytest.approx(expected_drag)
    assert out["proxy_netcover"] == pytest.approx(
        out["proxy_income_apr_pct"] / out["proxy_cost_apr_pct"]
    )


def test_low_fee_and_stable_pair_are_structural_cost_inputs_not_bonus_points():
    low_stable = proxy_netcover(
        _pool(symbol="USDC-USDT", fee_tier=0.0001, stablecoin=True, sigma=2.0)
    )
    high_volatile = proxy_netcover(
        _pool(symbol="WETH-USDC", fee_tier=0.003, stablecoin=False, sigma=2.0)
    )
    assert low_stable["proxy_stable_or_same_anchor"] is True
    assert low_stable["proxy_il_apr_pct"] == 0.0
    assert low_stable["proxy_fixed_drag_apr_pct"] < high_volatile["proxy_fixed_drag_apr_pct"]
    assert low_stable["proxy_netcover"] > high_volatile["proxy_netcover"]
    assert "bonus" not in low_stable


def test_emission_dominant_bluechip_is_explicit_and_unknown_reward_fails_closed():
    blue = proxy_netcover(_pool(apyBase=5.0, apyReward=40.0))
    assert blue["proxy_emission_dominant_bluechip"] is True
    non_blue = proxy_netcover(
        _pool(symbol="WETH-MORPHO", apyBase=5.0, apyReward=40.0)
    )
    assert non_blue["proxy_emission_dominant_bluechip"] is False
    assert non_blue["proxy_reward_pair_reliability"] < 1.0
    assert non_blue["proxy_reward_income_apr_pct"] < blue["proxy_reward_income_apr_pct"]
    unknown = proxy_netcover(
        _pool(symbol="WETH-MYSTERY", apyReward=40.0, rewardTokens=["0xdead"])
    )
    assert unknown["proxy_status"] == "UNAVAILABLE_FAIL_CLOSED"
    assert unknown["proxy_reason"] == "reward_category_unavailable"
    assert unknown["proxy_netcover"] is None


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"sigma": None}, "sigma_unavailable"),
        ({"fee_tier": None}, "fee_tier_unavailable"),
        ({"apyBase": None}, "apy_base_unavailable"),
        ({"apyReward": -1}, "apy_reward_invalid"),
    ],
)
def test_proxy_missing_or_invalid_free_evidence_fails_closed(changes, reason):
    out = proxy_netcover(_pool(**changes))
    assert out["proxy_status"] == "UNAVAILABLE_FAIL_CLOSED"
    assert out["proxy_reason"] == reason


def test_fixed_m1_position_is_not_a_ranking_factor():
    out = proxy_netcover(_pool(capital_usd=3_000_000, position_usd=3_000))
    assert out["proxy_position_usd"] == 50.0
    assert out["proxy_position_source"] == "M1_MIN_POSITION_USD_FIXED_NOT_RANKING_FACTOR"


def test_spearman_and_top_k_use_only_same_batch_fully_calculable_rows():
    rows = [
        {"id": str(i), "proxy_netcover": float(i), "netcover_ratio": float(i) / 10.0}
        for i in range(1, MIN_CORRELATION_PAIRS + 1)
    ] + [{"id": "missing", "proxy_netcover": 99.0, "netcover_ratio": None}]
    result = correlate_proxy_with_netcover(rows, id_key="id", top_k=2)
    assert result["same_batch_records"] == MIN_CORRELATION_PAIRS + 1
    assert result["fully_calculable_pairs"] == MIN_CORRELATION_PAIRS
    assert result["spearman"] == pytest.approx(1.0)
    assert result["top_k_denominator"] == 2
    assert result["top_k_hits"] == 2
    assert result["top_k_hit_rate"] == pytest.approx(1.0)
    assert result["proxy_valid"] is True


def test_perfect_but_thin_correlation_cannot_activate_proxy_ranking():
    rows = [
        {"id": "a", "proxy_netcover": 2.0, "netcover_ratio": 0.2},
        {"id": "b", "proxy_netcover": 1.0, "netcover_ratio": 0.1},
    ]
    result = correlate_proxy_with_netcover(rows, id_key="id", top_k=2)
    assert result["spearman"] == pytest.approx(1.0)
    assert result["fully_calculable_pairs"] < result["minimum_correlation_pairs"]
    assert result["proxy_valid"] is False
    assert result["production_ranking"] == "ORIGINAL_APR_FALLBACK"


def test_weak_correlation_falls_back_to_original_apr_order():
    rows = [
        dict(_pool(llama_pool_id="a", score=10.0), proxy_netcover=3.0),
        dict(_pool(llama_pool_id="b", score=30.0), proxy_netcover=2.0),
        dict(_pool(llama_pool_id="c", score=20.0), proxy_netcover=1.0),
    ]
    evidence = {"spearman": PROXY_VALID_SPEARMAN_MIN - 0.01, "proxy_valid": False}
    ranked = rank_stage1(rows, correlation_evidence=evidence)
    assert [r["llama_pool_id"] for r in ranked] == ["b", "c", "a"]
    assert all(r["stage1_ranking_method"] == "ORIGINAL_APR_FALLBACK" for r in ranked)


def test_valid_correlation_uses_proxy_but_preserves_apr_comparison_rank():
    rows = [
        dict(_pool(llama_pool_id="a", score=10.0), proxy_netcover=3.0),
        dict(_pool(llama_pool_id="b", score=30.0), proxy_netcover=2.0),
        dict(_pool(llama_pool_id="c", score=20.0), proxy_netcover=1.0),
    ]
    ranked = rank_stage1(
        rows,
        correlation_evidence={
            "spearman": 0.8,
            "fully_calculable_pairs": MIN_CORRELATION_PAIRS,
            "proxy_valid": True,
        },
    )
    assert [r["llama_pool_id"] for r in ranked] == ["a", "b", "c"]
    assert [r["original_apr_rank"] for r in ranked] == [3, 1, 2]
    assert [r["proxy_rank"] for r in ranked] == [1, 2, 3]


def test_valid_proxy_order_is_strictly_proxy_not_legacy_suspect_bucket():
    rows = [
        dict(_pool(llama_pool_id="high", score=100.0, suspect=["high reward"]), proxy_netcover=9.0),
        dict(_pool(llama_pool_id="low", score=10.0, suspect=[]), proxy_netcover=1.0),
    ]
    evidence = {
        "spearman": 0.8,
        "fully_calculable_pairs": MIN_CORRELATION_PAIRS,
        "proxy_valid": True,
    }
    ranked = rank_stage1(rows, correlation_evidence=evidence)
    assert [row["llama_pool_id"] for row in ranked] == ["high", "low"]


def test_proxy_valid_boolean_without_minimum_evidence_cannot_switch_production():
    rows = [
        dict(_pool(llama_pool_id="a", score=10.0), proxy_netcover=3.0),
        dict(_pool(llama_pool_id="b", score=30.0), proxy_netcover=2.0),
    ]
    ranked = rank_stage1(
        rows, correlation_evidence={"spearman": 1.0, "proxy_valid": True}
    )
    assert [row["llama_pool_id"] for row in ranked] == ["b", "a"]
    assert ranked[0]["stage1_ranking_method"] == "ORIGINAL_APR_FALLBACK"


def test_rpc_budget_separates_measured_calls_from_conservative_upper_bound():
    budget = build_rpc_budget(
        top_n=30,
        n_windows=6,
        resolve_log_chunks=44,
        stability_log_chunks_per_window=22,
        measured_calls={"eth_call": 120, "eth_getLogs": 900, "eth_blockNumber": 3},
    )
    assert budget["top_n"] == 30
    assert budget["measured_total_calls"] == 1023
    assert budget["upper_total_calls"] > budget["measured_total_calls"]
    assert budget["upper_components"]["stability_window_log_calls"] == 30 * 6 * 22
    assert budget["upper_components"]["cross_route_fixed_batch_calls"] == 89


def test_add2_targets_are_diagnostic_only_and_receive_honest_terminal_results():
    universe = [
        dict(_pool(symbol="WETH-USDC", llama_pool_id="target"), proxy_netcover=3.0),
        dict(_pool(symbol="WETH-CBBTC", llama_pool_id="missing"), proxy_netcover=2.0),
    ]
    actual = [
        dict(
            universe[0],
            netcover_ratio=0.2,
            accepted=False,
            rejection_reason="NETCOVER_BELOW_SHADOW",
            research_selection_sources=["PROXY_TOP_N", "ADD2_TARGET_RESEARCH"],
        )
    ]
    rows = target_evidence(universe, universe, actual, top_n=30)
    assert tuple(row["symbol"] for row in rows) == TARGET_SYMBOLS
    weth_usdc = next(row for row in rows if row["symbol"] == "WETH-USDC")
    assert weth_usdc["in_proxy_top_n"] is True
    assert weth_usdc["best_true_netcover"] == pytest.approx(0.2)
    assert weth_usdc["accepted_rows"] == 0
    assert weth_usdc["target_semantics"] == "validation_target_only_never_allowlist_or_gate_bypass"


def test_uniswap_only_same_symbol_is_not_an_aerodrome_target():
    uniswap = [
        dict(
            _pool(
                project="uniswap-v3",
                symbol="USDC-AVAIL",
                llama_pool_id="uni-only",
            ),
            proxy_netcover=10.0,
            research_selection_sources=["ADD2_TARGET_RESEARCH"],
            netcover_ratio=9.0,
            accepted=True,
        )
    ]
    rows = target_evidence(uniswap, uniswap, uniswap, top_n=30)
    target = next(row for row in rows if row["symbol"] == "USDC-AVAIL")
    assert target["live_status"] == "NOT_IN_LIVE_UNIVERSE"
    assert target["live_universe_matches"] == 0
    assert target["stage2_terminal_rows"] == 0
    assert target["best_true_netcover"] is None
    assert target["accepted_rows"] == 0


def test_research_cohort_is_proxy_top_n_union_every_live_target(monkeypatch):
    from scripts import lp_universe_screener_v1_readonly as screener

    def raw(index, *, symbol=None, tvl=2_000_000.0, apy=100.0):
        return {
            "chain": "Base",
            "project": "aerodrome-slipstream",
            "pool": f"pool-{index}",
            "symbol": symbol or f"WETH-X{index}",
            "poolMeta": "CL50 - 0.05%",
            "apyBase": apy,
            "apyReward": 0.0,
            "apyMean30d": apy,
            "tvlUsd": tvl,
            "volumeUsd1d": 500_000.0,
            "sigma": 1.0,
            "ilRisk": "yes",
            "stablecoin": False,
        }

    pools = [raw(i) for i in range(31)]
    # Deliberately below the coarse TVL gate and too weak for proxy top-30: ADD-2
    # still requires a terminal research attempt, without production allowlisting.
    pools.append(raw(99, symbol="USDC-AVAIL", tvl=1.0, apy=0.01))
    same_symbol_uniswap = raw(100, symbol="USDC-AVAIL", tvl=1.0, apy=0.01)
    same_symbol_uniswap["project"] = "uniswap-v3"
    pools.append(same_symbol_uniswap)
    monkeypatch.setattr(screener, "fetch_pools", lambda: pools)

    class Pool:
        def health_snapshot(self):
            return {"state": "NORMAL"}

    batch = ProxyEvidenceStages(rpc_pool=Pool(), top=30).screen()
    assert len(batch.candidates) == 31
    target = next(row for row in batch.candidates if row["symbol"] == "USDC-AVAIL")
    assert target["research_selection_sources"] == ["ADD2_TARGET_RESEARCH"]
    assert target["target_research_only_never_allowlist"] is True
    assert not any(
        row["project"] == "uniswap-v3" and row["symbol"] == "USDC-AVAIL"
        for row in batch.candidates
    )


@pytest.mark.parametrize("gate_ok", [False, True])
def test_target_only_netcover_pass_is_research_evidence_never_accepted(gate_ok):
    source = dict(
        _pool(symbol="CADC-USDC", llama_pool_id=f"target-{gate_ok}"),
        research_selection_sources=["ADD2_TARGET_RESEARCH"],
        gate_ok=gate_ok,
        gate_reason="ok" if gate_ok else "TVL below coarse minimum",
        vetted=True,
        netcover_pass=True,
        netcover_ratio=2.5,
        rejection_reason=None,
        gates={"netcover_shadow": True},
    )
    row = enforce_research_only_nonproduction([source])[0]
    assert row["research_netcover_ratio"] == pytest.approx(2.5)
    assert row["research_netcover_pass_before_boundary"] is True
    assert row["vetted"] is False
    assert row["netcover_pass"] is True
    assert row["accepted"] is False
    assert row["gates"]["netcover_shadow"] is True
    assert row["terminal_outcome"].startswith("RESEARCH_ONLY_NOT_PROXY_TOP_N:")
    assert row["terminal_outcome"].endswith(";NETCOVER_GATE_PASS")


def test_target_also_in_proxy_top_n_keeps_unchanged_terminal_gate_result():
    source = dict(
        _pool(symbol="WETH-USDC", llama_pool_id="both"),
        research_selection_sources=["PROXY_TOP_N", "ADD2_TARGET_RESEARCH"],
        gate_ok=True,
        vetted=True,
        netcover_pass=True,
        netcover_ratio=1.2,
    )
    row = enforce_research_only_nonproduction([source])[0]
    assert terminal_accepted(row) is True
    assert row["accepted"] is True
    assert row["terminal_outcome"] == "ACCEPTED"


def test_terminal_outcome_priority_never_reports_unknown_or_ok():
    permanent = dict(
        _pool(),
        permanent_fail_closed_reason="ambiguous_pool",
        research_selection_sources=["ADD2_TARGET_RESEARCH"],
        gate_ok=False,
        gate_reason="ok",
    )
    assert terminal_outcome(permanent) == "PERMANENT_FAIL_CLOSED:ambiguous_pool"
    coarse = dict(_pool(), gate_ok=False, gate_reason="TVL too low")
    assert terminal_outcome(coarse) == "COARSE_GATE_REJECTED:TVL too low"


def test_report_and_sqlite_derive_same_accepted_bit(tmp_path):
    import sqlite3

    from scripts.lp_scanner_daemon_v1_readonly import (
        FunnelOrchestrator,
        ScannerStore,
        ScreenBatch,
    )

    target_only = dict(
        _pool(symbol="CADC-USDC", llama_pool_id="target-only", pool="0x1"),
        research_selection_sources=["ADD2_TARGET_RESEARCH"],
        gate_ok=False,
        gate_reason="TVL too low",
        vetted=True,
        netcover_pass=True,
        netcover_ratio=2.0,
    )
    class Stages:
        rpc_health = "NORMAL"

        def __init__(self):
            self.final = []

        def screen(self):
            return ScreenBatch(all_records=[target_only], candidates=[target_only])

        def resolve(self, records):
            return list(records)

        def multiwindow(self, records):
            return []

        def funnel(self, records, _stability):
            return list(records)

        def netcover(self, records):
            self.final = enforce_research_only_nonproduction(records)
            return self.final

    db = tmp_path / "scanner.db"
    stages = Stages()
    cycle = FunnelOrchestrator(stages, ScannerStore(db)).run_once(
        refresh_coarse=True,
        as_of="2026-08-09T00:00:00+00:00",
    )
    bounded = stages.final[0]
    report = target_evidence([bounded], [], [bounded], top_n=30)
    report_target = next(row for row in report if row["symbol"] == "CADC-USDC")
    with sqlite3.connect(db) as connection:
        sql_accepted = connection.execute("SELECT accepted FROM opportunity_scores").fetchone()[0]
    expected = int(terminal_accepted(bounded))
    assert report_target["accepted_rows"] == expected
    assert cycle.accepted == sql_accepted == expected == 0


def test_production_scanner_defaults_to_top30():
    from scripts.lp_scanner_daemon_v1_readonly import DefaultStages, _parser

    class Pool:
        def health_snapshot(self):
            return {"state": "NORMAL"}

    assert DefaultStages(rpc_pool=Pool()).top == 30
    assert _parser().parse_args([]).top == 30


def test_production_screen_uses_validated_proxy_and_keeps_apr_rank(monkeypatch):
    from scripts import lp_universe_screener_v1_readonly as screener
    from scripts.lp_scanner_daemon_v1_readonly import DefaultStages

    def raw(index, *, symbol, apy, sigma, fee_meta, stable=False):
        return {
            "chain": "Base",
            "project": "aerodrome-slipstream",
            "pool": f"pool-{index}",
            "symbol": symbol,
            "poolMeta": fee_meta,
            "apyBase": apy,
            "apyReward": 0.0,
            "apyMean30d": apy,
            "tvlUsd": 2_000_000.0,
            "volumeUsd1d": 500_000.0,
            "sigma": sigma,
            "ilRisk": "yes",
            "stablecoin": stable,
        }

    pools = [
        raw(0, symbol="USDC-USDT", apy=10.0, sigma=1.0, fee_meta="CL1 - 0.01%", stable=True),
        raw(1, symbol="WETH-RISK", apy=100.0, sigma=10.0, fee_meta="CL200 - 1%"),
    ] + [
        raw(i, symbol=f"WETH-X{i}", apy=1.0, sigma=2.0, fee_meta="CL50 - 0.05%")
        for i in range(2, 33)
    ]
    monkeypatch.setattr(screener, "fetch_pools", lambda: pools)

    class Pool:
        def health_snapshot(self):
            return {"state": "NORMAL"}

    batch = DefaultStages(rpc_pool=Pool()).screen()
    assert len(batch.candidates) == 30
    assert batch.candidates[0]["symbol"] == "USDC-USDT"
    assert batch.candidates[0]["stage1_ranking_method"] == "PROXY_NETCOVER"
    assert batch.candidates[0]["original_apr_rank"] > 1
    apr_winner = next(row for row in batch.all_records if row["symbol"] == "WETH-RISK")
    assert apr_winner["score"] > batch.candidates[0]["score"]
    assert "proxy_netcover" in apr_winner
