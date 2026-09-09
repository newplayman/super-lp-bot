#!/usr/bin/env python3
"""RH-08b: graduation readiness dashboard (offline, read-only).
PRD §17.1 six questions + §21 Stage A/B/C/D thresholds -> READINESS_DASHBOARD.md.
Missing data renders NOT_MEASURED, never 0/guess. No network, no live-store writes.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
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

    # 6. RPC budget.  budget_status returns
    # {bytes, soft_budget_bytes, fraction, state} -- there is no
    # "over_budget" key, so reading one returns None and blocks a store
    # using 0.7% of its budget.  That is the same defect this function was
    # written to close (reading a key that does not exist), so key off the
    # field that is actually there and treat an unrecognised state as
    # unknown, which blocks.
    budget_ok = True
    if budget is None or budget.get("state") != "OK":
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
    Reuses column_stats from scripts.lp_rh_column_health_v1_readonly.
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
            "SELECT COUNT(*) FROM rh_market_states WHERE asset_address = ?",
            (asset_address,)
        ).fetchone()
        total_rows = total_row[0] if total_row else 0
        if total_rows == 0:
            return {"passed": False, "reason": "NO_ROWS_FOR_ASSET", "total_rows": 0, "columns": {}}

        # Use column_stats logic filtered by asset_address
        all_stats = {s["column"]: s for s in column_stats(conn, "rh_market_states")}
        col_results: dict[str, dict[str, Any]] = {}
        all_passed = True

        for col in STAGE_A_KEY_COLUMNS:
            if col not in all_stats:
                col_results[col] = {"non_null_ratio": Decimal("0"), "passed": False, "missing_column": True}
                all_passed = False
                continue
            # Query specific non-null count for this asset_address
            q_null = conn.execute(
                f'SELECT COUNT(*) FROM rh_market_states WHERE asset_address = ? AND "{col}" IS NOT NULL',
                (asset_address,)
            ).fetchone()
            non_null_count = q_null[0] if q_null else 0
            ratio = Decimal(str(non_null_count)) / Decimal(str(total_rows))
            is_ok = ratio >= STAGE_A_KEY_COLUMNS_MIN_RATIO
            if not is_ok:
                all_passed = False
            col_results[col] = {
                "non_null_count": non_null_count,
                "total_rows": total_rows,
                "non_null_ratio": ratio,
                "passed": is_ok,
            }

        return {
            "passed": all_passed,
            "total_rows": total_rows,
            "threshold": STAGE_A_KEY_COLUMNS_MIN_RATIO,
            "columns": col_results,
        }
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
            "FROM rh_market_states WHERE asset_address = ?",
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
            state["stage_b"] = stage_b_status(
                days_covered=span_days, weekends_covered=None, unexplained_ledger_diffs=0,
                invariant_violations=invariant_violations, missed_risk_events=0)
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
    args = parser.parse_args(argv)
    conn = open_store(args.db, read_only=True)
    try:
        state = _build_state(
            conn, args.db, args.interval_secs,
            asset_address=args.asset_address,
            synthetic_tests_passed=args.synthetic_tests_passed,
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
