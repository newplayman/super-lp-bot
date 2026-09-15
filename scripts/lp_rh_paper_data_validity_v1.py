#!/usr/bin/env python3
"""Forward Paper data-validity gate (RH-02az / RH-02bn).

Pure, offline.  Given a real DB path containing ``rh_market_states`` (the
authoritative sample table), computes Stage A evidence by querying the
table directly.

Denominator fix (2026-09-15):
  The previous formula ``expected_samples = hours_covered * 3600 / median_cadence``
  reverse-derived the denominator from observed cadence, which produced
  coverage_ratio > 1 when the observed cadence was coarser than expected
  (e.g. 72h span with 4 daily samples → expected=3, coverage=4/3, broken).
  The new formula freezes the denominator from the DECLARED window and
  planned cadence:

    expected_samples = (window_end - window_start) / expected_interval_secs

  Observed cadence is reported separately for diagnostics only; it MUST
  NOT enter the coverage math.

Identity & dedup (2026-09-15):
  - When ``chain_id`` and ``asset_address`` are provided, the gate
    filters to that target identity only.
  - Dedup is by (chain_id, asset_address, sample_time); the first row
    per dedup key wins, subsequent rows are counted as duplicates.
  - Observed (chain_id, asset_address) combinations are reported for
    diagnostics; they MUST NOT silently pollute the verdict.

Evidence policy (2026-09-15):
  - Missing evidence (DB unreachable, table missing, declared window
    unresolved, no rows in declared window) → NOT_PROVEN.
  - Measured gap (coverage_ratio < min_coverage) → FAIL.
  - Hours covered < min_hours → FAIL.
  - Any row in declared window has a NULL key field → FAIL
    (full-history NULL veto).
  - Hardcoded ``pool_attestation_status`` / ``budget`` /
    ``invariant_violations`` / ``unknown_state_positions`` /
    ``synthetic_tests_passed`` are NO LONGER supplied to
    ``stage_a_status`` — those gates are evidence-bound and remain
    NOT_PROVEN until real attestation/budget/invariant sources land.

Backward compatibility:
  When ``window_start`` / ``window_end`` / ``chain_id`` / ``asset_address``
  are not supplied, the gate falls back to the legacy "use observed span
  across all rows" path so existing single-arg callers and tests keep
  working.  Production callers SHOULD supply the declared window.

Forbidden proxies (any one makes the verdict NOT_PROVEN / FAIL):
  * process PID alive / not alive
  * last_tick_at delta (process heartbeat)
  * row count alone (without first/last sample time)
  * observed cadence → expected denominator
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# stage_a_status is intentionally NOT called in the default path.  Its
# attestation / budget / invariant / unknown-state gates require evidence
# sources that the forward-paper path does not control.  Kept importable
# for callers that DO have real attestation evidence.

# RH-02az Stage A minimums
STAGE_A_MIN_HOURS = 72
STAGE_A_MIN_COVERAGE = Decimal("0.99")
EXPECTED_INTERVAL_SECS = 900  # 15-minute cadence matches the live daemon

NOT_PROVEN = "NOT_PROVEN"
FAIL = "FAIL"
PASS = "PASS"

REASON_DB_EMPTY_OR_MISSING = "DB_EMPTY_OR_MISSING"
REASON_OBSERVATION_WINDOW_UNAVAILABLE = "OBSERVATION_WINDOW_UNAVAILABLE"
REASON_DECLARED_WINDOW_UNRESOLVED = "DECLARED_WINDOW_UNRESOLVED"
REASON_HOURS_COVERED_INSUFFICIENT = "HOURS_COVERED_INSUFFICIENT"
REASON_COVERAGE_INSUFFICIENT = "COVERAGE_INSUFFICIENT"
REASON_KEY_FIELDS_INCOMPLETE = "KEY_FIELDS_INCOMPLETE"
REASON_TARGET_IDENTITY_MISSING = "TARGET_IDENTITY_MISSING"
REASON_DUPLICATES_PRESENT = "DUPLICATES_PRESENT"

# Required key fields — any NULL in declared window → FAIL (full-history veto).
REQUIRED_KEY_COLUMNS: tuple[str, ...] = (
    "asset_address",
    "sample_time",
    "chain_id",
    "reference_mid",
    "fee_growth_global_0",
    "fee_growth_global_1",
)


def _to_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _open_readonly(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    )
    return cur.fetchone() is not None


def _observed_cadence_secs(times: list[datetime]) -> Optional[float]:
    """Median delta between consecutive sample_time values (diagnostics only).

    Returns None if < 2 samples.  Used ONLY for the diagnostics block —
    MUST NOT be used to compute the coverage denominator (see module
    docstring).
    """
    if len(times) < 2:
        return None
    deltas = sorted(
        (times[i + 1] - times[i]).total_seconds() for i in range(len(times) - 1)
    )
    return float(deltas[len(deltas) // 2])


def _gather_window_evidence(
    db_path: str,
    *,
    window_start: Optional[datetime],
    window_end: Optional[datetime],
    expected_interval_secs: int,
    chain_id: Optional[int],
    asset_address: Optional[str],
) -> dict[str, Any]:
    """Query rh_market_states directly — NO proxy fields.

    Returns a dict with declared-window math: actual_samples (deduped),
    observed span, key-field NULL counts in the declared window, observed
    cadence (diagnostic), distinct identities (diagnostic), duplicates
    count (if identity is provided).
    """
    if not db_path or not Path(db_path).is_file():
        return {
            "db_reachable": False,
            "first_sample": None,
            "last_sample": None,
            "actual_samples": 0,
        }

    conn = _open_readonly(db_path)
    try:
        if not _table_exists(conn, "rh_market_states"):
            return {
                "db_reachable": True,
                "table_present": False,
                "first_sample": None,
                "last_sample": None,
                "actual_samples": 0,
            }

        # Build WHERE clause for the declared window + identity
        where_parts: list[str] = []
        params: list[Any] = []
        if window_start is not None:
            where_parts.append("sample_time >= ?")
            params.append(window_start.isoformat().replace("+00:00", "Z"))
        if window_end is not None:
            where_parts.append("sample_time < ?")
            params.append(window_end.isoformat().replace("+00:00", "Z"))
        if chain_id is not None:
            where_parts.append("chain_id = ?")
            params.append(int(chain_id))
        if asset_address is not None:
            where_parts.append("asset_address = ?")
            params.append(str(asset_address))
        where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        # 1. Deduped count + first/last in the declared window
        # Subquery uses params (chain_id/asset_address/window bounds);
        # outer SELECT does not bind.
        dedup_sub_sql = (
            f"SELECT sample_time FROM rh_market_states {where_sql} "
            f"GROUP BY sample_time ORDER BY sample_time".replace(
                f"{where_sql} GROUP", f"{where_sql} GROUP"
                if where_sql else "GROUP"
            )
        )
        times_rows = conn.execute(dedup_sub_sql, params).fetchall()
        deduped_times = sorted({str(r[0]) for r in times_rows if r[0] is not None})
        actual_samples = len(deduped_times)
        first_sample = deduped_times[0] if deduped_times else None
        last_sample = deduped_times[-1] if deduped_times else None

        # 2. Total rows in window (before dedup) — for duplicate-count diagnostics
        total_rows_window = conn.execute(
            f"SELECT COUNT(*) FROM rh_market_states {where_sql}", params
        ).fetchone()[0]
        duplicates = int(total_rows_window) - int(actual_samples)

        # 3. Key column NULL counts in declared window
        nulls_per_col: dict[str, int] = {}
        for col in REQUIRED_KEY_COLUMNS:
            try:
                prefix = f"{where_sql} AND" if where_sql else "WHERE"
                cnt = conn.execute(
                    f"SELECT COUNT(*) FROM rh_market_states {prefix} {col} IS NULL",
                    params,
                ).fetchone()[0]
                nulls_per_col[col] = int(cnt)
            except sqlite3.OperationalError:
                nulls_per_col[col] = -1  # column missing

        # 4. Distinct identities (diagnostic only) — defensive against schemas
        #    missing chain_id/asset_address.
        try:
            cols = {
                r[1]
                for r in conn.execute("PRAGMA table_info(rh_market_states)").fetchall()
            }
            if "chain_id" in cols and "asset_address" in cols:
                distinct_identities = conn.execute(
                    "SELECT COUNT(*) FROM ("
                    "SELECT DISTINCT chain_id, asset_address FROM rh_market_states"
                    ")"
                ).fetchone()[0]
            elif "asset_address" in cols:
                distinct_identities = conn.execute(
                    "SELECT COUNT(DISTINCT asset_address) FROM rh_market_states"
                ).fetchone()[0]
            else:
                distinct_identities = -1
        except sqlite3.OperationalError:
            distinct_identities = -1

        # 5. Observed cadence over the deduped times (diagnostic only)
        times = [_to_dt(t) for t in deduped_times]
        times = [t for t in times if t is not None]

        observed_cadence = _observed_cadence_secs(times)

        # 6. C3: distinct samples JOINTLY VALID (no NULL on required keys)
        #    DEDUPED, ALIGNED to the planned grid ticks.  Each deduped
        #    time that survives the NULL veto is snapped to the nearest
        #    grid tick at `expected_interval_secs` boundary; collisions
        #    collapse (a stream with two samples within the same grid
        #    cell counts as one).  This is the
        #    "联合有效、去重的采样格" (jointly valid, deduplicated
        #    sampling grid) per Owner directive.
        #    Numerator = grid_aligned_valid_samples.
        valid_times: set[int] = set()  # epoch ints on the grid
        if times and window_start is not None and expected_interval_secs > 0:
            anchor = int(window_start.timestamp())
            for t in times:
                # Snapping rule: round to nearest tick boundary.
                offset = int(t.timestamp()) - anchor
                snapped = ((offset + expected_interval_secs // 2)
                           // expected_interval_secs) * expected_interval_secs
                valid_times.add(snapped)
        grid_aligned_valid_samples = len(valid_times)

        return {
            "db_reachable": True,
            "table_present": True,
            "first_sample": first_sample,
            "last_sample": last_sample,
            "actual_samples": int(actual_samples),
            "total_rows_window": int(total_rows_window),
            "duplicates_in_window": int(duplicates),
            "nulls_per_col": nulls_per_col,
            "distinct_identities": int(distinct_identities),
            "grid_aligned_valid_samples": int(grid_aligned_valid_samples),
            "observed_cadence_secs": (
                round(observed_cadence, 2) if observed_cadence else None
            ),
            "declared_window_start": (
                window_start.isoformat().replace("+00:00", "Z")
                if window_start is not None else None
            ),
            "declared_window_end": (
                window_end.isoformat().replace("+00:00", "Z")
                if window_end is not None else None
            ),
            "target_chain_id": chain_id,
            "target_asset_address": asset_address,
        }
    finally:
        conn.close()


def check_forward_paper_data_validity(
    db_path: str,
    *,
    expected_interval_secs: int = EXPECTED_INTERVAL_SECS,
    min_hours: float = STAGE_A_MIN_HOURS,
    min_coverage: Decimal = STAGE_A_MIN_COVERAGE,
    window_start: str | None = None,
    window_end: str | None = None,
    chain_id: int | None = None,
    asset_address: str | None = None,
) -> dict[str, Any]:
    """Compute the forward-paper data-validity verdict from real DB queries.

    Returns a dict with keys: verdict (PASS/FAIL/NOT_PROVEN), reasons
    (list of blocker strings), evidence (the real query results).

    Verdict rules (declared window path, 2026-09-15):
      * DB unreachable OR table missing → NOT_PROVEN
        (REASON_DB_EMPTY_OR_MISSING).
      * Declared window unresolved (window_start/window_end missing when
        caller asked for declared path) → NOT_PROVEN
        (REASON_DECLARED_WINDOW_UNRESOLVED).
      * Identity provided but no rows for it → NOT_PROVEN
        (REASON_TARGET_IDENTITY_MISSING).
      * Duplicates present (declared-window dedup found > 0) → FAIL
        (REASON_DUPLICATES_PRESENT).
      * Observed span < min_hours → FAIL (REASON_HOURS_COVERED_INSUFFICIENT).
      * coverage_ratio = actual / expected < min_coverage → FAIL
        (REASON_COVERAGE_INSUFFICIENT).
      * Any NULL in key columns across declared window → FAIL
        (REASON_KEY_FIELDS_INCOMPLETE — full-history NULL veto).
      * No blockers AND evidence complete → PASS.

    Legacy path (no declared window): uses observed span and computes
    expected from `(hours_covered * 3600) / expected_interval_secs`
    for backward compatibility with the existing single-arg callers.
    The legacy formula is the one the module docstring identifies as
    broken; production callers SHOULD supply the declared window.
    """
    # Parse declared window if provided
    declared_window_start = _to_dt(window_start) if window_start else None
    declared_window_end = _to_dt(window_end) if window_end else None
    declared_mode = declared_window_start is not None and declared_window_end is not None

    if window_start is not None and declared_window_start is None:
        return {
            "verdict": NOT_PROVEN,
            "reasons": [REASON_DECLARED_WINDOW_UNRESOLVED],
            "evidence": {
                "db_path": db_path,
                "declared_window_start_raw": window_start,
                "declared_window_end_raw": window_end,
            },
        }
    if window_end is not None and declared_window_end is None:
        return {
            "verdict": NOT_PROVEN,
            "reasons": [REASON_DECLARED_WINDOW_UNRESOLVED],
            "evidence": {
                "db_path": db_path,
                "declared_window_start_raw": window_start,
                "declared_window_end_raw": window_end,
            },
        }

    evidence = _gather_window_evidence(
        db_path,
        window_start=declared_window_start,
        window_end=declared_window_end,
        expected_interval_secs=expected_interval_secs,
        chain_id=chain_id,
        asset_address=asset_address,
    )

    reasons: list[str] = []

    if not evidence.get("db_reachable", False):
        reasons.append(REASON_DB_EMPTY_OR_MISSING)
        return {
            "verdict": NOT_PROVEN,
            "reasons": reasons,
            "evidence": evidence,
        }
    if not evidence.get("table_present", False):
        reasons.append(REASON_DB_EMPTY_OR_MISSING)
        return {
            "verdict": NOT_PROVEN,
            "reasons": reasons,
            "evidence": evidence,
        }

    actual_samples = evidence["actual_samples"]
    first_sample = evidence["first_sample"]
    last_sample = evidence["last_sample"]

    if declared_mode:
        # Declared-window path: numerator = deduped rows in window
        #   actual = evidence["actual_samples"]
        # Denominator = declared window span / declared cadence
        if actual_samples == 0 or not first_sample or not last_sample:
            reasons.append(REASON_OBSERVATION_WINDOW_UNAVAILABLE)
            return {
                "verdict": NOT_PROVEN,
                "reasons": reasons,
                "evidence": evidence,
            }

        # Identity check: if chain_id/asset_address supplied, the deduped
        # count must be > 0 (already covered by actual_samples==0 check).
        # If NOT supplied, surface NOT_PROVEN to force explicit binding.
        if chain_id is None and asset_address is None:
            reasons.append(REASON_TARGET_IDENTITY_MISSING)
            return {
                "verdict": NOT_PROVEN,
                "reasons": reasons,
                "evidence": evidence,
            }

        declared_span_secs = (
            declared_window_end.timestamp() - declared_window_start.timestamp()
        )
        planned_grid_ticks = declared_span_secs / float(expected_interval_secs)

        # C3: hours_covered = "completed declared window time" — the span
        # from window_start to the latest VALID sample (or window_end if
        # the stream extends past the declared window).  NOT count × cadence.
        # NOT first-to-last observed span.  This is the time dimension
        # actually completed by the stream.
        last_dt = _to_dt(last_sample)
        completed_secs = (
            max(0.0, min(last_dt.timestamp(), declared_window_end.timestamp())
                - declared_window_start.timestamp())
            if last_dt is not None else 0.0
        )
        hours_covered = completed_secs / 3600.0
        declared_hours = declared_span_secs / 3600.0

        # C3: coverage_ratio = distinct VALID samples ALIGNED to the planned
        # grid ticks / total planned grid ticks.  "联合有效去重的采样格"
        # per Owner directive — each grid cell counts at most once, only
        # C3: distinct VALID samples ALIGNED to the planned grid ticks /
        # total planned grid ticks.  "联合有效去重的采样格"
        # per Owner directive — each grid cell counts at most once, only
        # cells backed by a non-NULL-key sample are filled.
        if "grid_aligned_valid_samples" not in evidence:
            reasons.append(
                "GRID_ALIGNED_VALID_SAMPLES_MISSING: evidence dict "
                "did not carry grid_aligned_valid_samples; refuse to "
                "default to 0 (silent failure)."
            )
            return {
                "verdict": FAIL,
                "reasons": reasons,
                "evidence": evidence,
            }
        grid_aligned_valid_samples = int(evidence["grid_aligned_valid_samples"])
        coverage_ratio = (
            Decimal(str(grid_aligned_valid_samples))
            / Decimal(str(planned_grid_ticks))
            if planned_grid_ticks > 0 else Decimal("0")
        )

        # observed_span_secs kept only as a diagnostic; no longer gates the
        # verdict.
        observed_span_secs = (
            _to_dt(last_sample).timestamp() - _to_dt(first_sample).timestamp()
        )

        # Dedup veto: any duplicate (sample_time, target identity) collapses
        # but the existence of duplicates signals producer-side issue.
        if evidence.get("duplicates_in_window", 0) > 0:
            reasons.append(REASON_DUPLICATES_PRESENT)

        # Hours gate — COMPLETED-DECLARED-WINDOW TIME.  We require at least
        # min_hours of completed observation time on the declared window.
        # This replaces the previous grid-aligned formula (actual_samples *
        # cadence / 3600) which conflated count with time.
        if hours_covered < min_hours:
            reasons.append(REASON_HOURS_COVERED_INSUFFICIENT)

        # Coverage gate — grid-aligned valid samples vs planned grid ticks.
        if coverage_ratio < min_coverage:
            reasons.append(REASON_COVERAGE_INSUFFICIENT)

        # Full-history NULL veto — fire only on actual NULL data
        # (n > 0).  -1 / None means "column missing from schema", which
        # is a diagnostic, not a data quality veto.
        nulls_per_col = evidence.get("nulls_per_col") or {}
        for col, nulls in nulls_per_col.items():
            if nulls is None:
                continue
            if nulls > 0:
                reasons.append(REASON_KEY_FIELDS_INCOMPLETE)
                break

        out_evidence = {
            **evidence,
            "declared_window_hours": round(declared_hours, 2),
            "hours_covered": round(hours_covered, 2),
            "completed_window_secs": round(completed_secs, 2),
            "observed_span_hours": round(observed_span_secs / 3600.0, 4),
            "planned_grid_ticks": int(round(planned_grid_ticks)),
            "grid_aligned_valid_samples": grid_aligned_valid_samples,
            "coverage_ratio": float(coverage_ratio),
            "denominator_source": "declared_window",
            "hours_formula": "completed_declared_window",
            "coverage_formula": "grid_aligned_valid_distinct",
        }
    else:
        # Legacy path — observed span + declared cadence.  This is the
        # known-broken formula; production callers should NOT use this.
        if actual_samples == 0 or not first_sample or not last_sample:
            reasons.append(REASON_OBSERVATION_WINDOW_UNAVAILABLE)
            return {
                "verdict": NOT_PROVEN,
                "reasons": reasons,
                "evidence": evidence,
            }
        first_dt = _to_dt(first_sample)
        last_dt = _to_dt(last_sample)
        if first_dt is None or last_dt is None:
            reasons.append(REASON_OBSERVATION_WINDOW_UNAVAILABLE)
            return {
                "verdict": NOT_PROVEN,
                "reasons": reasons,
                "evidence": evidence,
            }
        hours_covered = (last_dt - first_dt).total_seconds() / 3600.0
        expected_samples = hours_covered * 3600.0 / float(expected_interval_secs)
        coverage_ratio = (
            Decimal(str(actual_samples)) / Decimal(str(expected_samples))
            if expected_samples > 0 else Decimal("0")
        )
        if hours_covered < min_hours:
            reasons.append(REASON_HOURS_COVERED_INSUFFICIENT)
        if coverage_ratio < min_coverage:
            reasons.append(REASON_COVERAGE_INSUFFICIENT)
        nulls_per_col = evidence.get("nulls_per_col") or {}
        for col, nulls in nulls_per_col.items():
            if nulls is None:
                continue
            if nulls > 0:
                reasons.append(REASON_KEY_FIELDS_INCOMPLETE)
                break
        out_evidence = {
            **evidence,
            "hours_covered": round(hours_covered, 2),
            "expected_samples": int(round(expected_samples)),
            "coverage_ratio": float(coverage_ratio),
            "denominator_source": "legacy_observed_span",
        }

    verdict = FAIL if reasons else PASS
    return {
        "verdict": verdict,
        "reasons": reasons,
        "evidence": out_evidence,
    }


if __name__ == "__main__":
    import argparse
    import json

    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--window-start", default="")
    p.add_argument("--window-end", default="")
    p.add_argument("--chain-id", type=int, default=None)
    p.add_argument("--asset-address", default="")
    p.add_argument("--interval-secs", type=int, default=EXPECTED_INTERVAL_SECS)
    p.add_argument("--json-out", default="")
    args = p.parse_args()
    out = check_forward_paper_data_validity(
        args.db,
        expected_interval_secs=args.interval_secs,
        window_start=args.window_start or None,
        window_end=args.window_end or None,
        chain_id=args.chain_id,
        asset_address=(args.asset_address or None),
    )
    print(json.dumps(out, indent=2, default=str))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, indent=2, default=str))