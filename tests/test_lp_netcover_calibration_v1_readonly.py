"""TP-J calibration contracts; all inputs are in-memory and read-only."""
from __future__ import annotations

import json
import sqlite3

import pytest

from scripts import lp_netcover_calibration_v1_readonly as calibration


def _snapshot_db(tmp_path, pool: str) -> None:
    db_path = tmp_path / "snapshot.db"
    con = sqlite3.connect(db_path)
    con.execute("create table opportunity_scores (pool text, as_of text, score_json text, id integer)")
    con.execute(
        "insert into opportunity_scores values (?, ?, ?, 1)",
        (pool, "2026-01-02T00:00:00+00:00", json.dumps({
            "measured_token1_usd": 1.0, "last_swap_liquidity_raw": 1e20,
            "last_swap_price_token1_per_token0": 100.0, "dec0": 18, "dec1": 6,
            "reward_ev_usd": 2.0, "reward_conversion_cost_usd": 0.02,
        })),
    )
    con.commit()
    con.close()


def test_calibration_preserves_observed_income_and_labels_absent_paper_costs(tmp_path, monkeypatch):
    pool = "0xpositive"
    _snapshot_db(tmp_path, pool)
    monkeypatch.setattr(calibration, "SNAPSHOT_SOURCES", {pool: ("snapshot.db", "2026-01-02T00:00:00+00:00")})
    report = calibration.calibrate(
        book=[{"pool": pool, "symbol": "X-Y", "project": "test", "capital": 1000, "fee_tier": 0.003, "range_pct": 20.0}],
        heartbeat={"ts_utc": "2026-01-03T00:00:00+00:00", "started_at": "2026-01-01T00:00:00+00:00", "by_pool": [{"pool": pool, "fees": 100, "reward": 20, "il": -5}]},
        repo_root=tmp_path,
    )
    row = report["rows"][0]
    assert row["holding_hours"] == pytest.approx(48.0)
    assert row["netcover"]["fee_ev_usd"] == 100.0
    assert row["netcover"]["reward_haircut_deduction_usd"] == 10.0
    assert row["paper_runner"]["entry_cost_usd"] == "UNMODELED"
    entry = next(item for item in row["differences_descending"] if item["component"] == "entry_cost_usd")
    assert entry["netcover_over_paper_factor"] == "N/A (paper UNMODELED)"
    assert row["netcover_pass"] is True


def test_full_position_baseline_uses_quote_usd_normalisation():
    snapshot = {
        "measured_token1_usd": 20.0, "last_swap_liquidity_raw": 1e23,
        "last_swap_price_token1_per_token0": 0.05, "dec0": 18, "dec1": 8,
    }
    costs = calibration._position_leg_swap_components(
        capital_usd=1000.0, fee_tier=0.003, range_pct=20.0, snapshot=snapshot,
        legacy_full_position_legs=True,
    )
    assert costs["entry_cost_usd"] == pytest.approx(3.0)
    assert costs["exit_cost_usd"] == pytest.approx(3.0)
    assert costs["slippage_usd"] >= 0.0
