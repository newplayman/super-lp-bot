"""Tests for scripts/lp_rh_shadow_watchdog_v1_readonly.py (RH-04g watchdog).

All tests use tmp_path scratch stores seeded through the daemon's own
persist_episode, so the watchdog is exercised against exactly the schema the
daemon writes.  The watchdog opens the store read-only and never writes.
No network.
"""
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from scripts.lp_rh_shadow_daemon_v1_readonly import (
    open_shadow_store,
    persist_episode,
)
from scripts.lp_rh_shadow_watchdog_v1_readonly import (
    main,
    open_shadow_db_readonly,
    watchdog,
)

NOW = "2026-01-01T00:00:00Z"


def _seed(db_path, started_at, episode_id="ep1", blocker_rows=()):
    conn = open_shadow_store(db_path)
    persist_episode(
        conn, episode_id=episode_id, started_at=started_at, ended_at=None,
        pool="0xpool", target_mode="SHADOW_SCENARIO",
        position_usd=Decimal("1000"), capital_usd=Decimal("10000"),
        horizon_hours=8760, pool_meta_hash="h",
        summary={"total_steps": 1, "eligible_steps": 0,
                 "status_counts": {"UNSUPPORTED": 1}},
        blocker_rows=blocker_rows)
    conn.commit()
    conn.close()


def test_watchdog_missing_db_is_no_data(tmp_path):
    assert main(["--db", str(tmp_path / "nope.db"), "--now", NOW]) == 1


def test_watchdog_empty_store_is_no_data(tmp_path, capsys):
    db = tmp_path / "s.db"
    conn = open_shadow_store(db); conn.close()
    assert main(["--db", str(db), "--now", NOW]) == 1
    assert "NO_DATA" in capsys.readouterr().out


def test_watchdog_fresh_episode_ok(tmp_path, capsys):
    db = tmp_path / "s.db"
    _seed(db, "2026-01-01T00:00:00Z")
    # age 60s < threshold 900*3 = 2700s
    assert main(["--db", str(db), "--now", "2026-01-01T00:01:00Z"]) == 0
    assert "OK" in capsys.readouterr().out


def test_watchdog_stale_episode(tmp_path, capsys):
    db = tmp_path / "s.db"
    _seed(db, "2026-01-01T00:00:00Z")
    # age 7200s > threshold 2700s
    assert main(["--db", str(db), "--now", "2026-01-01T02:00:00Z"]) == 2
    assert "STALE" in capsys.readouterr().out


def test_watchdog_age_equal_to_threshold_is_ok(tmp_path):
    db = tmp_path / "s.db"
    _seed(db, "2026-01-01T00:00:00Z")
    # age exactly 2700s == threshold: stale is strictly greater
    assert main(["--db", str(db), "--now", "2026-01-01T00:45:00Z"]) == 0


def test_watchdog_custom_period_and_multiplier(tmp_path):
    db = tmp_path / "s.db"
    _seed(db, "2026-01-01T00:00:00Z")
    # threshold = 100 * 2 = 200s; age 300s -> stale
    assert main(["--db", str(db), "--now", "2026-01-01T00:05:00Z",
                 "--period-secs", "100", "--stale-multiplier", "2"]) == 2


def test_watchdog_prints_latest_episode_and_blockers(tmp_path, capsys):
    db = tmp_path / "s.db"
    _seed(db, "2026-01-01T00:00:00Z", episode_id="ep-old",
          blocker_rows=[("oracle", "ASIA", 5)])
    _seed(db, "2026-01-01T00:05:00Z", episode_id="ep-new",
          blocker_rows=[("oracle", "EUROPE", 20), ("pool_meta", "EUROPE", 20)])
    assert main(["--db", str(db), "--now", "2026-01-01T00:06:00Z"]) == 0
    out = capsys.readouterr().out
    assert "latest_episode: ep-new" in out
    assert "session=EUROPE" in out
    assert "count=20" in out
    assert "ep-old" not in out


def test_watchdog_blockers_fall_back_to_older_episode(tmp_path, capsys):
    db = tmp_path / "s.db"
    _seed(db, "2026-01-01T00:00:00Z", episode_id="ep-old",
          blocker_rows=[("oracle", "ASIA", 7)])
    _seed(db, "2026-01-01T00:05:00Z", episode_id="ep-new")  # no blockers
    assert main(["--db", str(db), "--now", "2026-01-01T00:06:00Z"]) == 0
    out = capsys.readouterr().out
    assert "latest_episode: ep-new" in out
    assert "episode=ep-old" in out
    assert "count=7" in out


def test_watchdog_no_blockers_at_all(tmp_path, capsys):
    db = tmp_path / "s.db"
    _seed(db, "2026-01-01T00:00:00Z")
    assert main(["--db", str(db), "--now", "2026-01-01T00:01:00Z"]) == 0
    assert "latest_blockers: (none)" in capsys.readouterr().out


def test_watchdog_json_mode(tmp_path, capsys):
    db = tmp_path / "s.db"
    _seed(db, "2026-01-01T00:00:00Z", blocker_rows=[("oracle", "ASIA", 3)])
    assert main(["--db", str(db), "--now", "2026-01-01T00:01:00Z",
                 "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "OK"
    assert payload["latest_episode"]["episode_id"] == "ep1"
    assert payload["latest_blockers"][0]["conjunct"] == "oracle"
    assert payload["blocker_episode_id"] == "ep1"
    assert payload["age_secs"] == pytest.approx(60.0)
    assert payload["stale_threshold_secs"] == pytest.approx(2700.0)


def test_watchdog_json_no_data(tmp_path, capsys):
    assert main(["--db", str(tmp_path / "nope.db"), "--now", NOW,
                 "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "NO_DATA"
    assert payload["latest_episode"] is None


def test_watchdog_returns_status_and_payload(tmp_path):
    db = tmp_path / "s.db"
    _seed(db, "2026-01-01T00:00:00Z")
    now = datetime(2026, 1, 1, 0, 1, 0, tzinfo=timezone.utc)
    status, payload = watchdog(str(db), period_secs=900.0,
                               stale_multiplier=3.0, now=now)
    assert status == "OK"
    assert payload["latest_episode"]["episode_id"] == "ep1"
    assert payload["age_secs"] == pytest.approx(60.0)


def test_watchdog_unparseable_started_at_fails_closed(tmp_path):
    db = tmp_path / "s.db"
    conn = open_shadow_store(db)
    conn.execute(
        "insert into rh_shadow_episodes (episode_id, started_at, pool,"
        " target_mode) values ('ep', 'not-a-timestamp', 'p', 'm')")
    conn.commit(); conn.close()
    assert main(["--db", str(db), "--now", NOW]) == 2


def test_watchdog_db_open_readonly(tmp_path):
    db = tmp_path / "s.db"
    conn = open_shadow_store(db); conn.close()
    ro = open_shadow_db_readonly(str(db))
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("create table t (x int)")
    with pytest.raises(FileNotFoundError):
        open_shadow_db_readonly(str(tmp_path / "absent.db"))
