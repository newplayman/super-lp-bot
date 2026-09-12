"""Test Suite C: Full-Cost Flat Price Accounting & Seed Capital NAV Baseline.

Exercises _run_episode_persisted with a 5-sample flat-price sequence (price=2000),
zero fee APR, zero rewards, and position_open=True from sample 0 onward.
Injects round-trip costs: entry_cost_usd=5, exit_cost_usd=3, gas_usd=2.

Asserts:
1. episode_summary.net_pnl == -10 (relative error <= 1e-12).
2. episode_summary.nav_start == 1000 (pre-trade seed capital, not first mark).
3. steps[0].nav == 990 (cost recognized at open step).
4. compute_full_cost_nav matches episode step NAV.
"""

from decimal import Decimal
from pathlib import Path
import sqlite3
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_pnl_v1_readonly import compute_full_cost_nav
from scripts.lp_rh_shadow_daemon_v1_readonly import _run_episode_persisted
from scripts.lp_rh_shadow_runner_v1_readonly import episode_summary
import scripts.lp_rh_shadow_runner_v1_readonly as runner_mod
from scripts.lp_rh_store_v1_readonly import migrate, open_store
from tests.test_lp_rh_shadow_daemon_v1_readonly import _daemon_passing_sample
from tests.test_lp_rh_shadow_runner_v1_readonly import _conj_meta

POOL = "0x000000000000000000000000000000000000c001"
NOW = "2026-09-08T18:10:00Z"


def test_paper_c_full_cost_flat_nav_and_pnl_window(tmp_path, monkeypatch):
    ledger = open_store(tmp_path / "ledger.db")
    ledger.row_factory = sqlite3.Row
    migrate(ledger)

    samples = []
    for i in range(5):
        st = f"2026-09-08T18:0{i}:00Z"
        s = _daemon_passing_sample(i, pool=POOL, sample_time=st)
        s["reference_mid"] = Decimal("2000")
        s["fee_apr_pct"] = Decimal("0")
        s["reward_ev_usd"] = Decimal("0")
        s["position_open"] = True
        s["source_payload_hash"] = f"hash-paper-c-{i}"
        s["quote_usd_per_token1"] = {
            "value": "1.0",
            "source": "COINGECKO_API",
            "observed_at": st,
            "ttl_secs": 600,
        }
        s["fee_growth_global_0"] = 1000
        s["fee_growth_global_1"] = 1000
        samples.append(s)

    pm = _conj_meta(
        as_of="2026-09-08T17:59:55Z",
        range_pct="10.0",
        dec0=18,
        dec1=6,
        pool_address=POOL,
    )
    pm["tick_data"] = [{"tick": -200000, "liquidityGross": 1000000, "liquidityNet": 0}]
    pm["max_impact_bps"] = 50
    pm["entry_cost_usd"] = Decimal("5")
    pm["exit_cost_usd"] = Decimal("3")
    pm["gas_usd"] = Decimal("2")

    cfg = {
        "position_usd": Decimal("400"),
        "capital_usd": Decimal("1000"),
        "horizon_hours": 8760,
        "target_mode": "SHADOW_SCENARIO",
        "pool_meta": pm,
        "entry_cost_usd": Decimal("5"),
        "exit_cost_usd": Decimal("3"),
        "gas_usd": Decimal("2"),
    }

    # Ensure position opens from sample 0 onward despite fee_apr_pct=0
    orig_apply = runner_mod.apply_netcover_gate

    def mock_apply(records, **kwargs):
        res = orig_apply(records, **kwargs)
        for r in res:
            r["netcover_pass"] = True
            r["fee_ev_usd"] = 500.0
        return res

    monkeypatch.setattr(runner_mod, "apply_netcover_gate", mock_apply)

    ep_id = "ep-paper-c-flat-cost"
    steps, dups, stats = _run_episode_persisted(
        ledger,
        cfg=cfg,
        episode_id=ep_id,
        sample_list=samples,
        now_fn=lambda: NOW,
    )

    assert len(steps) == 5
    assert steps[0].reservation_granted is True
    marks = ledger.execute("SELECT unvalued_risk_json FROM rh_position_marks ORDER BY mark_time").fetchall()
    import json
    assert json.loads(marks[0]["unvalued_risk_json"])["position_open"] is True

    # 1. steps[0].nav == 990 (cost recognized at open step, not deferred)
    expected_step0_nav = Decimal("990")
    assert steps[0].nav is not None
    assert abs(steps[0].nav - expected_step0_nav) < Decimal("1e-9")

    # 2. episode_summary.nav_start == 1000 (pre-trade seed capital)
    # 3. episode_summary.net_pnl == -10
    summary = episode_summary(
        steps,
        capital_usd=cfg["capital_usd"],
        pool_meta=cfg["pool_meta"],
    )

    assert summary["nav_start"] == Decimal("1000")
    assert summary["nav_end"] is not None
    assert abs(summary["nav_end"] - Decimal("990")) < Decimal("1e-9")

    expected_pnl = Decimal("-10")
    assert summary["net_pnl"] is not None
    rel_error = abs(summary["net_pnl"] - expected_pnl) / abs(expected_pnl)
    assert rel_error <= Decimal("1e-12")

    # 4. Cross-check with compute_full_cost_nav
    wallet = cfg["capital_usd"] - cfg["position_usd"]  # 1000 - 400 = 600
    lp_principal = cfg["position_usd"]  # 400
    cross_nav = compute_full_cost_nav(
        wallet=wallet,
        lp_principal=lp_principal,
        accrued_fees=0,
        entry_cost_usd=Decimal("5"),
        exit_cost_usd=Decimal("3"),
        gas_usd=Decimal("2"),
        slippage_usd=0,
        verified_rewards=0,
        liabilities=0,
    )
    assert cross_nav == Decimal("990")
    assert abs(steps[0].nav - cross_nav) < Decimal("1e-9")

    ledger.close()
