from decimal import Decimal
import sqlite3
import pytest

from scripts.lp_rh_shadow_runner_v1_readonly import run_episode
from scripts.lp_rh_store_v1_readonly import open_store, migrate
from tests.test_lp_rh_shadow_runner_v1_readonly import _passing_sample, _run


def test_open_lifecycle_inventory_and_bounds_frozen_on_grant_only(tmp_path):
    """R2-02: Verify pre-grant steps do not record virtual inventory or accrue prior fee growth; bounds frozen only on grant."""
    db_path = tmp_path / "test_r2_02.db"
    conn = open_store(db_path)
    conn.row_factory = sqlite3.Row
    migrate(conn)

    # Step 0: not eligible, position not granted
    s0 = _passing_sample(
        0,
        price=Decimal("2000.0"),
        fee_growth=(1000, 1000),
        quote_usd_per_token1="1.0",
        quote_source="COINGECKO_API",
        quote_as_of="2026-01-01T00:00:00Z",
        absolute_profit_pass=False,  # fails gate
    )

    # Step 1: granted
    s1 = _passing_sample(
        1,
        price=Decimal("2000.0"),
        fee_growth=(2000, 2000),
        quote_usd_per_token1="1.0",
        quote_source="COINGECKO_API",
        quote_as_of="2026-01-01T00:01:00Z",
    )

    # Step 2: in position, fees accrue from baseline set at step 1
    s2 = _passing_sample(
        2,
        price=Decimal("2000.0"),
        fee_growth=(3000, 3000),
        quote_usd_per_token1="1.0",
        quote_source="COINGECKO_API",
        quote_as_of="2026-01-01T00:02:00Z",
    )

    pool_meta = {
        "pool_address": "0xpool",
        "range_pct": "10.0",
        "dec0": 18,
        "dec1": 6,
        "as_of": "2026-01-01T00:00:00Z",
    }

    steps = _run(conn, [s0, s1, s2], pool_meta=pool_meta, episode="ep_r2_02")

    assert len(steps) == 3

    # Step 0: not granted, cash valuation, no virtual LP inventory
    assert steps[0].reservation_granted is False
    assert steps[0].nav == Decimal("10000")  # Cash valuation
    assert steps[0].hodl_value is None
    assert steps[0].nav_reason == "POSITION_NOT_OPEN"

    # Positions table only recorded on step 1
    positions = conn.execute("SELECT * FROM rh_shadow_positions WHERE strategy_episode = 'ep_r2_02'").fetchall()
    assert len(positions) == 1

    # Step 1: granted step sets baseline
    assert steps[1].reservation_granted is True

    # Marks table checks
    marks = conn.execute("SELECT accrued_fee, liquidation_nav FROM rh_position_marks ORDER BY rowid ASC").fetchall()
    assert len(marks) == 3
    # Step 0 & 1 have 0 accrued fee
    assert Decimal(str(marks[0]["accrued_fee"])) == Decimal(0)
    assert Decimal(str(marks[1]["accrued_fee"])) == Decimal(0)
    # Step 2: in position, accrued fees reflect growth ONLY from step 1 (baseline) to step 2
    assert Decimal(str(marks[2]["accrued_fee"])) > Decimal(0)

    conn.close()
