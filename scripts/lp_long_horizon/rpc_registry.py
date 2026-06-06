"""RPC fallback registry for read-only adapters.

Centralizes public RPC endpoint configuration for base / bsc / solana chains
used by long-horizon adapters. Each chain provides:
- primary_public_rpc: the preferred free public endpoint
- fallback_public_rpc_list: ordered list of fallback endpoints to try
- env_override_name: environment variable name (NOT value) for users who
  want to override the primary with a custom endpoint (e.g. an Alchemy
  free-tier key). The actual value must NEVER be committed to the repo.
- healthcheck_method: a read-only RPC method to use for reachability probing

No paid keys, no secrets. All endpoints are public, free, https-only.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .utils.retry import retry_with_backoff, classify_429, with_timeout, TimeoutError_


# Public registry. Only env-var NAMES (not values) are stored here.
RPC_REGISTRY: list[dict[str, Any]] = [
    {
        "chain": "base",
        "primary_public_rpc": "https://mainnet.base.org",
        "fallback_public_rpc_list": [
            "https://mainnet.base.org",
            "https://base-rpc.publicnode.com",
            "https://base.llamarpc.com",
            "https://1rpc.io/base",
        ],
        "env_override_name": "BASE_RPC_URL",
        "healthcheck_method": "eth_chainId",
        "chain_id_expected": 8453,
    },
    {
        "chain": "bsc",
        "primary_public_rpc": "https://bsc-dataseed.binance.org",
        "fallback_public_rpc_list": [
            "https://bsc-dataseed.binance.org",
            "https://bsc-rpc.publicnode.com",
            "https://binance.llamarpc.com",
            "https://1rpc.io/bnb",
        ],
        "env_override_name": "BSC_RPC_URL",
        "healthcheck_method": "eth_chainId",
        "chain_id_expected": 56,
    },
    {
        "chain": "solana",
        "primary_public_rpc": "https://api.mainnet-beta.solana.com",
        "fallback_public_rpc_list": [
            "https://api.mainnet-beta.solana.com",
            "https://solana-rpc.publicnode.com",
            "https://1rpc.io/solana",
        ],
        "env_override_name": "SOLANA_RPC_URL",
        "healthcheck_method": "getHealth",
    },
]


@dataclass
class RpcEndpoint:
    chain: str
    endpoint: str
    is_override: bool
    is_fallback_index: int  # 0 = primary, 1+ = fallback


@dataclass
class RpcHealthResult:
    chain: str
    endpoint: str
    reachable: bool
    latency_ms: int
    method_tested: str
    response_preview: str = ""
    error: str = ""


def get_primary_rpc(chain: str) -> str:
    """Return primary public RPC for the given chain (after env override if set)."""
    for r in RPC_REGISTRY:
        if r["chain"] != chain:
            continue
        env_name = r["env_override_name"]
        env_val = os.environ.get(env_name, "")
        if env_val:
            return env_val
        return r["primary_public_rpc"]
    raise ValueError(f"unknown chain: {chain}")


def list_endpoints(chain: str) -> list[RpcEndpoint]:
    """Return ordered list of endpoints for a chain: env override (if set), then primary, then fallbacks."""
    out: list[RpcEndpoint] = []
    for r in RPC_REGISTRY:
        if r["chain"] != chain:
            continue
        env_name = r["env_override_name"]
        env_val = os.environ.get(env_name, "")
        if env_val:
            out.append(RpcEndpoint(chain=chain, endpoint=env_val, is_override=True, is_fallback_index=-1))
        out.append(RpcEndpoint(chain=chain, endpoint=r["primary_public_rpc"], is_override=False, is_fallback_index=0))
        for i, fb in enumerate(r["fallback_public_rpc_list"], start=1):
            if fb == r["primary_public_rpc"]:
                continue  # already added
            out.append(RpcEndpoint(chain=chain, endpoint=fb, is_override=False, is_fallback_index=i))
        return out
    raise ValueError(f"unknown chain: {chain}")


def _evm_healthcheck(endpoint: str, expected_chain_id: int | None, timeout_s: float = 5.0) -> RpcHealthResult:
    """Run eth_chainId via eth_call-style JSON-RPC POST."""
    body = '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}'.encode("utf-8")
    import time
    start = time.time()
    try:
        def _do():
            req = urllib.request.Request(endpoint, data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8")
            return json.loads(raw)

        from .utils.retry import retry_with_backoff
        data = retry_with_backoff(
            _do, max_retries=1, base_delay_s=0.3,
            is_retryable=lambda e: classify_429(e) or isinstance(e, (TimeoutError_, urllib.error.URLError)),
        )
    except Exception as exc:  # noqa: BLE001
        latency = int((time.time() - start) * 1000)
        return RpcHealthResult(
            chain="", endpoint=endpoint, reachable=False, latency_ms=latency,
            method_tested="eth_chainId", error=f"{type(exc).__name__}: {str(exc)[:80]}",
        )
    latency = int((time.time() - start) * 1000)
    if "result" not in data:
        err = str(data.get("error", "no result"))[:100]
        return RpcHealthResult(chain="", endpoint=endpoint, reachable=False,
                              latency_ms=latency, method_tested="eth_chainId", error=err)
    result = data.get("result", "")
    if expected_chain_id is not None:
        try:
            got = int(result, 16)
            if got != expected_chain_id:
                return RpcHealthResult(
                    chain="", endpoint=endpoint, reachable=False, latency_ms=latency,
                    method_tested="eth_chainId",
                    error=f"chain_id_mismatch: got {got}, expected {expected_chain_id}",
                )
        except (TypeError, ValueError):
            return RpcHealthResult(chain="", endpoint=endpoint, reachable=False,
                                  latency_ms=latency, method_tested="eth_chainId",
                                  error=f"chain_id_unparseable: {result}")
    return RpcHealthResult(chain="", endpoint=endpoint, reachable=True, latency_ms=latency,
                          method_tested="eth_chainId", response_preview=result[:32])


def _solana_healthcheck(endpoint: str, timeout_s: float = 5.0) -> RpcHealthResult:
    """Run getHealth via Solana JSON-RPC POST."""
    body = '{"jsonrpc":"2.0","id":1,"method":"getHealth"}'.encode("utf-8")
    import time
    start = time.time()
    try:
        def _do():
            req = urllib.request.Request(endpoint, data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8")
            return json.loads(raw)

        from .utils.retry import retry_with_backoff
        data = retry_with_backoff(
            _do, max_retries=1, base_delay_s=0.3,
            is_retryable=lambda e: classify_429(e) or isinstance(e, (TimeoutError_, urllib.error.URLError)),
        )
    except Exception as exc:  # noqa: BLE001
        latency = int((time.time() - start) * 1000)
        return RpcHealthResult(
            chain="", endpoint=endpoint, reachable=False, latency_ms=latency,
            method_tested="getHealth", error=f"{type(exc).__name__}: {str(exc)[:80]}",
        )
    latency = int((time.time() - start) * 1000)
    if "result" not in data:
        err = str(data.get("error", "no result"))[:100]
        return RpcHealthResult(chain="", endpoint=endpoint, reachable=False,
                              latency_ms=latency, method_tested="getHealth", error=err)
    return RpcHealthResult(chain="", endpoint=endpoint, reachable=True, latency_ms=latency,
                          method_tested="getHealth", response_preview=str(data.get("result", ""))[:64])


def probe_chain(chain: str, timeout_s: float = 5.0) -> list[RpcHealthResult]:
    """Probe all endpoints for a chain. Returns list of RpcHealthResult."""
    results: list[RpcHealthResult] = []
    expected_chain_id = None
    for r in RPC_REGISTRY:
        if r["chain"] == chain:
            expected_chain_id = r.get("chain_id_expected")
            break

    for ep in list_endpoints(chain):
        if chain == "solana":
            r = _solana_healthcheck(ep.endpoint, timeout_s=timeout_s)
        else:
            r = _evm_healthcheck(ep.endpoint, expected_chain_id=expected_chain_id, timeout_s=timeout_s)
        r.chain = chain
        results.append(r)
    return results


def select_best_endpoint(chain: str) -> RpcEndpoint | None:
    """Return the first reachable endpoint (env override > primary > fallbacks)."""
    for r in RPC_REGISTRY:
        if r["chain"] != chain:
            continue
        expected_chain_id = r.get("chain_id_expected")
        for ep in list_endpoints(chain):
            if chain == "solana":
                hr = _solana_healthcheck(ep.endpoint)
            else:
                hr = _evm_healthcheck(ep.endpoint, expected_chain_id=expected_chain_id)
            if hr.reachable:
                return ep
        return None
    return None


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


# JSON import at end to avoid circular import
import json  # noqa: E402
