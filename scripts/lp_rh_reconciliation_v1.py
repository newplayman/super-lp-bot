#!/usr/bin/env python3
"""LP RH Reconciliation runner (RH-RECON-V1).

Reconciles double-entry journal balance (C1), shadow positions opening legs (C2),
and fee accruals (C3). Writes reconciliation runs to rh_reconciliation_runs
when --apply is specified. Fail-close: empty tables or missing samples yield
INSUFFICIENT_EVIDENCE, never PASS.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import decimal
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple
import uuid

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_readiness_v1_readonly import audit_unexplained_ledger_diffs
from scripts.lp_rh_store_v1_readonly import DEFAULT_DB_PATH, insert_row, open_store


def check_c1_double_entry_balance(conn: sqlite3.Connection) -> dict[str, Any]:
    """C1: Check rh_journal double-entry balance via audit_unexplained_ledger_diffs."""
    try:
        journal_count = conn.execute("SELECT COUNT(*) FROM rh_journal").fetchone()[0]
    except Exception:
        journal_count = 0

    audit_res = audit_unexplained_ledger_diffs(conn)
    diff_count = audit_res.get("count")

    if diff_count is None or journal_count == 0:
        return {
            "check": "C1_DOUBLE_ENTRY_BALANCE",
            "has_evidence": False,
            "rows_examined": journal_count,
            "reason": audit_res.get("reason", "NO_JOURNAL_EVIDENCE"),
            "details": audit_res.get("details", []),
            "diff_count": None,
        }

    return {
        "check": "C1_DOUBLE_ENTRY_BALANCE",
        "has_evidence": True,
        "rows_examined": journal_count,
        "reason": audit_res.get("reason", "OK"),
        "details": audit_res.get("details", []),
        "diff_count": diff_count,
    }


def check_c2_opening_legs(conn: sqlite3.Connection) -> dict[str, Any]:
    """C2: Reconcile rh_shadow_positions initial amounts with opening legs in rh_journal."""
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "rh_shadow_positions" not in tables or "rh_journal" not in tables:
            return {
                "check": "C2_OPENING_LEGS",
                "has_evidence": False,
                "rows_examined": 0,
                "reason": "MISSING_TABLES",
                "diff_count": None,
                "diffs": [],
            }

        pos_rows = conn.execute(
            "SELECT position_id, initial_token0_raw, initial_token1_raw "
            "FROM rh_shadow_positions").fetchall()
        if not pos_rows:
            return {
                "check": "C2_OPENING_LEGS",
                "has_evidence": False,
                "rows_examined": 0,
                "reason": "NO_SHADOW_POSITIONS_EVIDENCE",
                "diff_count": None,
                "diffs": [],
            }

        journal_rows = conn.execute(
            "SELECT account_debit, account_credit, amount_raw, ref_json "
            "FROM rh_journal").fetchall()
        if not journal_rows:
            return {
                "check": "C2_OPENING_LEGS",
                "has_evidence": False,
                "rows_examined": len(pos_rows),
                "reason": "NO_JOURNAL_EVIDENCE",
                "diff_count": None,
                "diffs": [],
            }

        journal_by_pos: dict[str, dict[str, Decimal]] = {}
        diffs: list[dict[str, Any]] = []
        with decimal.localcontext(decimal.Context(prec=100)):
            for acct_deb, acct_crd, amt_raw, ref_json in journal_rows:
                if not ref_json:
                    continue
                try:
                    ref = json.loads(ref_json)
                except Exception:
                    continue
                pos_id = ref.get("position_id")
                if not pos_id:
                    continue
                if pos_id not in journal_by_pos:
                    journal_by_pos[pos_id] = {"token0": Decimal(0), "token1": Decimal(0)}

                try:
                    amt = Decimal(str(amt_raw).strip())
                except Exception:
                    amt = Decimal(0)

                if acct_deb == "LP_POSITION_TOKEN0" and acct_crd == "WALLET_TOKEN0":
                    journal_by_pos[pos_id]["token0"] += amt
                elif acct_deb == "LP_POSITION_TOKEN1" and acct_crd == "WALLET_TOKEN1":
                    journal_by_pos[pos_id]["token1"] += amt

            for pos_id, init_t0, init_t1 in pos_rows:
                try:
                    exp_t0 = Decimal(str(init_t0).strip()) if init_t0 is not None else Decimal(0)
                except Exception:
                    exp_t0 = Decimal(0)
                try:
                    exp_t1 = Decimal(str(init_t1).strip()) if init_t1 is not None else Decimal(0)
                except Exception:
                    exp_t1 = Decimal(0)

                act_t0 = journal_by_pos.get(pos_id, {}).get("token0", Decimal(0))
                act_t1 = journal_by_pos.get(pos_id, {}).get("token1", Decimal(0))

                diff_t0 = act_t0 - exp_t0
                diff_t1 = act_t1 - exp_t1

                if diff_t0 != Decimal(0) or diff_t1 != Decimal(0):
                    diffs.append({
                        "position_id": pos_id,
                        "token0": {
                            "journal": str(act_t0),
                            "expected": str(exp_t0),
                            "diff": str(diff_t0),
                        },
                        "token1": {
                            "journal": str(act_t1),
                            "expected": str(exp_t1),
                            "diff": str(diff_t1),
                        },
                    })

        return {
            "check": "C2_OPENING_LEGS",
            "has_evidence": True,
            "rows_examined": len(pos_rows),
            "journal_rows_examined": len(journal_rows),
            "reason": "OK" if not diffs else "OPENING_LEGS_DIFF",
            "diff_count": len(diffs),
            "diffs": diffs,
        }
    except Exception as exc:
        return {
            "check": "C2_OPENING_LEGS",
            "has_evidence": False,
            "rows_examined": 0,
            "reason": f"audit_exception:{exc}",
            "diff_count": None,
            "diffs": [],
        }


def check_c3_fee_accrual(conn: sqlite3.Connection) -> dict[str, Any]:
    """C3: Reconcile rh_journal LP_FEES_RECEIVABLE / LP_FEE_INCOME with position marks accrued_fee."""
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "rh_position_marks" not in tables or "rh_journal" not in tables:
            return {
                "check": "C3_FEE_ACCRUAL",
                "has_evidence": False,
                "rows_examined": 0,
                "reason": "MISSING_TABLES",
                "diff_count": None,
                "details": {},
            }

        mark_count = conn.execute("SELECT COUNT(*) FROM rh_position_marks").fetchone()[0]
        if mark_count == 0:
            return {
                "check": "C3_FEE_ACCRUAL",
                "has_evidence": False,
                "rows_examined": 0,
                "reason": "NO_POSITION_MARKS_EVIDENCE",
                "diff_count": None,
                "details": {},
            }

        fee_journal_rows = conn.execute(
            "SELECT amount_raw FROM rh_journal "
            "WHERE account_debit = 'LP_FEES_RECEIVABLE' AND account_credit = 'LP_FEE_INCOME'"
        ).fetchall()

        mark_rows = conn.execute(
            "SELECT position_id, mark_time, accrued_fee FROM rh_position_marks "
            "ORDER BY mark_time ASC"
        ).fetchall()
        latest_marks: dict[str, Any] = {}
        for pos_id, _mark_time, accrued_fee in mark_rows:
            latest_marks[pos_id] = accrued_fee

        fee_journal_total = Decimal(0)
        marks_fee_total = Decimal(0)
        has_non_zero_accrued = False

        with decimal.localcontext(decimal.Context(prec=100)):
            for (amt_raw,) in fee_journal_rows:
                try:
                    fee_journal_total += Decimal(str(amt_raw).strip())
                except Exception:
                    pass

            for pos_id, accrued_fee in latest_marks.items():
                if accrued_fee is not None and str(accrued_fee).strip() not in ("", "None"):
                    try:
                        f_val = Decimal(str(accrued_fee).strip())
                        marks_fee_total += f_val
                        if f_val != Decimal(0):
                            has_non_zero_accrued = True
                    except Exception:
                        pass

            diff = fee_journal_total - marks_fee_total

        # Fail-close: if no fee journal entries and all marks accrued_fee are zero/NULL -> no sample
        if len(fee_journal_rows) == 0 and not has_non_zero_accrued and marks_fee_total == Decimal(0):
            return {
                "check": "C3_FEE_ACCRUAL",
                "has_evidence": False,
                "rows_examined": mark_count,
                "positions_examined": len(latest_marks),
                "fee_journal_rows_examined": len(fee_journal_rows),
                "reason": "NO_FEE_EVIDENCE: no fee journal entries and accrued_fee is 0/NULL",
                "diff_count": None,
                "details": {},
            }
        has_diff = (diff != Decimal(0))

        details = {
            "fee_journal_total": str(fee_journal_total),
            "marks_fee_total": str(marks_fee_total),
            "diff": str(diff),
            "fee_journal_count": len(fee_journal_rows),
            "positions_with_marks": len(latest_marks),
        }

        return {
            "check": "C3_FEE_ACCRUAL",
            "has_evidence": True,
            "rows_examined": mark_count,
            "positions_examined": len(latest_marks),
            "fee_journal_rows_examined": len(fee_journal_rows),
            "reason": "OK" if not has_diff else "FEE_ACCRUAL_DIFF",
            "diff_count": 1 if has_diff else 0,
            "details": details,
        }
    except Exception as exc:
        return {
            "check": "C3_FEE_ACCRUAL",
            "has_evidence": False,
            "rows_examined": 0,
            "reason": f"audit_exception:{exc}",
            "diff_count": None,
            "details": {},
        }


def _latest_derived_block(conn: sqlite3.Connection) -> Tuple[Optional[str], Optional[int]]:
    """Extract latest derived block hash and number if available in store."""
    try:
        row = conn.execute(
            "SELECT derived_block_hash, derived_block_number FROM rh_position_marks "
            "WHERE derived_block_number IS NOT NULL ORDER BY mark_time DESC LIMIT 1"
        ).fetchone()
        if row and row[0] is not None:
            return str(row[0]), int(row[1])
    except Exception:
        pass
    try:
        row = conn.execute(
            "SELECT block_hash, block_number FROM rh_pool_events "
            "ORDER BY block_number DESC LIMIT 1"
        ).fetchone()
        if row and row[0] is not None:
            return str(row[0]), int(row[1])
    except Exception:
        pass
    return None, None


def run_reconciliation(
    conn: sqlite3.Connection,
    *,
    apply: bool = False,
    now_fn: Optional[Callable[[], str]] = None,
) -> dict[str, Any]:
    """Run all reconciliation checks and optionally persist to rh_reconciliation_runs."""
    get_now = now_fn or (lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    started_at = get_now()

    c1 = check_c1_double_entry_balance(conn)
    c2 = check_c2_opening_legs(conn)
    c3 = check_c3_fee_accrual(conn)

    evidence = {
        "c1": c1,
        "c2": c2,
        "c3": c3,
    }

    # Fail-close verdict decision:
    # 1. Any check lacking samples/evidence -> INSUFFICIENT_EVIDENCE
    if not c1["has_evidence"] or not c2["has_evidence"] or not c3["has_evidence"]:
        verdict = "INSUFFICIENT_EVIDENCE"
        delta: dict[str, Any] = {
            "insufficient_evidence": [
                {"check": c["check"], "reason": c.get("reason", "NO_EVIDENCE")}
                for c in (c1, c2, c3) if not c["has_evidence"]
            ]
        }
    # 2. All checks have evidence; check if any has non-zero diff
    elif (c1.get("diff_count") or 0) > 0 or (c2.get("diff_count") or 0) > 0 or (c3.get("diff_count") or 0) > 0:
        verdict = "UNEXPLAINED_DIFF"
        delta = {}
        if (c1.get("diff_count") or 0) > 0:
            delta["c1_diffs"] = c1.get("details", [])
        if (c2.get("diff_count") or 0) > 0:
            delta["c2_diffs"] = c2.get("diffs", [])
        if (c3.get("diff_count") or 0) > 0:
            delta["c3_diffs"] = c3.get("details", {})
    # 3. All checks have evidence and all differences are zero
    else:
        verdict = "PASS"
        delta = {}

    finished_at = get_now()
    block_hash, block_num = _latest_derived_block(conn)
    run_id = f"rh-recon-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

    if apply:
        row = {
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "evidence_json": json.dumps(evidence, sort_keys=True),
            "delta_json": json.dumps(delta, sort_keys=True),
            "verdict": verdict,
            "derived_block_hash": block_hash,
            "derived_block_number": block_num,
        }
        insert_row(conn, "rh_reconciliation_runs", row)
        conn.commit()

    return {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "verdict": verdict,
        "applied": apply,
        "derived_block_hash": block_hash,
        "derived_block_number": block_num,
        "evidence": evidence,
        "delta": delta,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point for reconciliation runner."""
    parser = argparse.ArgumentParser(description="LP RH Reconciliation Runner")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH),
                        help="Path to SQLite database (default: reports/lp_rh/scanner.db)")
    parser.add_argument("--apply", action="store_true",
                        help="Write reconciliation result to rh_reconciliation_runs (default: dry-run)")
    parser.add_argument("--json", action="store_true",
                        help="Output pure JSON result")
    args = parser.parse_args(argv)

    db_path = Path(args.db).resolve()
    # In dry-run mode, open read-only to guarantee no accidental database mutations
    conn = open_store(db_path, read_only=not args.apply)
    try:
        res = run_reconciliation(conn, apply=args.apply)
    finally:
        conn.close()

    if args.json:
        print(json.dumps(res, indent=2, sort_keys=True))
    else:
        mode = "APPLIED" if args.apply else "DRY-RUN"
        print(f"[{mode}] Reconciliation Run: {res['run_id']}")
        print(f"  Started:  {res['started_at']}")
        print(f"  Finished: {res['finished_at']}")
        print(f"  Verdict:  {res['verdict']}")
        print(f"  Evidence:")
        for k, v in res['evidence'].items():
            print(f"    {k}: check={v.get('check')} evidence={v.get('has_evidence')} "
                  f"rows_examined={v.get('rows_examined')} diff_count={v.get('diff_count')}")
        if res['delta']:
            print(f"  Delta:")
            print(f"    {json.dumps(res['delta'], indent=4, sort_keys=True)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
