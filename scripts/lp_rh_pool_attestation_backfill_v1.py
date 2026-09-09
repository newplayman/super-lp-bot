#!/usr/bin/env python3
"""RH-02bc: backfill contract attestations for CORE pool and underlying tokens.

Resolves target addresses (pool contract, token0, token1) and gathers
same-block bytecode attestations into rh_contract_attestations.
Reuses collect_attestations and write_attestations without reinventing logic.
Default mode is --dry-run (zero network calls, zero DB writes).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_capabilities_v1_readonly import _default_rpc  # noqa: E402
from scripts.lp_rh_evidence_collector_v1_readonly import (  # noqa: E402
    BEACON, collect_attestations, collect_pool_properties,
)
from scripts.lp_rh_evidence_writer_v1_readonly import write_attestations  # noqa: E402
from scripts.lp_rh_registry_v1_readonly import RH_CHAIN_ID, SEED_ADDRESSES  # noqa: E402
from scripts.lp_rh_store_v1_readonly import DEFAULT_DB_PATH, migrate, open_store  # noqa: E402

RPC_URL = "https://rpc.mainnet.chain.robinhood.com"
DEFAULT_POOL_META_PATH = REPO_ROOT / "reports/lp_rh/pool_meta.json"
_HEX_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _is_valid_address(val: Any) -> bool:
    return isinstance(val, str) and bool(_HEX_ADDR_RE.match(val.strip()))


def resolve_target_addresses(
    conn: Optional[sqlite3.Connection],
    *,
    pool_address: Optional[str] = None,
    pool_meta_path: Optional[Union[str, Path]] = None,
    rpc_fn: Optional[Callable] = None,
    allow_network: bool = False,
) -> Dict[str, Any]:
    """Resolve pool, token0, and token1 addresses and trace their source."""
    if pool_address is not None:
        if not _is_valid_address(pool_address):
            raise ValueError(f"INVALID_POOL_ADDRESS: {pool_address}")
        pool_addr, pool_src = pool_address.strip().lower(), "cli_arg"
    else:
        pool_addr, pool_src = None, None
        if conn is not None:
            row = conn.execute("SELECT pool_address, pool_key FROM rh_pool_registry LIMIT 1").fetchone()
            if row and (row[0] or row[1]) and _is_valid_address(row[0] or row[1]):
                pool_addr, pool_src = (row[0] or row[1]).strip().lower(), "rh_pool_registry"
        if pool_addr is None:
            seed = SEED_ADDRESSES.get("POOL_USDG_WETH", {}).get("address")
            if seed and _is_valid_address(str(seed)):
                pool_addr, pool_src = str(seed).strip().lower(), "seed_addresses:POOL_USDG_WETH"
            else:
                raise ValueError("MISSING_POOL_ADDRESS: unable to determine pool address")

    token0, token0_src = None, None
    token1, token1_src = None, None

    if conn is not None:
        row = conn.execute(
            "SELECT token0, token1 FROM rh_pool_registry "
            "WHERE LOWER(pool_address) = LOWER(?) OR LOWER(pool_key) = LOWER(?) LIMIT 1",
            (pool_addr, pool_addr),
        ).fetchone()
        if row:
            if row[0] and _is_valid_address(row[0]):
                token0, token0_src = row[0].strip().lower(), "rh_pool_registry"
            if row[1] and _is_valid_address(row[1]):
                token1, token1_src = row[1].strip().lower(), "rh_pool_registry"

    if (token0 is None or token1 is None) and pool_meta_path:
        p = Path(pool_meta_path)
        if p.is_file():
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(meta, dict):
                    if token0 is None and meta.get("token0") and _is_valid_address(meta["token0"]):
                        token0, token0_src = meta["token0"].strip().lower(), f"pool_meta:{p.name}"
                    if token1 is None and meta.get("token1") and _is_valid_address(meta["token1"]):
                        token1, token1_src = meta["token1"].strip().lower(), f"pool_meta:{p.name}"
            except Exception:
                pass

    if (token0 is None or token1 is None) and allow_network and rpc_fn:
        props = collect_pool_properties(rpc_fn, pool_addr)
        if token0 is None and props.get("token0") and _is_valid_address(props["token0"]):
            token0, token0_src = props["token0"].strip().lower(), "on_chain_rpc:eth_call"
        if token1 is None and props.get("token1") and _is_valid_address(props["token1"]):
            token1, token1_src = props["token1"].strip().lower(), "on_chain_rpc:eth_call"

    if not token0 or not _is_valid_address(token0):
        raise ValueError(f"MISSING_OR_INVALID_TOKEN0: unable to determine token0 for pool {pool_addr}")
    if not token1 or not _is_valid_address(token1):
        raise ValueError(f"MISSING_OR_INVALID_TOKEN1: unable to determine token1 for pool {pool_addr}")

    targets = [
        {"address": pool_addr, "role": "pool", "source": pool_src},
        {"address": token0, "role": "token0", "source": token0_src},
        {"address": token1, "role": "token1", "source": token1_src},
    ]
    return {"pool": {"address": pool_addr, "source": pool_src},
            "token0": {"address": token0, "source": token0_src},
            "token1": {"address": token1, "source": token1_src},
            "targets": targets}


def estimate_rpc_calls(targets: List[Dict[str, Any]]) -> Dict[str, int]:
    """Estimate RPC call budget for the backfill run."""
    n = len(targets)
    calls = {
        "eth_blockNumber": 1,
        "eth_getBlockByNumber": 1,
        "beacon_implementation_call": 1,
        "eth_getCode": n,
    }
    calls["total"] = sum(calls.values())
    return calls


def plan_backfill(
    conn: Optional[sqlite3.Connection],
    *,
    pool_address: Optional[str] = None,
    pool_meta_path: Optional[Union[str, Path]] = DEFAULT_POOL_META_PATH,
    chain_id: int = RH_CHAIN_ID,
    policy_version: str = "v1",
) -> Dict[str, Any]:
    """Pure offline plan for dry-run."""
    res = resolve_target_addresses(conn, pool_address=pool_address,
                                   pool_meta_path=pool_meta_path,
                                   allow_network=False)
    targets = res["targets"]
    return {
        "mode": "dry-run",
        "status": "PLAN_READY",
        "chain_id": chain_id,
        "policy_version": policy_version,
        "target_pool": res["pool"]["address"],
        "target_addresses": targets,
        "expected_writes": {"rh_contract_attestations": len(targets)},
        "estimated_rpc_calls": estimate_rpc_calls(targets),
        "network_calls_made": 0,
        "db_writes_made": 0,
    }


def apply_backfill(
    conn: sqlite3.Connection,
    *,
    rpc_fn: Callable,
    pool_address: Optional[str] = None,
    pool_meta_path: Optional[Union[str, Path]] = DEFAULT_POOL_META_PATH,
    beacon: str = BEACON,
    chain_id: int = RH_CHAIN_ID,
    policy_version: str = "v1",
) -> Dict[str, Any]:
    """Execute on-chain collection and persist to rh_contract_attestations."""
    res = resolve_target_addresses(conn, pool_address=pool_address,
                                   pool_meta_path=pool_meta_path,
                                   rpc_fn=rpc_fn, allow_network=True)
    targets = res["targets"]
    target_addrs = [t["address"] for t in targets]
    skip_reasons: Dict[str, str] = {}
    records = collect_attestations(rpc_fn, target_addrs, beacon=beacon, skip_out=skip_reasons)
    write_res = write_attestations(conn, records, chain_id=chain_id, policy_version=policy_version)
    return {
        "mode": "apply",
        "status": "APPLIED",
        "chain_id": chain_id,
        "policy_version": policy_version,
        "target_pool": res["pool"]["address"],
        "target_addresses": targets,
        "collected_records": len(records),
        "write_result": write_res,
        "skip_reasons": skip_reasons,
    }


def main(argv=None, *, rpc_fn: Optional[Callable] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill CORE pool contract attestations (default: --dry-run)"
    )
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="path to scanner.db")
    parser.add_argument("--pool-address", default=None, help="target pool address")
    parser.add_argument("--pool-meta", default=str(DEFAULT_POOL_META_PATH), help="path to pool_meta.json")
    parser.add_argument("--rpc-url", default=RPC_URL, help="chain RPC URL")
    parser.add_argument("--beacon", default=BEACON, help="beacon address")
    parser.add_argument("--chain-id", type=int, default=RH_CHAIN_ID)
    parser.add_argument("--policy-version", default="v1")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="plan only, make no network calls and no DB writes (default)")
    parser.add_argument("--apply", action="store_true", default=False,
                        help="execute RPC collection and write to database")
    parser.add_argument("--out", default=None, help="write JSON output to file")
    args = parser.parse_args(argv)

    is_apply = bool(args.apply and not args.dry_run)

    if not is_apply:
        db_path = Path(args.db)
        conn = None
        if db_path.exists():
            conn = open_store(db_path, read_only=True)
        try:
            plan = plan_backfill(
                conn, pool_address=args.pool_address,
                pool_meta_path=args.pool_meta,
                chain_id=args.chain_id, policy_version=args.policy_version,
            )
        finally:
            if conn is not None:
                conn.close()
        out = json.dumps(plan, indent=2, sort_keys=True)
        if args.out:
            Path(args.out).write_text(out + "\n", encoding="utf-8")
        print(out)
        return 0

    conn = open_store(args.db)
    try:
        migrate(conn)
        if rpc_fn is None:
            rpc_fn = _default_rpc(args.rpc_url)
        res = apply_backfill(
            conn, rpc_fn=rpc_fn, pool_address=args.pool_address,
            pool_meta_path=args.pool_meta, beacon=args.beacon,
            chain_id=args.chain_id, policy_version=args.policy_version,
        )
    finally:
        conn.close()

    out = json.dumps(res, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(out + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
