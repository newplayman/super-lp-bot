"""Solana Meteora DLMM long-horizon adapter check (verify).

This is NOT a new wire. It verifies that the existing
``scripts/lp_long_horizon/adapters/solana_rpc_readonly.py`` (which uses
``getMultipleAccountsInfo``) can read the 16 verified Meteora DLMM pools
from ``reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/meteora_pool_chain_verification.json``.

The Meteora DLMM LbPair struct is 904 bytes; the prior connector already
decoded it (data_len + owner check). This module:
- Loads 16 verified pool_addresses from the verification JSON
- Calls ``solana_rpc_readonly.fetch_accounts(addresses)`` to read live
- Validates each result has owner=LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo
  and data_len=904
- Emits a verification summary

If Solana public RPC is unavailable, returns honest error and marks
``rpc_unavailable=True``. No fallback to placeholder.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

# Reuse existing solana_rpc_readonly adapter
from .solana_rpc_readonly import SolanaRpcReadOnlyAdapter


METEORA_DLMM_OWNER = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
METEORA_DLMM_DATA_LEN = 904

VERIFICATION_ARTIFACT = (
    "/opt/lpbot/lp-bot-v3-origin-check/reports/"
    "lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/"
    "meteora_pool_chain_verification.json"
)


@dataclass
class MeteoraCheckSummary:
    pool_address: str
    account_exists: bool = False
    owner: str = ""
    owner_is_meteora_dlmm: bool = False
    data_len: int = 0
    dlmm_sized: bool = False
    verified: bool = False
    error: str = ""


def load_verified_pools() -> list[dict[str, Any]]:
    """Load 16 verified pools from prior research."""
    p = Path(VERIFICATION_ARTIFACT)
    if not p.exists():
        return []
    return json.loads(p.read_text())


def run_check(max_pools: int = 2, timeout_s: float = 5.0) -> dict[str, Any]:
    """Run short smoke: read first ``max_pools`` verified Meteora pools via
    ``solana_rpc_readonly``. Returns summary.

    Note: The prior verification used a different (private) RPC and returned
    data_len=904 for all 16 pools. We re-verify on the public RPC.
    """
    verifs = load_verified_pools()
    if not verifs:
        return {
            "smoke_ran": False,
            "error": f"verification_artifact_not_found: {VERIFICATION_ARTIFACT}",
            "verified_pool_count": 0,
        }

    # Use first max_pools addresses
    test_addrs = [v["pool_address"] for v in verifs[:max_pools]]
    adapter = SolanaRpcReadOnlyAdapter(timeout_s=timeout_s)
    accounts = adapter.fetch_accounts(test_addrs)

    summaries: list[MeteoraCheckSummary] = []
    for v in verifs[:max_pools]:
        addr = v["pool_address"]
        s = MeteoraCheckSummary(pool_address=addr)
        matching = [a for a in accounts if a.address == addr]
        if matching:
            a = matching[0]
            s.account_exists = True
            s.owner = a.owner
            s.owner_is_meteora_dlmm = (a.owner == METEORA_DLMM_OWNER)
            s.data_len = a.data_len
            s.dlmm_sized = (a.data_len == METEORA_DLMM_DATA_LEN)
            s.verified = s.account_exists and s.owner_is_meteora_dlmm and s.dlmm_sized
        else:
            s.error = "account_not_returned_or_rpc_unavailable"
        summaries.append(s)

    rpc_unavailable = all(not s.account_exists for s in summaries)
    verified_count = sum(1 for s in summaries if s.verified)
    return {
        "smoke_ran": True,
        "reuses_solana_rpc_readonly": True,
        "test_pool_count": len(test_addrs),
        "verified_pool_count": verified_count,
        "rpc_unavailable": rpc_unavailable,
        "summaries": [
            {
                "pool_address": s.pool_address,
                "account_exists": s.account_exists,
                "owner": s.owner,
                "owner_is_meteora_dlmm": s.owner_is_meteora_dlmm,
                "data_len": s.data_len,
                "dlmm_sized": s.dlmm_sized,
                "verified": s.verified,
                "error": s.error,
            }
            for s in summaries
        ],
    }


# Static self-check (read-only)
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
