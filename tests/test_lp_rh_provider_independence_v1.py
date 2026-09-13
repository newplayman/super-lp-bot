#!/usr/bin/env python3
"""H5: Provider independence probe tests.

Verifies check_independence() correctly classifies providers as independent or not
based on DNS/IP overlap and latency profile comparison.
"""
from __future__ import annotations

import socket

import pytest

from scripts.lp_rh_provider_independence_v1 import (
    LATENCY_DIFF_THRESHOLD,
    check_independence,
    resolve_hostname,
)


# ---------------------------------------------------------------------------
# Mock resolvers: a single function that dispatches based on hostname prefix.
# ---------------------------------------------------------------------------

def _resolver_dispatch(url_a: str, url_b: str):
    """Return a resolver that gives different IPs to provider_a vs provider_b URLs."""
    def resolver(hostname: str):
        # provider_a URL hostname contains "provider-a"
        # provider_b URL hostname contains "provider-b"
        if "provider-a" in hostname:
            return ["93.184.216.34"]  # IP for provider A
        elif "provider-b" in hostname:
            return ["151.101.1.140"]  # IP for provider B
        return []
    return resolver


RESOLVER_SAME_IP = lambda hostname: ["93.184.216.34"]
RESOLVER_DIFFERENT_IPS = _resolver_dispatch(
    "https://provider-a.example.com/eth",
    "https://provider-b.example.com/eth"
)
RESOLVER_DNS_FAILURE = lambda hostname: (_ for _ in ()).throw(socket.gaierror("Name resolution failed"))


# ---------------------------------------------------------------------------
# DNS resolution tests.
# ---------------------------------------------------------------------------

class TestResolveHostname:
    def test_same_ip_returns_not_independent(self):
        """Identical IP sets -> independent=False, reason=shared_backend."""
        result = check_independence(
            "https://provider-a.example.com/eth",
            "https://provider-b.example.com/eth",
            resolver=RESOLVER_SAME_IP,
        )
        assert result["independent"] is False
        assert result["reason"] == "shared_backend"
        assert result["evidence"]["ips_a"] == result["evidence"]["ips_b"]

    def test_different_ip_distinct_latency_returns_independent(self):
        """Different IPs with meaningfully different latency -> independent=True, reason=distinct."""
        import scripts.lp_rh_provider_independence_v1 as pi_mod

        orig = pi_mod.measure_latency

        def fast_then_slow(url, resolver=None):
            # Return fast (50ms) for provider-a, slow (500ms) for provider-b
            if "provider-a" in url:
                return {"p50_ms": 50.0, "samples": [0.05] * 5, "count": 5, "errors": 0, "success": True}
            return {"p50_ms": 500.0, "samples": [0.5] * 5, "count": 5, "errors": 0, "success": True}

        pi_mod.measure_latency = fast_then_slow
        try:
            result = check_independence(
                "https://provider-a.example.com/eth",
                "https://provider-b.example.com/eth",
                resolver=RESOLVER_DIFFERENT_IPS,
            )
            assert result["independent"] is True
            assert result["reason"] == "distinct"
        finally:
            pi_mod.measure_latency = orig

    def test_dns_failure_returns_indeterminate(self):
        """DNS failure for either provider -> independent=False, reason=dns_failure."""
        result = check_independence(
            "https://provider-a.example.com/eth",
            "https://provider-b.example.com/eth",
            resolver=RESOLVER_DNS_FAILURE,
        )
        assert result["independent"] is False
        assert result["reason"] == "dns_failure"

    def test_overlapping_ip_sets_shared_backend(self):
        """Identical IP sets -> shared_backend (not overlapping sets)."""
        def identical_resolver(hostname):
            return ["1.2.3.4", "1.2.3.5"]  # same for both

        result = check_independence(
            "https://provider-a.example.com/eth",
            "https://provider-b.example.com/eth",
            resolver=identical_resolver,
        )
        assert result["independent"] is False
        assert result["reason"] == "shared_backend"


class TestLatencyProfile:
    def test_similar_latency_not_independent(self):
        """Different IPs but nearly identical latency -> NOT independent, reason=similar_latency_profile."""
        import scripts.lp_rh_provider_independence_v1 as pi_mod

        orig = pi_mod.measure_latency

        # Both ~100ms — difference < 30% threshold
        def similar_latency(url, resolver=None):
            return {"p50_ms": 100.0, "samples": [0.1] * 5, "count": 5, "errors": 0, "success": True}

        pi_mod.measure_latency = similar_latency
        try:
            result = check_independence(
                "https://provider-a.example.com/eth",
                "https://provider-b.example.com/eth",
                resolver=RESOLVER_DIFFERENT_IPS,
            )
            assert result["independent"] is False
            assert result["reason"] == "similar_latency_profile"
        finally:
            pi_mod.measure_latency = orig


class TestEdgeCases:
    def test_empty_provider_urls(self):
        """Empty string URLs -> dns_failure (no IPs resolved)."""
        result = check_independence("", "", resolver=lambda h: [])
        assert result["reason"] == "dns_failure"

    def test_none_resolver_invalid_domains(self):
        """None resolver with invalid domains -> dns_failure without raising."""
        result = check_independence(
            "https://this-domain-does-not-exist-123456.invalid/eth",
            "https://another-invalid-domain-654321.invalid/eth",
            resolver=None,
        )
        assert result["reason"] in ("dns_failure", "indeterminate")

    def test_evidence_contains_ips_and_latency(self):
        """Result evidence dict contains IPs and (when reached) latency data."""
        import scripts.lp_rh_provider_independence_v1 as pi_mod

        orig = pi_mod.measure_latency
        pi_mod.measure_latency = lambda url, resolver=None: {
            "p50_ms": 80.0, "samples": [0.08] * 5, "count": 5, "errors": 0, "success": True
        }
        try:
            result = check_independence(
                "https://provider-a.example.com/eth",
                "https://provider-b.example.com/eth",
                resolver=RESOLVER_DIFFERENT_IPS,
            )
            ev = result["evidence"]
            assert "ips_a" in ev and "ips_b" in ev
            assert ev["ips_a"] != ev["ips_b"]
            assert "latency_a" in ev and "latency_b" in ev
            assert ev["latency_a"]["p50_ms"] == 80.0
            assert ev["latency_b"]["p50_ms"] == 80.0
        finally:
            pi_mod.measure_latency = orig

    def test_zero_latency_treated_as_distinct(self):
        """Both latencies 0ms (local/mocked) -> independent=True, reason=distinct."""
        import scripts.lp_rh_provider_independence_v1 as pi_mod

        orig = pi_mod.measure_latency
        pi_mod.measure_latency = lambda url, resolver=None: {
            "p50_ms": 0.0, "samples": [0.0] * 5, "count": 5, "errors": 0, "success": True
        }
        try:
            result = check_independence(
                "https://provider-a.example.com/eth",
                "https://provider-b.example.com/eth",
                resolver=RESOLVER_DIFFERENT_IPS,
            )
            assert result["independent"] is True
            assert result["reason"] == "distinct"
        finally:
            pi_mod.measure_latency = orig
