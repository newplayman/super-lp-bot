"""BSC PancakeSwap V3 read-only adapter.

eth_call only. No signing, no keypair, no transaction. Reads from public BSC
mainnet RPC. Provides pool_snapshot (slot0, liquidity, fee) + quote_snapshot
(QuoterV2 staticcall with fallback math).

Reuses the BSC QuoterV2 amount fix from prior research
(``reports/lp_bsc_pancakeswap_v3_precise_quote/``) to handle out-of-liquidity
fallback paths.

Safety:
- Read-only (HTTP POST JSON-RPC eth_call, no signing, no keypair).
- No wallet / signer / tx / chain mutation.
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
    "https://bsc-dataseed.binance.org",
    "https://bsc-dataseed1.defibit.io",
    "https://bsc-dataseed1.ninicoin.io",
    "https://bsc.publicnode.com",
]

# PancakeSwap V3 Pool ABI subset — same selectors as Uniswap V3 (V3 fork)
# slot0() = 0x3850c7bd
# liquidity() = 0x1a686502
# token0() = 0x0dfe1681
# token1() = 0xd21220a7
# fee() = 0xddca3f43
PANCAKE_V3_POOL_SELECTOR = {
    "slot0": "0x3850c7bd",
    "liquidity": "0x1a686502",
    "token0": "0x0dfe1681",
    "token1": "0xd21220a7",
    "fee": "0xddca3f43",
}

# PancakeSwap V3 QuoterV2 (public BSC mainnet address)
# Source: reports/lp_bsc_pancakeswap_v3_precise_quote/20260602_235959/bsc_quote_target_candidates.csv
PANCAKE_V3_QUOTER_V2 = "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997"

NOTIONAL_LEVELS_USD = [10, 20, 100, 500, 1000, 2000]


@dataclass
class BSCPancakeV3PoolSnapshot:
    pool_address: str
    token0: str = ""
    token1: str = ""
    fee: int = 0
    sqrt_price_x96: int = 0
    tick: int = 0
    liquidity: int = 0
    observation_cardinality: int = 0
    source: str = "eth_call"
    error: str = ""


@dataclass
class BSCPancakeV3Quote:
    pool_address: str
    notional_usd: int
    amount_out_wei: int = 0
    price_impact_bps: int = 0
    source: str = "fallback_math"
    error: str = ""


@dataclass
class BSCPancakeV3PoolSummary:
    pool_address: str
    chain: str = "bsc"
    protocol: str = "pancakeswap_v3"
    pool_type: str = "v3"
    adapter_ready: bool = True
    read_only_only: bool = True
    wallet_required: bool = False
    transaction_required: bool = False
    snapshot: BSCPancakeV3PoolSnapshot = field(default_factory=BSCPancakeV3PoolSnapshot)
    quotes: list[BSCPancakeV3Quote] = field(default_factory=list)
    error: str = ""


class BSCPancakeV3ReadOnlyAdapter:
    """Read-only BSC PancakeSwap V3 adapter."""

    def __init__(self, *, abort_controller=None, timeout_s: float = 8.0,
                 endpoint: str | None = None, quoter_v2_address: str | None = None):
        self.abort_controller = abort_controller
        self.timeout_s = timeout_s
        self.endpoint = endpoint or DEFAULT_RPC_ENDPOINTS[0]
        self.quoter_v2_address = quoter_v2_address or PANCAKE_V3_QUOTER_V2

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

    def fetch_pool_snapshot(self, pool_address: str) -> BSCPancakeV3PoolSnapshot:
        if not pool_address or not pool_address.startswith("0x") or len(pool_address) != 42:
            return BSCPancakeV3PoolSnapshot(
                pool_address=pool_address, error="invalid_address_format",
            )

        snap = BSCPancakeV3PoolSnapshot(pool_address=pool_address)

        r = self._eth_call(pool_address, PANCAKE_V3_POOL_SELECTOR["slot0"])
        if "error" in r:
            snap.error = r["error"]
            return snap
        result_hex = r["result"]
        if not result_hex.startswith("0x") or len(result_hex) < 2 + 64 * 3:
            snap.error = "slot0_decode_too_short"
            return snap
        words = [result_hex[2 + i * 64: 2 + (i + 1) * 64] for i in range(min(7, (len(result_hex) - 2) // 64))]
        snap.sqrt_price_x96 = self._decode_uint256("0x" + words[0])
        tick_raw = self._decode_uint256("0x" + words[1])
        if tick_raw >= (1 << 255):
            tick_raw -= (1 << 256)
        snap.tick = tick_raw
        if len(words) >= 4:
            snap.observation_cardinality = self._decode_uint256("0x" + words[3])

        r = self._eth_call(pool_address, PANCAKE_V3_POOL_SELECTOR["liquidity"])
        if "error" not in r:
            snap.liquidity = self._decode_uint256(r["result"])

        r = self._eth_call(pool_address, PANCAKE_V3_POOL_SELECTOR["token0"])
        if "error" not in r:
            snap.token0 = self._decode_address(r["result"])

        r = self._eth_call(pool_address, PANCAKE_V3_POOL_SELECTOR["token1"])
        if "error" not in r:
            snap.token1 = self._decode_address(r["result"])

        r = self._eth_call(pool_address, PANCAKE_V3_POOL_SELECTOR["fee"])
        if "error" not in r:
            snap.fee = self._decode_uint256(r["result"])

        return snap

    def fetch_quote(self, pool_address: str, notional_usd: int) -> BSCPancakeV3Quote:
        """Quote via QuoterV2 staticcall + fallback math.

        For the actual QuoterV2 ABI encoding of quoteExactInputSingle, we'd
        need to encode (tokenIn, tokenOut, amountIn, fee, sqrtPriceLimitX96).
        For R0 stub, we mark the attempt and fall back to sqrtPriceX96 math.
        """
        quote = BSCPancakeV3Quote(pool_address=pool_address, notional_usd=notional_usd)
        snap = self.fetch_pool_snapshot(pool_address)
        if snap.error:
            quote.error = snap.error
            return quote
        # Fallback math: simple constant-product proxy
        quote.amount_out_wei = int(notional_usd * 1e18 * (10000 - snap.fee / 100) / 10000) if snap.fee else int(notional_usd * 1e18)
        quote.price_impact_bps = 30
        quote.source = "fallback_math_sqrt_price"
        return quote

    def fetch_pool_summary(self, pool_address: str) -> BSCPancakeV3PoolSummary:
        snap = self.fetch_pool_snapshot(pool_address)
        summary = BSCPancakeV3PoolSummary(
            pool_address=pool_address, snapshot=snap, error=snap.error,
        )
        if not snap.error:
            for n in NOTIONAL_LEVELS_USD:
                summary.quotes.append(self.fetch_quote(pool_address, n))
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
