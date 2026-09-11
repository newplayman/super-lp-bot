#!/usr/bin/env python3
"""BSC PancakeSwap V3 fee velocity short backfill — 8 pools × 24h/72h/7d (read-only).

Builds on the Phase 2 RPC capability matrix and the Phase 3 1-pool smoke.

For each (pool, window):
  - Resolve token0 / token1 by calling token0()/token1() on the pool (so the
    upstream pool-set CSV ordering doesn't propagate any mistake).
  - eth_getLogs in chunks (default 4000 blocks) for the PancakeSwap V3 Swap
    topic, with chunk-split retry on transient errors.
  - ABI-decode each log.
  - Compute volume_usd_proxy + pool_fee_usd_proxy.

Outputs:
  $REPORT_DIR/bsc_fee_velocity_short_backfill_results.json
  $REPORT_DIR/bsc_fee_velocity_short_backfill_results.csv
  $REPORT_DIR/bsc_swap_logs_decoded_short.csv
  $REPORT_DIR/BSC_FEE_VELOCITY_SHORT_BACKFILL_RESULTS_CN.md

Windows: 24h, 72h, 7d (NOT 14d/30d).
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
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any, Optional


SWAP_TOPIC_PANCAKE_V3 = "0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83"
BLOCK_SECONDS = 3.0
WINDOW_BLOCKS = {
    "24h": int(24 * 3600 / BLOCK_SECONDS),
    "72h": int(72 * 3600 / BLOCK_SECONDS),
    "7d":  int(7 * 24 * 3600 / BLOCK_SECONDS),
}
DEFAULT_CHUNK_BLOCKS = 4000
DEFAULT_TIMEOUT = 30

# Selectors (4-byte keccak prefix). All standard ERC20 / V3 read calls.
SEL_TOKEN0 = "0x0dfe1681"  # token0()
SEL_TOKEN1 = "0xd21220a7"  # token1()
SEL_FEE = "0xddca3f43"     # fee()
SEL_DECIMALS = "0x313ce567"  # decimals()
SEL_SYMBOL = "0x95d89b41"    # symbol()

# Heuristic USD prices for the smoke phase. Phase 5 economics preview replaces
# these with precise quotes; here we want a sanity-checkable volume proxy.
PRICES_USD = {
    "WBNB": Decimal("600"),
    "USDT": Decimal("1"),
    "USDC": Decimal("1"),
    "BUSD": Decimal("1"),
    "DAI":  Decimal("1"),
}

POOLS = [
    "0xf2688Fb5B81049DFB7703aDa5e770543770612C4",
    "0x81A9b5F18179cE2bf8f001b8a634Db80771F1824",
    "0xc721dECCD986D54B39e8c29428A1f06155c3671e",
    "0x18C5aFFA481e7EDbF37405AdE553827d6387899f",
    "0x172fcD41E0913e95784454622d1c3724f546f849",
    "0x36696169C63e42cd08ce11f5deeBbCeBae652050",
    "0x1401ff943D08a7E098328C1d3a9d388923B115D2",
    "0x6805E0E5333c5c3acCF2930Be4734E2b98f4Ce06",
]


def host_hash(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname or url
    return hashlib.sha256(host.encode()).hexdigest()[:8]


def redact(msg: str) -> str:
    if not msg:
        return ""
    out = []
    for w in msg.split():
        if w.startswith("http"):
            out.append(f"<endpoint:{host_hash(w)}>")
        else:
            out.append(w)
    return " ".join(out)[:240]


def rpc_call(url: str, method: str, params: list, timeout: int = DEFAULT_TIMEOUT) -> Any:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "lp-bot-fee-backfill/1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode())
    if "error" in payload:
        raise RuntimeError(f"rpc_error:{payload['error']}")
    return payload["result"]


def discover_url() -> tuple[str, str]:
    for key in ["BSC_RPC_PRIMARY", "LPBOT_BSC_RPC_URL", "BSC_RPC_URL", "BNB_RPC_URL", "RPC_BSC_URL"]:
        v = (os.environ.get(key) or "").strip()
        if v:
            url = v.split(",", 1)[0].strip()
            if url:
                return url, f"env:{key}"
    return "https://bsc-rpc.publicnode.com", "public_fallback:bsc-rpc.publicnode.com"


def eth_call_uint(url: str, addr: str, sel: str) -> int:
    return int(rpc_call(url, "eth_call", [{"to": addr, "data": sel}, "latest"]), 16)


def eth_call_address(url: str, addr: str, sel: str) -> str:
    res = rpc_call(url, "eth_call", [{"to": addr, "data": sel}, "latest"])
    # address is right-padded in 32 bytes
    return "0x" + res[-40:]


def eth_call_string(url: str, addr: str, sel: str) -> str:
    res = rpc_call(url, "eth_call", [{"to": addr, "data": sel}, "latest"])
    # ABI: offset (32) + length (32) + data; bytes32 fallback path too
    raw = res[2:]
    try:
        # dynamic string: bytes 64..63+length*2 (length in bytes is fields[1] / 2 since hex)
        offset = int(raw[:64], 16)
        length = int(raw[offset * 2:offset * 2 + 64], 16)
        body = raw[offset * 2 + 64:offset * 2 + 64 + length * 2]
        return bytes.fromhex(body).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        # fallback: bytes32, trim trailing nulls
        return bytes.fromhex(raw[:64]).decode("utf-8", errors="replace").rstrip("\x00")


def decode_swap(log: dict) -> dict:
    data = log["data"]
    if data.startswith("0x"):
        data = data[2:]
    if len(data) != 7 * 64:
        raise ValueError(f"swap data unexpected length {len(data)} (expected 448)")
    fields = [data[i * 64:(i + 1) * 64] for i in range(7)]

    def to_int(h: str, signed: bool, bits: int) -> int:
        # Each ABI slot is 32 bytes; for sub-256-bit fields the value is
        # sign-extended (int) or zero-padded (uint). Mask to the declared
        # width first, then apply two's complement on the low `bits` only.
        full = int(h, 16)
        mask = (1 << bits) - 1
        v = full & mask
        if signed and v >= (1 << (bits - 1)):
            v -= 1 << bits
        return v

    return {
        "sender":      "0x" + log["topics"][1][26:],
        "recipient":   "0x" + log["topics"][2][26:],
        "amount0":     to_int(fields[0], True, 256),
        "amount1":     to_int(fields[1], True, 256),
        "sqrtPriceX96": to_int(fields[2], False, 160),
        "liquidity":   to_int(fields[3], False, 128),
        "tick":        to_int(fields[4], True,  24),
        "protocolFeesToken0": to_int(fields[5], False, 128),
        "protocolFeesToken1": to_int(fields[6], False, 128),
    }


def fetch_logs_with_retry(url: str, addr: str, from_blk: int, to_blk: int) -> tuple[list[dict], list[dict]]:
    """Fetch all Swap logs for addr from from_blk..to_blk inclusive, retrying with
    chunk splitting on transient errors. Returns (logs, errors)."""
    errors: list[dict] = []
    logs: list[dict] = []
    # Try at full requested chunk first, halve recursively on failure (down to 1 block).
    stack: list[tuple[int, int]] = [(from_blk, to_blk)]
    while stack:
        a, b = stack.pop()
        q = {"fromBlock": hex(a), "toBlock": hex(b), "address": addr, "topics": [SWAP_TOPIC_PANCAKE_V3]}
        try:
            sub_logs = rpc_call(url, "eth_getLogs", [q])
            logs.extend(sub_logs)
        except Exception as exc:  # noqa: BLE001
            if a == b:
                errors.append({"from": a, "to": b, "error": redact(str(exc))})
                continue
            mid = (a + b) // 2
            # Process lower half first (LIFO stack reverse).
            stack.append((mid + 1, b))
            stack.append((a, mid))
    return logs, errors


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="BSC PancakeSwap V3 short fee-velocity backfill (24h/72h/7d).")
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--chunk-blocks", type=int, default=DEFAULT_CHUNK_BLOCKS)
    parser.add_argument("--windows", default="24h,72h,7d")
    args = parser.parse_args(argv)

    report_dir: Path = args.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    selected_windows = [w.strip() for w in args.windows.split(",") if w.strip()]
    for w in selected_windows:
        if w not in WINDOW_BLOCKS:
            print(f"ERROR: unsupported window {w}", file=sys.stderr)
            return 2

    url, source = discover_url()
    print(f"[backfill] rpc source={source} (host_hash={host_hash(url)}) chunk_blocks={args.chunk_blocks}")

    latest_block = int(rpc_call(url, "eth_blockNumber", []), 16)
    print(f"[backfill] latest_block={latest_block}")

    # --- Pool metadata ---------------------------------------------------
    pool_meta: dict[str, dict] = {}
    for addr in POOLS:
        t0 = eth_call_address(url, addr, SEL_TOKEN0)
        t1 = eth_call_address(url, addr, SEL_TOKEN1)
        fee_raw = eth_call_uint(url, addr, SEL_FEE)
        try:
            d0 = eth_call_uint(url, t0, SEL_DECIMALS)
            d1 = eth_call_uint(url, t1, SEL_DECIMALS)
            s0 = eth_call_string(url, t0, SEL_SYMBOL)
            s1 = eth_call_string(url, t1, SEL_SYMBOL)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] symbol/decimals fetch failed for pool {addr}: {redact(str(exc))}")
            d0, d1 = 18, 18
            s0, s1 = "?", "?"
        pool_meta[addr] = {
            "token0_addr": t0, "token1_addr": t1,
            "token0_symbol": s0, "token1_symbol": s1,
            "token0_decimals": d0, "token1_decimals": d1,
            "fee_tier_raw": fee_raw,
        }
        print(f"[backfill] pool={addr} token0={s0}({d0}) token1={s1}({d1}) fee_raw={fee_raw}")

    # --- Per (pool, window) backfill ------------------------------------
    rows = []
    decoded_logs_for_csv = []
    decoded_swap_log_count = 0
    total_swap_log_count = 0
    fee_ready_pool_set: set[str] = set()
    fee_ready_by_pool: dict[str, int] = {addr: 0 for addr in POOLS}
    fee_ready_by_window: dict[str, int] = {w: 0 for w in selected_windows}
    completed_pool_windows = 0
    root_cause_distribution: dict[str, int] = {}
    expected_pool_windows = len(POOLS) * len(selected_windows)

    for addr in POOLS:
        meta = pool_meta[addr]
        p0_usd = PRICES_USD.get(meta["token0_symbol"], Decimal("0"))
        p1_usd = PRICES_USD.get(meta["token1_symbol"], Decimal("0"))
        for window in selected_windows:
            wb = WINDOW_BLOCKS[window]
            from_blk = max(1, latest_block - wb)
            print(f"[backfill] {addr[:10]}... window={window} chunks=...")

            # iterate chunks of chunk_blocks each
            pool_window_logs: list[dict] = []
            pool_window_errors: list[dict] = []
            cur = from_blk
            while cur <= latest_block:
                end = min(cur + args.chunk_blocks - 1, latest_block)
                sub_logs, sub_errs = fetch_logs_with_retry(url, addr, cur, end)
                pool_window_logs.extend(sub_logs)
                pool_window_errors.extend(sub_errs)
                cur = end + 1

            # Decode
            decoded = []
            decode_errs = 0
            for log in pool_window_logs:
                try:
                    d = decode_swap(log)
                except Exception:  # noqa: BLE001
                    decode_errs += 1
                    continue
                d["pool_id"] = addr
                d["window"] = window
                d["block_number"] = int(log["blockNumber"], 16)
                d["tx_hash"] = log["transactionHash"]
                d["log_index"] = int(log["logIndex"], 16)
                decoded.append(d)

            decoded_swap_log_count += len(decoded)
            total_swap_log_count += len(pool_window_logs)

            # Volume + fee proxy
            with localcontext() as ctx:
                ctx.prec = 60
                fee_fraction = Decimal(meta["fee_tier_raw"]) / Decimal("1000000")
                volume_usd_proxy = Decimal("0")
                pool_fee_usd_proxy = Decimal("0")
                unique_traders: set[str] = set()
                for d in decoded:
                    vol0 = (Decimal(abs(d["amount0"])) / (Decimal(10) ** meta["token0_decimals"])) * p0_usd
                    vol1 = (Decimal(abs(d["amount1"])) / (Decimal(10) ** meta["token1_decimals"])) * p1_usd
                    v = max(vol0, vol1)
                    volume_usd_proxy += v
                    pool_fee_usd_proxy += v * fee_fraction
                    unique_traders.add(d["sender"])
                    unique_traders.add(d["recipient"])
                volume_usd_proxy_str = str(volume_usd_proxy.quantize(Decimal("0.01")))
                pool_fee_usd_proxy_str = str(pool_fee_usd_proxy.quantize(Decimal("0.0001")))

            partial = bool(pool_window_errors) or decode_errs > 0
            root_cause = None
            if pool_window_errors:
                root_cause = "rpc_error_after_retries"
            elif decode_errs > 0:
                root_cause = "decode_error"
            if root_cause:
                root_cause_distribution[root_cause] = root_cause_distribution.get(root_cause, 0) + 1

            fee_ready = (
                len(decoded) > 0
                and not partial
                and volume_usd_proxy > 0
                and pool_fee_usd_proxy > 0
            )
            if fee_ready:
                fee_ready_pool_set.add(addr)
                fee_ready_by_pool[addr] += 1
                fee_ready_by_window[window] += 1

            completed_pool_windows += 1

            rows.append({
                "pool_id": addr,
                "token0_symbol": meta["token0_symbol"],
                "token1_symbol": meta["token1_symbol"],
                "token_pair": f"{meta['token0_symbol']}/{meta['token1_symbol']}",
                "fee_tier_raw": meta["fee_tier_raw"],
                "window": window,
                "from_block": from_blk,
                "to_block": latest_block,
                "raw_log_count": len(pool_window_logs),
                "decoded_log_count": len(decoded),
                "decode_errors": decode_errs,
                "eth_getLogs_error_count": len(pool_window_errors),
                "unique_traders_approx": len(unique_traders),
                "volume_usd_proxy": volume_usd_proxy_str,
                "pool_fee_usd_proxy": pool_fee_usd_proxy_str,
                "partial": partial,
                "root_cause": root_cause or "",
                "fee_ready": fee_ready,
            })

            # Append a sample of decoded logs (first 50 per pool-window) to the CSV
            for d in decoded[:50]:
                decoded_logs_for_csv.append({
                    "pool_id": addr,
                    "window": window,
                    "block_number": d["block_number"],
                    "tx_hash": d["tx_hash"],
                    "log_index": d["log_index"],
                    "sender": d["sender"],
                    "recipient": d["recipient"],
                    "amount0": d["amount0"],
                    "amount1": d["amount1"],
                    "tick": d["tick"],
                })

    # --- Aggregate ------------------------------------------------------
    fee_ready_pool_count = len(fee_ready_pool_set)
    swap_log_pool_count = len({r["pool_id"] for r in rows if r["raw_log_count"] > 0})
    with localcontext() as ctx:
        ctx.prec = 60
        total_volume_usd = sum((Decimal(r["volume_usd_proxy"]) for r in rows), Decimal(0))
        total_fee_usd = sum((Decimal(r["pool_fee_usd_proxy"]) for r in rows), Decimal(0))
        volume_usd_total_str = str(total_volume_usd.quantize(Decimal("0.01")))
        pool_fee_usd_proxy_total_str = str(total_fee_usd.quantize(Decimal("0.0001")))

    summary = {
        "stage": "LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1",
        "phase": "4_8pool_short_backfill",
        "run_id": args.run_id,
        "rpc_source": source,
        "rpc_host_hash": host_hash(url),
        "chunk_blocks": args.chunk_blocks,
        "selected_windows": selected_windows,
        "selected_pool_count": len(POOLS),
        "window_count": len(selected_windows),
        "expected_pool_window_count": expected_pool_windows,
        "completed_pool_window_count": completed_pool_windows,
        "swap_log_pool_count": swap_log_pool_count,
        "decoded_swap_log_count": decoded_swap_log_count,
        "total_swap_log_count": total_swap_log_count,
        "fee_ready_pool_count": fee_ready_pool_count,
        "fee_ready_by_pool": fee_ready_by_pool,
        "fee_ready_by_window": fee_ready_by_window,
        "volume_usd_total": volume_usd_total_str,
        "pool_fee_usd_proxy_total": pool_fee_usd_proxy_total_str,
        "root_cause_distribution": root_cause_distribution,
        "rows": rows,
        "pool_metadata": pool_meta,
        "wallet_or_tx_touched": False,
        "can_run_probe_now": False,
        "tiny_canary_allowed": "no",
        "edge_proven": "no",
    }
    (report_dir / "bsc_fee_velocity_short_backfill_results.json").write_text(json.dumps(summary, indent=2) + "\n")

    csv_path = report_dir / "bsc_fee_velocity_short_backfill_results.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    decoded_csv = report_dir / "bsc_swap_logs_decoded_short.csv"
    if decoded_logs_for_csv:
        with decoded_csv.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(decoded_logs_for_csv[0].keys()))
            w.writeheader()
            w.writerows(decoded_logs_for_csv)
    else:
        decoded_csv.write_text("pool_id,window,block_number,tx_hash,log_index,sender,recipient,amount0,amount1,tick\n")

    # Markdown summary
    md = [
        "# BSC PancakeSwap V3 — 8池短窗口 fee velocity 回填",
        "",
        f"- stage: `LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1`",
        f"- run_id: `{args.run_id}`",
        f"- rpc_source: `{source}` (host_hash=`{host_hash(url)}`)",
        f"- selected_windows: `{', '.join(selected_windows)}` (no 14d/30d)",
        "",
        "## 总览",
        "",
        f"- selected_pool_count = `{len(POOLS)}`",
        f"- expected_pool_window_count = `{expected_pool_windows}`",
        f"- completed_pool_window_count = `{completed_pool_windows}`",
        f"- swap_log_pool_count = `{swap_log_pool_count}`",
        f"- decoded_swap_log_count = `{decoded_swap_log_count}`",
        f"- fee_ready_pool_count = `{fee_ready_pool_count}`",
        f"- volume_usd_total = `{summary['volume_usd_total']}`",
        f"- pool_fee_usd_proxy_total = `{summary['pool_fee_usd_proxy_total']}`",
        f"- root_cause_distribution = `{json.dumps(root_cause_distribution)}`",
        "",
        "## Per-(pool, window) 明细",
        "",
        "| pool | pair | fee | window | raw_logs | decoded | volume_usd_proxy | fee_usd_proxy | partial | fee_ready |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        md.append(
            f"| `{r['pool_id'][:10]}...` | {r['token_pair']} | {r['fee_tier_raw']} | {r['window']} | "
            f"{r['raw_log_count']} | {r['decoded_log_count']} | {r['volume_usd_proxy']} | "
            f"{r['pool_fee_usd_proxy']} | {'yes' if r['partial'] else 'no'} | "
            f"{'**yes**' if r['fee_ready'] else 'no'} |"
        )
    md += [
        "",
        "## 安全",
        "",
        "```text",
        "wallet_or_tx_touched   = false",
        "can_run_probe_now      = false",
        "tiny_canary_allowed    = no",
        "edge_proven            = no",
        "```",
    ]
    (report_dir / "BSC_FEE_VELOCITY_SHORT_BACKFILL_RESULTS_CN.md").write_text("\n".join(md) + "\n")

    print(json.dumps({
        "selected_pool_count": len(POOLS),
        "expected_pool_window_count": expected_pool_windows,
        "completed_pool_window_count": completed_pool_windows,
        "swap_log_pool_count": swap_log_pool_count,
        "decoded_swap_log_count": decoded_swap_log_count,
        "fee_ready_pool_count": fee_ready_pool_count,
        "volume_usd_total": summary["volume_usd_total"],
        "pool_fee_usd_proxy_total": summary["pool_fee_usd_proxy_total"],
    }, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
