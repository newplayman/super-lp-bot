import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import json
from decimal import Decimal

from scripts.lp_rh_meme_aggregation_v1_readonly import (
    MAX_MEME_TOTAL_PCT,
    MAX_SINGLE_ASSET_PCT,
    MAX_SINGLE_POOL_PCT,
    aggregate_by_asset,
    aggregation_gate,
    main,
    position_exposure,
)


def _pos(pool, wallet, asset, asset_usd, paired_usd, in_range=True):
    return {
        "pool": pool, "wallet": wallet, "asset": asset, "paired_asset": "ETH",
        "asset_amount_usd": asset_usd, "paired_amount_usd": paired_usd,
        "in_range": in_range,
    }


def test_constants_values():
    # Regression guard: the three caps must not be silently loosened.
    assert MAX_SINGLE_ASSET_PCT == Decimal("2")
    assert MAX_MEME_TOTAL_PCT == Decimal("8")
    assert MAX_SINGLE_POOL_PCT == Decimal("2")


def test_position_exposure_basic():
    result = position_exposure(_pos("p", "w", "MEME", Decimal("100"), Decimal("40")))
    assert result["asset"] == "MEME"
    assert result["current_usd"] == Decimal("100")
    assert result["worst_case_usd"] == Decimal("140")


def test_position_exposure_missing_amount_is_none():
    # Missing asset amount -> current None; missing paired -> worst None (never 0).
    result = position_exposure(_pos("p", "w", "MEME", None, Decimal("40")))
    assert result["current_usd"] is None
    assert result["worst_case_usd"] is None
    result2 = position_exposure(_pos("p", "w", "MEME", Decimal("100"), None))
    assert result2["current_usd"] == Decimal("100")
    assert result2["worst_case_usd"] is None


def test_position_exposure_out_of_range_equal():
    # Already out of range: the whole position is one-sided, so current == worst.
    result = position_exposure(_pos("p", "w", "MEME", Decimal("100"), Decimal("0"), in_range=False))
    assert result["current_usd"] == result["worst_case_usd"]


def test_t26_cross_pool_bypass_blocked():
    # T26 bypass: same asset split across 4 pools, each 0.6% (< 2% per pool),
    # aggregated to 2.4% -> must be blocked on the single-asset current cap.
    positions = [_pos(f"pool{i}", "w", "MEME", Decimal("60"), Decimal("40")) for i in range(4)]
    result = aggregation_gate(positions, capital_usd=Decimal("10000"))
    assert result["pass"] is False
    current = [v for v in result["violations"] if v["kind"] == "SINGLE_ASSET_CURRENT"]
    assert current and current[0]["pct"] == Decimal("2.4")
    assert result["by_asset"]["MEME"]["pool_count"] == 4


def test_cross_wallet_bypass_blocked():
    # Same asset across 3 wallets, each 0.8% -> aggregated 2.4% -> blocked.
    positions = [_pos(f"pool{i}", f"wallet{i}", "MEME", Decimal("80"), Decimal("0")) for i in range(3)]
    result = aggregation_gate(positions, capital_usd=Decimal("10000"))
    assert result["pass"] is False
    assert result["by_asset"]["MEME"]["wallet_count"] == 3
    assert "SINGLE_ASSET_CURRENT" in {v["kind"] for v in result["violations"]}


def test_worst_case_independently_capped():
    # Current 1.5% (ok) but worst-case 3% after out-of-range -> blocked on worst case.
    positions = [
        _pos("poolA", "w", "MEME", Decimal("75"), Decimal("75")),
        _pos("poolB", "w", "MEME", Decimal("75"), Decimal("75")),
    ]
    result = aggregation_gate(positions, capital_usd=Decimal("10000"))
    assert result["pass"] is False
    kinds = {v["kind"] for v in result["violations"]}
    assert "SINGLE_ASSET_WORST_CASE" in kinds
    assert "SINGLE_ASSET_CURRENT" not in kinds
    assert "SINGLE_POOL" not in kinds


def test_single_pool_over_cap():
    # Two assets in one pool; pool total 3% > 2% while each asset stays under cap.
    positions = [
        _pos("poolA", "w1", "AAA", Decimal("100"), Decimal("50")),
        _pos("poolA", "w2", "BBB", Decimal("100"), Decimal("50")),
    ]
    result = aggregation_gate(positions, capital_usd=Decimal("10000"))
    assert result["pass"] is False
    kinds = {v["kind"] for v in result["violations"]}
    assert "SINGLE_POOL" in kinds
    assert "SINGLE_ASSET_CURRENT" not in kinds
    assert "SINGLE_ASSET_WORST_CASE" not in kinds


def test_meme_total_over_cap():
    # 5 assets, each 1.8% (ok individually), total 9% > 8% -> MEME_TOTAL.
    positions = [_pos(f"pool{i}", f"w{i}", f"A{i}", Decimal("180"), Decimal("0")) for i in range(5)]
    result = aggregation_gate(positions, capital_usd=Decimal("10000"))
    assert result["pass"] is False
    kinds = {v["kind"] for v in result["violations"]}
    assert "MEME_TOTAL" in kinds
    assert "SINGLE_ASSET_CURRENT" not in kinds
    assert "SINGLE_ASSET_WORST_CASE" not in kinds
    assert "SINGLE_POOL" not in kinds


def test_multiple_violations_all_listed():
    # A portfolio breaching every cap at once -> all four kinds are listed.
    positions = [
        _pos("poolA", "w", "X", Decimal("300"), Decimal("300")),  # current 3%, worst 6%, pool 6%
        _pos("poolB", "w", "Y", Decimal("600"), Decimal("0")),    # current 6%, worst 6%, pool 6%
    ]
    result = aggregation_gate(positions, capital_usd=Decimal("10000"))
    assert result["pass"] is False
    kinds = {v["kind"] for v in result["violations"]}
    assert {"SINGLE_ASSET_CURRENT", "SINGLE_ASSET_WORST_CASE", "MEME_TOTAL", "SINGLE_POOL"} <= kinds


def test_missing_amount_marks_incomplete():
    # An asset whose amount is missing cannot be computed -> gate must fail.
    positions = [_pos("poolA", "w", "MEME", None, Decimal("100"))]
    result = aggregation_gate(positions, capital_usd=Decimal("10000"))
    assert result["pass"] is False
    assert "MEME" in result["incomplete_assets"]
    assert "EXPOSURE_INCOMPLETE" in {v["kind"] for v in result["violations"]}


def test_missing_amount_not_zero_sum():
    # Missing amounts must not be summed as 0: the asset total is None.
    positions = [_pos("poolA", "w", "MEME", None, Decimal("100"))]
    by_asset = aggregate_by_asset(positions)
    assert by_asset["MEME"]["current_usd"] is None
    assert by_asset["MEME"]["worst_case_usd"] is None


def test_capital_unknown():
    positions = [_pos("poolA", "w", "MEME", Decimal("100"), Decimal("0"))]
    for bad_capital in (None, Decimal("0"), Decimal("-5")):
        result = aggregation_gate(positions, capital_usd=bad_capital)
        assert result["pass"] is False
        assert "CAPITAL_UNKNOWN" in {v["kind"] for v in result["violations"]}


def test_exactly_two_percent_passes():
    # Closed interval: exactly 2% is within the "<= 2%" cap -> passes.
    positions = [_pos("poolA", "w", "MEME", Decimal("200"), Decimal("0"))]
    result = aggregation_gate(positions, capital_usd=Decimal("10000"))
    assert result["pass"] is True
    assert result["violations"] == []


def test_slightly_over_two_percent_blocked():
    positions = [_pos("poolA", "w", "MEME", Decimal("201"), Decimal("0"))]
    result = aggregation_gate(positions, capital_usd=Decimal("10000"))
    assert result["pass"] is False
    assert "SINGLE_ASSET_CURRENT" in {v["kind"] for v in result["violations"]}


def test_empty_positions_pass():
    result = aggregation_gate([], capital_usd=Decimal("10000"))
    assert result["pass"] is True
    assert result["violations"] == []
    assert result["by_asset"] == {}


def test_amounts_and_pcts_are_decimal():
    positions = [_pos("poolA", "w", "MEME", Decimal("300"), Decimal("300"))]
    result = aggregation_gate(positions, capital_usd=Decimal("10000"))
    entry = result["by_asset"]["MEME"]
    assert isinstance(entry["current_usd"], Decimal)
    assert isinstance(entry["worst_case_usd"], Decimal)
    assert isinstance(result["totals"]["meme_total_current_usd"], Decimal)
    for violation in result["violations"]:
        if violation["pct"] is not None:
            assert isinstance(violation["pct"], Decimal)
        if violation["cap"] is not None:
            assert isinstance(violation["cap"], Decimal)


def test_pool_wallet_count_dedup():
    # pool_count / wallet_count are deduplicated counts, not raw position counts.
    positions = [
        _pos("poolA", "w1", "MEME", Decimal("10"), Decimal("0")),
        _pos("poolA", "w1", "MEME", Decimal("10"), Decimal("0")),
        _pos("poolA", "w2", "MEME", Decimal("10"), Decimal("0")),
    ]
    by_asset = aggregate_by_asset(positions)
    assert by_asset["MEME"]["pool_count"] == 1
    assert by_asset["MEME"]["wallet_count"] == 2
    assert len(by_asset["MEME"]["positions"]) == 3


def test_main_writes_json(tmp_path):
    # Offline CLI: reads positions JSON, writes the gate result as JSON.
    positions = [_pos("poolA", "w", "MEME", "300", "300")]
    positions_file = tmp_path / "positions.json"
    positions_file.write_text(json.dumps({"positions": positions}), encoding="utf-8")
    out_file = tmp_path / "out.json"
    rc = main(["--positions-json", str(positions_file),
               "--capital-usd", "10000", "--out", str(out_file)])
    assert rc == 0
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload["pass"] is False
    assert any(v["kind"] == "SINGLE_ASSET_CURRENT" for v in payload["violations"])


def test_worst_case_does_not_branch_on_in_range_and_that_is_deliberate():
    """Pinning the reasoning so nobody "fixes" this by branching on in_range.

    worst_case is asset + paired either way.  In range, crossing out turns the
    whole position into one leg, so the sum is the worst case.  Out of range the
    paired leg is already drained, so the sum equals current.  Branching would
    understate the worst case for in-range positions, which admits risk.
    """
    from decimal import Decimal
    base = {"pool": "p", "wallet": "w", "asset": "DOGE", "paired_asset": "USDG",
            "asset_amount_usd": Decimal("100"), "paired_amount_usd": Decimal("100")}
    inside = position_exposure({**base, "in_range": True})
    outside = position_exposure({**base, "in_range": False})
    assert inside["worst_case_usd"] == outside["worst_case_usd"] == Decimal("200")

    # The realistic out-of-range shape: the paired leg is already gone.
    drained = position_exposure({**base, "paired_amount_usd": Decimal("0"),
                                 "in_range": False})
    assert drained["current_usd"] == drained["worst_case_usd"] == Decimal("100")
