#!/usr/bin/env python3
"""Stage G: chain verify Raydium AMM v4 candidate pools.

For each pool:
  getAccountInfo
  check owner == 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8
  check data_len == 752 (AMM v4 pool state size)
"""
import json
import csv
import os
import time
import urllib.request
import concurrent.futures
import base64

REPORT_DIR = os.environ["REPORT_DIR"]
RAYDIUM_AMM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
EXPECTED_DATA_LEN = 752  # AMM v4 pool state
RPC_URLS = [
    "https://solana-rpc.publicnode.com",
    "https://api.mainnet-beta.solana.com",
]


def http_post_json(url, payload, timeout=12):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "lpbot-research-readonly/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def rpc_get_account_info(pubkey, rpc_url):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [pubkey, {"encoding": "base64", "commitment": "confirmed"}],
    }
    return http_post_json(rpc_url, payload, timeout=12)


def verify_one(addr):
    out = {
        "pool_address": addr,
        "owner": None,
        "owner_is_raydium_cpmm": False,
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
            d = rpc_get_account_info(addr, rpc)
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
                out["data_len"] = len(base64.b64decode(data_b64))
            if out["owner"] != RAYDIUM_AMM_V4:
                out["invalid_reason"] = f"owner_not_raydium_amm_v4: {out['owner']}"
                return out
            if out["data_len"] != EXPECTED_DATA_LEN:
                out["invalid_reason"] = f"data_len_mismatch: {out['data_len']} (expected 752 for AMM v4)"
                return out
            out["owner_is_raydium_cpmm"] = True
            out["verified"] = True
            out["selected_for_sdk_decode"] = True
            return out
        except Exception as e:
            last_err = str(e)[:80]
            out["invalid_reason"] = f"rpc_error: {last_err}"
            continue
    return out


def main():
    cand_path = f"{REPORT_DIR}/raydium_cpmm_candidate_source_collection.json"
    with open(cand_path) as f:
        candidates = json.load(f)
    selected = [c for c in candidates if c.get("selected_for_chain_verify")]
    print(f"selected for chain verify: {len(selected)}")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(verify_one, c["pool_address"]): c for c in selected}
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            r = fut.result()
            results.append(r)
            done += 1
            if done % 20 == 0 or done == len(selected):
                n_v = sum(1 for x in results if x["verified"])
                print(f"  verified {done}/{len(selected)} (success={n_v})")

    addr_count = {}
    for r in results:
        addr_count[r["pool_address"]] = addr_count.get(r["pool_address"], 0) + 1
    for r in results:
        if addr_count[r["pool_address"]] > 1:
            r["duplicate"] = True

    with open(f"{REPORT_DIR}/raydium_cpmm_pool_chain_verification.json", "w") as f:
        json.dump(results, f, indent=2)

    with open(f"{REPORT_DIR}/raydium_cpmm_pool_chain_verification.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "pool_address", "owner", "owner_is_raydium_cpmm", "data_len",
            "verified", "duplicate", "selected_for_sdk_decode", "invalid_reason",
        ])
        for r in results:
            w.writerow([
                r["pool_address"], r["owner"], r["owner_is_raydium_cpmm"],
                r["data_len"], r["verified"], r["duplicate"],
                r["selected_for_sdk_decode"], r["invalid_reason"],
            ])

    def _ir(r):
        return r.get("invalid_reason") or ""
    n = len(results)
    n_v = sum(1 for r in results if r["verified"])
    n_owner_mm = sum(1 for r in results if _ir(r).startswith("owner_not_raydium_amm_v4"))
    n_data_mm = sum(1 for r in results if _ir(r).startswith("data_len_mismatch"))
    n_null = sum(1 for r in results if _ir(r) == "account_null")
    n_rpc = sum(1 for r in results if _ir(r).startswith("rpc_error"))

    summary = {
        "stage": "LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1",
        "run_id": os.environ.get("RUN_ID", ""),
        "candidate_count": n,
        "verified_pool_count": n_v,
        "owner_mismatch_count": n_owner_mm,
        "data_len_mismatch_count": n_data_mm,
        "account_null_count": n_null,
        "rpc_error_count": n_rpc,
        "duplicate_count": sum(1 for r in results if r["duplicate"]),
        "selected_for_sdk_decode_count": sum(1 for r in results if r["selected_for_sdk_decode"]),
    }
    with open(f"{REPORT_DIR}/data/chain_verify_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"summary: {summary}")


if __name__ == "__main__":
    main()
