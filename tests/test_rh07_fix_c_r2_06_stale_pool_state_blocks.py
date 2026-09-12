"""R2-06 + R3 / Package D: pool state freshness blocks new simulated
positions by default, including in SHADOW_SCENARIO and when ``as_of``
is unknown.

Re-audit 04e8a45 / 6fda329 confirmed:
  * ``pool_state_as_of is None`` only appended a reason and let the step
    stay eligible — silent acceptance of as-of-unknown evidence.
  * The block fired only when ``target_mode == LIVE_READINESS`` or an
    explicit ``enforce_pool_state_freshness`` flag was set; SHADOW_SCENARIO
    with no flag silently accepted stale / unknown evidence.
"""

from decimal import Decimal
import sqlite3

import pytest

from scripts.lp_rh_shadow_runner_v1_readonly import run_episode
from scripts.lp_rh_store_v1_readonly import open_store, migrate
from tests.test_lp_rh_shadow_runner_v1_readonly import _passing_sample, _run


def test_stale_pool_state_blocks_live_readiness(tmp_path):
    """R2-06 control: LIVE_READINESS + 24h stale as_of blocks."""
    conn = open_store(tmp_path / "live_mode.db")
    conn.row_factory = sqlite3.Row
    migrate(conn)

    pool_meta = {
        "pool_address": "0xpool",
        "range_pct": "10.0",
        "dec0": 18,
        "dec1": 6,
        "as_of": "2026-01-01T00:00:00Z",
    }

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
    assert steps[0].terminal_eligible is False
    assert steps[0].reservation_granted is False
    conn.close()


def test_stale_pool_state_blocks_default_shadow(tmp_path):
    """R3 / Package D: SHADOW_SCENARIO + stale as_of now BLOCKS by
    default.  Previously the 6fda329 code accepted it unless an
    ``enforce_pool_state_freshness`` flag was set; the re-audit flagged
    this as a regression.
    """
    conn = open_store(tmp_path / "shadow_stale.db")
    conn.row_factory = sqlite3.Row
    migrate(conn)

    pool_meta = {
        "pool_address": "0xpool",
        "range_pct": "10.0",
        "dec0": 18,
        "dec1": 6,
        "as_of": "2026-01-01T00:00:00Z",
    }
    sample = _passing_sample(
        0,
        sample_time="2026-01-02T00:00:00Z",  # 24h stale
        price=Decimal("2000.0"),
        quote_usd_per_token1="1.0",
        quote_source="COINGECKO_API",
        quote_as_of="2026-01-02T00:00:00Z",
    )

    steps = _run(
        conn,
        [sample],
        pool_meta=pool_meta,
        target_mode="SHADOW_SCENARIO",
        episode="ep_r2_06_shadow_stale",
    )

    assert len(steps) == 1
    # R3 fix: stale pool state blocks by default, no flag required.
    assert steps[0].terminal_eligible is False, (
        "stale pool_state_as_of must block terminal eligibility by default; "
        "the 6fda329 code required an explicit enforce flag"
    )
    assert steps[0].reservation_granted is False
    conn.close()


def test_unknown_pool_state_as_of_blocks_default_shadow(tmp_path):
    """R3 / Package D: ``pool_meta.as_of = None`` (unknown provenance)
    now sets pool_state_fault=True and blocks by default.  Previously
    this only appended ``POOL_STATE_AS_OF_UNAVAILABLE`` and let the
    step stay eligible — silent acceptance of as-of-unknown evidence.
    """
    conn = open_store(tmp_path / "shadow_unknown.db")
    conn.row_factory = sqlite3.Row
    migrate(conn)

    pool_meta = {
        "pool_address": "0xpool",
        "range_pct": "10.0",
        "dec0": 18,
        "dec1": 6,
        # No 'as_of' field -> as-of-unknown
    }
    sample = _passing_sample(
        0,
        sample_time="2026-01-01T00:00:00Z",
        price=Decimal("2000.0"),
        quote_usd_per_token1="1.0",
        quote_source="COINGECKO_API",
        quote_as_of="2026-01-01T00:00:00Z",
    )

    steps = _run(
        conn,
        [sample],
        pool_meta=pool_meta,
        target_mode="SHADOW_SCENARIO",
        episode="ep_r2_06_unknown",
    )

    assert len(steps) == 1
    assert steps[0].terminal_eligible is False, (
        "pool_meta.as_of = None must block terminal eligibility by default; "
        "the 6fda329 code only appended a reason and let the step stay eligible"
    )
    assert steps[0].reservation_granted is False
    conn.close()


def test_fresh_pool_state_allows_default_shadow(tmp_path):
    """R3 / Package D control: a fresh pool_meta.as_of (<= 6h old) must
    still allow the step to remain eligible.  Regression check: the
    fix doesn't over-block."""
    conn = open_store(tmp_path / "shadow_fresh.db")
    conn.row_factory = sqlite3.Row
    migrate(conn)

    pool_meta = {
        "pool_address": "0xpool",
        "range_pct": "10.0",
        "dec0": 18,
        "dec1": 6,
        "as_of": "2026-01-01T00:00:00Z",
    }
    sample = _passing_sample(
        0,
        sample_time="2026-01-01T01:00:00Z",  # 1h fresh
        price=Decimal("2000.0"),
        quote_usd_per_token1="1.0",
        quote_source="COINGECKO_API",
        quote_as_of="2026-01-01T01:00:00Z",
    )

    steps = _run(
        conn,
        [sample],
        pool_meta=pool_meta,
        target_mode="SHADOW_SCENARIO",
        episode="ep_r2_06_fresh",
    )

    assert len(steps) == 1
    assert steps[0].terminal_eligible is True
    assert steps[0].reservation_granted is True
    conn.close()
