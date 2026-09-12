"""Test Suite F: Crash Recovery, Idempotent Duplicate Replay, and Reservation Cleanup.

Exercises resilience against mid-episode failures, duplicate episode replays,
and orphaned bucket reservation cleanup.
"""

from decimal import Decimal
from pathlib import Path
import sqlite3
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_reservation_cleanup_v1 import run_cleanup
from scripts.lp_rh_shadow_daemon_v1_readonly import _run_episode_persisted
from scripts.lp_rh_store_v1_readonly import migrate, open_store
from tests.test_lp_rh_shadow_daemon_v1_readonly import _daemon_passing_sample
from tests.test_lp_rh_shadow_runner_v1_readonly import _conj_meta

POOL = "0x000000000000000000000000000000000000f001"
NOW = "2026-09-08T18:05:00Z"


class _CrashingSample(dict):
    """Sample that raises an unhandled exception when accessed mid-episode."""

    def get(self, key, default=None):
        if key == "sample_time":
            raise RuntimeError("Simulated worker SIGKILL / unhandled exception")
        return super().get(key, default)


def test_paper_f_crash_recovery_mid_episode(tmp_path):
    """Scenario 1: Crash recovery mid-episode.

    1. Run episode 1 with samples 0 and 1 (successfully committed).
    2. Run episode 2 with samples 0, 1, and exploding sample 2 (crashes mid-run).
    3. Assert ledger contains NO dangling state from episode 2 and ONLY marks for samples 0 and 1.
    """
    db_path = tmp_path / "ledger_s1.db"
    ledger = open_store(db_path)
    ledger.row_factory = sqlite3.Row
    migrate(ledger)

    pm = _conj_meta(as_of="2026-09-08T17:59:55Z", pool_address=POOL)
    cfg = {
        "position_usd": Decimal("1000"),
        "capital_usd": Decimal("10000"),
        "horizon_hours": 8760,
        "target_mode": "SHADOW_SCENARIO",
        "pool_meta": pm,
    }

    s0 = _daemon_passing_sample(0, pool=POOL, sample_time="2026-09-08T18:00:00Z")
    s1 = _daemon_passing_sample(1, pool=POOL, sample_time="2026-09-08T18:01:00Z")
    _run_episode_persisted(
        ledger, cfg=cfg, episode_id="ep-s1-ok", sample_list=[s0, s1], now_fn=lambda: NOW
    )

    s_c0 = _daemon_passing_sample(0, pool=POOL, sample_time="2026-09-08T18:02:00Z")
    s_c1 = _daemon_passing_sample(1, pool=POOL, sample_time="2026-09-08T18:03:00Z")
    s_c2 = _CrashingSample()

    with pytest.raises(RuntimeError, match="Simulated worker SIGKILL"):
        _run_episode_persisted(
            ledger,
            cfg=cfg,
            episode_id="ep-s1-crashed",
            sample_list=[s_c0, s_c1, s_c2],
            now_fn=lambda: NOW,
        )

    ledger.close()

    # Verify fresh connection has no dangling state from crashed episode
    fresh = open_store(db_path)
    fresh.row_factory = sqlite3.Row

    marks = fresh.execute("SELECT position_id, mark_time FROM rh_position_marks").fetchall()
    assert len(marks) == 2
    assert all("ep-s1-ok" in m["position_id"] for m in marks)
    assert not any("ep-s1-crashed" in m["position_id"] for m in marks)

    reservations = fresh.execute("SELECT intent_id FROM rh_bucket_reservations").fetchall()
    assert not any("ep-s1-crashed" in r["intent_id"] for r in reservations)
    fresh.close()


def test_paper_f_duplicate_episode_replay(tmp_path):
    """Scenario 2: Duplicate episode replay.

    1. Run episode E on ledger.
    2. Re-run identical episode E on same ledger.
    3. Assert second run returns duplicate_rows > 0.
    4. Assert row counts in ledger tables did NOT double.
    """
    db_path = tmp_path / "ledger_s2.db"
    ledger = open_store(db_path)
    ledger.row_factory = sqlite3.Row
    migrate(ledger)

    pm = _conj_meta(as_of="2026-09-08T17:59:55Z", pool_address=POOL)
    cfg = {
        "position_usd": Decimal("1000"),
        "capital_usd": Decimal("10000"),
        "horizon_hours": 8760,
        "target_mode": "SHADOW_SCENARIO",
        "pool_meta": pm,
    }

    s0 = _daemon_passing_sample(0, pool=POOL, sample_time="2026-09-08T18:00:00Z")
    steps1, dups1, stats1 = _run_episode_persisted(
        ledger, cfg=cfg, episode_id="ep-s2-dup", sample_list=[s0], now_fn=lambda: NOW
    )

    cnt_gates_1 = ledger.execute("SELECT count(*) FROM rh_gate_decisions").fetchone()[0]
    cnt_marks_1 = ledger.execute("SELECT count(*) FROM rh_position_marks").fetchone()[0]
    cnt_pos_1 = ledger.execute("SELECT count(*) FROM rh_shadow_positions").fetchone()[0]

    steps2, dups2, stats2 = _run_episode_persisted(
        ledger, cfg=cfg, episode_id="ep-s2-dup", sample_list=[s0], now_fn=lambda: NOW
    )

    cnt_gates_2 = ledger.execute("SELECT count(*) FROM rh_gate_decisions").fetchone()[0]
    cnt_marks_2 = ledger.execute("SELECT count(*) FROM rh_position_marks").fetchone()[0]
    cnt_pos_2 = ledger.execute("SELECT count(*) FROM rh_shadow_positions").fetchone()[0]

    assert dups2 > 0
    assert cnt_gates_1 == cnt_gates_2
    assert cnt_marks_1 == cnt_marks_2
    assert cnt_pos_1 == cnt_pos_2
    ledger.close()


def test_paper_f_reservation_recovery_after_crash(tmp_path):
    """Scenario 3: Reservation recovery after crash.

    1. Simulate orphaned PENDING reservation left by crashed run.
    2. Run run_cleanup(db_path, apply=True).
    3. Assert reservation transitioned to RELEASED.
    4. Assert NO rows deleted (audit log intact).
    """
    db_path = tmp_path / "ledger_s3.db"
    ledger = open_store(db_path)
    migrate(ledger)

    orphan_intent = "rh-shadow-orphan-crash-1"
    ledger.execute(
        """
        INSERT INTO rh_bucket_reservations
            (intent_id, policy_version, bucket, amount_usd, status, created_at)
        VALUES (?, 'pol1', 'CORE', '500.00', 'PENDING', '2026-09-08T10:00:00Z')
        """,
        (orphan_intent,),
    )
    ledger.commit()
    count_before = ledger.execute("SELECT count(*) FROM rh_bucket_reservations").fetchone()[0]
    ledger.close()

    report = run_cleanup(db_path, older_than_hours=0.0, apply=True)
    assert report["released"] >= 1

    ledger2 = open_store(db_path)
    ledger2.row_factory = sqlite3.Row
    count_after = ledger2.execute("SELECT count(*) FROM rh_bucket_reservations").fetchone()[0]
    assert count_before == count_after, "No rows should be deleted from audit log"

    row = ledger2.execute(
        "SELECT status, released_at FROM rh_bucket_reservations WHERE intent_id = ?",
        (orphan_intent,),
    ).fetchone()
    assert row["status"] == "RELEASED"
    assert row["released_at"] is not None
    ledger2.close()
