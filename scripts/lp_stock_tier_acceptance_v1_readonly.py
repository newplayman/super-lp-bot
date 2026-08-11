#!/usr/bin/env python3
"""Combine Stage-1, Solana Stage-2, E5 sizing and E6 shadow into A/B/C gates."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lp_stock_tier_policy_v1_readonly import evaluate_ab_gate, evaluate_c_gate
from scripts.lp_netcover_inputs_v1_readonly import NETCOVER_INPUT_FIELDS


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("records", "rows", "pools", "data"):
            if isinstance(payload.get(key), list):
                return _rows(payload[key])
    raise ValueError("payload does not contain records")


def _index(rows: list[Mapping[str, Any]], *keys: str) -> dict[str, Mapping[str, Any]]:
    output = {}
    for row in rows:
        for key in keys:
            if row.get(key):
                output[str(row[key])] = row
                break
    return output


def _terminal_zero_cause(stage2: Mapping[str, Any], decision: Mapping[str, Any]) -> str | None:
    """Separate genuine failed economics from a terminal gate with no inputs."""
    if decision.get("passed") is True:
        return None
    economics = stage2.get("economics") if isinstance(stage2.get("economics"), Mapping) else {}
    netcover = stage2.get("netcover") if isinstance(stage2.get("netcover"), Mapping) else {}
    inputs = netcover.get("inputs") if isinstance(netcover.get("inputs"), Mapping) else {}
    if not stage2:
        return "0_because_inputs_unavailable"
    if stage2.get("stage2_pass") is True:
        return "0_because_computed_and_failed"
    if economics.get("passed") is not True:
        return "0_because_inputs_unavailable"
    if netcover and any(inputs.get(field) is None for field in NETCOVER_INPUT_FIELDS):
        return "0_because_inputs_unavailable"
    return "0_because_computed_and_failed"


def build_acceptance(
    universe_payload: Any,
    stage2_payload: Mapping[str, Any],
    e5_payload: Mapping[str, Any],
    shadow_payload: Mapping[str, Any],
    c_risk_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    universe = _rows(universe_payload)
    stage2 = _index(list(stage2_payload.get("results") or []), "llama_pool_id")
    e5 = _index(list(e5_payload.get("rows") or []), "llama_pool_id")
    shadow = _index(list(shadow_payload.get("pools") or []), "pool_id")
    c_risk = _index(list((c_risk_payload or {}).get("results") or []), "llama_pool_id")
    decisions = []
    current_c_exposure_usd = 0.0
    for row in universe:
        pool_id = str(row.get("pool_id") or row.get("pool") or row.get("llama_pool_id") or "")
        tier = str(row.get("tier") or "").upper()
        s2, sizing = stage2.get(pool_id, {}), e5.get(pool_id, {})
        if tier in {"A", "B"}:
            # Stage-2 is necessary but never silently upgraded into the complete
            # pre-existing conjunction (basis/session/stability/NetCover/etc.).
            evidence = {
                "existing_terminal_conjunction": s2.get("existing_terminal_conjunction") is True,
                "instrument_normalized": row.get("issuer") != "unknown",
                "absolute_profit_pass": sizing.get("absolute_profit_pass") is True,
                "dual_volatility_tightened_pass": s2.get("dual_volatility_tightened_pass") is True,
            }
            decision = evaluate_ab_gate(tier, evidence)
        elif tier == "C":
            instrument_normalized = (
                isinstance(row.get("issuer"), str)
                and bool(row.get("issuer").strip())
                and row.get("issuer") != "unknown"
            )
            if not instrument_normalized:
                decision = {
                    "tier": "C", "passed": False,
                    "reason": "FAIL_CLOSED:0_instrument_normalization",
                    "failures": ["0_instrument_normalization"],
                    "gates": {}, "terminal_conjunction_complete": False,
                }
                decisions.append({
                    "llama_pool_id": pool_id, "symbol": row.get("symbol"), "chain": row.get("chain"),
                    "project": row.get("project"), "issuer": row.get("issuer"), "tier": tier,
                    "stage2_pass": s2.get("stage2_pass") is True, "decision": decision,
                })
                continue
            if row.get("wash_suspect") is True:
                decision = {
                    "tier": "C", "passed": False, "reason": "FAIL_CLOSED:WASH_SUSPECT_REJECTED",
                    "failures": ["0_wash_suspect"], "gates": {}, "terminal_conjunction_complete": False,
                }
                decisions.append({
                    "llama_pool_id": pool_id, "symbol": row.get("symbol"), "chain": row.get("chain"),
                    "project": row.get("project"), "issuer": row.get("issuer"), "tier": tier,
                    "stage2_pass": s2.get("stage2_pass") is True, "decision": decision,
                })
                continue
            persistence = shadow.get(pool_id, {})
            economics = s2.get("economics") or {}
            risk = c_risk.get(pool_id, {})
            holders = risk.get("holder_snapshot") or {}
            age = risk.get("token_age") or {}
            c_evidence = {
                "exit_verdict": s2.get("exit_verdict"),
                "largest_holder_pct": holders.get("largest_holder_pct"),
                "pool_vaults_verified_and_excluded": holders.get("pool_vaults_verified_and_excluded") is True,
                "sell_simulation_ok": s2.get("sell_simulation_ok") is True,
                "known_honeypot": s2.get("known_honeypot"),
                "sell_tax_pct": s2.get("sell_tax_pct"),
                "simulation_broadcast_count": 0,
                "yield_persistence_hours": persistence.get("span_hours"),
                "yield_persistence_samples": persistence.get("sample_count"),
                "yield_persistence_threshold_held": persistence.get("eligible_48h") is True,
                "counter_token_age_days": age.get("counter_token_age_days"),
                "position_usd": 5.0,
                "exit_depth_usd": economics.get("exit_depth_usd"),
                "exit_slippage_bps": s2.get("exit_slippage_bps"),
            }
            decision = evaluate_c_gate(
                c_evidence, current_c_exposure_usd=current_c_exposure_usd
            )
            # Exposure is a batch-level constraint.  Only a fully passed
            # terminal C decision reserves capital for later candidates.
            if decision.get("passed") is True:
                current_c_exposure_usd += float(c_evidence["position_usd"])
        else:
            decision = {"tier": tier, "passed": False,
                        "reason": "STOCK_STOCK_RESEARCH_ONLY_NO_TIER_POLICY"}
        decisions.append({
            "llama_pool_id": pool_id, "symbol": row.get("symbol"), "chain": row.get("chain"),
            "project": row.get("project"), "issuer": row.get("issuer"), "tier": tier,
            "stage2_pass": s2.get("stage2_pass") is True,
            "decision": decision,
        })
    for row in decisions:
        row["terminal_zero_cause"] = _terminal_zero_cause(
            stage2.get(str(row["llama_pool_id"]), {}), row["decision"],
        )
    terminal_decisions = [
        row for row in decisions if row["decision"].get("passed") is True
    ]
    return {
        "counts_are_real_chain_terminal_not_defillama_yield_claims": all(
            row["stage2_pass"] for row in terminal_decisions
        ),
        "tier_counts": {
            tier: {
                "universe": sum(row["tier"] == tier for row in decisions),
                "stage2_pass": sum(row["tier"] == tier and row["stage2_pass"] for row in decisions),
                "terminal_pass": sum(row["tier"] == tier and row["decision"].get("passed") is True for row in decisions),
                "0_because_computed_and_failed": sum(
                    row["tier"] == tier and row.get("terminal_zero_cause") == "0_because_computed_and_failed"
                    for row in decisions
                ),
                "0_because_inputs_unavailable": sum(
                    row["tier"] == tier and row.get("terminal_zero_cause") == "0_because_inputs_unavailable"
                    for row in decisions
                ),
            } for tier in ("A", "B", "C", "STOCK_STOCK")
        },
        "terminal_pass_count": sum(row["decision"].get("passed") is True for row in decisions),
        "signed": False, "broadcast_count": 0, "decisions": decisions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--stage2", type=Path, required=True)
    parser.add_argument("--e5", type=Path, required=True)
    parser.add_argument("--shadow", type=Path, required=True)
    parser.add_argument("--c-risk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_acceptance(
        json.loads(args.universe.read_text()), json.loads(args.stage2.read_text()),
        json.loads(args.e5.read_text()), json.loads(args.shadow.read_text()),
        json.loads(args.c_risk.read_text()),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"tier_counts": report["tier_counts"],
                      "terminal_pass_count": report["terminal_pass_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
