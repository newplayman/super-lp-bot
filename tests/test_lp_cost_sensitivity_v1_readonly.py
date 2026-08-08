"""Cost Sensitivity replay contracts for the real Base vetted-pool snapshot."""

import json

import pytest

from scripts.lp_cost_sensitivity_v1_readonly import (
    SIZES_USD,
    BasePoolParameters,
    analyse_sizes,
    default_base_vetted_pool,
    price_from_sqrt_x96,
    render_report,
    write_report,
)


def test_default_parameters_are_traceable_real_base_vetted_pool():
    pool = default_base_vetted_pool()
    assert isinstance(pool, BasePoolParameters)
    assert pool.chain == "base"
    assert pool.symbol == "WETH-USDC"
    assert pool.address == "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"
    assert pool.source_paths
    assert all(path.startswith("reports/") for path in pool.source_paths)
    assert pool.pool_tvl_usd > 0
    assert pool.active_liquidity_notional_usd > 0


def test_price_and_raw_liquidity_come_from_real_swap_not_range_l_factor():
    pool = default_base_vetted_pool()
    # First matching historical Swap row: sqrtPriceX96 and raw active liquidity.
    sqrt_price_x96 = 3237636589800383610325516
    assert pool.price_usd == pytest.approx(
        price_from_sqrt_x96(sqrt_price_x96, dec0=18, dec1=6)
    )
    assert pool.price_usd == pytest.approx(1669.9252504577303)
    assert pool.price_usd != pytest.approx(1721.743864340594)  # R4B l_factor, not price
    assert pool.l_active_raw_historical == 2641450665466979248
    assert any("swap_event_fee_replay" in path for path in pool.source_paths)


def test_six_required_sizes_and_cost_math_are_self_consistent():
    pool = default_base_vetted_pool()
    rows = analyse_sizes(pool)
    assert [row["size_usd"] for row in rows] == list(SIZES_USD) == [25, 50, 75, 100, 200, 500]
    for row in rows:
        assert row["round_trip_cost_usd"] > 0
        assert row["break_even_holding_hours"] > 0
        assert row["min_economic_position_usd"] > 0
        assert row["adjusted_income_rate_per_year"] > row["risk_rate_per_year"]
        assert row["position_cap_usd"] > 0
        assert row["source_kind"] == "historical_real_base_vetted_pool"


def test_break_even_recomputes_from_rate_and_fixed_cost():
    row = analyse_sizes(default_base_vetted_pool())[0]
    annual_net_dollars = row["size_usd"] * (
        row["adjusted_income_rate_per_year"] - row["risk_rate_per_year"]
    )
    recomputed_hours = row["fixed_cost_usd"] / annual_net_dollars * 365.0 * 24.0
    assert row["break_even_holding_hours"] == pytest.approx(recomputed_hours)


def test_report_writes_json_and_markdown_to_requested_directory(tmp_path):
    pool = default_base_vetted_pool()
    rows = analyse_sizes(pool)
    out = write_report(tmp_path, pool, rows, as_of="2026-08-08T00:00:00Z")
    payload = json.loads((tmp_path / "cost_sensitivity.json").read_text())
    md = (tmp_path / "cost_sensitivity.md").read_text()
    assert out == tmp_path
    assert len(payload["rows"]) == 6
    assert payload["pool"]["address"] == pool.address
    assert "break-even" in md
    assert "MinEconomicPosition" in md
    assert render_report(pool, rows, "2026-08-08T00:00:00Z") == md
