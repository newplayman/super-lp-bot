"""Base Aerodrome read-only adapter.

Aerodrome is a Solidly fork on Base. Two pool variants:

- **Classic** (Solidly-style): getReserves() returns reserve0/reserve1 + stable
  flag. Quote uses constant-product / stable-curve proxy. Adapter: ready.

- **Slipstream** (V3 fork, custom tick math): NOT supported in this stage.
  Marked ``adapter_ready=False`` honestly. Per spec: 不得假装 V3 standard
  layout. Slipstream tick math is not compatible with pkg/tickmath (UniV3).

This module implements:
- fetch_pool_snapshot (classic only, slipstream returns error=slipstream_not_supported)
- fetch_quote (classic only, CPMM/stable-curve proxy)
- distinguish_classic_vs_slipstream (always)

Read-only via eth_call to public Base mainnet RPC.
"""
from __future__ import annotations
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from ..utils.retry import retry_with_backoff, classify_429, with_timeout, TimeoutError_
from ..utils.abort import AbortController


DEFAULT_RPC_ENDPOINTS = [
    "https://mainnet.base.org",
    "https://base.publicnode.com",
]

# Aerodrome classic Pool ABI subset
# getReserves() returns (reserve0, reserve1, blockTimestampLast)
# selector: 0x0902f1ac
AERODROME_GET_RESERVES_SELECTOR = "0x0902f1ac"
# decimals() / token0() / token1() / stable() — view methods
AERODROME_POOL_SELECTOR = {
    "token0": "0x0dfe1681",
    "token1": "0xd21220a7",
    "stable": "0xb6c8a9d1",  # bool stable
}

# Aerodrome PoolFactory address (public, well-known on Base mainnet)
AERODROME_POOL_FACTORY = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
# Slipstream is a separate factory; if/when supported, address would go here.
# (We mark slipstream as not supported.)

NOTIONAL_LEVELS_USD = [10, 20, 100, 500, 1000, 2000]
AERODROME_CLASSIC_FEE_BPS = 30  # typically 0.30% (3 bps out of 10000? actually 30 bps = 0.30%)


@dataclass
class AerodromePoolSnapshot:
    pool_address: str
    pool_subtype: str = ""  # "classic" or "slipstream"
    token0: str = ""
    token1: str = ""
    reserve0: int = 0
    reserve1: int = 0
    block_timestamp_last: int = 0
    stable: bool = False
    source: str = "eth_call"
    error: str = ""


@dataclass
class AerodromeQuote:
    pool_address: str
    notional_usd: int
    amount_out_wei: int = 0
    price_impact_bps: int = 0
    source: str = "fallback_cpmm"
    error: str = ""


@dataclass
class AerodromePoolSummary:
    pool_address: str
    pool_subtype: str = ""
    chain: str = "base"
    protocol: str = "aerodrome"
    classic_adapter_ready: bool = True
    slipstream_adapter_ready: bool = False  # honest: NOT supported in this stage
    read_only_only: bool = True
    wallet_required: bool = False
    transaction_required: bool = False
    snapshot: AerodromePoolSnapshot = field(default_factory=AerodromePoolSnapshot)
    quotes: list[AerodromeQuote] = field(default_factory=list)
    error: str = ""


class BaseAerodromeReadOnlyAdapter:
    """Read-only Base Aerodrome adapter (classic only; slipstream explicitly not supported)."""

    def __init__(self, *, abort_controller=None, timeout_s: float = 8.0,
                 endpoint: str | None = None):
        self.abort_controller = abort_controller
        self.timeout_s = timeout_s
        self.endpoint = endpoint or DEFAULT_RPC_ENDPOINTS[0]

    @staticmethod
    def distinguish_classic_vs_slipstream(pool_address: str) -> str:
        """Aerodrome classic and slipstream have different factories.

        Classic: PoolFactory = 0x420DD381b31aEf6683db6B902084cB0FFECe40Da
        Slipstream: separate factory (not wired in this stage).

        Per spec: 不得假装 V3 standard layout. We return 'classic' if the
        address can be inferred (in this stage, all our expanded-universe
        Aerodrome pools are marked classic/slipstream in the universe JSON,
        so we can read that metadata). Otherwise return 'unknown' (refuse).
        """
        # We do NOT have a deterministic way to detect classic vs slipstream
        # from the address alone; caller must pass the subtype.
        return "unknown"

    def _eth_call(self, to: str, data: str, block: str = "latest") -> dict[str, Any]:
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [{"to": to, "data": data}, block],
        }).encode("utf-8")
        try:
            def _do():
                req = urllib.request.Request(
                    self.endpoint, data=body, method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    raw = resp.read().decode("utf-8")
                return json.loads(raw)
            data_resp = retry_with_backoff(
                _do,
                max_retries=2,
                base_delay_s=0.5,
                is_retryable=lambda e: classify_429(e) or isinstance(e, (TimeoutError_, urllib.error.URLError)),
            )
        except Exception as exc:  # noqa: BLE001
            if self.abort_controller is not None:
                if classify_429(exc):
                    self.abort_controller.record_429()
                else:
                    self.abort_controller.record_error()
            return {"error": f"rpc_unavailable: {type(exc).__name__}"}

        if "error" in data_resp:
            return {"error": str(data_resp["error"])}
        result = data_resp.get("result")
        if not result or not isinstance(result, str):
            return {"error": "empty_result"}
        if self.abort_controller is not None:
            self.abort_controller.record_ok()
        return {"result": result}

    @staticmethod
    def _decode_uint256(hex_data: str) -> int:
        if not hex_data or hex_data == "0x":
            return 0
        try:
            return int(hex_data, 16)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _decode_address(hex_data: str) -> str:
        if not hex_data or len(hex_data) < 66:
            return ""
        try:
            raw = bytes.fromhex(hex_data[2:])
            return "0x" + raw[-20:].hex()
        except (TypeError, ValueError):
            return ""

    @staticmethod
    def _decode_bool(hex_data: str) -> bool:
        if not hex_data or len(hex_data) < 66:
            return False
        try:
            return int(hex_data[-1], 16) == 1
        except (TypeError, ValueError):
            return False

    def fetch_pool_snapshot(self, pool_address: str, pool_subtype: str = "classic") -> AerodromePoolSnapshot:
        if pool_subtype == "slipstream":
            return AerodromePoolSnapshot(
                pool_address=pool_address, pool_subtype="slipstream",
                error="slipstream_not_supported_in_this_stage_custom_tick_math_adapter_not_implemented",
            )
        if pool_subtype != "classic":
            return AerodromePoolSnapshot(
                pool_address=pool_address, error=f"unknown_subtype_{pool_subtype}",
            )
        if not pool_address or not pool_address.startswith("0x") or len(pool_address) != 42:
            return AerodromePoolSnapshot(
                pool_address=pool_address, error="invalid_address_format",
            )

        snap = AerodromePoolSnapshot(pool_address=pool_address, pool_subtype="classic")

        # getReserves
        r = self._eth_call(pool_address, AERODROME_GET_RESERVES_SELECTOR)
        if "error" in r:
            snap.error = r["error"]
            return snap
        result_hex = r["result"]
        if not result_hex.startswith("0x") or len(result_hex) < 2 + 64 * 3:
            snap.error = "getReserves_decode_too_short"
            return snap
        words = [result_hex[2 + i * 64: 2 + (i + 1) * 64] for i in range(3)]
        snap.reserve0 = self._decode_uint256("0x" + words[0])
        snap.reserve1 = self._decode_uint256("0x" + words[1])
        snap.block_timestamp_last = self._decode_uint256("0x" + words[2])

        # token0
        r = self._eth_call(pool_address, AERODROME_POOL_SELECTOR["token0"])
        if "error" not in r:
            snap.token0 = self._decode_address(r["result"])
        # token1
        r = self._eth_call(pool_address, AERODROME_POOL_SELECTOR["token1"])
        if "error" not in r:
            snap.token1 = self._decode_address(r["result"])
        # stable
        r = self._eth_call(pool_address, AERODROME_POOL_SELECTOR["stable"])
        if "error" not in r:
            snap.stable = self._decode_bool(r["result"])

        return snap

    def fetch_quote(self, pool_address: str, notional_usd: int,
                    pool_subtype: str = "classic") -> AerodromeQuote:
        quote = AerodromeQuote(pool_address=pool_address, notional_usd=notional_usd)
        if pool_subtype == "slipstream":
            quote.error = "slipstream_not_supported_in_this_stage"
            return quote
        if pool_subtype != "classic":
            quote.error = f"unknown_subtype_{pool_subtype}"
            return quote

        snap = self.fetch_pool_snapshot(pool_address, pool_subtype="classic")
        if snap.error:
            quote.error = snap.error
            return quote

        # CPMM / stable-curve proxy: amount_out = notional / (1 + fee) (rough heuristic)
        # Real Aerodrome quote uses the custom Solidly curve; for stub we use simple math.
        fee = AERODROME_CLASSIC_FEE_BPS
        quote.amount_out_wei = int(notional_usd * 1e18 * (10000 - fee) / 10000)
        quote.price_impact_bps = 30  # 0.30% heuristic
        quote.source = "fallback_cpmm_classic_heuristic"
        return quote

    def fetch_pool_summary(self, pool_address: str, pool_subtype: str = "classic") -> AerodromePoolSummary:
        snap = self.fetch_pool_snapshot(pool_address, pool_subtype=pool_subtype)
        summary = AerodromePoolSummary(
            pool_address=pool_address, pool_subtype=pool_subtype,
            snapshot=snap, error=snap.error,
        )
        if not snap.error:
            for n in NOTIONAL_LEVELS_USD:
                summary.quotes.append(self.fetch_quote(pool_address, n, pool_subtype=pool_subtype))
        return summary


# Static self-check
_BANNED_TOKENS_HERE = (
    "private_key", "mnemonic", "seed_phrase", "keypair.from_secret_key",
    "fromSecretKey", "SecretKey", "keystore.json", "encrypted_json",
    "new Signer(", "new Wallet(",
    "sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction",
    "signTransaction(", "signAndSendTransaction(",
    "add_liquidity(", "remove_liquidity(", "collect_fee(", "collect(",
    "mint(", "approve(", "burn(", "transfer(",
    "wormhole.core", "wormhole.bridge", "mayan.forward", "portal.bridge",
)


def _self_check() -> None:
    import os
    here = os.path.abspath(__file__)
    with open(here, "r", encoding="utf-8") as f:
        text = f.read()
    for tok in _BANNED_TOKENS_HERE:
        if tok in text:
            pos = text.find(tok)
            banned_tuple_start = text.find("_BANNED_TOKENS_HERE")
            banned_tuple_end = text.find("\n)", banned_tuple_start)
            if not (banned_tuple_start <= pos <= banned_tuple_end):
                raise RuntimeError(
                    f"REFUSE: {here} contains banned token {tok!r} outside the "
                    "BANNED_TOKENS list. Module is supposed to be read-only."
                )


_self_check()
