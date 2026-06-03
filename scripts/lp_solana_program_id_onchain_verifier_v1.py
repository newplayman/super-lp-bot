#!/usr/bin/env python3
"""Solana program id on-chain verifier (read-only).

Reads a registry v2 JSON, and for each officially_source_verified program id
queries getAccountInfo on the verified RPC endpoint(s) to check
executable, owner, lamports, data length, programdata (if upgradeable).

Safety: read-only. No keypair, no signing, no transactions.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Solana program-derived address for upgradeable loader programdata
# BPF Loader Upgradeable (ProgramData) - well-known public constant
BPF_LOADER_UPGRADEABLE_PROGRAM = "BPFLoaderUpgradeab1e11111111111111111111111"
BPF_LOADER_V2 = "BPFLoader2111111111111111111111111111111111"
BPF_LOADER_V3 = "BPFLoaderV111111111111111111111111111111111"

PUBLIC_FALLBACK_RPCS = [
    "https://api.mainnet-beta.solana.com",
    "https://solana.publicnode.com",
]

# well-known public system programs
SYSTEM_PROGRAMS = {
    "11111111111111111111111111111111",  # System Program
    "Vote111111111111111111111111111111111111111",  # Vote
    "Stake11111111111111111111111111111111111111",  # Stake
    "Config11111111111111111111111111111111111111",  # Config
    "ComputeBudget111111111111111111111111111111",  # Compute Budget
    "BPFLoader2111111111111111111111111111111111",
    "BPFLoaderUpgradeab1e11111111111111111111111",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "ATokenGPvbdGVxr1b2hvZbsiqEq5pc6Ihf78Aa6h7owEQ",
    "So11111111111111111111111111111111111111112",  # wSOL
}


def _hash_host(url: str) -> str:
    import hashlib
    return hashlib.sha256(url.encode()).hexdigest()[:8]


def _resolve_rpc() -> str:
    for env in ("SOLANA_RPC_URL", "SOLANA_RPC_PRIMARY", "LPBOT_SOLANA_RPC_URL"):
        v = os.environ.get(env)
        if v:
            return v
    return PUBLIC_FALLBACK_RPCS[0]


def _rpc_call(url: str, method: str, params: list | None = None,
              timeout: float = 10.0) -> tuple[Any, float, str]:
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
    except Exception as e:
        return None, (time.time() - t0) * 1000.0, repr(e)[:200]


def _derive_programdata(program_id: str) -> str:
    """PDA for BPFLoaderUpgradeable programdata from program_id.

    v1 placeholder: skip programdata detail; rely on getAccountInfo
    on the program_id itself for executable flag.
    Full PDA derivation (involving base58->bytes, sha256) is a future enhancement.
    """
    return None


def verify_program(url: str, program_id: str, timeout: float = 15.0) -> dict:
    out = {
        "program_id": program_id,
        "account_exists": False,
        "executable": False,
        "owner": "",
        "lamports": 0,
        "data_len": 0,
        "upgradeable_program": "unknown",
        "programdata_address": "",
        "verification_status": "not_found",
        "confidence": 0.0,
        "latency_ms": 0.0,
        "invalid_reason": "",
    }
    if program_id in SYSTEM_PROGRAMS:
        # Well-known public system program - skip on-chain verify; mark as confirmed
        out["verification_status"] = "system_program_known"
        out["confidence"] = 0.95
        out["invalid_reason"] = "well-known public system program; not user-provided pid"
        return out

    # try up to 3 times with backoff for transient RPC errors
    for attempt in range(3):
        r, lat, err = _rpc_call(url, "getAccountInfo", [program_id, {"encoding": "base64"}], timeout=timeout)
        out["latency_ms"] = round(lat, 2)
        if not err:
            break
        if attempt < 2:
            time.sleep(0.5 * (attempt + 1))
    if err:
        out["verification_status"] = "rpc_error"
        out["invalid_reason"] = err[:200]
        return out
    if isinstance(r, dict) and r.get("value") is not None:
        v = r["value"]
        out["account_exists"] = True
        out["executable"] = bool(v.get("executable", False))
        out["owner"] = v.get("owner", "")
        data = v.get("data", ["", ""])
        if isinstance(data, list) and len(data) >= 1:
            out["data_len"] = len(data[0]) if isinstance(data[0], str) else 0
        out["lamports"] = v.get("lamports", 0)
        # upgradeable loader detection
        if out["owner"] == "BPFLoaderUpgradeab1e11111111111111111111111":
            out["upgradeable_program"] = "yes"
            pda = _derive_programdata(program_id)
            out["programdata_address"] = pda or ""
        elif out["owner"] in ("BPFLoader2111111111111111111111111111111111",
                              "BPFLoaderV111111111111111111111111111111111"):
            out["upgradeable_program"] = "no_legacy_loader"
        if out["executable"]:
            out["verification_status"] = "verified"
            out["confidence"] = 0.95
        else:
            out["verification_status"] = "account_exists_not_executable"
            out["confidence"] = 0.3
            out["invalid_reason"] = "account exists but is not executable"
    elif r is not None and isinstance(r, dict) and r.get("value") is None:
        out["verification_status"] = "not_found"
        out["invalid_reason"] = "getAccountInfo returned null (pid not on mainnet or not yet deployed)"
    return out


def main() -> int:
    p = argparse.ArgumentParser(
        description="Solana program id on-chain verifier (read-only)"
    )
    p.add_argument("--run-id", required=True)
    p.add_argument("--registry-json", required=True,
                   help="registry v2 JSON (from Stage D)")
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reg = json.loads(Path(args.registry_json).read_text())
    rpc_url = _resolve_rpc()
    rpc_host_hash = _hash_host(rpc_url)
    sys.stderr.write(f"verifying via RPC host_hash={rpc_host_hash}\n")

    results = []
    for entry in reg["registry"]:
        if not entry.get("oficial_source_verified"):
            # skip unknown
            results.append({
                "protocol": entry["protocol"],
                "program_id": entry.get("program_id"),
                "account_exists": False,
                "executable": False,
                "owner": "",
                "lamports": 0,
                "data_len": 0,
                "upgradeable_program": "unknown",
                "programdata_address": "",
                "verification_status": "skipped_unknown",
                "confidence": 0.0,
                "latency_ms": 0.0,
                "invalid_reason": "oficial_source_verified=False; per spec skip on-chain verify",
            })
            continue
        pid = entry["program_id"]
        if not pid:
            results.append({
                "protocol": entry["protocol"],
                "program_id": None,
                "account_exists": False,
                "executable": False,
                "owner": "",
                "lamports": 0,
                "data_len": 0,
                "upgradeable_program": "unknown",
                "programdata_address": "",
                "verification_status": "skipped_no_pid",
                "confidence": 0.0,
                "latency_ms": 0.0,
                "invalid_reason": "no program_id in registry",
            })
            continue
        sys.stderr.write(f"verifying {entry['protocol']} pid={pid}\n")
        v = verify_program(rpc_url, pid)
        v["protocol"] = entry["protocol"]
        results.append(v)
        time.sleep(0.2)  # polite

    out = {
        "stage": "LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1",
        "run_id": args.run_id,
        "phase": "E_onchain_program_verification_v2",
        "rpc_host_hash": rpc_host_hash,
        "verified_count": sum(1 for r in results if r["verification_status"] == "verified"),
        "skipped_count": sum(1 for r in results if r["verification_status"].startswith("skipped")),
        "results": results,
        "wallet_or_tx_touched": False,
    }
    json_path = out_dir / "solana_program_id_onchain_verification_v2.json"
    json_path.write_text(json.dumps(out, indent=2))

    csv_path = out_dir / "solana_program_id_onchain_verification_v2.csv"
    fieldnames = [
        "protocol", "program_id", "account_exists", "executable", "owner",
        "lamports", "data_len", "upgradeable_program", "programdata_address",
        "verification_status", "confidence", "latency_ms", "invalid_reason"
    ]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow(r)

    print(json.dumps({
        "verified_count": out["verified_count"],
        "skipped_count": out["skipped_count"],
        "total": len(results),
    }, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Stage F: bounded GPA smoke
# ---------------------------------------------------------------------------

def gpa_smoke(url: str, program_id: str, timeout: float = 8.0) -> dict:
    """Bounded getProgramAccounts smoke with dataSlice 0 bytes."""
    out = {
        "program_id": program_id,
        "gpa_attempted": True,
        "gpa_success": False,
        "returned_count_sample": 0,
        "data_slice_used": True,
        "filter_used": "dataSize unknown (dataSlice 0 bytes)",
        "timeout_sec": timeout,
        "rate_limit_seen": "no",
        "rpc_error_type": "",
        "needs_paid_rpc": "unknown",
        "needs_sdk_decoder": "unknown",
        "discovery_feasible": "unknown",
        "confidence": 0.0,
        "latency_ms": 0.0,
        "invalid_reason": "",
    }
    params = [
        program_id,
        {
            "encoding": "base64",
            "dataSlice": {"offset": 0, "length": 0},
        },
    ]
    for attempt in range(2):
        r, lat, err = _rpc_call(url, "getProgramAccounts", params, timeout=timeout)
        out["latency_ms"] = round(lat, 2)
        if not err:
            break
        if attempt == 0:
            time.sleep(0.5)
    if err:
        out["gpa_success"] = False
        out["rpc_error_type"] = err[:200]
        if "429" in err or "Too Many" in err or "rate" in err.lower():
            out["rate_limit_seen"] = "yes"
            out["needs_paid_rpc"] = "likely"
            out["confidence"] = 0.3
        else:
            out["confidence"] = 0.2
        return out
    if isinstance(r, list):
        out["gpa_success"] = True
        out["returned_count_sample"] = len(r)
        if len(r) > 0:
            out["needs_sdk_decoder"] = "yes"
            out["discovery_feasible"] = "yes_with_sdk"
            out["confidence"] = 0.8
        else:
            out["needs_sdk_decoder"] = "no_accounts_visible"
            out["discovery_feasible"] = "yes_no_accounts"
            out["confidence"] = 0.6
    return out


def gpa_main() -> int:
    p = argparse.ArgumentParser(
        description="Solana bounded GPA smoke v2 (read-only)"
    )
    p.add_argument("--run-id", required=True)
    p.add_argument("--registry-json", required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reg = json.loads(Path(args.registry_json).read_text())
    rpc_url = _resolve_rpc()
    rpc_host_hash = _hash_host(rpc_url)
    sys.stderr.write(f"GPA smoke via RPC host_hash={rpc_host_hash}\n")

    results = []
    # load verification v2
    ver_json_path = Path(args.registry_json).parent / "solana_program_id_onchain_verification_v2.json"
    ver_data = json.loads(ver_json_path.read_text())
    verified_map = {r["protocol"]: r for r in ver_data["results"]
                   if r["verification_status"] == "verified"}

    for entry in reg["registry"]:
        if entry["protocol"] not in verified_map:
            results.append({
                "protocol": entry["protocol"],
                "program_id": entry.get("program_id"),
                "gpa_attempted": False,
                "gpa_success": False,
                "returned_count_sample": 0,
                "data_slice_used": True,
                "filter_used": "n/a",
                "timeout_sec": 0.0,
                "rate_limit_seen": "no",
                "rpc_error_type": "",
                "needs_paid_rpc": "unknown",
                "needs_sdk_decoder": "unknown",
                "discovery_feasible": "no",
                "confidence": 0.0,
                "latency_ms": 0.0,
                "invalid_reason": "not_verified_onchain; per spec skip GPA smoke",
            })
            continue
        pid = entry["program_id"]
        sys.stderr.write(f"GPA smoke {entry['protocol']} pid={pid}\n")
        g = gpa_smoke(rpc_url, pid)
        g["protocol"] = entry["protocol"]
        results.append(g)
        time.sleep(0.3)

    out = {
        "stage": "LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1",
        "run_id": args.run_id,
        "phase": "F_bounded_gpa_smoke_v2",
        "rpc_host_hash": rpc_host_hash,
        "gpa_success_count": sum(1 for r in results if r["gpa_success"]),
        "results": results,
        "wallet_or_tx_touched": False,
    }
    json_path = out_dir / "solana_gpa_smoke_v2.json"
    json_path.write_text(json.dumps(out, indent=2))

    csv_path = out_dir / "solana_gpa_smoke_v2.csv"
    fieldnames = [
        "protocol", "program_id", "gpa_attempted", "gpa_success",
        "returned_count_sample", "data_slice_used", "filter_used",
        "timeout_sec", "rate_limit_seen", "rpc_error_type",
        "needs_paid_rpc", "needs_sdk_decoder", "discovery_feasible",
        "confidence", "latency_ms", "invalid_reason"
    ]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow(r)

    print(json.dumps({
        "gpa_success_count": out["gpa_success_count"],
        "gpa_attempted_count": sum(1 for r in results if r["gpa_attempted"]),
        "total": len(results),
    }, indent=2))
    return 0



if __name__ == "__main__":
    # dispatch on first arg: 'gpa' -> gpa_main, default -> main (verify)
    if len(sys.argv) > 1 and sys.argv[1] == "gpa":
        sys.argv.pop(1)
        sys.exit(gpa_main())
    sys.exit(main())
