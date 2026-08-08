from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.lp_scanner_daemon_v1_readonly import (
    DEFAULT_COARSE_INTERVAL_SECS,
    DEFAULT_TOP_INTERVAL_SECS,
    DefaultStages,
    MARKET_SESSION_COLUMNS,
    OPPORTUNITY_SCORE_COLUMNS,
    POOL_SNAPSHOT_COLUMNS,
    CycleResult,
    FunnelOrchestrator,
    ScannerDaemon,
    ScannerStore,
    ScreenBatch,
    main,
)
from scripts.lp_tg_alerter_v1_readonly import ScannerAlertBridge


AS_OF = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


class FakeStages:
    def __init__(self):
        self.calls = []

    def screen(self):
        self.calls.append("screen")
        records = [
            {
                "chain": "Base",
                "project": "aerodrome-slipstream",
                "symbol": "WETH-USDC",
                "llama_pool_id": "llama-1",
                "resolved_pool": "0x1111111111111111111111111111111111111111",
                "tvlUsd": 2_000_000,
                "volumeUsd1d": 400_000,
                "apyBase": 18.0,
                "apyReward": 2.0,
                "price": 3_200.0,
                "liquidity": 900_000.0,
                "active_liquidity": 500_000.0,
                "range_pct": 8.0,
                "reference_price": 3_198.0,
                "basis_bps": 6.25,
                "market_session": "PRIMARY_CLOSED",
                "instrument_id": "AAPLX-USD",
                "source_timestamp": "2026-08-08T11:59:00+00:00",
                "redemption_status": "OPEN",
            }
        ]
        return ScreenBatch(all_records=records, candidates=records)

    def resolve(self, candidates):
        self.calls.append("resolve")
        return [dict(candidates[0], resolve_status="OK", status="OK")]

    def multiwindow(self, resolved):
        self.calls.append("multiwindow")
        return [
            {
                "pool": resolved[0]["resolved_pool"],
                "fee_cover_stability": {"stable": True, "enter_frac": 1.0},
            }
        ]

    def funnel(self, resolved, stability):
        self.calls.append("funnel_vet")
        return [dict(resolved[0], vetted=True, stable=True, rejection_reason=None)]

    def netcover(self, vetted):
        self.calls.append("netcover")
        return [
            dict(
                vetted[0],
                fee_ev_usd=5.0,
                reward_ev_usd=1.0,
                il_ev_usd=-1.5,
                lvr_ev_usd=-0.25,
                risk_usd=-0.5,
                expected_net_yield_usd=2.75,
                expected_net_yield_pct=0.275,
                netcover_ratio=1.8,
                netcover_pass=True,
            )
        ]


def _table_columns(db: Path, table: str):
    with sqlite3.connect(db) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_default_scanner_cadence_matches_task_package():
    assert DEFAULT_COARSE_INTERVAL_SECS == 15 * 60
    assert DEFAULT_TOP_INTERVAL_SECS == 60


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        ("pool_snapshots", POOL_SNAPSHOT_COLUMNS),
        ("opportunity_scores", OPPORTUNITY_SCORE_COLUMNS),
        ("market_sessions", MARKET_SESSION_COLUMNS),
    ],
)
def test_sqlite_schema_contains_prd_v1_section_30_fields_plus_as_of(tmp_path, table, expected):
    db = tmp_path / "scanner.db"
    ScannerStore(db).initialize_schema()
    assert set(expected) <= _table_columns(db, table)
    assert "as_of" in _table_columns(db, table)


def test_once_executes_every_funnel_stage_and_persists_all_three_tables(tmp_path):
    db = tmp_path / "scanner.db"
    stages = FakeStages()

    rc = main(["--once", "--db", str(db)], stages=stages, now=lambda: AS_OF)

    assert rc == 0
    assert stages.calls == ["screen", "resolve", "multiwindow", "funnel_vet", "netcover"]
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM pool_snapshots").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM opportunity_scores").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM market_sessions").fetchone()[0] == 1
        accepted, reason = conn.execute(
            "SELECT accepted, rejection_reason FROM opportunity_scores"
        ).fetchone()
        assert accepted == 1
        assert reason is None
        session = conn.execute("SELECT market_session FROM market_sessions").fetchone()[0]
        assert session == "PRIMARY_CLOSED"


def test_coarse_screen_is_cached_between_top_candidate_cycles(tmp_path):
    stages = FakeStages()
    orchestrator = FunnelOrchestrator(stages, ScannerStore(tmp_path / "scanner.db"))

    orchestrator.run_once(refresh_coarse=True, as_of=AS_OF)
    orchestrator.run_once(refresh_coarse=False, as_of=AS_OF.replace(minute=1))

    assert stages.calls.count("screen") == 1
    assert stages.calls.count("resolve") == 2


def test_netcover_unavailable_is_fail_closed_and_explained(tmp_path):
    stages = FakeStages()

    def unavailable(records):
        return [dict(records[0], netcover_pass=False, rejection_reason="netcover unavailable")]

    stages.netcover = unavailable
    db = tmp_path / "scanner.db"
    FunnelOrchestrator(stages, ScannerStore(db)).run_once(refresh_coarse=True, as_of=AS_OF)

    with sqlite3.connect(db) as conn:
        accepted, reason = conn.execute(
            "SELECT accepted, rejection_reason FROM opportunity_scores"
        ).fetchone()
    assert accepted == 0
    assert reason == "netcover unavailable"


def test_wp04_adapter_is_the_strict_fifth_gate_not_only_a_diagnostic():
    complete = {
        "pool": "0x1",
        "vetted": True,
        "gates": {"quality": True, "yield_cover": True, "stable": True, "status_ok": True},
        "capital_usd": 100.0,
        "fee_ev_usd": 4.0,
        "reward_ev_usd": 2.0,
        "il_ev_usd": 1.0,
        "entry_cost_usd": 0.1,
        "exit_cost_usd": 0.1,
        "gas_usd": 0.1,
        "slippage_usd": 0.1,
        "reward_conversion_cost_usd": 0.1,
        "exit_latency_loss_usd": 0.1,
    }
    missing = {"pool": "0x2", "vetted": True, "gates": {"quality": True}}

    passed, rejected = DefaultStages().netcover([complete, missing])

    assert passed["netcover_pass"] is True
    assert passed["gates"]["netcover_shadow"] is True
    assert passed["vetted"] is True
    assert rejected["netcover_pass"] is False
    assert rejected["gates"]["netcover_shadow"] is False
    assert rejected["netcover_gate_status"] == "MISSING_FAIL_CLOSED"
    assert rejected["vetted"] is False
    assert rejected["rejection_reason"].startswith("NETCOVER_INPUT_MISSING:")


def test_scanner_marks_prefifth_funnel_as_explicit_intermediate(monkeypatch):
    import scripts.lp_funnel_vet_v1_readonly as funnel

    observed = {}

    def intermediate(bridge, stability, **kwargs):
        observed.update(kwargs)
        return [dict(bridge[0], vetted=True)]

    monkeypatch.setattr(funnel, "funnel_vet", intermediate)
    out = DefaultStages().funnel([{"pool": "0x1"}], [])

    assert out[0]["vetted"] is True
    assert observed["allow_legacy_without_netcover"] is True


def test_default_live_stages_inject_rotating_rpc_pool_into_calls_and_logs(monkeypatch):
    import scripts.lp_multiwindow_stability_v1_readonly as stability
    import scripts.lp_pool_resolve_and_rank_v1_readonly as bridge
    import scripts.lp_rpc_pool_v1_readonly as rpc_module

    calls = []

    class FakeRpcPool:
        def __init__(self, chain):
            assert chain == "base"

        def call(self, method, params, timeout=20):
            calls.append((method, params, timeout))
            return "0x64" if method == "eth_blockNumber" else []

    def raw_fetch(pool, lo, hi, dec0, dec1, rpc_call=None):
        assert rpc_call is not None
        rpc_call("eth_getLogs", [{"address": pool}])
        return []

    live = {"_rpc_with_retry": lambda *_: pytest.fail("legacy RPC used"), "fetch_pool_swaps": raw_fetch}
    monkeypatch.setattr(rpc_module, "RpcPool", FakeRpcPool)
    monkeypatch.setattr(bridge, "_load_live_helpers", lambda: dict(live))
    monkeypatch.setattr(bridge, "_eth_block_number", lambda rpc: int(rpc("eth_blockNumber", []), 16))

    def process(candidate, window_blocks, current_block, caches, injected):
        assert current_block == 100
        injected["fetch_pool_swaps"]("0x1", 1, 2, 18, 6)
        return dict(candidate, status="OK")

    monkeypatch.setattr(bridge, "process_candidate", process)
    monkeypatch.setattr(stability, "_live", lambda: dict(live))
    monkeypatch.setattr(
        stability,
        "assess_pool",
        lambda injected, cfg, *_: (
            injected["fetch_pool_swaps"]("0x1", 1, 2, 18, 6) or {"pool": cfg["pool"]}
        ),
    )
    monkeypatch.setattr(
        bridge,
        "build_policy_config",
        lambda records: [{"pool": "0x1", "dec0": 18, "dec1": 6, "fee_tier": 0.0005}],
    )

    stages = DefaultStages(chain="Base")
    assert stages.resolve([{"pool": "0x1"}])[0]["status"] == "OK"
    assert stages.multiwindow([{"pool": "0x1"}]) == [{"pool": "0x1"}]
    assert [method for method, _, _ in calls] == [
        "eth_blockNumber",
        "eth_getLogs",
        "eth_blockNumber",
        "eth_getLogs",
    ]


def test_default_stages_reuses_one_rpc_pool_and_exports_real_health_snapshot():
    class PersistentPool:
        def __init__(self):
            self.state = "NORMAL"

        def call(self, method, params, timeout=20):
            return "0x64" if method == "eth_blockNumber" else []

        def health_snapshot(self):
            return {"state": self.state, "impaired_endpoints": int(self.state != "NORMAL")}

    pool = PersistentPool()
    stages = DefaultStages(chain="Base", rpc_pool=pool)
    raw = lambda *args, **kwargs: []

    first = stages._live_with_rotating_rpc({"fetch_pool_swaps": raw})
    second = stages._live_with_rotating_rpc({"fetch_pool_swaps": raw})

    assert first["_rpc_with_retry"].__self__ is pool
    assert second["_rpc_with_retry"].__self__ is pool
    assert stages.rpc_health == "NORMAL"
    pool.state = "DEGRADED"
    assert stages.rpc_health == "DEGRADED"


def test_real_pool_degradation_and_recovery_flow_through_daemon_alert_hook():
    from scripts.lp_rpc_pool_v1_readonly import CHAINS, RpcPool

    class Clock:
        def now(self):
            return 1000.0

        def sleep(self, secs):
            pass

    class RecordingAlerter:
        def __init__(self):
            self.events = []

        def send_event(self, event_type, message, **kwargs):
            self.events.append(event_type)

    pool = RpcPool("base", post=lambda *a, **k: {"result": "0x1"}, clock=Clock())
    impaired = CHAINS["base"]["endpoints"][0]["url"]
    stages = DefaultStages(chain="Base", rpc_pool=pool)
    alerter = RecordingAlerter()
    hook = ScannerAlertBridge(alerter, utc_now=lambda: AS_OF)

    def cycle(refresh_coarse):
        return CycleResult(AS_OF.isoformat(), 0, 0, 0, 0, 0, 0, stages.rpc_health)

    daemon = ScannerDaemon(cycle, event_hook=hook)
    pool._penalize(impaired)
    assert daemon.run(once=True) == 0
    pool._reset(impaired)
    assert daemon.run(once=True) == 0

    assert alerter.events == ["rpc_degraded", "rpc_normal"]


def test_all_endpoint_cycle_failure_alerts_exit_only_then_success_recovers_normal():
    from scripts.lp_rpc_pool_v1_readonly import CHAINS, RpcPool

    class Clock:
        def now(self):
            return 1000.0

        def sleep(self, secs):
            pass

    class RecordingAlerter:
        def __init__(self):
            self.events = []

        def send_event(self, event_type, message, **kwargs):
            self.events.append(event_type)

    failing = [True]

    def post(url, method, params, timeout=20):
        if failing[0]:
            raise OSError("public endpoint unavailable")
        return {"result": "0x1"}

    pool = RpcPool("base", post=post, clock=Clock())
    stages = DefaultStages(chain="Base", rpc_pool=pool)
    alerter = RecordingAlerter()
    hook = ScannerAlertBridge(alerter, utc_now=lambda: AS_OF)

    def cycle(refresh_coarse):
        pool.call("eth_blockNumber", [])
        return CycleResult(AS_OF.isoformat(), 0, 0, 0, 0, 0, 0, stages.rpc_health)

    daemon = ScannerDaemon(cycle, event_hook=hook)
    with pytest.raises(RuntimeError, match="failed on all"):
        daemon.run(once=True)

    failing[0] = False
    for endpoint in CHAINS["base"]["endpoints"]:
        pool._reset(endpoint["url"])
    assert daemon.run(once=True) == 0

    assert alerter.events == ["rpc_exit_only", "rpc_normal"]


def test_store_rolls_back_the_whole_cycle_on_invalid_market_session(tmp_path):
    stages = FakeStages()
    original = stages.screen

    def bad_screen():
        batch = original()
        batch.all_records[0]["market_session"] = "MADE_UP"
        return batch

    stages.screen = bad_screen
    db = tmp_path / "scanner.db"

    with pytest.raises(ValueError, match="market_session"):
        FunnelOrchestrator(stages, ScannerStore(db)).run_once(refresh_coarse=True, as_of=AS_OF)

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM pool_snapshots").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM opportunity_scores").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM market_sessions").fetchone()[0] == 0


def test_sigterm_causes_graceful_shutdown_after_cycle(tmp_path):
    started = tmp_path / "started"
    stopped = tmp_path / "stopped"
    code = "\n".join(
        [
            "from pathlib import Path",
            "from scripts.lp_scanner_daemon_v1_readonly import ScannerDaemon",
            f"started = Path({str(started)!r})",
            f"stopped = Path({str(stopped)!r})",
            "def cycle(refresh_coarse):",
            "    started.write_text('started')",
            "daemon = ScannerDaemon(cycle, coarse_interval_secs=900, top_interval_secs=60,",
            "                       on_shutdown=lambda: stopped.write_text('flushed'))",
            "raise SystemExit(daemon.run())",
        ]
    )
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=Path(__file__).parents[1])
    deadline = time.time() + 10
    while time.time() < deadline and not started.exists():
        time.sleep(0.02)
    assert started.exists(), "daemon never completed its initial cycle"

    os.kill(proc.pid, signal.SIGTERM)
    assert proc.wait(timeout=10) == 0
    assert stopped.read_text() == "flushed"


def test_systemd_template_is_shadow_only_credential_free_and_preflighted():
    root = Path(__file__).parents[1]
    text = (root / "deploy/systemd/lpbot-scanner-shadow.service").read_text()
    lowered = text.lower()

    assert "lp_scanner_daemon_v1_readonly.py" in text
    assert "--db" in text
    assert "ExecStartPre=" in text
    assert "/opt/lpbot/lp-bot-v3-origin-check" in text
    assert "EnvironmentFile=" not in text
    assert "token" not in lowered
    assert "wallet" not in lowered
    assert "private_key" not in lowered
    assert "WantedBy=multi-user.target" in text
