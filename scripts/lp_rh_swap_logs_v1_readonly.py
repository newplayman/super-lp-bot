"""RH-05g: fetch and decode Uniswap-v3-style Swap logs (read-only, offline).

Feeds real swap events into the RH-05f organic-volume module.  The module is
pure logic: all network access goes through an injected ``call_fn`` so the
module itself never opens a socket.  ``main()`` wires a urllib-backed
``call_fn`` for real use and a fake one for ``--dry-run``.

The critical trap this module exists to avoid: ``amount0`` / ``amount1`` are
``int256`` two's-complement.  Reading them as unsigned turns every sell into a
~1.15e77 buy and inflates total volume by ~60 orders of magnitude with the
sign flipped.  ``decode_int256`` handles the sign.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from typing import Callable, Optional

# keccak("Swap(address,address,int256,int256,uint160,uint128,int24)")
SWAP_TOPIC0 = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"

# Substrings (lowercased) that mark a "range too large" provider error.
_RANGE_ERROR_KEYS = ("more than", "too many", "range", "limit")

_UINT256 = 2 ** 256
_SIGN_BIT = 2 ** 255


def decode_int256(word_hex: str) -> int:
    """Decode a 32-byte word as a signed int256 (two's complement)."""
    h = word_hex
    if h[:2].lower() == "0x":
        h = h[2:]
    value = int(h, 16)
    if value >= _SIGN_BIT:
        value -= _UINT256
    return value


def _strip_hex(value: str) -> str:
    v = value or ""
    if v[:2].lower() == "0x":
        return v[2:]
    return v


def _to_int(value) -> int:
    """Hex-string (or int) to int; blockNumber/logIndex arrive as 0x strings."""
    if isinstance(value, int):
        return value
    return int(value, 16)


def _topic_address(topic: str) -> str:
    """Low 20 bytes of a 32-byte topic, lowercased, 0x-prefixed."""
    return "0x" + _strip_hex(topic)[-40:].lower()


def decode_swap_log(log: dict) -> Optional[dict]:
    """Decode one eth_getLogs entry into a Swap event, or None if not a Swap."""
    topics = log.get("topics") or []
    if not topics or topics[0] != SWAP_TOPIC0:
        return None
    if len(topics) < 3:
        return None
    data = _strip_hex(log.get("data") or "")
    if len(data) < 5 * 64:
        return None
    words = [data[i * 64:(i + 1) * 64] for i in range(5)]
    return {
        "block": _to_int(log["blockNumber"]),
        "tx_hash": log["transactionHash"],
        "log_index": _to_int(log["logIndex"]),
        "sender": _topic_address(topics[1]),
        "recipient": _topic_address(topics[2]),
        "amount0": decode_int256("0x" + words[0]),
        "amount1": decode_int256("0x" + words[1]),
        "sqrt_price_x96": int(words[2], 16),
        "liquidity": int(words[3], 16),
        "tick": decode_int256("0x" + words[4]),
    }


def split_range(from_block: int, to_block: int, max_span: int) -> list[tuple[int, int]]:
    """Split closed interval [from_block, to_block] into chunks of <= max_span blocks."""
    if max_span <= 0:
        raise ValueError("max_span must be > 0")
    if from_block > to_block:
        return []
    chunks: list[tuple[int, int]] = []
    start = from_block
    while start <= to_block:
        end = min(start + max_span - 1, to_block)
        chunks.append((start, end))
        start = end + 1
    return chunks


def _is_range_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(key in msg for key in _RANGE_ERROR_KEYS)


def fetch_swaps(
    pool: str,
    from_block: int,
    to_block: int,
    call_fn: Callable[[dict], list],
    *,
    max_span: int = 2000,
    max_depth: int = 6,
) -> dict:
    """Fetch Swap events for ``pool`` over [from_block, to_block] via ``call_fn``.

    Ranges failing with a too-large provider error are split in half and
    retried up to ``max_depth``; ranges that still fail are recorded in
    ``failed_ranges`` and the rest of the range is still processed.
    """
    events: list[dict] = []
    failed_ranges: list[list[int]] = []

    def _process(a: int, b: int, depth: int) -> None:
        params = {
            "address": pool,
            "topics": [SWAP_TOPIC0],
            "fromBlock": hex(a),
            "toBlock": hex(b),
        }
        try:
            logs = call_fn(params)
        except Exception as exc:
            if _is_range_error(exc) and a < b and depth < max_depth:
                mid = (a + b) // 2
                _process(a, mid, depth + 1)
                _process(mid + 1, b, depth + 1)
                return
            failed_ranges.append([a, b])
            return
        for log in logs or []:
            event = decode_swap_log(log)
            if event is not None:
                events.append(event)

    if from_block <= to_block:
        _process(from_block, to_block, 0)

    seen: set[tuple[str, int]] = set()
    deduped: list[dict] = []
    for event in events:
        key = (event["tx_hash"], event["log_index"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)

    requested_blocks = to_block - from_block + 1
    if requested_blocks <= 0:
        return {
            "events": [],
            "requested_blocks": 0,
            "covered_blocks": 0,
            "failed_ranges": [],
            "coverage_frac": None,
            "status": "COMPLETE",
        }
    failed_blocks = sum(b - a + 1 for a, b in failed_ranges)
    covered_blocks = requested_blocks - failed_blocks
    if not failed_ranges:
        status = "COMPLETE"
        coverage_frac = Decimal(covered_blocks) / Decimal(requested_blocks)
    elif covered_blocks <= 0:
        status = "INPUTS_UNAVAILABLE"
        coverage_frac = None
    else:
        status = "PARTIAL"
        coverage_frac = Decimal(covered_blocks) / Decimal(requested_blocks)
    return {
        "events": deduped,
        "requested_blocks": requested_blocks,
        "covered_blocks": covered_blocks,
        "failed_ranges": failed_ranges,
        "coverage_frac": coverage_frac,
        "status": status,
    }


def to_organic_events(events: list[dict]) -> list[dict]:
    """Reshape decoded events into the RH-05f organic_volume_estimate input shape."""
    out: list[dict] = []
    for event in events:
        item = dict(event)
        item["amount0"] = Decimal(event["amount0"])
        item["amount1"] = Decimal(event["amount1"])
        out.append(item)
    return out


def make_urllib_call_fn(rpc_url: str) -> Callable[[dict], list]:
    """Build a real eth_getLogs call_fn backed by urllib (with a User-Agent)."""
    import urllib.request

    def call_fn(params: dict) -> list:
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [params]}
        ).encode("utf-8")
        request = urllib.request.Request(
            rpc_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "lpbot-rh05g/1.0 (read-only research)",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        if isinstance(body, dict) and body.get("error"):
            raise RuntimeError(str(body["error"]))
        return (body or {}).get("result", []) if isinstance(body, dict) else []

    return call_fn


def _dry_run_call_fn(params: dict) -> list:
    """Offline fake call_fn for --dry-run: returns no events, never touches the network."""
    return []


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch and decode Swap logs (read-only).")
    parser.add_argument("--pool", required=True, help="Pool address (0x...)")
    parser.add_argument("--from-block", type=int, required=True)
    parser.add_argument("--to-block", type=int, required=True)
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Use an offline fake call_fn")
    parser.add_argument("--rpc-url", default="https://mainnet.base.org")
    args = parser.parse_args(argv)

    call_fn = _dry_run_call_fn if args.dry_run else make_urllib_call_fn(args.rpc_url)
    result = fetch_swaps(args.pool, args.from_block, args.to_block, call_fn)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, default=str, indent=2)
    print(json.dumps({"status": result["status"], "events": len(result["events"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
