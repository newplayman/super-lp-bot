#!/usr/bin/env python3
"""Collect fail-closed Solana holder concentration and token-age evidence."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lp_rpc_pool_v1_readonly import RpcPool


MAX_SIGNATURES = 1000
MIN_AGE_DAYS = 7.0


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("rows", "records", "pools", "data"):
            if isinstance(payload.get(key), list):
                return _rows(payload[key])
    raise ValueError("universe must contain rows")


def counter_leg(universe_row: Mapping[str, Any], resolved: Mapping[str, Any]) -> tuple[str, str]:
    legs = list(universe_row.get("pair_legs") or [])
    tokens = list(universe_row.get("underlying_tokens") or [])
    stock_symbols = {
        str(item.get("pool_token_symbol") or "").upper()
        for item in universe_row.get("stock_instruments") or []
        if isinstance(item, Mapping)
    }
    indexes = [index for index, leg in enumerate(legs) if str(leg).upper() not in stock_symbols]
    if len(legs) != 2 or len(tokens) != 2 or len(indexes) != 1:
        raise ValueError("EXACTLY_ONE_NON_STOCK_LEG_REQUIRED")
    index = indexes[0]
    mint = str(tokens[index])
    if mint == resolved.get("mint_a"):
        vault = str(resolved.get("vault_a") or "")
    elif mint == resolved.get("mint_b"):
        vault = str(resolved.get("vault_b") or "")
    else:
        raise ValueError("COUNTER_MINT_NOT_IN_RESOLVED_POOL")
    if not mint or not vault:
        raise ValueError("COUNTER_MINT_OR_VAULT_MISSING")
    return mint, vault


def holder_snapshot(rpc: RpcPool, mint: str, verified_pool_vault: str) -> dict[str, Any]:
    mint_info = rpc.call("getAccountInfo", [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}])
    try:
        value = mint_info["value"]
        info = value["data"]["parsed"]["info"]
        supply = int(info["supply"])
    except (KeyError, TypeError, ValueError):
        return {"passed": False, "reason": "MINT_SUPPLY_UNAVAILABLE"}
    largest = rpc.call("getTokenLargestAccounts", [mint, {"commitment": "confirmed"}])
    rows = largest.get("value") if isinstance(largest, Mapping) else None
    if supply <= 0 or not isinstance(rows, list):
        return {"passed": False, "reason": "LARGEST_ACCOUNTS_UNAVAILABLE"}
    holders = []
    for row in rows:
        try:
            address, amount = str(row["address"]), int(row["amount"])
        except (KeyError, TypeError, ValueError):
            continue
        if address == verified_pool_vault:
            continue
        holders.append({"token_account": address, "raw_amount": amount,
                        "supply_pct": amount / supply * 100.0})
    if not holders:
        return {"passed": False, "reason": "NO_NON_POOL_HOLDER_EVIDENCE"}
    return {
        "passed": True, "reason": "PASS", "mint": mint,
        "pool_vaults_verified_and_excluded": True,
        "excluded_pool_vault": verified_pool_vault,
        "largest_holder_pct": max(row["supply_pct"] for row in holders),
        "holder_accounts_are_token_accounts_not_beneficial_owner_clusters": True,
        "holders": holders,
    }


def token_age_evidence(rpc: RpcPool, mint: str, *, now_unix: int | None = None) -> dict[str, Any]:
    signatures = rpc.call("getSignaturesForAddress", [
        mint, {"limit": MAX_SIGNATURES, "commitment": "confirmed"},
    ])
    if not isinstance(signatures, list) or not signatures:
        return {"passed": False, "reason": "NO_MINT_SIGNATURE_HISTORY"}
    times = [int(row["blockTime"]) for row in signatures
             if isinstance(row, Mapping) and isinstance(row.get("blockTime"), int)]
    if not times:
        return {"passed": False, "reason": "MINT_BLOCK_TIMES_UNAVAILABLE"}
    now = int(time.time()) if now_unix is None else int(now_unix)
    lower_bound_days = max(0.0, (now - min(times)) / 86400.0)
    return {
        "passed": lower_bound_days >= MIN_AGE_DAYS,
        "reason": "PASS" if lower_bound_days >= MIN_AGE_DAYS else "AGE_AT_LEAST_7D_NOT_PROVEN",
        "counter_token_age_days": lower_bound_days,
        "semantics": "lower_bound_from_oldest_returned_mint_signature",
        "signature_count": len(signatures),
        "history_truncated_at_1000": len(signatures) == MAX_SIGNATURES,
    }


def assess(row: Mapping[str, Any], stage2: Mapping[str, Any], rpc: RpcPool) -> dict[str, Any]:
    pool_id = str(row.get("pool_id") or "")
    result = {"llama_pool_id": pool_id, "symbol": row.get("symbol"), "passed": False}
    resolved = stage2.get("resolved") if isinstance(stage2, Mapping) else None
    onchain = stage2.get("onchain") if isinstance(stage2, Mapping) else None
    if not isinstance(resolved, Mapping) or not isinstance(onchain, Mapping) or onchain.get("passed") is not True:
        result["reason"] = "POOL_NOT_RESOLVED_AND_VERIFIED"
        return result
    try:
        mint, vault = counter_leg(row, resolved)
        holders = holder_snapshot(rpc, mint, vault)
        age = token_age_evidence(rpc, mint)
        result.update({"counter_mint": mint, "holder_snapshot": holders, "token_age": age})
        result["passed"] = holders.get("passed") is True and age.get("passed") is True
        result["reason"] = "PASS" if result["passed"] else "FAIL_CLOSED"
    except Exception as exc:
        result["reason"] = f"FAIL_CLOSED:{type(exc).__name__}:{exc}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--stage2", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fail-closed-rpc-reason", default="",
                        help="record an observed provider blocker without retrying; can only reject")
    args = parser.parse_args()
    universe = [row for row in _rows(json.loads(args.universe.read_text())) if row.get("tier") == "C"]
    stage2_rows = {
        str(row.get("llama_pool_id")): row for row in json.loads(args.stage2.read_text()).get("results") or []
    }
    rpc = RpcPool("solana")
    if args.fail_closed_rpc_reason:
        results = [{
            "llama_pool_id": row.get("pool_id"), "symbol": row.get("symbol"),
            "passed": False, "reason": "FAIL_CLOSED_RPC_UNAVAILABLE",
            "rpc_blocker": args.fail_closed_rpc_reason,
        } for row in universe]
    else:
        results = [assess(row, stage2_rows.get(str(row.get("pool_id")), {}), rpc) for row in universe]
    payload = {
        "pool_count": len(results), "pass_count": sum(row["passed"] for row in results),
        "rpc_health": rpc.health_snapshot(), "results": results,
        "signed": False, "broadcast_count": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"pool_count": payload["pool_count"], "pass_count": payload["pass_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
