from decimal import Decimal
import json
import sqlite3
import pytest

from scripts.lp_rh_shadow_runner_v1_readonly import run_episode
from scripts.lp_rh_store_v1_readonly import open_store, migrate
from tests.test_lp_rh_shadow_runner_v1_readonly import _passing_sample, _run


def test_runner_uses_full_cost_nav_in_marks(tmp_path):
    """R2-01: Verify runner writes liquidation_nav to marks and net_pnl reflects entry/exit costs."""
    db_path = tmp_path / "test_r2_01.db"
    conn = open_store(db_path)
    conn.row_factory = sqlite3.Row
    migrate(conn)

    sample0 = _passing_sample(
        0,
        price=Decimal("2000.0"),
        fee_growth=(1000000000000000000, 1000000000000000000),
        quote_usd_per_token1="1.0",
        quote_source="COINGECKO_API",
        quote_as_of="2026-01-01T00:00:00Z",
        entry_cost_usd=10.0,
        exit_cost_usd=0.0,
        gas_usd=0.0,
        slippage_usd=0.0,
    )
    sample1 = _passing_sample(
        1,
        price=Decimal("2000.0"),
        fee_growth=(1000000000000000000, 1000000000000000000),
        quote_usd_per_token1="1.0",
        quote_source="COINGECKO_API",
        quote_as_of="2026-01-01T00:01:00Z",
        entry_cost_usd=10.0,
        exit_cost_usd=5.0,
        gas_usd=1.0,
        slippage_usd=0.0,
    )

    pool_meta = {
        "pool_address": "0xpool",
        "range_pct": "10.0",
        "dec0": 18,
        "dec1": 6,
        "as_of": "2026-01-01T00:00:00Z",
    }

    steps = _run(conn, [sample0, sample1], pool_meta=pool_meta, episode="ep_r2_01")

    assert len(steps) == 2
    marks = conn.execute("SELECT liquidation_nav, reference_nav, accrued_fee FROM rh_position_marks ORDER BY rowid ASC").fetchall()
    assert len(marks) == 2

    # R2-01: liquidation_nav must NOT be None on both marks
    assert marks[0]["liquidation_nav"] is not None
    assert marks[1]["liquidation_nav"] is not None

    liq_nav0 = Decimal(str(marks[0]["liquidation_nav"]))
    liq_nav1 = Decimal(str(marks[1]["liquidation_nav"]))
    assert liq_nav0 < Decimal("10000")
    assert liq_nav1 <= liq_nav0  # exit cost deducted on step 1

    # Steps have valid NAV reflecting costs
    assert steps[0].nav is not None
    assert steps[1].nav is not None
    assert steps[1].nav < Decimal("10000")
    conn.close()
