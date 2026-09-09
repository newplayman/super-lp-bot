#!/usr/bin/env python3
"""RH-02h: write identity & capability evidence into the RH store.

Stage A blocker: PRD §21.1 requires that identity and capability evidence be
clear. The three producing modules (registry / capabilities / pool_probe)
already exist and are tested; this package only CALLS them and maps their
return values into the three evidence tables. It does not modify those modules.

Read-only research pipeline. Pure offline: data is fed in via JSON files; this
module never touches the network, wallets, or chain state.

Tables written (DDL in scripts/lp_rh_store_v1_readonly.py):
  rh_assets, rh_pool_registry, rh_contract_attestations

Every write uses INSERT OR REPLACE (primary keys are defined, so this is
idempotent). Fields the producing modules do not emit are written as NULL and
counted in the returned ``missing_fields`` dict, so gaps stay visible instead
of being silently nulled.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_registry_v1_readonly import (  # noqa: E402
    RH_CHAIN_ID,
    asset_from_json,
    normalize_capability,
)
from scripts.lp_rh_pool_probe_v1_readonly import dispatch_protocol  # noqa: E402
from scripts.lp_rh_store_v1_readonly import migrate, open_store  # noqa: E402

# Nullable columns per target table. A NULL here means "the producing module /
# input did not supply this field"; it is surfaced via missing_fields.
_ASSET_NULLABLE = (
    "symbol_display", "uid", "underlying", "decimals", "multiplier_raw",
    "status", "capability_json", "source_payload_hash",
)
_POOL_NULLABLE = ("pool_address", "pool_id", "token0", "token1", "fee",
                  "tick_spacing", "hooks")
_ATTEST_NULLABLE = ("code_hash", "implementation", "abi_version",
                    "evidence_json", "expires_at")
# Required columns that must come from the input record (not the params).
_ATTEST_REQUIRED = ("address", "block_hash", "attestation_status")


def _now_rfc3339() -> str:
    """Current UTC time as an RFC3339 string (write timestamp, not module data)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_list(payload: Any, key: str) -> List[dict]:
    """Accept either a bare list or a ``{key: [...]}`` envelope; drop non-dicts."""
    if payload is None:
        return []
    if isinstance(payload, dict):
        payload = payload.get(key, [])
    if not isinstance(payload, list):
        raise ValueError(f"INPUT_NOT_A_LIST: {key}")
    return [item for item in payload if isinstance(item, dict)]


def _lc(value: Any) -> Optional[str]:
    """Lower-cased string, or None when missing/empty. For addresses / ids."""
    if value is None:
        return None
    text = str(value)
    return text.lower() if text else None


def _raw(value: Any) -> Optional[Any]:
    """The value as-is, or None when missing/empty. For fee / spacing / hooks."""
    if value is None:
        return None
    if isinstance(value, str) and value == "":
        return None
    return value


def _json_field(value: Any) -> Optional[str]:
    """Serialize a structured field to JSON text; pass strings through."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def _insert_or_replace(conn: sqlite3.Connection, table: str, row: Dict[str, Any],
                       nullable: tuple, result: Dict[str, Any]) -> None:
    """One idempotent INSERT OR REPLACE; count NULL nullable columns."""
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) "
        f"VALUES ({placeholders})",
        [row[c] for c in cols],
    )
    for col in nullable:
        if row.get(col) is None:
            result["missing_fields"][col] = result["missing_fields"].get(col, 0) + 1


def _pool_key(protocol: str, candidate: Mapping[str, Any]) -> Optional[str]:
    """The registry primary-key component: pool address (v3) or pool_id (v4)."""
    if protocol == "v3":
        return _lc(candidate.get("pool"))
    if protocol == "v4":
        return _lc(candidate.get("pool_id"))
    return None


def write_assets(conn: sqlite3.Connection, assets_json: Any, *,
                 chain_id: int, metadata_version: int,
                 source: str) -> Dict[str, Any]:
    """Map registry AssetIdentity + SessionCapability rows into rh_assets.

    The identity gate is enforced here: a batch whose ``chain_id`` is not the
    RH chain (4663) is skipped wholesale, so the gate cannot be bypassed at the
    write layer.
    """
    result: Dict[str, Any] = {"written": 0, "skipped": 0, "missing_fields": {}}
    assets = _as_list(assets_json, "assets")
    if chain_id != RH_CHAIN_ID:
        result["skipped"] = len(assets)
        return result
    now = _now_rfc3339()
    for asset_json in assets:
        try:
            identity = asset_from_json(chain_id, asset_json,
                                       str(metadata_version), source)
        except ValueError:
            result["skipped"] += 1
            continue
        capability = normalize_capability(asset_json)
        row = {
            "chain_id": chain_id,
            "address": identity.address,
            "metadata_version": int(metadata_version),
            "symbol_display": identity.symbol_display or None,
            "uid": identity.uid,
            "underlying": identity.underlying,
            "decimals": identity.decimals,
            "multiplier_raw": None,
            "status": None,
            "capability_json": json.dumps(dataclasses.asdict(capability),
                                          sort_keys=True),
            "source_payload_hash": None,
            "updated_at": now,
        }
        _insert_or_replace(conn, "rh_assets", row, _ASSET_NULLABLE, result)
        result["written"] += 1
    conn.commit()
    return result


def write_pool_registry(conn: sqlite3.Connection, candidates: Any, *,
                        chain_id: int) -> Dict[str, Any]:
    """Map discovered pool candidates into rh_pool_registry.

    ``protocol`` comes from dispatch_protocol (never hard-coded). A candidate
    dispatch_protocol cannot place (UNSUPPORTED_PROTOCOL) or that yields no
    pool_key is skipped. attestation_status is DISCOVERED_NOT_ATTESTED: this
    writer only records discovery, it never attests.
    """
    result: Dict[str, Any] = {"written": 0, "skipped": 0, "missing_fields": {}}
    cands = _as_list(candidates, "candidates")
    if chain_id != RH_CHAIN_ID:
        result["skipped"] = len(cands)
        return result
    now = _now_rfc3339()
    for candidate in cands:
        protocol = dispatch_protocol(candidate)
        pool_key = _pool_key(protocol, candidate)
        if protocol == "UNSUPPORTED_PROTOCOL" or not pool_key:
            result["skipped"] += 1
            continue
        row = {
            "chain_id": chain_id,
            "protocol": protocol,
            "pool_key": pool_key,
            "pool_address": _lc(candidate.get("pool")),
            "pool_id": _lc(candidate.get("pool_id")),
            "token0": _lc(candidate.get("token0")),
            "token1": _lc(candidate.get("token1")),
            "fee": _raw(candidate.get("fee")),
            "tick_spacing": _raw(candidate.get("tick_spacing")),
            "hooks": _raw(candidate.get("hooks")),
            "attestation_status": "DISCOVERED_NOT_ATTESTED",
            "discovered_at": now,
        }
        _insert_or_replace(conn, "rh_pool_registry", row, _POOL_NULLABLE, result)
        result["written"] += 1
    conn.commit()
    return result


def write_attestations(conn: sqlite3.Connection, probes: Any, *,
                       chain_id: int, policy_version: str) -> Dict[str, Any]:
    """Map produced attestation records into rh_contract_attestations.

    A record missing a required column (address / block_hash /
    attestation_status) raises naming that column -- it is never written as an
    empty string.
    """
    result: Dict[str, Any] = {"written": 0, "skipped": 0, "missing_fields": {}}
    records = _as_list(probes, "probes")
    if chain_id != RH_CHAIN_ID:
        result["skipped"] = len(records)
        return result
    now = _now_rfc3339()
    for record in records:
        for col in _ATTEST_REQUIRED:
            if record.get(col) in (None, ""):
                raise ValueError(f"ATTESTATION_REQUIRED_MISSING: {col}")
        row = {
            "chain_id": chain_id,
            "address": _lc(record.get("address")),
            "block_hash": record.get("block_hash"),
            "policy_version": policy_version,
            "attestation_status": record.get("attestation_status"),
            "code_hash": _raw(record.get("code_hash")),
            "implementation": _raw(record.get("implementation")),
            "abi_version": _raw(record.get("abi_version")),
            "evidence_json": _json_field(record.get("evidence_json")),
            "expires_at": _raw(record.get("expires_at")),
            "created_at": now,
        }
        _insert_or_replace(conn, "rh_contract_attestations", row,
                           _ATTEST_NULLABLE, result)
        result["written"] += 1
    conn.commit()
    return result


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write RH identity/capability evidence (offline).")
    parser.add_argument("--db", required=True)
    parser.add_argument("--assets-json")
    parser.add_argument("--candidates-json")
    parser.add_argument("--probes-json")
    parser.add_argument("--out", required=True)
    parser.add_argument("--chain-id", type=int, default=RH_CHAIN_ID)
    parser.add_argument("--metadata-version", type=int, default=1)
    parser.add_argument("--source", default="rh-evidence-writer-v1")
    parser.add_argument("--policy-version", default="v1")
    args = parser.parse_args(argv)

    conn = open_store(args.db)
    try:
        migrate(conn)
        report: Dict[str, Any] = {}
        if args.assets_json:
            report["assets"] = write_assets(
                conn, _load_json(args.assets_json),
                chain_id=args.chain_id,
                metadata_version=args.metadata_version,
                source=args.source)
        if args.candidates_json:
            report["pool_registry"] = write_pool_registry(
                conn, _load_json(args.candidates_json),
                chain_id=args.chain_id)
        if args.probes_json:
            report["attestations"] = write_attestations(
                conn, _load_json(args.probes_json),
                chain_id=args.chain_id, policy_version=args.policy_version)
        conn.commit()
    finally:
        conn.close()

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
