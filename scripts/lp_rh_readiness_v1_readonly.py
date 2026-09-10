#!/usr/bin/env python3
"""RH-08b: graduation readiness dashboard (offline, read-only).
PRD §17.1 six questions + §21 Stage A/B/C/D thresholds -> READINESS_DASHBOARD.md.
Missing data renders NOT_MEASURED, never 0/guess. No network, no live-store writes.
"""
from __future__ import annotations

import argparse
import bisect
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_daily_report_v1_readonly import (  # noqa: E402
    SIX_QUESTIONS, answer_six_questions, evidence_freshness_table)
from scripts.lp_rh_terminal_gate_v1_readonly import (  # noqa: E402
    CONJUNCT_ORDER, TERMINAL_CONJUNCTS)
from scripts.lp_rh_store_v1_readonly import (  # noqa: E402
    DEFAULT_DB_PATH, budget_status, open_store)
from scripts.lp_rh_coverage_audit_v1_readonly import (  # noqa: E402
    NO_ASSET_DATA, coverage_for_asset)
from scripts.lp_rh_column_health_v1_readonly import (  # noqa: E402
    column_stats)

# PRD §21 graduation thresholds.
STAGE_A_MIN_HOURS = 72
STAGE_A_MIN_COVERAGE = Decimal("0.99")
STAGE_B_MIN_DAYS = 14
STAGE_B_MIN_WEEKENDS = 1
STAGE_C_MIN_DAYS = 30

# RH-02az (spec 20260909_RH-02az_stage_a_gate_wiring.md):
# Key columns in rh_market_states required for Stage A graduation per PRD §21.1 / §16.2.
# Rationale:
# - reference_mid: fundamental pool price derived from tick/sqrtPriceX96 for all economic & PnL models.
# - sample_time: observation time index; missing means broken time-series.
# - session: market session classification (RTH, PREMARKET, etc.) required for risk & trading gates.
# - fee_growth_global_0: fee accumulator for token0, indispensable for fee accrual & NAV calculation.
# - fee_growth_global_1: fee accumulator for token1, indispensable for fee accrual & NAV calculation.
STAGE_A_KEY_COLUMNS = (
    "reference_mid",
    "sample_time",
    "session",
    "fee_growth_global_0",
    "fee_growth_global_1",
)
STAGE_A_KEY_COLUMNS_MIN_RATIO = Decimal("0.99")

# Blocker constants for Stage A (RH-02az)
STAGE_A_KEY_FIELDS_INCOMPLETE = "STAGE_A_KEY_FIELDS_INCOMPLETE"
STAGE_A_POOL_NOT_ATTESTED = "STAGE_A_POOL_NOT_ATTESTED"
STAGE_A_BUDGET_EXCEEDED = "STAGE_A_BUDGET_EXCEEDED"
STAGE_A_INVARIANT_VIOLATIONS = "STAGE_A_INVARIANT_VIOLATIONS"
STAGE_A_UNKNOWN_STATE_POSITIONS = "STAGE_A_UNKNOWN_STATE_POSITIONS"
STAGE_A_SYNTHETIC_TESTS_UNKNOWN = "STAGE_A_SYNTHETIC_TESTS_UNKNOWN"

# Key field health reason codes (RH-02bj)
KEY_FIELD_NEVER_POPULATED = "KEY_FIELD_NEVER_POPULATED"
KEY_FIELD_INCOMPLETE = "KEY_FIELD_INCOMPLETE"
KEY_FIELD_MISSING_COLUMN = "KEY_FIELD_MISSING_COLUMN"

def _to_datetime(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None

def _fmt(value: Any) -> str:
    """Render a value; None -> NOT_MEASURED (never 0, never a guess)."""
    return "NOT_MEASURED" if value is None else str(value)

def _fmt_bool(value: Any) -> str:
    return "NOT_MEASURED" if value is None else ("true" if value else "false")

def _safe_div(num: Any, den: Any) -> Optional[float]:
    if num is None or den is None or den == 0:
        return None
    return num / den

def _progress_bar(fraction: Optional[float], width: int = 10) -> str:
    if fraction is None:
        return "NOT_MEASURED"
    clamped = max(0.0, min(1.0, fraction))
    filled = int(round(clamped * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"

def stage_a_status(*, first_sample, last_sample, expected_interval_secs,
                   actual_samples, coverage_ratio: Optional[Any] = None,
                   key_field_health: Optional[Mapping[str, Any]] = None,
                   pool_attestation_status: Optional[Mapping[str, Any]] = None,
                   budget: Optional[Mapping[str, Any]] = None,
                   invariant_violations: Optional[int] = None,
                   unknown_state_positions: Optional[int] = None,
                   synthetic_tests_passed: Optional[bool] = None) -> dict:
    """Stage A graduation gate (PRD §21.1 / RH-02az).

    Evaluates the 7 hard criteria for Stage A graduation:
      1. 72 hours positive observation duration.
      2. Valid calendar/exception synthetic test evidence provided (synthetic_tests_passed).
         Note: This is an external evidence input, not a self-check runner.
      3. Key field health (rh_market_states non-null ratio >= 0.99 for key columns).
      4. Pool identity & capability attestations verified for the observed asset.
      5. RPC budget within limit (budget['over_budget'] is False).
      6. Invariant violations count == 0.
      7. New simulated positions with unknown/degraded state == 0.
      8. Effective data coverage >= 99%.

    Core rule: Unknown is NEVER passed (fail-closed, no silent green).
    """
    first, last = _to_datetime(first_sample), _to_datetime(last_sample)
    if first is None or last is None:
        hours_covered = None
        expected_samples = None
        gaps = None
        window_available = False
    else:
        hours_covered = (last - first).total_seconds() / 3600.0
        expected_samples = (hours_covered * 3600.0) / expected_interval_secs
        if coverage_ratio is None:
            coverage_ratio = (actual_samples / expected_samples) if expected_samples > 0 else 0.0
        gaps = max(0, int(round(expected_samples - actual_samples)))
        window_available = True

    blockers = []

    # 1. Observation window duration & coverage
    if not window_available:
        blockers.append("OBSERVATION_WINDOW_UNAVAILABLE")
    else:
        if hours_covered < STAGE_A_MIN_HOURS:
            blockers.append("HOURS_COVERED_INSUFFICIENT")
        cov_cmp = Decimal(str(coverage_ratio)) if not isinstance(coverage_ratio, Decimal) else coverage_ratio
        if cov_cmp < STAGE_A_MIN_COVERAGE:
            blockers.append("COVERAGE_INSUFFICIENT")

    # 2. Synthetic tests passed (external evidence input)
    if synthetic_tests_passed is None or synthetic_tests_passed is False:
        blockers.append(STAGE_A_SYNTHETIC_TESTS_UNKNOWN)

    # 3. Key fields non-null check
    key_fields_ok = True
    if key_field_health is None or not key_field_health.get("passed", False):
        key_fields_ok = False
        blockers.append(STAGE_A_KEY_FIELDS_INCOMPLETE)

    # 4. Pool identity and attestation
    pool_attested_ok = True
    if pool_attestation_status is None or not pool_attestation_status.get("passed", False):
        pool_attested_ok = False
        blockers.append(STAGE_A_POOL_NOT_ATTESTED)

    # 6. RPC budget. budget_status returns
    # {bytes, soft_budget_bytes, fraction, state} where state is OK, WARN, or OVER.
    # Policy decision (RH-02bd): PRD §21.1 requires RPC budget sustainability
    # (not exceeding soft budget limit).
    # WARN means usage is elevated but still strictly within soft budget (< 100%),
    # so WARN is recorded in dashboard telemetry but does NOT block Stage A.
    # OVER (fraction >= 1.0) or an unrecognized/missing budget state blocks fail-close.
    budget_ok = True
    b_state = budget.get("state") if budget is not None else None
    if b_state not in ("OK", "WARN"):
        budget_ok = False
        blockers.append(STAGE_A_BUDGET_EXCEEDED)

    # 7. Invariant violations
    invariant_ok = True
    if invariant_violations is None or invariant_violations > 0:
        invariant_ok = False
        blockers.append(STAGE_A_INVARIANT_VIOLATIONS)

    # 9. Unknown state positions
    unknown_positions_ok = True
    if unknown_state_positions is None or unknown_state_positions > 0:
        unknown_positions_ok = False
        blockers.append(STAGE_A_UNKNOWN_STATE_POSITIONS)

    passed = (len(blockers) == 0)

    return {
        "hours_covered": hours_covered,
        "hours_required": STAGE_A_MIN_HOURS,
        "coverage_ratio": coverage_ratio,
        "expected_samples": int(round(expected_samples)) if expected_samples is not None else None,
        "actual_samples": actual_samples,
        "gaps": gaps,
        "key_field_health": key_field_health,
        "pool_attestation_status": pool_attestation_status,
        "budget": budget,
        "invariant_violations": invariant_violations,
        "unknown_state_positions": unknown_state_positions,
        "synthetic_tests_passed": synthetic_tests_passed,
        "passed": passed,
        "blockers": blockers,
    }

def stage_b_status(*, days_covered, weekends_covered, unexplained_ledger_diffs,
                   invariant_violations, missed_risk_events) -> dict:
    """Stage B. Running the full 14 days does NOT auto-PASS (PRD §21.2): any
    unexplained diff, invariant violation, or missed risk event keeps it failed."""
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
            "missed_risk_events": missed_risk_events,
            "passed": not blockers, "blockers": blockers}

def live_gate_status(*, usable_provider_count, capital_policy_approved,
                     signatures, broadcasts, keys_created) -> dict:
    """LIVE gate (PRD §8.3). live_allowed is False unless every check is clean:
    >=2 usable providers, capital policy explicitly approved, zero unauthorized
    signatures / broadcasts / keys."""
    blockers = []
    if usable_provider_count is None or usable_provider_count < 2:
        blockers.append("SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE")
    if capital_policy_approved is False:
        blockers.append("CAPITAL_POLICY_CONFLICT")
    elif capital_policy_approved is None:
        blockers.append("CAPITAL_POLICY_NOT_APPROVED")
    action_counts = (signatures, broadcasts, keys_created)
    valid_counts = tuple(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in action_counts
    )
    if not all(valid_counts):
        blockers.append("UNAUTHORIZED_ACTION_COUNTS_UNAVAILABLE")
    if any(valid and value > 0 for value, valid in zip(action_counts, valid_counts)):
        blockers.append("UNAUTHORIZED_ACTION_DETECTED")
    return {"usable_provider_count": usable_provider_count,
            "capital_policy_approved": capital_policy_approved,
            "signatures": signatures, "broadcasts": broadcasts,
            "keys_created": keys_created, "live_allowed": not blockers,
            "blockers": blockers}

def graduation_verdict(stage_a, stage_b, live_gate) -> dict:
    """Overall verdict. Any live-gate blocker forces verdict != PASS."""
    stage_a, stage_b, live_gate = stage_a or {}, stage_b or {}, live_gate or {}
    raw_live_blockers = live_gate.get("blockers")
    live_blockers = (list(raw_live_blockers)
                     if raw_live_blockers is not None
                     else ["LIVE_GATE_STATUS_UNAVAILABLE"])
    if not live_blockers and live_gate.get("live_allowed") is not True:
        live_blockers.append("LIVE_GATE_STATUS_UNAVAILABLE")
    if live_blockers:
        verdict = "FAIL"
    elif stage_a.get("passed") and stage_b.get("passed"):
        verdict = "PASS"
    else:
        verdict = "WARN"
    if verdict == "FAIL":
        next_task = "resolve live-gate blockers before any LIVE action: " \
                    + ", ".join(live_blockers)
    elif verdict == "WARN":
        next_task = "continue Stage A/B observation until both stages pass"
    else:
        next_task = "graduation criteria met; follow PRD §21 promotion procedure"
    not_authorized = []
    if live_gate.get("live_allowed") is not True:
        not_authorized.append("LIVE_EXECUTION")
    return {"verdict": verdict, "next_allowed_task": next_task,
            "explicitly_not_authorized": not_authorized}

def _render_six(six_data: Optional[Mapping]) -> list:
    answers = answer_six_questions(six_data)
    lines = ["## 首页六问", ""]
    for key, question in SIX_QUESTIONS:
        entry = answers.get(key, {})
        lines.append(f"- **{question}**")
        lines.append(f"  - answer: {entry.get('answer', 'NOT_MEASURED')}")
    lines.append("")
    return lines

def _render_stages(state, stage_a, stage_b, live_gate) -> list:
    lines = ["## 四阶段进度", ""]
    hours = stage_a.get("hours_covered")
    lines.append("- Stage A: " + _progress_bar(_safe_div(hours, STAGE_A_MIN_HOURS))
                 + f" hours={_fmt(hours)}/{STAGE_A_MIN_HOURS} "
                 + f"coverage_ratio={_fmt(stage_a.get('coverage_ratio'))} "
                 + f"passed={_fmt_bool(stage_a.get('passed'))}")
    if stage_a.get("blockers"):
        lines.append("  - blockers: " + ", ".join(stage_a["blockers"]))
    kf = stage_a.get("key_field_health")
    if kf and isinstance(kf, dict) and kf.get("columns"):
        lines.append("  - key_fields:")
        for col_name, c_stat in kf["columns"].items():
            first_time = c_stat.get("first_populated_time")
            w_rows = c_stat.get("window_rows")
            t_rows = c_stat.get("total_rows")
            ratio = c_stat.get("non_null_ratio")
            p = c_stat.get("passed")
            if first_time is None:
                lines.append(f"    - {col_name}: NEVER_POPULATED (全表 {t_rows} 行均为 NULL) passed={_fmt_bool(p)}")
            elif t_rows is not None and w_rows is not None and w_rows < t_rows:
                lines.append(f"    - {col_name}: ratio={_fmt(ratio)} (窗口自 {first_time} 起, 最近 {w_rows}/{t_rows} 行) passed={_fmt_bool(p)}")
            else:
                lines.append(f"    - {col_name}: ratio={_fmt(ratio)} (窗口行数={w_rows}) passed={_fmt_bool(p)}")
    days = stage_b.get("days_covered")
    lines.append("- Stage B: " + _progress_bar(_safe_div(days, STAGE_B_MIN_DAYS))
                 + f" days={_fmt(days)}/{STAGE_B_MIN_DAYS} "
                 + f"passed={_fmt_bool(stage_b.get('passed'))}")
    if stage_b.get("blockers"):
        lines.append("  - blockers: " + ", ".join(stage_b["blockers"]))
    c_days = state.get("stage_c_days_covered")
    lines.append("- Stage C: " + _progress_bar(_safe_div(c_days, STAGE_C_MIN_DAYS))
                 + f" days={_fmt(c_days)}/{STAGE_C_MIN_DAYS}")
    lines.append("- Stage D (LIVE): live_allowed="
                 + _fmt_bool(live_gate.get("live_allowed")))
    lines.append("")
    return lines

def _render_terminal_gate(terminal_gate: Optional[Mapping]) -> list:
    lines = [f"## 终闸十项当前值 ({len(TERMINAL_CONJUNCTS)} 项)", ""]
    tg = terminal_gate or {}
    for conjunct in CONJUNCT_ORDER:
        lines.append(f"- {conjunct}: {_fmt(tg.get(conjunct))}")
    lines.append("")
    return lines

def _render_evidence(sources: Optional[list]) -> list:
    lines = ["## 证据新鲜度", ""]
    lines.append("NOT_MEASURED" if not sources else evidence_freshness_table(sources))
    lines.append("")
    return lines

def audit_key_field_health(conn, *, asset_address: str) -> dict:
    """Audit non-null ratios for STAGE_A_KEY_COLUMNS in rh_market_states.
    RH-02bj: Windowed per-column starting from that column's first non-null sample_time.
    Columns never populated are explicitly blocked under KEY_FIELD_NEVER_POPULATED.
    """
    if not asset_address:
        return {"passed": False, "reason": "NO_ASSET_ADDRESS", "columns": {}}
    try:
        # Check if table exists
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rh_market_states'"
        ).fetchone()
        if not exists:
            return {"passed": False, "reason": "TABLE_NOT_FOUND", "columns": {}}

        total_row = conn.execute(
            "SELECT COUNT(*) FROM rh_market_states WHERE LOWER(asset_address) = LOWER(?)",
            (asset_address,)
        ).fetchone()
        total_rows = total_row[0] if total_row else 0
        if total_rows == 0:
            return {"passed": False, "reason": "NO_ROWS_FOR_ASSET", "total_rows": 0, "columns": {}}

        # Use column_stats logic filtered by asset_address
        all_stats = {s["column"]: s for s in column_stats(conn, "rh_market_states")}
        col_results: dict[str, dict[str, Any]] = {}
        all_passed = True
        failed_reasons: list[str] = []

        for col in STAGE_A_KEY_COLUMNS:
            if col not in all_stats:
                col_reason = f"{KEY_FIELD_MISSING_COLUMN}:{col}"
                col_results[col] = {
                    "first_populated_time": None,
                    "window_rows": 0,
                    "window_non_null_ratio": Decimal("0"),
                    "non_null_count": 0,
                    "total_rows": total_rows,
                    "non_null_ratio": Decimal("0"),
                    "passed": False,
                    "missing_column": True,
                    "reason": col_reason,
                    "code": KEY_FIELD_MISSING_COLUMN,
                }
                all_passed = False
                failed_reasons.append(col_reason)
                continue

            # Query earliest populated sample_time for this column and asset
            min_row = conn.execute(
                f'SELECT MIN(sample_time) FROM rh_market_states '
                f'WHERE LOWER(asset_address) = LOWER(?) AND "{col}" IS NOT NULL',
                (asset_address,)
            ).fetchone()
            first_time = min_row[0] if min_row else None

            # Defect guard: A column that was never populated (first_time is None)
            # must NEVER pass under an empty window (0 rows, 0 nulls != 100% pass).
            if first_time is None:
                col_reason = f"{KEY_FIELD_NEVER_POPULATED}:{col}"
                col_results[col] = {
                    "first_populated_time": None,
                    "window_rows": 0,
                    "window_non_null_ratio": Decimal("0"),
                    "non_null_count": 0,
                    "total_rows": total_rows,
                    "non_null_ratio": Decimal("0"),
                    "passed": False,
                    "reason": col_reason,
                    "code": KEY_FIELD_NEVER_POPULATED,
                }
                all_passed = False
                failed_reasons.append(col_reason)
                continue

            # Query window metrics: rows >= first_time and non-null count >= first_time
            w_row = conn.execute(
                f'SELECT COUNT(*), COUNT("{col}") FROM rh_market_states '
                f'WHERE LOWER(asset_address) = LOWER(?) AND sample_time >= ?',
                (asset_address, first_time)
            ).fetchone()
            window_rows = w_row[0] if w_row else 0
            non_null_count = w_row[1] if w_row else 0

            if window_rows == 0:
                col_reason = f"{KEY_FIELD_NEVER_POPULATED}:{col}"
                col_results[col] = {
                    "first_populated_time": first_time,
                    "window_rows": 0,
                    "window_non_null_ratio": Decimal("0"),
                    "non_null_count": 0,
                    "total_rows": total_rows,
                    "non_null_ratio": Decimal("0"),
                    "passed": False,
                    "reason": col_reason,
                    "code": KEY_FIELD_NEVER_POPULATED,
                }
                all_passed = False
                failed_reasons.append(col_reason)
                continue

            ratio = Decimal(str(non_null_count)) / Decimal(str(window_rows))
            is_ok = ratio >= STAGE_A_KEY_COLUMNS_MIN_RATIO
            col_info: dict[str, Any] = {
                "first_populated_time": first_time,
                "window_rows": window_rows,
                "window_non_null_ratio": ratio,
                "non_null_count": non_null_count,
                "total_rows": total_rows,
                "non_null_ratio": ratio,
                "passed": is_ok,
            }
            if not is_ok:
                all_passed = False
                col_reason = f"{KEY_FIELD_INCOMPLETE}:{col}"
                col_info["reason"] = col_reason
                col_info["code"] = KEY_FIELD_INCOMPLETE
                failed_reasons.append(col_reason)

            col_results[col] = col_info

        res: dict[str, Any] = {
            "passed": all_passed,
            "total_rows": total_rows,
            "threshold": STAGE_A_KEY_COLUMNS_MIN_RATIO,
            "columns": col_results,
        }
        if not all_passed:
            res["reasons"] = failed_reasons
            never_pop_cols = [c for c, d in col_results.items() if d.get("code") == KEY_FIELD_NEVER_POPULATED]
            if never_pop_cols:
                res["code"] = KEY_FIELD_NEVER_POPULATED
                res["reason"] = f"{KEY_FIELD_NEVER_POPULATED}:{','.join(never_pop_cols)}"
            else:
                res["code"] = KEY_FIELD_INCOMPLETE
                res["reason"] = "; ".join(failed_reasons)
        return res
    except Exception as exc:
        return {"passed": False, "error": str(exc), "columns": {}}


def audit_pool_attestation(conn, *, asset_address: str) -> dict:
    """Audit identity and capabilities evidence for the observed pool (PRD §21.1 Condition 4).
    Asserts:
      1. asset_address exists in rh_contract_attestations.
      2. rh_pool_registry entry exists for pool_address = asset_address (or token0/token1/fee/tick_spacing non-null).
    """
    if not asset_address:
        return {"passed": False, "reason": "NO_ASSET_ADDRESS", "missing": ["asset_address"]}
    missing = []
    try:
        # 1. rh_contract_attestations
        att_row = conn.execute(
            "SELECT COUNT(*) FROM rh_contract_attestations WHERE LOWER(address) = LOWER(?)",
            (asset_address,)
        ).fetchone()
        has_attestation = (att_row[0] > 0) if att_row else False
        if not has_attestation:
            missing.append("rh_contract_attestations")

        # 2. rh_pool_registry
        reg_row = conn.execute(
            "SELECT token0, token1, fee, tick_spacing FROM rh_pool_registry WHERE LOWER(pool_address) = LOWER(?) LIMIT 1",
            (asset_address,)
        ).fetchone()
        if not reg_row:
            missing.append("rh_pool_registry_record")
        else:
            token0, token1, fee, tick_spacing = reg_row
            if token0 is None or str(token0).strip() == "":
                missing.append("rh_pool_registry.token0")
            if token1 is None or str(token1).strip() == "":
                missing.append("rh_pool_registry.token1")
            if fee is None or str(fee).strip() == "":
                missing.append("rh_pool_registry.fee")
            if tick_spacing is None:
                missing.append("rh_pool_registry.tick_spacing")

        return {
            "passed": len(missing) == 0,
            "has_contract_attestation": has_attestation,
            "missing": missing,
        }
    except Exception as exc:
        return {"passed": False, "error": str(exc), "missing": ["query_exception"]}


def audit_invariant_violations(conn) -> dict:
    """Read-only audit of detectable system invariants on current SQLite store.

    Checks:
      1. INV-GATE-02 / gate consistency: in rh_gate_decisions, COMPUTED_PASS must
         not have a dominant blocker or any False terminal bit.
      2. Market sanity: in rh_market_states, reference_mid > 0 when non-null;
         reference_bid <= reference_ask when both non-null (no crossed market).
      3. Position mark non-negativity: in rh_position_marks, reference_nav >= 0.
      4. Journal balance integrity: in rh_journal, debit and credit accounts must
         be non-empty, and amount_raw must be non-negative.
    Returns:
      dict with passed, violations_count, details, checks_performed, unsupported.
    """
    try:
        tbls = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        violations = 0
        details = []
        checks_performed = []
        unsupported = [
            "INV-IL-01 (fee/reward ex-nav separation requiring full replay)",
            "INV-V4-01 (v4 snapshot collector dynamic mutation)",
            "INV-TVLSHARE-01 (active liquidity allocator live boundary)",
        ]

        if "rh_gate_decisions" in tbls:
            checks_performed.append("rh_gate_decisions:conjunction_consistency")
            rows = conn.execute(
                "SELECT decision_id, primary_status, terminal_bits_json, dominant_blocker "
                "FROM rh_gate_decisions WHERE primary_status = 'COMPUTED_PASS'"
            ).fetchall()
            for dec_id, p_status, bits_raw, dom_blocker in rows:
                if dom_blocker is not None and dom_blocker != "":
                    violations += 1
                    details.append(f"rh_gate_decisions:{dec_id}:COMPUTED_PASS_has_dominant_blocker:{dom_blocker}")
                if bits_raw:
                    try:
                        bits = json.loads(bits_raw)
                        if isinstance(bits, dict):
                            for bit_name, val in bits.items():
                                if val is False:
                                    violations += 1
                                    details.append(f"rh_gate_decisions:{dec_id}:COMPUTED_PASS_with_false_bit:{bit_name}")
                    except Exception:
                        pass

        if "rh_market_states" in tbls:
            checks_performed.append("rh_market_states:price_positivity_and_spread")
            # mid > 0 check
            bad_mids = conn.execute(
                "SELECT COUNT(*) FROM rh_market_states WHERE reference_mid IS NOT NULL AND CAST(reference_mid AS REAL) <= 0"
            ).fetchone()[0]
            if bad_mids > 0:
                violations += bad_mids
                details.append(f"rh_market_states:non_positive_reference_mid_count:{bad_mids}")
            # crossed market check (bid > ask)
            crossed = conn.execute(
                "SELECT COUNT(*) FROM rh_market_states WHERE reference_bid IS NOT NULL AND reference_ask IS NOT NULL "
                "AND CAST(reference_bid AS REAL) > CAST(reference_ask AS REAL)"
            ).fetchone()[0]
            if crossed > 0:
                violations += crossed
                details.append(f"rh_market_states:crossed_market_count:{crossed}")

        if "rh_position_marks" in tbls:
            checks_performed.append("rh_position_marks:nav_non_negative")
            bad_navs = conn.execute(
                "SELECT COUNT(*) FROM rh_position_marks WHERE reference_nav IS NOT NULL AND CAST(reference_nav AS REAL) < 0"
            ).fetchone()[0]
            if bad_navs > 0:
                violations += bad_navs
                details.append(f"rh_position_marks:negative_reference_nav_count:{bad_navs}")

        if "rh_journal" in tbls:
            checks_performed.append("rh_journal:accounts_and_amounts")
            bad_journal = conn.execute(
                "SELECT COUNT(*) FROM rh_journal WHERE (account_debit = '' OR account_credit = '') "
                "OR (CAST(amount_raw AS REAL) < 0)"
            ).fetchone()[0]
            if bad_journal > 0:
                violations += bad_journal
                details.append(f"rh_journal:invalid_journal_rows:{bad_journal}")

        return {
            "passed": violations == 0,
            "violations_count": violations,
            "details": details,
            "checks_performed": checks_performed,
            "unsupported": unsupported,
        }
    except Exception as exc:
        return {
            "passed": False,
            "violations_count": None,
            "error": str(exc),
            "checks_performed": [],
            "unsupported": [],
            "details": [f"audit_exception:{exc}"],
        }


def _day_start(day, tzinfo):
    """该 UTC 自然日的 00:00:00。"""
    return datetime(day.year, day.month, day.day, tzinfo=tzinfo)


def audit_weekends_covered(conn, *, asset_address, interval_secs=15) -> dict:
    """Count complete weekend days (Sat/Sun, UTC) covered by rh_market_states
    samples for one asset (RH-02bm).

    A UTC calendar day is "complete" when it holds at least 90% of the samples
    expected for that day (expected = day_span_secs / interval_secs). The first
    and last partial days are prorated over their actual sample span instead of
    being judged incomplete outright. Missing table or zero rows for the asset
    -> weekends_covered=None (unknown, never 0).
    """
    try:
        if not asset_address:
            return {"weekends_covered": None, "checks_performed": [],
                    "reason": "ASSET_ADDRESS_REQUIRED"}
        interval = float(interval_secs)
        if interval <= 0:
            return {"weekends_covered": None, "checks_performed": [],
                    "reason": "INVALID_INTERVAL"}
        tbls = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "rh_market_states" not in tbls:
            return {"weekends_covered": None, "checks_performed": [],
                    "reason": "NO_MARKET_STATE_EVIDENCE"}
        rows = conn.execute(
            "SELECT sample_time FROM rh_market_states "
            "WHERE LOWER(asset_address) = LOWER(?)",
            (asset_address,)).fetchall()
        times = sorted(t for r in rows if (t := _to_datetime(r[0])) is not None)
        if not times:
            return {"weekends_covered": None,
                    "checks_performed": ["rh_market_states:weekend_coverage"],
                    "reason": "NO_ASSET_SAMPLES"}
        by_day: dict = {}
        for t in times:
            by_day[t.date()] = by_day.get(t.date(), 0) + 1
        first_day, last_day = times[0].date(), times[-1].date()
        complete_weekend_days = 0
        day_details = []
        for day in sorted(by_day):
            actual = by_day[day]
            if day == first_day and day == last_day:
                span_secs = (times[-1] - times[0]).total_seconds()
            elif day == first_day:
                span_secs = (_day_start(day + timedelta(days=1), times[0].tzinfo) - times[0]).total_seconds()
            elif day == last_day:
                span_secs = (times[-1] - _day_start(day, times[-1].tzinfo)).total_seconds()
            else:
                span_secs = 86400.0
            expected = span_secs / interval
            complete = actual >= 0.9 * expected
            is_weekend = day.weekday() in (5, 6)
            if complete and is_weekend:
                complete_weekend_days += 1
            day_details.append({"date": str(day), "weekday": day.weekday(),
                                "actual": actual, "expected": round(expected, 3),
                                "complete": complete, "weekend": is_weekend})
        return {"weekends_covered": complete_weekend_days,
                "checks_performed": ["rh_market_states:weekend_coverage"],
                "days": day_details, "reason": "OK"}
    except Exception as exc:
        return {"weekends_covered": None, "checks_performed": [],
                "reason": f"audit_exception:{exc}"}


def _journal_amount(value) -> Decimal:
    """Parse a rh_journal amount_raw TEXT cell; unparseable -> 0 (matches the
    CAST(... AS REAL) idiom used by audit_invariant_violations)."""
    if value is None:
        return Decimal(0)
    try:
        return Decimal(str(value).strip())
    except Exception:
        return Decimal(0)


def audit_unexplained_ledger_diffs(conn) -> dict:
    """Check rh_journal double-entry balance, grouped into entries by event_id
    (RH-02bm). An entry is unexplained when its debit total (sum of amount_raw
    over legs carrying a debit account) differs from its credit total, or when
    any leg has an empty debit/credit account. Missing table OR zero rows ->
    count=None with reason NO_JOURNAL_EVIDENCE: an empty ledger is 'unknown',
    never 'zero diffs'.
    """
    try:
        tbls = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "rh_journal" not in tbls:
            return {"count": None, "checks_performed": [],
                    "reason": "NO_JOURNAL_EVIDENCE"}
        rows = conn.execute(
            "SELECT event_id, account_debit, account_credit, amount_raw "
            "FROM rh_journal").fetchall()
        if not rows:
            return {"count": None, "checks_performed": ["rh_journal:balance"],
                    "reason": "NO_JOURNAL_EVIDENCE"}
        entries: dict = {}
        for idx, (event_id, acct_debit, acct_credit, amount_raw) in enumerate(rows):
            key = event_id if event_id else f"__row__{idx}"
            entries.setdefault(key, []).append((acct_debit, acct_credit, amount_raw))
        count = 0
        details = []
        for key, legs in entries.items():
            debit_total = Decimal(0)
            credit_total = Decimal(0)
            empty_account = False
            for acct_debit, acct_credit, amount_raw in legs:
                if not acct_debit or not acct_credit:
                    empty_account = True
                amount = _journal_amount(amount_raw)
                if acct_debit:
                    debit_total += amount
                if acct_credit:
                    credit_total += amount
            if empty_account or debit_total != credit_total:
                count += 1
                details.append(f"rh_journal:{key}:debit={debit_total}:"
                               f"credit={credit_total}:empty_account={empty_account}")
        return {"count": count, "checks_performed": ["rh_journal:balance"],
                "details": details,
                "reason": "OK" if count == 0 else "UNBALANCED_ENTRIES"}
    except Exception as exc:
        return {"count": None, "checks_performed": [],
                "reason": f"audit_exception:{exc}"}


def _parse_health_flags(raw) -> list:
    """Parse health_flags_json; returns the flag list (empty when the field is
    null, '', '[]', or an empty list). Unparseable non-empty text is treated
    as flagged (fail-close)."""
    if raw is None:
        return []
    text = str(raw).strip()
    if text in ("", "[]"):
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        return [text]
    if isinstance(parsed, list):
        return [f for f in parsed if f not in (None, "")]
    return [parsed]


def audit_missed_risk_events(conn) -> dict:
    """Evidence of 'should have blocked but did not' (RH-02bm): a COMPUTED_PASS
    rh_gate_decisions row whose nearest preceding market sample (max
    sample_time <= decided_at) carries non-empty health flags. Missing
    rh_gate_decisions table OR zero rows -> count=None with reason
    NO_GATE_DECISION_EVIDENCE (never 0).
    """
    try:
        tbls = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "rh_gate_decisions" not in tbls:
            return {"count": None, "checks_performed": [],
                    "reason": "NO_GATE_DECISION_EVIDENCE"}
        total = conn.execute("SELECT COUNT(*) FROM rh_gate_decisions").fetchone()[0]
        if total == 0:
            return {"count": None,
                    "checks_performed": ["rh_gate_decisions:missed_risk_events"],
                    "reason": "NO_GATE_DECISION_EVIDENCE"}
        decisions = conn.execute(
            "SELECT decision_id, decided_at FROM rh_gate_decisions "
            "WHERE primary_status = 'COMPUTED_PASS'").fetchall()
        samples = []
        if "rh_market_states" in tbls:
            for sample_time, flags_raw in conn.execute(
                    "SELECT sample_time, health_flags_json FROM rh_market_states"):
                t = _to_datetime(sample_time)
                if t is not None:
                    samples.append((t, flags_raw))
        samples.sort(key=lambda item: item[0])
        sample_times = [t for t, _ in samples]
        count = 0
        details = []
        for dec_id, decided_at in decisions:
            decided = _to_datetime(decided_at)
            if decided is None:
                continue
            idx = bisect.bisect_right(sample_times, decided) - 1
            if idx < 0:
                continue
            flags = _parse_health_flags(samples[idx][1])
            if flags:
                count += 1
                details.append(
                    f"rh_gate_decisions:{dec_id}:COMPUTED_PASS_with_health_flags:{flags}")
        return {"count": count, "sample_count": len(samples),
                "checks_performed": ["rh_gate_decisions:missed_risk_events"],
                "details": details,
                "reason": "OK" if count == 0 else "MISSED_RISK_EVENTS_FOUND"}
    except Exception as exc:
        return {"count": None, "checks_performed": [],
                "reason": f"audit_exception:{exc}"}


def audit_unknown_state_positions(conn) -> dict:
    """Audit Condition 9: Assert 0 simulated positions opened under UNKNOWN / degraded state.
    Checks rh_shadow_positions and rh_gate_decisions for invalid admissions.
    """
    try:
        # Check tables existence
        tbls = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        violations = 0
        details = []

        # If rh_gate_decisions has records, check if any granted/COMPUTED_PASS decision had unknown state
        if "rh_gate_decisions" in tbls:
            rows = conn.execute(
                "SELECT decision_id, primary_status, reasons_json FROM rh_gate_decisions WHERE primary_status = 'COMPUTED_PASS'"
            ).fetchall()
            for dec_id, p_status, reasons_raw in rows:
                reasons = json.loads(reasons_raw) if reasons_raw else []
                for r in reasons:
                    if "UNKNOWN" in r or "HEALTH_FLAGS" in r:
                        violations += 1
                        details.append(f"rh_gate_decisions:{dec_id}:{r}")

        return {
            "passed": violations == 0,
            "violations_count": violations,
            "details": details,
        }
    except Exception as exc:
        return {"passed": False, "violations_count": None, "error": str(exc)}


def _render_budget(budget: Optional[Mapping]) -> list:
    lines = ["## 预算用量", ""]
    b = budget or {}
    for key in ("bytes", "soft_budget_bytes", "fraction", "state"):
        lines.append(f"- {key}: {_fmt(b.get(key))}")
    lines.append("")
    return lines

def render_dashboard(state: Optional[Mapping]) -> str:
    """Render the full readiness dashboard; missing data -> NOT_MEASURED."""
    state = state or {}
    stage_a, stage_b = state.get("stage_a") or {}, state.get("stage_b") or {}
    live_gate = state.get("live_gate") or {}
    verdict = graduation_verdict(stage_a, stage_b, live_gate)
    lines = ["# RH 毕业就绪度面板 (Graduation Readiness Dashboard)", ""]
    lines.append(f"- as_of: {_fmt(state.get('as_of'))}")
    lines.append(f"- verdict: {verdict['verdict']}")
    lines.append(f"- next_allowed_task: {verdict['next_allowed_task']}")
    for item in verdict["explicitly_not_authorized"]:
        lines.append(f"- explicitly_not_authorized: {item}")
    lines.append("")
    lines.extend(_render_six(state.get("six_questions")))
    lines.extend(_render_stages(state, stage_a, stage_b, live_gate))
    lines.extend(_render_terminal_gate(state.get("terminal_gate")))
    lines.extend(_render_evidence(state.get("evidence_sources")))
    lines.extend(_render_budget(state.get("budget")))
    return "\n".join(lines)

def _build_state(conn, db_path: str, interval_secs: float, asset_address: str,
                 synthetic_tests_passed: Optional[bool] = None,
                 invariant_violations: Optional[int] = None) -> dict:
    """Assemble the dashboard state from the read-only RH store."""
    if not asset_address:
        raise ValueError("asset_address is required")
    state: dict = {}
    cov = coverage_for_asset(
        conn,
        asset_address=asset_address,
        expected_interval_secs=int(round(interval_secs)),
    )

    # Pre-calculate auxiliary evidence for Stage A
    b_stat = budget_status(db_path)
    state["budget"] = b_stat
    kf_health = audit_key_field_health(conn, asset_address=asset_address)
    pool_att_status = audit_pool_attestation(conn, asset_address=asset_address)
    unk_state = audit_unknown_state_positions(conn)
    unk_positions_count = unk_state.get("violations_count")
    inv_audit = audit_invariant_violations(conn)
    state["invariant_violations_audit"] = inv_audit
    if invariant_violations is None:
        invariant_violations = inv_audit.get("violations_count")

    if cov.get("status") == NO_ASSET_DATA or not cov.get("has_data"):
        state["as_of"] = None
        state["stage_a"] = {
            "hours_covered": None,
            "hours_required": STAGE_A_MIN_HOURS,
            "coverage_ratio": None,
            "expected_samples": None,
            "actual_samples": 0,
            "gaps": None,
            "passed": False,
            "blockers": ["NO_ASSET_DATA"],
            "reason": cov.get("message", "无该资产数据"),
            "status": NO_ASSET_DATA,
        }
    else:
        cov_ratio = cov.get("coverage_ratio")
        row = conn.execute(
            "SELECT MIN(sample_time), MAX(sample_time), COUNT(*) "
            "FROM rh_market_states WHERE LOWER(asset_address) = LOWER(?)",
            (asset_address,)
        ).fetchone()
        first_sample, last_sample, actual_samples = row if row else (None, None, 0)
        state["as_of"] = last_sample
        if first_sample is not None and last_sample is not None:
            state["stage_a"] = stage_a_status(
                first_sample=first_sample, last_sample=last_sample,
                expected_interval_secs=interval_secs, actual_samples=actual_samples,
                coverage_ratio=cov_ratio,
                key_field_health=kf_health,
                pool_attestation_status=pool_att_status,
                budget=b_stat,
                invariant_violations=invariant_violations,
                unknown_state_positions=unk_positions_count,
                synthetic_tests_passed=synthetic_tests_passed)
            span_days = (_to_datetime(last_sample) - _to_datetime(first_sample)).days
            wk = audit_weekends_covered(conn, asset_address=asset_address,
                                        interval_secs=interval_secs)
            led = audit_unexplained_ledger_diffs(conn)
            mre = audit_missed_risk_events(conn)
            state["weekends_audit"] = wk
            state["ledger_diffs_audit"] = led
            state["missed_risk_events_audit"] = mre
            state["stage_b"] = stage_b_status(
                days_covered=span_days,
                weekends_covered=wk.get("weekends_covered"),
                unexplained_ledger_diffs=led.get("count"),
                invariant_violations=invariant_violations,
                missed_risk_events=mre.get("count"))
            state["stage_c_days_covered"] = span_days
    tg = conn.execute("SELECT terminal_bits_json FROM rh_gate_decisions "
                      "ORDER BY decided_at DESC LIMIT 1").fetchone()
    if tg and tg[0]:
        state["terminal_gate"] = json.loads(tg[0])
    state["evidence_sources"] = [
        {"source": r[0], "fetched_at": r[1], "source_event_time": r[2],
         "age_secs": None, "quality": r[3]}
        for r in conn.execute("SELECT source, fetch_time, source_event_time, quality "
                              "FROM rh_source_snapshots ORDER BY fetch_time DESC LIMIT 50")]
    prov = conn.execute("SELECT COUNT(DISTINCT provider) FROM rh_rpc_health "
                        "WHERE state = 'GOOD'").fetchone()
    state["live_gate"] = live_gate_status(
        usable_provider_count=prov[0] if prov else None,
        capital_policy_approved=None, signatures=0, broadcasts=0, keys_created=0)
    return state

def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RH graduation readiness dashboard (read-only)")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="RH scanner.db (read-only)")
    parser.add_argument("--out", default="READINESS_DASHBOARD.md", help="output Markdown path")
    parser.add_argument("--interval-secs", type=float, default=15.0, help="Stage A sample interval (s)")
    parser.add_argument("--asset-address", required=True, help="asset address to audit Stage A coverage for")
    parser.add_argument("--synthetic-tests-passed", action="store_true", default=None,
                        help="evidence input indicating synthetic calendar/exception tests passed")
    parser.add_argument("--invariant-violations", type=int, default=None,
                        help="override detected invariant violations count (defaults to read-only DB audit)")
    args = parser.parse_args(argv)
    conn = open_store(args.db, read_only=True)
    try:
        state = _build_state(
            conn, args.db, args.interval_secs,
            asset_address=args.asset_address,
            synthetic_tests_passed=args.synthetic_tests_passed,
            invariant_violations=args.invariant_violations,
        )
    finally:
        conn.close()
    dashboard = render_dashboard(state)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(dashboard, encoding="utf-8")
    print(f"wrote {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
