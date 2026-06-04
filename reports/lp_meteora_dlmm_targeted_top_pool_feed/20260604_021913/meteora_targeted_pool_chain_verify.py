#!/usr/bin/env python3
"""Stage E: chain verify Meteora DLMM candidate pools via public RPC.

For each candidate address:
  * getAccountInfo (base64, confirmed)
  * check: account exists, owner == Meteora DLMM program
  * check: data_len == 904 (LbPair struct)
  * dedupe by address
  * mark selected_for_sdk_decode
"""
import json
import csv
import os
import time
import urllib.request
import urllib.error
import concurrent.futures

REPORT_DIR = os.environ["REPORT_DIR"]
os.makedirs(f"{REPORT_DIR}/data", exist_ok=True)

METEORA_DLMM_PROGRAM = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
EXPECTED_DATA_LEN = 904

RPC_URLS = [
    "https://solana-rpc.publicnode.com",
    "https://api.mainnet-beta.solana.com",
]


def rpc_get_account_info(pubkey, rpc_url, timeout=10):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [pubkey, {"encoding": "base64", "commitment": "confirmed"}],
    }
    req = urllib.request.Request(
        rpc_url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "lpbot-research-readonly/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def verify_one(addr, rpc_url):
    """Verify one address. Returns dict."""
    out = {
        "pool_address": addr,
        "owner": None,
        "owner_is_meteora_dlmm": False,
        "data_len": None,
        "verified": False,
        "duplicate": False,
        "selected_for_sdk_decode": False,
        "invalid_reason": None,
        "rpc_url_used": None,
        "latency_ms": None,
    }
    last_err = None
    for rpc in RPC_URLS:
        t0 = time.time()
        try:
            d = rpc_get_account_info(addr, rpc, timeout=10)
            latency = int((time.time() - t0) * 1000)
            out["rpc_url_used"] = rpc
            out["latency_ms"] = latency
            value = d.get("result", {}).get("value")
            if value is None:
                out["invalid_reason"] = "account_null"
                return out
            out["owner"] = value.get("owner")
            data_b64 = value.get("data", [None, None])[0]
            if data_b64:
                import base64
                data = base64.b64decode(data_b64)
                out["data_len"] = len(data)
            if out["owner"] != METEORA_DLMM_PROGRAM:
                out["invalid_reason"] = f"owner_not_meteora_dlmm: {out['owner']}"
                return out
            if out["data_len"] != EXPECTED_DATA_LEN:
                out["invalid_reason"] = f"data_len_mismatch: {out['data_len']}"
                return out
            out["owner_is_meteora_dlmm"] = True
            out["verified"] = True
            out["selected_for_sdk_decode"] = True
            return out
        except Exception as e:
            last_err = str(e)[:80]
            out["rpc_url_used"] = rpc
            out["invalid_reason"] = f"rpc_error: {last_err}"
            continue
    return out


def main():
    cand_path = f"{REPORT_DIR}/meteora_targeted_candidate_source_collection.json"
    with open(cand_path) as f:
        candidates = json.load(f)
    print(f"loaded {len(candidates)} candidates from {cand_path}")

    # dedupe
    seen = set()
    unique = []
    for c in candidates:
        a = c["pool_address"]
        if a in seen:
            continue
        seen.add(a)
        unique.append(c)
    print(f"unique: {len(unique)}")

    # parallel chain verify
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(verify_one, c["pool_address"], RPC_URLS[0]): c for c in unique}
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            r = fut.result()
            results.append(r)
            done += 1
            if done % 10 == 0 or done == len(unique):
                print(f"  verified {done}/{len(unique)}")

    # mark duplicates
    addr_count = {}
    for r in results:
        addr_count[r["pool_address"]] = addr_count.get(r["pool_address"], 0) + 1
    for r in results:
        if addr_count[r["pool_address"]] > 1:
            r["duplicate"] = True

    # write JSON
    with open(f"{REPORT_DIR}/meteora_targeted_pool_chain_verify.json", "w") as f:
        json.dump(results, f, indent=2)

    # write CSV
    with open(f"{REPORT_DIR}/meteora_targeted_pool_chain_verify.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "pool_address", "owner", "owner_is_meteora_dlmm", "data_len",
            "verified", "duplicate", "selected_for_sdk_decode", "invalid_reason",
        ])
        for r in results:
            w.writerow([
                r["pool_address"], r["owner"], r["owner_is_meteora_dlmm"],
                r["data_len"], r["verified"], r["duplicate"],
                r["selected_for_sdk_decode"], r["invalid_reason"],
            ])

    # summary
    n = len(results)
    n_verified = sum(1 for r in results if r["verified"])
    def _ir(r):
        return r.get("invalid_reason") or ""
    n_owner_mismatch = sum(1 for r in results if _ir(r).startswith("owner_not_meteora_dlmm"))
    n_data_len_mismatch = sum(1 for r in results if _ir(r).startswith("data_len_mismatch"))
    n_account_null = sum(1 for r in results if _ir(r) == "account_null")
    n_rpc_error = sum(1 for r in results if _ir(r).startswith("rpc_error"))

    summary = {
        "stage": "LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1",
        "run_id": os.environ.get("RUN_ID", ""),
        "candidate_count": n,
        "verified_pool_count": n_verified,
        "owner_mismatch_count": n_owner_mismatch,
        "data_len_mismatch_count": n_data_len_mismatch,
        "account_null_count": n_account_null,
        "rpc_error_count": n_rpc_error,
        "duplicate_count": sum(1 for r in results if r["duplicate"]),
        "selected_for_sdk_decode_count": sum(1 for r in results if r["selected_for_sdk_decode"]),
    }
    with open(f"{REPORT_DIR}/data/chain_verify_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"summary: {summary}")


if __name__ == "__main__":
    main()
