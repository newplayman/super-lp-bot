"""Pure tests for the portfolio allocator (no network)."""
from scripts.lp_portfolio_allocator_v1_readonly import (
    is_enterable,
    select_per_tier,
    allocate,
)


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
    out = allocate(recs, total=10000)
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
    out = allocate(recs, total=10000)
    assert abs(out["deployed"] - 10000) < 1
    assert all(a["tier"] == "A" for a in out["allocations"])


def test_allocate_empty_when_none_enterable():
    recs = [_rec("w", "B", 99, wash=True), _rec("weak", "A", 5, yc=0.2)]
    out = allocate(recs, total=10000)
    assert out["n_pools"] == 0 and out["deployed"] == 0.0 and out["idle"] == 10000
