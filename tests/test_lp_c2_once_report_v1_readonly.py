import json
import sqlite3

from scripts.lp_c2_once_report_v1_readonly import build, render_markdown


def test_report_renders_position_cap_per_pool(tmp_path):
    db = tmp_path / "scanner.db"
    connection = sqlite3.connect(db)
    connection.execute(
        "CREATE TABLE opportunity_scores(pool TEXT,symbol TEXT,accepted INTEGER,rejection_reason TEXT,"
        "expected_net_yield_pct REAL,score_json TEXT,as_of TEXT)"
    )
    score = {"capital_tier": "M1", "tvlUsd": 200_000, "active_liquidity_notional_usd": 10_000,
             "position_cap_usd": 60, "position_cap_pass": True, "netcover_pass": False,
             "entry_eligible": True, "vetted": False}
    connection.execute("INSERT INTO opportunity_scores VALUES(?,?,?,?,?,?,?)",
                       ("0x1", "USDC-WETH", 0, "NETCOVER_BELOW_SHADOW", -1, json.dumps(score), "2026-08-09T00:00:00Z"))
    connection.commit()
    report = build(db)
    assert report["pool_count"] == 1
    assert report["position_cap_pass_count"] == 1
    assert "0x1" in render_markdown(report)
