#!/usr/bin/env python3
"""Rotating multi-endpoint public-RPC pool (READ-ONLY).

Motivation
----------
A single free RPC endpoint, hit 24/7, gets rate-limited or 403'd (and a single
*paid* endpoint runs up a bill). This pool spreads read-only JSON-RPC calls
across *all* known free public endpoints for a chain, rotating between them and
backing off any endpoint that starts failing — so no single provider carries
the whole load.

Design
------
* **Method-aware**: EVM ``eth_getLogs`` and Solana heavy read methods are only
  routed to endpoints empirically verified to support them. Cheap calls rotate
  across the full pool.
* **Rotation**: consecutive calls start at the next endpoint, distributing load.
* **Health / backoff**: a failing endpoint (transport error, HTTP 429/403/5xx,
  or a JSON-RPC error response) is put in exponential-backoff cooldown and
  skipped until it expires, then transparently brought back.

Drop-in: ``RpcPool.call(method, params)`` matches the signature of the old
``_rpc_with_retry(method, params)``, so it slots straight into existing readers.

Endpoint capabilities below were probed live on 2026-06-24 (Base) and
2026-08-08 (Solana). Re-probe with ``--probe`` if providers change. Pure-logic paths are covered by
``tests/test_lp_rpc_pool_v1_readonly.py`` (transport + clock injected).
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request


SOLANA_CHEAP_METHODS = (
    "getSlot",
    "getHealth",
    "getLatestBlockhash",
    "getAccountInfo",
    "getMultipleAccounts",
    "getTokenLargestAccounts",
    "getRecentPrioritizationFees",
    "getMinimumBalanceForRentExemption",
)
SOLANA_HEAVY_METHODS = (
    "getSignaturesForAddress",
    "getTransaction",
    "getProgramAccounts",
)

# Public, well-known program/account identifiers used only by the live probe.
_SOLANA_SYSTEM_PROGRAM = "11111111111111111111111111111111"
_SOLANA_MEMO_PROGRAM = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
_FORBIDDEN_WRITE_METHODS = frozenset({
    "eth_sendTransaction",
    "eth_sendRawTransaction",
    "eth_sign",
    "eth_signTransaction",
    "personal_sign",
    "personal_sendTransaction",
    "sendTransaction",
})

# ---------------------------------------------------------------------------
# Per-chain free public endpoint registry (extensible: add chains as needed)
#   getlogs=True  -> verified to serve >= ~2000-block eth_getLogs ranges
#   getlogs=False -> blockNumber/eth_call only (getLogs restricted/disabled)
# ---------------------------------------------------------------------------
CHAINS = {
    "base": {
        "chain_id": 8453,
        "endpoints": [
            # --- getLogs-capable (probed 2026-06-24, 2000-block range OK) ---
            {"url": "https://mainnet.base.org", "getlogs": True, "max_log_range": 2000},
            {"url": "https://developer-access-mainnet.base.org", "getlogs": True, "max_log_range": 2000},
            {"url": "https://base.drpc.org", "getlogs": True, "max_log_range": 2000},
            {"url": "https://base.lava.build", "getlogs": True, "max_log_range": 2000},
            # --- cheap-call only (getLogs range-limited/disabled) -----------
            {"url": "https://base-rpc.publicnode.com", "getlogs": False},
            {"url": "https://1rpc.io/base", "getlogs": False},
            {"url": "https://public.1rpc.io/base", "getlogs": False},
            {"url": "https://base.meowrpc.com", "getlogs": False},
            {"url": "https://base-mainnet.public.blastapi.io", "getlogs": False},
            {"url": "https://base-pokt.nodies.app", "getlogs": False},
            {"url": "https://api.zan.top/base-mainnet", "getlogs": False},
        ],
    },
    # Seeded for extensibility — verify with --probe before relying on getlogs.
    "ethereum": {
        "chain_id": 1,
        "endpoints": [
            {"url": "https://eth.drpc.org", "getlogs": True, "max_log_range": 2000},
            {"url": "https://ethereum-rpc.publicnode.com", "getlogs": False},
            {"url": "https://eth.llamarpc.com", "getlogs": False},
            {"url": "https://1rpc.io/eth", "getlogs": False},
            {"url": "https://rpc.ankr.com/eth", "getlogs": False},
        ],
    },
    "arbitrum": {
        "chain_id": 42161,
        "endpoints": [
            {"url": "https://arbitrum.drpc.org", "getlogs": True, "max_log_range": 2000},
            {"url": "https://arbitrum-one-rpc.publicnode.com", "getlogs": False},
            {"url": "https://1rpc.io/arb", "getlogs": False},
            {"url": "https://arb1.arbitrum.io/rpc", "getlogs": False},
        ],
    },
    "optimism": {
        "chain_id": 10,
        "endpoints": [
            {"url": "https://optimism.drpc.org", "getlogs": True, "max_log_range": 2000},
            {"url": "https://optimism-rpc.publicnode.com", "getlogs": False},
            {"url": "https://1rpc.io/op", "getlogs": False},
            {"url": "https://mainnet.optimism.io", "getlogs": False},
        ],
    },
    "solana": {
        "chain_id": "mainnet-beta",
        # Solana's official public limit is 100 requests/10s/IP overall and
        # 40 requests/10s/IP per method. These floors target at most 50% of
        # each allowance across the whole pool: <=5 calls/s overall and
        # <=2 calls/s for any one method. Heavy reads are slower still.
        "pool_min_interval_secs": 0.2,
        "method_min_interval_secs": {
            **{method: 0.5 for method in SOLANA_CHEAP_METHODS},
            **{method: 2.0 for method in SOLANA_HEAVY_METHODS},
        },
        "endpoints": [
            {
                "url": "https://api.mainnet-beta.solana.com",
                "provider": "solana-foundation",
                "cheap_methods": SOLANA_CHEAP_METHODS,
                "heavy_methods": SOLANA_HEAVY_METHODS,
                "min_interval_secs": 0.2,
            },
            {
                "url": "https://api.mainnet.solana.com",
                "provider": "solana-foundation",
                "cheap_methods": SOLANA_CHEAP_METHODS,
                "heavy_methods": SOLANA_HEAVY_METHODS,
                "min_interval_secs": 0.2,
            },
            {
                "url": "https://solana-rpc.publicnode.com",
                "provider": "publicnode",
                "cheap_methods": SOLANA_CHEAP_METHODS,
                "heavy_methods": (
                    "getSignaturesForAddress", "getTransaction",
                ),
                "min_interval_secs": 0.2,
            },
            {
                "url": "https://solana.publicnode.com",
                "provider": "publicnode",
                "cheap_methods": SOLANA_CHEAP_METHODS,
                "heavy_methods": (
                    "getSignaturesForAddress", "getTransaction",
                ),
                "min_interval_secs": 0.2,
            },
            {
                "url": "https://solana.lava.build",
                "provider": "lava",
                "cheap_methods": SOLANA_CHEAP_METHODS,
                "heavy_methods": SOLANA_HEAVY_METHODS,
                "min_interval_secs": 0.2,
            },
            {
                "url": "https://rpc.solanatracker.io/public",
                "provider": "solana-tracker",
                "cheap_methods": SOLANA_CHEAP_METHODS,
                "heavy_methods": (
                    "getSignaturesForAddress", "getTransaction",
                ),
                "min_interval_secs": 0.2,
            },
        ],
    },
}

DEFAULT_CHAIN = "base"


class RpcPoolExhaustedError(RuntimeError):
    """Every capable public endpoint was exhausted for one read call."""


class _SystemClock:
    def now(self):
        return time.time()

    def sleep(self, secs):
        if secs > 0:
            time.sleep(secs)


# Many free RPC providers 403 the default "Python-urllib/3.x" User-Agent.
# Send a curl-like UA (which they allow) so the pool isn't blocked outright.
_USER_AGENT = "curl/8.5.0"


def _build_request(url, method, params):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                          "params": params}).encode()
    return urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT})


def _default_post(url, method, params, timeout=20):
    req = _build_request(url, method, params)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


class RpcPool:
    """Rotating, health-aware pool of free public RPC endpoints for one chain."""

    def __init__(self, chain=DEFAULT_CHAIN, *, post=None, clock=None,
                 cooldown_base=None, cooldown_max=None, pace_secs=None):
        if chain not in CHAINS:
            raise KeyError(f"unknown chain {chain!r}; known: {list(CHAINS)}")
        self.chain = chain
        self._endpoints = list(CHAINS[chain]["endpoints"])
        self._post = post or _default_post
        self._clock = clock or _SystemClock()
        self._chain_cfg = CHAINS[chain]
        # exponential backoff: base * 2**(fails-1), capped at max
        self._cooldown_base = (cooldown_base
                               if cooldown_base is not None
                               else float(os.environ.get("RPC_COOLDOWN_BASE", "2.0")))
        self._cooldown_max = (cooldown_max
                              if cooldown_max is not None
                              else float(os.environ.get("RPC_COOLDOWN_MAX", "300.0")))
        requested_pace = (pace_secs
                          if pace_secs is not None
                          else float(os.environ.get("RPC_CALL_PACE_SECS", "0.2")))
        self._pace = max(
            requested_pace,
            float(self._chain_cfg.get("pool_min_interval_secs", 0.0)),
        )
        self._fails = {}            # url -> consecutive fail count
        self._cooldown_until = {}   # url -> epoch seconds
        self._rr = 0                # round-robin cursor
        self._last_pool_request = None
        self._last_endpoint_request = {}
        self._last_method_request = {}

    # --- endpoint selection ------------------------------------------------

    def _supporting(self, method):
        if method in _FORBIDDEN_WRITE_METHODS:
            raise ValueError(f"forbidden write/signing method {method!r}")
        if self.chain == "solana":
            if method in SOLANA_CHEAP_METHODS:
                capability = "cheap_methods"
            elif method in SOLANA_HEAVY_METHODS:
                capability = "heavy_methods"
            else:
                raise ValueError(
                    f"Solana RPC method {method!r} is not an allowed read method")
            return [e for e in self._endpoints if method in e[capability]]
        if method == "eth_getLogs":
            return [e for e in self._endpoints if e["getlogs"]]
        return list(self._endpoints)

    def _healthy(self, method):
        now = self._clock.now()
        return [e for e in self._supporting(method)
                if self._cooldown_until.get(e["url"], 0.0) <= now]

    # --- health bookkeeping ------------------------------------------------

    def _penalize(self, url):
        fails = self._fails.get(url, 0) + 1
        self._fails[url] = fails
        exponent = min(fails - 1, 30)
        backoff = self._cooldown_base * (2 ** exponent)
        self._cooldown_until[url] = self._clock.now() + min(backoff, self._cooldown_max)

    def _reset(self, url):
        self._fails.pop(url, None)
        self._cooldown_until.pop(url, None)

    def health_snapshot(self):
        """Return a read-only aggregate of persistent endpoint health.

        A failure remains impaired until that endpoint succeeds and ``_reset``
        clears it; merely reaching the end of cooldown makes it eligible for a
        probe but does not claim recovery.  Action policy is intentionally not
        encoded here—the scanner maps this evidence to its fail-closed state.
        """
        urls = {endpoint["url"] for endpoint in self._endpoints}
        now = self._clock.now()
        failed = {url for url in urls if self._fails.get(url, 0) > 0}
        cooling = {
            url for url in urls if self._cooldown_until.get(url, 0.0) > now
        }
        impaired = failed | cooling
        return {
            "state": "DEGRADED" if impaired else "NORMAL",
            "total_endpoints": len(urls),
            "impaired_endpoints": len(impaired),
            "cooling_endpoints": len(cooling),
            "max_consecutive_failures": max(
                (self._fails.get(url, 0) for url in urls), default=0
            ),
        }

    # --- pacing ------------------------------------------------------------

    def _pace_request(self, endpoint, method):
        """Apply pool, endpoint, and per-method minimum request intervals."""
        now = self._clock.now()
        waits = [self._pace if self._last_pool_request is None else
                 self._last_pool_request + self._pace - now]

        url = endpoint["url"]
        if url in self._last_endpoint_request:
            endpoint_pace = float(endpoint.get("min_interval_secs", 0.0))
            waits.append(self._last_endpoint_request[url] + endpoint_pace - now)

        if method in self._last_method_request:
            method_pace = float(
                self._chain_cfg.get("method_min_interval_secs", {}).get(method, 0.0))
            waits.append(self._last_method_request[method] + method_pace - now)

        self._clock.sleep(max(0.0, *waits))
        sent_at = self._clock.now()
        self._last_pool_request = sent_at
        self._last_endpoint_request[url] = sent_at
        self._last_method_request[method] = sent_at

    # --- the call ----------------------------------------------------------

    def call(self, method, params, timeout=20):
        """Rotate across healthy endpoints; return the JSON-RPC ``result``.

        Raises RuntimeError only if *every* candidate endpoint fails.
        """
        cands = self._healthy(method)
        if not cands:
            cands = self._supporting(method)   # all cooled down: try anyway
        n = len(cands)
        if not n:
            raise RpcPoolExhaustedError(
                f"RPC {method} has no capable {self.chain} endpoints")
        start = self._rr % n
        self._rr += 1
        last = None
        for i in range(n):
            endpoint = cands[(start + i) % n]
            url = endpoint["url"]
            try:
                self._pace_request(endpoint, method)
                resp = self._post(url, method, params, timeout=timeout)
                if isinstance(resp, dict) and "result" in resp:
                    self._reset(url)
                    return resp["result"]
                last = (resp.get("error") if isinstance(resp, dict) else resp)
                self._penalize(url)
            except Exception as e:   # noqa: BLE001  (transport/HTTP error)
                last = str(e)
                self._penalize(url)
        raise RpcPoolExhaustedError(
            f"RPC {method} failed on all {n} {self.chain} endpoints: {last}")

    # --- convenience -------------------------------------------------------

    def block_number(self):
        return int(self.call("eth_blockNumber", []), 16)

    def slot(self):
        return int(self.call("getSlot", []))


# ---------------------------------------------------------------------------
# CLI: live probe of endpoint health + getLogs capability
# ---------------------------------------------------------------------------

# Representative address-filtered getLogs probe (mirrors the real workload,
# which is ALWAYS filtered to one pool). Unfiltered topic-only queries match the
# whole chain and time out everywhere, so they are not a useful capability test.
_PROBE_POOLS = {
    "base": "0x4e829f8a5213c42535ab84aa40bd4adcce9cba02",  # an active WETH-BRETT V3 pool
}
_V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"


def _probe(chain):
    if chain == "solana":
        return _probe_solana()
    cfg = CHAINS[chain]
    pool_addr = _PROBE_POOLS.get(chain)
    print(f"# probing {chain} (chain_id={cfg['chain_id']}) — {len(cfg['endpoints'])} endpoints")
    for e in cfg["endpoints"]:
        url = e["url"]
        try:
            r = _default_post(url, "eth_blockNumber", [], timeout=8)
            bn = int(r["result"], 16)
        except Exception as ex:   # noqa: BLE001
            print(f"  DOWN   {url}  ({str(ex)[:50]})")
            continue
        # address-filtered getLogs probe over a 2000-block range
        gl = "n/a (no probe pool for chain)"
        if pool_addr:
            try:
                params = [{"address": pool_addr, "topics": [_V3_SWAP_TOPIC],
                           "fromBlock": hex(bn - 2000), "toBlock": hex(bn)}]
                rr = _default_post(url, "eth_getLogs", params, timeout=12)
                gl = (f"OK(n={len(rr['result'])})" if "result" in rr
                      else f"NO[{rr.get('error', {}).get('message', '?')[:30]}]")
            except Exception as ex:   # noqa: BLE001
                gl = f"NO[{str(ex)[:30]}]"
        flag = "getlogs" if e["getlogs"] else "cheap  "
        print(f"  UP blk={bn}  {flag}  getLogs2k={gl}  {url}")


def _solana_probe_call(url, method, params):
    """Paced direct call used to report one specific endpoint honestly."""
    time.sleep(CHAINS["solana"]["pool_min_interval_secs"])
    response = _default_post(url, method, params, timeout=10)
    if not isinstance(response, dict) or "result" not in response:
        error = response.get("error") if isinstance(response, dict) else response
        raise RuntimeError(str(error))
    return response["result"]


def _probe_solana():
    cfg = CHAINS["solana"]
    print(f"# probing solana (cluster={cfg['chain_id']}) — {len(cfg['endpoints'])} endpoints")
    for endpoint in cfg["endpoints"]:
        url = endpoint["url"]
        checks = {}
        signature = None
        try:
            checks["getHealth"] = _solana_probe_call(url, "getHealth", []) == "ok"
            slot = _solana_probe_call(url, "getSlot", [])
            checks["getSlot"] = isinstance(slot, int) and slot > 0
        except Exception as ex:  # noqa: BLE001
            print(f"  DOWN   {url}  ({str(ex)[:70]})")
            continue

        try:
            signatures = _solana_probe_call(
                url, "getSignaturesForAddress",
                [_SOLANA_SYSTEM_PROGRAM, {"limit": 1}],
            )
            checks["getSignaturesForAddress"] = isinstance(signatures, list)
            if signatures:
                signature = signatures[0].get("signature")
        except Exception:  # noqa: BLE001
            checks["getSignaturesForAddress"] = False

        try:
            transaction = _solana_probe_call(
                url, "getTransaction",
                [signature, {"encoding": "json", "maxSupportedTransactionVersion": 0}],
            ) if signature else None
            checks["getTransaction"] = isinstance(transaction, dict)
        except Exception:  # noqa: BLE001
            checks["getTransaction"] = False

        try:
            accounts = _solana_probe_call(
                url, "getProgramAccounts",
                [_SOLANA_MEMO_PROGRAM, {
                    "encoding": "base64",
                    "dataSlice": {"offset": 0, "length": 0},
                    "filters": [{"dataSize": 1}],
                }],
            )
            checks["getProgramAccounts"] = isinstance(accounts, list)
        except Exception:  # noqa: BLE001
            checks["getProgramAccounts"] = False

        cheap = "OK" if checks["getHealth"] and checks["getSlot"] else "NO"
        heavy = ",".join(
            f"{method}={'OK' if checks.get(method) else 'NO'}"
            for method in SOLANA_HEAVY_METHODS
        )
        status = "UP" if cheap == "OK" else "DOWN"
        print(f"  {status:<4} slot={slot} cheap={cheap} heavy=[{heavy}]  {url}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chain", default=DEFAULT_CHAIN, choices=list(CHAINS))
    ap.add_argument("--probe", action="store_true",
                    help="live-probe every endpoint for health + getLogs capability")
    a = ap.parse_args(argv)
    if a.probe:
        _probe(a.chain)
    else:
        pool = RpcPool(a.chain)
        if a.chain == "solana":
            print(f"solana latest slot = {pool.slot()}")
        else:
            print(f"{a.chain} latest block = {pool.block_number()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
