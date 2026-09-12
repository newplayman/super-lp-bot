"""Test Suite E: Pool State Fail-Close & Paper Evaluation Invalidation.

Exercises _run_episode_persisted with three pool state fault scenarios:
1. STALE: pool state timestamp older than reference_age_secs cap (> 6 hours).
2. FUTURE: pool state timestamp in future relative to sample time.
3. UNKNOWN: pool state timestamp missing/None.

Asserts:
- All three produce terminal_eligible=False.
- Post-migration rh_position_marks contains invalid_for_paper_evaluation column.
- Marks table has invalid_for_paper_evaluation=1.
- rh_journal row count == 0 (no fee events booked).
- rh_bucket_reservations row count == 0 (no bucket leaked).
"""

from decimal import Decimal
from pathlib import Path
import sqlite3
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_shadow_daemon_v1_readonly import _run_episode_persisted
from scripts.lp_rh_store_v1_readonly import migrate, open_store
from tests.test_lp_rh_shadow_daemon_v1_readonly import _daemon_passing_sample
from tests.test_lp_rh_shadow_runner_v1_readonly import _conj_meta

POOL = "0x000000000000000000000000000000000000e001"
NOW = "2026-09-08T18:05:00Z"
SAMPLE_TIME = "2026-09-08T18:00:00Z"


@pytest.mark.parametrize(
    "scenario_name,as_of_ts,expected_blocker_prefix",
    [
        ("STALE", "2026-09-08T10:00:00Z", "POOL_STATE_STALE"),
        ("FUTURE", "2026-09-08T19:00:00Z", "POOL_STATE_AS_OF_IN_FUTURE"),
        ("UNKNOWN", None, "POOL_STATE_AS_OF_UNAVAILABLE"),
    ],
)
def test_paper_e_pool_state_fail_close_and_invalidates_paper(
    tmp_path, scenario_name, as_of_ts, expected_blocker_prefix
):
    ledger = open_store(tmp_path / f"ledger_{scenario_name}.db")
    ledger.row_factory = sqlite3.Row
    migrate(ledger)

    # Validate column exists post-migration; fail with clear message if missing
    columns = [
        r["name"]
        for r in ledger.execute("PRAGMA table_info(rh_position_marks)").fetchall()
    ]
    assert "invalid_for_paper_evaluation" in columns, (
        f"Column 'invalid_for_paper_evaluation' missing from rh_position_marks schema. "
        f"Existing columns: {columns}"
    )

    s = _daemon_passing_sample(0, pool=POOL, sample_time=SAMPLE_TIME)
    s["source_payload_hash"] = f"hash-paper-e-{scenario_name}"
    s["quote_usd_per_token1"] = {
        "value": "1.0",
        "source": "COINGECKO_API",
        "observed_at": SAMPLE_TIME,
        "ttl_secs": 600,
    }

    if as_of_ts is not None:
        pm = _conj_meta(as_of=as_of_ts, pool_address=POOL)
    else:
        pm = {"pool_address": POOL}

    cfg = {
        "position_usd": Decimal("1000"),
        "capital_usd": Decimal("10000"),
        "horizon_hours": 8760,
        "target_mode": "SHADOW_SCENARIO",
        "pool_meta": pm,
    }

    ep_id = f"ep-paper-e-{scenario_name.lower()}"
    steps, dups, stats = _run_episode_persisted(
        ledger,
        cfg=cfg,
        episode_id=ep_id,
        sample_list=[s],
        now_fn=lambda: NOW,
    )

    # 1. Step fail-closed: terminal_eligible is False, dominant blocker matches
    assert len(steps) == 1
    assert steps[0].terminal_eligible is False
    assert steps[0].reservation_granted is False
    assert steps[0].dominant_blocker is not None
    assert steps[0].dominant_blocker.startswith(expected_blocker_prefix)

    # 2. Assert rh_position_marks has invalid_for_paper_evaluation = 1
    marks = ledger.execute(
        "SELECT invalid_for_paper_evaluation FROM rh_position_marks WHERE position_id = ?",
        (f"rh-shadow-{ep_id}",),
    ).fetchall()
    assert len(marks) == 1
    assert marks[0]["invalid_for_paper_evaluation"] == 1

    # 3. Assert rh_journal count == 0 (no fee event booked)
    journal_count = ledger.execute("SELECT count(*) FROM rh_journal").fetchone()[0]
    assert journal_count == 0, f"Expected 0 rh_journal rows, found {journal_count}"

    # 4. Assert rh_bucket_reservations count == 0 (no bucket leaked)
    res_count = ledger.execute("SELECT count(*) FROM rh_bucket_reservations").fetchone()[0]
    assert res_count == 0, f"Expected 0 rh_bucket_reservations rows, found {res_count}"

    ledger.close()
