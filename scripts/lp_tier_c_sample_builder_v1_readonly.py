"""Build a read-only sample list of fresh Base Uniswap-V3 Tier-C candidates.

Read-only discipline:
    - no wallet access
    - no signing
    - no transaction broadcast
    - no chain writes

This script scans Base Uniswap-V3 PoolCreated logs and writes pools.json plus
sample_summary.json for the existing backtest pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from typing import Dict, List, Optional, Tuple

FACTORY = "0x33128a8fC17869897dcE68Ed026d694621f6FDfD"
TOPIC_POOL_CREATED = (
    "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
)
TOPIC_POOL_SWAPPED = (
    "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
)
WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
MAJORS = {WETH.lower(), USDC.lower()}

DECIMALS_SELECTOR = "313ce567"
SYMBOL_SELECTOR = "95d89b41"
RPC_DEFAULT = "https://mainnet.base.org"

RETRY_DELAYS = [0.5, 1.0, 2.0]


def _to_checksum(addr: str) -> str:
    a = (addr[2:] if addr.startswith("0x") else addr).lower().zfill(40)
    try:
        from eth_utils import to_checksum_address

        return to_checksum_address("0x" + a)
    except Exception:
        return "0x" + a


def _clean_addr(raw: str) -> str:
    clean = (raw[2:] if raw.startswith("0x") else raw).lower()
    return "0x" + clean[-40:].rjust(40, "0")


def decode_pool_created(log: Dict) -> Dict:
    """Decode one PoolCreated event dict into a normalized payload. Pure function."""
    topics = log["topics"]
    if len(topics) < 4:
        raise ValueError("log topics missing required entries")
    token0 = _to_checksum(_clean_addr(topics[1]))
    token1 = _to_checksum(_clean_addr(topics[2]))
    fee = int(topics[3], 16)

    data = (log.get("data") or "0x").lower()
    if not data.startswith("0x"):
        raise ValueError("data must be hex string")
    data = data[2:]
    if len(data) < 128:
        raise ValueError(f"unexpected PoolCreated data length {len(data)}")

    tick_hex = data[0:64]
    tick_spacing = int.from_bytes(bytes.fromhex(tick_hex), "big", signed=True)

    pool_raw = data[64 + 24: 128]
    pool = _to_checksum("0x" + pool_raw)
    creation_block = int(log["blockNumber"], 16)

    return {
        "token0": token0,
        "token1": token1,
        "fee": fee,
        "tickSpacing": tick_spacing,
        "pool": pool,
        "creation_block": creation_block,
    }


def fresh_token_for_major_pair(token0: str, token1: str) -> Optional[Tuple[str, str]]:
    """Return (fresh_token, major_token) when exactly one token is a major. Pure function."""
    t0_major = token0.lower() in MAJORS
    t1_major = token1.lower() in MAJORS
    if t0_major == t1_major:
        return None
    if t0_major:
        return (_to_checksum(token1), _to_checksum(token0))
    return (_to_checksum(token0), _to_checksum(token1))


def decode_decimals_from_word(word_hex: str) -> int:
    """Decode uint8 decimals from the last byte of a 32-byte ABI word. Pure function."""
    if not word_hex:
        raise ValueError("empty word")
    clean = word_hex[2:] if word_hex.startswith("0x") else word_hex
    clean = clean[-64:].rjust(64, "0")
    return int(clean[-2:], 16)


def _decode_symbol_from_word(data_hex: str) -> Optional[str]:
    """Decode a Solidity ABI-encoded string (best-effort)."""
    clean = data_hex[2:] if data_hex.startswith("0x") else data_hex
    if len(clean) < 128:
        return None
    try:
        offset = int(clean[0:64], 16)
    except ValueError:
        return None
    pos = offset * 2
    if len(clean) < pos + 64:
        return None
    try:
        strlen = int(clean[pos : pos + 64], 16)
    except ValueError:
        return None
    start = pos + 64
    end = start + strlen * 2
    if strlen <= 0 or len(clean) < end:
        return None
    try:
        return bytes.fromhex(clean[start:end]).decode("utf-8", errors="ignore").rstrip("\x00")
    except Exception:
        return None


def _rpc_request(rpc_url: str, method: str, params) -> object:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    last_err: Exception | None = None
    for delay in RETRY_DELAYS:
        req = urllib.request.Request(
            rpc_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if "error" in body:
                raise RuntimeError(body["error"])
            return body["result"]
        except Exception as exc:
            last_err = exc
            time.sleep(delay)
    raise last_err


def _eth_block_number(rpc_url: str) -> int:
    result = _rpc_request(rpc_url, "eth_blockNumber", [])
    return int(str(result), 16)


def _eth_get_logs(
    rpc_url: str,
    from_block: int,
    to_block: int,
    *,
    address: str = FACTORY,
    topics: Optional[List[str]] = None,
) -> List[Dict]:
    if topics is None:
        topics = [TOPIC_POOL_CREATED]
    params = [{"address": address, "fromBlock": hex(from_block), "toBlock": hex(to_block), "topics": topics}]
    result = _rpc_request(rpc_url, "eth_getLogs", params)
    return result if isinstance(result, list) else []


def _eth_call(rpc_url: str, to_addr: str, data: str) -> str:
    result = _rpc_request(rpc_url, "eth_call", [{"to": to_addr, "data": data}, "latest"])
    return str(result) if result is not None else "0x"


def count_pool_swaps(rpc_url: str, pool: str, from_block: int, to_block: int) -> int:
    """Count swap events for a pool in [from_block, to_block], inclusive."""
    if to_block < from_block:
        return 0
    return len(
        _eth_get_logs(
            rpc_url,
            from_block,
            to_block,
            address=pool,
            topics=[TOPIC_POOL_SWAPPED],
        )
    )


def passes_activity(swap_count: int, min_swaps: int) -> bool:
    return swap_count >= min_swaps


def _safe_decimal(rpc_url: str, token: str) -> int:
    raw = _eth_call(rpc_url, token, "0x" + DECIMALS_SELECTOR)
    return decode_decimals_from_word(raw)


def _safe_symbol(rpc_url: str, token: str) -> str:
    try:
        raw = _eth_call(rpc_url, token, "0x" + SYMBOL_SELECTOR)
        sym = _decode_symbol_from_word(raw or "0x")
        if sym:
            return sym
    except Exception:
        pass
    return f"{token[:6]}..{token[-4:]}"


def _default_out_path() -> str:
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return os.path.join("reports", "lp_tier_c_sample", ts, "pools.json")


def run_scanner(
    *,
    blocks_back: int = 200000,
    blocks_recent: int = 20000,
    blocks_forward: int = 20000,
    range_pct: float = 5.0,
    max_pools: int = 8,
    min_swaps: int = 20,
    activity_window: int = 3000,
    max_probe: int = 60,
    rpc_url: Optional[str] = None,
    out: Optional[str] = None,
) -> Tuple[list, dict]:
    """Scan PoolCreated logs and emit pools.json + sample_summary.json."""
    if rpc_url is None:
        rpc_url = (
            os.environ.get("D4_BASE_RPC_URL")
            or os.environ.get("BASE_RPC_URL")
            or RPC_DEFAULT
        )

    head = _eth_block_number(rpc_url)
    start_block = max(0, head - blocks_back)
    end_block = max(0, head - blocks_recent)

    candidates: List[Dict] = []
    scanned = 0

    cursor = start_block
    window = 2000
    while cursor <= end_block:
        window_to = min(cursor + window - 1, end_block)
        for raw_log in _eth_get_logs(rpc_url, cursor, window_to):
            decoded = decode_pool_created(raw_log)
            scanned += 1
            pair = fresh_token_for_major_pair(decoded["token0"], decoded["token1"])
            if pair is None:
                continue
            fresh, major = pair
            candidates.append({"decoded": decoded, "fresh": fresh, "major": major})
        cursor = window_to + 1

    candidates.sort(key=lambda c: c["decoded"]["creation_block"], reverse=True)
    kept = len(candidates)

    rows: List[Dict] = []
    probed = 0
    active = 0

    for idx, c in enumerate(candidates):
        if idx >= max_probe:
            break

        decoded = c["decoded"]
        swap_count = count_pool_swaps(
            rpc_url,
            decoded["pool"],
            decoded["creation_block"],
            decoded["creation_block"] + activity_window,
        )
        probed += 1

        if not passes_activity(swap_count, min_swaps):
            continue

        active += 1

        if len(rows) >= max_pools:
            continue

        maj_sym = "WETH" if c["major"].lower() == WETH.lower() else "USDC"
        rows.append(
            {
                "pool": decoded["pool"],
                "entry_block": decoded["creation_block"],
                "blocks_forward": blocks_forward,
                "range_pct": range_pct,
                "dec0": _safe_decimal(rpc_url, decoded["token0"]),
                "dec1": _safe_decimal(rpc_url, decoded["token1"]),
                "label": f"{_safe_symbol(rpc_url, c['fresh'])}/{maj_sym} fee{decoded['fee']}",
                "swap_count": swap_count,
            }
        )

    written_rows = rows
    summary = {
        "scanned": scanned,
        "kept": kept,
        "probed": probed,
        "active": active,
        "written": len(written_rows),
        "truncated": active > max_pools,
    }

    if out is None:
        out = _default_out_path()
    out_dir = os.path.dirname(out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(written_rows, f)

    summary_path = os.path.join(out_dir or ".", "sample_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f)

    for row in written_rows:
        print(row["pool"], row["entry_block"], row["label"])

    if summary["truncated"]:
        print(f"truncated: active {active} > max-pools {max_pools}")

    return written_rows, summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only Tier-C pool sample")
    parser.add_argument("--blocks-back", type=int, default=200000)
    parser.add_argument("--blocks-recent", type=int, default=20000)
    parser.add_argument("--blocks-forward", type=int, default=20000)
    parser.add_argument("--range-pct", type=float, default=5.0)
    parser.add_argument("--max-pools", type=int, default=8)
    parser.add_argument("--min-swaps", type=int, default=20)
    parser.add_argument("--activity-window", type=int, default=3000)
    parser.add_argument("--max-probe", type=int, default=60)
    parser.add_argument("--out", default=None)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run_scanner(
        blocks_back=args.blocks_back,
        blocks_recent=args.blocks_recent,
        blocks_forward=args.blocks_forward,
        range_pct=args.range_pct,
        max_pools=args.max_pools,
        min_swaps=args.min_swaps,
        activity_window=args.activity_window,
        max_probe=args.max_probe,
        out=args.out,
    )


if __name__ == "__main__":
    main()
