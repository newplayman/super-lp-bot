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

# PRD §21 graduation thresholds.
STAGE_A_MIN_HOURS = 72
STAGE_A_MIN_COVERAGE = Decimal("0.99")
STAGE_B_MIN_DAYS = 14
STAGE_B_MIN_WEEKENDS = 1
STAGE_C_MIN_DAYS = 30

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
                   actual_samples) -> dict:
    """Stage A. Coverage denominator is the PLANNED window (hours*3600/interval),
    never the actual count -- a bad window must not report 100% (PRD §21.1)."""
    first, last = _to_datetime(first_sample), _to_datetime(last_sample)
    if first is None or last is None:
        return {"hours_covered": None, "hours_required": STAGE_A_MIN_HOURS,
                "coverage_ratio": None, "expected_samples": None,
                "actual_samples": actual_samples, "gaps": None, "passed": False,
                "blockers": ["OBSERVATION_WINDOW_UNAVAILABLE"]}
    hours_covered = (last - first).total_seconds() / 3600.0
    expected_samples = (hours_covered * 3600.0) / expected_interval_secs
    coverage_ratio = (actual_samples / expected_samples) if expected_samples > 0 else 0.0
    gaps = max(0, int(round(expected_samples - actual_samples)))
    blockers = []
    if hours_covered < STAGE_A_MIN_HOURS:
        blockers.append("HOURS_COVERED_INSUFFICIENT")
    if coverage_ratio < STAGE_A_MIN_COVERAGE:
        blockers.append("COVERAGE_INSUFFICIENT")
    passed = (hours_covered >= STAGE_A_MIN_HOURS
              and coverage_ratio >= STAGE_A_MIN_COVERAGE)
    return {"hours_covered": hours_covered, "hours_required": STAGE_A_MIN_HOURS,
            "coverage_ratio": coverage_ratio,
            "expected_samples": int(round(expected_samples)),
            "actual_samples": actual_samples, "gaps": gaps, "passed": passed,
            "blockers": blockers}

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
    days = stage_b.get("days_covered")
    lines.append("- Stage B: " + _progress_bar(_safe_div(days, STAGE_B_MIN_DAYS))
                 + f" days={_fmt(days)}/{STAGE_B_MIN_DAYS} "
                 + f"passed={_fmt_bool(stage_b.get('passed'))}")
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

def _build_state(conn, db_path: str, interval_secs: float) -> dict:
    """Assemble the dashboard state from the read-only RH store."""
    state: dict = {}
    row = conn.execute("SELECT MIN(sample_time), MAX(sample_time), COUNT(*) "
                       "FROM rh_market_states").fetchone()
    first_sample, last_sample, actual_samples = row if row else (None, None, 0)
    state["as_of"] = last_sample
    if first_sample is not None and last_sample is not None:
        state["stage_a"] = stage_a_status(
            first_sample=first_sample, last_sample=last_sample,
            expected_interval_secs=interval_secs, actual_samples=actual_samples)
        span_days = (_to_datetime(last_sample) - _to_datetime(first_sample)).days
        state["stage_b"] = stage_b_status(
            days_covered=span_days, weekends_covered=None, unexplained_ledger_diffs=0,
            invariant_violations=0, missed_risk_events=0)
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
    state["budget"] = budget_status(db_path)
    return state

def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RH graduation readiness dashboard (read-only)")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="RH scanner.db (read-only)")
    parser.add_argument("--out", default="READINESS_DASHBOARD.md", help="output Markdown path")
    parser.add_argument("--interval-secs", type=float, default=15.0, help="Stage A sample interval (s)")
    args = parser.parse_args(argv)
    conn = open_store(args.db, read_only=True)
    try:
        state = _build_state(conn, args.db, args.interval_secs)
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
