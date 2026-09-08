#!/usr/bin/env python3
"""RH-05b: on-chain multiplier reader + beacon attestation (offline).
Data-source layer for ``lp_rh_stock_reference_v1_readonly``.  Reads the real stock-token ABI selectors measured 2026-09-08 (see
``reports/rh_pivot/20260907T124500Z/RH-05-research/STOCK_TOKEN_ABI_DISCOVERY_20260908.md``).
RPC is injected (``rpc_fn``); no network.  Money/multiplier are ``Decimal``;
no ``float``.  A failed read is ``None`` + a ``read_errors`` entry, never 0/False (PRD §9.5: a failed read is UNKNOWN, not a value).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_registry_v1_readonly import RH_CHAIN_ID  # noqa: E402

# --- measured selectors (2026-09-08; do not invent) -------------------------
SEL_MULTIPLIER = "0xa60bf13d"
SEL_MULT_EFFECTIVE = "0x97a4064f"
SEL_PAUSED = "0x5c975abb"
SEL_DECIMALS = "0x313ce567"
SEL_TOTAL_SUPPLY = "0x18160ddd"
SEL_BEACON_IMPL = "0x5c60da1b"
EIP1967_BEACON_SLOT = "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50"
EIP1967_IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
KNOWN_BEACON = "0xe10b6f6b275de231345c20d14ab812db62151b00"
# Registered, NOT used for any decision (no sample can confirm them yet).
UNVERIFIED_SELECTORS = {
    "0xdc767007": "same value as multiplier; no pending sample to distinguish",
    "0x9bea6429": "matches totalSupply on QQQ only; unconfirmed",
}

POLICY_VERSION = "rh-05b-v1"
ATTESTATION_TTL_SECONDS = 86400


@dataclass
class OnChainMultiplier:
    token: str
    multiplier_human: Optional[Decimal] = None
    effective_at_unix: Optional[int] = None
    paused: Optional[bool] = None
    decimals: Optional[int] = None
    total_supply_raw: Optional[int] = None
    read_errors: list[str] = field(default_factory=list)
    block_number: Optional[int] = None


def _read_uint(rpc_fn, to, selector, block):
    """One eth_call returning a uint.  -> (int|None, error|None)."""
    try:
        raw = rpc_fn(to, selector, block)
    except Exception as exc:  # revert / RPC error
        return None, f"{selector}: {exc}"
    if raw is None:
        return None, f"{selector}: empty return"
    try:
        return int(raw, 16), None
    except (TypeError, ValueError) as exc:
        return None, f"{selector}: bad data {raw!r}: {exc}"


def _to_address(raw_int):
    """32-byte storage word -> 0x address (None when zero/absent)."""
    if raw_int is None or raw_int == 0:
        return None
    return "0x" + format(raw_int & ((1 << 160) - 1), "040x")


def _rfc3339(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def read_multiplier(token, *, rpc_fn, block="latest"):
    """Read every measured selector; failures -> None + read_errors."""
    errors = []
    block_number = block if isinstance(block, int) else None

    mult, err = _read_uint(rpc_fn, token, SEL_MULTIPLIER, block)
    multiplier_human = None
    if err:
        errors.append(err)
    else:
        multiplier_human = Decimal(mult) / Decimal(10) ** 18

    eff, err = _read_uint(rpc_fn, token, SEL_MULT_EFFECTIVE, block)
    effective_at_unix = None
    if err:
        errors.append(err)
    elif eff != 0:
        effective_at_unix = eff  # 0 == never changed, not an error

    paused, err = _read_uint(rpc_fn, token, SEL_PAUSED, block)
    if err:
        errors.append(err)
        paused = None
    else:
        paused = paused != 0

    dec, err = _read_uint(rpc_fn, token, SEL_DECIMALS, block)
    if err:
        errors.append(err)
        dec = None

    ts, err = _read_uint(rpc_fn, token, SEL_TOTAL_SUPPLY, block)
    if err:
        errors.append(err)
        ts = None

    return OnChainMultiplier(
        token=token, multiplier_human=multiplier_human,
        effective_at_unix=effective_at_unix, paused=paused, decimals=dec,
        total_supply_raw=ts, read_errors=errors, block_number=block_number)


def resolve_beacon(token, *, rpc_fn, block="latest"):
    """Classify the proxy and resolve the implementation address."""
    impl, _ = _read_uint(rpc_fn, token, EIP1967_IMPL_SLOT, block)
    beacon, _ = _read_uint(rpc_fn, token, EIP1967_BEACON_SLOT, block)
    impl_addr = _to_address(impl)
    beacon_addr = _to_address(beacon)
    matches = beacon_addr == KNOWN_BEACON

    if impl_addr:
        return {"proxy_kind": "DIRECT", "beacon": beacon_addr,
                "implementation": impl_addr, "matches_known_beacon": matches}
    if beacon_addr:
        beacon_impl, _ = _read_uint(rpc_fn, beacon_addr, SEL_BEACON_IMPL, block)
        return {"proxy_kind": "BEACON", "beacon": beacon_addr,
                "implementation": _to_address(beacon_impl),
                "matches_known_beacon": matches}
    return {"proxy_kind": "UNKNOWN", "beacon": beacon_addr,
            "implementation": impl_addr, "matches_known_beacon": False}


def detect_multiplier_change(previous, current):
    """Compare two reads.  Any None -> conservative UNKNOWN_CANNOT_COMPARE."""
    for m in (previous, current):
        if m.multiplier_human is None or m.effective_at_unix is None:
            return True, "UNKNOWN_CANNOT_COMPARE"
    if previous.effective_at_unix != current.effective_at_unix:
        return True, "MULTIPLIER_EFFECTIVE_AT_CHANGED"
    if previous.multiplier_human != current.multiplier_human:
        return True, "MULTIPLIER_VALUE_CHANGED_WITHOUT_TIMESTAMP"
    return False, "STABLE"


def cross_check_api(onchain, api_current_multiplier):
    """PRD §9.3: a source disagreement stops new positions, no averaging."""
    if onchain.multiplier_human is None or api_current_multiplier is None:
        reasons = []
        if onchain.multiplier_human is None:
            reasons.append("onchain multiplier unreadable")
        if api_current_multiplier is None:
            reasons.append("api multiplier missing")
        return "UNKNOWN", "; ".join(reasons)
    api = Decimal(api_current_multiplier)
    if onchain.multiplier_human == api:
        return "AGREE", ""
    return ("SOURCE_DISAGREEMENT",
            f"onchain={onchain.multiplier_human} api={api}")


def attestation_record(token, onchain, beacon_info, *, now):
    """A row for rh_contract_attestations (offline; block_hash is derived)."""
    status = "ATTESTED_SAME_BLOCK"
    if not beacon_info.get("matches_known_beacon") or onchain.read_errors:
        status = "DISCOVERED_NOT_ATTESTED"
    bn = onchain.block_number
    block_hash = ("0x" + format(bn, "064x") if bn is not None
                  else "0x" + "00" * 32)
    evidence = {
        "multiplier_human": (str(onchain.multiplier_human)
                             if onchain.multiplier_human is not None else None),
        "effective_at_unix": onchain.effective_at_unix,
        "paused": onchain.paused,
        "decimals": onchain.decimals,
        "total_supply_raw": onchain.total_supply_raw,
        "read_errors": onchain.read_errors,
        "beacon": beacon_info,
    }
    return {
        "chain_id": RH_CHAIN_ID,
        "address": token,
        "block_hash": block_hash,
        "policy_version": POLICY_VERSION,
        "code_hash": None,
        "implementation": beacon_info.get("implementation"),
        "attestation_status": status,
        "evidence_json": json.dumps(evidence, sort_keys=True),
        "expires_at": _rfc3339(now + timedelta(seconds=ATTESTATION_TTL_SECONDS)),
        "created_at": _rfc3339(now),
    }


def _fixture_rpc(calls):
    def rpc_fn(to, data, block="latest"):
        if data not in calls:
            raise RuntimeError(f"revert: no fixture for {data}")
        return calls[data]
    return rpc_fn


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="RH-05b on-chain multiplier reader (offline replay)")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with open(args.fixture, "r", encoding="utf-8") as f:
        fx = json.load(f)
    rpc_fn = _fixture_rpc(fx["calls"])
    token = fx["token"]
    block = fx.get("block", "latest")
    onchain = read_multiplier(token, rpc_fn=rpc_fn, block=block)
    beacon_info = resolve_beacon(token, rpc_fn=rpc_fn, block=block)
    cross = cross_check_api(onchain, fx.get("api_current_multiplier"))
    now = (datetime.fromisoformat(fx["now"])
           if "now" in fx else datetime.now(timezone.utc))
    record = attestation_record(token, onchain, beacon_info, now=now)
    result = {
        "token": token,
        "multiplier_human": (str(onchain.multiplier_human)
                             if onchain.multiplier_human is not None else None),
        "effective_at_unix": onchain.effective_at_unix,
        "paused": onchain.paused,
        "decimals": onchain.decimals,
        "total_supply_raw": onchain.total_supply_raw,
        "read_errors": onchain.read_errors,
        "beacon": beacon_info,
        "cross_check": {"status": cross[0], "detail": cross[1]},
        "attestation": record,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
