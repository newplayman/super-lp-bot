#!/usr/bin/env python3
"""Build and simulate one FIX-E3 Solana plan; contains no signer/send path."""
from __future__ import annotations

import argparse
import base64
import hashlib
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
    build_unsigned_legacy_transaction,
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


def _successful_simulation(simulation: Any) -> Mapping[str, Any]:
    value = simulation.get("value") if isinstance(simulation, Mapping) else None
    if not isinstance(value, Mapping) or value.get("err") is not None:
        raise PolicyRejected("simulateTransaction rejected the unsigned transaction")
    return value


def _quote_from_simulation(simulation: Any) -> tuple[bool, dict[str, Any]]:
    """Accept a quote only when the unsigned transaction returned it on-chain."""
    value = _successful_simulation(simulation)
    returned = value.get("returnData")
    data = returned.get("data") if isinstance(returned, Mapping) else None
    if not isinstance(data, list) or len(data) != 2 or data[1] != "base64" or not isinstance(data[0], str):
        return False, {"source": "simulateTransaction", "reason": "SIMULATION_RETURN_DATA_UNAVAILABLE"}
    try:
        raw = base64.b64decode(data[0], validate=True)
    except Exception:
        return False, {"source": "simulateTransaction", "reason": "SIMULATION_RETURN_DATA_MALFORMED"}
    if len(raw) < 8:
        return False, {"source": "simulateTransaction", "reason": "SIMULATION_RETURN_DATA_TOO_SHORT"}
    amount_out_raw = int.from_bytes(raw[:8], "little")
    if amount_out_raw <= 0:
        return False, {"source": "simulateTransaction", "reason": "SIMULATION_QUOTE_ZERO"}
    return True, {
        "source": "simulateTransaction.returnData",
        "amount_out_raw": amount_out_raw,
        "units_consumed": value.get("unitsConsumed"),
    }


def _pool_basis_from_chain(rpc: Any, pool: str, protocol: Protocol) -> tuple[bool, dict[str, Any]]:
    """Pin basis evidence to the current, non-executable on-chain pool state."""
    response = rpc.account_info(pool)
    value = response.get("value") if isinstance(response, Mapping) else None
    if not isinstance(value, Mapping) or value.get("executable") is True:
        return False, {"source": "getAccountInfo", "reason": "POOL_STATE_UNAVAILABLE"}
    if value.get("owner") != {
        Protocol.RAYDIUM_AMM: "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
        Protocol.RAYDIUM_CLMM: "CAMMCzo5YL8w4VFF8KVrK22GGUsp5VTaW7grrKgrWqK",
        Protocol.ORCA_WHIRLPOOL: "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
    }[protocol]:
        return False, {"source": "getAccountInfo", "reason": "POOL_OWNER_PROTOCOL_MISMATCH"}
    if value.get("data") is None:
        return False, {"source": "getAccountInfo", "reason": "POOL_STATE_DATA_UNAVAILABLE"}
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    context = response.get("context") if isinstance(response.get("context"), Mapping) else {}
    return True, {
        "source": "getAccountInfo",
        "pool_state_sha256": hashlib.sha256(encoded).hexdigest(),
        "slot": context.get("slot"),
        "owner": value.get("owner"),
    }


def _int_value(value: Any, label: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise PolicyRejected(f"{label} is malformed") from exc
    if result < 0:
        raise PolicyRejected(f"{label} is negative")
    return result


def _wallet_balance_from_chain(rpc: Any, wallet: str, supplied: Mapping[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Read native and requested SPL account balances directly from RPC."""
    native_result = rpc.call("getBalance", [wallet, {"commitment": "confirmed"}])
    native_lamports = _int_value(
        native_result.get("value") if isinstance(native_result, Mapping) else None, "getBalance value"
    )
    requested = supplied.get("token_accounts", [])
    if not isinstance(requested, list) or not requested or any(not isinstance(item, str) for item in requested):
        return False, {
            "source": "getBalance/getTokenAccountBalance",
            "lamports": native_lamports,
            "token_accounts": [],
            "reason": "TOKEN_ACCOUNT_BALANCE_EVIDENCE_REQUIRED",
        }
    token_accounts = []
    token_ok = True
    for account in requested:
        result = rpc.call("getTokenAccountBalance", [account, {"commitment": "confirmed"}])
        value = result.get("value") if isinstance(result, Mapping) else None
        amount = value.get("amount") if isinstance(value, Mapping) else None
        raw = _int_value(amount, "getTokenAccountBalance amount")
        token_accounts.append({"address": account, "amount_raw": raw})
        token_ok = token_ok and raw > 0
    return native_lamports > 0 and token_ok, {
        "source": "getBalance/getTokenAccountBalance",
        "lamports": native_lamports,
        "token_accounts": token_accounts,
    }


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
        position_mint=(
            None if intent_value.get("position_mint") is None else str(intent_value["position_mint"])
        ),
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
    # These three checks intentionally never consume plan-provided booleans.
    # A first unsigned simulation provides the quote evidence; dry_run repeats
    # it after all gates exactly as the final sidecar boundary does.
    preview = build_unsigned_legacy_transaction(
        fee_payer=intent.wallet, recent_blockhash=recent_blockhash,
        last_valid_block_height=last_valid, instructions=instructions,
    )
    preview_simulation = rpc.simulate(preview)
    simulate_ok = True
    try:
        _successful_simulation(preview_simulation)
    except PolicyRejected:
        simulate_ok = False
    quote_ok, quote = _quote_from_simulation(preview_simulation) if simulate_ok else (
        False, {"source": "simulateTransaction", "reason": "SIMULATION_FAILED"}
    )
    basis_ok, basis = _pool_basis_from_chain(rpc, intent.pool, intent.protocol)
    wallet_balance_ok, wallet_balance = _wallet_balance_from_chain(rpc, intent.wallet, supplied)
    preflight = Preflight(
        simulate_ok=simulate_ok,
        quote_ok=quote_ok,
        basis_ok=basis_ok,
        rpc_health_ok=True,
        wallet_balance_ok=wallet_balance_ok,
        simulation={"source": "simulateTransaction", "result": preview_simulation},
        quote=quote,
        basis=basis,
        rpc_health={"genesis_hash": genesis_hash, "block_height": current_height},
        wallet_balance=wallet_balance,
    )
    mint_evidence = [asdict(read_mint_semantics(rpc, mint, now)) for mint in intent.token_mints]
    dry_ledger = Ledger(out_path.parent / ".dry-run-ledger-must-not-exist.jsonl")
    if not all((simulate_ok, quote_ok, basis_ok, wallet_balance_ok)):
        # A failed runner preflight is still an auditable read-only result, not
        # an exception that can be mistaken for a skipped check.
        report = {
            "stage": "E3_SOLANA_DRY_RUN",
            "network": "solana_mainnet",
            "intent": {"action": intent.action.value, "protocol": intent.protocol.value},
            "preflight": {
                "simulate": simulate_ok, "quote": quote_ok, "basis": basis_ok,
                "rpc_health": True, "wallet_balance": wallet_balance_ok,
            },
            "preflight_all_pass": False,
            "simulation_result": preview_simulation,
            "broadcast_count": 0, "signed": False, "raw_transaction": None,
            "transaction_signatures": [], "keystore_loaded": False,
        }
    else:
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
