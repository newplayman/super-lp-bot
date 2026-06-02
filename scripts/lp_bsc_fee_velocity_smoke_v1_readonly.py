#!/usr/bin/env python3
"""BSC PancakeSwap V3 fee velocity smoke — 1 pool, 24h (read-only).

Validates the recovered-topic pipeline against a single high-volume pool
before running the 8-pool short backfill (Phase 4).

Pool (default):
  WBNB/USDT 0.01%  0x172fcD41E0913e95784454622d1c3724f546f849

Window: 24h via BSC ≈ 28800 blocks (3 s/block). Chunked with the chunk
size recommended by the Phase 2 capability matrix.

Outputs:
  $REPORT_DIR/bsc_fee_velocity_1pool_24h_smoke.json
  $REPORT_DIR/bsc_fee_velocity_1pool_24h_smoke.csv
  $REPORT_DIR/BSC_FEE_VELOCITY_1POOL_24H_SMOKE_CN.md

Pass requires:
  - selected_pool_loaded = yes
  - eth_getLogs_success  = yes (no errors across all chunks)
  - decode_success       = yes (all logs ABI-decoded without exception)
  - decoded_log_count    > 0

Safety: read-only. No wallet, signer, keystore, eth_sendTransaction,
eth_sendRawTransaction, swap/mint/burn/collect/approve calls.
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
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Optional


getcontext().prec = 50

SWAP_TOPIC_PANCAKE_V3 = "0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83"
DEFAULT_POOL = "0x172fcD41E0913e95784454622d1c3724f546f849"  # WBNB/USDT fee=100
# Pool token ordering follows the on-chain rule token0 < token1 by address.
# For 0x172fcD41... the tokens are USDT (0x55d398...) and WBNB (0xbb4CdB...),
# and 0x55 < 0xbb, so token0=USDT, token1=WBNB.
DEFAULT_TOKEN0 = "USDT"
DEFAULT_TOKEN1 = "WBNB"
DEFAULT_FEE_TIER_RAW = 100  # 0.01% in 1e6 units
# Heuristic prices for USD proxy (smoke doesn't need precision; downstream phases pull real quotes).
DEFAULT_PRICES_USD = {"WBNB": Decimal("600"), "USDT": Decimal("1"), "USDC": Decimal("1")}
# BSC mainnet decimals: WBNB=18, USDT=18 (BEP-20 differs from ETH mainnet), USDC=18.
DEFAULT_DECIMALS = {"WBNB": 18, "USDT": 18, "USDC": 18}

BLOCK_SECONDS = 3.0
WINDOW_SECONDS_24H = 24 * 3600
DEFAULT_WINDOW_BLOCKS = int(WINDOW_SECONDS_24H / BLOCK_SECONDS)  # 28800
DEFAULT_CHUNK_BLOCKS = 4000
DEFAULT_TIMEOUT = 25


def host_hash(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname or url
    return hashlib.sha256(host.encode()).hexdigest()[:8]


def redact_error(msg: str) -> str:
    if not msg:
        return ""
    out = []
    for word in msg.split():
        if word.startswith("http://") or word.startswith("https://"):
            out.append(f"<endpoint:{host_hash(word)}>")
        else:
            out.append(word)
    return " ".join(out)[:240]


def rpc_call(url: str, method: str, params: list, timeout: int = DEFAULT_TIMEOUT) -> Any:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "lp-bot-fee-smoke/1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode())
    if "error" in payload:
        raise RuntimeError(f"rpc_error:{payload['error']}")
    return payload["result"]


def discover_url() -> tuple[str, str]:
    """Return (url, source). Honors env vars before falling back to publicnode."""
    for key in ["BSC_RPC_PRIMARY", "LPBOT_BSC_RPC_URL", "BSC_RPC_URL", "BNB_RPC_URL", "RPC_BSC_URL"]:
        val = (os.environ.get(key) or "").strip()
        if val:
            url = val.split(",", 1)[0].strip()
            if url:
                return url, f"env:{key}"
    return "https://bsc-rpc.publicnode.com", "public_fallback:bsc-rpc.publicnode.com"


def decode_pancake_v3_swap(log: dict) -> dict:
    """ABI-decode a PancakeSwap V3 Swap event log.

    Event signature (sender, recipient indexed; rest non-indexed):
        Swap(
            address indexed sender,
            address indexed recipient,
            int256 amount0,
            int256 amount1,
            uint160 sqrtPriceX96,
            uint128 liquidity,
            int24 tick,
            uint128 protocolFeesToken0,
            uint128 protocolFeesToken1
        )

    BSC mainnet emits exactly 7 × 32 bytes = 448 hex chars + 0x. Each
    non-indexed field is padded to 32 bytes (the high bits are zero for
    uint, sign-extended for int).
    """
    data = log["data"]
    if data.startswith("0x"):
        data = data[2:]
    if len(data) != 7 * 64:
        raise ValueError(f"swap data unexpected length {len(data)} (expected 448)")
    fields = [data[i * 64:(i + 1) * 64] for i in range(7)]

    def to_int(hexstr: str, signed: bool, bits: int) -> int:
        # Each ABI slot is 32 bytes; for sub-256-bit types the value is
        # sign-extended (int) or zero-padded (uint) in the high bytes.
        # Mask to the declared width first, THEN apply two's complement on
        # the low `bits` only.
        full = int(hexstr, 16)
        mask = (1 << bits) - 1
        v = full & mask
        if signed and v >= (1 << (bits - 1)):
            v -= 1 << bits
        return v

    amount0      = to_int(fields[0], True,  256)
    amount1      = to_int(fields[1], True,  256)
    sqrtPriceX96 = to_int(fields[2], False, 160)
    liquidity    = to_int(fields[3], False, 128)
    tick         = to_int(fields[4], True,   24)
    protoFee0    = to_int(fields[5], False, 128)
    protoFee1    = to_int(fields[6], False, 128)

    return {
        "sender":       "0x" + log["topics"][1][26:],
        "recipient":    "0x" + log["topics"][2][26:],
        "amount0":      amount0,
        "amount1":      amount1,
        "sqrtPriceX96": sqrtPriceX96,
        "liquidity":    liquidity,
        "tick":         tick,
        "protocolFeesToken0": protoFee0,
        "protocolFeesToken1": protoFee1,
    }


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="BSC PancakeSwap V3 1-pool 24h fee-velocity smoke.")
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--pool", default=DEFAULT_POOL)
    parser.add_argument("--token0", default=DEFAULT_TOKEN0)
    parser.add_argument("--token1", default=DEFAULT_TOKEN1)
    parser.add_argument("--fee-tier-raw", type=int, default=DEFAULT_FEE_TIER_RAW)
    parser.add_argument("--window-blocks", type=int, default=DEFAULT_WINDOW_BLOCKS)
    parser.add_argument("--chunk-blocks", type=int, default=DEFAULT_CHUNK_BLOCKS)
    args = parser.parse_args(argv)

    args.report_dir.mkdir(parents=True, exist_ok=True)

    url, source = discover_url()
    print(f"[smoke] rpc source={source} (host_hash={host_hash(url)})")

    # Pool readiness
    pool_addr = args.pool
    try:
        code = rpc_call(url, "eth_getCode", [pool_addr, "latest"])
        pool_loaded = bool(code and code != "0x")
    except Exception as exc:  # noqa: BLE001
        pool_loaded = False
        code = None
        pool_load_err = redact_error(str(exc))
    else:
        pool_load_err = None

    if not pool_loaded:
        result = {
            "stage": "LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1",
            "phase": "3_1pool_24h_smoke",
            "run_id": args.run_id,
            "pool": pool_addr,
            "selected_pool_loaded": False,
            "pool_load_error_redacted": pool_load_err,
            "smoke_pass": False,
            "reason": "pool getCode failed or returned empty bytecode",
        }
        (args.report_dir / "bsc_fee_velocity_1pool_24h_smoke.json").write_text(json.dumps(result, indent=2) + "\n")
        return 0

    # Block range
    latest_block = int(rpc_call(url, "eth_blockNumber", []), 16)
    from_block = latest_block - args.window_blocks
    chunks = []
    cur = from_block
    while cur <= latest_block:
        end = min(cur + args.chunk_blocks - 1, latest_block)
        chunks.append((cur, end))
        cur = end + 1

    raw_logs = []
    chunk_log_counts = []
    eth_getLogs_errors = []
    for i, (a, b) in enumerate(chunks):
        q = {"fromBlock": hex(a), "toBlock": hex(b), "address": pool_addr, "topics": [SWAP_TOPIC_PANCAKE_V3]}
        # First attempt at full chunk.
        try:
            logs = rpc_call(url, "eth_getLogs", [q])
        except Exception as exc:  # noqa: BLE001
            err1 = redact_error(str(exc))
            # Retry by splitting the chunk in half (transient truncations and
            # response-size limits both clear up at smaller chunks).
            mid = (a + b) // 2
            logs = []
            sub_ok = True
            for (sa, sb) in [(a, mid), (mid + 1, b)]:
                sub_q = {"fromBlock": hex(sa), "toBlock": hex(sb), "address": pool_addr, "topics": [SWAP_TOPIC_PANCAKE_V3]}
                try:
                    sub_logs = rpc_call(url, "eth_getLogs", [sub_q])
                    logs.extend(sub_logs)
                except Exception as sub_exc:  # noqa: BLE001
                    sub_ok = False
                    eth_getLogs_errors.append({
                        "chunk_index": i, "from": sa, "to": sb,
                        "initial_error": err1,
                        "subchunk_error": redact_error(str(sub_exc)),
                    })
                    break
            if not sub_ok:
                chunk_log_counts.append(0)
                continue
        chunk_log_counts.append(len(logs))
        raw_logs.extend(logs)

    # Decode
    decoded_rows = []
    decode_errors = 0
    decoded_log_count = 0
    for log in raw_logs:
        try:
            d = decode_pancake_v3_swap(log)
        except Exception as exc:  # noqa: BLE001
            decode_errors += 1
            continue
        decoded_log_count += 1
        decoded_rows.append({
            "block_number": int(log["blockNumber"], 16),
            "tx_hash": log["transactionHash"],
            "log_index": int(log["logIndex"], 16),
            "sender": d["sender"],
            "recipient": d["recipient"],
            "amount0": d["amount0"],
            "amount1": d["amount1"],
            "sqrtPriceX96": d["sqrtPriceX96"],
            "liquidity": d["liquidity"],
            "tick": d["tick"],
        })

    # Heuristic USD proxy + fee proxy
    decimals0 = DEFAULT_DECIMALS.get(args.token0, 18)
    decimals1 = DEFAULT_DECIMALS.get(args.token1, 18)
    p0 = DEFAULT_PRICES_USD.get(args.token0, Decimal("0"))
    p1 = DEFAULT_PRICES_USD.get(args.token1, Decimal("0"))
    fee_fraction = Decimal(args.fee_tier_raw) / Decimal("1000000")

    volume_usd_proxy = Decimal("0")
    pool_fee_usd_proxy = Decimal("0")
    unique_traders = set()
    for r in decoded_rows:
        # In v3, exactly one of amount0/amount1 is paid in by trader (positive),
        # the other is paid out (negative). Volume = max(abs(amount0)*p0, abs(amount1)*p1).
        vol0 = (Decimal(abs(r["amount0"])) / (Decimal(10) ** decimals0)) * p0
        vol1 = (Decimal(abs(r["amount1"])) / (Decimal(10) ** decimals1)) * p1
        v = max(vol0, vol1)
        volume_usd_proxy += v
        pool_fee_usd_proxy += v * fee_fraction
        unique_traders.add(r["sender"])
        unique_traders.add(r["recipient"])

    eth_getLogs_success = len(eth_getLogs_errors) == 0
    decode_success = decode_errors == 0
    smoke_pass = bool(pool_loaded and eth_getLogs_success and decode_success and decoded_log_count > 0)

    summary = {
        "stage": "LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1",
        "phase": "3_1pool_24h_smoke",
        "run_id": args.run_id,
        "rpc_source": source,
        "rpc_host_hash": host_hash(url),
        "pool": pool_addr,
        "token_pair": f"{args.token0}/{args.token1}",
        "fee_tier_raw": args.fee_tier_raw,
        "selected_pool_loaded": pool_loaded,
        "from_block": from_block,
        "to_block": latest_block,
        "window_blocks": args.window_blocks,
        "chunk_blocks": args.chunk_blocks,
        "chunk_count": len(chunks),
        "chunk_log_counts": chunk_log_counts,
        "raw_log_count": len(raw_logs),
        "decoded_log_count": decoded_log_count,
        "decode_errors": decode_errors,
        "eth_getLogs_errors": eth_getLogs_errors,
        "eth_getLogs_success": eth_getLogs_success,
        "decode_success": decode_success,
        "unique_traders_approx": len(unique_traders),
        "volume_usd_proxy": str(volume_usd_proxy.quantize(Decimal("0.01"))),
        "pool_fee_usd_proxy": str(pool_fee_usd_proxy.quantize(Decimal("0.0001"))),
        "smoke_pass": smoke_pass,
        "wallet_or_tx_touched": False,
        "can_run_probe_now": False,
        "tiny_canary_allowed": "no",
        "edge_proven": "no",
    }

    (args.report_dir / "bsc_fee_velocity_1pool_24h_smoke.json").write_text(json.dumps(summary, indent=2) + "\n")

    # CSV: one summary row + (separately) per-decoded-log file is too big, so emit summary CSV only.
    csv_path = args.report_dir / "bsc_fee_velocity_1pool_24h_smoke.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "run_id", "pool", "token_pair", "fee_tier_raw", "from_block", "to_block",
            "raw_log_count", "decoded_log_count", "decode_errors",
            "unique_traders_approx", "volume_usd_proxy", "pool_fee_usd_proxy",
            "eth_getLogs_success", "decode_success", "smoke_pass",
        ])
        w.writerow([
            args.run_id, pool_addr, f"{args.token0}/{args.token1}", args.fee_tier_raw,
            from_block, latest_block,
            len(raw_logs), decoded_log_count, decode_errors,
            len(unique_traders),
            summary["volume_usd_proxy"], summary["pool_fee_usd_proxy"],
            "yes" if eth_getLogs_success else "no",
            "yes" if decode_success else "no",
            "yes" if smoke_pass else "no",
        ])

    md_path = args.report_dir / "BSC_FEE_VELOCITY_1POOL_24H_SMOKE_CN.md"
    md_path.write_text(
        f"""# BSC PancakeSwap V3 — 1池 24h fee velocity smoke

- stage: `LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1`
- run_id: `{args.run_id}`
- pool: `{pool_addr}` ({args.token0}/{args.token1}, fee_tier_raw={args.fee_tier_raw})
- rpc_source: `{source}` (host_hash=`{host_hash(url)}`)

## 范围

| 字段 | 值 |
|---|---|
| from_block | `{from_block}` |
| to_block | `{latest_block}` |
| window_blocks | `{args.window_blocks}` |
| chunk_blocks | `{args.chunk_blocks}` |
| chunk_count | `{len(chunks)}` |

## 结果

| 字段 | 值 |
|---|---|
| selected_pool_loaded | `{pool_loaded}` |
| raw_log_count | `{len(raw_logs)}` |
| decoded_log_count | `{decoded_log_count}` |
| decode_errors | `{decode_errors}` |
| eth_getLogs_success | `{eth_getLogs_success}` |
| decode_success | `{decode_success}` |
| unique_traders_approx | `{len(unique_traders)}` |
| volume_usd_proxy | `{summary['volume_usd_proxy']}` |
| pool_fee_usd_proxy | `{summary['pool_fee_usd_proxy']}` |
| **smoke_pass** | **`{smoke_pass}`** |

## Decoder

Topic `0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83` (PancakeSwap V3 Swap).
ABI: `Swap(address indexed sender, address indexed recipient, int256 amount0, int256 amount1, uint160 sqrtPriceX96, uint128 liquidity, int24 tick, uint128 protocolFeesToken0, uint128 protocolFeesToken1)`.

价格 / 小数位用启发式（{args.token0}=`${DEFAULT_PRICES_USD.get(args.token0)}`, {args.token1}=`${DEFAULT_PRICES_USD.get(args.token1)}`，皆为 18 decimals）。精确 USD 价值由 Phase 5 economics preview 接管。

## 安全

```text
wallet_or_tx_touched   = false
can_run_probe_now      = false
tiny_canary_allowed    = no
edge_proven            = no
```
"""
    )

    print(json.dumps({
        "smoke_pass": smoke_pass,
        "raw_log_count": len(raw_logs),
        "decoded_log_count": decoded_log_count,
        "decode_errors": decode_errors,
        "eth_getLogs_errors": len(eth_getLogs_errors),
        "volume_usd_proxy": summary["volume_usd_proxy"],
        "pool_fee_usd_proxy": summary["pool_fee_usd_proxy"],
    }, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
