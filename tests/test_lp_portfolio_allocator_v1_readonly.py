"""Pure tests for the portfolio allocator (no network)."""
import json
import sys

import pytest

from scripts.lp_portfolio_allocator_v1_readonly import (
    M1_MIN_POSITION_EVIDENCE,
    M1_MIN_POSITION_USD,
    is_enterable,
    select_per_tier,
    allocate,
    rank_metric,
    merge_stability,
    main,
)


def test_rank_metric_uses_net_apr_uncapped():
    # discriminates above 100 (composite_score saturated; rank_metric does not)
    a = {"total_income_apr": 300.0, "il_apr": 20.0, "composite_score": 100}
    b = {"total_income_apr": 150.0, "il_apr": 20.0, "composite_score": 100}
    assert rank_metric(a) > rank_metric(b)
    assert rank_metric(a) == 280.0
    # falls back to composite_score when APR fields absent
    assert rank_metric({"composite_score": 42}) == 42.0
    # negative net clamped to 0
    assert rank_metric({"total_income_apr": 5.0, "il_apr": 50.0}) == 0.0


def test_merge_stability_annotates_by_pool():
    recs = [{"pool": "0xAAA", "composite_score": 10},
            {"resolved_pool": "0xBbB", "composite_score": 10}]
    stab = [{"pool": "0xaaa", "fee_cover_stability": {"stable": True, "enter_frac": 1.0}}]
    out = merge_stability(recs, stab)
    assert out[0]["stable"] is True and out[0]["enter_frac"] == 1.0
    assert out[1]["stable"] is False    # not in stability set -> not stable


def test_require_stable_gate_drops_unstable():
    recs = [
        {"symbol": "S1", "tier": "A", "status": "OK", "resolve_status": "OK",
         "composite_score": 50, "yield_cover": 5, "wash_flag": False, "stable": True, "range_pct": 10},
        {"symbol": "U1", "tier": "A", "status": "OK", "resolve_status": "OK",
         "composite_score": 99, "yield_cover": 9, "wash_flag": False, "stable": False, "range_pct": 10},
    ]
    out = allocate(recs, total=10000, require_stable=True, enforce_runtime_gates=False)
    syms = [a["symbol"] for a in out["allocations"]]
    assert "S1" in syms and "U1" not in syms    # unstable dropped despite higher score


def _rec(sym, tier, score, yc=5.0, wash=False, status="OK", resolve="OK"):
    return {"symbol": sym, "tier": tier, "composite_score": score, "yield_cover": yc,
            "wash_flag": wash, "status": status, "resolve_status": resolve, "range_pct": 10.0}


def test_is_enterable_gates():
    assert is_enterable(_rec("ok", "A", 10))
    assert not is_enterable(_rec("wash", "A", 99, wash=True))
    assert not is_enterable(_rec("weak", "A", 10, yc=0.5))
    assert not is_enterable(_rec("zero", "A", 0))
    assert not is_enterable(_rec("err", "A", 10, status="ERROR"))
    assert not is_enterable(_rec("nf", "A", 10, resolve="NOT_FOUND"))
    assert is_enterable({**_rec("inf", "A", 10), "yield_cover": "inf"})


def test_select_per_tier_caps_and_sorts():
    recs = [_rec(f"A{i}", "A", 100 - i) for i in range(5)] + [_rec("B1", "B", 30)]
    by = select_per_tier(recs, {"A": 3, "B": 2})
    assert [r["symbol"] for r in by["A"]] == ["A0", "A1", "A2"]   # top-3 by score
    assert len(by["B"]) == 1


def test_allocate_tier_weights_and_score_weighting():
    recs = [_rec("A1", "A", 100), _rec("A2", "A", 50), _rec("A3", "A", 25),
            _rec("A4", "A", 10), _rec("B1", "B", 40)]
    out = allocate(recs, total=10000, enforce_runtime_gates=False)
    a_usd = sum(a["usd"] for a in out["allocations"] if a["tier"] == "A")
    b_usd = sum(a["usd"] for a in out["allocations"] if a["tier"] == "B")
    assert abs(a_usd - 7000) < 1 and abs(b_usd - 3000) < 1
    aa = {a["symbol"]: a["usd"] for a in out["allocations"]}
    assert "A4" not in aa                      # capped at 3
    assert aa["A1"] > aa["A2"] > aa["A3"]      # score-weighted
    assert abs(out["deployed"] - 10000) < 1


def test_allocate_redistributes_empty_tier():
    # only Tier A enterable -> A absorbs the whole book (B weight redistributed)
    recs = [_rec("A1", "A", 100), _rec("A2", "A", 50)]
    out = allocate(recs, total=10000, enforce_runtime_gates=False)
    assert abs(out["deployed"] - 10000) < 1
    assert all(a["tier"] == "A" for a in out["allocations"])


def test_allocate_empty_when_none_enterable():
    recs = [_rec("w", "B", 99, wash=True), _rec("weak", "A", 5, yc=0.2)]
    out = allocate(recs, total=10000, enforce_runtime_gates=False)
    assert out["n_pools"] == 0 and out["deployed"] == 0.0 and out["idle"] == 10000


def _runtime_rec(sym="RUNTIME", **overrides):
    rec = _rec(sym, "A", 100)
    rec.update({
        "tvlUsd": 1_000_000.0,
        "active_liquidity_notional_usd": 10_000.0,
        "tier_configured_max_usd": 500.0,
        "expected_net_profit_h": 2.0,
        "round_trip_cost_usd": 0.2,
        "netcover": 2.0,
    })
    rec.update(overrides)
    return rec


def test_allocator_applies_runtime_position_cap_before_output():
    out = allocate([_runtime_rec()], total=1_000, enforce_runtime_gates=True)
    assert out["n_pools"] == 1
    assert out["allocations"][0]["position_cap_usd"] == 200.0
    assert out["allocations"][0]["usd"] == 200.0
    assert out["deployed"] == 200.0
    assert out["idle"] == 800.0


def test_allocator_active_liquidity_term_can_be_binding():
    out = allocate([
        _runtime_rec(tvlUsd=100_000_000, active_liquidity_notional_usd=1_000)
    ], total=1_000, enforce_runtime_gates=True)
    assert out["allocations"][0]["position_cap_usd"] == 20.0
    assert out["allocations"][0]["usd"] == 20.0


def test_allocator_inv_cost_01_skips_high_apr_tiny_absolute_profit():
    rec = _runtime_rec(total_income_apr=80.0, expected_net_profit_h=0.08, round_trip_cost_usd=0.10)
    out = allocate([rec], total=30.0, enforce_runtime_gates=True)
    assert out["allocations"] == []
    assert out["skipped"][0]["reason"] == "INV-COST-01_EXPECTED_NET_PROFIT_TOO_LOW"


def test_allocator_runtime_gate_missing_inputs_fails_closed():
    out = allocate([_rec("INCOMPLETE", "A", 100)], total=100, enforce_runtime_gates=True)
    assert out["allocations"] == []
    assert out["skipped"][0]["reason"] == "RUNTIME_GATE_INPUT_MISSING"


def test_allocator_defaults_to_fail_closed_runtime_gates():
    out = allocate([_rec("NO_BYPASS", "A", 100)], total=100)
    assert out["allocations"] == []
    assert out["runtime_gates_enforced"] is True
    assert out["skipped"][0]["reason"] == "RUNTIME_GATE_INPUT_MISSING"


def test_m1_min_position_boundary_is_annotation_only():
    below = allocate([_runtime_rec()], total=49.0, enforce_runtime_gates=True)
    at_min = allocate([_runtime_rec()], total=50.0, enforce_runtime_gates=True)

    assert M1_MIN_POSITION_USD == 50.0
    assert below["allocations"][0]["usd"] == 49.0
    assert below["allocations"][0]["below_min"] is True
    assert at_min["allocations"][0]["usd"] == 50.0
    assert at_min["allocations"][0]["below_min"] is False
    assert at_min["runtime_gates_enforced"] is True


def test_cli_records_m1_min_position_config(tmp_path, monkeypatch):
    ranked = tmp_path / "ranked.json"
    ranked.write_text(json.dumps([_runtime_rec()]), encoding="utf-8")
    output = tmp_path / "allocation"
    monkeypatch.setattr(sys, "argv", [
        "lp_portfolio_allocator_v1_readonly.py",
        "--ranked", str(ranked),
        "--total", "50",
        "--min-position-usd", "50",
        "--out", str(output),
    ])

    main()

    result = json.loads((output / "allocation.json").read_text(encoding="utf-8"))
    assert result["config"] == {
        "min_position_profile": "M1_1x50_60U",
        "min_position_usd": 50.0,
        "min_position_evidence": M1_MIN_POSITION_EVIDENCE,
    }
    assert result["allocations"][0]["below_min"] is False


def test_min_position_must_be_finite_and_positive_for_api_and_cli(monkeypatch):
    for invalid in (0, -1, float("nan"), float("inf"), "not-a-number"):
        with pytest.raises(ValueError, match="min_pool_usd must be finite and positive"):
            allocate([_runtime_rec()], total=50, min_pool_usd=invalid)

    monkeypatch.setattr(sys, "argv", [
        "lp_portfolio_allocator_v1_readonly.py", "--self-test",
        "--min-position-usd", "0",
    ])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 2
