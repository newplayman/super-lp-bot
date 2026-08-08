from __future__ import annotations

import json
import sqlite3

import pytest

from scripts.lp_shadow_gate_v1_readonly import (
    GateStore,
    build_gate_report_markdown,
    evaluate_shadow_gate,
)


def _heartbeat(*, as_of, pools, nav=5_100.0, rpc_health="NORMAL"):
    return {
        "ledger_schema_version": 2,
        "ts_utc": as_of,
        "portfolio_net_usd": nav,
        "rpc_health": rpc_health,
        "by_pool": pools,
    }


def _pool(index, *, predicted=10.0, actual=9.0, pnl=2.0):
    return {
        "pool": f"pool-{index}",
        "entry_capital_usd": 100.0,
        "fee_prediction_usd": predicted,
        "swap_fee_income": actual,
        "pnl_vs_usdc": pnl,
    }


def test_schema_migrates_existing_scanner_db_without_changing_old_tables(tmp_path):
    db = tmp_path / "scanner.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE pool_snapshots (id INTEGER PRIMARY KEY, as_of TEXT)")
        connection.execute("INSERT INTO pool_snapshots(as_of) VALUES ('old')")

    GateStore(db).initialize_schema()

    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT as_of FROM pool_snapshots").fetchone() == ("old",)
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"shadow_gate_observations", "shadow_positions", "rpc_severe_incidents"} <= tables


def test_runner_heartbeat_is_idempotently_recorded_with_public_fee_error_formula(tmp_path):
    store = GateStore(tmp_path / "scanner.db")
    heartbeat = _heartbeat(
        as_of="2026-08-08T00:00:00+00:00",
        pools=[_pool(1, predicted=10.0, actual=8.0, pnl=3.0)],
        nav=103.0,
    )

    first = store.record_heartbeat("run-a", 7, heartbeat)
    second = store.record_heartbeat("run-a", 7, heartbeat)

    assert first["evidence_status"] == "COMPLETE"
    assert first["fee_prediction_error_pct"] == pytest.approx(20.0)
    assert first["shadow_net_pnl_usd"] == pytest.approx(3.0)
    assert second == first
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT count(*) FROM shadow_gate_observations").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM shadow_positions").fetchone()[0] == 1


@pytest.mark.parametrize("prediction", [None, float("nan"), 0.0, -1.0])
def test_missing_or_invalid_fee_prediction_is_unknown_never_zero_error(tmp_path, prediction):
    pool = _pool(1)
    pool["fee_prediction_usd"] = prediction

    row = GateStore(tmp_path / "scanner.db").record_heartbeat(
        "run-a", 0, _heartbeat(as_of="2026-08-08T00:00:00+00:00", pools=[pool])
    )

    assert row["fee_prediction_error_pct"] is None
    assert row["fee_prediction_status"] == "UNKNOWN"
    assert row["evidence_status"] == "INCOMPLETE"


def test_drawdown_uses_running_portfolio_peak_and_rpc_incident_resolves_on_normal(tmp_path):
    store = GateStore(tmp_path / "scanner.db")
    store.record_heartbeat(
        "run-a",
        0,
        _heartbeat(as_of="2026-08-08T00:00:00+00:00", pools=[_pool(1)], nav=100.0),
    )
    row = store.record_heartbeat(
        "run-a",
        1,
        _heartbeat(as_of="2026-08-08T01:00:00+00:00", pools=[_pool(1)], nav=92.0),
    )
    assert row["simulated_drawdown_pct"] == pytest.approx(8.0)

    store.record_rpc_health("EXIT_ONLY", as_of="2026-08-08T01:01:00+00:00", source="scanner")
    assert store.unresolved_rpc_severe_count() == 1
    store.record_rpc_health("NORMAL", as_of="2026-08-08T01:02:00+00:00", source="scanner")
    assert store.unresolved_rpc_severe_count() == 0


def test_gate_report_applies_exact_section_12_thresholds_and_keeps_evidence(tmp_path):
    store = GateStore(tmp_path / "scanner.db")
    pools = [_pool(index) for index in range(50)]
    store.record_heartbeat(
        "run-a",
        0,
        _heartbeat(as_of="2026-07-25T00:00:00+00:00", pools=pools, nav=5_000.0),
    )
    store.record_heartbeat(
        "run-a",
        1,
        _heartbeat(as_of="2026-08-08T00:00:00+00:00", pools=pools, nav=5_100.0),
    )

    report = evaluate_shadow_gate(store.path, as_of="2026-08-08T00:00:00+00:00")
    markdown = build_gate_report_markdown(report)

    assert report["thresholds"] == {
        "minimum_shadow_days": 14.0,
        "minimum_simulated_positions": 50,
        "maximum_fee_prediction_error_pct": 20.0,
        "minimum_shadow_net_pnl_usd_exclusive": 0.0,
        "maximum_simulated_drawdown_pct": 8.0,
        "maximum_unresolved_rpc_severe_incidents": 0,
    }
    assert report["overall_status"] == "PASS"
    assert all(item["status"] == "PASS" for item in report["checks"].values())
    assert "fee_prediction_error_pct = abs(actual - predicted) / predicted * 100" in markdown
    assert "不授权 M1" in markdown
    json.dumps(report, allow_nan=False)


def test_gate_evaluation_fails_closed_without_observations(tmp_path):
    db = tmp_path / "scanner.db"
    GateStore(db).initialize_schema()

    report = evaluate_shadow_gate(db)

    assert report["overall_status"] == "INSUFFICIENT_EVIDENCE"
    assert report["checks"]["fee_prediction_error_pct"]["status"] == "UNKNOWN"
    assert report["checks"]["rpc_severe_unresolved"]["status"] == "PASS"
