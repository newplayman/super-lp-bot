from __future__ import annotations

import json
import sqlite3

import pytest

import scripts.lp_portfolio_paper_runner_v1_readonly as runner

from scripts.lp_shadow_gate_v1_readonly import (
    GateStore,
    MIN_UNIQUE_ROOT_POOLS,
    build_gate_report_markdown,
    evaluate_shadow_gate,
    root_position_identity,
)


def _heartbeat(*, as_of, pools, net_pnl=100.0, portfolio_nav=5_100.0, rpc_health="NORMAL"):
    return {
        "ledger_schema_version": 2,
        "ts_utc": as_of,
        "portfolio_net_usd": net_pnl,
        "portfolio_nav_usd": portfolio_nav,
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
        net_pnl=3.0,
        portfolio_nav=103.0,
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
        _heartbeat(
            as_of="2026-08-08T00:00:00+00:00", pools=[_pool(1)],
            net_pnl=0.0, portfolio_nav=100.0,
        ),
    )
    row = store.record_heartbeat(
        "run-a",
        1,
        _heartbeat(
            as_of="2026-08-08T01:00:00+00:00", pools=[_pool(1)],
            net_pnl=-8.0, portfolio_nav=92.0,
        ),
    )
    assert row["simulated_drawdown_pct"] == pytest.approx(8.0)

    store.record_rpc_health("EXIT_ONLY", as_of="2026-08-08T01:01:00+00:00", source="scanner")
    assert store.unresolved_rpc_severe_count() == 1
    store.record_rpc_health("NORMAL", as_of="2026-08-08T01:02:00+00:00", source="scanner")
    assert store.unresolved_rpc_severe_count() == 0

    store.record_rpc_health("KILLED", as_of="2026-08-08T01:03:00+00:00", source="runner")
    store.record_rpc_health("DEGRADED", as_of="2026-08-08T01:04:00+00:00", source="runner")
    assert store.unresolved_rpc_severe_count() == 1
    store.record_rpc_health("NORMAL", as_of="2026-08-08T01:05:00+00:00", source="runner")
    assert store.unresolved_rpc_severe_count() == 0


def test_gate_report_applies_exact_section_12_thresholds_and_keeps_evidence(tmp_path):
    store = GateStore(tmp_path / "scanner.db")
    pools = [_pool(index) for index in range(50)]
    store.record_heartbeat(
        "run-a",
        0,
        _heartbeat(
            as_of="2026-07-25T00:00:00+00:00", pools=pools,
            net_pnl=0.0, portfolio_nav=5_000.0,
        ),
    )
    store.record_heartbeat(
        "run-a",
        1,
        _heartbeat(
            as_of="2026-08-08T00:00:00+00:00", pools=pools,
            net_pnl=100.0, portfolio_nav=5_100.0,
        ),
    )

    report = evaluate_shadow_gate(store.path, as_of="2026-08-08T00:00:00+00:00")
    markdown = build_gate_report_markdown(report)

    assert report["thresholds"] == {
        "minimum_shadow_days": 14.0,
        "minimum_simulated_positions": 50,
        "minimum_unique_root_pools": 5,
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


def test_sixty_reentries_of_one_pool_cannot_satisfy_position_coverage_gate(tmp_path):
    store = GateStore(tmp_path / "scanner.db")
    pools = []
    for sequence in range(60):
        pool = _pool(sequence)
        pool["position_id"] = f"same-root:reentry:{sequence + 1}"
        pools.append(pool)
    for tick, as_of in enumerate(
        ("2026-07-25T00:00:00+00:00", "2026-08-08T00:00:00+00:00")
    ):
        store.record_heartbeat(
            "run-a", tick,
            _heartbeat(as_of=as_of, pools=pools, net_pnl=100.0),
        )

    report = evaluate_shadow_gate(store.path)
    positions = report["checks"]["simulated_positions"]

    assert positions["value"] == 60
    assert positions["unique_root_pools"] == 1
    assert positions["status"] == "FAIL"
    assert report["position_coverage"] == {
        "unique_position_identities": 60,
        "unique_root_pools": 1,
        "root_pool_rule": "strip trailing :reentry:N suffixes",
    }
    assert report["overall_status"] == "FAIL"
    markdown = build_gate_report_markdown(report)
    assert "unique position identities = 60" in markdown
    assert "unique root pools = 1" in markdown


def test_root_pool_normalization_and_five_pool_coverage_remain_compatible(tmp_path):
    assert root_position_identity("pool-a:reentry:2") == "pool-a"
    assert root_position_identity("pool-a:reentry:2:reentry:3") == "pool-a"
    assert root_position_identity("pool-a:reentry:not-a-number") == (
        "pool-a:reentry:not-a-number"
    )
    assert MIN_UNIQUE_ROOT_POOLS == 5

    store = GateStore(tmp_path / "scanner.db")
    pools = []
    for root in range(5):
        for sequence in range(10):
            pool = _pool(root * 10 + sequence)
            pool["position_id"] = f"pool-{root}:reentry:{sequence + 1}"
            pools.append(pool)
    for tick, as_of in enumerate(
        ("2026-07-25T00:00:00+00:00", "2026-08-08T00:00:00+00:00")
    ):
        store.record_heartbeat(
            "run-a", tick,
            _heartbeat(as_of=as_of, pools=pools, net_pnl=100.0),
        )

    check = evaluate_shadow_gate(store.path)["checks"]["simulated_positions"]
    assert check["value"] == 50
    assert check["unique_root_pools"] == 5
    assert check["status"] == "PASS"


def test_gate_evaluation_fails_closed_without_observations(tmp_path):
    db = tmp_path / "scanner.db"
    GateStore(db).initialize_schema()

    report = evaluate_shadow_gate(db)

    assert report["overall_status"] == "INSUFFICIENT_EVIDENCE"
    assert report["checks"]["fee_prediction_error_pct"]["status"] == "UNKNOWN"
    assert report["checks"]["rpc_severe_unresolved"]["status"] == "PASS"


@pytest.mark.parametrize(
    "raw_pnl",
    [0.0, 1.4210854715202004e-14, 1e-9, -1e-9],
)
def test_shadow_net_pnl_near_zero_noise_never_passes_positive_gate(tmp_path, raw_pnl):
    store = GateStore(tmp_path / "scanner.db")
    pools = [_pool(index, pnl=0.0) for index in range(50)]
    store.record_heartbeat(
        "run-a", 0,
        _heartbeat(
            as_of="2026-07-25T00:00:00+00:00", pools=pools,
            net_pnl=0.0, portfolio_nav=5_000.0,
        ),
    )
    pools[-1]["pnl_vs_usdc"] = raw_pnl
    store.record_heartbeat(
        "run-a", 1,
        _heartbeat(
            as_of="2026-08-08T00:00:00+00:00", pools=pools,
            net_pnl=raw_pnl, portfolio_nav=5_000.0 + raw_pnl,
        ),
    )

    check = evaluate_shadow_gate(store.path)["checks"]["shadow_net_pnl_usd"]

    assert check["raw_value"] == pytest.approx(raw_pnl)
    assert check["value"] == 0.0
    assert check["status"] == "FAIL"


def test_shadow_net_pnl_above_published_zero_tolerance_can_pass(tmp_path):
    store = GateStore(tmp_path / "scanner.db")
    pools = [_pool(index, pnl=0.0) for index in range(50)]
    store.record_heartbeat(
        "run-a", 0,
        _heartbeat(
            as_of="2026-07-25T00:00:00+00:00", pools=pools,
            net_pnl=0.0, portfolio_nav=5_000.0,
        ),
    )
    meaningful = 1.000001e-9
    pools[-1]["pnl_vs_usdc"] = meaningful
    store.record_heartbeat(
        "run-a", 1,
        _heartbeat(
            as_of="2026-08-08T00:00:00+00:00", pools=pools,
            net_pnl=meaningful, portfolio_nav=5_000.0 + meaningful,
        ),
    )

    report = evaluate_shadow_gate(store.path)
    check = report["checks"]["shadow_net_pnl_usd"]

    assert check["raw_value"] == pytest.approx(meaningful)
    assert check["value"] == pytest.approx(meaningful)
    assert check["status"] == "PASS"
    assert report["measurement_precision"]["usd_near_zero_tolerance"] == 1e-9
    assert "<= 1e-09 USD" in build_gate_report_markdown(report)


def test_runner_tick_exposes_nav_fee_prediction_and_rpc_health(monkeypatch):
    state = runner.init_state(
        capital=100.0, anchor=1.0, range_pct=10.0, fee_tier=0.003,
        dec0=18, dec1=18, last_block=0,
    )
    book = [{
        "symbol": "TEST/USDC", "project": "test", "tier": "A", "pool": "0x1",
        "fee_apr_onchain": 10.0, "reward_apr": 0.0,
        "reward_price_usd": 1.0, "last_price": 1.0, "state": state,
    }]
    class HealthyPool:
        def call(self, method, params):
            raise AssertionError((method, params))

        def health_snapshot(self):
            return {"state": "NORMAL"}
    monkeypatch.setattr(runner, "_POOL", HealthyPool())
    monkeypatch.setattr(runner, "_latest_block", lambda: 1)
    monkeypatch.setattr(runner, "fetch_pool_swaps", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        runner, "_now_utc",
        lambda: __import__("datetime").datetime(2026, 8, 8, tzinfo=__import__("datetime").timezone.utc),
    )

    record, _ = runner._tick(
        book,
        last_ts=__import__("datetime").datetime(2025, 8, 8, tzinfo=__import__("datetime").timezone.utc),
    )

    assert record["rpc_health"] == "NORMAL"
    assert record["portfolio_nav_usd"] == pytest.approx(100.0)
    assert record["portfolio_net_usd"] == pytest.approx(0.0)
    assert record["by_pool"][0]["fee_prediction_usd"] == pytest.approx(10.0)


def test_runner_gate_write_is_normal_tick_path_not_manual_helper(tmp_path):
    store = GateStore(tmp_path / "scanner.db")
    heartbeat = _heartbeat(
        as_of="2026-08-08T00:00:00+00:00",
        pools=[_pool(1)], net_pnl=2.0, portfolio_nav=102.0,
    )

    row = runner._record_gate_observation(store, "run-a", 3, heartbeat)

    assert row["source_run"] == "run-a"
    assert row["tick"] == 3
