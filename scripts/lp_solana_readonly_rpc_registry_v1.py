#!/usr/bin/env python3
"""Solana read-only RPC registry and readiness script.

This is the Phase-1 entry from the Solana connector implementation roadmap:
verify public RPC endpoints work, identify which Solana LP protocols can
be entered in the next phase, and write a registry seed.

Safety: read-only. No keypair / private key / seed phrase / wallet.
No sendTransaction, no signing, no swap, no LP open/close, no bridge.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Public fallback RPCs (no keys; no secrets)
PUBLIC_FALLBACK_RPCS = [
    "https://api.mainnet-beta.solana.com",
    "https://solana.publicnode.com",
]

# Solana system program pubkey (well-known public constant; not from a wallet)
SYSTEM_PROGRAM = "11111111111111111111111111111111"

# Read-only RPC methods to smoke-test per spec
RPC_METHODS = [
    "getHealth",
    "getVersion",
    "getSlot",
    "getBlockHeight",
    "getLatestBlockhash",
    "getEpochInfo",
    "getGenesisHash",
]

# Bounded getProgramAccounts smoke limit
GPA_SMOKE_LIMIT_PER_PROGRAM = 5
GPA_SMOKE_TIMEOUT_SECONDS = 8.0


# ---------------------------------------------------------------------------

def _hash_host(url: str) -> str:
    """Return sha256[0:8] of the URL (for redaction)."""
    return hashlib.sha256(url.encode()).hexdigest()[:8]


def _source_type(url: str) -> str:
    if "helius" in url.lower():
        return "helius_env"
    if "quicknode" in url.lower():
        return "quicknode_env"
    if "mainnet-beta.solana.com" in url:
        return "public_mainnet_beta"
    if "publicnode.com" in url:
        return "public_publicnode"
    return "public_other"


def _endpoint_id(url: str) -> str:
    return f"{_source_type(url)}-{_hash_host(url)}"


def _rpc_call(url: str, method: str, params: list | None = None,
              timeout: float = 10.0) -> tuple[Any, float, str]:
    """Return (result, latency_ms, error)."""
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method,
        "params": params or [],
    }).encode()
    req = urllib.request.Request(
        url, data=body, headers={
            "Content-Type": "application/json",
            "User-Agent": "lpbot-solana-readonly-rpc/1.0",
        },
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            latency = (time.time() - t0) * 1000.0
            if "error" in data:
                return None, latency, json.dumps(data["error"])[:200]
            return data.get("result"), latency, ""
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return None, (time.time() - t0) * 1000.0, repr(e)[:200]
    except Exception as e:  # noqa
        return None, (time.time() - t0) * 1000.0, repr(e)[:200]


# ---------------------------------------------------------------------------

def collect_endpoints(args: argparse.Namespace) -> list[str]:
    """Collect RPC endpoint URLs (env + public fallback), redacted in output."""
    candidates: list[tuple[str, str]] = []  # (url, source_env_or_static)
    for env_name in ("SOLANA_RPC_URL", "SOLANA_RPC_PRIMARY", "LPBOT_SOLANA_RPC_URL"):
        v = os.environ.get(env_name)
        if v:
            candidates.append((v, env_name))
    for env_name in ("HELIUS_RPC_URL", "QUICKNODE_SOLANA_RPC_URL"):
        v = os.environ.get(env_name)
        if v:
            candidates.append((v, env_name))
    for url in PUBLIC_FALLBACK_RPCS:
        candidates.append((url, "public_fallback"))
    if args.rpc_override:
        candidates.insert(0, (args.rpc_override, "cli_override"))
    # de-dup
    seen = set()
    out = []
    for url, src in candidates:
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


# ---------------------------------------------------------------------------

def probe_endpoint(url: str) -> dict:
    """Probe a single endpoint with the 7 read-only methods + 1 getAccountInfo."""
    out: dict = {
        "endpoint_id": _endpoint_id(url),
        "source_type": _source_type(url),
        "host_hash": _hash_host(url),
        "health_ok": False,
        "version_ok": False,
        "slot_ok": False,
        "blockheight_ok": False,
        "latest_blockhash_ok": False,
        "epochinfo_ok": False,
        "genesishash_ok": False,
        "accountinfo_ok": False,
        "version_string": "",
        "slot": None,
        "block_height": None,
        "epoch": None,
        "avg_latency_ms": 0.0,
        "latency_samples_ms": [],
        "rate_limit_seen": "no",
        "usable_for_registry": False,
        "usable_for_getProgramAccounts": "unknown",
        "confidence": 0.0,
        "invalid_reason": "",
    }
    latencies: list[float] = []
    fails: list[str] = []

    # 1) getHealth
    r, lat, err = _rpc_call(url, "getHealth")
    if r == "ok" or (isinstance(r, str) and r.lower() == "ok"):
        out["health_ok"] = True
    elif err:
        fails.append(f"getHealth: {err[:80]}")
    latencies.append(lat)
    if "429" in err or "Too Many" in err or "rate" in err.lower():
        out["rate_limit_seen"] = "yes"

    # 2) getVersion
    r, lat, err = _rpc_call(url, "getVersion")
    if isinstance(r, dict) and "solana-core" in r:
        out["version_ok"] = True
        out["version_string"] = r.get("solana-core", "")
    elif err:
        fails.append(f"getVersion: {err[:80]}")
    latencies.append(lat)
    if "429" in err or "Too Many" in err:
        out["rate_limit_seen"] = "yes"

    # 3) getSlot
    r, lat, err = _rpc_call(url, "getSlot")
    if isinstance(r, int) and r > 0:
        out["slot_ok"] = True
        out["slot"] = r
    elif err:
        fails.append(f"getSlot: {err[:80]}")
    latencies.append(lat)

    # 4) getBlockHeight
    r, lat, err = _rpc_call(url, "getBlockHeight")
    if isinstance(r, int) and r > 0:
        out["blockheight_ok"] = True
        out["block_height"] = r
    elif err:
        fails.append(f"getBlockHeight: {err[:80]}")
    latencies.append(lat)

    # 5) getLatestBlockhash
    r, lat, err = _rpc_call(url, "getLatestBlockhash")
    if isinstance(r, dict) and "value" in r and "blockhash" in r.get("value", {}):
        out["latest_blockhash_ok"] = True
    elif err:
        fails.append(f"getLatestBlockhash: {err[:80]}")
    latencies.append(lat)

    # 6) getEpochInfo
    r, lat, err = _rpc_call(url, "getEpochInfo")
    if isinstance(r, dict) and "epoch" in r:
        out["epochinfo_ok"] = True
        out["epoch"] = r.get("epoch")
    elif err:
        fails.append(f"getEpochInfo: {err[:80]}")
    latencies.append(lat)

    # 7) getGenesisHash
    r, lat, err = _rpc_call(url, "getGenesisHash")
    if isinstance(r, str) and len(r) >= 32:
        out["genesishash_ok"] = True
    elif err:
        fails.append(f"getGenesisHash: {err[:80]}")
    latencies.append(lat)

    # 8) getAccountInfo on system program
    r, lat, err = _rpc_call(url, "getAccountInfo", [SYSTEM_PROGRAM, {"encoding": "base64"}])
    if isinstance(r, dict) and "value" in r and r["value"] is not None:
        out["accountinfo_ok"] = True
    elif err:
        fails.append(f"getAccountInfo: {err[:80]}")
    latencies.append(lat)

    # compute averages and confidence
    out["latency_samples_ms"] = [round(x, 2) for x in latencies]
    out["avg_latency_ms"] = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
    critical_ok = [out["health_ok"], out["version_ok"], out["slot_ok"],
                   out["blockheight_ok"], out["latest_blockhash_ok"]]
    out["usable_for_registry"] = all(critical_ok)
    n_critical = sum(critical_ok)
    out["confidence"] = round(n_critical / 5.0, 2)  # 0.0-1.0
    if not out["usable_for_registry"]:
        out["invalid_reason"] = "; ".join(fails[:3])[:300]
    # if all 8 ok, mark getProgramAccounts as likely usable
    if all(critical_ok) and out["accountinfo_ok"]:
        out["usable_for_getProgramAccounts"] = "likely"
    elif out["rate_limit_seen"] == "yes":
        out["usable_for_getProgramAccounts"] = "risky_rate_limited"
    return out


# ---------------------------------------------------------------------------

def gpa_smoke(url: str, program_id: str) -> dict:
    """Bounded getProgramAccounts smoke.

    Uses dataSlice to limit response size; respects the per-program limit.
    """
    out: dict = {
        "program_id": program_id,
        "gpa_attempted": True,
        "gpa_success": False,
        "filter_strategy": "dataSize + dataSlice (0,0)",
        "data_slice_strategy": "dataSlice: { offset: 0, length: 0 }",
        "returned_count_sample": 0,
        "rate_limit_seen": "no",
        "needs_paid_rpc": "unknown",
        "needs_sdk_decoder": "unknown",
        "confidence": 0.0,
        "blocker": "",
    }
    params = [
        program_id,
        {
            "encoding": "base64",
            "dataSlice": {"offset": 0, "length": 0},  # 0 bytes data, just count
        },
    ]
    r, lat, err = _rpc_call(url, "getProgramAccounts", params, timeout=GPA_SMOKE_TIMEOUT_SECONDS)
    if isinstance(r, list):
        out["gpa_success"] = True
        out["returned_count_sample"] = len(r)
        if len(r) > 0:
            out["needs_sdk_decoder"] = "yes"  # need to decode accounts
        else:
            out["needs_sdk_decoder"] = "no_accounts_visible_or_filter"
    elif err:
        out["gpa_success"] = False
        out["blocker"] = err[:200]
        if "429" in err or "Too Many" in err:
            out["rate_limit_seen"] = "yes"
            out["needs_paid_rpc"] = "likely"
    # only consider needs_paid_rpc = no if success and small response
    if out["gpa_success"] and out["returned_count_sample"] < 10000:
        out["needs_paid_rpc"] = "no"
        out["confidence"] = 0.8
    elif not out["gpa_success"] and out["rate_limit_seen"] == "yes":
        out["needs_paid_rpc"] = "likely"
        out["confidence"] = 0.3
    elif not out["gpa_success"]:
        out["confidence"] = 0.2
    return out


# ---------------------------------------------------------------------------

def verify_program(url: str, program_id: str) -> dict:
    """Verify program id via getAccountInfo + check executable flag."""
    out: dict = {
        "program_id": program_id,
        "account_exists": False,
        "executable": False,
        "owner": "",
        "data_len": 0,
        "lamports": 0,
        "verification_status": "not_found",
        "confidence": 0.0,
        "invalid_reason": "",
    }
    r, lat, err = _rpc_call(url, "getAccountInfo", [program_id, {"encoding": "base64"}])
    if isinstance(r, dict) and r.get("value") is not None:
        v = r["value"]
        out["account_exists"] = True
        out["executable"] = bool(v.get("executable", False))
        out["owner"] = v.get("owner", "")
        data = v.get("data", ["", ""])
        if isinstance(data, list) and len(data) >= 1:
            out["data_len"] = len(data[0]) if isinstance(data[0], str) else 0
        out["lamports"] = v.get("lamports", 0)
        if out["executable"]:
            out["verification_status"] = "verified"
            out["confidence"] = 0.95
        else:
            out["verification_status"] = "account_exists_not_executable"
            out["confidence"] = 0.3
            out["invalid_reason"] = "account exists but is not executable"
    elif err:
        out["verification_status"] = "not_found"
        out["invalid_reason"] = err[:200]
    return out


# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description="Solana read-only RPC registry + readiness (Phase 1)"
    )
    p.add_argument("--run-id", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--rpc-override", default=None,
                   help="single RPC URL to test (will be redacted in output)")
    p.add_argument("--skip-gpa-smoke", action="store_true",
                   help="skip bounded getProgramAccounts smoke per program")
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    endpoints = collect_endpoints(args)
    if not endpoints:
        sys.stderr.write("no RPC endpoints found\n")
        return 1

    # 1) probe each endpoint
    probe_results: list[dict] = []
    for url in endpoints:
        sys.stderr.write(f"probing endpoint: {url[:30]}...\n")
        probe_results.append(probe_endpoint(url))

    # 2) take the most usable endpoint for downstream checks
    usable = [p for p in probe_results if p["usable_for_registry"]]
    usable.sort(key=lambda x: (-x["confidence"], x["avg_latency_ms"]))
    primary = usable[0] if usable else None
    primary_url = None
    if primary:
        # map back to URL via endpoint_id
        for u, pr in zip(endpoints, probe_results):
            if pr["endpoint_id"] == primary["endpoint_id"]:
                primary_url = u
                break

    # 3) write RPC matrix
    rpc_matrix = {
        "stage": "LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1",
        "run_id": args.run_id,
        "phase": "C_rpc_readiness",
        "endpoint_count": len(endpoints),
        "usable_endpoint_count": len(usable),
        "primary_endpoint_id": primary["endpoint_id"] if primary else None,
        "primary_host_hash": primary["host_hash"] if primary else None,
        "primary_source_type": primary["source_type"] if primary else None,
        "probes": probe_results,
        "rpc_url_redaction_policy": "endpoint_id + source_type + host_hash only; full URL never printed",
    }
    json_path = out_dir / "solana_rpc_readiness_matrix.json"
    json_path.write_text(json.dumps(rpc_matrix, indent=2))

    csv_path = out_dir / "solana_rpc_readiness_matrix.csv"
    fieldnames = [
        "endpoint_id", "source_type", "host_hash",
        "health_ok", "version_ok", "slot_ok", "blockheight_ok",
        "latest_blockhash_ok", "epochinfo_ok", "genesishash_ok", "accountinfo_ok",
        "version_string", "slot", "block_height", "epoch",
        "avg_latency_ms", "rate_limit_seen", "usable_for_registry",
        "usable_for_getProgramAccounts", "confidence", "invalid_reason"
    ]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in probe_results:
            w.writerow(r)

    print(json.dumps({
        "endpoint_count": len(endpoints),
        "usable_endpoint_count": len(usable),
        "primary_endpoint_id": primary["endpoint_id"] if primary else None,
    }, indent=2))
    # save primary_url for downstream stages via output JSON sidecar
    if primary_url:
        (out_dir / "_primary_endpoint.txt").write_text(primary_url + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
