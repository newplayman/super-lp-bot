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
* **Method-aware**: ``eth_getLogs`` is only routed to endpoints empirically
  verified to serve a useful block range (most free endpoints cap getLogs to
  10-50 blocks or disable it). Cheap calls (``eth_blockNumber`` etc.) rotate
  across the full pool.
* **Rotation**: consecutive calls start at the next endpoint, distributing load.
* **Health / backoff**: a failing endpoint (transport error, HTTP 429/403/5xx,
  or a JSON-RPC error response) is put in exponential-backoff cooldown and
  skipped until it expires, then transparently brought back.

Drop-in: ``RpcPool.call(method, params)`` matches the signature of the old
``_rpc_with_retry(method, params)``, so it slots straight into existing readers.

Endpoint capabilities below were probed live on 2026-06-24 (Base). Re-probe with
``--probe`` if providers change. Pure-logic paths are covered by
``tests/test_lp_rpc_pool_v1_readonly.py`` (transport + clock injected).
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request

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
}

DEFAULT_CHAIN = "base"


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
        # exponential backoff: base * 2**(fails-1), capped at max
        self._cooldown_base = (cooldown_base
                               if cooldown_base is not None
                               else float(os.environ.get("RPC_COOLDOWN_BASE", "2.0")))
        self._cooldown_max = (cooldown_max
                              if cooldown_max is not None
                              else float(os.environ.get("RPC_COOLDOWN_MAX", "300.0")))
        self._pace = (pace_secs
                      if pace_secs is not None
                      else float(os.environ.get("RPC_CALL_PACE_SECS", "0.2")))
        self._fails = {}            # url -> consecutive fail count
        self._cooldown_until = {}   # url -> epoch seconds
        self._rr = 0                # round-robin cursor

    # --- endpoint selection ------------------------------------------------

    def _supporting(self, method):
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
        backoff = self._cooldown_base * (2 ** (fails - 1))
        self._cooldown_until[url] = self._clock.now() + min(backoff, self._cooldown_max)

    def _reset(self, url):
        self._fails.pop(url, None)
        self._cooldown_until.pop(url, None)

    # --- the call ----------------------------------------------------------

    def call(self, method, params, timeout=20):
        """Rotate across healthy endpoints; return the JSON-RPC ``result``.

        Raises RuntimeError only if *every* candidate endpoint fails.
        """
        cands = self._healthy(method)
        if not cands:
            cands = self._supporting(method)   # all cooled down: try anyway
        n = len(cands)
        start = self._rr % n
        self._rr += 1
        last = None
        for i in range(n):
            url = cands[(start + i) % n]["url"]
            try:
                self._clock.sleep(self._pace)
                resp = self._post(url, method, params, timeout=timeout)
                if isinstance(resp, dict) and "result" in resp:
                    self._reset(url)
                    return resp["result"]
                last = (resp.get("error") if isinstance(resp, dict) else resp)
                self._penalize(url)
            except Exception as e:   # noqa: BLE001  (transport/HTTP error)
                last = str(e)
                self._penalize(url)
        raise RuntimeError(
            f"RPC {method} failed on all {n} {self.chain} endpoints: {last}")

    # --- convenience -------------------------------------------------------

    def block_number(self):
        return int(self.call("eth_blockNumber", []), 16)


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
        print(f"{a.chain} latest block = {pool.block_number()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
