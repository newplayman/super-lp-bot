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


def _live_store_fingerprint():
    """(exists, mtime_ns) of the production shadow store, or (False, None)."""
    p = REPO_ROOT / "reports" / "lp_rh" / "shadow.db"
    return (p.exists(), p.stat().st_mtime_ns if p.exists() else None)


def test_main_once_returns_zero_no_reports_db(tmp_path, monkeypatch):
    import scripts.lp_rh_shadow_daemon_v1_readonly as mod
    live = open_store(tmp_path / "live.db"); migrate(live)
    _insert_minimal_sample(live, POOL, NOW); live.commit(); live.close()
    meta = tmp_path / "meta.json"; meta.write_text('{"dec0": 18, "dec1": 6}')
    db_path = tmp_path / "s.db"
    monkeypatch.setattr(mod, "LIVE_DB", str(tmp_path / "live.db"))
    live_before = _live_store_fingerprint()
    rc = mod.main(["--once", "--db", str(db_path), "--pool", POOL,
                   "--pool-meta-json", str(meta), "--position-usd", "1000",
                   "--capital-usd", "10000", "--horizon-hours", "8760"])
    assert rc == 0
    assert db_path.exists()
    # Was `assert not (...shadow.db).exists()`, which asserted the absence of
    # production state and went red the moment the real daemon was started.  What
    # this guards is that a --once run touches only the path it was given, so
    # compare the live store before and after instead.
    assert live_before == _live_store_fingerprint(), (
        "the --once run created or wrote the live shadow store")
    err = sqlite3.connect(db_path).execute(
        "select error from rh_shadow_episodes").fetchone()[0]
    assert err is None


def test_session_is_derived_from_timestamp_not_the_column():
    """The collector hardcodes session='UNKNOWN', so trusting the column is useless.

    lp_rh_collector_v1_readonly line 228 writes the literal "UNKNOWN" for every
    row, which made every blocker land in one bucket and defeated the point of
    grouping by session.  Deriving it from sample_time is exact and works on rows
    already collected.
    """
    from scripts.lp_rh_shadow_daemon_v1_readonly import _session_of
    # 18:00 UTC is 14:00 ET, inside regular trading hours.
    assert _session_of({"sample_time": "2026-09-08T18:00:00Z",
                        "session": "UNKNOWN"}) == "RTH"
    # 20:30 UTC is 16:30 ET, after the bell.
    assert _session_of({"sample_time": "2026-09-08T20:30:00Z",
                        "session": "UNKNOWN"}) == "POSTMARKET"


def test_session_falls_back_to_the_column_when_the_stamp_is_unusable():
    from scripts.lp_rh_shadow_daemon_v1_readonly import _session_of
    assert _session_of({"sample_time": "not-a-time", "session": "RTH"}) == "RTH"
    assert _session_of({"sample_time": None, "session": None}) == "UNKNOWN"


# ---------------------------------------------------------------------------
# --ledger-db: persist every step's gate/mark/reservation rows to a store.
#
# decision_id does not include the episode, so re-running an overlapping sample
# window collides on the rh_gate_decisions PK.  The daemon must catch that class
# of collision, count it (ledger_duplicate_rows), and not let the round crash --
# and it must NOT mask it with INSERT OR IGNORE.  Without the arg the behavior
# is byte-for-byte unchanged (throwaway scratch, destroyed).
# ---------------------------------------------------------------------------

def _cfg_with_ledger(live_db, ledger_db, pool=POOL):
    cfg = _cfg(live_db, pool=pool)
    cfg["ledger_db"] = ledger_db
    return cfg


def _ledger_counts(path):
    conn = sqlite3.connect(path)
    try:
        gate = conn.execute(
            "select count(*) from rh_gate_decisions").fetchone()[0]
        marks = conn.execute(
            "select count(*) from rh_position_marks").fetchone()[0]
        return gate, marks
    finally:
        conn.close()


def test_no_ledger_db_behavior_unchanged(tmp_path):
    live = open_store(tmp_path / "live.db"); migrate(live)
    _insert_minimal_sample(live, POOL, NOW); live.commit(); live.close()
    shadow = open_shadow_store(":memory:")
    summary = run_one_round(_cfg(str(tmp_path / "live.db")), shadow_conn=shadow,
                            episode_id="ep1", started_at=NOW, now_fn=lambda: NOW)
    # Persistence not enabled -> the field is None, not 0.
    assert summary["ledger_duplicate_rows"] is None
    # No ledger file was created; the scratch store is destroyed.
    assert not (tmp_path / "ledger.db").exists()


def test_ledger_db_persists_gate_and_marks(tmp_path):
    live = open_store(tmp_path / "live.db"); migrate(live)
    _insert_minimal_sample(live, POOL, NOW); live.commit(); live.close()
    ledger = tmp_path / "ledger.db"
    shadow = open_shadow_store(":memory:")
    summary = run_one_round(
        _cfg_with_ledger(str(tmp_path / "live.db"), str(ledger)),
        shadow_conn=shadow, episode_id="ep1", started_at=NOW,
        now_fn=lambda: NOW)
    assert ledger.exists()
    gate, marks = _ledger_counts(str(ledger))
    assert gate > 0
    assert marks > 0
    # Fresh ledger -> no duplicates.
    assert summary["ledger_duplicate_rows"] == 0


def test_ledger_db_duplicate_counted_not_masked(tmp_path):
    live = open_store(tmp_path / "live.db"); migrate(live)
    for i in range(3):
        _insert_minimal_sample(live, POOL, f"2026-01-01T00:0{i}:00Z")
    live.commit(); live.close()
    ledger = tmp_path / "ledger.db"
    shadow = open_shadow_store(":memory:")
    cfg = _cfg_with_ledger(str(tmp_path / "live.db"), str(ledger))
    # Round 1: fresh ledger, no duplicates.
    s1 = run_one_round(cfg, shadow_conn=shadow, episode_id="ep1",
                       started_at=NOW, now_fn=lambda: NOW)
    gate1, _ = _ledger_counts(str(ledger))
    assert s1["ledger_duplicate_rows"] == 0
    assert gate1 > 0
    # Round 2: same samples, every decision_id collides on the PK.
    s2 = run_one_round(cfg, shadow_conn=shadow, episode_id="ep2",
                       started_at=NOW, now_fn=lambda: NOW)
    gate2, _ = _ledger_counts(str(ledger))
    # The collision is counted, not masked: all three are reported.
    assert s2["ledger_duplicate_rows"] == 3
    # Round 1's rows were neither deleted nor overwritten.
    assert gate2 >= gate1


def test_unwritable_ledger_db_fails_not_silent(tmp_path):
    live = open_store(tmp_path / "live.db"); migrate(live)
    _insert_minimal_sample(live, POOL, NOW); live.commit(); live.close()
    # Make the ledger path unwritable: its parent is a regular file, so
    # open_store's mkdir raises.  The round must fail clearly, not fall back.
    blocker = tmp_path / "blocker"; blocker.write_text("x")
    cfg = _cfg(str(tmp_path / "live.db"))
    cfg["ledger_db"] = str(blocker / "x.db")
    shadow = open_shadow_store(":memory:")
    rc = run_round_safe(cfg, shadow_conn=shadow, episode_id="ep",
                        now_fn=lambda: NOW)
    assert rc == 0
    err = shadow.execute(
        "select error from rh_shadow_episodes").fetchone()[0]
    # The round clearly failed and the reason was recorded.
    assert err is not None and err != ""
    # No silent fallback to scratch: the ledger file was never created.
    assert not (blocker / "x.db").exists()


def test_both_branches_pass_identical_run_episode_args(tmp_path, monkeypatch):
    import scripts.lp_rh_shadow_daemon_v1_readonly as mod
    live = open_store(tmp_path / "live.db"); migrate(live)
    _insert_minimal_sample(live, POOL, NOW); live.commit(); live.close()
    calls = []
    orig = mod.run_episode

    def capture(conn, **kwargs):
        calls.append(dict(kwargs))
        return orig(conn, **kwargs)

    monkeypatch.setattr(mod, "run_episode", capture)
    shadow = open_shadow_store(":memory:")
    now_fn = lambda: NOW
    # scratch branch (no ledger_db)
    run_one_round(_cfg(str(tmp_path / "live.db")), shadow_conn=shadow,
                  episode_id="ep1", started_at=NOW, now_fn=now_fn)
    # ledger branch
    cfg = _cfg(str(tmp_path / "live.db"))
    cfg["ledger_db"] = str(tmp_path / "ledger.db")
    run_one_round(cfg, shadow_conn=shadow, episode_id="ep1",
                  started_at=NOW, now_fn=now_fn)
    assert len(calls) == 2
    # Only the connection differs; the kwargs are identical.
    assert calls[0] == calls[1]


# ---------------------------------------------------------------------------
# RH-02ca: ledger rollback path copy_new_rows gap tests
# ---------------------------------------------------------------------------

def test_meta_runner_tables_match_ledger_tables():
    """RH-02ca section 4 meta-test: runner written tables == _LEDGER_TABLES."""
    import re
    from scripts.lp_rh_shadow_daemon_v1_readonly import _LEDGER_TABLES
    src = (REPO_ROOT / "scripts" / "lp_rh_shadow_runner_v1_readonly.py").read_text()
    written = set(re.findall(r'insert_row\(\s*conn\s*,\s*"(rh_\w+)"', src))
    written.add("rh_journal")
    if "try_reserve" in src:
        written.add("rh_bucket_reservations")
    assert written == set(_LEDGER_TABLES)


def test_economic_evaluations_grow_across_rounds_and_no_duplicate_pk(tmp_path):
    """RH-02ca section 2: economic evaluations grow in round 2 with no duplicate PK."""
    live = open_store(tmp_path / "live.db"); migrate(live)
    for i in range(2):
        insert_row(live, "rh_market_states", {
            "asset_address": POOL, "sample_time": f"2026-01-01T00:0{i}:00Z", "chain_id": 4663,
            "reference_mid": "1.0", "multiplier_human": None, "session": "ASIA",
            "health_flags_json": "{}", "reference_age_secs": 10, "oracle_paused": 0,
            "source_payload_hash": f"hash-{i}", "reference_bid": None, "reference_ask": None,
        })
    live.commit(); live.close()
    ledger = tmp_path / "ledger.db"
    shadow = open_shadow_store(":memory:")
    cfg = _cfg_with_ledger(str(tmp_path / "live.db"), str(ledger))
    s1 = run_one_round(cfg, shadow_conn=shadow, episode_id="ep1",
                       started_at=NOW, now_fn=lambda: NOW)
    c1 = open_store(ledger)
    econ1 = c1.execute("SELECT count(*) FROM rh_economic_evaluations").fetchone()[0]
    c1.close()
    assert econ1 == 2
    # Add new sample for round 2 (reads samples 0, 1, 2)
    live = open_store(tmp_path / "live.db")
    insert_row(live, "rh_market_states", {
        "asset_address": POOL, "sample_time": "2026-01-01T00:02:00Z", "chain_id": 4663,
        "reference_mid": "1.0", "multiplier_human": None, "session": "ASIA",
        "health_flags_json": "{}", "reference_age_secs": 10, "oracle_paused": 0,
        "source_payload_hash": "hash-2", "reference_bid": None, "reference_ask": None,
    })
    live.commit(); live.close()
    s2 = run_one_round(cfg, shadow_conn=shadow, episode_id="ep2",
                       started_at=NOW, now_fn=lambda: NOW)
    c2 = open_store(ledger)
    econ2 = c2.execute("SELECT count(*) FROM rh_economic_evaluations").fetchone()[0]
    pk_dist = c2.execute(
        "SELECT count(DISTINCT candidate_key || '|' || snapshot_id || '|' || "
        "model_version || '|' || policy_version || '|' || horizon_hours || '|' || position_usd) "
        "FROM rh_economic_evaluations").fetchone()[0]
    c2.close()
    assert econ2 > econ1
    assert econ2 == 3
    assert pk_dist == econ2


def test_position_marks_dedup_no_duplicate_mark_time(tmp_path):
    """RH-02ca section 3: position marks deduplicated, count == count(distinct PK)."""
    live = open_store(tmp_path / "live.db"); migrate(live)
    for i in range(3):
        _insert_minimal_sample(live, POOL, f"2026-01-01T00:0{i}:00Z")
    live.commit(); live.close()
    ledger = tmp_path / "ledger.db"
    shadow = open_shadow_store(":memory:")
    cfg = _cfg_with_ledger(str(tmp_path / "live.db"), str(ledger))
    run_one_round(cfg, shadow_conn=shadow, episode_id="ep1",
                  started_at=NOW, now_fn=lambda: NOW)
    run_one_round(cfg, shadow_conn=shadow, episode_id="ep2",
                  started_at=NOW, now_fn=lambda: NOW)
    conn = open_store(ledger)
    total = conn.execute("SELECT count(*) FROM rh_position_marks").fetchone()[0]
    distinct = conn.execute(
        "SELECT count(DISTINCT position_id || '|' || mark_time) FROM rh_position_marks").fetchone()[0]
    conn.close()
    assert total == distinct


def test_gate_decisions_dedup_maintained(tmp_path):
    """RH-02ca section 4: gate decisions deduplication is maintained without regression."""
    live = open_store(tmp_path / "live.db"); migrate(live)
    for i in range(3):
        _insert_minimal_sample(live, POOL, f"2026-01-01T00:0{i}:00Z")
    live.commit(); live.close()
    ledger = tmp_path / "ledger.db"
    shadow = open_shadow_store(":memory:")
    cfg = _cfg_with_ledger(str(tmp_path / "live.db"), str(ledger))
    run_one_round(cfg, shadow_conn=shadow, episode_id="ep1",
                  started_at=NOW, now_fn=lambda: NOW)
    run_one_round(cfg, shadow_conn=shadow, episode_id="ep2",
                  started_at=NOW, now_fn=lambda: NOW)
    conn = open_store(ledger)
    total = conn.execute("SELECT count(*) FROM rh_gate_decisions").fetchone()[0]
    distinct = conn.execute("SELECT count(DISTINCT decision_id) FROM rh_gate_decisions").fetchone()[0]
    conn.close()
    assert total == distinct
    assert total == 3


def test_copy_new_rows_stats_match_scratch_row_counts(tmp_path):
    """RH-02ca section 5: copy_new_rows stats copied + skipped_existing == scratch count."""
    from scripts.lp_rh_shadow_daemon_v1_readonly import _copy_new_rows, _LEDGER_TABLES
    scratch = open_store(tmp_path / "scratch.db"); migrate(scratch)
    ledger = open_store(tmp_path / "ledger.db"); migrate(ledger)
    insert_row(ledger, "rh_gate_decisions", {
        "decision_id": "dec-0", "candidate_key": "cand-0", "target_mode": "SHADOW_SCENARIO",
        "primary_status": "COMPUTED_PASS", "terminal_bits_json": "{}", "dominant_blocker": None,
        "reasons_json": "[]", "snapshot_ids_json": "[]", "decided_at": NOW,
    })
    insert_row(ledger, "rh_position_marks", {
        "position_id": "pos-0", "mark_time": NOW, "price_snapshot_id": "s0",
        "reference_nav": "1000", "liquidation_nav": "1000", "accrued_fee": "0",
        "unvalued_risk_json": "{}",
    })
    ledger.commit()
    insert_row(scratch, "rh_gate_decisions", {
        "decision_id": "dec-0", "candidate_key": "cand-0", "target_mode": "SHADOW_SCENARIO",
        "primary_status": "COMPUTED_PASS", "terminal_bits_json": "{}", "dominant_blocker": None,
        "reasons_json": "[]", "snapshot_ids_json": "[]", "decided_at": NOW,
    })
    insert_row(scratch, "rh_gate_decisions", {
        "decision_id": "dec-1", "candidate_key": "cand-1", "target_mode": "SHADOW_SCENARIO",
        "primary_status": "COMPUTED_PASS", "terminal_bits_json": "{}", "dominant_blocker": None,
        "reasons_json": "[]", "snapshot_ids_json": "[]", "decided_at": NOW,
    })
    insert_row(scratch, "rh_position_marks", {
        "position_id": "pos-0", "mark_time": NOW, "price_snapshot_id": "s0",
        "reference_nav": "1000", "liquidation_nav": "1000", "accrued_fee": "0",
        "unvalued_risk_json": "{}",
    })
    insert_row(scratch, "rh_position_marks", {
        "position_id": "pos-1", "mark_time": NOW, "price_snapshot_id": "s1",
        "reference_nav": "1000", "liquidation_nav": "1000", "accrued_fee": "0",
        "unvalued_risk_json": "{}",
    })
    insert_row(scratch, "rh_economic_evaluations", {
        "candidate_key": "cand-0", "snapshot_id": "snap-0", "model_version": "m1",
        "policy_version": "p1", "horizon_hours": 24, "position_usd": "1000",
        "evaluated_at": NOW,
    })
    scratch.commit()
    stats = _copy_new_rows(scratch, ledger)
    ledger.commit()
    assert set(stats.keys()) == set(_LEDGER_TABLES)
    for tbl in _LEDGER_TABLES:
        cnt = scratch.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        assert stats[tbl]["copied"] + stats[tbl]["skipped_existing"] == cnt
    assert stats["rh_gate_decisions"] == {"copied": 1, "skipped_existing": 1}
    assert stats["rh_position_marks"] == {"copied": 1, "skipped_existing": 1}
    assert stats["rh_economic_evaluations"] == {"copied": 1, "skipped_existing": 0}
    scratch.close(); ledger.close()


def test_shadow_positions_and_journal_survive_the_rollback_path(tmp_path):
    """RH-02ca section 6: the two tables added last must be carried by _copy_new_rows.

    Driving this through run_one_round would need a granted step, which needs the
    terminal gate to pass, which needs a New York RTH timestamp -- the module's
    NOW is 00:00Z (19:00 ET the previous day), so nothing is ever granted and the
    assertion passes vacuously on a broken copier. The earlier version of this
    test did exactly that and found 0 rows.

    So it exercises the copier directly, which is where the defect was: writers
    for rh_shadow_positions (f1ab502) and rh_journal (4af0aba) landed after
    _copy_new_rows (330ab3e) and were never added to it, so on every round that
    hit the primary-key rollback path their rows were silently dropped.
    """
    from scripts.lp_rh_shadow_daemon_v1_readonly import _copy_new_rows

    scratch = open_store(tmp_path / "scratch.db"); migrate(scratch)
    ledger = open_store(tmp_path / "ledger.db"); migrate(ledger)

    insert_row(scratch, "rh_shadow_positions", {
        "strategy_episode": "ep1", "position_id": "rh-shadow-ep1",
        "pool_key": "0xpool", "profile": "CORE", "bucket": "CORE",
        "initial_token0_raw": "123", "initial_token1_raw": "456",
        "virtual_liquidity_raw": "789", "opened_at": "2026-09-10T00:00:00Z",
    })
    for leg in ("token0", "token1"):
        insert_row(scratch, "rh_journal", {
            "event_id": f"ep1-open-{leg}", "idempotency_key": f"ep1-open-{leg}",
            "account_debit": f"LP_POSITION_{leg.upper()}",
            "account_credit": f"WALLET_{leg.upper()}",
            "asset": "0xtoken", "amount_raw": "1000",
            "is_external_flow": 0, "booked_at": "2026-09-10T00:00:00Z",
        })
    scratch.commit()

    stats = _copy_new_rows(scratch, ledger, set())
    ledger.commit()
    assert ledger.execute("SELECT COUNT(*) FROM rh_shadow_positions").fetchone()[0] == 1
    assert ledger.execute("SELECT COUNT(*) FROM rh_journal").fetchone()[0] == 2
    assert stats["rh_shadow_positions"]["copied"] == 1
    assert stats["rh_journal"]["copied"] == 2

    # Second round over the same scratch: nothing new, nothing duplicated.
    stats2 = _copy_new_rows(scratch, ledger, set())
    ledger.commit()
    assert ledger.execute("SELECT COUNT(*) FROM rh_shadow_positions").fetchone()[0] == 1
    assert ledger.execute("SELECT COUNT(*) FROM rh_journal").fetchone()[0] == 2
    assert stats2["rh_shadow_positions"] == {"copied": 0, "skipped_existing": 1}
    assert stats2["rh_journal"] == {"copied": 0, "skipped_existing": 2}
    scratch.close(); ledger.close()
