#!/usr/bin/env python3
"""RH daily decision report generator (offline, read-only).

PRD v1.1 §17.3: DAILY_DECISION.md needs seven fixed sections and forbids a
bare "accepted=0, tests green" plus citing the paper runner's virtual P&L.
§17.1: the front page answers six questions.  No network I/O, no live store.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_funnel_autopsy_v1_readonly import (  # noqa: E402
    STATUS_ORDER,
    zero_candidate_explanation,
)
from scripts.lp_rh_terminal_gate_v1_readonly import TERMINAL_CONJUNCTS  # noqa: E402
from scripts.lp_rh_store_v1_readonly import budget_status  # noqa: E402

# PRD §17.3: the seven fixed sections, in report order.
SEVEN_SECTIONS = (
    "证据日期与完整性",
    "已算与未算",
    "最接近通过的三个候选",
    "100U 政策下可行性",
    "全部费用与风险成本",
    "无交易是否合理",
    "基础设施缺口",
)

# The four non-pass statuses that must be broken out when COMPUTED_PASS == 0.
FOUR_CATEGORIES = ("COMPUTED_FAIL", "INPUTS_UNAVAILABLE", "UNSUPPORTED", "POLICY_BLOCKED")

# PRD §17.1: the six front-page questions, keyed for answer_six_questions.
SIX_QUESTIONS = (
    ("q1_mode", "当前模式与授权是什么？是否只有 Shadow？哪一道门阻止 LIVE？"),
    ("q2_budgets", "三桶预算、LP 部署、钱包风险库存、预留在途资金和原生 gas 分别多少？"),
    ("q3_pools", "从发现到可部署剩多少池？未计算、不盈利、不支持、政策阻挡分别多少？"),
    ("q4_values", "实际净值／现金流／HODL 差／净手续费分别是多少？哪些是虚拟、估计或陈旧值？"),
    ("q5_cost", "最近的主导成本是什么？持有／不建仓／再平衡哪个保守 EV 更好？"),
    ("q6_exit", "能否按当前仓位 size 退出？最近退出模拟何时完成，有没有未知交易或残余库存？"),
)


def _is_blank(value: Any) -> bool:
    """True when a value carries no evidence (None / empty / blank)."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def _section_evidence(as_of: Any, evidence_freshness: Any) -> str:
    lines = [f"as_of: {as_of}", ""]
    lines.append(evidence_freshness_table(evidence_freshness))
    return "\n".join(lines)


def _section_computed(coverage: Mapping[str, Any]) -> str:
    lines = []
    for status in STATUS_ORDER:
        if status in coverage:
            lines.append(f"{status}: {coverage[status]}")
    for key, value in coverage.items():
        if key not in STATUS_ORDER:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _section_closest(autopsy_summary: Mapping[str, Any]) -> str:
    closest = autopsy_summary.get("closest_to_pass") or []
    if not closest:
        body = "no candidate is within a single gate of passing"
    else:
        rows = [
            f"{i}. {c.get('candidate_key')} — missing gate: {c.get('missing_gate')}"
            for i, c in enumerate(closest, 1)
        ]
        body = "\n".join(rows)
    body += "\n\nterminal gates: " + ", ".join(sorted(TERMINAL_CONJUNCTS))
    return body


def _section_capital(capital_policy: Mapping[str, Any]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in capital_policy.items())


def _section_cost(cost_breakdown: Any) -> str:
    if isinstance(cost_breakdown, Mapping):
        return "\n".join(f"{k}: {v}" for k, v in cost_breakdown.items())
    return "\n".join(str(item) for item in cost_breakdown)


def _section_no_trade(autopsy_summary: Mapping[str, Any]) -> str:
    statuses = autopsy_summary.get("by_primary_status", {})
    computed_pass = int(statuses.get("COMPUTED_PASS", 0))
    if computed_pass == 0:
        lines = [
            "no candidate passes the terminal gate under the current policy;",
            "no-trade is the reasonable choice this cycle.",
            "",
            zero_candidate_explanation(autopsy_summary),
        ]
    else:
        lines = [f"{computed_pass} candidate(s) pass; verify feasibility before trading."]
    return "\n".join(lines)


def _section_infra(infra_gaps: Any) -> str:
    if not infra_gaps:
        return "no infrastructure gaps reported"
    return "\n".join(f"- {gap}" for gap in infra_gaps)


def evidence_freshness_table(sources: Any) -> str:
    """One row per source; None source_event_time -> SERVER_TIME_UNKNOWN (§8.1)."""
    lines = [
        "| source | fetched_at | source_event_time | age_secs | quality |",
        "|---|---|---|---|---|",
    ]
    for source in sources:
        event_time = source.get("source_event_time")
        event_display = "SERVER_TIME_UNKNOWN" if event_time is None else str(event_time)
        lines.append(
            "| {src} | {fetched} | {event} | {age} | {quality} |".format(
                src=source.get("source"),
                fetched=source.get("fetched_at"),
                event=event_display,
                age=source.get("age_secs"),
                quality=source.get("quality"),
            )
        )
    return "\n".join(lines)


def build_report(
    *,
    run_id: str,
    as_of: Any,
    autopsy_summary: Mapping[str, Any],
    coverage: Mapping[str, Any],
    capital_policy: Mapping[str, Any],
    cost_breakdown: Any,
    infra_gaps: Any,
    evidence_freshness: Any,
) -> str:
    """Render the seven-section DAILY_DECISION body; missing input -> MISSING_SECTION."""
    checks = (
        ("证据日期与完整性", isinstance(evidence_freshness, (list, tuple)) and bool(evidence_freshness)),
        ("已算与未算", isinstance(coverage, Mapping) and bool(coverage)),
        ("最接近通过的三个候选", isinstance(autopsy_summary, Mapping) and "closest_to_pass" in autopsy_summary),
        ("100U 政策下可行性", isinstance(capital_policy, Mapping) and bool(capital_policy)),
        ("全部费用与风险成本", not _is_blank(cost_breakdown)),
        ("无交易是否合理", isinstance(autopsy_summary, Mapping) and "by_primary_status" in autopsy_summary),
        ("基础设施缺口", infra_gaps is not None),
    )
    for name, ok in checks:
        if not ok:
            raise ValueError(f"MISSING_SECTION:{name}")

    bodies = {
        "证据日期与完整性": _section_evidence(as_of, evidence_freshness),
        "已算与未算": _section_computed(coverage),
        "最接近通过的三个候选": _section_closest(autopsy_summary),
        "100U 政策下可行性": _section_capital(capital_policy),
        "全部费用与风险成本": _section_cost(cost_breakdown),
        "无交易是否合理": _section_no_trade(autopsy_summary),
        "基础设施缺口": _section_infra(infra_gaps),
    }

    lines = [
        "# DAILY_DECISION",
        f"run_id: {run_id}",
        f"as_of: {as_of}",
        "",
    ]
    for name in SEVEN_SECTIONS:
        lines.append(f"## {name}")
        lines.append("")
        lines.append(bodies[name])
        lines.append("")
    return "\n".join(lines)


def _render_answer(data: Any) -> str:
    if isinstance(data, str):
        return data
    if isinstance(data, Mapping):
        return "; ".join(f"{k}={v}" for k, v in data.items())
    if isinstance(data, (list, tuple)):
        return "; ".join(str(item) for item in data)
    return str(data)


def answer_six_questions(state: Optional[Mapping[str, Any]]) -> dict:
    """Answer the six §17.1 questions; no evidence -> NOT_MEASURED, never fabricated."""
    state = state or {}
    result: dict[str, dict[str, str]] = {}
    for key, question in SIX_QUESTIONS:
        data = state.get(key)
        if _is_blank(data):
            result[key] = {
                "answer": "NOT_MEASURED",
                "evidence": f"no evidence supplied for: {question}",
            }
        else:
            result[key] = {
                "answer": _render_answer(data),
                "evidence": json.dumps(data, ensure_ascii=False, default=str),
            }
    return result


def _render_six_questions(answers: Mapping[str, dict]) -> str:
    lines = ["## 首页六问", ""]
    for key, question in SIX_QUESTIONS:
        entry = answers.get(key, {})
        lines.append(f"- **{question}**")
        lines.append(f"  - answer: {entry.get('answer', 'NOT_MEASURED')}")
        lines.append(f"  - evidence: {entry.get('evidence', '')}")
    lines.append("")
    return "\n".join(lines)


_PAPER_RE = re.compile(r"paper", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"(?:\$|USDT?|USDC)\s*[\d][\d,]*(?:\.\d+)?", re.IGNORECASE)


def forbid_paper_pnl(text: str) -> None:
    """Raise PAPER_PNL_CITED_FOR_RH if 'paper' and a currency amount share a line (§17.3)."""
    for line in text.splitlines():
        if _PAPER_RE.search(line) and _AMOUNT_RE.search(line):
            raise ValueError("PAPER_PNL_CITED_FOR_RH")


def assert_not_bare_accepted_zero(report: str, summary: Mapping[str, Any]) -> None:
    """Raise BARE_ACCEPTED_ZERO when COMPUTED_PASS == 0 but the four-way split is absent."""
    statuses = summary.get("by_primary_status", {}) if isinstance(summary, Mapping) else {}
    computed_pass = int(statuses.get("COMPUTED_PASS", 0))
    if computed_pass == 0 and not all(cat in report for cat in FOUR_CATEGORIES):
        raise ValueError("BARE_ACCEPTED_ZERO")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="RH daily decision report (offline/read-only)")
    parser.add_argument("--state-json", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    with open(args.state_json, "r", encoding="utf-8") as handle:
        state = json.load(handle)

    report = build_report(
        run_id=state["run_id"],
        as_of=state["as_of"],
        autopsy_summary=state["autopsy_summary"],
        coverage=state["coverage"],
        capital_policy=state["capital_policy"],
        cost_breakdown=state["cost_breakdown"],
        infra_gaps=state["infra_gaps"],
        evidence_freshness=state["evidence_freshness"],
    )

    six_answers = answer_six_questions(state.get("six_questions"))
    full = _render_six_questions(six_answers) + "\n" + report

    if state.get("store_path"):
        budget = budget_status(state["store_path"])
        full += f"\n## 存储预算\n\nstore budget: {budget['state']} " \
                f"({budget['bytes']}/{budget['soft_budget_bytes']} bytes)\n"

    forbid_paper_pnl(full)
    assert_not_bare_accepted_zero(full, state["autopsy_summary"])

    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(full)
    print(f"Wrote daily decision report to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
