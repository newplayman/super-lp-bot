from decimal import Decimal
import sqlite3
import pytest

from scripts.lp_rh_shadow_runner_v1_readonly import run_episode
from scripts.lp_rh_store_v1_readonly import open_store, migrate
from tests.test_lp_rh_shadow_runner_v1_readonly import _passing_sample, _run


def test_pool_state_fault_blocks_live_readiness_mode(tmp_path):
    """R2-06: Verify pool_state_fault blocks terminal_eligible when target_mode is LIVE_READINESS."""
    conn = open_store(tmp_path / "live_mode.db")
    migrate(conn)

    pool_meta = {
        "pool_address": "0xpool",
        "range_pct": "10.0",
        "dec0": 18,
        "dec1": 6,
        "as_of": "2026-01-01T00:00:00Z",
    }

    # Sample is 24 hours later than pool_meta as_of (> 21600s) -> POOL_STATE_STALE
    sample = _passing_sample(
        0,
        sample_time="2026-01-02T00:00:00Z",
        price=Decimal("2000.0"),
        quote_usd_per_token1="1.0",
        quote_source="COINGECKO_API",
        quote_as_of="2026-01-02T00:00:00Z",
    )

    steps = _run(
        conn,
        [sample],
        pool_meta=pool_meta,
        target_mode="LIVE_READINESS",
        episode="ep_r2_06_live",
    )

    assert len(steps) == 1
    # Must be blocked in LIVE_READINESS
    assert steps[0].terminal_eligible is False
    assert steps[0].reservation_granted is False
    conn.close()


def test_pool_state_fault_tolerated_in_shadow_scenario(tmp_path):
    """R2-06: Verify SHADOW_SCENARIO tolerates stale pool state when freshness enforcement is not requested."""
    conn = open_store(tmp_path / "shadow_mode.db")
    migrate(conn)

    sample = _passing_sample(
        0,
        price=Decimal("2000.0"),
        quote_usd_per_token1="1.0",
        quote_source="COINGECKO_API",
        quote_as_of="2026-01-01T00:00:00Z",
        pool_state_fault=True,
    )

    pool_meta = {
        "pool_address": "0xpool",
        "range_pct": "10.0",
        "dec0": 18,
        "dec1": 6,
        "as_of": "2026-01-01T00:00:00Z",
    }

    steps = _run(
        conn,
        [sample],
        target_mode="SHADOW_SCENARIO",
        pool_meta=pool_meta,
        episode="ep_r2_06_shadow",
    )

    assert len(steps) == 1
    # In SHADOW_SCENARIO, pool_state_fault alone does not block terminal eligibility
    assert steps[0].terminal_eligible is True
    assert steps[0].reservation_granted is True
    conn.close()
