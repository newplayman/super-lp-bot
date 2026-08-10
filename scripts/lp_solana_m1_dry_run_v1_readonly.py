#!/usr/bin/env python3
"""Build and simulate one FIX-E3 Solana plan; contains no signer/send path."""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.solana_m1_sidecar_v1 import (
    SOLANA_MAINNET_GENESIS_HASH,
    AccountMeta,
    Action,
    ExecutionPolicy,
    Instruction,
    Intent,
    Ledger,
    PolicyRejected,
    Preflight,
    Protocol,
    SolanaRpc,
    dry_run,
    read_mint_semantics,
)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PolicyRejected(f"{label} must be an object")
    return value


def _instructions(rows: Any) -> list[Instruction]:
    if not isinstance(rows, list) or not rows:
        raise PolicyRejected("instructions must be a non-empty list")
    result = []
    for row_value in rows:
        row = _mapping(row_value, "instruction")
        account_values = row.get("accounts") or []
        if not isinstance(account_values, list):
            raise PolicyRejected("instruction accounts must be a list")
        accounts = tuple(
            AccountMeta(
                str(_mapping(item, "account")["pubkey"]),
                bool(_mapping(item, "account").get("is_signer", False)),
                bool(_mapping(item, "account").get("is_writable", False)),
            )
            for item in account_values
        )
        try:
            data = base64.b64decode(str(row["data_base64"]), validate=True)
        except Exception as exc:
            raise PolicyRejected("instruction data_base64 is malformed") from exc
        action_value = row.get("semantic_action")
        result.append(
            Instruction(
                str(row["program_id"]),
                accounts,
                data,
                None if action_value is None else Action(str(action_value)),
            )
        )
    return result


def run(plan: Mapping[str, Any], out_path: Path, rpc: Any, now_unix: int | None = None) -> dict[str, Any]:
    """Run against a supplied RPC; production CLI supplies the read/simulate-only client."""
    now = int(time.time()) if now_unix is None else int(now_unix)
    intent_value = _mapping(plan.get("intent"), "intent")
    protocol = Protocol(str(intent_value["protocol"]))
    action = Action(str(intent_value["action"]))
    token_mints_value = intent_value.get("token_mints")
    if not isinstance(token_mints_value, list) or not token_mints_value:
        raise PolicyRejected("intent token_mints must be a non-empty list")
    intent = Intent(
        protocol=protocol,
        action=action,
        wallet=str(intent_value["wallet"]),
        pool=str(intent_value["pool"]),
        token_mints=tuple(str(item) for item in token_mints_value),
        strategy_decision_id=str(intent_value["strategy_decision_id"]),
        risk_verdict_id=str(intent_value["risk_verdict_id"]),
        idempotency_key=str(intent_value["idempotency_key"]),
        notional_usd=float(intent_value["notional_usd"]),
        slippage_bps=int(intent_value["slippage_bps"]),
        deadline_unix=int(intent_value.get("deadline_unix", now + 120)),
        reduces_risk=bool(intent_value.get("reduces_risk", False)),
    )
    instructions = _instructions(plan.get("instructions"))
    supplied = _mapping(plan.get("preflight"), "preflight")

    genesis_hash = rpc.call("getGenesisHash", [])
    if genesis_hash != SOLANA_MAINNET_GENESIS_HASH:
        raise PolicyRejected(f"refusing non-mainnet Solana genesis hash: {genesis_hash}")
    latest = _mapping(rpc.call("getLatestBlockhash", [{"commitment": "confirmed"}]), "blockhash response")
    blockhash_value = _mapping(latest.get("value"), "blockhash value")
    recent_blockhash = str(blockhash_value["blockhash"])
    last_valid = int(blockhash_value["lastValidBlockHeight"])
    current_height = int(rpc.call("getBlockHeight", [{"commitment": "confirmed"}]))
    preflight = Preflight(
        # The actual simulation is repeated and authoritatively checked inside dry_run.
        simulate_ok=True,
        quote_ok=supplied.get("quote_ok") is True,
        basis_ok=supplied.get("basis_ok") is True,
        rpc_health_ok=True,
        wallet_balance_ok=supplied.get("wallet_balance_ok") is True,
        simulation={"source": "same-run simulateTransaction"},
        quote=_mapping(supplied.get("quote"), "quote evidence"),
        basis=_mapping(supplied.get("basis"), "basis evidence"),
        rpc_health={"genesis_hash": genesis_hash, "block_height": current_height},
        wallet_balance=_mapping(supplied.get("wallet_balance"), "wallet balance evidence"),
    )
    mint_evidence = [asdict(read_mint_semantics(rpc, mint, now)) for mint in intent.token_mints]
    dry_ledger = Ledger(out_path.parent / ".dry-run-ledger-must-not-exist.jsonl")
    report = dict(
        dry_run(
            intent=intent,
            preflight=preflight,
            instructions=instructions,
            recent_blockhash=recent_blockhash,
            last_valid_block_height=last_valid,
            current_block_height=current_height,
            rpc=rpc,
            policy=ExecutionPolicy(
                allowed_pools=frozenset({intent.pool}), allowed_mints=frozenset(intent.token_mints)
            ),
            ledger=dry_ledger,
            now=lambda: now,
        )
    )
    if dry_ledger.path.exists():
        raise RuntimeError("dry-run invariant violated: execution ledger was written")
    report["genesis_hash"] = genesis_hash
    report["mint_semantics"] = mint_evidence
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True, help="reviewed unsigned instruction plan JSON")
    parser.add_argument("--rpc-url", required=True, help="free Solana mainnet RPC URL")
    parser.add_argument("--out", type=Path, required=True, help="C5-shaped JSON report path")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    run(_mapping(plan, "plan"), args.out, SolanaRpc(args.rpc_url))
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
