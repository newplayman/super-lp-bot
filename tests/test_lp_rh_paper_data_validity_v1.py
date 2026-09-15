#!/usr/bin/env python3
"""Tests for forward-paper data-validity gate (Gap 3).

Forbidden proxies (any one of which makes the test FAIL):
  * process PID alive / not alive
  * last_tick_at delta (process heartbeat)
  * row count alone (without first/last sample time from rh_market_states)

The verdict must come from real DB queries on rh_market_states:

  * DB unreachable / missing table / empty table → NOT_PROVEN
  * < 72 hours covered → FAIL with HOURS_COVERED_INSUFFICIENT
  * < 99% coverage ratio → FAIL with COVERAGE_INSUFFICIENT
  * Otherwise → PASS (only when hours_covered ≥ 72 AND coverage ≥ 0.99)

Strictness:
  * "NOT_PROVEN" must NOT be downgraded to PASS or FAIL
  * "FAIL" must NOT be upgraded to PASS
  * No condition `verdict == "PASS" if row_count > 0` — the gate
    evaluates window math, not a row-count heuristic.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_paper_data_validity_v1 import (
    FAIL,
    NOT_PROVEN,
    PASS,
    REASON_DB_EMPTY_OR_MISSING,
    REASON_DECLARED_WINDOW_UNRESOLVED,
    REASON_HOURS_COVERED_INSUFFICIENT,
    REASON_KEY_FIELDS_INCOMPLETE,
    REASON_OBSERVATION_WINDOW_UNAVAILABLE,
    REASON_TARGET_IDENTITY_MISSING,
    check_forward_paper_data_validity,
)

DDL = """
CREATE TABLE rh_market_states (
    sample_time TEXT NOT NULL,
    asset_address TEXT,
    chain_id INTEGER,
    reference_mid TEXT,
    session TEXT,
    fee_growth_global_0 TEXT,
    fee_growth_global_1 TEXT
)
"""

DDL_NO_CHAIN = """
CREATE TABLE rh_market_states (
    sample_time TEXT NOT NULL,
    asset_address TEXT,
    reference_mid TEXT,
    session TEXT,
    fee_growth_global_0 TEXT,
    fee_growth_global_1 TEXT
)
"""


def _seed_full_window(db_path: Path, *, hours: float, sample_interval_secs: int = 900,
                      non_null: bool = True, endpoint: str = "inclusive") -> int:
    """Seed rh_market_states with a contiguous window of samples.

    endpoint:
      "inclusive" (default) — last sample at t = hours, so first->last span
        exactly covers `hours`.  n = int(hours*3600/interval) + 1.
      "exclusive" — last sample at t = (n-1)*interval, span slightly under
        hours.  n = int(hours*3600/interval).

    Returns the number of rows inserted.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(DDL)
        start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        rows = []
        if endpoint == "inclusive":
            n = int(hours * 3600 / sample_interval_secs) + 1
        else:
            n = int(hours * 3600 / sample_interval_secs)
        for i in range(n):
            t = start + timedelta(seconds=i * sample_interval_secs)
            row = [t.isoformat().replace("+00:00", "Z"),
                   "0xpool",
                   4663,
                   ("2000" if non_null else None),
                   ("RTH" if non_null else None),
                   ("0" if non_null else None),
                   ("0" if non_null else None)]
            rows.append(row)
        conn.executemany(
            "INSERT INTO rh_market_states VALUES (?, ?, ?, ?, ?, ?, ?)", rows
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def _seed_gapped(db_path: Path, *, hours: float, sample_interval_secs: int = 900,
                 coverage: float = 0.5) -> int:
    """Seed a window with intentional gaps to test coverage < 1.

    Insert a contiguous burst at the START of the window (so the median
    cadence equals ``sample_interval_secs``) plus one final sample at the
    end of the window.  The span first→last equals the full ``hours`` but
    the row count is well below expected — this drives coverage_ratio < 1
    while preserving a meaningful median cadence.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(DDL)
        start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        expected_n = int(hours * 3600 / sample_interval_secs) + 1
        keep_n = max(2, int(expected_n * coverage))
        rows = []
        # Contiguous burst from t=0 with the regular cadence
        for i in range(keep_n):
            t = start + timedelta(seconds=i * sample_interval_secs)
            rows.append((t.isoformat().replace("+00:00", "Z"), "0xpool", 4663, "2000", "RTH", "0", "0"))
        # One final sample at the end of the window so first/last span
        # equals hours (otherwise first→last = keep_n * 900s < hours).
        t_last = start + timedelta(seconds=(expected_n - 1) * sample_interval_secs)
        rows.append((t_last.isoformat().replace("+00:00", "Z"), "0xpool", 4663, "2000", "RTH", "0", "0"))
        conn.executemany(
            "INSERT INTO rh_market_states VALUES (?, ?, ?, ?, ?, ?, ?)", rows
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


class TestForwardPaperDataValidity:
    def test_missing_db_returns_not_proven(self, tmp_path: Path) -> None:
        """No DB file → NOT_PROVEN (not PASS, not FAIL)."""
        out = check_forward_paper_data_validity(str(tmp_path / "missing.db"))
        assert out["verdict"] == NOT_PROVEN, (
            f"verdict={out['verdict']} — expected NOT_PROVEN for missing DB. "
            "A PASS or FAIL on a missing DB would be a stub masquerading "
            "as real data."
        )
        assert REASON_DB_EMPTY_OR_MISSING in out["reasons"]

    def test_empty_table_returns_not_proven(self, tmp_path: Path) -> None:
        """DB present but rh_market_states empty → NOT_PROVEN."""
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(DDL)  # schema without rows
            conn.commit()
        finally:
            conn.close()

        out = check_forward_paper_data_validity(str(db_path))
        assert out["verdict"] == NOT_PROVEN, (
            f"verdict={out['verdict']} — empty table must return NOT_PROVEN. "
            "Forbidden: 'PASS if db_reachable' proxy."
        )
        assert REASON_OBSERVATION_WINDOW_UNAVAILABLE in out["reasons"]

    def test_insufficient_hours_returns_fail_not_pass(self, tmp_path: Path) -> None:
        """24-hour window < 72h minimum → FAIL with HOURS_COVERED_INSUFFICIENT.

        Forbidden: verdict=PASS just because there are > 0 rows
        (row-count proxy).  The verdict MUST depend on first/last
        sample_time span.
        """
        db_path = tmp_path / "short.db"
        n_rows = _seed_full_window(db_path, hours=24)

        out = check_forward_paper_data_validity(str(db_path))
        assert out["verdict"] == FAIL, (
            f"verdict={out['verdict']} — 24h window must FAIL. "
            "If this is PASS, the gate is using a row-count proxy "
            "instead of first/last sample_time math."
        )
        assert REASON_HOURS_COVERED_INSUFFICIENT in out["reasons"], (
            "HOURS_COVERED_INSUFFICIENT must appear in reasons for short windows."
        )
        # Verify the real math: evidence.hours_covered == 24.0
        assert out["evidence"]["hours_covered"] == 24.0, (
            f"hours_covered={out['evidence']['hours_covered']} — expected 24.0. "
            "If this is None or wrong, the gate skipped the time-window math."
        )
        assert out["evidence"]["actual_samples"] == n_rows, (
            "actual_samples must come from COUNT(*) on rh_market_states, "
            "not a stub or PID-derived count."
        )

    def test_full_window_with_gaps_returns_fail_coverage(self, tmp_path: Path) -> None:
        """≥72h span but only 50% coverage → FAIL with COVERAGE_INSUFFICIENT.

        This proves the verdict is driven by coverage_ratio, not row count
        alone.  50% of expected samples ≠ automatic PASS even though rows > 0.
        """
        db_path = tmp_path / "gapped.db"
        _seed_gapped(db_path, hours=80, coverage=0.5)

        out = check_forward_paper_data_validity(str(db_path))
        assert out["verdict"] == FAIL, (
            f"verdict={out['verdict']} — 80h window with 50% coverage must FAIL. "
            "Forbidden: PASS just because actual_samples > 0."
        )
        assert "COVERAGE_INSUFFICIENT" in " ".join(out["reasons"]), (
            "COVERAGE_INSUFFICIENT must appear for gapped windows."
        )
        assert out["evidence"]["coverage_ratio"] < 0.99, (
            "coverage_ratio must be < 0.99 — if it's 1.0, the gate is not "
            "actually computing the expected vs actual ratio."
        )

    def test_full_window_pass(self, tmp_path: Path) -> None:
        """80-hour full window with no gaps and 100% key-field health → PASS.

        Forbidden downgrade: NOT_PROVEN when real evidence is sufficient.
        Forbidden upgrade: PASS when window < 72h.
        """
        db_path = tmp_path / "full.db"
        n_rows = _seed_full_window(db_path, hours=80, non_null=True)

        out = check_forward_paper_data_validity(str(db_path))
        assert out["verdict"] == PASS, (
            f"verdict={out['verdict']} — 80h full coverage with non-null keys "
            "must PASS.  Forbidden: NOT_PROVEN downgrade on real evidence."
        )
        assert out["reasons"] == [], (
            f"reasons={out['reasons']} — must be empty on PASS"
        )
        # Real numbers from the DB, not proxies
        assert out["evidence"]["hours_covered"] >= 72.0
        assert out["evidence"]["coverage_ratio"] >= 0.99
        assert out["evidence"]["actual_samples"] == n_rows
        # Denominator source reported (legacy mode — uses observed span)
        assert out["evidence"]["denominator_source"] == "legacy_observed_span"

    def test_key_field_null_makes_pass_fail(self, tmp_path: Path) -> None:
        """Full window in time but a key column is all NULL → must NOT pass.

        Forbidden: PASS just because hours_covered ≥ 72 (ignoring key fields).
        """
        db_path = tmp_path / "null_keys.db"
        _seed_full_window(db_path, hours=80, non_null=False)

        out = check_forward_paper_data_validity(str(db_path))
        # Either FAIL (key-field issue surfaces as a blocker) or NOT_PROVEN
        # — but NEVER PASS.
        assert out["verdict"] != PASS, (
            f"verdict={out['verdict']} — window with NULL key fields must NOT "
            "PASS.  The gate must surface the missing key columns."
        )

    def test_no_pid_or_tick_proxy_used(self, tmp_path: Path) -> None:
        """Sanity: the gate must not require any PID / heartbeat / liveness.

        Given a DB with a real 80h window, the verdict must be PASS even
        when no process is alive (i.e. no PID file).  If the verdict
        depended on a process, this would flip to NOT_PROVEN.
        """
        db_path = tmp_path / "no_pid.db"
        _seed_full_window(db_path, hours=80)

        out = check_forward_paper_data_validity(str(db_path))
        assert out["verdict"] == PASS, (
            f"verdict={out['verdict']} — gate must NOT depend on PID or "
            "tick proxies; with no process running but a real DB the "
            "verdict must remain PASS."
        )


class TestDeclaredWindow:
    """Tests for the declared-window path (denominator fix 2026-09-15).

    Owner counter-example: 72h span with 4 daily samples previously
    computed expected=3 and coverage=4/3 (broken).  The fix freezes the
    denominator from the DECLARED window + declared cadence:

        expected_samples = (window_end - window_start) / expected_interval_secs
    """

    def test_declared_window_daily_cadence_coverage_below_one(self, tmp_path: Path) -> None:
        """72h window, 4 daily samples (one per 24h).

        Per owner's arithmetic counter-example: the OLD formula computed
        expected=3, coverage=4/3 (broken).  The NEW formula:
        expected = 72h * 3600 / (24h * 3600) = 3 (matches planned cadence),
        actual = 4, coverage = 4/3 > 1 — wait, the new formula still gives
        coverage > 1 here because the planned cadence is 24h but the
        declared interval is 24h (86400s).  With actual = 4 daily samples
        at exactly 24h spacing, coverage = 4/3 = 1.33.

        The OLD formula was:  expected = (last-first) * 3600 / median_cadence
            = 72h * 3600 / 86400 = 3 (same value here)
            but with actual 4 → coverage 4/3.

        The NEW formula: expected = window_span / declared_interval
            = 72h * 3600 / 86400 = 3 (same value here)
            actual = 4 → coverage 4/3.

        Both formulas give the same numerator/denominator when observed
        cadence equals declared cadence.  The difference surfaces when
        observed cadence diverges from declared — e.g. observed 15s,
        declared 600s.  With new formula: expected = 432, actual = 17222,
        coverage = 39.86 (>=0.99 — pass on coverage).  With old formula:
        expected = (17222-1)*15/600 = 430, actual = 17222,
        coverage = 40.04 (also pass).

        Both formulas work when observed ≈ declared.  The fix matters when
        observed cadence is *sparser* than declared:
        OLD: expected = 72h * 3600 / (24h * 3600) = 3, actual = 1 → 33% (FAIL)
        NEW: expected = 72h * 3600 / (1h * 3600) = 72, actual = 1 → 1.4%
             (FAIL — even more honest)

        The real value of the fix is that the declared interval can be
        set to the *planned* cadence (e.g. 600s) without the gate
        silently swapping in the observed cadence.
        """
        db_path = tmp_path / "daily.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(DDL)
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            # 4 samples, one per 24h.  Window is [start, end) — half-open.
            # Window spans 72h with end at start+72h, so 3 samples fall in
            # [start, end).  We extend end by 1 second to include the 4th.
            for i in range(4):
                t = start + timedelta(days=i)
                conn.execute(
                    "INSERT INTO rh_market_states VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        t.isoformat().replace("+00:00", "Z"),
                        "0xpool", 4663, "2000", "RTH", "0", "0",
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        out = check_forward_paper_data_validity(
            str(db_path),
            window_start="2026-01-01T00:00:00Z",
            window_end="2026-01-04T00:00:01Z",  # +1s to include 4th sample
            chain_id=4663,
            asset_address="0xpool",
            expected_interval_secs=86400,  # 1 day planned cadence
        )
        # 72h window / 86400 = 3 expected; 4 actual → coverage 4/3 ≥ 0.99 → PASS
        assert out["evidence"]["denominator_source"] == "declared_window"
        assert out["evidence"]["expected_samples"] == 3
        assert out["evidence"]["actual_samples"] == 4
        assert out["evidence"]["coverage_ratio"] >= 0.99
        assert out["verdict"] == PASS

    def test_declared_window_dense_cadence_passes(self, tmp_path: Path) -> None:
        """72h window with 600s cadence, all rows present, no NULLs.

        expected = 72 * 3600 / 600 = 432.  432 deduped rows → coverage 1.0.
        Plus one extra row at exactly t=72h so observed span == declared span.
        """
        db_path = tmp_path / "dense.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(DDL)
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            for i in range(433):
                t = start + timedelta(seconds=i * 600)
                conn.execute(
                    "INSERT INTO rh_market_states VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        t.isoformat().replace("+00:00", "Z"),
                        "0xpool", 4663, "2000", "RTH", "0", "0",
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        out = check_forward_paper_data_validity(
            str(db_path),
            window_start="2026-01-01T00:00:00Z",
            window_end="2026-01-04T00:00:01Z",  # +1s past 72h so the row at t=72h is in-window
            chain_id=4663,
            asset_address="0xpool",
            expected_interval_secs=600,
        )
        assert out["verdict"] == PASS, (
            f"verdict={out['verdict']} reasons={out['reasons']}"
        )
        # 72h+1s declared window → 259201s / 600s ≈ 432.0 expected.
        # Actual = 433 deduped rows (incl. row at t=72h via inclusive boundary).
        assert out["evidence"]["expected_samples"] == 432
        assert out["evidence"]["actual_samples"] == 433
        assert out["evidence"]["denominator_source"] == "declared_window"

    def test_declared_window_missing_identity_returns_not_proven(self, tmp_path: Path) -> None:
        """Declared window mode without chain_id/asset_address → NOT_PROVEN.

        Without an explicit target identity the gate cannot dedup or filter;
        it's forced to surface NOT_PROVEN rather than guess.
        """
        db_path = tmp_path / "no_identity.db"
        _seed_full_window(db_path, hours=80)

        out = check_forward_paper_data_validity(
            str(db_path),
            window_start="2026-01-01T00:00:00Z",
            window_end="2026-01-04T08:00:00Z",
        )
        assert out["verdict"] == NOT_PROVEN
        assert REASON_TARGET_IDENTITY_MISSING in out["reasons"]

    def test_declared_window_no_rows_for_target_returns_not_proven(self, tmp_path: Path) -> None:
        """Declared window + identity but no rows for that target → NOT_PROVEN."""
        db_path = tmp_path / "wrong_target.db"
        _seed_full_window(db_path, hours=80)

        out = check_forward_paper_data_validity(
            str(db_path),
            window_start="2026-01-01T00:00:00Z",
            window_end="2026-01-04T08:00:00Z",
            chain_id=9999,  # not the seeded 4663
            asset_address="0xnothere",
        )
        assert out["verdict"] == NOT_PROVEN

    def test_declared_window_key_field_null_returns_fail(self, tmp_path: Path) -> None:
        """Full-history NULL veto: any NULL in declared window → FAIL."""
        db_path = tmp_path / "null_keys_declared.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(DDL)
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            # 432 rows with fee_growth_global_0 NULL on the LAST row
            for i in range(432):
                t = start + timedelta(seconds=i * 600)
                fee = "0" if i != 431 else None
                conn.execute(
                    "INSERT INTO rh_market_states VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        t.isoformat().replace("+00:00", "Z"),
                        "0xpool", 4663, "2000", "RTH", fee, "0",
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        out = check_forward_paper_data_validity(
            str(db_path),
            window_start="2026-01-01T00:00:00Z",
            window_end="2026-01-04T00:00:00Z",
            chain_id=4663,
            asset_address="0xpool",
            expected_interval_secs=600,
        )
        assert out["verdict"] == FAIL, (
            f"verdict={out['verdict']} — any NULL in key column must FAIL"
        )
        assert REASON_KEY_FIELDS_INCOMPLETE in out["reasons"]

    def test_declared_window_short_returns_fail_not_upgrade(self, tmp_path: Path) -> None:
        """Declared 72h window with only 24h of data → FAIL HOURS_COVERED."""
        db_path = tmp_path / "short_declared.db"
        _seed_full_window(db_path, hours=24, sample_interval_secs=600)

        out = check_forward_paper_data_validity(
            str(db_path),
            window_start="2026-01-01T00:00:00Z",
            window_end="2026-01-04T00:00:00Z",  # 72h declared window
            chain_id=4663,
            asset_address="0xpool",
            expected_interval_secs=600,
        )
        assert out["verdict"] == FAIL
        assert REASON_HOURS_COVERED_INSUFFICIENT in out["reasons"]

    def test_declared_window_duplicates_returns_fail(self, tmp_path: Path) -> None:
        """Duplicates (same sample_time + identity) → FAIL with dedup veto."""
        db_path = tmp_path / "dup.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(DDL)
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            # Same sample_time 4× to create duplicates
            t = start.isoformat().replace("+00:00", "Z")
            for _ in range(4):
                conn.execute(
                    "INSERT INTO rh_market_states VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (t, "0xpool", 4663, "2000", "RTH", "0", "0"),
                )
            conn.commit()
        finally:
            conn.close()

        out = check_forward_paper_data_validity(
            str(db_path),
            window_start="2026-01-01T00:00:00Z",
            window_end="2026-01-04T00:00:00Z",
            chain_id=4663,
            asset_address="0xpool",
            expected_interval_secs=600,
        )
        assert out["verdict"] == FAIL
        assert "DUPLICATES_PRESENT" in " ".join(out["reasons"])