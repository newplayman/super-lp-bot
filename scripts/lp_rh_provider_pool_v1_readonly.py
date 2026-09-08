"""RH-01d: multi-provider round-robin pool with per-method availability checks.

Offline pure-logic module. All network I/O is injected via ``call_fn``; the
module itself never opens a socket. The orchestrating agent supplies real
endpoints and runs verification.

Design notes
------------
* Fail-closed: a provider is usable only when *every* required method is ok.
* Backoff is exponent-capped (``max_backoff_exponent``) so
  ``cooldown_base ** exp`` can never overflow float. This repo's
  ``lp_rpc_pool_v1_readonly.py`` once overflowed at ``fails >= 1025`` and took
  down a 28-day daemon; the cap is a hard requirement.
* Disagreement is reported, never resolved (no average / majority / first).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from typing import Dict, List, Optional

__all__ = [
    "verify_provider_methods",
    "usable_providers",
    "detect_disagreement",
    "ProviderPool",
    "live_readiness",
    "main",
]

_USER_AGENT = "lp-rh-provider-pool/1.0 (readonly)"


def _digest(result) -> Optional[str]:
    """``sha256(json.dumps(result, sort_keys=True))[:16]``; None if unserializable."""
    try:
        s = json.dumps(result, sort_keys=True)
    except (TypeError, ValueError):
        try:
            s = json.dumps(str(result), sort_keys=True)
        except Exception:
            return None
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def verify_provider_methods(providers, methods, call_fn):
    """Probe every (provider, method) pair; one failure never aborts the matrix.

    ``providers`` is ``[{"name","url"}]``; ``methods`` is ``[{"method","params"}]``.
    ``call_fn(url, method, params)`` returns a result or raises.

    Returns ``{provider_name: {method_name: record}}`` where each record is
    ``{"ok": bool, "latency_ms": float|None, "error": str|None,
    "result_digest": str|None}``.
    """
    matrix: Dict[str, Dict[str, dict]] = {}
    for prov in providers:
        name = prov["name"]
        url = prov["url"]
        row: Dict[str, dict] = {}
        for m in methods:
            method = m["method"]
            params = m.get("params", [])
            t0 = time.perf_counter()
            try:
                result = call_fn(url, method, params)
            except Exception as exc:  # noqa: BLE001 - isolate every failure
                latency = (time.perf_counter() - t0) * 1000.0
                row[method] = {
                    "ok": False,
                    "latency_ms": latency,
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "result_digest": None,
                }
                continue
            latency = (time.perf_counter() - t0) * 1000.0
            row[method] = {
                "ok": True,
                "latency_ms": latency,
                "error": None,
                "result_digest": _digest(result),
            }
        matrix[name] = row
    return matrix


def usable_providers(matrix, required_methods):
    """Providers where *all* ``required_methods`` are ok. Fail-closed.

    A provider missing a method entirely (no record) or with any required
    method not ok is excluded -- "most methods work" equals unusable.
    """
    usable = []
    for prov, meths in matrix.items():
        if all(meths.get(m, {}).get("ok") is True for m in required_methods):
            usable.append(prov)
    return usable


def _method_name(m):
    return m["method"] if isinstance(m, dict) else m


def detect_disagreement(matrix, methods, *, consensus_methods):
    """Compare ``result_digest`` across providers for each consensus method.

    Never averages / takes majority / silently picks first. For every
    ``consensus_method`` whose digests are not all equal, appends
    ``{"method", "digests": {name: digest}}`` so the caller can raise
    ``SOURCE_DISAGREEMENT``. Providers whose method failed (no digest) are
    omitted from the comparison.
    """
    known = {_method_name(m) for m in methods} if methods else None
    out: List[dict] = []
    for cm in consensus_methods:
        cm_name = _method_name(cm)
        if known is not None and cm_name not in known:
            continue
        digests: Dict[str, str] = {}
        for prov, meths in matrix.items():
            rec = meths.get(cm_name)
            if rec is not None and rec.get("result_digest") is not None:
                digests[prov] = rec["result_digest"]
        if len(set(digests.values())) > 1:
            out.append({"method": cm_name, "digests": digests})
    return out


class ProviderPool:
    """Round-robin provider selection with per-provider failure isolation.

    ``providers`` is ``[{"name","url"}]``. Cooldown after the ``n``-th failure
    is ``cooldown_base ** min(n - 1, max_backoff_exponent)`` seconds; the
    exponent cap guarantees the power can never overflow float.

    Clock convention (hard requirement): every time argument (``now`` on
    ``pick`` / ``report_failure`` / ``report_success``) MUST come from
    ``time.monotonic()`` -- never ``time.time()``. ``report_failure`` stores
    the cooldown deadline as ``now + cooldown`` and ``pick`` compares that
    deadline against its own ``now``; the two only agree when they share one
    clock. ``time.time()`` (wall clock) is ~1.7e9 larger than
    ``time.monotonic()`` on this host, so mixing them silently breaks cooldown
    in both directions without raising: a wall-clock deadline lands far in the
    monotonic future (provider permanently cooling -> whole pool starved), or a
    tiny value lands in the past (cooldown never expires -> hammering a dead
    endpoint). Omit ``now`` to use ``time.monotonic()`` internally, or inject
    the SAME clock into every call.
    """

    def __init__(self, providers, *, cooldown_base=2.0, max_backoff_exponent=30):
        self._providers = list(providers)
        self._names = [p["name"] for p in self._providers]
        self._cooldown_base = float(cooldown_base)
        self._max_exp = int(max_backoff_exponent)
        self._fails = {n: 0 for n in self._names}
        self._cooling_until = {n: 0.0 for n in self._names}
        self._last_ok = {n: None for n in self._names}
        self._index = 0

    def pick(self, now=None):
        """Return the next non-cooling provider (round-robin), or ``None``.

        If every provider is cooling, returns ``None`` -- never force-picks one.
        ``now`` defaults to ``time.monotonic()``; see the class docstring for
        the clock convention.
        """
        if now is None:
            now = time.monotonic()
        n = len(self._providers)
        if n == 0:
            return None
        for offset in range(n):
            i = (self._index + offset) % n
            name = self._providers[i]["name"]
            if self._cooling_until.get(name, 0.0) <= now:
                self._index = (i + 1) % n
                return self._providers[i]
        return None

    def report_failure(self, name, now=None):
        """Increment the fail count and cool for the capped backoff duration.

        ``now`` defaults to ``time.monotonic()``; the stored deadline is later
        compared against ``pick(now=...)``, so both must share one clock (see
        the class docstring).
        """
        if now is None:
            now = time.monotonic()
        self._fails[name] = self._fails.get(name, 0) + 1
        fails = self._fails[name]
        exp = min(fails - 1, self._max_exp)
        cooldown = self._cooldown_base ** exp
        self._cooling_until[name] = now + cooldown

    def report_success(self, name, now=None):
        """Reset the fail count; the provider is immediately eligible again.

        ``now`` (``time.monotonic()`` by default) stamps ``last_ok`` on the
        same clock as ``pick`` / ``report_failure``.
        """
        if now is None:
            now = time.monotonic()
        self._fails[name] = 0
        self._cooling_until[name] = 0.0
        self._last_ok[name] = now

    def health(self):
        """Per-provider ``{"fails", "cooling_until", "last_ok"}`` snapshot."""
        return {
            name: {
                "fails": self._fails.get(name, 0),
                "cooling_until": self._cooling_until.get(name, 0.0),
                "last_ok": self._last_ok.get(name),
            }
            for name in self._names
        }


def live_readiness(usable_count, *, min_required=2):
    """LIVE gate (PRD §8.3): PASS only when ``usable_count >= min_required``.

    ``min_required`` defaults to 2 and is never lowered inside this function.
    """
    if usable_count == 0:
        return {"status": "BLOCKED", "reason": "NO_PROVIDER", "usable_count": usable_count}
    if usable_count < min_required:
        return {"status": "BLOCKED", "reason": "SINGLE_PROVIDER", "usable_count": usable_count}
    return {"status": "PASS", "reason": None, "usable_count": usable_count}


def _default_call_fn(url, method, params):
    """urllib JSON-RPC POST with a User-Agent; raises on transport/RPC error."""
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(str(data["error"]))
    return data.get("result") if isinstance(data, dict) else data


def _fake_call_fn(url, method, params):
    """Deterministic offline stand-in used by ``--dry-run`` (no network)."""
    return {"method": method, "url": url, "params": params}


def main(argv=None):
    parser = argparse.ArgumentParser(description="RH-01d provider pool verification")
    parser.add_argument("--providers-json", required=True)
    parser.add_argument("--methods-json", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    providers = json.loads(args.providers_json)
    methods = json.loads(args.methods_json)
    call_fn = _fake_call_fn if args.dry_run else _default_call_fn

    matrix = verify_provider_methods(providers, methods, call_fn)
    required = [m["method"] for m in methods]
    usable = usable_providers(matrix, required)
    consensus = [m["method"] for m in methods if m.get("consensus")]
    disagreements = detect_disagreement(matrix, methods, consensus_methods=consensus)
    readiness = live_readiness(len(usable))

    out = {
        "matrix": matrix,
        "usable_providers": usable,
        "disagreements": disagreements,
        "live_readiness": readiness,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, sort_keys=True)
    print(json.dumps(readiness))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
