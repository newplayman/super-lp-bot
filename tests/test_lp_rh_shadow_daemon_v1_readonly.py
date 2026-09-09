"""Tests for scripts/lp_rh_shadow_daemon_v1_readonly.py (RH-04g Shadow daemon).

All tests use in-memory or tmp_path scratch stores and synthetic samples.
The live source is only ever opened read-only. No network, no wallet, no
broadcast, and nothing is written under reports/.
"""
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import json
import sqlite3
import threading
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.lp_rh_shadow_daemon_v1_readonly import (
    _money_text,
    blocker_rows_from_steps,
    open_live_store,
    open_shadow_store,
    persist_episode,
    pool_meta_hash_of,
    run_daemon,
    run_one_round,
    run_round_safe,
)
from scripts.lp_rh_shadow_runner_v1_readonly import ShadowStep
from scripts.lp_rh_store_v1_readonly import insert_row, migrate, open_store

REPO_ROOT = Path(__file__).resolve().parents[1]
POOL = "0xpool"
POSITION_USD = Decimal("1000")
CAPITAL_USD = Decimal("10000")
HORIZON_HOURS = 8760
NOW = "2026-01-01T00:00:00Z"


def _cfg(live_db, pool=POOL):
    return {"live_db": live_db, "pool": pool, "samples": 20,
            "position_usd": POSITION_USD, "capital_usd": CAPITAL_USD,
            "horizon_hours": HORIZON_HOURS, "target_mode": "SHADOW_SCENARIO",
            "pool_meta": None, "pool_meta_hash": "h"}


def _insert_minimal_sample(conn, pool, sample_time, *, session="ASIA", mid="1.0"):
    insert_row(conn, "rh_market_states", {
        "asset_address": pool, "sample_time": sample_time, "chain_id": 4663,
        "reference_mid": mid, "multiplier_human": None, "session": session,
        "health_flags_json": "{}", "reference_age_secs": 10, "oracle_paused": 0,
        "source_payload_hash": None, "reference_bid": None, "reference_ask": None,
    })


def _step(reasons=()):
    return ShadowStep(0, NOW, None, False, "UNSUPPORTED", None, None, None,
                      None, False, False, reasons)


def _persist(conn, episode_id="ep", summary=None, **kw):
    base = {"total_steps": 1, "eligible_steps": 0, "first_eligible_at": None,
            "nav_start": None, "nav_end": None, "net_pnl": None,
            "hodl_delta": None, "skipped_at_load": 0, "steps_without_nav": 1,
            "status_counts": {"UNSUPPORTED": 1}, "conjunct_failure_counts": {}}
    if summary:
        base.update(summary)
    persist_episode(conn, episode_id=episode_id, started_at="t0", ended_at="t1",
                    pool="p", target_mode="m", position_usd=Decimal("1"),
                    capital_usd=Decimal("2"), horizon_hours=1,
                    pool_meta_hash="h", summary=base, **kw)


def test_one_round_writes_one_episode_row(tmp_path):
    live = open_store(tmp_path / "live.db"); migrate(live)
    _insert_minimal_sample(live, POOL, NOW); live.commit()
    shadow = open_shadow_store(":memory:")
    summary = run_one_round(_cfg(str(tmp_path / "live.db")), shadow_conn=shadow,
                            episode_id="ep1", started_at=NOW, now_fn=lambda: NOW)
    assert shadow.execute(
        "select count(*) from rh_shadow_episodes").fetchone()[0] == 1
    assert summary["total_steps"] == 1


def test_same_episode_id_dedup():
    conn = open_shadow_store(":memory:")
    _persist(conn, episode_id="ep")
    _persist(conn, episode_id="ep")
    assert conn.execute(
        "select count(*) from rh_shadow_episodes").fetchone()[0] == 1


def test_conjunct_failure_counts_json_loads():
    conn = open_shadow_store(":memory:")
    _persist(conn, summary={"conjunct_failure_counts": {"A": 3, "B": 1}})
    text = conn.execute(
        "select conjunct_failure_counts_json from rh_shadow_episodes").fetchone()[0]
    assert json.loads(text) == {"A": 3, "B": 1}


def test_blocker_rows_group_by_session():
    steps = [_step(("oracle: missing",)), _step(("oracle: missing",))]
    samples = [{"session": "ASIA"}, {"session": "EUROPE"}]
    rows = blocker_rows_from_steps(steps, samples)
    assert {r[1] for r in rows} == {"ASIA", "EUROPE"}
    counts = {(r[0], r[1]): r[2] for r in rows}
    assert counts[("oracle", "ASIA")] == 1
    assert counts[("oracle", "EUROPE")] == 1


def test_blocker_rows_unknown_session():
    rows = blocker_rows_from_steps([_step(("oracle: missing",))], [{}])
    assert rows == [("oracle", "UNKNOWN", 1)]


def test_eligible_zero_first_eligible_none():
    conn = open_shadow_store(":memory:")
    _persist(conn, summary={"eligible_steps": 0, "first_eligible_at": None})
    val = conn.execute(
        "select first_eligible_at from rh_shadow_episodes").fetchone()[0]
    assert val is None


def test_first_eligible_equals_sample_time():
    conn = open_shadow_store(":memory:")
    _persist(conn, summary={"eligible_steps": 2,
                            "first_eligible_at": "2026-01-01T00:03:00Z"})
    val = conn.execute(
        "select first_eligible_at from rh_shadow_episodes").fetchone()[0]
    assert val == "2026-01-01T00:03:00Z"


def test_run_round_safe_records_error_no_raise(tmp_path):
    shadow = open_shadow_store(":memory:")
    cfg = _cfg(str(tmp_path / "nonexistent.db"))
    rc = run_round_safe(cfg, shadow_conn=shadow, episode_id="ep",
                        now_fn=lambda: NOW)
    assert rc == 0
    err, ended = shadow.execute(
        "select error, ended_at from rh_shadow_episodes").fetchone()
    assert err is not None and err != ""
    assert ended is None


def test_pool_meta_hash_stable_and_different():
    a = pool_meta_hash_of('{"x": 1}')
    assert a == pool_meta_hash_of('{"x": 1}')
    assert a != pool_meta_hash_of('{"x": 2}')
    assert isinstance(a, str) and len(a) == 64


def test_pool_meta_hash_none_raises():
    # Source behavior: pool_meta_hash_of(None) calls None.encode -> AttributeError.
    # Recorded as-is; the source is not changed to return None for None.
    with pytest.raises(AttributeError):
        pool_meta_hash_of(None)


def test_money_text_roundtrip_decimal():
    v = Decimal("12345.678901234")
    text = _money_text(v)
    assert text == "12345.678901234"
    assert Decimal(text) == v
    assert _money_text(Decimal("0.1")) == "0.1"
    assert _money_text(None) is None
    assert _money_text(5) == "5"


def test_no_nav_nav_start_net_pnl_null():
    conn = open_shadow_store(":memory:")
    _persist(conn)  # base summary carries nav_start / net_pnl as None
    nav_start, net_pnl = conn.execute(
        "select nav_start, net_pnl from rh_shadow_episodes").fetchone()
    assert nav_start is None
    assert net_pnl is None


def test_run_daemon_two_rounds_one_sleep(tmp_path):
    live = open_store(tmp_path / "live.db"); migrate(live); live.commit()
    shadow = open_shadow_store(":memory:")
    t0, t1 = "2026-01-01T00:00:00Z", "2026-01-01T00:00:11Z"
    calls = {"n": 0}

    def now_fn():
        calls["n"] += 1
        return t0 if calls["n"] <= 3 else t1

    sleeps = []
    stop = threading.Event()

    def sleep_fn(secs):
        sleeps.append(secs)
        stop.set()

    rc = run_daemon(_cfg(str(tmp_path / "live.db")), shadow_conn=shadow,
                    period_secs=10, now_fn=now_fn, sleep_fn=sleep_fn,
                    stop_event=stop)
    assert rc == 0
    assert shadow.execute(
        "select count(*) from rh_shadow_episodes").fetchone()[0] == 2
    assert len(sleeps) == 1


def test_run_daemon_deadline_from_round_start(tmp_path):
    live = open_store(tmp_path / "live.db"); migrate(live); live.commit()
    shadow = open_shadow_store(":memory:")
    t0 = "2026-01-01T00:00:00Z"
    t_end = "2026-01-01T00:00:09.500000Z"  # t0 + 9.5s
    calls = {"n": 0}

    def now_fn():
        calls["n"] += 1
        return t0 if calls["n"] <= 2 else t_end

    sleeps = []
    stop = threading.Event()

    def sleep_fn(secs):
        sleeps.append(secs)
        stop.set()

    rc = run_daemon(_cfg(str(tmp_path / "live.db")), shadow_conn=shadow,
                    period_secs=10, now_fn=now_fn, sleep_fn=sleep_fn,
                    stop_event=stop)
    assert rc == 0
    assert len(sleeps) == 1
    # deadline counted from this round's start: sleep = 10 - 9.5 = 0.5, not 10
    assert sleeps[0] == pytest.approx(0.5)
    assert sleeps[0] != 10


def test_open_live_store_readonly(tmp_path):
    live_path = tmp_path / "live.db"
    live = open_store(live_path); migrate(live); live.commit(); live.close()
    ro = open_live_store(str(live_path))
    assert any("rh_market_states" in t for t, in ro.execute(
        "select name from sqlite_master where type='table'"))
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("insert into rh_market_states (asset_address, sample_time,"
                   " chain_id, session, health_flags_json)"
                   " values ('x','y',1,'z','{}')")


def test_main_once_returns_zero_no_reports_db(tmp_path, monkeypatch):
    import scripts.lp_rh_shadow_daemon_v1_readonly as mod
    live = open_store(tmp_path / "live.db"); migrate(live)
    _insert_minimal_sample(live, POOL, NOW); live.commit(); live.close()
    meta = tmp_path / "meta.json"; meta.write_text('{"dec0": 18, "dec1": 6}')
    db_path = tmp_path / "s.db"
    monkeypatch.setattr(mod, "LIVE_DB", str(tmp_path / "live.db"))
    rc = mod.main(["--once", "--db", str(db_path), "--pool", POOL,
                   "--pool-meta-json", str(meta), "--position-usd", "1000",
                   "--capital-usd", "10000", "--horizon-hours", "8760"])
    assert rc == 0
    assert db_path.exists()
    assert not (REPO_ROOT / "reports" / "lp_rh" / "shadow.db").exists()
    err = sqlite3.connect(db_path).execute(
        "select error from rh_shadow_episodes").fetchone()[0]
    assert err is None
