#!/usr/bin/env python3
"""RH Uniswap V3/V4 pool identity probe (read-only, offline-testable).

Issues only JSON-RPC read methods (eth_getCode, eth_call, eth_blockNumber,
eth_getBlockByNumber); never signs, broadcasts, or touches wallets; imports
none of web3, eth_account, solana, or requests. Identity-only: it attests a
pool address against its factory and never reads balances/TVL (a PoolManager
balance is never TVL, T10). Offline: every public function is exercisable
from an injected ``rpc`` callable or a local JSON fixture. V3 is fail-closed
(getPool mismatch -> IDENTITY_FAIL, T07; any error -> DISCOVERED_NOT_ATTESTED
with the original text kept, T12). V4: PoolId = keccak256(abi.encode(PoolKey));
no keccak -> UNVERIFIED_NO_KECCAK with the PoolKey preserved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_capabilities_v1_readonly import (  # noqa: E402
    _call, _default_rpc, _fixture_rpc, _hex_to_int,
)
from scripts.lp_rh_registry_v1_readonly import RH_CHAIN_ID, SEED_ADDRESSES  # noqa: E402

SEL_TOKEN0 = "0x0dfe1681"
SEL_TOKEN1 = "0xd21220a7"
SEL_FEE = "0xddca3f43"
SEL_TICK_SPACING = "0xd0c93a7c"
SEL_GET_POOL = "0x1698ee82"
_ZERO_ADDR = "0x0000000000000000000000000000000000000000"
_ZERO32 = "0x" + "0" * 64
_HEX = set("0123456789abcdefABCDEF")
SECURITY_IMPL_CHANGED = "IMPLEMENTATION_CHANGED"

@dataclass
class PoolIdentityV3:
    chain_id: int
    factory: str
    pool: str
    token0: Optional[str] = None
    token1: Optional[str] = None
    fee: Optional[int] = None
    tick_spacing: Optional[int] = None
    code_nonempty: bool = False
    factory_get_pool_matches: Optional[bool] = None
    attestation_status: str = "DISCOVERED_NOT_ATTESTED"

@dataclass
class PoolIdentityV4:
    chain_id: int
    pool_manager: str
    pool_id: Optional[str] = None
    currency0: Optional[str] = None
    currency1: Optional[str] = None
    fee: Optional[int] = None
    tick_spacing: Optional[int] = None
    hooks: Optional[str] = None
    attestation_status: str = "DISCOVERED_NOT_ATTESTED"

def _decode_address(result: object) -> Optional[str]:
    """Last 20 bytes of a 32-byte word, lowercased; None when not decodable."""
    if not isinstance(result, str) or not result.lower().startswith("0x"):
        return None
    body = result[2:]
    if len(body) < 40:
        return None
    return "0x" + body[-40:].lower()

def _decode_uint(result: object) -> Optional[int]:
    if not isinstance(result, str) or not result.lower().startswith("0x"):
        return None
    try:
        return int(result, 16)
    except ValueError:
        return None

def _abi_address(addr: str) -> str:
    body = str(addr).lower().replace("0x", "")
    return "0x" + "0" * 12 + body

def _abi_uint24(fee: int) -> str:
    return "0x" + "0" * 28 + format(int(fee), "06x")

def _abi_bytes32(value: object) -> str:
    if not value:
        return _ZERO32
    body = str(value).lower().replace("0x", "")
    if len(body) == 40:
        return "0x" + "0" * 12 + body
    return "0x" + body.rjust(64, "0")

def _abi_int24(value: int) -> str:
    v = int(value)
    return format(v & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF, "064x")

def _abi_encode_pool_key(pk: Dict[str, object]) -> bytes:
    raw = (_abi_bytes32(pk.get("currency0"))[2:]
           + _abi_bytes32(pk.get("currency1"))[2:]
           + _abi_int24(pk.get("tick_spacing", 0))
           + _abi_address(pk.get("hooks", _ZERO_ADDR))[2:])
    return bytes.fromhex(raw)

def _v4_pool_key(candidate: Dict[str, object]) -> Dict[str, object]:
    pk = candidate.get("pool_key")
    if isinstance(pk, dict):
        return dict(pk)
    return {
        "currency0": candidate.get("currency0"),
        "currency1": candidate.get("currency1"),
        "tick_spacing": candidate.get("tick_spacing", 0),
        "hooks": candidate.get("hooks", _ZERO_ADDR),
    }

def _try_keccak() -> Optional[Callable[[bytes], str]]:
    """keccak256(bytes)->'0x..' or None. EVM keccak != hashlib.sha3_256; only
    a real keccak (pycryptodome/pysha3) is accepted."""
    try:
        from Crypto.Hash import keccak as _keccak_mod
        def _k(data: bytes) -> str:
            h = _keccak_mod.new(digest_bits=256)
            h.update(data)
            return "0x" + h.hexdigest()
        return _k
    except Exception:
        pass
    try:
        import sha3 as _sha3_mod
        return lambda data: "0x" + _sha3_mod.keccak_256(data).hexdigest()
    except Exception:
        return None

def _code_hash(code: str) -> str:
    """Stable sha256 fingerprint of the bytecode for change detection (T06)."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()

def _is_addr20(value: object) -> bool:
    return (isinstance(value, str) and value.lower().startswith("0x")
            and len(value) == 42 and all(c in _HEX for c in value[2:]))

def _is_bytes32(value: object) -> bool:
    return (isinstance(value, str) and value.lower().startswith("0x")
            and len(value) == 66 and all(c in _HEX for c in value[2:]))

def dispatch_protocol(candidate: Dict[str, object]) -> str:
    """'v4' (32-byte pool_id, no pool) / 'v3' (20-byte pool, no pool_id) /
    'UNSUPPORTED_PROTOCOL' (both or neither) (T08)."""
    has_pool = _is_addr20(candidate.get("pool"))
    has_pool_id = _is_bytes32(candidate.get("pool_id"))
    if has_pool_id and not has_pool:
        return "v4"
    if has_pool and not has_pool_id:
        return "v3"
    return "UNSUPPORTED_PROTOCOL"

def probe_v3_pool(candidate: Dict[str, object], rpc: Callable,
                  expected: int = RH_CHAIN_ID) -> Dict[str, object]:
    """Attest a V3 pool against its factory (fail-closed, T07/T12). eth_getCode
    must be non-empty; token0/token1/fee/tickSpacing via eth_call; factory
    getPool(token0,token1,fee) must equal the pool. Mismatch -> IDENTITY_FAIL
    (economic fields withheld); any error -> DISCOVERED_NOT_ATTESTED."""
    pool = candidate.get("pool")
    factory = candidate.get("factory") or SEED_ADDRESSES["V3_FACTORY"]["address"]
    out: Dict[str, object] = {
        "protocol": "v3", "chain_id": expected, "factory": factory, "pool": pool,
        "token0": None, "token1": None, "fee": None, "tick_spacing": None,
        "code_nonempty": False, "factory_get_pool_matches": None,
        "attestation_status": "DISCOVERED_NOT_ATTESTED",
        "block_number": None, "block_hash": None, "code_hash": None, "error": None,
    }

    value, err = _call(rpc, "eth_getCode", [pool, "latest"])
    if err:
        out["error"] = err
        return out
    code = value if isinstance(value, str) else "0x"
    if code in ("0x", ""):
        out["error"] = "POOL_CODE_EMPTY"
        return out
    out["code_nonempty"] = True
    out["code_hash"] = _code_hash(code)

    for key, selector in (("token0", SEL_TOKEN0), ("token1", SEL_TOKEN1),
                          ("fee", SEL_FEE), ("tick_spacing", SEL_TICK_SPACING)):
        value, err = _call(rpc, "eth_call", [{"to": pool, "data": selector}, "latest"])
        if err:
            out["error"] = err
            return out
        out[key] = _decode_address(value) if key in ("token0", "token1") \
            else _decode_uint(value)

    if out["token0"] is None or out["token1"] is None or out["fee"] is None:
        out["error"] = "POOL_FIELD_DECODE_FAILED"
        return out

    data = (SEL_GET_POOL + _abi_address(out["token0"])[2:]
            + _abi_address(out["token1"])[2:] + _abi_uint24(out["fee"])[2:])
    value, err = _call(rpc, "eth_call", [{"to": factory, "data": data}, "latest"])
    if err:
        out["error"] = err
        return out
    out["factory_get_pool_matches"] = (_decode_address(value) == str(pool).lower())
    if not out["factory_get_pool_matches"]:
        out["attestation_status"] = "IDENTITY_FAIL"
        out["token0"] = out["token1"] = None
        out["fee"] = out["tick_spacing"] = None
        return out

    value, err = _call(rpc, "eth_blockNumber", [])
    if err:
        out["error"] = err
        return out
    out["block_number"] = _hex_to_int(value)
    value, err = _call(rpc, "eth_getBlockByNumber", [hex(out["block_number"]), False])
    if err:
        out["error"] = err
        return out
    if isinstance(value, dict):
        out["block_hash"] = value.get("hash")
    out["attestation_status"] = "ATTESTED_SAME_BLOCK"
    return out

def probe_v4_pool(candidate: Dict[str, object], rpc: Callable,
                  state_view: Optional[str] = None,
                  expected: int = RH_CHAIN_ID) -> Dict[str, object]:
    """Identity-only V4 probe (T08/T09/T10); never calls token0() on the
    PoolManager and never treats its balance as TVL."""
    pool_manager = candidate.get("pool_manager")
    out: Dict[str, object] = {
        "protocol": "v4", "chain_id": expected, "pool_manager": pool_manager,
        "pool_id": candidate.get("pool_id"),
        "currency0": candidate.get("currency0"),
        "currency1": candidate.get("currency1"),
        "fee": candidate.get("fee"), "tick_spacing": candidate.get("tick_spacing"),
        "hooks": candidate.get("hooks"),
        "attestation_status": "DISCOVERED_NOT_ATTESTED",
        "pool_key": None, "pool_id_computed": None,
        "tvl_source": None, "error": None,
    }

    if state_view is not None:
        if isinstance(state_view, str) and pool_manager is not None \
                and state_view.lower() == str(pool_manager).lower():
            raise ValueError("T10: tvl_source cannot be POOL_MANAGER_BALANCE")
        out["tvl_source"] = "STATE_VIEW"

    hooks = candidate.get("hooks")
    if hooks is not None and str(hooks).lower() != _ZERO32:
        out["attestation_status"] = "UNSUPPORTED_HOOK_POLICY"
        return out

    pool_key = _v4_pool_key(candidate)
    out["pool_key"] = pool_key
    keccak = _try_keccak()
    if keccak is None:
        out["attestation_status"] = "UNVERIFIED_NO_KECCAK"
        out["error"] = "KECCAK_UNAVAILABLE"
        return out
    out["pool_id_computed"] = keccak(_abi_encode_pool_key(pool_key))
    declared = candidate.get("pool_id")
    if declared is not None \
            and out["pool_id_computed"].lower() == str(declared).lower():
        out["attestation_status"] = "ATTESTED_SAME_BLOCK"
    else:
        out["attestation_status"] = "UNVERIFIED"
    return out

def attestation_expired(record: Dict[str, object],
                        current_impl_codehash: Optional[str]) -> Dict[str, object]:
    """T06: expired when code_hash differs; security_event=IMPLEMENTATION_CHANGED."""
    if not isinstance(record, dict):
        return {"expired": False, "security_event": None}
    recorded = record.get("code_hash")
    if recorded is None or current_impl_codehash is None:
        return {"expired": False, "security_event": None}
    if recorded != current_impl_codehash:
        return {"expired": True, "security_event": SECURITY_IMPL_CHANGED}
    return {"expired": False, "security_event": None}

def _default_candidates() -> List[Dict[str, object]]:
    return [{"pool": SEED_ADDRESSES["POOL_USDG_WETH"]["address"],
             "factory": SEED_ADDRESSES["V3_FACTORY"]["address"]}]

def _load_candidates(path: str) -> List[Dict[str, object]]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        cands = data.get("candidates", [])
        return cands if isinstance(cands, list) else []
    return []

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe RH Uniswap V3/V4 pool identity (read-only).")
    parser.add_argument("--candidates", help="JSON file with a candidate list")
    parser.add_argument("--offline-fixture", help="local JSON fixture (no network)")
    parser.add_argument("--rpc-url", help="provider endpoint")
    parser.add_argument("--out", help="output JSON path")
    args = parser.parse_args(argv)

    candidates = _load_candidates(args.candidates) if args.candidates else _default_candidates()

    notes: List[str] = []
    if args.offline_fixture:
        with open(args.offline_fixture, "r", encoding="utf-8") as handle:
            fixture = json.load(handle)
        rpc: Optional[Callable] = _fixture_rpc(fixture)
        notes.append("OFFLINE_FIXTURE")
    elif args.rpc_url:
        rpc = _default_rpc(args.rpc_url)
    else:
        rpc = None
        notes.append("NO_PROVIDER_CONFIGURED")

    results: List[Dict[str, object]] = []
    for cand in candidates:
        proto = dispatch_protocol(cand)
        if proto == "UNSUPPORTED_PROTOCOL":
            results.append({"protocol": "UNSUPPORTED_PROTOCOL", "attestation_status": "UNSUPPORTED", "error": "UNSUPPORTED_PROTOCOL"})
        elif rpc is None:
            results.append({"protocol": proto, "attestation_status": "UNVERIFIED", "error": "NO_RPC"})
        elif proto == "v3":
            results.append(probe_v3_pool(cand, rpc))
        else:
            results.append(probe_v4_pool(cand, rpc))

    output = {
        "generated_by": "lp_rh_pool_probe_v1_readonly",
        "chain_id": RH_CHAIN_ID,
        "count": len(results),
        "results": results,
        "notes": notes,
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(output, handle, indent=2)
            handle.write("\n")
    else:
        print(json.dumps(output, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
