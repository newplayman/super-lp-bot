#!/usr/bin/env python3
"""Deprecated Solana read-only RPC compatibility entry.

This module is superseded by lp_rpc_pool CHAINS['solana'].  The canonical
endpoint registry, capability declarations, pacing, health/backoff logic, and
live probe now live in :mod:`scripts.lp_rpc_pool_v1_readonly`.

The old registry implementation wrote redacted ``endpoint_id``, ``host_hash``,
and ``source_type`` artifact fields using ``_hash_host``.  This compatibility
shell no longer generates those one-off readiness artifacts; their historical
reports remain immutable.  Existing read-only imports can use the re-exported
pool symbols below, and command-line callers are forwarded to the canonical
Solana pool entry point.

Safety: read-only.  No wallet, signer, keypair, transaction, swap, LP action,
or bridge operation is exposed here.
"""
from __future__ import annotations

import sys

try:
    from scripts.lp_rpc_pool_v1_readonly import (
        CHAINS,
        SOLANA_CHEAP_METHODS,
        SOLANA_HEAVY_METHODS,
        RpcPool,
        RpcPoolExhaustedError,
        main as _rpc_pool_main,
    )
except ModuleNotFoundError:  # Direct execution: python3 scripts/<this-file>.py
    from lp_rpc_pool_v1_readonly import (  # type: ignore[no-redef]
        CHAINS,
        SOLANA_CHEAP_METHODS,
        SOLANA_HEAVY_METHODS,
        RpcPool,
        RpcPoolExhaustedError,
        main as _rpc_pool_main,
    )


# Compatibility views are derived from the single canonical registry.  They
# intentionally do not duplicate endpoint data or probe behavior.
SOLANA_CHAIN = CHAINS["solana"]
PUBLIC_FALLBACK_RPCS = tuple(
    endpoint["url"] for endpoint in SOLANA_CHAIN["endpoints"]
)

__all__ = (
    "CHAINS",
    "SOLANA_CHAIN",
    "PUBLIC_FALLBACK_RPCS",
    "SOLANA_CHEAP_METHODS",
    "SOLANA_HEAVY_METHODS",
    "RpcPool",
    "RpcPoolExhaustedError",
    "main",
)


def main(argv: list[str] | None = None) -> int:
    """Forward this legacy read-only CLI to the canonical Solana pool CLI."""
    forwarded = list(sys.argv[1:] if argv is None else argv)
    if "--chain" not in forwarded:
        forwarded.extend(("--chain", "solana"))
    return _rpc_pool_main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
