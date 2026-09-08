#!/usr/bin/env python3
"""RH NetCover input assembler: 9-key engine contract from RH evidence (read-only)."""
from __future__ import annotations

import json, math, sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_netcover_engine_v1_readonly import (
    ACTIVE_SHARE_LIMIT, HARD_POSITION_TVL_SHARE, POSITION_TVL_SHARE,
    netcover_model_path, position_cap_usd,
)
from scripts.lp_netcover_inputs_v1_readonly import (
    EXIT_LATENCY_LOSS_APR_PCT_MODEL, LVR_COEFFICIENT_MODEL,
)
from scripts.lp_swap_cost_model_v1_readonly import (
    clmm_token0_value_fraction, exit_conversion_cost_usd, roundtrip_cost_usd,
)

RH_CHAIN_ID = 4663
REQUIRED_ENGINE_KEYS = (
    "fee_ev_usd", "reward_ev_usd", "il_ev_usd", "entry_cost_usd",
    "exit_cost_usd", "gas_usd", "slippage_usd",
    "reward_conversion_cost_usd", "exit_latency_loss_usd",
)

class MissingInput(NamedTuple):
    field: str
    reason: str

def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")

def _to_float(value: Any) -> Optional[float]:
    if _is_missing(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _fail_closed(reason, missing_fields, *, evidence, position_usd, horizon_hours):
    record = {
        "permanent_fail_closed_reason": reason,
        "missing_inputs": [{"field": f, "reason": r} for f, r in missing_fields],
        "protocol_type": "clmm",
        "netcover_model_path": netcover_model_path("clmm"),
        "capital_usd": float(position_usd),
        "lvr_coefficient": LVR_COEFFICIENT_MODEL,
        "holding_horizon_hours": horizon_hours,
        "rh_evidence_block_hash": evidence.get("block_hash"),
        "assembled_at": _utc_now_rfc3339(),
    }
    for key in REQUIRED_ENGINE_KEYS:
        record[key] = None
    return record

def assemble_rh_clmm_inputs(evidence, *, position_usd, horizon_hours):
    """Assemble 9-key NetCover contract from RH evidence. Fail-closed on first hit."""
    chain_id = _to_float(evidence.get("chain_id"))
    attestation = evidence.get("attestation_status")
    protocol = evidence.get("protocol")
    if chain_id is not None and int(chain_id) != RH_CHAIN_ID:
        return _fail_closed("RH_CHAIN_ID_MISMATCH", [("chain_id", "CHAIN_DATA_UNAVAILABLE")],
                            evidence=evidence, position_usd=position_usd, horizon_hours=horizon_hours)
    if attestation != "ATTESTED_SAME_BLOCK":
        return _fail_closed("DISCOVERED_NOT_ATTESTED", [("attestation_status", "CHAIN_DATA_UNAVAILABLE")],
                            evidence=evidence, position_usd=position_usd, horizon_hours=horizon_hours)
    if protocol != "v3":
        return _fail_closed("UNSUPPORTED_PROTOCOL", [("protocol", "UNSUPPORTED_PROTOCOL")],
                            evidence=evidence, position_usd=position_usd, horizon_hours=horizon_hours)
    missing = []
    pos = float(position_usd)
    fee_apr_pct = _to_float(evidence.get("fee_apr_pct"))
    if fee_apr_pct is None:
        fee_ev_usd = None
        missing.append(("fee_apr_pct", "EXTERNAL_DATA_UNAVAILABLE"))
    else:
        fee_ev_usd = pos * fee_apr_pct / 100.0 * horizon_hours / 8760.0
    reward_apr_pct = _to_float(evidence.get("reward_apr_pct"))
    reward_verified = bool(evidence.get("reward_verified", False))
    if reward_apr_pct is None or not reward_verified:
        reward_ev_usd = 0.0
        reward_unverified_reason = "reward_unverified_or_missing"
    else:
        reward_ev_usd = pos * reward_apr_pct / 100.0 * horizon_hours / 8760.0
        reward_unverified_reason = None
    sigma_daily = _to_float(evidence.get("sigma_daily"))
    if sigma_daily is None:
        il_ev_usd = None
        missing.append(("sigma_daily", "EXTERNAL_DATA_UNAVAILABLE"))
    else:
        il_ev_usd = pos * sigma_daily ** 2 * (horizon_hours / 24.0) / 8.0
    liquidity_raw = _to_float(evidence.get("liquidity_raw"))
    sqrt_price_x96 = _to_float(evidence.get("sqrt_price_x96"))
    fee = _to_float(evidence.get("fee"))
    dec0 = _to_float(evidence.get("dec0"))
    dec1 = _to_float(evidence.get("dec1"))
    cost_ok = all(v is not None and v > 0 for v in (liquidity_raw, sqrt_price_x96, fee, dec0, dec1))
    if not cost_ok:
        entry_cost_usd = exit_cost_usd = slippage_usd = None
        for field in ("liquidity_raw", "sqrt_price_x96", "fee", "dec0", "dec1"):
            if _to_float(evidence.get(field)) is None:
                missing.append((field, "CHAIN_DATA_UNAVAILABLE"))
    else:
        price = (sqrt_price_x96 / 2.0 ** 96) ** 2
        fee_tier = fee / 1e6
        d0, d1 = int(dec0), int(dec1)
        entry_cost_usd = exit_conversion_cost_usd(pos, liquidity_raw, price, fee_tier, d0, d1, side="buy_base")
        exit_cost_usd = exit_conversion_cost_usd(pos, liquidity_raw, price, fee_tier, d0, d1, side="sell_base")
        # roundtrip is entry+exit by construction; clamp float noise so the
        # engine's non-negative amount check never sees a -1e-18 slippage.
        slippage_usd = max(0.0, roundtrip_cost_usd(pos, liquidity_raw, price, fee_tier, d0, d1)
                           - entry_cost_usd - exit_cost_usd)
    gas_usd_estimate = _to_float(evidence.get("gas_usd_estimate"))
    if gas_usd_estimate is None:
        gas_usd = None
        missing.append(("gas_usd_estimate", "CHAIN_DATA_UNAVAILABLE"))
    else:
        gas_usd = gas_usd_estimate
    record = {
        "protocol_type": "clmm",
        "netcover_model_path": netcover_model_path("clmm"),
        "capital_usd": pos,
        "lvr_coefficient": LVR_COEFFICIENT_MODEL,
        "holding_horizon_hours": horizon_hours,
        "rh_evidence_block_hash": evidence.get("block_hash"),
        "assembled_at": _utc_now_rfc3339(),
        "fee_ev_usd": fee_ev_usd,
        "reward_ev_usd": reward_ev_usd,
        "il_ev_usd": il_ev_usd,
        "entry_cost_usd": entry_cost_usd,
        "exit_cost_usd": exit_cost_usd,
        "gas_usd": gas_usd,
        "slippage_usd": slippage_usd,
        "reward_conversion_cost_usd": 0.0,
        "exit_latency_loss_usd": pos * (EXIT_LATENCY_LOSS_APR_PCT_MODEL / 100.0) * horizon_hours / 8760.0,
        "missing_inputs": [{"field": f, "reason": r} for f, r in missing],
    }
    if reward_unverified_reason is not None:
        record["reward_unverified_reason"] = reward_unverified_reason
    return record

def position_cap_for_rh(evidence, *, tier_configured_max):
    """INV-TVLSHARE-01 cap via position_cap_usd; None cap on missing/invalid TVL."""
    tvl = _to_float(evidence.get("tvl_usd"))
    active = _to_float(evidence.get("active_liquidity_notional_usd"))
    if tvl is None or tvl <= 0 or active is None or active <= 0:
        return {"position_cap_usd": None, "position_cap_pass": False,
                "position_cap_reason": "INV-TVLSHARE-01_INPUT_MISSING_OR_INVALID"}
    cap = position_cap_usd(tier_configured_max, tvl, active, active_share_limit=ACTIVE_SHARE_LIMIT)
    return {"position_cap_usd": cap, "position_cap_pass": True, "position_cap_reason": None}

def classify_zero_candidate(record):
    """PRD 8.4 status. Non-economic engine rejections never map to COMPUTED_FAIL:
    a gate that never produced a number is not an economic failure (PRD 10.1)."""
    rejection = record.get("rejection_reason") or ""
    if rejection.startswith("NETCOVER_MODEL_PATH_MISMATCH:") or \
            rejection.startswith("NETCOVER_PROTOCOL_TYPE_INVALID:"):
        return "UNSUPPORTED"
    if record.get("permanent_fail_closed_reason") == "UNSUPPORTED_PROTOCOL":
        return "UNSUPPORTED"
    if rejection.startswith("NETCOVER_INPUT_MISSING:") or \
            rejection.startswith("NETCOVER_INPUT_INVALID:"):
        return "INPUTS_UNAVAILABLE"
    if record.get("missing_inputs") or any(record.get(k) is None for k in REQUIRED_ENGINE_KEYS):
        return "INPUTS_UNAVAILABLE"
    if record.get("netcover_pass") is True:
        return "COMPUTED_PASS"
    if record.get("netcover_pass") is False:
        netcover = record.get("netcover")
        if isinstance(netcover, (int, float)) and not isinstance(netcover, bool) \
                and math.isfinite(netcover):
            return "COMPUTED_FAIL"
    return "INPUTS_UNAVAILABLE"

def main(argv=None):
    """CLI: --evidence-json <file> --out <file> [--position-usd N] [--horizon-hours H]."""
    import argparse
    from scripts.lp_netcover_engine_v1_readonly import apply_netcover_gate
    parser = argparse.ArgumentParser(description="RH NetCover input assembler (read-only).")
    parser.add_argument("--evidence-json", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--position-usd", type=float, default=1000.0)
    parser.add_argument("--horizon-hours", type=float, default=24.0)
    args = parser.parse_args(argv)
    with open(args.evidence_json, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    # Accept a bare evidence list, or an object {"data_kind": ..., "records": [...]}.
    evidence_list = list(payload.get("records") or []) if isinstance(payload, Mapping) else list(payload)
    position_usd = Decimal(str(args.position_usd))
    results = []
    for evidence in evidence_list:
        record = assemble_rh_clmm_inputs(evidence, position_usd=position_usd, horizon_hours=args.horizon_hours)
        gate_results = apply_netcover_gate([record])
        gate = gate_results[0] if gate_results else {}
        record["netcover"] = gate.get("netcover")
        record["netcover_pass"] = gate.get("netcover_pass")
        record["rejection_reason"] = gate.get("rejection_reason")
        record["primary_status"] = classify_zero_candidate(record)
        results.append(record)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"generated_by": "lp_rh_netcover_inputs_v1_readonly",
                   "count": len(results), "results": results}, fh, indent=2)
        fh.write("\n")
    print(f"Wrote {len(results)} records to {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
