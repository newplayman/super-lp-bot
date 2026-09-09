#!/usr/bin/env python3
"""RH asset registry and old/new schema adapter (read-only, offline-testable).

Scope and guarantees:
  * Read-only. This module never touches wallets, chain state, or RPC.
  * No key material and no transaction-submission path: it imports none of
    web3, eth_account, solana, or requests. Network capture of the real
    ``/rhj/assets`` response belongs to the RH-01b probe, not here.
  * Offline: every public function is exercisable from local JSON fixtures.

Asset primary key is ``(chain_id, token_address)``; ``symbol`` is display-only.
Robinhood's ``/rhj/assets`` is observed in two shapes:
  * ``LEGACY_FIELDS``  -- ``tradingCapabilities.{fractionalTradability,
    allDayTradability, extendedHoursFractionalTradability}`` (bools)
  * ``SESSION_NESTED`` -- ``tradingCapabilities.{market,extended,overnight}.
    {whole,fractional}`` (``TRADING_STATUS_*`` strings) plus ``tokenDecimals``

Unknown / missing / null / empty-string never means "tradable". When both
shapes are present and disagree, the result is ``SCHEMA_SEMANTIC_CONFLICT``.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional

# --- chain constants -------------------------------------------------------
RH_CHAIN_ID = 4663
RH_TESTNET_CHAIN_ID = 46630

# Discovery seeds only. Every entry is attested=False; presence here is not
# permission to trade and is not on-chain validation.
SEED_ADDRESSES: Dict[str, Dict[str, object]] = {
    "WETH": {"address": "0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73", "attested": False},
    "USDG": {"address": "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168", "attested": False},
    "V3_FACTORY": {"address": "0x1f7d7550b1b028f7571e69a784071f0205fd2efa", "attested": False},
    "V3_POSITION_MANAGER": {"address": "0x73991a25c818bf1f1128deaab1492d45638de0d3", "attested": False},
    "POOL_USDG_WETH": {"address": "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca", "attested": False},
}

# --- capability / schema vocabulary ---------------------------------------
TRADABLE, NOT_TRADABLE, UNKNOWN = "TRADABLE", "NOT_TRADABLE", "UNKNOWN"
SCHEMA_LEGACY, SCHEMA_NESTED = "LEGACY_FIELDS", "SESSION_NESTED"
SCHEMA_UNKNOWN, SCHEMA_CONFLICT = "UNKNOWN", "SCHEMA_SEMANTIC_CONFLICT"

# Higher value == more conservative. Used to combine whole/fractional.
_CONSERVATIVENESS = {TRADABLE: 0, UNKNOWN: 1, NOT_TRADABLE: 2}

_LEGACY_KEYS = (
    "fractionalTradability",
    "allDayTradability",
    "extendedHoursFractionalTradability",
)
_NESTED_KEYS = ("market", "extended", "overnight")
_ADDRESS_KEYS = ("tokenAddress", "assetAddress", "address")
_HEX = set("0123456789abcdefABCDEF")


@dataclass
class AssetIdentity:
    chain_id: int
    address: str
    symbol_display: str
    issuer: Optional[str] = None
    uid: Optional[str] = None
    underlying: Optional[str] = None
    decimals: Optional[int] = None
    metadata_version: str = ""
    source: str = ""
    attested: bool = False


@dataclass
class SessionCapability:
    market: str = UNKNOWN
    extended: str = UNKNOWN
    overnight: str = UNKNOWN
    schema_kind: str = SCHEMA_UNKNOWN
    raw_flags: Dict[str, object] = field(default_factory=dict)


# --- internal helpers ------------------------------------------------------
def _trading_capabilities(asset_json: Mapping[str, object]) -> Dict[str, object]:
    tc = asset_json.get("tradingCapabilities")
    return dict(tc) if isinstance(tc, dict) else {}


def _legacy_present(tc: Mapping[str, object]) -> bool:
    return any(k in tc for k in _LEGACY_KEYS)


def _nested_present(tc: Mapping[str, object]) -> bool:
    return any(k in tc for k in _NESTED_KEYS)


def _bool_to_status(value: object) -> str:
    if value is True:
        return TRADABLE
    if value is False:
        return NOT_TRADABLE
    return UNKNOWN


def _legacy_session(tc: Mapping[str, object]) -> tuple:
    return (
        _bool_to_status(tc.get("fractionalTradability")),
        _bool_to_status(tc.get("extendedHoursFractionalTradability")),
        _bool_to_status(tc.get("allDayTradability")),
    )


def _enum_to_status(value: object) -> str:
    if value == "TRADING_STATUS_TRADABLE":
        return TRADABLE
    if value in ("TRADING_STATUS_NOT_TRADABLE", "TRADING_STATUS_CLOSING_ONLY"):
        return NOT_TRADABLE
    return UNKNOWN


def _more_conservative(a: str, b: str) -> str:
    return a if _CONSERVATIVENESS[a] >= _CONSERVATIVENESS[b] else b


def _nested_session_value(tc: Mapping[str, object], key: str) -> str:
    node = tc.get(key)
    if not isinstance(node, dict):
        return UNKNOWN
    whole = _enum_to_status(node.get("whole"))
    fractional = _enum_to_status(node.get("fractional"))
    return _more_conservative(whole, fractional)


def _nested_session(tc: Mapping[str, object]) -> tuple:
    return (
        _nested_session_value(tc, "market"),
        _nested_session_value(tc, "extended"),
        _nested_session_value(tc, "overnight"),
    )


# --- public API ------------------------------------------------------------
def detect_schema(asset_json: Mapping[str, object]) -> str:
    """Classify the observed ``tradingCapabilities`` shape.

    Only legacy keys -> LEGACY_FIELDS; only nested sessions -> SESSION_NESTED;
    both -> compare derived semantics (equal -> SESSION_NESTED, else
    SCHEMA_SEMANTIC_CONFLICT); neither -> UNKNOWN.
    """
    tc = _trading_capabilities(asset_json)
    has_legacy = _legacy_present(tc)
    has_nested = _nested_present(tc)
    if has_legacy and not has_nested:
        return SCHEMA_LEGACY
    if has_nested and not has_legacy:
        return SCHEMA_NESTED
    if has_legacy and has_nested:
        if _legacy_session(tc) == _nested_session(tc):
            return SCHEMA_NESTED
        return SCHEMA_CONFLICT
    return SCHEMA_UNKNOWN


def normalize_capability(asset_json: Mapping[str, object]) -> SessionCapability:
    """Map either schema to a unified SessionCapability (fail-closed)."""
    tc = _trading_capabilities(asset_json)
    schema = detect_schema(asset_json)
    raw_flags: Dict[str, object] = {
        "raw_trading_capabilities": tc,
        "both_present": _legacy_present(tc) and _nested_present(tc),
    }
    if schema == SCHEMA_LEGACY:
        market, extended, overnight = _legacy_session(tc)
    elif schema == SCHEMA_NESTED:
        market, extended, overnight = _nested_session(tc)
    else:  # SCHEMA_UNKNOWN or SCHEMA_CONFLICT: never assume tradable.
        market = extended = overnight = UNKNOWN
    return SessionCapability(
        market=market,
        extended=extended,
        overnight=overnight,
        schema_kind=schema,
        raw_flags=raw_flags,
    )


def _opt_str(value: object) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _first_present(mapping: Mapping[str, object], *keys: str) -> Optional[str]:
    """First non-None value among ``keys`` as str, else None.

    Top-level original key first, then the measured feed key, so an old record
    carrying the original key still wins (backward compatible)."""
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return str(value)
    return None


def _extract_address(asset_json: Mapping[str, object],
                     chain_id: Optional[int] = None) -> Optional[str]:
    for key in _ADDRESS_KEYS:
        value = asset_json.get(key)
        if value is not None:
            return value
    # Top-level keys all empty: fall back to deployments[], taking the first
    # entry whose chainId equals chain_id. Never guess: deployments not a
    # list, an element that is not a dict, or no matching chainId -> None
    # (do not fall back to the first entry).
    deployments = asset_json.get("deployments")
    if not isinstance(deployments, list) or chain_id is None:
        return None
    for deployment in deployments:
        if not isinstance(deployment, dict):
            continue
        if deployment.get("chainId") != chain_id:
            continue
        address = deployment.get("contractAddress")
        if address is not None:
            return address
    return None


def _validate_address(address: object) -> None:
    if not isinstance(address, str):
        raise ValueError("ASSET_ADDRESS_INVALID")
    body = address[2:] if address.lower().startswith("0x") else address
    if len(body) != 40 or any(c not in _HEX for c in body):
        raise ValueError("ASSET_ADDRESS_INVALID")


def asset_from_json(
    chain_id: int,
    asset_json: Mapping[str, object],
    metadata_version: str,
    source: str,
) -> AssetIdentity:
    """Build an AssetIdentity from one /rhj/assets record.

    Raises ValueError("ASSET_ADDRESS_INVALID") when the address is missing or
    not a 40-hex address. Missing tokenDecimals -> decimals=None.
    """
    address = _extract_address(asset_json, chain_id=chain_id)
    _validate_address(address)
    decimals_raw = asset_json.get("tokenDecimals")
    decimals = int(decimals_raw) if decimals_raw is not None else None
    return AssetIdentity(
        chain_id=int(chain_id),
        address=str(address).lower(),
        symbol_display=_first_present(asset_json, "symbol", "tokenSymbol") or "",
        issuer=_opt_str(asset_json.get("issuer")),
        uid=_first_present(asset_json, "uid", "id"),
        underlying=_first_present(asset_json, "underlying", "isin"),
        decimals=decimals,
        metadata_version=metadata_version,
        source=source,
        attested=False,
    )


def verify_identity(
    candidate: AssetIdentity,
    registry: Mapping[str, AssetIdentity],
) -> str:
    """Check a candidate against a registry keyed by lower address.

    Missing address, differing symbol, uid, or decimals -> MISMATCH.
    A candidate whose symbol matches a *different* address is always MISMATCH.
    """
    known = registry.get(candidate.address.lower())
    if known is None:
        return "ASSET_IDENTITY_MISMATCH"
    if candidate.symbol_display != known.symbol_display:
        return "ASSET_IDENTITY_MISMATCH"
    if candidate.uid != known.uid:
        return "ASSET_IDENTITY_MISMATCH"
    if candidate.decimals != known.decimals:
        return "ASSET_IDENTITY_MISMATCH"
    return "ASSET_IDENTITY_OK"


def is_new_position_allowed(cap: SessionCapability, session: str) -> bool:
    """True only when the named session is TRADABLE (T05: else False)."""
    if session == "market":
        return cap.market == TRADABLE
    if session == "extended":
        return cap.extended == TRADABLE
    if session == "overnight":
        return cap.overnight == TRADABLE
    return False


def _read_json(path: str) -> object:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _assets_from_data(data: object) -> List[dict]:
    if isinstance(data, dict):
        assets = data.get("assets", [])
    elif isinstance(data, list):
        assets = data
    else:
        raise ValueError("ASSET_FILE_INVALID")
    if not isinstance(assets, list):
        raise ValueError("ASSET_FILE_INVALID")
    return assets


def load_assets(path: str) -> List[dict]:
    """Read a local assets JSON file (no network). Returns the asset list."""
    return _assets_from_data(_read_json(path))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an ASSET_ATTESTATIONS.json prototype (read-only).",
    )
    parser.add_argument("--assets-json", required=True, help="local assets JSON")
    parser.add_argument("--registry-out", required=True, help="output JSON path")
    parser.add_argument("--chain-id", type=int, default=RH_CHAIN_ID)
    args = parser.parse_args(argv)

    data = _read_json(args.assets_json)
    assets = _assets_from_data(data)
    metadata_version = (
        data.get("metadata_version", "rh-assets-v1")
        if isinstance(data, dict)
        else "rh-assets-v1"
    )
    source = "local-json:" + Path(args.assets_json).name

    attestations: List[dict] = []
    for asset in assets:
        chain_id = int(asset.get("chainId", args.chain_id))
        identity = asset_from_json(chain_id, asset, metadata_version, source)
        cap = normalize_capability(asset)
        attestations.append(
            {
                "chain_id": identity.chain_id,
                "address": identity.address,
                "symbol_display": identity.symbol_display,
                "attested": False,
                "attestation_status": "DISCOVERED_NOT_ATTESTED",
                "decimals": identity.decimals,
                "schema_kind": cap.schema_kind,
                "capability": {
                    "market": cap.market,
                    "extended": cap.extended,
                    "overnight": cap.overnight,
                },
                "metadata_version": identity.metadata_version,
                "source": identity.source,
            }
        )

    output = {
        "generated_by": "lp_rh_registry_v1_readonly",
        "default_chain_id": RH_CHAIN_ID,
        "count": len(attestations),
        "attestations": attestations,
    }
    with open(args.registry_out, "w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
