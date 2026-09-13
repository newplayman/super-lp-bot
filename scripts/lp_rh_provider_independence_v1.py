#!/usr/bin/env python3
"""H5: Provider independence probe — DNS/IP/latency probe for dual-provider independence.

Determines whether two RPC providers share a common backend (IP-level) and whether
their latency profiles suggest they are the same logical endpoint behind a load balancer.

No real network by default in tests; a --resolver-callback parameter allows test injection.
"""
from __future__ import annotations

import argparse
import statistics
import socket
import urllib.request
from typing import Any, Callable, Optional

#: Maximum p50 latency difference (as fraction) before declaring NOT independent.
#  e.g. 0.30 means p50 of provider B must be at least 70% of p50 of provider A
#  (or vice versa) to be considered distinct.
LATENCY_DIFF_THRESHOLD = 0.30
#: Number of probe requests per provider when measuring latency.
LATENCY_SAMPLE_COUNT = 5
#: Timeout per request in seconds.
REQUEST_TIMEOUT_SECS = 5.0


def resolve_hostname(url: str, resolver: Optional[Callable[[str], list[str]]] = None) -> list[str]:
    """Resolve a URL/hostname to a list of IP addresses (deduplicated).

    Args:
        url: Full URL or hostname string.
        resolver: Optional injected resolver for testing.
                  Signature: resolver(hostname) -> [ip1, ip2, ...]

    Returns:
        Sorted list of unique IP strings, or [] on failure.
    """
    # Strip scheme if present to get hostname
    host = url
    for scheme in ("https://", "http://"):
        if host.startswith(scheme):
            host = host[len(scheme):]
            break
    # Remove path/query
    host = host.split("/")[0].split("?")[0]
    # Remove port
    host = host.split(":")[0]

    if resolver is not None:
        try:
            return sorted(set(resolver(host)))
        except Exception:
            return []

    try:
        results = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        ips = sorted(set(r[4][0] for r in results))
        return ips
    except Exception:
        return []


def measure_latency(url: str, resolver: Optional[Callable[[str], list[str]]] = None) -> dict:
    """Make LATENCY_SAMPLE_COUNT small HEAD/GET requests and compute latency stats.

    Args:
        url: Target URL.
        resolver: Optional injected resolver (not used for HTTP, only for DNS).

    Returns:
        dict with keys: p50_ms (float), samples (list of float seconds), count (int),
                        errors (int), success (bool).
    """
    samples: list[float] = []
    errors = 0
    for _ in range(LATENCY_SAMPLE_COUNT):
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "lp-rh-provider-independence/1.0")
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECS) as resp:
                pass
            # urllib doesn't provide timing directly; approximate using a GET with timing
            import time
            t0 = time.perf_counter()
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "lp-rh-provider-independence/1.0")
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECS) as resp:
                resp.read(1024)  # consume some body
            elapsed = time.perf_counter() - t0
            samples.append(elapsed * 1000)  # ms
        except Exception:
            errors += 1

    if not samples:
        return {"p50_ms": None, "samples": [], "count": 0, "errors": errors, "success": False}

    p50_ms = statistics.median(samples)
    return {"p50_ms": p50_ms, "samples": samples, "count": len(samples),
            "errors": errors, "success": True}


def check_independence(
    provider_a_url: str,
    provider_b_url: str,
    resolver: Optional[Callable[[str], list[str]]] = None,
) -> dict:
    """Determine whether two RPC providers are independently operated.

    Logic:
      1. DNS resolve both URLs -> collect IP sets.
      2. If IP sets are identical (or both empty) -> independent=False, reason=shared_backend.
      3. If IPs differ, measure latency (5 samples each, p50).
      4. If |p50_A - p50_B| / max(p50_A, p50_B) < LATENCY_DIFF_THRESHOLD -> independent=True.
      5. Otherwise (similar latency profile despite different IPs) -> independent=False.

    Args:
        provider_a_url: URL of provider A.
        provider_b_url: URL of provider B.
        resolver: Optional injected DNS resolver for testing.

    Returns:
        dict with keys:
          - independent (bool): True if providers appear independent.
          - reason (str): One of "shared_backend", "distinct", "similar_latency_profile",
                          "dns_failure", "indeterminate".
          - evidence (dict): Contains IP sets, latency measurements, request counts.
    """
    ips_a = resolve_hostname(provider_a_url, resolver=resolver)
    ips_b = resolve_hostname(provider_b_url, resolver=resolver)

    evidence: dict[str, Any] = {
        "provider_a_url": provider_a_url,
        "provider_b_url": provider_b_url,
        "ips_a": ips_a,
        "ips_b": ips_b,
        "ips_a_count": len(ips_a),
        "ips_b_count": len(ips_b),
    }

    # DNS failure case
    if not ips_a or not ips_b:
        return {
            "independent": False,
            "reason": "dns_failure",
            "evidence": {**evidence, "note": "One or both providers could not be resolved"},
        }

    # IP-level identity check
    ip_set_a = frozenset(ips_a)
    ip_set_b = frozenset(ips_b)
    if ip_set_a == ip_set_b:
        return {
            "independent": False,
            "reason": "shared_backend",
            "evidence": evidence,
        }

    # IPs differ — measure latency
    try:
        lat_a = measure_latency(provider_a_url, resolver=resolver)
        lat_b = measure_latency(provider_b_url, resolver=resolver)
    except Exception:
        return {
            "independent": False,
            "reason": "indeterminate",
            "evidence": {**evidence, "note": "Latency measurement failed"},
        }

    p50_a = lat_a.get("p50_ms")
    p50_b = lat_b.get("p50_ms")

    # measure_latency returns a complete dict — re-emit its fields verbatim.
    evidence["latency_a"] = {
        "p50_ms": p50_a,
        "samples": lat_a["samples"],
        "success": lat_a["success"],
        "errors": lat_a["errors"],
    }
    evidence["latency_b"] = {
        "p50_ms": p50_b,
        "samples": lat_b["samples"],
        "success": lat_b["success"],
        "errors": lat_b["errors"],
    }

    if p50_a is None or p50_b is None:
        return {
            "independent": False,
            "reason": "indeterminate",
            "evidence": evidence,
        }

    max_p50 = max(p50_a, p50_b)
    if max_p50 == 0:
        # Both zero latency — likely local/mocked; treat as potentially independent
        return {
            "independent": True,
            "reason": "distinct",
            "evidence": evidence,
        }

    p50_diff_fraction = abs(p50_a - p50_b) / max_p50

    if p50_diff_fraction < LATENCY_DIFF_THRESHOLD:
        # Latencies are similar despite different IPs -> likely same backend
        return {
            "independent": False,
            "reason": "similar_latency_profile",
            "evidence": {**evidence, "p50_diff_fraction": p50_diff_fraction,
                         "threshold": LATENCY_DIFF_THRESHOLD},
        }

    # Different IPs + meaningfully different latency -> independent
    return {
        "independent": True,
        "reason": "distinct",
        "evidence": {**evidence, "p50_diff_fraction": p50_diff_fraction,
                     "threshold": LATENCY_DIFF_THRESHOLD},
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe independence of two RPC providers by DNS/IP and latency comparison."
    )
    parser.add_argument("provider_a_url", help="URL of provider A")
    parser.add_argument("provider_b_url", help="URL of provider B")
    parser.add_argument("--resolver-callback", dest="resolver_module", default=None,
                        help="Python module:func that provides a custom DNS resolver for tests")
    args = parser.parse_args()

    resolver = None
    if args.resolver_module:
        mod_name, func_name = args.resolver_module.rsplit(":", 1)
        import importlib
        mod = importlib.import_module(mod_name)
        resolver = getattr(mod, func_name)

    result = check_independence(args.provider_a_url, args.provider_b_url, resolver=resolver)
    print("Independent:", result["independent"])
    print("Reason:", result["reason"])
    print("Evidence:", result["evidence"])
    return 0 if result["independent"] else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
