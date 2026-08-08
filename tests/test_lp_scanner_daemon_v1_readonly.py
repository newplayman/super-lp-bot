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
    MARKET_SESSION_COLUMNS,
    OPPORTUNITY_SCORE_COLUMNS,
    POOL_SNAPSHOT_COLUMNS,
    FunnelOrchestrator,
    ScannerStore,
    ScreenBatch,
    main,
)


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
