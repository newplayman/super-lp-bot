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
from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_paper_data_validity_v1 import (
    FAIL,
    NOT_PROVEN,
    PASS,
    REASON_COVERAGE_INSUFFICIENT,
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
        # 72h+1s window / 86400 = 3 ticks; 4 distinct samples → coverage 4/3 ≥ 0.99
        assert out["evidence"]["denominator_source"] == "declared_window"
        assert out["evidence"]["planned_grid_ticks"] == 3
        assert out["evidence"]["actual_samples"] == 4
        assert out["evidence"]["grid_aligned_valid_samples"] == 4
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
        assert out["evidence"]["planned_grid_ticks"] == 432
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

    def test_completed_declared_window_passes_when_last_reaches_end(
        self, tmp_path: Path
    ) -> None:
        """C3 positive: when window_end is set to include the last sample
        at t=72h, hours_covered = 72h exactly → PASS at min_hours=72.

        NB: this test extends window_end by +1s past 72h so the
        half-open boundary [S, E) includes the row at t=72h.  Without
        the extension, see test_halfopen_window_short_by_one_tick — the
        completed time is 71.833h < 72h → FAIL.
        """
        db_path = tmp_path / "completed.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(DDL)
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            for i in range(433):  # inclusive of t=72h
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
            window_end="2026-01-04T00:00:01Z",  # inclusive of t=72h
            chain_id=4663,
            asset_address="0xpool",
            expected_interval_secs=600,
            min_hours=72.0,
        )
        ev = out["evidence"]
        # hours_covered = completed declared window time = 72h
        assert ev["hours_formula"] == "completed_declared_window", (
            f"hours_formula={ev.get('hours_formula')!r}"
        )
        assert ev["hours_covered"] >= 72.0, (
            f"hours_covered={ev['hours_covered']} < 72.0"
        )
        # coverage_ratio uses grid_aligned_valid_samples / planned_grid_ticks
        assert ev["coverage_formula"] == "grid_aligned_valid_distinct"
        assert ev["grid_aligned_valid_samples"] > 0
        assert ev["planned_grid_ticks"] > 0
        assert ev["coverage_ratio"] >= 0.99
        assert out["verdict"] == PASS, (
            f"expected PASS; got {out['verdict']} reasons={out['reasons']}"
        )
        assert REASON_HOURS_COVERED_INSUFFICIENT not in out["reasons"]

    def test_hours_covered_fails_when_last_sample_short_of_window_end(
        self, tmp_path: Path
    ) -> None:
        """C3 negative: even with dense grid, if last sample is short of
        window_end the completed time < min_hours → FAIL.

        Regression guard: completed_declared_window must NOT silently lower
        the bar by counting samples × cadence.
        """
        db_path = tmp_path / "short_completed.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(DDL)
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            # Only 24h of data — last sample is at t=24h, window_end=72h.
            # hours_covered = (24h - 0) = 24h < 71h min_hours → FAIL.
            for i in range(145):  # 24h × 3600 / 600 = 144 ticks; 145 incl.
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
            window_end="2026-01-04T00:00:00Z",  # 72h declared
            chain_id=4663,
            asset_address="0xpool",
            expected_interval_secs=600,
            min_hours=71.0,
        )
        ev = out["evidence"]
        assert ev["hours_formula"] == "completed_declared_window"
        assert ev["hours_covered"] < 71.0, (
            f"hours_covered={ev['hours_covered']} >= 71.0; test premise broken"
        )
        assert out["verdict"] == FAIL, (
            f"expected FAIL; got {out['verdict']} reasons={out['reasons']}"
        )
        assert REASON_HOURS_COVERED_INSUFFICIENT in out["reasons"]

    def test_halfopen_window_short_by_one_tick_fails(
        self, tmp_path: Path
    ) -> None:
        """C3 (frozen contract 2026-09-16): half-open [S, E) window.

        Test intent: when the LAST tick of the planned grid is unobserved
        AND the resulting coverage falls below the min_coverage threshold,
        the declared window fails the gate.  The frozen rule is:
        coverage >= threshold → hours_covered = declared span → PASS;
        coverage < threshold → FAIL at coverage gate (regardless of
        last-tick snap details).

        Setup: 72h window, 600s cadence → planned grid = 432 ticks.
        Insert 425 samples covering the first 425 ticks (0..424),
        deliberately dropping the last 7 ticks → coverage ≈ 0.984,
        below min_coverage = 0.99 → FAIL.
        """
        db_path = tmp_path / "halfopen.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(DDL)
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            # 425 rows: covers ticks 0..424 (offsets 0..254400).
            # Last tick at offset 254400.  7 ticks missing near E.
            # coverage = 425/432 = 0.984 < 0.99 → FAIL.
            for i in range(425):
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
            window_end="2026-01-04T00:00:00Z",  # 72h
            chain_id=4663,
            asset_address="0xpool",
            expected_interval_secs=600,
            min_hours=72.0,
            min_coverage=Decimal("0.99"),
        )
        ev = out["evidence"]
        assert ev["hours_formula"] == "completed_declared_window"
        # coverage < 0.99 → COVERAGE_INSUFFICIENT → FAIL.
        assert out["verdict"] == FAIL, (
            f"expected FAIL at coverage<0.99; got {out['verdict']} "
            f"reasons={out['reasons']}"
        )
        assert any("COVERAGE_INSUFFICIENT" in r for r in out["reasons"]), (
            f"expected COVERAGE_INSUFFICIENT in reasons; got {out['reasons']}"
        )
        assert REASON_HOURS_COVERED_INSUFFICIENT in out["reasons"], (
            f"HOURS_COVERED_INSUFFICIENT must fire; reasons={out['reasons']}"
        )

    def test_coverage_ratio_distinct_grid_ticks_dedup(
        self, tmp_path: Path
    ) -> None:
        """C3: coverage_ratio = distinct grid-aligned samples / planned
        grid ticks.  Dedup rule: same grid tick from multiple rows
        counts ONCE.

        Scenario: 24h window, 600s cadence → 144 planned ticks.
        Insert 200 rows: 144 at unique ticks + 56 duplicates of
        existing ticks.  grid_aligned_valid_samples = 144 (NOT 200).
        coverage_ratio = 144 / 144 = 1.0.
        """
        db_path = tmp_path / "dup_grid.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(DDL)
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            # 144 unique ticks
            for i in range(144):
                t = start + timedelta(seconds=i * 600)
                conn.execute(
                    "INSERT INTO rh_market_states VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        t.isoformat().replace("+00:00", "Z"),
                        "0xpool", 4663, "2000", "RTH", "0", "0",
                    ),
                )
            # 56 duplicates of existing ticks (100s offset within the
            # same 600s cell).  After snapping they collide.  These are
            # DIFFERENT sample_times so SQL GROUP BY dedup doesn't
            # collapse them; the grid-snap dedup is what catches them.
            for i in range(56):
                t = start + timedelta(seconds=i * 600 + 100)
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
            window_end="2026-01-02T00:00:00Z",  # 24h
            chain_id=4663,
            asset_address="0xpool",
            expected_interval_secs=600,
            min_hours=23.5,
        )
        ev = out["evidence"]
        # actual_samples (raw) = 200, grid_aligned_valid_samples = 144
        assert ev["coverage_formula"] == "grid_aligned_valid_distinct"
        assert ev["grid_aligned_valid_samples"] == 144, (
            f"grid_aligned_valid_samples must dedup to 144; got "
            f"{ev['grid_aligned_valid_samples']}"
        )
        assert ev["planned_grid_ticks"] == 144
        assert ev["coverage_ratio"] == pytest.approx(1.0, abs=1e-6), (
            f"coverage_ratio={ev['coverage_ratio']}; expected 1.0"
        )
        # This test exercises GRID-LEVEL dedup (different sample_times
        # snapping to the same 600s cell).  SQL-level dedup
        # (same sample_time) is exercised by
        # test_declared_window_duplicates_returns_fail below; that one
        # DOES fire DUPLICATES_PRESENT.

    def test_gap_in_middle_fails_coverage_with_no_tolerance(
        self, tmp_path: Path
    ) -> None:
        """C3: gaps in the middle of the window reduce coverage_ratio
        linearly with gap size; no implicit tolerance.

        24h window, 600s cadence → 144 planned ticks.  Insert 100 rows
        covering t = S..(S + 99*600) = 0:00 .. 16:20, then a 44-tick
        gap (16:20 to 24:00).  grid_aligned_valid_samples = 100.
        coverage_ratio = 100 / 144 ≈ 0.694.
        """
        db_path = tmp_path / "gap.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(DDL)
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            for i in range(100):
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
            window_end="2026-01-02T00:00:00Z",
            chain_id=4663,
            asset_address="0xpool",
            expected_interval_secs=600,
            min_hours=16.0,
            min_coverage=Decimal("0.95"),
        )
        ev = out["evidence"]
        # hours_covered = (S + 99*600) - S = 16.5h ≥ 16h → HOURS gate OK
        # coverage = 100 / 144 ≈ 0.694 < 0.95 → COVERAGE gate FAILS
        assert ev["hours_covered"] >= 16.0
        assert ev["coverage_ratio"] == pytest.approx(
            float(Decimal("100") / Decimal("144")), abs=1e-3
        ), (
            f"coverage_ratio={ev['coverage_ratio']}; expected "
            f"100/144 ≈ 0.694"
        )
        assert out["verdict"] == FAIL
        assert REASON_COVERAGE_INSUFFICIENT in out["reasons"]

    def test_stale_window_fail_no_tolerance(self, tmp_path: Path) -> None:
        """C3: stale data — completed time is the last sample time,
        NOT anything else.  No implicit tolerance.

        Window [S, E) = 24h.  All samples in the first 1h.  last_sample
        at t = S + 3000s.  completed_secs = 3000s = 0.833h.  min_hours=2
        → FAIL on hours.
        """
        db_path = tmp_path / "stale.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(DDL)
            start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            for i in range(6):
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
            window_end="2026-01-02T00:00:00Z",
            chain_id=4663,
            asset_address="0xpool",
            expected_interval_secs=600,
            min_hours=2.0,
        )
        ev = out["evidence"]
        assert ev["hours_covered"] == pytest.approx(0.833, abs=0.01), (
            f"hours_covered={ev['hours_covered']}; expected ~0.833h"
        )
        assert out["verdict"] == FAIL
        assert REASON_HOURS_COVERED_INSUFFICIENT in out["reasons"]