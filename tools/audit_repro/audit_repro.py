#!/usr/bin/env python3
"""Offline audit counterexamples for newplayman/super-lp-bot @ c2fb020a1ad3.

Default mode uses explicitly reduced reference implementations transcribed from
reviewed source. These are NOT the full repository, full pytest, or a daemon E2E
run. --repo PATH instead AST-extracts the named functions from that checkout,
without importing or running the application's module-level code. All data is
synthetic and stored in SQLite :memory: databases. No wallet, network, or service.

Exit 1: at least one targeted defect was reproduced.
Exit 0: no targeted defect reproduced (NOT a release certificate).
Exit 2: a probe or checkout validation failed.
"""
from __future__ import annotations
import argparse
import ast
import contextlib
import json
import platform
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

PIN = "c2fb020a1ad36b7b186e71d3b25a0563b24b8e08"
NOW = "2026-09-11T14:00:00Z"
BUCKETS = ("CORE", "STOCK", "MEME")
POLICY_ID = "rh_50_30_20_proposed_v1"
BUCKET_WEIGHTS = {"CORE": Decimal(".50"), "STOCK": Decimal(".30"), "MEME": Decimal(".20")}
ACTIVE_FRACTION = {"CORE": Decimal(".85"), "STOCK": Decimal(".70"), "MEME": Decimal(".40")}
RESERVED_STATUSES = ("PENDING", "CONFIRMED", "BROADCAST_UNKNOWN")
STAGE_B_MIN_DAYS, STAGE_B_MIN_WEEKENDS = 14, 1
STAGE_A_KEY_COLUMNS = ("reference_mid", "sample_time", "session", "fee_growth_global_0", "fee_growth_global_1")
STAGE_A_KEY_COLUMNS_MIN_RATIO = Decimal(".99")
KEY_FIELD_MISSING_COLUMN = "KEY_FIELD_MISSING_COLUMN"
KEY_FIELD_NEVER_POPULATED = "KEY_FIELD_NEVER_POPULATED"
KEY_FIELD_INCOMPLETE = "KEY_FIELD_INCOMPLETE"
# Test scope is one table. The reviewed daemon iterates six; the branch being
# tested is identical for the reservations table.
_LEDGER_TABLES = ("rh_bucket_reservations",)
_TABLE_PRIMARY_KEYS = {"rh_bucket_reservations": ("intent_id",)}

# Benign validation shims for known-valid test inputs. These do not test the
# repository's validators. The tested transaction and verdict branches do not
# depend on differences between these shims and the production validators.
def assert_utc_rfc3339(value, field):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(field)
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value

def assert_decimal_text(value, field):
    if not isinstance(value, str) or not Decimal(value).is_finite():
        raise ValueError(field)
    return value

def _require_decimal(value, field):
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise TypeError(field)
    return value

def _to_decimal_text(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text

def bucket_budget(capital_usd, bucket):
    if bucket not in BUCKETS:
        raise ValueError("UNKNOWN_BUCKET")
    return _require_decimal(capital_usd, "capital_usd") * BUCKET_WEIGHTS[bucket]

def bucket_active_cap(capital_usd, bucket):
    return bucket_budget(capital_usd, bucket) * ACTIVE_FRACTION[bucket]

def reserved_total(conn, bucket, policy_version):
    placeholders = ", ".join("?" for _ in RESERVED_STATUSES)
    rows = conn.execute(
        "SELECT amount_usd FROM rh_bucket_reservations "
        f"WHERE bucket = ? AND policy_version = ? AND status IN ({placeholders}) "
        "AND released_at IS NULL", (bucket, policy_version, *RESERVED_STATUSES)).fetchall()
    return sum((Decimal(row[0]) for row in rows), Decimal(0))

def try_reserve(conn, *, intent_id, bucket, amount_usd, capital_usd,
                policy_version=POLICY_ID, now):
    if bucket not in BUCKETS:
        raise ValueError("UNKNOWN_BUCKET")
    amount_usd = _require_decimal(amount_usd, "amount_usd")
    capital_usd = _require_decimal(capital_usd, "capital_usd")
    if amount_usd <= 0:
        raise ValueError("NON_POSITIVE_RESERVATION")
    now = assert_utc_rfc3339(now, "now")
    amount_text = assert_decimal_text(_to_decimal_text(amount_usd), "amount_usd")
    own_txn = not conn.in_transaction
    _SP = "rh_try_reserve"
    if own_txn:
        conn.execute("BEGIN IMMEDIATE")
    else:
        conn.execute(f"SAVEPOINT {_SP}")
    def _undo():
        if own_txn:
            conn.execute("ROLLBACK")
        else:
            conn.execute(f"ROLLBACK TO {_SP}")
            conn.execute(f"RELEASE {_SP}")
    def _finish():
        if own_txn:
            conn.execute("COMMIT")
        else:
            conn.execute(f"RELEASE {_SP}")
    try:
        reserved = reserved_total(conn, bucket, policy_version)
        room = bucket_active_cap(capital_usd, bucket) - reserved
        if amount_usd > room:
            _undo()
            return {"granted": False, "reason": "BUCKET_ACTIVE_CAP_EXCEEDED", "room": _to_decimal_text(room)}
        conn.execute("INSERT INTO rh_bucket_reservations "
                     "(intent_id, policy_version, bucket, amount_usd, status, created_at, released_at) "
                     "VALUES (?, ?, ?, ?, 'PENDING', ?, NULL)",
                     (intent_id, policy_version, bucket, amount_text, now))
        _finish()
        return {"granted": True, "reservation_id": intent_id, "room_after": _to_decimal_text(room - amount_usd)}
    except Exception:
        if conn.in_transaction:
            _undo()
        raise

def release(conn, intent_id, *, now, reason):
    now = assert_utc_rfc3339(now, "now")
    row = conn.execute("SELECT status FROM rh_bucket_reservations WHERE intent_id = ?", (intent_id,)).fetchone()
    if row is None:
        return False
    if row[0] == "BROADCAST_UNKNOWN":
        raise ValueError("CANNOT_RELEASE_BROADCAST_UNKNOWN")
    conn.execute("UPDATE rh_bucket_reservations SET status = 'RELEASED', released_at = ? WHERE intent_id = ?", (now, intent_id))
    conn.commit()
    return True

def _copy_new_rows(scratch_conn, ledger_conn, existing_decision_ids=None):
    stats = {}
    for table in _LEDGER_TABLES:
        cols = [r[1] for r in scratch_conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if not cols:
            continue
        pk_cols = _TABLE_PRIMARY_KEYS[table]
        pk_indices = [cols.index(c) for c in pk_cols]
        pk_cols_sql = ", ".join(pk_cols)
        existing_keys = {tuple(r) for r in ledger_conn.execute(f"SELECT {pk_cols_sql} FROM {table}").fetchall()}
        if table == "rh_gate_decisions" and existing_decision_ids is not None:
            for d in existing_decision_ids:
                existing_keys.add((d,) if not isinstance(d, tuple) else d)
        cols_sql = ", ".join(cols)
        placeholders = ", ".join("?" for _ in cols)
        insert_sql = f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders})"
        select_sql = f"SELECT {cols_sql} FROM {table}"
        copied = skipped = 0
        for row in scratch_conn.execute(select_sql):
            pk_val = tuple(row[idx] for idx in pk_indices)
            if pk_val in existing_keys:
                skipped += 1
                continue
            ledger_conn.execute(insert_sql, row)
            existing_keys.add(pk_val)
            copied += 1
        stats[table] = {"copied": copied, "skipped_existing": skipped}
    return stats

def _to_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None

def _day_start(day, tzinfo):
    return datetime(day.year, day.month, day.day, tzinfo=tzinfo)

def audit_weekends_covered(conn, *, asset_address, interval_secs=15):
    # Reference model of the non-error path in readiness lines 948-1005.
    times = sorted(_to_datetime(r[0]) for r in conn.execute(
        "SELECT sample_time FROM rh_market_states WHERE LOWER(asset_address) = LOWER(?)", (asset_address,)))
    if not times:
        return {"weekends_covered": None}
    by_day = {}
    for t in times:
        by_day[t.date()] = by_day.get(t.date(), 0) + 1
    first_day, last_day = times[0].date(), times[-1].date()
    complete_weekend_days = 0
    details = []
    for day in sorted(by_day):
        if day == first_day and day == last_day:
            span_secs = (times[-1] - times[0]).total_seconds()
        elif day == first_day:
            span_secs = (_day_start(day + timedelta(days=1), times[0].tzinfo) - times[0]).total_seconds()
        elif day == last_day:
            span_secs = (times[-1] - _day_start(day, times[-1].tzinfo)).total_seconds()
        else:
            span_secs = 86400.0
        expected = span_secs / float(interval_secs)
        complete = by_day[day] >= .9 * expected
        is_weekend = day.weekday() in (5, 6)
        if complete and is_weekend:
            complete_weekend_days += 1
        details.append({"date": str(day), "actual": by_day[day], "expected": expected, "complete": complete})
    return {"weekends_covered": complete_weekend_days, "days": details}

def stage_b_status(*, days_covered, weekends_covered, unexplained_ledger_diffs,
                   invariant_violations, missed_risk_events):
    blockers = []
    if days_covered is None or days_covered < STAGE_B_MIN_DAYS:
        blockers.append("DAYS_COVERED_INSUFFICIENT")
    if weekends_covered is None or weekends_covered < STAGE_B_MIN_WEEKENDS:
        blockers.append("WEEKENDS_COVERED_INSUFFICIENT")
    if unexplained_ledger_diffs is None:
        blockers.append("UNEXPLAINED_LEDGER_DIFFS_UNAVAILABLE")
    elif unexplained_ledger_diffs:
        blockers.append("UNEXPLAINED_LEDGER_DIFFS")
    if invariant_violations is None:
        blockers.append("INVARIANT_VIOLATIONS_UNAVAILABLE")
    elif invariant_violations:
        blockers.append("INVARIANT_VIOLATIONS")
    if missed_risk_events is None:
        blockers.append("MISSED_RISK_EVENTS_UNAVAILABLE")
    elif missed_risk_events:
        blockers.append("MISSED_RISK_EVENTS")
    return {"days_covered": days_covered, "days_required": STAGE_B_MIN_DAYS,
            "weekends_covered": weekends_covered, "weekends_required": STAGE_B_MIN_WEEKENDS,
            "unexplained_ledger_diffs": unexplained_ledger_diffs,
            "invariant_violations": invariant_violations,
            "missed_risk_events": missed_risk_events, "passed": not blockers, "blockers": blockers}

def _journal_amount(value):
    if value is None:
        return Decimal(0)
    try:
        return Decimal(str(value).strip())
    except Exception:
        return Decimal(0)

def audit_unexplained_ledger_diffs(conn):
    # Reference model of the queried evidence and balance arithmetic. The
    # --repo variant also includes the repository's exception handling.
    rows = conn.execute("SELECT event_id, account_debit, account_credit, amount_raw FROM rh_journal").fetchall()
    if not rows:
        return {"count": None, "reason": "NO_JOURNAL_EVIDENCE"}
    entries = {}
    for idx, (eid, debit, credit, amount) in enumerate(rows):
        entries.setdefault(eid or f"__row__{idx}", []).append((debit, credit, amount))
    count = 0
    for legs in entries.values():
        debits = credits = Decimal(0)
        empty = False
        for debit, credit, amount_raw in legs:
            if not debit or not credit:
                empty = True
            amount = _journal_amount(amount_raw)
            if debit:
                debits += amount
            if credit:
                credits += amount
        if empty or debits != credits:
            count += 1
    return {"count": count}

def column_stats(conn, table):
    # The selected readiness function uses this result only for column names.
    return [{"column": r[1]} for r in conn.execute(f"PRAGMA table_info({table})")]

def audit_key_field_health(conn, *, asset_address):
    columns = {}
    total = conn.execute("SELECT COUNT(*) FROM rh_market_states WHERE asset_address=?", (asset_address,)).fetchone()[0]
    all_ok = total > 0
    for col in STAGE_A_KEY_COLUMNS:
        first_time = conn.execute(f'SELECT MIN(sample_time) FROM rh_market_states WHERE asset_address=? AND "{col}" IS NOT NULL', (asset_address,)).fetchone()[0]
        if first_time is None:
            all_ok = False
            columns[col] = {"passed": False}
            continue
        n, valid = conn.execute(f'SELECT COUNT(*), COUNT("{col}") FROM rh_market_states WHERE asset_address=? AND sample_time >= ?', (asset_address, first_time)).fetchone()
        ratio = Decimal(valid) / Decimal(n)
        ok = ratio >= STAGE_A_KEY_COLUMNS_MIN_RATIO
        all_ok = all_ok and ok
        columns[col] = {"passed": ok, "non_null_ratio": ratio, "window_rows": n, "total_rows": total}
    return {"passed": all_ok, "columns": columns}

def build_verdict(state, full_test, fault_injection, code_version, working_tree_clean, db_path, generated_at):
    # Reduced reference of the final-state decision and the failed-test reasons.
    reasons = []
    if full_test:
        if full_test.get("failed") and full_test["failed"] > 0:
            reasons.append(f"FULL_TEST_FAILED: {full_test['failed']} failures")
        if full_test.get("exit_code") != 0:
            reasons.append(f"FULL_TEST_NONZERO_EXIT: {full_test.get('exit_code')}")
    a = (state.get("stage_a") or {}).get("passed") is True
    b = (state.get("stage_b") or {}).get("passed") is True
    return {"verdict": "SHADOW_COMPLETE" if a and b else "STAGE_A_PASSED" if a else "NOT_GRADUATED",
            "verdict_reasons": reasons, "tiny_live_authorized": False}

EXTRACTIONS = {
    "scripts/lp_rh_bucket_ledger_v1_readonly.py": ["_require_decimal", "_to_decimal_text", "bucket_budget", "bucket_active_cap", "reserved_total", "try_reserve", "release"],
    "scripts/lp_rh_shadow_daemon_v1_readonly.py": ["_copy_new_rows"],
    "scripts/lp_rh_readiness_v1_readonly.py": ["_to_datetime", "_day_start", "audit_weekends_covered", "stage_b_status", "_journal_amount", "audit_unexplained_ledger_diffs", "audit_key_field_health"],
    "scripts/lp_rh_graduation_evidence_v1.py": ["build_verdict"],
}

def load_repo_functions(repo, allow_other_head=False):
    """AST extraction only: excludes application imports and top-level calls."""
    proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, capture_output=True, timeout=10, check=True)
    head = proc.stdout.strip()
    if head != PIN and not allow_other_head:
        raise ValueError(f"Expected pinned commit {PIN}, got {head}; use --allow-other-head only for a repair comparison")
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", *EXTRACTIONS], text=True, capture_output=True, timeout=10, check=True)
    if status.stdout.strip() and not allow_other_head:
        raise ValueError("Reviewed source files have local modifications; refusing to label them as the pinned snapshot")
    source_ranges = {}
    for relpath, names in EXTRACTIONS.items():
        text = (repo / relpath).read_text(encoding="utf-8")
        tree = ast.parse(text, filename=relpath)
        selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        if {n.name for n in selected} != set(names):
            raise ValueError(f"Required functions missing in {relpath}")
        future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
        module = ast.fix_missing_locations(ast.Module(body=[future, *selected], type_ignores=[]))
        exec(compile(module, str(repo / relpath), "exec"), globals())
        source_ranges[relpath] = {n.name: [n.lineno, n.end_lineno] for n in selected}
    return {"head": head, "source_ranges": source_ranges, "worktree_source_modified": bool(status.stdout.strip())}

def db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
    CREATE TABLE rh_bucket_reservations (intent_id TEXT PRIMARY KEY, policy_version TEXT NOT NULL,
      bucket TEXT, amount_usd TEXT, status TEXT, created_at TEXT, released_at TEXT);
    CREATE TABLE rh_gate_decisions (decision_id TEXT PRIMARY KEY);
    CREATE TABLE sentinel (id TEXT PRIMARY KEY);
    CREATE TABLE rh_market_states (asset_address TEXT, sample_time TEXT, reference_mid TEXT,
      session TEXT, fee_growth_global_0 TEXT, fee_growth_global_1 TEXT);
    CREATE TABLE rh_journal (event_id TEXT PRIMARY KEY, account_debit TEXT, account_credit TEXT, amount_raw TEXT);
    CREATE TABLE rh_position_marks (position_id TEXT, accrued_fee TEXT);
    CREATE TABLE rh_reconciliation_runs (status TEXT);
    """)
    return conn

def reserve(conn, name):
    return try_reserve(conn, intent_id=name, bucket="CORE", amount_usd=Decimal("1000"), capital_usd=Decimal("10000"), now=NOW)

def probe_reservation_leak():
    with contextlib.closing(db()) as conn:
        conn.execute("INSERT INTO rh_gate_decisions VALUES ('already-observed-sample')")
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        res = reserve(conn, "episode-1")
        try:
            conn.execute("INSERT INTO rh_gate_decisions VALUES ('already-observed-sample')")
        except sqlite3.IntegrityError:
            conn.rollback()
        row = conn.execute("SELECT status FROM rh_bucket_reservations WHERE intent_id='episode-1'").fetchone()
        amount = reserved_total(conn, "CORE", POLICY_ID)
        return row == ("PENDING",), {"grant": res["granted"], "reservation_after_rollback": row, "reserved_usd": str(amount)}

def probe_release_commits_caller():
    with contextlib.closing(db()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO sentinel VALUES ('should-rollback')")
        reserve(conn, "episode-2")
        release(conn, "episode-2", now=NOW, reason="TEST")
        conn.rollback()
        count = conn.execute("SELECT COUNT(*) FROM sentinel").fetchone()[0]
        return count == 1, {"unrelated_caller_write_survived_rollback": count}

def probe_scratch_release_discarded():
    with contextlib.closing(db()) as ledger, contextlib.closing(db()) as scratch:
        reserve(ledger, "episode-3")
        reserve(scratch, "episode-3")
        release(scratch, "episode-3", now=NOW, reason="TEST")
        stats = _copy_new_rows(scratch, ledger)
        ledger.commit()
        row = ledger.execute("SELECT status, released_at FROM rh_bucket_reservations").fetchone()
        return row == ("PENDING", None), {"copy_stats": stats, "ledger_row": row}

def probe_single_sample_weekend():
    with contextlib.closing(db()) as conn:
        conn.execute("INSERT INTO rh_market_states(asset_address,sample_time) VALUES ('pool','2026-09-12T12:00:00Z')")
        result = audit_weekends_covered(conn, asset_address="pool", interval_secs=15)
        return result.get("weekends_covered") == 1, result

def probe_stage_b_no_economics():
    result = stage_b_status(days_covered=14, weekends_covered=1, unexplained_ledger_diffs=0, invariant_violations=0, missed_risk_events=0)
    return result.get("passed") is True, {"all_cost_profit_evidence_supplied": False, "result": result}

def probe_reconciliation_ignored():
    with contextlib.closing(db()) as conn:
        conn.execute("INSERT INTO rh_journal VALUES ('opening-leg','LP_POSITION_TOKEN0','WALLET_TOKEN0','1')")
        conn.execute("INSERT INTO rh_position_marks VALUES ('position','100')")
        conn.execute("INSERT INTO rh_reconciliation_runs VALUES ('UNEXPLAINED_DIFF')")
        result = audit_unexplained_ledger_diffs(conn)
        return result.get("count") == 0, {"marks_accrued_fee": "100", "fee_journal_rows": 0, "reconciliation_status": "UNEXPLAINED_DIFF", "graduation_ledger_probe": result}

def probe_key_field_denominator():
    with contextlib.closing(db()) as conn:
        start = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)
        n = 72 * 3600 // 15 + 1
        rows = []
        for i in range(n):
            timestamp = (start + timedelta(seconds=15*i)).strftime("%Y-%m-%dT%H:%M:%SZ")
            fees = "10" if i == n - 1 else None
            rows.append(("pool", timestamp, "100", "RTH", fees, fees))
        conn.executemany("INSERT INTO rh_market_states VALUES(?,?,?,?,?,?)", rows)
        result = audit_key_field_health(conn, asset_address="pool")
        col = result.get("columns", {}).get("fee_growth_global_0", {})
        return result.get("passed") is True, {"total_rows": n, "fee_populated_rows": 1,
            "actual_fee_valid_fraction": str(Decimal(1)/Decimal(n)), "health_passed": result.get("passed"), "reported_fee_column": col}

def probe_failed_tests_complete():
    result = build_verdict(state={"stage_a": {"passed": True, "blockers": []}, "stage_b": {"passed": True, "blockers": []},
            "live_gate": {"live_allowed": False, "blockers": ["CAPITAL_POLICY_NOT_APPROVED"]}},
        full_test={"passed": 0, "failed": 3, "exit_code": 1},
        fault_injection={"report_present": True, "scenarios_passed": 0, "scenarios_total": 6},
        code_version=PIN, working_tree_clean=True, db_path=":memory:", generated_at=NOW)
    return result.get("verdict") == "SHADOW_COMPLETE", result

PROBES = [
    ("R01_reservation_survives_later_rollback", probe_reservation_leak),
    ("R02_release_commits_unrelated_caller_write", probe_release_commits_caller),
    ("R03_scratch_release_skipped_by_primary_key", probe_scratch_release_discarded),
    ("R04_one_sample_counts_as_weekend", probe_single_sample_weekend),
    ("R05_stage_b_pass_without_economic_evidence", probe_stage_b_no_economics),
    ("R06_reconciliation_failure_ignored", probe_reconciliation_ignored),
    ("R07_missing_key_fields_excluded_from_denominator", probe_key_field_denominator),
    ("R08_failed_tests_still_shadow_complete", probe_failed_tests_complete),
]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, help="AST-extract actual functions from a local checkout instead of the reduced reference models")
    parser.add_argument("--allow-other-head", action="store_true", help="Explicitly permit a changed checkout for repair comparison")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    source = {"mode": "REDUCED_REFERENCE_MODEL", "not_full_repository_tests": True, "pinned_source": PIN}
    try:
        if args.repo:
            source.update(load_repo_functions(args.repo.resolve(), args.allow_other_head))
            source["mode"] = "AST_EXTRACTED_CHECKOUT_FUNCTIONS_WITH_TEST_SHIMS"
        items = []
        for name, probe in PROBES:
            try:
                reproduced, details = probe()
                items.append({"id": name, "status": "DEFECT_REPRODUCED" if reproduced else "NOT_REPRODUCED", "details": details})
            except Exception as exc:
                items.append({"id": name, "status": "PROBE_ERROR", "error": repr(exc)})
        report = {"source": source, "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                  "tests": items, "defects_reproduced": sum(x["status"] == "DEFECT_REPRODUCED" for x in items),
                  "probe_errors": sum(x["status"] == "PROBE_ERROR" for x in items)}
        serialized = json.dumps(report, ensure_ascii=False, indent=2, default=str)
        print(serialized)
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(serialized + "\n", encoding="utf-8")
        return 2 if report["probe_errors"] else 1 if report["defects_reproduced"] else 0
    except Exception as exc:
        print(json.dumps({"status": "PROBE_SETUP_ERROR", "error": repr(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
