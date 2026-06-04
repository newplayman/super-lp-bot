#!/usr/bin/env python3
"""Stage F: chain verify stable pool candidates.

For each pool:
  getAccountInfo
  check owner in accepted_programs (Orca Whirlpool / Meteora DAMM v2 / Meteora Stable Swap / Raydium AMM v4)
  check data_len in known range per protocol
"""
import json
import csv
import os
import time
import urllib.request
import concurrent.futures
import base64

REPORT_DIR = os.environ["REPORT_DIR"]

ACCEPTED_PROGRAMS = {
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": ("OrcaWhirlpool", 600, 1400),
    "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG": ("MeteoraDAMMv2", 600, 2000),
    "SSwpkEEcbUqx4vtoEByFjSkhKdCT862DNVb52nZg1UZ": ("MeteoraStableSwap", 600, 1000),
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": ("RaydiumAMMv4", 600, 800),
}
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


def verify_one(addr, source_type):
    out = {
        "pool_address": addr,
        "owner": None,
        "owner_program": None,
        "data_len": None,
        "verified": False,
        "duplicate": False,
        "selected_for_sdk_decode": False,
        "invalid_reason": None,
        "source_type": source_type,
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
            if out["owner"] not in ACCEPTED_PROGRAMS:
                out["invalid_reason"] = f"owner_not_accepted: {out['owner']}"
                return out
            out["owner_program"] = ACCEPTED_PROGRAMS[out["owner"]][0]
            min_len, max_len = ACCEPTED_PROGRAMS[out["owner"]][1], ACCEPTED_PROGRAMS[out["owner"]][2]
            if out["data_len"] < min_len or out["data_len"] > max_len:
                out["invalid_reason"] = f"data_len_out_of_range: {out['data_len']} (expected {min_len}-{max_len} for {out['owner_program']})"
                return out
            out["verified"] = True
            out["selected_for_sdk_decode"] = True
            return out
        except Exception as e:
            last_err = str(e)[:80]
            out["invalid_reason"] = f"rpc_error: {last_err}"
            continue
    return out


def main():
    cand_path = f"{REPORT_DIR}/stable_pool_candidate_source_collection.json"
    with open(cand_path) as f:
        candidates = json.load(f)
    print(f"candidates: {len(candidates)}")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(verify_one, c["pool_address"], c.get("source_type", "")): c for c in candidates}
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            r = fut.result()
            results.append(r)
            done += 1
            if done % 5 == 0 or done == len(candidates):
                n_v = sum(1 for x in results if x["verified"])
                print(f"  verified {done}/{len(candidates)} (success={n_v})")

    # mark duplicates
    addr_count = {}
    for r in results:
        addr_count[r["pool_address"]] = addr_count.get(r["pool_address"], 0) + 1
    for r in results:
        if addr_count[r["pool_address"]] > 1:
            r["duplicate"] = True

    with open(f"{REPORT_DIR}/stable_pool_chain_verification.json", "w") as f:
        json.dump(results, f, indent=2)

    with open(f"{REPORT_DIR}/stable_pool_chain_verification.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "pool_address", "owner", "owner_program", "data_len",
            "verified", "duplicate", "selected_for_sdk_decode", "invalid_reason", "source_type",
        ])
        for r in results:
            w.writerow([
                r["pool_address"], r["owner"], r["owner_program"], r["data_len"],
                r["verified"], r["duplicate"], r["selected_for_sdk_decode"],
                r["invalid_reason"], r["source_type"],
            ])

    def _ir(r):
        return r.get("invalid_reason") or ""
    n = len(results)
    n_v = sum(1 for r in results if r["verified"])
    by_program = {}
    for r in results:
        if r["verified"]:
            by_program[r["owner_program"]] = by_program.get(r["owner_program"], 0) + 1

    summary = {
        "stage": "LP_SOLANA_STABLE_POOL_RESEARCH_V1",
        "run_id": os.environ.get("RUN_ID", ""),
        "candidate_count": n,
        "verified_pool_count": n_v,
        "by_program": by_program,
        "duplicate_count": sum(1 for r in results if r["duplicate"]),
        "selected_for_sdk_decode_count": sum(1 for r in results if r["selected_for_sdk_decode"]),
    }
    with open(f"{REPORT_DIR}/data/chain_verify_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"summary: {summary}")


if __name__ == "__main__":
    main()
