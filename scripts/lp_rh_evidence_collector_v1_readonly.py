#!/usr/bin/env python3
"""RH-02j: evidence collector — fill the two remaining empty evidence tables.

RH-02h landed the writer (rh_pool_registry now has 1 row) but rh_assets and
rh_contract_attestations stayed empty: they need data sources this package
supplies. rh_assets needs the REST /rhj/assets response; rh_contract_
attestations need on-chain probe-produced attestations.

Single-writer discipline (spec-decided, do NOT change): this collector writes
scanner.db but ONLY the three evidence tables (rh_assets / rh_pool_registry /
rh_contract_attestations), disjoint from the existing collector's three
(rh_market_states / rh_rpc_health / rh_source_snapshots). SQLite WAL
serializes the two writers. Read-only research pipeline; pure offline in
tests (data fed via injected fetch_fn / rpc_fn; defaults use urllib). Never
touches wallets or writes chain state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from collections import namedtuple
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_evidence_writer_v1_readonly import (  # noqa: E402
    write_assets, write_pool_registry, write_attestations,
)
from scripts.lp_rh_registry_v1_readonly import RH_CHAIN_ID, SEED_ADDRESSES  # noqa: E402
from scripts.lp_rh_store_v1_readonly import migrate, open_store  # noqa: E402
from scripts.lp_rh_capabilities_v1_readonly import (  # noqa: E402
    _call, _default_rpc, _hex_to_int,
)

ASSETS_URL = "https://api.robinhood.com/rhj/assets"
RPC_URL = "https://rpc.mainnet.chain.robinhood.com"
BEACON = "0xe10b6f6b275de231345c20d14ab812db62151b00"
SEL_IMPLEMENTATION = "0x5c60da1b"   # EIP-1967 implementation()
_BACKOFF_SECS = (5, 15, 45, 90)
_STOP = {"flag": False}

FetchResult = namedtuple("FetchResult", ["status", "payload"])


def _default_fetch(url: str) -> FetchResult:
    """urllib GET; on HTTPError return FetchResult(code, None) (no raise)."""
    req = urllib.request.Request(url, headers={"User-Agent": "lp-bot-rh-readonly/1.0",
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as fh:
            return FetchResult(200, json.loads(fh.read().decode()))
    except urllib.error.HTTPError as exc:
        return FetchResult(exc.code, None)
    except Exception:
        return FetchResult(0, None)


def _fetch_with_backoff(fetch_fn, url, *, sleep_fn, backoff_secs=_BACKOFF_SECS):
    """fetch_fn(url) -> FetchResult. On 429, back off and retry; return last."""
    last = fetch_fn(url)
    for delay in backoff_secs:
        if last.status != 429:
            return last
        sleep_fn(delay)
        last = fetch_fn(url)
    return last


def _extract_items(payload, container_key):
    """The record list from a /rhj/assets payload, or None when unobtainable."""
    if isinstance(payload, dict):
        items = payload.get(container_key)
        return items if isinstance(items, list) else None
    if isinstance(payload, list):
        return payload
    return None


def collect_assets(fetch_fn, *, container_key="assets", sleep_fn=time.sleep,
                   backoff_secs=_BACKOFF_SECS) -> List[dict]:
    """Pull /rhj/assets and return the asset record list. The container key is
    based on actual measurement; when unobtainable, return [] and log the
    reason (do not raise)."""
    result = _fetch_with_backoff(fetch_fn, ASSETS_URL, sleep_fn=sleep_fn,
                                 backoff_secs=backoff_secs)
    if result.status != 200:
        print(f"collect_assets: HTTP {result.status}, no records", file=sys.stderr)
        return []
    items = _extract_items(result.payload, container_key)
    if items is None:
        print(f"collect_assets: container key '{container_key}' missing or "
              f"payload not a list", file=sys.stderr)
        return []
    return [item for item in items if isinstance(item, dict)]


def _block_hash(rpc_fn) -> tuple:
    """Current block hash via eth_blockNumber + eth_getBlockByNumber."""
    num, err = _call(rpc_fn, "eth_blockNumber", [])
    if err:
        return None, err
    block_num = _hex_to_int(num)
    if block_num is None:
        return None, "BLOCK_NUMBER_DECODE_FAILED"
    block, err = _call(rpc_fn, "eth_getBlockByNumber", [hex(block_num), False])
    if err:
        return None, err
    if isinstance(block, dict):
        return block.get("hash"), None
    return None, "BLOCK_NOT_DICT"


def _beacon_implementation(rpc_fn, beacon) -> Optional[str]:
    """beacon implementation() (EIP-1967) -> address, or None when
    unobtainable. This is an OPTIONAL attestation column."""
    value, err = _call(rpc_fn, "eth_call",
                       [{"to": beacon, "data": SEL_IMPLEMENTATION}, "latest"])
    if err or not isinstance(value, str) or not value.lower().startswith("0x"):
        return None
    body = value[2:]
    if len(body) < 40:
        return None
    return "0x" + body[-40:].lower()


def collect_attestations(rpc_fn, addresses, *, beacon) -> List[dict]:
    """For each address: eth_getCode -> code_hash (required), block_hash
    (required), beacon implementation() (optional -> None). Assemble the shape
    write_attestations wants. A missing required field skips the address; it
    is never written as an empty string (the writer would raise)."""
    block_hash, _ = _block_hash(rpc_fn)
    if not block_hash:
        return []  # no block_hash -> all addresses skipped
    implementation = _beacon_implementation(rpc_fn, beacon)
    records = []
    for address in addresses:
        code, err = _call(rpc_fn, "eth_getCode", [address, "latest"])
        if err or not isinstance(code, str) or code in ("0x", ""):
            continue  # no code_hash -> skip this address
        records.append({
            "address": address,
            "block_hash": block_hash,
            "attestation_status": "ATTESTED_SAME_BLOCK",
            "code_hash": hashlib.sha256(code.encode("utf-8")).hexdigest(),
            "implementation": implementation,
        })
    return records


def _record_address(record, chain_id=None):
    """One address from a record: top-level keys first, then deployments[]
    filtered by chainId. None when nothing usable (never guess: no matching
    chainId -> nothing for that record)."""
    for key in ("tokenAddress", "assetAddress", "address"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    deployments = record.get("deployments")
    if not isinstance(deployments, list) or chain_id is None:
        return None
    for deployment in deployments:
        if not isinstance(deployment, dict):
            continue
        if deployment.get("chainId") != chain_id:
            continue
        address = deployment.get("contractAddress")
        if isinstance(address, str) and address:
            return address
    return None


def _asset_addresses(asset_records, chain_id: Optional[int] = None) -> List[str]:
    """Token addresses from asset records, deduplicated, order-preserving.
    Top-level keys first; when empty, fall back to deployments[] filtered by
    chainId (never guess: no matching chainId -> nothing for that record)."""
    seen, out = set(), []
    for record in asset_records:
        value = _record_address(record, chain_id)
        if value is None:
            continue
        low = value.lower()
        if low not in seen:
            seen.add(low)
            out.append(low)
    return out


def run_once(conn, *, fetch_fn, rpc_fn, chain_id, policy_version,
             metadata_version=1, source="rh-evidence-collector-v1",
             container_key="assets", sleep_fn=time.sleep) -> Dict[str, Any]:
    """Call the three write functions in sequence. A single step's failure
    must not interrupt the others; exceptions are collected in 'errors'."""
    report: Dict[str, Any] = {"assets": {}, "pool_registry": {},
                              "attestations": {}, "errors": []}
    try:
        asset_records = collect_assets(fetch_fn, container_key=container_key,
                                       sleep_fn=sleep_fn)
    except Exception as exc:
        asset_records = []
        report["errors"].append(f"collect_assets: {exc}")
    try:
        report["assets"] = write_assets(conn, asset_records, chain_id=chain_id,
                                        metadata_version=metadata_version,
                                        source=source)
    except Exception as exc:
        report["errors"].append(f"assets: {exc}")
    try:
        candidates = [{"pool": SEED_ADDRESSES["POOL_USDG_WETH"]["address"]}]
        report["pool_registry"] = write_pool_registry(conn, candidates,
                                                      chain_id=chain_id)
    except Exception as exc:
        report["errors"].append(f"pool_registry: {exc}")
    try:
        addresses = _asset_addresses(asset_records, chain_id=chain_id)
        records = collect_attestations(rpc_fn, addresses, beacon=BEACON)
        report["attestations"] = write_attestations(conn, records,
                                                    chain_id=chain_id,
                                                    policy_version=policy_version)
        report["attestations"]["collect_skipped"] = len(addresses) - len(records)
    except Exception as exc:
        report["errors"].append(f"attestations: {exc}")
    return report


def run_loop(run_once_fn, *, period_secs, clock=time.monotonic,
             sleep_fn=time.sleep, stop_check=lambda: False, tick=1.0) -> None:
    """Run run_once_fn on a period; the deadline is measured from each round's
    START (not its end), or the period drifts."""
    while not stop_check():
        started = clock()
        run_once_fn()
        deadline = started + period_secs
        while not stop_check():
            left = deadline - clock()
            if left <= 0:
                break
            sleep_fn(min(tick, left))


def _dry_run(fetch_fn, container_key) -> int:
    """Fetch /rhj/assets and print the keys of the first two records; no DB."""
    result = _fetch_with_backoff(fetch_fn, ASSETS_URL, sleep_fn=time.sleep)
    print(f"dry-run: status={result.status}")
    items = _extract_items(result.payload, container_key)
    if items is None:
        print("dry-run: no records")
        return 0
    for item in items[:2]:
        if isinstance(item, dict):
            print("dry-run: record keys:", sorted(item.keys()))
    return 0


def _on_signal(signum, frame):
    _STOP["flag"] = True


def main(argv=None, *, fetch_fn=None, rpc_fn=None, clock=time.monotonic,
         sleep_fn=time.sleep) -> int:
    ap = argparse.ArgumentParser(description="RH evidence collector (read-only)")
    ap.add_argument("--db", required=True)
    ap.add_argument("--period-secs", type=int, default=300)
    ap.add_argument("--pid-file", default=None)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--chain-id", type=int, default=RH_CHAIN_ID)
    ap.add_argument("--policy-version", default="v1")
    ap.add_argument("--metadata-version", type=int, default=1)
    ap.add_argument("--source", default="rh-evidence-collector-v1")
    ap.add_argument("--container-key", default="assets")
    args = ap.parse_args(argv)

    if fetch_fn is None:
        fetch_fn = _default_fetch
    if rpc_fn is None:
        rpc_fn = _default_rpc(RPC_URL)

    if args.dry_run:
        return _dry_run(fetch_fn, args.container_key)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    if args.pid_file:
        Path(args.pid_file).write_text(str(os.getpid()))
    conn = open_store(args.db)
    migrate(conn)
    try:
        def do_round():
            report = run_once(conn, fetch_fn=fetch_fn, rpc_fn=rpc_fn,
                              chain_id=args.chain_id,
                              policy_version=args.policy_version,
                              metadata_version=args.metadata_version,
                              source=args.source,
                              container_key=args.container_key,
                              sleep_fn=sleep_fn)
            print(json.dumps(report, indent=2, sort_keys=True), flush=True)
        if args.once:
            do_round()
        else:
            run_loop(do_round, period_secs=args.period_secs, clock=clock,
                     sleep_fn=sleep_fn, stop_check=lambda: _STOP["flag"])
    finally:
        conn.close()
        if args.pid_file:
            try:
                os.unlink(args.pid_file)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
