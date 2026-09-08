#!/usr/bin/env python3
"""Offline autopsy helpers for the RH ten-gate terminal funnel."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

sys.path.insert(0, "/opt/lpbot/lp-bot-v3-origin-check")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_terminal_gate_v1_readonly import (  # noqa: E402
    CONJUNCT_ORDER,
    TERMINAL_CONJUNCTS,
    evaluate_terminal_gate,
    mutation_witness_removed_gate,
)

STATUS_ORDER = (
    "COMPUTED_PASS",
    "COMPUTED_FAIL",
    "INPUTS_UNAVAILABLE",
    "UNSUPPORTED",
    "POLICY_BLOCKED",
)

# Re-export the authoritative gate set for callers inspecting the autopsy.
assert frozenset(CONJUNCT_ORDER) == TERMINAL_CONJUNCTS


def _as_records(payload: Any) -> list[Mapping[str, Any]]:
    """Accept a bare list or the usual ``{"records": [...]}`` wrapper."""
    if isinstance(payload, Mapping):
        payload = payload.get("records", payload.get("data"))
    if not isinstance(payload, list):
        raise ValueError("expected a JSON list or an object containing records")
    if not all(isinstance(record, Mapping) for record in payload):
        raise ValueError("every record must be a JSON object")
    return payload


def _decisions(records: Sequence[Mapping[str, Any]], *, target_mode: str, now: Any):
    return [
        (record, evaluate_terminal_gate(record, target_mode=target_mode, now=now))
        for record in records
    ]


def autopsy(records, *, target_mode, now) -> dict[str, Any]:
    """Run every record through the terminal gate and summarize the funnel."""
    records = list(records)
    decisions = _decisions(records, target_mode=target_mode, now=now)

    by_status = {status: 0 for status in STATUS_ORDER}
    by_blocker = {gate: 0 for gate in CONJUNCT_ORDER}
    for _record, decision in decisions:
        by_status[decision.primary_status] = by_status.get(decision.primary_status, 0) + 1
        if decision.dominant_blocker is not None:
            by_blocker[decision.dominant_blocker] += 1

    closest: list[dict[str, Any]] = []
    for record, decision in decisions:
        missing = [gate for gate in CONJUNCT_ORDER if not decision.terminal_bits[gate]]
        if len(missing) != 1:
            continue
        closest.append({
            "candidate_key": decision.candidate_key,
            "missing_gate": missing[0],
            "record": dict(record),
        })
    closest = closest[:3]

    survivors = list(decisions)
    decay = []
    for gate in CONJUNCT_ORDER:
        survivors = [
            (_record, decision)
            for _record, decision in survivors
            if decision.terminal_bits[gate]
        ]
        decay.append({"gate": gate, "survivors": len(survivors)})

    return {
        "total": len(records),
        "by_primary_status": by_status,
        "by_dominant_blocker": by_blocker,
        "closest_to_pass": closest,
        "no_producer_fields": [
            field for field, detail in producer_map_check(records, CONJUNCT_ORDER).items()
            if detail["verdict"] == "NO_PRODUCER"
        ],
        "decay": decay,
    }


def zero_candidate_explanation(summary) -> str:
    """Render a status-only explanation for a zero computed-pass cohort."""
    statuses = summary.get("by_primary_status", {})
    computed_pass = int(statuses.get("COMPUTED_PASS", 0))
    return "\n".join((
        "zero_candidate_summary:",
        f"COMPUTED_PASS: {computed_pass}",
        f"已完成经济评估且不合格: {int(statuses.get('COMPUTED_FAIL', 0))}",
        f"尚未能评估: {int(statuses.get('INPUTS_UNAVAILABLE', 0))}",
        f"不支持: {int(statuses.get('UNSUPPORTED', 0))}",
        f"政策阻挡: {int(statuses.get('POLICY_BLOCKED', 0))}",
    ))


def mutation_harness(records, *, target_mode, now) -> dict[str, dict[str, Any]]:
    """Count bad records admitted when each individual gate is forced True."""
    records = list(records)
    original = _decisions(records, target_mode=target_mode, now=now)
    result: dict[str, dict[str, Any]] = {}
    for gate in CONJUNCT_ORDER:
        false_admits = 0
        for record, decision in original:
            if decision.terminal_eligible:
                continue
            if mutation_witness_removed_gate(
                record, removed=gate, target_mode=target_mode, now=now
            ):
                false_admits += 1
        result[gate] = {
            "false_admits": false_admits,
            "witness_detected": false_admits > 0,
        }
    return result


def producer_map_check(records, required_fields) -> dict[str, dict[str, Any]]:
    """Report fields with no observed producer, without judging economics."""
    records = list(records)
    result: dict[str, dict[str, Any]] = {}
    for field in required_fields:
        missing = sum(field not in record or record.get(field) is None for record in records)
        result[str(field)] = {
            "missing": missing,
            "verdict": "NO_PRODUCER" if missing == len(records) else "OK",
        }
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="RH funnel autopsy (offline/read-only)")
    parser.add_argument("--records-json", required=True)
    parser.add_argument("--target-mode", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    with open(args.records_json, "r", encoding="utf-8") as handle:
        records = _as_records(json.load(handle))
    now = datetime.now(timezone.utc)
    summary = autopsy(records, target_mode=args.target_mode, now=now)
    output = {
        "generated_by": "lp_rh_funnel_autopsy_v1_readonly",
        "target_mode": args.target_mode,
        "summary": summary,
        "mutation": mutation_harness(records, target_mode=args.target_mode, now=now),
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Wrote autopsy for {len(records)} records to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
