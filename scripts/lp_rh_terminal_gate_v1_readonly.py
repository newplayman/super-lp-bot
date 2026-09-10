#!/usr/bin/env python3
"""RH terminal gate: ten-way conjunction + mutation witness (read-only, offline).

PRD v1.1 §11.5 defines the RH terminal gate as a ten-way conjunction.  RH-INV-04
(§18.3) requires every hard gate to have a producer, to be read, to enter the
terminal conjunction, and to carry a mutation witness proving that omitting it
lets a bad sample through.  This module is the production conjunction; the
paired test asserts its source shape (which names participate in the ``and``)
and that each gate, when forced False, rejects.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_netcover_inputs_v1_readonly import classify_zero_candidate

# PRD §11.5: the ten terminal-gate conjuncts.  The set is asserted by the
# paired AST test; the tuple fixes the dominant_blocker priority order.
TERMINAL_CONJUNCTS = frozenset({
    "legacy_required_conjunction",
    "identity_verified",
    "protocol_capabilities_sufficient",
    "data_complete_and_fresh",
    "profile_policy_pass",
    "market_and_chain_risk_pass",
    "netcover_pass",
    "absolute_profit_pass",
    "position_and_exit_depth_pass",
    "capital_policy_pass",
})

CONJUNCT_ORDER = (
    "legacy_required_conjunction",
    "identity_verified",
    "protocol_capabilities_sufficient",
    "data_complete_and_fresh",
    "profile_policy_pass",
    "market_and_chain_risk_pass",
    "netcover_pass",
    "absolute_profit_pass",
    "position_and_exit_depth_pass",
    "capital_policy_pass",
)

VALID_TARGET_MODES = ("SHADOW_SCENARIO", "LIVE_READINESS")


@dataclass
class GateDecision:
    decision_id: str
    candidate_key: str
    target_mode: str
    terminal_eligible: bool
    terminal_bits: dict[str, bool]
    primary_status: str
    dominant_blocker: Optional[str]
    reasons: list[str]
    snapshot_ids: list[str]
    decided_at: str
    simulated_policy_only: bool = False


def _capital_policy_conflict_present(record: Mapping[str, Any]) -> bool:
    """True when the record carries a capital-policy conflict (dict or bool)."""
    cpc = record.get("capital_policy_conflict")
    if isinstance(cpc, Mapping):
        return bool(cpc.get("conflict"))
    return bool(cpc)


def _decided_at(now: Any) -> str:
    return now if isinstance(now, str) else now.isoformat()


def evaluate_terminal_gate(record, *, target_mode, now) -> GateDecision:
    if target_mode not in VALID_TARGET_MODES:
        raise ValueError("UNKNOWN_TARGET_MODE")
    record = dict(record)
    reasons: list[str] = []

    legacy = record.get("legacy_required_conjunction")
    if legacy is None:
        legacy_required_conjunction = False
        reasons.append("LEGACY_CONJUNCTION_NO_PRODUCER")
    else:
        legacy_required_conjunction = bool(legacy)

    identity_verified = bool(record.get("identity_verified"))
    protocol_capabilities_sufficient = bool(record.get("protocol_capabilities_sufficient"))
    data_complete_and_fresh = bool(record.get("data_complete_and_fresh"))
    profile_policy_pass = bool(record.get("profile_policy_pass"))
    market_and_chain_risk_pass = bool(record.get("market_and_chain_risk_pass"))
    netcover_pass = bool(record.get("netcover_pass"))
    absolute_profit_pass = bool(record.get("absolute_profit_pass"))
    position_and_exit_depth_pass = bool(record.get("position_and_exit_depth_pass"))

    conflict_present = _capital_policy_conflict_present(record)
    if target_mode == "LIVE_READINESS" and conflict_present:
        capital_policy_pass = False
        reasons.append("CAPITAL_POLICY_CONFLICT")
    else:
        capital_policy_pass = bool(record.get("capital_policy_pass"))

    terminal_eligible = (
        legacy_required_conjunction
        and identity_verified
        and protocol_capabilities_sufficient
        and data_complete_and_fresh
        and profile_policy_pass
        and market_and_chain_risk_pass
        and netcover_pass
        and absolute_profit_pass
        and position_and_exit_depth_pass
        and capital_policy_pass
    )

    terminal_bits = {
        "legacy_required_conjunction": legacy_required_conjunction,
        "identity_verified": identity_verified,
        "protocol_capabilities_sufficient": protocol_capabilities_sufficient,
        "data_complete_and_fresh": data_complete_and_fresh,
        "profile_policy_pass": profile_policy_pass,
        "market_and_chain_risk_pass": market_and_chain_risk_pass,
        "netcover_pass": netcover_pass,
        "absolute_profit_pass": absolute_profit_pass,
        "position_and_exit_depth_pass": position_and_exit_depth_pass,
        "capital_policy_pass": capital_policy_pass,
    }

    dominant_blocker: Optional[str] = None
    for name in CONJUNCT_ORDER:
        if not terminal_bits[name]:
            dominant_blocker = name
            break

    # PRD §8.4/§10.1: fixed priority for primary_status.  A candidate the
    # terminal gate rejected must never read as COMPUTED_PASS to consumers
    # that only read the status.
    missing_conjuncts = [n for n in CONJUNCT_ORDER if record.get(n) is None]
    rejection = str(record.get("rejection_reason") or "")
    if target_mode == "LIVE_READINESS" and capital_policy_pass is False:
        primary_status = "POLICY_BLOCKED"
    elif "LEGACY_CONJUNCTION_NO_PRODUCER" in reasons or missing_conjuncts:
        primary_status = "INPUTS_UNAVAILABLE"
    elif protocol_capabilities_sufficient is False or rejection.startswith(
        "NETCOVER_MODEL_PATH_MISMATCH:"
    ) or rejection.startswith("NETCOVER_PROTOCOL_TYPE_INVALID:"):
        primary_status = "UNSUPPORTED"
    else:
        primary_status = classify_zero_candidate(record)
    if terminal_eligible is False and primary_status == "COMPUTED_PASS":
        primary_status = "COMPUTED_FAIL"

    simulated_policy_only = target_mode == "SHADOW_SCENARIO"
    if simulated_policy_only:
        reasons.append("SIMULATED_POLICY_ONLY")

    candidate_key = str(record.get("candidate_key") or record.get("pool_key") or "unknown")
    episode = str(record.get("strategy_episode") or "").strip()
    if episode:
        decision_id = f"rh-terminal-{episode}-{candidate_key}-{target_mode}"
    else:
        decision_id = f"rh-terminal-{candidate_key}-{target_mode}"
    return GateDecision(
        decision_id=decision_id,
        candidate_key=candidate_key,
        target_mode=target_mode,
        terminal_eligible=terminal_eligible,
        terminal_bits=terminal_bits,
        primary_status=primary_status,
        dominant_blocker=dominant_blocker,
        reasons=reasons,
        snapshot_ids=list(record.get("source_snapshot_ids") or []),
        decided_at=_decided_at(now),
        simulated_policy_only=simulated_policy_only,
    )


def mutation_witness_removed_gate(record, *, removed, target_mode, now) -> bool:
    """Force ``removed`` to True and recompute the conjunction.

    Returns the mutant's ``terminal_eligible``.  The paired test uses this to
    prove that omitting any one gate lets a bad sample through: a mutant that
    restores one false bit to True must fail the per-gate rejection check.
    """
    if removed not in TERMINAL_CONJUNCTS:
        raise ValueError(f"UNKNOWN_GATE: {removed}")
    mutated = dict(record)
    mutated[removed] = True
    return evaluate_terminal_gate(
        mutated, target_mode=target_mode, now=now
    ).terminal_eligible


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="RH terminal gate (read-only).")
    parser.add_argument("--record-json", required=True)
    parser.add_argument("--target-mode", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with open(args.record_json, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    records = payload.get("records") if isinstance(payload, Mapping) else payload
    if not isinstance(records, list):
        records = [records]
    now = datetime.now(timezone.utc)
    results = [
        asdict(evaluate_terminal_gate(r, target_mode=args.target_mode, now=now))
        for r in records
    ]
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({
            "generated_by": "lp_rh_terminal_gate_v1_readonly",
            "target_mode": args.target_mode,
            "count": len(results),
            "results": results,
        }, fh, indent=2)
        fh.write("\n")
    print(f"Wrote {len(results)} decisions to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
