#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests


V2_SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
BASE_RPC_URL = os.environ.get("LPBOT_BASE_RPC_URL") or os.environ.get("BASE_RPC_URL") or "https://mainnet.base.org"
BLOCKS_PER_HOUR = 1800
CHUNK_SIZE = 5000


def read_csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, fieldnames):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def rpc_post(payload):
    resp = requests.post(BASE_RPC_URL, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def rpc_post_batch(payloads):
    resp = requests.post(BASE_RPC_URL, json=payloads, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise RuntimeError(f"batch rpc expected list, got {type(data)!r}")
    return {item["id"]: item for item in data}


def rpc_block_number():
    data = rpc_post({"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []})
    return int(data["result"], 16)


def chunked(start, end, size):
    cur = start
    while cur <= end:
        nxt = min(cur + size - 1, end)
        yield cur, nxt
        cur = nxt + 1


def fetch_logs_for_topic(pool_id, topic, start_block, end_block):
    all_logs = []
    last_error = ""
    for a, b in chunked(start_block, end_block, CHUNK_SIZE):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getLogs",
            "params": [{
                "fromBlock": hex(a),
                "toBlock": hex(b),
                "address": pool_id,
                "topics": [topic],
            }],
        }
        try:
            data = rpc_post(payload)
            if "error" in data:
                last_error = data["error"].get("message", str(data["error"]))
                continue
            all_logs.extend(data.get("result", []))
        except Exception as exc:
            last_error = str(exc)
    return all_logs, last_error


def pick_protocol(v2_logs, v3_logs):
    if v2_logs and not v3_logs:
        return "uniswap_v2_like", v2_logs
    if v3_logs and not v2_logs:
        return "uniswap_v3_like", v3_logs
    if v2_logs and v3_logs:
        return ("uniswap_v3_like", v3_logs) if len(v3_logs) >= len(v2_logs) else ("uniswap_v2_like", v2_logs)
    return "", []


def parse_uint256(word):
    return int(word, 16)


def parse_int256(word):
    value = int(word, 16)
    if value >= 2 ** 255:
        value -= 2 ** 256
    return value


def decode_v2_direction(log):
    data = log.get("data", "")[2:]
    if len(data) < 64 * 4:
        return "unknown"
    words = [data[i:i + 64] for i in range(0, 64 * 4, 64)]
    amount0_in, amount1_in, amount0_out, amount1_out = [parse_uint256(x) for x in words]
    if amount1_in > 0 and amount0_out > 0:
        return "buy"
    if amount0_in > 0 and amount1_out > 0:
        return "sell"
    return "unknown"


def decode_v3_direction(log):
    data = log.get("data", "")[2:]
    if len(data) < 64 * 2:
        return "unknown"
    words = [data[i:i + 64] for i in range(0, 64 * 2, 64)]
    amount0 = parse_int256(words[0])
    amount1 = parse_int256(words[1])
    if amount0 < 0 and amount1 > 0:
        return "buy"
    if amount0 > 0 and amount1 < 0:
        return "sell"
    return "unknown"


def topic_address(topic_word):
    if not topic_word:
        return ""
    word = topic_word.lower().replace("0x", "")
    if len(word) != 64:
        return ""
    return "0x" + word[-40:]


def actor_candidates_from_log(protocol, log):
    topics = log.get("topics") or []
    zero = "0x" + ("0" * 40)
    actors = []
    # Uniswap V3 Swap(sender indexed, recipient indexed, ...)
    # Uniswap V2 Swap(sender indexed, ..., to indexed)
    if protocol in {"uniswap_v2_like", "uniswap_v3_like"}:
        if len(topics) >= 2:
            actor = topic_address(topics[1])
            if actor and actor != zero:
                actors.append(actor)
        if len(topics) >= 3:
            actor = topic_address(topics[2])
            if actor and actor != zero and actor not in actors:
                actors.append(actor)
    return actors


def fetch_tx_from_map(tx_hashes):
    out = {}
    tx_hashes = sorted(set(tx_hashes))
    for i in range(0, len(tx_hashes), 100):
        batch = tx_hashes[i:i + 100]
        payloads = [
            {"jsonrpc": "2.0", "id": idx + 1, "method": "eth_getTransactionByHash", "params": [txh]}
            for idx, txh in enumerate(batch)
        ]
        try:
            results = rpc_post_batch(payloads)
        except Exception:
            continue
        for idx, txh in enumerate(batch, start=1):
            item = results.get(idx, {})
            result = item.get("result") or {}
            trader = (result.get("from") or "").lower()
            if trader:
                out[txh] = trader
    return out


def concentration_status(top1, top5):
    if top1 is None or top5 is None:
        return "missing"
    if top1 > 50 or top5 > 85:
        return "high"
    if top1 > 30 or top5 > 65:
        return "warn"
    return "ok"


def analyze_window(logs, protocol, block_cutoff):
    window_logs = [log for log in logs if int(log["blockNumber"], 16) >= block_cutoff]
    if not window_logs:
        return {
            "log_count": 0,
            "unique_traders": "",
            "buyer_count": "",
            "seller_count": "",
            "buy_count": "",
            "sell_count": "",
            "top1_trader_volume_share": "",
            "top5_trader_volume_share": "",
            "concentration_status": "missing",
            "data_quality_status": "missing",
            "failure_reason": "no_swap_logs",
            "trader_proxy_method": "unavailable",
        }
    trader_counts = Counter()
    buyers = set()
    sellers = set()
    buy_count = 0
    sell_count = 0
    event_actor_seen = False
    for log in window_logs:
        actors = actor_candidates_from_log(protocol, log)
        if actors:
            event_actor_seen = True
            for trader in actors:
                trader_counts[trader] += 1
        direction = decode_v2_direction(log) if protocol == "uniswap_v2_like" else decode_v3_direction(log)
        if direction == "buy":
            buy_count += 1
            for trader in actors[:1]:
                buyers.add(trader)
        elif direction == "sell":
            sell_count += 1
            for trader in actors[:1]:
                sellers.add(trader)
    trader_proxy_method = "event_sender_recipient" if protocol == "uniswap_v3_like" else "event_sender_to"
    if not trader_counts:
        tx_from_map = fetch_tx_from_map([log.get("transactionHash", "") for log in window_logs if log.get("transactionHash")])
        for log in window_logs:
            trader = tx_from_map.get(log.get("transactionHash", ""))
            if not trader:
                continue
            trader_counts[trader] += 1
            direction = decode_v2_direction(log) if protocol == "uniswap_v2_like" else decode_v3_direction(log)
            if direction == "buy":
                buyers.add(trader)
            elif direction == "sell":
                sellers.add(trader)
        if trader_counts:
            trader_proxy_method = "tx_from"
    if not trader_counts:
        return {
            "log_count": len(window_logs),
            "unique_traders": "",
            "buyer_count": len(buyers) or "",
            "seller_count": len(sellers) or "",
            "buy_count": buy_count or "",
            "sell_count": sell_count or "",
            "top1_trader_volume_share": "",
            "top5_trader_volume_share": "",
            "concentration_status": "missing",
            "data_quality_status": "missing",
            "failure_reason": "tx_sender_unavailable" if event_actor_seen else "actor_proxy_unavailable",
            "trader_proxy_method": "unavailable",
        }
    total = sum(trader_counts.values())
    ordered = trader_counts.most_common()
    top1 = round(ordered[0][1] * 100.0 / total, 2)
    top5 = round(sum(v for _, v in ordered[:5]) * 100.0 / total, 2)
    return {
        "log_count": len(window_logs),
        "unique_traders": len(trader_counts),
        "buyer_count": len(buyers) or "",
        "seller_count": len(sellers) or "",
        "buy_count": buy_count or "",
        "sell_count": sell_count or "",
        "top1_trader_volume_share": f"{top1:.2f}",
        "top5_trader_volume_share": f"{top5:.2f}",
        "concentration_status": concentration_status(top1, top5),
        "data_quality_status": "ok",
        "failure_reason": "",
        "trader_proxy_method": trader_proxy_method,
    }


def is_truthy(v):
    return v not in ("", None, "0", "0.0")


def fmt_num(v, default=""):
    return default if v in ("", None) else str(v)


def classify_v1c(base_row, merged_row):
    prior = base_row["reclassification"]
    if prior == "REJECT":
        return "REJECT", "prior_reject_freeze"

    missing = []
    if not is_truthy(base_row["exit_depth_usd"]):
        missing.append("exit_depth_usd")
    if not is_truthy(base_row["top10_holder_pct"]):
        missing.append("top10_holder_pct")
    if not is_truthy(base_row["tvl_change_1h"]):
        missing.append("tvl_change_1h")
    if not is_truthy(base_row["volume_change_1h"]):
        missing.append("volume_change_1h")
    if not is_truthy(base_row["price_move_5m"]) or not is_truthy(base_row["price_move_15m"]) or not is_truthy(base_row["price_move_30m"]):
        missing.append("price_move_5m/15m/30m")
    if not is_truthy(merged_row["buyers_24h"]):
        missing.append("buyers_24h")
    if not is_truthy(merged_row["sellers_24h"]):
        missing.append("sellers_24h")
    if not is_truthy(merged_row["buy_count_24h"]):
        missing.append("buy_count_24h")
    if not is_truthy(merged_row["sell_count_24h"]):
        missing.append("sell_count_24h")
    if not is_truthy(merged_row["unique_traders_24h"]):
        missing.append("unique_traders")
    if not is_truthy(merged_row["top1_trader_volume_share"]) or not is_truthy(merged_row["top5_trader_volume_share"]):
        missing.append("trader_concentration")

    if missing:
        return "WATCH_DATA_MISSING", ";".join(sorted(set(missing)))

    top10 = float(base_row["top10_holder_pct"])
    exit_depth = float(base_row["exit_depth_usd"])
    slippage10 = float(base_row["slippage_10usd"])
    top1 = float(merged_row["top1_trader_volume_share"])
    top5 = float(merged_row["top5_trader_volume_share"])
    price5 = abs(float(base_row["price_move_5m"]))
    price15 = abs(float(base_row["price_move_15m"]))
    price30 = abs(float(base_row["price_move_30m"]))
    volume_change_1h = float(base_row["volume_change_1h"])
    tvl_change_1h = float(base_row["tvl_change_1h"])

    reject_reasons = []
    watch_reasons = []
    if top10 > 40:
        reject_reasons.append("holder_concentration_extreme")
    elif top10 > 25:
        watch_reasons.append("holder_concentration_high")
    if exit_depth < 100 or slippage10 > 0.01:
        reject_reasons.append("exit_depth_too_thin")
    elif slippage10 > 0.005:
        watch_reasons.append("slippage_10usd_high")
    if top1 > 50 or top5 > 85:
        reject_reasons.append("trader_concentration_extreme")
    elif top1 > 30 or top5 > 65:
        watch_reasons.append("trader_concentration_high")
    if price5 > 2.0 or price15 > 3.0 or price30 > 4.0:
        reject_reasons.append("short_window_instability")
    elif price5 > 1.0 or price15 > 1.5 or price30 > 2.0:
        watch_reasons.append("short_window_volatility")
    if volume_change_1h < -0.50:
        watch_reasons.append("volume_collapse_1h")
    if tvl_change_1h < -0.20:
        watch_reasons.append("tvl_drop_1h")

    if reject_reasons:
        return "REJECT", ";".join(reject_reasons)
    if watch_reasons:
        return "WATCH_RISK_HIGH", ";".join(watch_reasons)

    if top10 <= 25 and exit_depth >= 500 and slippage10 <= 0.0025 and top1 <= 25 and top5 <= 55:
        return "MICRO_CANDIDATE_RESEARCH_ONLY", "data_ready_and_risk_within_research_limits"
    return "SHADOW_ONLY_DATA_READY", "data_ready_but_not_micro_quality"


def md_write(path, body):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--report-root", default="reports/tierc_shadow")
    ap.add_argument("--reclass-v1b", default="reports/tierc_shadow/20260529_204154/tierc_data_ready_reclassification_v1b.csv")
    ap.add_argument("--trader-v1b", default="reports/tierc_shadow/20260529_204154/tierc_trader_concentration_v1b.csv")
    ap.add_argument("--rediscovery-v2", default="reports/tierc_shadow/20260529_180220/tierc_rediscovery_v2_candidates.csv")
    ap.add_argument("--final-v1b", default="reports/tierc_shadow/20260529_204154/TIER_C_DATA_SOURCE_IMPLEMENTATION_V1B_FINAL_VERDICT.json")
    args = ap.parse_args()

    out_dir = Path(args.report_root) / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    reclass_rows = read_csv(args.reclass_v1b)
    trader_rows = {row["pool_id"]: row for row in read_csv(args.trader_v1b)}
    redisc_rows = {row["pool_id"]: row for row in read_csv(args.rediscovery_v2)}
    with open(args.final_v1b) as fh:
        verdict_v1b = json.load(fh)

    target_rows = []
    process_pools = []
    for row in reclass_rows:
        pid = row["pool_id"]
        current_verdict = row["reclassification"]
        tr = trader_rows.get(pid, {})
        missing = []
        if not is_truthy(tr.get("unique_traders_24h")):
            missing.append("unique_traders")
        if not is_truthy(tr.get("top1_trader_volume_share")):
            missing.append("trader_concentration")
        if not is_truthy(row.get("buyers_24h")):
            missing.append("buyers_24h")
        if not is_truthy(row.get("sellers_24h")):
            missing.append("sellers_24h")
        protocol_hint = "unsupported_pool_type" if len(pid) != 42 else "evm_pool_address"
        priority = 99 if current_verdict == "REJECT" else (1 if missing else 2)
        target_rows.append({
            "pool_id": pid,
            "token_pair": row["token_pair"],
            "current_verdict": current_verdict,
            "trader_concentration_available": "yes" if is_truthy(tr.get("top1_trader_volume_share")) else "no",
            "unique_traders_available": "yes" if is_truthy(tr.get("unique_traders_24h")) else "no",
            "missing_fields": ";".join(missing),
            "protocol": protocol_hint,
            "chain": "base",
            "priority_rank": priority,
        })
        if current_verdict != "REJECT":
            process_pools.append(pid)

    write_csv(out_dir / "tierc_onchain_logs_targets.csv", target_rows, [
        "pool_id", "token_pair", "current_verdict", "unique_traders_available",
        "trader_concentration_available", "missing_fields", "protocol", "chain", "priority_rank",
    ])

    target_md = ["# TIER_C_ONCHAIN_LOGS_TARGETS", "", f"- candidate_count: {len(target_rows)}", f"- process_count_non_reject: {len(process_pools)}", ""]
    for row in sorted(target_rows, key=lambda x: (int(x["priority_rank"]), x["pool_id"])):
        target_md.append(f"- `{row['pool_id']}` {row['current_verdict']} priority={row['priority_rank']} protocol={row['protocol']} missing={row['missing_fields'] or 'none'}")
    md_write(out_dir / "TIER_C_ONCHAIN_LOGS_TARGETS_CN.md", "\n".join(target_md) + "\n")

    head = rpc_block_number()
    start_24h = head - 24 * BLOCKS_PER_HOUR
    cutoffs = {"1h": head - 1 * BLOCKS_PER_HOUR, "6h": head - 6 * BLOCKS_PER_HOUR, "24h": start_24h}

    fallback_rows = []
    supported_count = 0
    success_pools = set()
    for row in target_rows:
        pid = row["pool_id"]
        token_pair = row["token_pair"]
        if row["current_verdict"] == "REJECT":
            for window in ("1h", "6h", "24h"):
                fallback_rows.append({
                    "pool_id": pid,
                    "token_pair": token_pair,
                    "protocol_detected": "",
                    "window": window,
                    "log_count": "",
                    "unique_traders": "",
                    "buyer_count": "",
                    "seller_count": "",
                    "buy_count": "",
                    "sell_count": "",
                    "top1_trader_volume_share": "",
                    "top5_trader_volume_share": "",
                    "concentration_status": "not_processed",
                    "data_quality_status": "not_processed",
                    "failure_reason": "reject_excluded",
                })
            continue

        if len(pid) != 42:
            for window in ("1h", "6h", "24h"):
                fallback_rows.append({
                    "pool_id": pid,
                    "token_pair": token_pair,
                    "protocol_detected": "unsupported_pool_type",
                    "window": window,
                    "log_count": "",
                    "unique_traders": "",
                    "buyer_count": "",
                    "seller_count": "",
                    "buy_count": "",
                    "sell_count": "",
                    "top1_trader_volume_share": "",
                    "top5_trader_volume_share": "",
                    "concentration_status": "missing",
                    "data_quality_status": "unsupported",
                    "failure_reason": "unsupported_pool_type",
                })
            continue

        supported_count += 1
        v2_logs, v2_err = fetch_logs_for_topic(pid, V2_SWAP_TOPIC, start_24h, head)
        v3_logs, v3_err = fetch_logs_for_topic(pid, V3_SWAP_TOPIC, start_24h, head)
        protocol, selected_logs = pick_protocol(v2_logs, v3_logs)
        if not protocol:
            for window in ("1h", "6h", "24h"):
                fallback_rows.append({
                    "pool_id": pid,
                    "token_pair": token_pair,
                    "protocol_detected": "",
                    "window": window,
                    "log_count": 0,
                    "unique_traders": "",
                    "buyer_count": "",
                    "seller_count": "",
                    "buy_count": "",
                    "sell_count": "",
                    "top1_trader_volume_share": "",
                    "top5_trader_volume_share": "",
                    "concentration_status": "missing",
                    "data_quality_status": "missing",
                    "failure_reason": v2_err or v3_err or "no_swap_logs",
                })
            continue

        for window in ("1h", "6h", "24h"):
            result = analyze_window(selected_logs, protocol, cutoffs[window])
            if result["data_quality_status"] == "ok":
                success_pools.add(pid)
            fallback_rows.append({
                "pool_id": pid,
                "token_pair": token_pair,
                "protocol_detected": protocol,
                "window": window,
                **result,
            })

    write_csv(out_dir / "tierc_onchain_logs_fallback.csv", fallback_rows, [
        "pool_id", "token_pair", "protocol_detected", "window", "log_count",
        "unique_traders", "buyer_count", "seller_count", "buy_count", "sell_count",
        "top1_trader_volume_share", "top5_trader_volume_share", "concentration_status",
        "data_quality_status", "failure_reason",
    ])

    md = [
        "# TIER_C_ONCHAIN_LOGS_FALLBACK",
        "",
        f"- rpc_url: `{BASE_RPC_URL}`",
        f"- supported_count: {supported_count}",
        f"- success_pool_count: {len(success_pools)}",
        "- note: trader concentration uses on-chain tx sender as read-only trader proxy; volume share is tx-share proxy within each pool/window.",
        "",
    ]
    for pid in process_pools:
        rows = [r for r in fallback_rows if r["pool_id"] == pid]
        md.append(f"## {pid}")
        for r in rows:
            md.append(f"- {r['window']}: protocol={r['protocol_detected'] or 'n/a'} logs={r['log_count']} unique={r['unique_traders'] or 'n/a'} top1={r['top1_trader_volume_share'] or 'n/a'} top5={r['top5_trader_volume_share'] or 'n/a'} dq={r['data_quality_status']} failure={r['failure_reason'] or 'none'}")
        md.append("")
    md_write(out_dir / "TIER_C_ONCHAIN_LOGS_FALLBACK_CN.md", "\n".join(md))

    merged_rows = []
    fallback_24h = {r["pool_id"]: r for r in fallback_rows if r["window"] == "24h"}
    fallback_6h = {r["pool_id"]: r for r in fallback_rows if r["window"] == "6h"}
    fallback_1h = {r["pool_id"]: r for r in fallback_rows if r["window"] == "1h"}
    for row in reclass_rows:
        pid = row["pool_id"]
        proxy = trader_rows.get(pid, {})
        on24 = fallback_24h.get(pid, {})
        on6 = fallback_6h.get(pid, {})
        on1 = fallback_1h.get(pid, {})
        use_onchain = on24.get("data_quality_status") == "ok"
        use_proxy = not use_onchain and is_truthy(proxy.get("unique_traders_24h")) and is_truthy(proxy.get("top1_trader_volume_share"))
        source = "onchain_logs" if use_onchain else ("proxy" if use_proxy else "missing")
        confidence = "high" if use_onchain else ("medium" if use_proxy else "none")
        merged_rows.append({
            "pool_id": pid,
            "token_pair": row["token_pair"],
            "unique_traders_1h": on1.get("unique_traders") if use_onchain else proxy.get("unique_traders_1h", ""),
            "unique_traders_6h": on6.get("unique_traders") if use_onchain else proxy.get("unique_traders_6h", ""),
            "unique_traders_24h": on24.get("unique_traders") if use_onchain else proxy.get("unique_traders_24h", ""),
            "top1_trader_volume_share": on24.get("top1_trader_volume_share") if use_onchain else proxy.get("top1_trader_volume_share", ""),
            "top5_trader_volume_share": on24.get("top5_trader_volume_share") if use_onchain else proxy.get("top5_trader_volume_share", ""),
            "buy_count_24h": on24.get("buy_count") if use_onchain else proxy.get("buy_count_24h", ""),
            "sell_count_24h": on24.get("sell_count") if use_onchain else proxy.get("sell_count_24h", ""),
            "buyers_24h": on24.get("buyer_count") if use_onchain else proxy.get("buyers_24h", ""),
            "sellers_24h": on24.get("seller_count") if use_onchain else proxy.get("sellers_24h", ""),
            "concentration_status": on24.get("concentration_status") if use_onchain else proxy.get("concentration_status", "missing"),
            "source": source,
            "confidence": confidence,
            "failure_reason": "" if source != "missing" else (on24.get("failure_reason") or proxy.get("failure_reason", "missing")),
        })

    write_csv(out_dir / "tierc_trader_concentration_merged.csv", merged_rows, [
        "pool_id", "token_pair", "unique_traders_1h", "unique_traders_6h", "unique_traders_24h",
        "top1_trader_volume_share", "top5_trader_volume_share", "buy_count_24h", "sell_count_24h",
        "buyers_24h", "sellers_24h", "concentration_status", "source", "confidence", "failure_reason",
    ])
    merged_md = ["# TIER_C_TRADER_CONCENTRATION_MERGED", ""]
    for row in merged_rows:
        merged_md.append(f"- `{row['pool_id']}` source={row['source']} confidence={row['confidence']} unique24={row['unique_traders_24h'] or 'n/a'} top1={row['top1_trader_volume_share'] or 'n/a'} top5={row['top5_trader_volume_share'] or 'n/a'} failure={row['failure_reason'] or 'none'}")
    md_write(out_dir / "TIER_C_TRADER_CONCENTRATION_MERGED_CN.md", "\n".join(merged_md) + "\n")

    merged_map = {r["pool_id"]: r for r in merged_rows}
    reclass_v1c_rows = []
    for row in reclass_rows:
        merged = merged_map[row["pool_id"]]
        cls, reason = classify_v1c(row, merged)
        out = dict(row)
        out.update({
            "merged_source": merged["source"],
            "merged_confidence": merged["confidence"],
            "buyers_24h": merged["buyers_24h"],
            "sellers_24h": merged["sellers_24h"],
            "buy_count_24h": merged["buy_count_24h"],
            "sell_count_24h": merged["sell_count_24h"],
            "unique_traders_24h": merged["unique_traders_24h"],
            "top1_trader_volume_share": merged["top1_trader_volume_share"],
            "top5_trader_volume_share": merged["top5_trader_volume_share"],
            "reclassification_v1c": cls,
            "reclass_reason_v1c": reason,
        })
        reclass_v1c_rows.append(out)

    write_csv(out_dir / "tierc_data_ready_reclassification_v1c.csv", reclass_v1c_rows, [
        "pool_id", "token_pair", "source_verdict", "merged_source", "merged_confidence", "buyers_24h",
        "sellers_24h", "buy_count_24h", "sell_count_24h", "unique_traders_24h",
        "top1_trader_volume_share", "top5_trader_volume_share", "top10_holder_pct", "exit_depth_usd",
        "slippage_10usd", "tvl_change_1h", "volume_change_1h", "price_move_5m", "price_move_15m",
        "price_move_30m", "reclassification_v1c", "reclass_reason_v1c",
    ])
    reclass_md = ["# TIER_C_DATA_READY_RECLASSIFICATION_V1C", ""]
    for row in reclass_v1c_rows:
        reclass_md.append(f"- `{row['pool_id']}` => {row['reclassification_v1c']} source={row['merged_source']} reason={row['reclass_reason_v1c']}")
    md_write(out_dir / "TIER_C_DATA_READY_RECLASSIFICATION_V1C_CN.md", "\n".join(reclass_md) + "\n")

    counts = Counter(r["reclassification_v1c"] for r in reclass_v1c_rows)
    missing_counter = Counter()
    for row in reclass_v1c_rows:
        for item in row["reclass_reason_v1c"].split(";"):
            if item and item not in {"prior_reject_freeze", "holder_concentration_extreme", "exit_depth_too_thin", "trader_concentration_extreme", "short_window_instability", "holder_concentration_high", "slippage_10usd_high", "trader_concentration_high", "short_window_volatility", "volume_collapse_1h", "tvl_drop_1h", "data_ready_and_risk_within_research_limits", "data_ready_but_not_micro_quality"}:
                missing_counter[item] += 1
    final_verdict = {
        "status": "WARN" if counts["MICRO_CANDIDATE_RESEARCH_ONLY"] == 0 else "PASS",
        "stage": "TIER_C_ONCHAIN_LOGS_FALLBACK_V1",
        "candidate_count": len(reclass_v1c_rows),
        "onchain_logs_supported_count": supported_count,
        "onchain_logs_success_count": len(success_pools),
        "trader_concentration_coverage_before": verdict_v1b["trader_concentration_coverage"],
        "trader_concentration_coverage_after": sum(1 for r in merged_rows if r["source"] != "missing"),
        "data_ready_count": counts["MICRO_CANDIDATE_RESEARCH_ONLY"] + counts["SHADOW_ONLY_DATA_READY"],
        "micro_candidate_research_only_count": counts["MICRO_CANDIDATE_RESEARCH_ONLY"],
        "shadow_only_data_ready_count": counts["SHADOW_ONLY_DATA_READY"],
        "watch_count": counts["WATCH_DATA_MISSING"] + counts["WATCH_RISK_HIGH"],
        "reject_count": counts["REJECT"],
        "top_missing_fields": [k for k, _ in missing_counter.most_common(8)],
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": "TIER_C_CONTINUE_WATCH_ONLY" if counts["SHADOW_ONLY_DATA_READY"] > 0 else "TIER_C_DATA_SOURCE_IMPLEMENTATION_REPEAT",
    }
    with open(out_dir / "TIER_C_ONCHAIN_LOGS_FALLBACK_FINAL_VERDICT.json", "w") as fh:
        json.dump(final_verdict, fh, indent=2)

    onepage = [
        "# TIER_C_ONCHAIN_LOGS_FALLBACK_ONEPAGE",
        "",
        f"- status: {final_verdict['status']}",
        f"- candidate_count: {final_verdict['candidate_count']}",
        f"- onchain_logs_supported_count: {final_verdict['onchain_logs_supported_count']}",
        f"- onchain_logs_success_count: {final_verdict['onchain_logs_success_count']}",
        f"- trader_concentration_coverage_before: {final_verdict['trader_concentration_coverage_before']}",
        f"- trader_concentration_coverage_after: {final_verdict['trader_concentration_coverage_after']}",
        f"- data_ready_count: {final_verdict['data_ready_count']}",
        f"- micro_candidate_research_only_count: {final_verdict['micro_candidate_research_only_count']}",
        f"- shadow_only_data_ready_count: {final_verdict['shadow_only_data_ready_count']}",
        f"- watch_count: {final_verdict['watch_count']}",
        f"- reject_count: {final_verdict['reject_count']}",
        f"- top_missing_fields: {', '.join(final_verdict['top_missing_fields']) or 'none'}",
        "- edge_proven: no",
        "- tiny_canary_candidate: no",
        "- tiny_canary_allowed: no",
        f"- recommended_next_stage: {final_verdict['recommended_next_stage']}",
    ]
    md_write(out_dir / "TIER_C_ONCHAIN_LOGS_FALLBACK_ONEPAGE_CN.md", "\n".join(onepage) + "\n")

    artifact_index = [
        "# ARTIFACT_INDEX",
        "",
        f"- report_dir: {out_dir}",
        f"- final_verdict: {out_dir / 'TIER_C_ONCHAIN_LOGS_FALLBACK_FINAL_VERDICT.json'}",
        f"- targets: {out_dir / 'tierc_onchain_logs_targets.csv'}",
        f"- fallback_csv: {out_dir / 'tierc_onchain_logs_fallback.csv'}",
        f"- merged_csv: {out_dir / 'tierc_trader_concentration_merged.csv'}",
        f"- reclassification_csv: {out_dir / 'tierc_data_ready_reclassification_v1c.csv'}",
        "- touched_trading_path: no",
        "- touched_wallet_tx_bridge_live_paper: no",
        "- tiny_canary_allowed: no",
    ]
    md_write(out_dir / "ARTIFACT_INDEX.md", "\n".join(artifact_index) + "\n")


if __name__ == "__main__":
    main()
