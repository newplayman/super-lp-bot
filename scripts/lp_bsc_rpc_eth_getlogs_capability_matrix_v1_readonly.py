#!/usr/bin/env python3
"""BSC RPC eth_getLogs capability matrix (read-only).

For each candidate BSC RPC endpoint (env-var sourced + public fallbacks),
exercise:
  - eth_chainId       (must equal 0x38 / 56)
  - eth_blockNumber
  - eth_getCode(pool) (sanity check; bytecode exists)
  - eth_getLogs at chunk sizes 500 / 1000 / 2000 / 4000 blocks, topic =
    PancakeSwap V3 Swap, against two pools (WBNB/USDT fee=100,
    WBNB/USDC fee=100).

Outputs:
  $REPORT_DIR/bsc_rpc_eth_getlogs_capability_matrix.json
  $REPORT_DIR/bsc_rpc_eth_getlogs_capability_matrix.csv
  $REPORT_DIR/BSC_RPC_ETH_GETLOGS_CAPABILITY_MATRIX_CN.md
  $REPORT_DIR/BSC_RPC_REQUIRED_CN.md  (only if no usable endpoint)

Safety:
  - NO wallet, signer, keystore, eth_sendTransaction, eth_sendRawTransaction.
  - Only eth_call (for getCode) and eth_getLogs.
  - Endpoints are referenced by a stable 8-char hash of the host; the URL is
    never printed in stdout, in the JSON, or in any committed file.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


SWAP_TOPIC_PANCAKE_V3 = "0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83"
# Uniswap V3 Swap is 0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67
# (PancakeSwap V3's event adds protocolFeesToken0/1 fields, so the topic differs.)
SWAP_TOPIC_V3 = SWAP_TOPIC_PANCAKE_V3  # public name kept for backward-compat readers
BSC_CHAIN_ID_HEX = "0x38"

# Reflect the runner's defaults so the matrix tests what the runner would actually use.
RPC_ENV_KEYS = [
    "BSC_RPC_PRIMARY",
    "LPBOT_BSC_RPC_URL",
    "BSC_RPC_URL",
    "BNB_RPC_URL",
    "RPC_BSC_URL",
    "LPBOT_BSC_RPC_FALLBACK",
]
PUBLIC_FALLBACKS = [
    ("bsc-dataseed.binance.org", "https://bsc-dataseed.binance.org"),
    ("bsc-dataseed1.defibit.io",  "https://bsc-dataseed1.defibit.io"),
    ("bsc-rpc.publicnode.com",    "https://bsc-rpc.publicnode.com"),
    ("rpc.ankr.com/bsc",          "https://rpc.ankr.com/bsc"),
    ("binance.nodereal.io",       "https://binance.nodereal.io"),
]

POOLS_TO_TEST = [
    ("WBNB/USDT-100", "0x172fcD41E0913e95784454622d1c3724f546f849"),
    ("WBNB/USDC-100", "0xf2688Fb5B81049DFB7703aDa5e770543770612C4"),
]
CHUNK_SIZES = [500, 1000, 2000, 4000]
PER_CALL_TIMEOUT = 15
PER_CALL_RETRIES = 1


def host_hash(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname or url
    return hashlib.sha256(host.encode()).hexdigest()[:8]


def redact_error(msg: str) -> str:
    if not msg:
        return ""
    # Strip any embedded URL substring so error text never contains a full endpoint.
    out = []
    for word in msg.split():
        if word.startswith("http://") or word.startswith("https://"):
            try:
                h = urllib.parse.urlparse(word).hostname
                out.append(f"<endpoint:{host_hash(word)}@{h.split('.')[-2] if h and '.' in h else 'host'}>")
            except Exception:
                out.append("<endpoint:redacted>")
        else:
            out.append(word)
    return " ".join(out)[:240]


def rpc_call(url: str, method: str, params: list, timeout: int = PER_CALL_TIMEOUT) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last_err = None
    for _ in range(PER_CALL_RETRIES + 1):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "lp-bot-rpc-matrix/1"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode())
            if "error" in payload:
                last_err = f"rpc_error:{payload['error']}"
                continue
            return payload
        except urllib.error.HTTPError as exc:
            last_err = f"http:{exc.code}"
        except urllib.error.URLError as exc:
            last_err = f"url:{type(exc.reason).__name__}"
        except (TimeoutError, ConnectionError) as exc:
            last_err = f"conn:{type(exc).__name__}"
        except Exception as exc:  # noqa: BLE001
            last_err = f"other:{type(exc).__name__}"
    raise RuntimeError(last_err or "unknown")


@dataclass
class EndpointResult:
    endpoint_id: str
    source: str
    host_hash: str
    chain_id_ok: bool = False
    latest_block_ok: bool = False
    latest_block: Optional[int] = None
    getcode_ok: bool = False
    getcode_pools_with_bytecode: list = field(default_factory=list)
    chunk_results: dict = field(default_factory=dict)
    recommended_chunk_size: Optional[int] = None
    usable_for_backfill: bool = False
    confidence: str = "low"
    error_type: Optional[str] = None
    error_message_redacted: Optional[str] = None
    notes: list = field(default_factory=list)


def test_endpoint(endpoint_id: str, source: str, url: str) -> EndpointResult:
    res = EndpointResult(endpoint_id=endpoint_id, source=source, host_hash=host_hash(url))

    # chainId
    try:
        cid = rpc_call(url, "eth_chainId", [])["result"]
        res.chain_id_ok = cid.lower() == BSC_CHAIN_ID_HEX
        if not res.chain_id_ok:
            res.error_type = "wrong_chain"
            res.error_message_redacted = f"chainId={cid} expected={BSC_CHAIN_ID_HEX}"
            return res
    except Exception as exc:  # noqa: BLE001
        res.error_type = "chainId_failed"
        res.error_message_redacted = redact_error(str(exc))
        return res

    # blockNumber
    try:
        blk_hex = rpc_call(url, "eth_blockNumber", [])["result"]
        res.latest_block = int(blk_hex, 16)
        res.latest_block_ok = res.latest_block > 0
    except Exception as exc:  # noqa: BLE001
        res.error_type = "blockNumber_failed"
        res.error_message_redacted = redact_error(str(exc))
        return res

    # getCode for each pool (we want both to return non-0x bytecode)
    bytecode_ok_pools = []
    for label, addr in POOLS_TO_TEST:
        try:
            code = rpc_call(url, "eth_getCode", [addr, "latest"])["result"]
            if code and code != "0x":
                bytecode_ok_pools.append(label)
        except Exception as exc:  # noqa: BLE001
            res.notes.append(f"getCode({label}) failed: {redact_error(str(exc))}")
    res.getcode_ok = len(bytecode_ok_pools) == len(POOLS_TO_TEST)
    res.getcode_pools_with_bytecode = bytecode_ok_pools
    if not res.getcode_ok:
        res.error_type = "getCode_incomplete"
        res.error_message_redacted = f"got_bytecode_for={bytecode_ok_pools}"
        # still proceed to test getLogs — many providers limit getCode but allow logs

    # eth_getLogs at multiple chunk sizes; use a recent window ending at latest_block
    end_block = res.latest_block
    successful_chunk_sizes = []
    for chunk in CHUNK_SIZES:
        from_block = max(1, end_block - chunk)
        any_pool_ok = False
        total_logs = 0
        pool_outcomes = {}
        for label, addr in POOLS_TO_TEST:
            query = {
                "fromBlock": hex(from_block),
                "toBlock": hex(end_block),
                "address": addr,
                "topics": [SWAP_TOPIC_V3],
            }
            try:
                payload = rpc_call(url, "eth_getLogs", [query], timeout=PER_CALL_TIMEOUT)
                logs = payload.get("result", [])
                pool_outcomes[label] = {"ok": True, "log_count": len(logs)}
                total_logs += len(logs)
                any_pool_ok = True
            except Exception as exc:  # noqa: BLE001
                pool_outcomes[label] = {"ok": False, "error": redact_error(str(exc))}
        res.chunk_results[str(chunk)] = {
            "any_pool_ok": any_pool_ok,
            "total_logs": total_logs,
            "pool_outcomes": pool_outcomes,
            "from_block": from_block,
            "to_block": end_block,
        }
        if any_pool_ok:
            successful_chunk_sizes.append(chunk)

    if successful_chunk_sizes:
        # Pick the largest chunk that still works — fewer round trips per backfill.
        res.recommended_chunk_size = max(successful_chunk_sizes)
        # Confidence: env-sourced > public fallback; both pools returning logs > only one.
        decoded_both = all(
            res.chunk_results[str(res.recommended_chunk_size)]["pool_outcomes"][label]["ok"]
            for label, _ in POOLS_TO_TEST
        )
        res.usable_for_backfill = True
        if source.startswith("env:") and decoded_both and res.recommended_chunk_size >= 1000:
            res.confidence = "high"
        elif decoded_both:
            res.confidence = "medium"
        else:
            res.confidence = "low"

    return res


def discover_endpoints() -> list[tuple[str, str, str]]:
    """Yield (endpoint_id, source, url). Env entries first, then public fallbacks."""
    seen_urls = set()
    out = []
    for key in RPC_ENV_KEYS:
        val = os.environ.get(key)
        if not val:
            continue
        for url in [u.strip() for u in val.split(",") if u.strip()]:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            out.append((f"env_{host_hash(url)}", f"env:{key}", url))
    for label, url in PUBLIC_FALLBACKS:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        out.append((f"pub_{host_hash(url)}", f"public_fallback:{label}", url))
    return out


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="BSC RPC eth_getLogs capability matrix (read-only).")
    parser.add_argument("--report-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    args.report_dir.mkdir(parents=True, exist_ok=True)
    endpoints = discover_endpoints()
    results = []
    for endpoint_id, source, url in endpoints:
        print(f"[matrix] testing endpoint_id={endpoint_id} source={source}")
        try:
            res = test_endpoint(endpoint_id, source, url)
        except Exception as exc:  # noqa: BLE001
            res = EndpointResult(
                endpoint_id=endpoint_id,
                source=source,
                host_hash=host_hash(url),
                error_type="harness_exception",
                error_message_redacted=redact_error(str(exc)),
            )
        results.append(res)

    # Persist
    json_path = args.report_dir / "bsc_rpc_eth_getlogs_capability_matrix.json"
    csv_path = args.report_dir / "bsc_rpc_eth_getlogs_capability_matrix.csv"
    md_path = args.report_dir / "BSC_RPC_ETH_GETLOGS_CAPABILITY_MATRIX_CN.md"

    summary = {
        "stage": "LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1",
        "phase": "2_bsc_rpc_eth_getlogs_capability_matrix",
        "endpoint_count": len(results),
        "usable_count": sum(1 for r in results if r.usable_for_backfill),
        "high_confidence_count": sum(1 for r in results if r.confidence == "high"),
        "results": [asdict(r) for r in results],
    }
    json_path.write_text(json.dumps(summary, indent=2) + "\n")

    with csv_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "endpoint_id", "source", "host_hash",
            "chain_id_ok", "latest_block_ok", "latest_block", "getcode_ok",
            "getlogs_500_ok", "getlogs_1000_ok", "getlogs_2000_ok", "getlogs_4000_ok",
            "recommended_chunk_size", "usable_for_backfill", "confidence",
            "error_type", "error_message_redacted",
        ])
        for r in results:
            def chunk_ok(c):
                d = r.chunk_results.get(str(c)) or {}
                return "yes" if d.get("any_pool_ok") else "no"
            w.writerow([
                r.endpoint_id, r.source, r.host_hash,
                "yes" if r.chain_id_ok else "no",
                "yes" if r.latest_block_ok else "no",
                r.latest_block if r.latest_block is not None else "",
                "yes" if r.getcode_ok else "no",
                chunk_ok(500), chunk_ok(1000), chunk_ok(2000), chunk_ok(4000),
                r.recommended_chunk_size if r.recommended_chunk_size else "",
                "yes" if r.usable_for_backfill else "no",
                r.confidence,
                r.error_type or "",
                r.error_message_redacted or "",
            ])

    # Markdown summary
    md_lines = [
        "# BSC RPC eth_getLogs capability matrix",
        "",
        f"- stage: `LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1`",
        f"- endpoint_count: `{summary['endpoint_count']}`",
        f"- usable_count: `{summary['usable_count']}`",
        f"- high_confidence_count: `{summary['high_confidence_count']}`",
        "",
        "| endpoint_id | source | chainId | block | getCode | 500 | 1000 | 2000 | 4000 | rec | usable | conf | err |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        def ck(c):
            d = r.chunk_results.get(str(c)) or {}
            return "✓" if d.get("any_pool_ok") else "✗"
        md_lines.append(
            f"| `{r.endpoint_id}` | `{r.source}` | "
            f"{'✓' if r.chain_id_ok else '✗'} | "
            f"{'✓' if r.latest_block_ok else '✗'} | "
            f"{'✓' if r.getcode_ok else '✗'} | "
            f"{ck(500)} | {ck(1000)} | {ck(2000)} | {ck(4000)} | "
            f"{r.recommended_chunk_size or '-'} | "
            f"{'yes' if r.usable_for_backfill else 'no'} | "
            f"{r.confidence} | {r.error_type or ''} |"
        )
    md_lines += [
        "",
        "## Note",
        "",
        "Endpoint URLs are not printed (only an 8-char SHA-256 of the host). 'env:*' entries come from BSC_RPC_PRIMARY / LPBOT_BSC_RPC_URL / BSC_RPC_URL / BNB_RPC_URL / RPC_BSC_URL / LPBOT_BSC_RPC_FALLBACK environment variables.",
    ]
    md_path.write_text("\n".join(md_lines) + "\n")

    # Print verdict to stdout for Phase 7 harvesting
    print(json.dumps({
        "endpoint_count": summary["endpoint_count"],
        "usable_count": summary["usable_count"],
        "best_usable_endpoint_id": next((r.endpoint_id for r in results if r.usable_for_backfill), None),
        "best_chunk_size": next((r.recommended_chunk_size for r in results if r.usable_for_backfill), None),
    }, indent=2))

    if summary["usable_count"] == 0:
        # Write BSC_RPC_REQUIRED hint
        (args.report_dir / "BSC_RPC_REQUIRED_CN.md").write_text(
            "# BSC RPC required\n\n"
            "No tested endpoint returned eth_getLogs successfully on any chunk size for the\n"
            "two BSC PancakeSwap V3 pools. The pipeline cannot continue without a usable\n"
            "endpoint. recommended_next_stage = BSC_RPC_SETUP_REQUIRED.\n"
        )

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
