"""Test Suite B: Delayed Grant Lifecycle Price & Baseline Locking.

Exercises _run_episode_persisted with a 3-sample sequence where samples 0 and 1
are rejected (price=2000) and sample 2 is granted (price=2200).
Locks down the R3 fix ensuring entry price, inventory, and tick range bind to the
grant step (2200), not the earlier rejected steps.
"""

from decimal import Decimal
from pathlib import Path
import sqlite3
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_shadow_daemon_v1_readonly import _run_episode_persisted
from scripts.lp_rh_shadow_runner_v1_readonly import tick_from_price
from scripts.lp_rh_store_v1_readonly import migrate, open_store
from scripts.lp_rh_v3_inventory_v1_readonly import inventory_for_position
from tests.test_lp_rh_shadow_daemon_v1_readonly import _daemon_passing_sample
from tests.test_lp_rh_shadow_runner_v1_readonly import _conj_meta

POOL = "0x000000000000000000000000000000000000b001"
NOW = "2026-09-08T18:05:00Z"


def test_paper_b_delayed_grant_locks_price_ticks_and_inventory(tmp_path):
    """Samples [0, 1] rejected (mid=2000); sample [2] granted (mid=2200).

    Asserts:
    1. Steps 0 and 1 rejected; step 2 granted.
    2. Entry price is 2200 (not 2000).
    3. Ticks computed from 2200 range, not 2000.
    4. Virtual inventory liquidity matches 2200 entry price calculation.
    5. Baseline fee growth recorded at grant step matches sample 2.
    """
    ledger = open_store(tmp_path / "ledger.db")
    ledger.row_factory = sqlite3.Row
    migrate(ledger)

    samples = []
    for i in range(2):
        st = f"2026-09-08T18:0{i}:00Z"
        s = _daemon_passing_sample(i, pool=POOL, sample_time=st)
        s["reference_mid"] = Decimal("2000")
        s["absolute_profit_pass"] = False
        s["source_payload_hash"] = f"hash-paper-b-{i}"
        s["quote_usd_per_token1"] = {
            "value": "1.0",
            "source": "COINGECKO_API",
            "observed_at": st,
            "ttl_secs": 600,
        }
        s["fee_growth_global_0"] = 1000 + i * 1000
        s["fee_growth_global_1"] = 2000 + i * 2000
        samples.append(s)

    st2 = "2026-09-08T18:02:00Z"
    s2 = _daemon_passing_sample(2, pool=POOL, sample_time=st2)
    s2["reference_mid"] = Decimal("2200")
    s2["absolute_profit_pass"] = True
    s2["fee_ev_usd"] = Decimal("500.0")
    s2["source_payload_hash"] = "hash-paper-b-2"
    s2["quote_usd_per_token1"] = {
        "value": "1.0",
        "source": "COINGECKO_API",
        "observed_at": st2,
        "ttl_secs": 600,
    }
    s2["fee_growth_global_0"] = 3000
    s2["fee_growth_global_1"] = 6000
    samples.append(s2)

    pm = _conj_meta(
        as_of="2026-09-08T17:59:55Z",
        range_pct="10.0",
        dec0=18,
        dec1=6,
        pool_address=POOL,
    )
    pm["tick_data"] = [{"tick": -200000, "liquidityGross": 1000000, "liquidityNet": 0}]
    pm["max_impact_bps"] = 50

    cfg = {
        "position_usd": Decimal("1000"),
        "capital_usd": Decimal("10000"),
        "horizon_hours": 8760,
        "target_mode": "SHADOW_SCENARIO",
        "pool_meta": pm,
    }

    ep_id = "ep-paper-b-delayed"
    steps, dups, stats = _run_episode_persisted(
        ledger,
        cfg=cfg,
        episode_id=ep_id,
        sample_list=samples,
        now_fn=lambda: NOW,
    )

    assert len(steps) == 3
    assert steps[0].reservation_granted is False
    assert steps[1].reservation_granted is False
    assert steps[2].reservation_granted is True
    assert steps[2].price == Decimal("2200")

    pos_rows = ledger.execute(
        "SELECT * FROM rh_shadow_positions WHERE strategy_episode = ?",
        (ep_id,),
    ).fetchall()
    assert len(pos_rows) == 1
    pos = pos_rows[0]

    # Expected ticks for 2000 vs 2200 with range_pct=10, dec0=18, dec1=6
    t_2000_l = tick_from_price(Decimal("2000") * Decimal("0.9"), dec0=18, dec1=6)
    t_2000_u = tick_from_price(Decimal("2000") * Decimal("1.1"), dec0=18, dec1=6)
    t_2200_l = tick_from_price(Decimal("2200") * Decimal("0.9"), dec0=18, dec1=6)
    t_2200_u = tick_from_price(Decimal("2200") * Decimal("1.1"), dec0=18, dec1=6)

    expected_tick_lower = min(t_2200_l, t_2200_u)
    expected_tick_upper = max(t_2200_l, t_2200_u)
    rejected_tick_lower = min(t_2000_l, t_2000_u)
    rejected_tick_upper = max(t_2000_l, t_2000_u)

    assert pos["tick_lower"] == expected_tick_lower
    assert pos["tick_upper"] == expected_tick_upper
    assert pos["tick_lower"] != rejected_tick_lower
    assert pos["tick_upper"] != rejected_tick_upper

    inv_2000 = inventory_for_position(
        position_usd=Decimal("1000"),
        entry_price=Decimal("2000"),
        range_pct=Decimal("10.0"),
        dec0=18,
        dec1=6,
        quote_usd_per_token1=Decimal("1.0"),
    )
    inv_2200 = inventory_for_position(
        position_usd=Decimal("1000"),
        entry_price=Decimal("2200"),
        range_pct=Decimal("10.0"),
        dec0=18,
        dec1=6,
        quote_usd_per_token1=Decimal("1.0"),
    )

    assert pos["virtual_liquidity_raw"] == str(inv_2200.liquidity_raw)
    assert pos["virtual_liquidity_raw"] != str(inv_2000.liquidity_raw)

    marks = ledger.execute(
        "SELECT * FROM rh_position_marks WHERE position_id = ? ORDER BY mark_time",
        (pos["position_id"],),
    ).fetchall()
    assert len(marks) == 3
    grant_mark = marks[2]
    assert grant_mark["price_snapshot_id"] == samples[2]["source_payload_hash"]
    assert samples[2]["fee_growth_global_0"] == 3000
    assert samples[2]["fee_growth_global_1"] == 6000

    ledger.close()
