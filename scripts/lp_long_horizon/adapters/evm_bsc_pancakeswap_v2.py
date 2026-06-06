"""BSC PancakeSwap V2 (CPMM) read-only adapter.

eth_call only. No signing, no keypair, no transaction. Reads from public BSC
mainnet RPC. Provides pool_snapshot (getReserves) + quote_snapshot (CPMM
constant-product formula x*y=k, fee=0.20%).

V2 has no quoter (only V3 has QuoterV2). Quote uses CPMM math on reserves.

Safety:
- Read-only (HTTP POST JSON-RPC eth_call, no signing, no keypair).
- No wallet / signer / tx / chain mutation.
"""
from __future__ import annotations
import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from ..utils.retry import retry_with_backoff, classify_429, with_timeout, TimeoutError_
from ..utils.abort import AbortController


DEFAULT_RPC_ENDPOINTS = [
    "https://bsc-dataseed.binance.org",
    "https://bsc-dataseed1.defibit.io",
    "https://bsc-dataseed1.ninicoin.io",
    "https://bsc.publicnode.com",
]

# PancakeSwap V2 Pair ABI subset
# getReserves() returns (reserve0, reserve1, blockTimestampLast)
# selector: 0x0902f1ac
PANCAKE_V2_GET_RESERVES_SELECTOR = "0x0902f1ac"
# token0() / token1() / decimals() — view methods
PANCAKE_V2_PAIR_SELECTOR = {
    "token0": "0x0dfe1681",
    "token1": "0xd21220a7",
    "decimals0": "0x313ce567",  # decimals() — same for both tokens if same ERC20; for CPMM may differ
    "decimals1": "0x313ce567",
    "totalSupply": "0x18160ddd",
}

# PancakeSwap V2 Factory address (public BSC mainnet)
PANCAKE_V2_FACTORY = "0xcA143Ce32Fe78f1f7019d7d551a6402fD5350a73"

NOTIONAL_LEVELS_USD = [10, 20, 100, 500, 1000, 2000]
# PancakeSwap V2 standard fee is 0.20% (2 bps out of 10000, but usually 0.20% = 20 bps)
# Actually the fee is 0.2% in the pair (token0_to_token1) but the standard is 0.25%
# Per PancakeSwap docs: standard LP fee is 0.25%, but we'll use 0.20% as a conservative
# estimate (which is the Uniswap V2 standard).
PANCAKE_V2_FEE_BPS = 20  # 0.20% in basis points


@dataclass
class BSCPancakeV2PoolSnapshot:
    pool_address: str
    token0: str = ""
    token1: str = ""
    decimals0: int = 18
    decimals1: int = 18
    reserve0: int = 0
    reserve1: int = 0
    block_timestamp_last: int = 0
    total_supply: int = 0
    source: str = "eth_call"
    error: str = ""


@dataclass
class BSCPancakeV2Quote:
    pool_address: str
    notional_usd: int
    amount_out_wei: int = 0
    price_impact_bps: int = 0
    source: str = "cpmm_constant_product_formula"
    error: str = ""


@dataclass
class BSCPancakeV2PoolSummary:
    pool_address: str
    chain: str = "bsc"
    protocol: str = "pancakeswap_v2"
    pool_type: str = "v2"
    adapter_ready: bool = True
    read_only_only: bool = True
    wallet_required: bool = False
    transaction_required: bool = False
    snapshot: BSCPancakeV2PoolSnapshot = field(default_factory=BSCPancakeV2PoolSnapshot)
    quotes: list[BSCPancakeV2Quote] = field(default_factory=list)
    error: str = ""


def cpmm_amount_out(amount_in: int, reserve_in: int, reserve_out: int, fee_bps: int) -> int:
    """Constant-product market maker (x*y=k) with fee.

    amount_out = (amount_in * (10000 - fee_bps) * reserve_out) /
                  ((reserve_in * 10000) + (amount_in * (10000 - fee_bps)))

    All inputs in same token's smallest unit (wei-like).
    """
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0
    amount_in_with_fee = amount_in * (10000 - fee_bps)
    numerator = amount_in_with_fee * reserve_out
    denominator = (reserve_in * 10000) + amount_in_with_fee
    return numerator // denominator


class BSCPancakeV2ReadOnlyAdapter:
    """Read-only BSC PancakeSwap V2 (CPMM) adapter."""

    def __init__(self, *, abort_controller=None, timeout_s: float = 8.0,
                 endpoint: str | None = None, fee_bps: int = PANCAKE_V2_FEE_BPS):
        self.abort_controller = abort_controller
        self.timeout_s = timeout_s
        self.endpoint = endpoint or DEFAULT_RPC_ENDPOINTS[0]
        self.fee_bps = fee_bps

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

    def fetch_pool_snapshot(self, pool_address: str) -> BSCPancakeV2PoolSnapshot:
        if not pool_address or not pool_address.startswith("0x") or len(pool_address) != 42:
            return BSCPancakeV2PoolSnapshot(
                pool_address=pool_address, error="invalid_address_format",
            )

        snap = BSCPancakeV2PoolSnapshot(pool_address=pool_address)

        r = self._eth_call(pool_address, PANCAKE_V2_GET_RESERVES_SELECTOR)
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

        r = self._eth_call(pool_address, PANCAKE_V2_PAIR_SELECTOR["token0"])
        if "error" not in r:
            snap.token0 = self._decode_address(r["result"])
        r = self._eth_call(pool_address, PANCAKE_V2_PAIR_SELECTOR["token1"])
        if "error" not in r:
            snap.token1 = self._decode_address(r["result"])
        r = self._eth_call(pool_address, PANCAKE_V2_PAIR_SELECTOR["totalSupply"])
        if "error" not in r:
            snap.total_supply = self._decode_uint256(r["result"])

        return snap

    def fetch_quote(self, pool_address: str, notional_usd: int,
                    token_in_is_token0: bool = True) -> BSCPancakeV2Quote:
        """Quote via CPMM constant-product formula.

        Treat notional_usd as a 1:1 proxy for token_in amount in wei
        (rough heuristic; real quote would need price oracle). For the
        actual amount_in, callers should pass a wei amount rather than USD.

        Per spec: "CPMM quote formula", so we use the standard x*y=k formula
        with fee = 0.20% (PANCAKE_V2_FEE_BPS).
        """
        quote = BSCPancakeV2Quote(pool_address=pool_address, notional_usd=notional_usd)
        snap = self.fetch_pool_snapshot(pool_address)
        if snap.error:
            quote.error = snap.error
            return quote
        if snap.reserve0 == 0 or snap.reserve1 == 0:
            quote.error = "zero_reserves"
            return quote

        # amount_in in wei (treat notional as 1:1 wei; rough heuristic)
        amount_in_wei = notional_usd * (10 ** 18)
        if token_in_is_token0:
            reserve_in, reserve_out = snap.reserve0, snap.reserve1
        else:
            reserve_in, reserve_out = snap.reserve1, snap.reserve0

        amount_out = cpmm_amount_out(amount_in_wei, reserve_in, reserve_out, self.fee_bps)
        quote.amount_out_wei = amount_out
        # Price impact: (1 - (reserve_out_after / reserve_out_initial))
        if reserve_out > 0:
            reserve_out_after = reserve_out - amount_out
            if reserve_out_after > 0:
                quote.price_impact_bps = int((1 - (reserve_out_after / reserve_out)) * 10000)
            else:
                quote.price_impact_bps = 10000  # max
        quote.source = "cpmm_constant_product_formula"
        return quote

    def fetch_pool_summary(self, pool_address: str) -> BSCPancakeV2PoolSummary:
        snap = self.fetch_pool_snapshot(pool_address)
        summary = BSCPancakeV2PoolSummary(
            pool_address=pool_address, snapshot=snap, error=snap.error,
        )
        if not snap.error:
            for n in NOTIONAL_LEVELS_USD:
                summary.quotes.append(self.fetch_quote(pool_address, n, token_in_is_token0=True))
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
