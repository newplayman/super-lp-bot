#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
from eth_abi import decode as abi_decode


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", str(Path(__file__).resolve().parents[1]))).resolve()
WORKSPACE = "/opt/lpbot/lp-bot-v3-origin-check"
SWAP_TOPIC_V3 = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
READONLY_RPC_FALLBACKS = [
    "https://bsc-dataseed.binance.org",
    "https://bsc-dataseed1.defibit.io",
    "https://bsc-rpc.publicnode.com",
]
RPC_ENV_KEYS = [
    "BSC_RPC_PRIMARY",
    "LPBOT_BSC_RPC_URL",
    "BSC_RPC_URL",
    "LPBOT_BSC_RPC_FALLBACK",
    "BASE_RPC_PRIMARY",
    "BASE_RPC_URL",
]
BLOCK_SECONDS_HINT = 3.0
WINDOW_SECONDS = {
    "24h": 24 * 3600,
    "72h": 72 * 3600,
    "7d": 7 * 24 * 3600,
    "14d": 14 * 24 * 3600,
    "30d": 30 * 24 * 3600,
}
FEE_HORIZONS = ["15m", "30m", "1h", "2h", "6h", "24h"]
HORIZON_HOURS = {"15m": 0.25, "30m": 0.5, "1h": 1.0, "2h": 2.0, "6h": 6.0, "24h": 24.0}
ALLOWED_NEXT = {
    "LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1",
    "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_FIX_REPEAT",
    "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}
STABLE_SYMBOLS = {"USDT", "USDC", "BUSD", "DAI", "FDUSD"}

OVERNIGHT_REALDATA_DIR = REPO_ROOT / "reports" / "lp_bsc_overnight_realdata_pipeline" / "20260601_180812"
QUOTER_AMOUNT_FIX_DIR = REPO_ROOT / "reports" / "lp_bsc_quoter_staticcall_amount_fix" / "20260601_173837"

HTTP = requests.Session()
HTTP.headers.update({"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
HTTP.trust_env = False


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        return f"{value:.10f}".rstrip("0").rstrip(".")
    return str(value)


def as_float(value: Any) -> float | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def as_int(value: Any) -> int | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def redact_secretish(text: str) -> str:
    text = re.sub(r"postgres(?:ql)?://[^\s'\\\"]+", "<redacted-dsn>", text)
    text = re.sub(r"(POSTGRES_DSN|DATABASE_URL|SHADOW_POSTGRES_DSN)=\S+", r"\1=<redacted>", text)
    text = re.sub(r"(BSC_RPC_PRIMARY|LPBOT_BSC_RPC_URL|BSC_RPC_URL|LPBOT_BSC_RPC_FALLBACK)=\S+", r"\1=<redacted>", text)
    return text


def load_helper(name: str, rel: str) -> Any:
    return load_module(name, REPO_ROOT / "scripts" / rel)


RPC_HELPER = load_helper("lp_bsc_pancakeswap_v3_precise_quote_v2_readonly", "lp_bsc_pancakeswap_v3_precise_quote_v2_readonly.py")
TICK_HELPER = load_helper("lp_v3_tick_liquidity_pipeline_v1_readonly", "lp_v3_tick_liquidity_pipeline_v1_readonly.py")


def read_only_rpc() -> tuple[str, dict[str, Any]]:
    env_key = None
    rpc_url = ""
    for key in RPC_ENV_KEYS:
        if os.environ.get(key):
            env_key = key
            rpc_url = os.environ.get(key, "")
            break
    if not rpc_url:
        rpc_url = READONLY_RPC_FALLBACKS[0]
        env_key = "public_fallback"
    ready = {
        "rpc_env_key": env_key,
        "rpc_present": bool(rpc_url),
        "rpc_read_only_test_pass": False,
        "chain_id": "",
        "latest_block": "",
        "eth_getLogs_smoke_pass": False,
        "eth_getCode_smoke_pass": False,
        "rpc_error": "",
    }
    try:
        chain_hex = rpc_call(rpc_url, "eth_chainId", [], timeout=20)
        latest_hex = rpc_call(rpc_url, "eth_blockNumber", [], timeout=20)
        ready["chain_id"] = str(int(chain_hex, 16))
        ready["latest_block"] = str(int(latest_hex, 16))
        ready["rpc_read_only_test_pass"] = ready["chain_id"] == "56"
        ready["eth_getLogs_smoke_pass"] = isinstance(
            rpc_call(
                rpc_url,
                "eth_getLogs",
                [{
                    "fromBlock": latest_hex,
                    "toBlock": latest_hex,
                    "topics": [SWAP_TOPIC_V3],
                }],
                timeout=20,
            ),
            list,
        )
    except Exception as exc:
        ready["rpc_error"] = str(exc)
    return rpc_url, ready


def rpc_call(rpc_url: str, method: str, params: list[Any], timeout: int = 20) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    endpoints = [rpc_url] + [u for u in READONLY_RPC_FALLBACKS if u != rpc_url]
    last_error: Exception | None = None
    for endpoint in endpoints:
        try:
            resp = HTTP.post(endpoint, json=payload, timeout=(5, timeout))
            resp.raise_for_status()
            out = resp.json()
            if "error" in out:
                raise RuntimeError(str(out["error"]))
            return out.get("result")
        except Exception as exc:
            last_error = exc
    raise RuntimeError(str(last_error) if last_error else f"rpc call failed: {method}")


def latest_report_dir(base: Path) -> Path | None:
    if not base.exists():
        return None
    candidates = sorted([p for p in base.iterdir() if p.is_dir()])
    return candidates[-1] if candidates else None


def latest_overnight_realdata_dir() -> Path:
    latest = latest_report_dir(REPO_ROOT / "reports" / "lp_bsc_overnight_realdata_pipeline")
    if latest:
        return latest
    return OVERNIGHT_REALDATA_DIR


def input_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    overnight = latest_overnight_realdata_dir()
    inputs = [
        overnight / "FINAL_VERDICT.json",
        overnight / "BSC_REALDATA_ECONOMICS_PREVIEW_CN.md",
        overnight / "BSC_REALDATA_ECONOMICS_PREVIEW_CN.csv",
        overnight / "BSC_FEE_VELOCITY_RESULTS_CN.md",
        overnight / "BSC_FEE_VELOCITY_RESULTS_CN.csv",
        overnight / "BSC_SELECTED_POOL_SET_CN.md",
        overnight / "BSC_SELECTED_POOL_SET_CN.csv",
        QUOTER_AMOUNT_FIX_DIR / "FINAL_VERDICT.json",
        QUOTER_AMOUNT_FIX_DIR / "bsc_precise_quote_staticcall_v3_results.csv",
    ]
    rows = [{"path": str(p.relative_to(REPO_ROOT)), "exists": p.exists()} for p in inputs]
    overnight_verdict = load_json(overnight / "FINAL_VERDICT.json")
    quoter_verdict = load_json(QUOTER_AMOUNT_FIX_DIR / "FINAL_VERDICT.json")
    summary = {
        "missing_input_list": [r["path"] for r in rows if not r["exists"]],
        "quoter_staticcall_ready": quoter_verdict.get("quoter_v2_staticcall_fixed") is True,
        "tick_ready_pool_count": overnight_verdict.get("tick_ready_pool_count"),
        "cost_ready_pool_count": overnight_verdict.get("cost_ready_pool_count"),
        "fee_ready_pool_count": overnight_verdict.get("fee_ready_pool_count"),
        "recommended_next_stage": overnight_verdict.get("recommended_next_stage"),
        "selected_pool_count": overnight_verdict.get("selected_pool_count"),
        "overnight_realdata_stage": overnight_verdict.get("stage"),
        "suitable_for_fee_velocity_backfill": (
            quoter_verdict.get("quoter_v2_staticcall_fixed") is True
            and overnight_verdict.get("tick_ready_pool_count") == 8
            and overnight_verdict.get("cost_ready_pool_count") == 8
            and overnight_verdict.get("fee_ready_pool_count") == 0
            and overnight_verdict.get("recommended_next_stage") == "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_FIX_REPEAT"
        ),
    }
    return rows, summary


def read_selected_pools() -> list[dict[str, str]]:
    path = latest_overnight_realdata_dir() / "BSC_SELECTED_POOL_SET_CN.csv"
    rows = load_csv(path)
    if rows:
        return rows
    rows = load_csv(OVERNIGHT_REALDATA_DIR / "BSC_SELECTED_POOL_SET_CN.csv")
    return rows


def load_quote_anchors() -> tuple[dict[str, Decimal], dict[str, int]]:
    rows = load_csv(QUOTER_AMOUNT_FIX_DIR / "bsc_precise_quote_staticcall_v3_results.csv")
    prices: dict[str, Decimal] = {}
    decimals: dict[str, int] = {}
    for r in rows:
        if r.get("quote_success") != "yes":
            continue
        token_in = (r.get("token_in") or "").lower()
        token_out = (r.get("token_out") or "").lower()
        symbol_in = (r.get("token_in_symbol") or "").upper()
        symbol_out = (r.get("token_out_symbol") or "").upper()
        anchor = as_float(r.get("token_usd_anchor_price"))
        dec = as_int(r.get("token_in_decimals"))
        if token_in and anchor is not None:
            prices.setdefault(token_in, Decimal(str(anchor)))
        if token_in and dec is not None:
            decimals.setdefault(token_in, dec)
        if token_out and symbol_out in STABLE_SYMBOLS:
            prices.setdefault(token_out, Decimal("1"))
        if token_out and symbol_out in STABLE_SYMBOLS:
            decimals.setdefault(token_out, as_int(r.get("token_in_decimals")) or 18)
        if token_in and symbol_in in STABLE_SYMBOLS:
            prices.setdefault(token_in, Decimal("1"))
    return prices, decimals


def build_pool_contexts(rpc_url: str, selected_rows: list[dict[str, str]], prices: dict[str, Decimal], decimals: dict[str, int]) -> list[dict[str, Any]]:
    contexts = []
    for row in selected_rows:
        token0 = (row.get("token0") or "").lower()
        token1 = (row.get("token1") or "").lower()
        token0_symbol = row.get("token0_symbol") or ""
        token1_symbol = row.get("token1_symbol") or ""
        try:
            token0_decimals = decimals.get(token0) or TICK_HELPER.call_simple_uint(rpc_url, token0, "decimals()")
        except Exception:
            token0_decimals = 18
        try:
            token1_decimals = decimals.get(token1) or TICK_HELPER.call_simple_uint(rpc_url, token1, "decimals()")
        except Exception:
            token1_decimals = 18
        if token0 not in prices and token0_symbol.upper() in STABLE_SYMBOLS:
            prices[token0] = Decimal("1")
        if token1 not in prices and token1_symbol.upper() in STABLE_SYMBOLS:
            prices[token1] = Decimal("1")
        contexts.append(
            {
                "pool_id": row.get("pool_address"),
                "token_pair": row.get("token_pair"),
                "token0": token0,
                "token1": token1,
                "token0_symbol": token0_symbol,
                "token1_symbol": token1_symbol,
                "token0_decimals": int(token0_decimals or 18),
                "token1_decimals": int(token1_decimals or 18),
                "fee_tier_raw": as_int(row.get("fee_tier_raw")) or 0,
                "fee_rate_fraction": (as_int(row.get("fee_tier_raw")) or 0) / 10000.0,
                "quote_staticcall_ready": row.get("quote_staticcall_ready", "yes"),
                "selected_for_fee": row.get("selected_for_fee", "yes"),
                "selected_for_economics": row.get("selected_for_economics", "yes"),
            }
        )
    return contexts


def get_code_ok(rpc_url: str, address: str) -> bool:
    try:
        code = rpc_call(rpc_url, "eth_getCode", [address, "latest"], timeout=20)
        return bool(code and code != "0x")
    except Exception:
        return False


def decode_swap_v3(log: dict[str, Any]) -> dict[str, Any]:
    payload = bytes.fromhex(log["data"][2:])
    amount0, amount1, sqrt_price_x96, liquidity, tick = abi_decode(["int256", "int256", "uint160", "uint128", "int24"], payload)
    sender = "0x" + log["topics"][1][-40:] if len(log.get("topics") or []) > 1 else ""
    recipient = "0x" + log["topics"][2][-40:] if len(log.get("topics") or []) > 2 else ""
    return {
        "block_number": int(log["blockNumber"], 16),
        "tx_hash": log["transactionHash"],
        "log_index": int(log["logIndex"], 16),
        "sender": sender.lower(),
        "recipient": recipient.lower(),
        "amount0": int(amount0),
        "amount1": int(amount1),
        "sqrtPriceX96": int(sqrt_price_x96),
        "liquidity": int(liquidity),
        "tick": int(tick),
    }


def fetch_logs_bounded(
    rpc_url: str,
    pool_id: str,
    from_block: int,
    to_block: int,
    max_blocks_per_query: int,
    max_logs_per_pool: int,
    rpc_timeout: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    query_count = 0
    partial = False
    root_cause = ""
    start = from_block
    min_chunk = max(128, min(max_blocks_per_query, 500))
    chunk = max_blocks_per_query
    while start <= to_block and len(logs) < max_logs_per_pool:
        end = min(start + chunk - 1, to_block)
        query = {
            "fromBlock": hex(max(start, 0)),
            "toBlock": hex(max(end, 0)),
            "address": pool_id,
            "topics": [SWAP_TOPIC_V3],
        }
        query_count += 1
        try:
            chunk_logs = rpc_call(rpc_url, "eth_getLogs", [query], timeout=rpc_timeout)
            if isinstance(chunk_logs, dict) and "error" in chunk_logs:
                raise RuntimeError(str(chunk_logs["error"]))
            if not isinstance(chunk_logs, list):
                raise RuntimeError(f"unexpected_eth_getLogs_result:{type(chunk_logs).__name__}")
            if len(logs) + len(chunk_logs) > max_logs_per_pool:
                chunk_logs = chunk_logs[: max(0, max_logs_per_pool - len(logs))]
                partial = True
                root_cause = root_cause or "max_logs_cap_reached"
            logs.extend(chunk_logs)
            start = end + 1
            chunk = max_blocks_per_query
        except Exception as exc:
            partial = True
            root_cause = root_cause or f"rpc_error:{type(exc).__name__}"
            if chunk > min_chunk:
                chunk = max(min_chunk, chunk // 2)
                continue
            start = end + 1
            chunk = max_blocks_per_query
    if start <= to_block:
        partial = True
        root_cause = root_cause or "window_incomplete"
    return logs, {"partial": partial, "root_cause": root_cause, "query_count": query_count}


def estimate_block_window(latest_block: int, window_seconds: int) -> int:
    blocks = int(window_seconds / BLOCK_SECONDS_HINT)
    return max(1, blocks)


def windowed_fee_row(
    pool: dict[str, Any],
    window_label: str,
    latest_block: int,
    rpc_url: str,
    max_blocks_per_query: int,
    max_logs_per_pool: int,
    rpc_timeout: int,
    prices: dict[str, Decimal],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from_block = max(latest_block - estimate_block_window(latest_block, WINDOW_SECONDS[window_label]), 0)
    logs, meta = fetch_logs_bounded(
        rpc_url=rpc_url,
        pool_id=pool["pool_id"],
        from_block=from_block,
        to_block=latest_block,
        max_blocks_per_query=max_blocks_per_query,
        max_logs_per_pool=max_logs_per_pool,
        rpc_timeout=rpc_timeout,
    )
    decoded_rows: list[dict[str, Any]] = []
    volume_usd = Decimal("0")
    sender_set: set[str] = set()
    recipient_set: set[str] = set()
    buy_count = 0
    sell_count = 0
    for log in logs:
        try:
            dec = decode_swap_v3(log)
        except Exception:
            continue
        sender_set.add(dec["sender"])
        recipient_set.add(dec["recipient"])
        if dec["amount0"] < 0 and dec["amount1"] > 0:
            buy_count += 1
        elif dec["amount0"] > 0 and dec["amount1"] < 0:
            sell_count += 1
        price0 = prices.get(pool["token0"]) or Decimal("1")
        price1 = prices.get(pool["token1"]) or Decimal("1")
        amt0 = abs(Decimal(dec["amount0"])) / Decimal(10 ** pool["token0_decimals"])
        amt1 = abs(Decimal(dec["amount1"])) / Decimal(10 ** pool["token1_decimals"])
        usd0 = amt0 * price0
        usd1 = amt1 * price1
        volume_usd += max(usd0, usd1)
        decoded_rows.append(
            {
                "run_id": "",
                "pool_id": pool["pool_id"],
                "token_pair": pool["token_pair"],
                "window": window_label,
                "block_number": dec["block_number"],
                "tx_hash": dec["tx_hash"],
                "log_index": dec["log_index"],
                "sender": dec["sender"],
                "recipient": dec["recipient"],
                "amount0": dec["amount0"],
                "amount1": dec["amount1"],
                "sqrtPriceX96": dec["sqrtPriceX96"],
                "liquidity": dec["liquidity"],
                "tick": dec["tick"],
                "amount0_usd_proxy": float(usd0),
                "amount1_usd_proxy": float(usd1),
                "volume_usd_proxy": float(max(usd0, usd1)),
                "fee_tier_raw": pool["fee_tier_raw"],
                "fee_rate_fraction": pool["fee_rate_fraction"],
                "created_at": int(time.time()),
            }
        )
    pool_fee_usd_proxy = float(volume_usd * Decimal(str(pool["fee_rate_fraction"])))
    hours = WINDOW_SECONDS[window_label] / 3600.0
    per_hour_fee = pool_fee_usd_proxy / hours if hours > 0 else 0.0
    row = {
        "run_id": "",
        "pool_id": pool["pool_id"],
        "token_pair": pool["token_pair"],
        "chain": "BSC",
        "protocol": "PancakeSwap V3",
        "pool_type": "CLMM",
        "fee_tier_raw": pool["fee_tier_raw"],
        "window": window_label,
        "from_block": from_block,
        "to_block": latest_block,
        "block_window_hint": estimate_block_window(latest_block, WINDOW_SECONDS[window_label]),
        "query_count": meta["query_count"],
        "log_count": len(logs),
        "decoded_log_count": len(decoded_rows),
        "unique_traders": len(sender_set | recipient_set),
        "buyer_count": len(sender_set),
        "seller_count": len(recipient_set),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "volume_usd_proxy": float(volume_usd),
        "pool_fee_usd_proxy": pool_fee_usd_proxy,
        "fee_velocity_15m": per_hour_fee * 0.25,
        "fee_velocity_30m": per_hour_fee * 0.5,
        "fee_velocity_1h": per_hour_fee * 1.0,
        "fee_velocity_2h": per_hour_fee * 2.0,
        "fee_velocity_6h": per_hour_fee * 6.0,
        "fee_velocity_24h": per_hour_fee * 24.0,
        "fee_source": "onchain_swap_logs",
        "partial": meta["partial"],
        "root_cause": meta["root_cause"],
        "confidence": "high" if not meta["partial"] and len(logs) > 0 else ("medium" if len(logs) > 0 else "low"),
        "invalid_reason": "" if len(logs) > 0 else (meta["root_cause"] or "no_swap_logs"),
        "created_at": int(time.time()),
    }
    return row, decoded_rows


def economics_preview_rows(
    selected_rows: list[dict[str, str]],
    pool_contexts: list[dict[str, Any]],
    fee_rows: list[dict[str, Any]],
    cost_rows: list[dict[str, str]],
    tick_rows: list[dict[str, str]],
    quote_rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cost_by_pool = {r["pool_id"]: r for r in cost_rows if r.get("scenario") == "realistic_mid"}
    tick_by_pool = {r["pool_id"]: r for r in tick_rows}
    fee_by_pool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in fee_rows:
        fee_by_pool[r["pool_id"]].append(r)
    best_fee_window: dict[str, dict[str, Any]] = {}
    for pool_id, rows in fee_by_pool.items():
        complete = [r for r in rows if not r["partial"] and r["log_count"] > 0]
        candidate_rows = complete or [r for r in rows if r["log_count"] > 0] or rows
        if candidate_rows:
            best_fee_window[pool_id] = sorted(candidate_rows, key=lambda r: WINDOW_SECONDS[r["window"]])[-1]
    out = []
    best = None
    for pool in pool_contexts:
        fee_row = best_fee_window.get(pool["pool_id"])
        if not fee_row:
            continue
        cost_row = cost_by_pool.get(pool["pool_id"], {})
        tick_row = tick_by_pool.get(pool["pool_id"], {})
        fixed_cost = as_float(cost_row.get("total_fixed_cost_usd")) or 0.0
        fee_proxy_base = as_float(fee_row.get("pool_fee_usd_proxy")) or 0.0
        base_hours = WINDOW_SECONDS[fee_row["window"]] / 3600.0
        for hold_window in FEE_HORIZONS:
            hold_hours = HORIZON_HOURS[hold_window]
            fee_proxy = fee_proxy_base * (hold_hours / base_hours) if base_hours > 0 else 0.0
            il_proxy = 0.0 if hold_window in {"15m", "30m"} else max(0.0, (as_float(cost_row.get("quote_gas_usd")) or 0.0) * 0.02)
            for scenario, mult in [("zero_il_lvr", 1.0), ("optimistic", 1.15), ("realistic", 1.0), ("conservative", 0.85)]:
                net = fee_proxy * mult - fixed_cost - il_proxy
                row = {
                    "pool_id": pool["pool_id"],
                    "token_pair": pool["token_pair"],
                    "fee_tier_raw": pool["fee_tier_raw"],
                    "notional_usd": 20,
                    "hold_window": hold_window,
                    "scenario": scenario,
                    "fee_proxy_usd": fee_proxy,
                    "fixed_cost_usd": fixed_cost,
                    "il_lvr_proxy_usd": il_proxy,
                    "net_ev_proxy_usd": net,
                    "net_ev_proxy_pct": (net / 20.0 * 100.0),
                    "capacity_ok": "yes" if as_float(tick_row.get("liquidity")) is not None else "no",
                    "data_sufficient": "yes" if fee_row and not fee_row["partial"] else "no",
                    "confidence": "high" if fee_row and not fee_row["partial"] else "medium",
                    "fee_window_used": fee_row["window"],
                }
                out.append(row)
                if best is None or (scenario == "realistic" and row["net_ev_proxy_usd"] > best["net_ev_proxy_usd"]):
                    best = row
    agg = {
        "row_count": len(out),
        "positive_proxy_count_total": sum(1 for r in out if r["net_ev_proxy_usd"] > 0),
        "positive_proxy_count_realistic": sum(1 for r in out if r["scenario"] == "realistic" and r["net_ev_proxy_usd"] > 0),
        "best_pool": best["pool_id"] if best else "",
        "best_pair": best["token_pair"] if best else "",
        "best_fee_tier": best["fee_tier_raw"] if best else "",
        "best_notional": best["notional_usd"] if best else None,
        "best_hold_window": best["hold_window"] if best else "",
        "best_net_ev_proxy_usd": best["net_ev_proxy_usd"] if best else None,
        "best_fee_window_used": best["fee_window_used"] if best else "",
    }
    return out, agg


def candidate_review_rows(pool_contexts: list[dict[str, Any]], fee_rows: list[dict[str, Any]], econ_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fee_by_pool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in fee_rows:
        fee_by_pool[r["pool_id"]].append(r)
    econ_by_pool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in econ_rows:
        econ_by_pool[r["pool_id"]].append(r)
    out = []
    for pool in pool_contexts:
        fees = fee_by_pool.get(pool["pool_id"], [])
        best_econ = max((r for r in econ_by_pool.get(pool["pool_id"], []) if r["scenario"] == "realistic"), key=lambda r: r["net_ev_proxy_usd"], default=None)
        best_fee = max((r for r in fees if r["log_count"] > 0), key=lambda r: r["pool_fee_usd_proxy"], default=None)
        status = "REJECT"
        reason = "no_swap_logs"
        if best_fee and not best_fee["partial"] and best_fee["log_count"] > 0:
            status = "WATCH"
            reason = "read_only_fee_backfill"
            if best_econ and best_econ["net_ev_proxy_usd"] > 0:
                status = "WATCH"
                reason = "positive_proxy_only"
        out.append(
            {
                "pool_id": pool["pool_id"],
                "token_pair": pool["token_pair"],
                "fee_tier_raw": pool["fee_tier_raw"],
                "best_fee_window": best_fee["window"] if best_fee else "",
                "best_net_ev_proxy_usd": best_econ["net_ev_proxy_usd"] if best_econ else "",
                "best_net_ev_proxy_pct": best_econ["net_ev_proxy_pct"] if best_econ else "",
                "candidate_status": status,
                "reason": reason,
            }
        )
    return out


def blocker_diagnosis(fee_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_pool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in fee_rows:
        by_pool[row["pool_id"]].append(row)
    rows = []
    for pool_id, items in by_pool.items():
        nonzero = [r for r in items if r["log_count"] > 0]
        complete = [r for r in items if not r["partial"] and r["log_count"] > 0]
        root_causes = Counter((r["root_cause"] or "none") for r in items)
        rows.append(
            {
                "pool_id": pool_id,
                "window_count": len(items),
                "nonzero_window_count": len(nonzero),
                "complete_window_count": len(complete),
                "most_common_root_cause": root_causes.most_common(1)[0][0] if root_causes else "",
                "root_cause_counts": json.dumps(dict(root_causes), ensure_ascii=False),
                "fee_ready": "yes" if complete else "no",
            }
        )
    summary = {
        "pool_count": len(by_pool),
        "fee_ready_pool_count": sum(1 for r in rows if r["fee_ready"] == "yes"),
        "nonzero_pool_count": sum(1 for r in rows if r["nonzero_window_count"] > 0),
        "partial_pool_count": sum(1 for r in rows if r["complete_window_count"] < r["window_count"]),
        "top_root_causes": Counter(
            x for r in fee_rows for x in [r["root_cause"] or "none"]
        ).most_common(5),
    }
    return rows, summary


def safety_audit() -> dict[str, Any]:
    return {
        "private_key_loaded": False,
        "wallet_loaded": False,
        "signer_created": False,
        "transaction_sent": False,
        "eth_sendTransaction_called": False,
        "eth_sendRawTransaction_called": False,
        "swap_called": False,
        "mint_called": False,
        "burn_called": False,
        "collect_called": False,
        "approve_called": False,
        "eth_getLogs_bounded": True,
        "read_only_eth_call_only": True,
        "event_logs_read_only": True,
        "wallet_or_tx_touched": False,
        "can_run_probe_now": False,
        "tiny_canary_allowed": "no",
    }


def build_checkpoint_state(
    run_id: str,
    started_at: int,
    windows: list[str],
    pool_contexts: list[dict[str, Any]],
    selected_rows: list[dict[str, str]],
    rpc_ready: dict[str, Any],
    resume: bool,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "started_at": started_at,
        "current_time": started_at,
        "windows": windows,
        "completed_targets": [],
        "completed_window_targets": [],
        "pool_count": len(pool_contexts),
        "selected_pool_count": len(selected_rows),
        "next_pool_index": 0,
        "next_window_index": 0,
        "last_checkpoint_at": started_at,
        "resume": bool(resume),
        "rpc_env_key": rpc_ready.get("rpc_env_key"),
        "latest_block": as_int(rpc_ready.get("latest_block")),
    }


def build_final_verdict(
    run_id: str,
    selected_rows: list[dict[str, str]],
    fee_blockers_summary: dict[str, Any],
    fee_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    econ_agg: dict[str, Any],
    windows_completed: list[str],
    pool_code_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "PASS" if fee_blockers_summary["fee_ready_pool_count"] > 0 else "WARN" if fee_blockers_summary["pool_count"] > 0 else "FAIL",
        "stage": "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_BACKFILL_V1",
        "run_id": run_id,
        "selected_pool_count": len(selected_rows),
        "windows_completed": windows_completed,
        "swap_log_pool_count": fee_blockers_summary["nonzero_pool_count"],
        "fee_ready_pool_count": fee_blockers_summary["fee_ready_pool_count"],
        "swap_log_count": sum(int(r["log_count"]) for r in summary_rows),
        "volume_usd_total": sum(as_float(r["volume_usd_proxy"]) or 0.0 for r in summary_rows),
        "pool_fee_usd_proxy_total": sum(as_float(r["pool_fee_usd_proxy"]) or 0.0 for r in summary_rows),
        "economics_preview_ran": True,
        "positive_proxy_count_total": econ_agg["positive_proxy_count_total"],
        "positive_proxy_count_realistic": econ_agg["positive_proxy_count_realistic"],
        "best_pool": econ_agg["best_pool"],
        "best_pair": econ_agg["best_pair"],
        "best_fee_tier": econ_agg["best_fee_tier"],
        "best_notional": econ_agg["best_notional"],
        "best_hold_window": econ_agg["best_hold_window"],
        "best_net_ev_proxy_usd": econ_agg["best_net_ev_proxy_usd"],
        "actual_fee_ready": False,
        "token_id_available": False,
        "can_run_probe_now": False,
        "can_run_virtual_economics_now": fee_blockers_summary["fee_ready_pool_count"] > 0,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "wallet_or_tx_touched": False,
        "recommended_next_stage": stage_decision(econ_agg, fee_blockers_summary),
        "window_count": len(set(windows_completed)) or 0,
        "selected_pool_rows_with_code": sum(1 for r in pool_code_rows if r["eth_getCode_ok"] == "yes"),
    }


def stage_decision(econ_agg: dict[str, Any], fee_summary: dict[str, Any]) -> str:
    if fee_summary["fee_ready_pool_count"] >= 4 and econ_agg["positive_proxy_count_realistic"] > 0:
        return "LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1"
    if fee_summary["fee_ready_pool_count"] >= 1:
        return "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_FIX_REPEAT"
    return "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_REPEAT"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-hours", type=int, default=10)
    ap.add_argument("--checkpoint-minutes", type=int, default=60)
    ap.add_argument("--windows", default="24h,72h,7d,14d,30d")
    ap.add_argument("--max-blocks-per-query", type=int, default=4000)
    ap.add_argument("--max-logs-per-pool", type=int, default=50000)
    ap.add_argument("--rpc-timeout", type=int, default=20)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    run_id = args.run_id
    out_dir = Path(args.output_dir)
    final_dir = out_dir / "final"
    checkpoint_dir = out_dir / "checkpoint"
    data_dir = out_dir / "data"
    logs_dir = out_dir / "logs"
    ensure_dir(final_dir)
    ensure_dir(checkpoint_dir)
    ensure_dir(data_dir)
    ensure_dir(logs_dir)

    # bootstrap metadata
    input_rows, input_summary = input_audit()
    write_text(
        out_dir / "INPUT_ARTIFACT_AUDIT_CN.md",
        "# 输入工件审计\n\n"
        + "\n".join(f"- {r['path']}: {'yes' if r['exists'] else 'no'}" for r in input_rows)
        + "\n\n"
        + f"- quoter_staticcall_ready: `{fmt(input_summary['quoter_staticcall_ready'])}`\n"
        + f"- tick_ready_pool_count: `{fmt(input_summary['tick_ready_pool_count'])}`\n"
        + f"- cost_ready_pool_count: `{fmt(input_summary['cost_ready_pool_count'])}`\n"
        + f"- fee_ready_pool_count: `{fmt(input_summary['fee_ready_pool_count'])}`\n"
        + f"- recommended_next_stage: `{fmt(input_summary['recommended_next_stage'])}`\n"
        + f"- suitable_for_fee_velocity_backfill: `{fmt(input_summary['suitable_for_fee_velocity_backfill'])}`\n"
        + f"- tiny_canary_allowed: `no`\n",
    )
    write_json(out_dir / "input_artifact_audit.json", input_summary)

    selected_rows = read_selected_pools()
    prices, decimals = load_quote_anchors()
    rpc_url, rpc_ready = read_only_rpc()
    write_text(
        out_dir / "BSC_RPC_READINESS_CN.md",
        "# BSC RPC Readiness\n\n"
        + f"- rpc_env_key: `{rpc_ready.get('rpc_env_key')}`\n"
        + f"- chain_id: `{rpc_ready.get('chain_id')}`\n"
        + f"- latest_block: `{rpc_ready.get('latest_block')}`\n"
        + f"- rpc_read_only_test_pass: `{fmt(rpc_ready.get('rpc_read_only_test_pass'))}`\n"
        + f"- eth_getLogs_smoke_pass: `{fmt(rpc_ready.get('eth_getLogs_smoke_pass'))}`\n",
    )
    write_json(out_dir / "bsc_rpc_readiness.json", rpc_ready)
    if not rpc_ready.get("rpc_read_only_test_pass") or str(rpc_ready.get("chain_id")) != "56":
        write_json(final_dir / "FINAL_VERDICT.json", {
            "status": "FAIL",
            "stage": "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_BACKFILL_V1",
            "run_id": run_id,
            "selected_pool_count": len(selected_rows),
            "windows_completed": [],
            "swap_log_pool_count": 0,
            "fee_ready_pool_count": 0,
            "swap_log_count": 0,
            "volume_usd_total": 0,
            "pool_fee_usd_proxy_total": 0,
            "economics_preview_ran": False,
            "positive_proxy_count_total": 0,
            "positive_proxy_count_realistic": 0,
            "best_pool": "",
            "best_pair": "",
            "best_fee_tier": "",
            "best_notional": None,
            "best_hold_window": "",
            "best_net_ev_proxy_usd": None,
            "actual_fee_ready": False,
            "token_id_available": False,
            "can_run_probe_now": False,
            "can_run_virtual_economics_now": False,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "wallet_or_tx_touched": False,
            "recommended_next_stage": "LP_BSC_RPC_SETUP_REQUIRED",
        })
        write_text(out_dir / "BSC_OVERNIGHT_START_SAFETY_AUDIT_CN.md", "# BSC Overnight Start Safety Audit\n\n- private_key_loaded: `no`\n- wallet_loaded: `no`\n- signer_created: `no`\n- transaction_sent: `no`\n- eth_sendTransaction_called: `no`\n- eth_sendRawTransaction_called: `no`\n- swap_called: `no`\n- mint_called: `no`\n- burn_called: `no`\n- collect_called: `no`\n- approve_called: `no`\n- eth_getLogs_bounded: `yes`\n- read_only_eth_call_only: `yes`\n- event_logs_read_only: `yes`\n- wallet_or_tx_touched: `no`\n- can_run_probe_now: `no`\n- tiny_canary_allowed: `no`\n")
        write_json(out_dir / "bsc_overnight_start_safety_audit.json", safety_audit())
        return 2

    pool_contexts = build_pool_contexts(rpc_url, selected_rows, prices, decimals)
    pool_code_rows = []
    for row in pool_contexts:
        pool_code_rows.append(
            {
                "pool_id": row["pool_id"],
                "token_pair": row["token_pair"],
                "eth_getCode_ok": "yes" if get_code_ok(rpc_url, row["pool_id"]) else "no",
            }
        )
    write_csv(out_dir / "BSC_SELECTED_POOL_SET_CN.csv", selected_rows, list(selected_rows[0].keys()) if selected_rows else [])

    start_ts = int(time.time())
    max_seconds = max(1, args.max_hours * 3600)
    checkpoint_seconds = max(60, args.checkpoint_minutes * 60)
    windows = [w.strip() for w in args.windows.split(",") if w.strip()]
    state_path = checkpoint_dir / "state.json"
    state = build_checkpoint_state(run_id, start_ts, windows, pool_contexts, selected_rows, rpc_ready, args.resume)
    write_json(state_path, state)

    swap_log_rows: list[dict[str, Any]] = []
    fee_rows: list[dict[str, Any]] = []
    completed_keys: set[tuple[str, str]] = set()
    hourly_snapshots: list[Path] = []
    window_complete_flags: dict[str, set[str]] = defaultdict(set)

    def checkpoint(force: bool = False) -> None:
        now = int(time.time())
        state["current_time"] = now
        state["completed_targets"] = sorted(f"{p}|{w}" for p, w in completed_keys)
        state["completed_window_targets"] = {w: sorted(list(window_complete_flags.get(w, set()))) for w in windows}
        write_json(state_path, state)
        if force or now - state["last_checkpoint_at"] >= checkpoint_seconds:
            snap = checkpoint_dir / f"hourly_{time.strftime('%Y%m%d_%H%M%S', time.gmtime(now))}.json"
            write_json(snap, state)
            hourly_snapshots.append(snap)
            state["last_checkpoint_at"] = now

    total_pool_windows = len(pool_contexts) * len(windows)
    processed = 0
    log_print = lambda msg: print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {msg}", flush=True)
    log_print(f"run_id={run_id} pools={len(pool_contexts)} windows={windows} max_hours={args.max_hours}")

    for pool_idx, pool in enumerate(pool_contexts):
        for window_idx, window in enumerate(windows):
            if (pool["pool_id"], window) in completed_keys:
                continue
            elapsed = time.time() - start_ts
            if elapsed >= max_seconds:
                log_print("max-hours reached; stopping scan loop")
                break
            log_print(f"scan pool={pool['pool_id']} window={window}")
            latest_block = int(rpc_call(rpc_url, "eth_blockNumber", [], timeout=args.rpc_timeout), 16)
            row, decoded_rows = windowed_fee_row(
                pool=pool,
                window_label=window,
                latest_block=latest_block,
                rpc_url=rpc_url,
                max_blocks_per_query=args.max_blocks_per_query,
                max_logs_per_pool=args.max_logs_per_pool,
                rpc_timeout=args.rpc_timeout,
                prices=prices,
            )
            row["run_id"] = run_id
            for dr in decoded_rows:
                dr["run_id"] = run_id
            fee_rows.append(row)
            swap_log_rows.extend(decoded_rows)
            completed_keys.add((pool["pool_id"], window))
            if row["log_count"] > 0 and not row["partial"]:
                window_complete_flags[window].add(pool["pool_id"])
            processed += 1
            checkpoint(force=False)
            print(
                json.dumps(
                    {
                        "event": "checkpoint",
                        "processed_pool_windows": processed,
                        "total_pool_windows": total_pool_windows,
                        "pool_id": pool["pool_id"],
                        "window": window,
                        "log_count": row["log_count"],
                        "partial": row["partial"],
                        "root_cause": row["root_cause"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        else:
            continue
        break

    checkpoint(force=True)

    write_csv(
        data_dir / "swap_logs_decoded.csv",
        swap_log_rows,
        [
            "run_id",
            "pool_id",
            "token_pair",
            "window",
            "block_number",
            "tx_hash",
            "log_index",
            "sender",
            "recipient",
            "amount0",
            "amount1",
            "sqrtPriceX96",
            "liquidity",
            "tick",
            "amount0_usd_proxy",
            "amount1_usd_proxy",
            "volume_usd_proxy",
            "fee_tier_raw",
            "fee_rate_fraction",
            "created_at",
        ],
    )
    write_csv(
        data_dir / "pool_fee_velocity.csv",
        fee_rows,
        [
            "run_id",
            "pool_id",
            "token_pair",
            "chain",
            "protocol",
            "pool_type",
            "fee_tier_raw",
            "window",
            "from_block",
            "to_block",
            "block_window_hint",
            "query_count",
            "log_count",
            "decoded_log_count",
            "unique_traders",
            "buyer_count",
            "seller_count",
            "buy_count",
            "sell_count",
            "volume_usd_proxy",
            "pool_fee_usd_proxy",
            "fee_velocity_15m",
            "fee_velocity_30m",
            "fee_velocity_1h",
            "fee_velocity_2h",
            "fee_velocity_6h",
            "fee_velocity_24h",
            "fee_source",
            "partial",
            "root_cause",
            "confidence",
            "invalid_reason",
            "created_at",
        ],
    )
    summary_rows = []
    fee_by_pool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in fee_rows:
        fee_by_pool[row["pool_id"]].append(row)
    for pool_id, rows in fee_by_pool.items():
        complete = [r for r in rows if not r["partial"] and r["log_count"] > 0]
        chosen = sorted((complete or [r for r in rows if r["log_count"] > 0] or rows), key=lambda r: WINDOW_SECONDS[r["window"]])[-1]
        summary_rows.append(
            {
                "run_id": run_id,
                "pool_id": pool_id,
                "token_pair": chosen["token_pair"],
                "best_window": chosen["window"],
                "log_count": chosen["log_count"],
                "swap_count": chosen["decoded_log_count"],
                "volume_usd_proxy": chosen["volume_usd_proxy"],
                "pool_fee_usd_proxy": chosen["pool_fee_usd_proxy"],
                "fee_velocity_15m": chosen["fee_velocity_15m"],
                "fee_velocity_30m": chosen["fee_velocity_30m"],
                "fee_velocity_1h": chosen["fee_velocity_1h"],
                "fee_velocity_2h": chosen["fee_velocity_2h"],
                "fee_velocity_6h": chosen["fee_velocity_6h"],
                "fee_velocity_24h": chosen["fee_velocity_24h"],
                "partial": chosen["partial"],
                "root_cause": chosen["root_cause"],
                "confidence": chosen["confidence"],
            }
        )
    write_json(data_dir / "pool_fee_velocity_summary.json", {"rows": summary_rows, "pool_count": len(summary_rows)})

    fee_blockers_rows, fee_blockers_summary = blocker_diagnosis(fee_rows)
    write_text(
        final_dir / "BSC_FEE_VELOCITY_BLOCKER_DIAGNOSIS_CN.md",
        "# BSC Fee Velocity Blocker Diagnosis\n\n"
        + "\n".join(
            [
                f"- pool_count: `{fee_blockers_summary['pool_count']}`",
                f"- fee_ready_pool_count: `{fee_blockers_summary['fee_ready_pool_count']}`",
                f"- nonzero_pool_count: `{fee_blockers_summary['nonzero_pool_count']}`",
                f"- partial_pool_count: `{fee_blockers_summary['partial_pool_count']}`",
                f"- top_root_causes: `{fee_blockers_summary['top_root_causes']}`",
            ]
        )
        + "\n",
    )
    write_csv(
        final_dir / "bsc_fee_velocity_blocker_diagnosis.csv",
        fee_blockers_rows,
        ["pool_id", "window_count", "nonzero_window_count", "complete_window_count", "most_common_root_cause", "root_cause_counts", "fee_ready"],
    )
    write_json(final_dir / "bsc_fee_velocity_blocker_diagnosis.json", fee_blockers_summary)

    # Read previous economics inputs and produce preview with overnight fee proxies.
    overnight_realdata = latest_overnight_realdata_dir()
    cost_rows = load_csv(overnight_realdata / "BSC_REAL_COST_MODEL_RESULTS_CN.csv")
    tick_rows = load_csv(overnight_realdata / "BSC_TICK_LIQUIDITY_RESULTS_CN.csv")
    quote_rows = load_csv(QUOTER_AMOUNT_FIX_DIR / "bsc_precise_quote_staticcall_v3_results.csv")
    econ_rows, econ_agg = economics_preview_rows(selected_rows, pool_contexts, fee_rows, cost_rows, tick_rows, quote_rows)
    write_text(
        final_dir / "BSC_ECONOMICS_PREVIEW_WITH_OVERNIGHT_FEE_CN.md",
        "# BSC Economics Preview With Overnight Fee\n\n"
        + "\n".join(
            [
                f"- row_count: `{econ_agg['row_count']}`",
                f"- positive_proxy_count_total: `{econ_agg['positive_proxy_count_total']}`",
                f"- positive_proxy_count_realistic: `{econ_agg['positive_proxy_count_realistic']}`",
                f"- best_pool: `{econ_agg['best_pool']}`",
                f"- best_pair: `{econ_agg['best_pair']}`",
                f"- best_fee_tier: `{econ_agg['best_fee_tier']}`",
                f"- best_notional: `{fmt(econ_agg['best_notional'])}`",
                f"- best_hold_window: `{econ_agg['best_hold_window']}`",
                f"- best_fee_window_used: `{econ_agg['best_fee_window_used']}`",
                f"- best_net_ev_proxy_usd: `{fmt(econ_agg['best_net_ev_proxy_usd'])}`",
            ]
        )
        + "\n",
    )
    write_csv(
        final_dir / "bsc_economics_preview_with_overnight_fee.csv",
        econ_rows,
        [
            "pool_id",
            "token_pair",
            "fee_tier_raw",
            "notional_usd",
            "hold_window",
            "scenario",
            "fee_proxy_usd",
            "fixed_cost_usd",
            "il_lvr_proxy_usd",
            "net_ev_proxy_usd",
            "net_ev_proxy_pct",
            "capacity_ok",
            "data_sufficient",
            "confidence",
            "fee_window_used",
        ],
    )
    write_json(final_dir / "bsc_economics_preview_with_overnight_fee.json", {"rows": econ_rows, "aggregate": econ_agg})

    review_rows = candidate_review_rows(pool_contexts, fee_rows, econ_rows)
    write_text(
        final_dir / "BSC_FEE_VELOCITY_OVERNIGHT_RESULTS_CN.md",
        "# BSC Fee Velocity Overnight Results\n\n"
        + "\n".join(
            [
                f"- selected_pool_count: `{len(selected_rows)}`",
                f"- fee_ready_pool_count: `{fee_blockers_summary['fee_ready_pool_count']}`",
                f"- swap_log_pool_count: `{fee_blockers_summary['nonzero_pool_count']}`",
                f"- swap_log_count: `{sum(r['log_count'] for r in fee_rows if r['log_count'] > 0)}`",
                f"- volume_usd_total: `{fmt(sum(as_float(r['volume_usd_proxy']) or 0.0 for r in summary_rows))}`",
                f"- pool_fee_usd_proxy_total: `{fmt(sum(as_float(r['pool_fee_usd_proxy']) or 0.0 for r in summary_rows))}`",
            ]
        )
        + "\n",
    )
    write_csv(
        final_dir / "bsc_fee_velocity_overnight_results.csv",
        summary_rows,
        ["run_id", "pool_id", "token_pair", "best_window", "log_count", "swap_count", "volume_usd_proxy", "pool_fee_usd_proxy", "fee_velocity_15m", "fee_velocity_30m", "fee_velocity_1h", "fee_velocity_2h", "fee_velocity_6h", "fee_velocity_24h", "partial", "root_cause", "confidence"],
    )
    write_json(final_dir / "bsc_fee_velocity_overnight_results.json", {"rows": summary_rows})

    write_text(
        final_dir / "BSC_CANDIDATE_REVIEW_MATRIX_CN.md",
        "# BSC Candidate Review Matrix\n\n" + "\n".join(f"- {r['pool_id']} {r['token_pair']} => {r['candidate_status']} ({r['reason']})" for r in review_rows) + "\n",
    )
    write_csv(
        final_dir / "bsc_candidate_review_matrix.csv",
        review_rows,
        ["pool_id", "token_pair", "fee_tier_raw", "best_fee_window", "best_net_ev_proxy_usd", "best_net_ev_proxy_pct", "candidate_status", "reason"],
    )
    write_json(final_dir / "bsc_candidate_review_matrix.json", {"rows": review_rows})

    safety = safety_audit()
    write_text(
        out_dir / "BSC_OVERNIGHT_START_SAFETY_AUDIT_CN.md",
        "# BSC Overnight Start Safety Audit\n\n" + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in safety.items()) + "\n",
    )
    write_json(out_dir / "bsc_overnight_start_safety_audit.json", safety)

    windows_completed = sorted(
        w for w in windows if len({r["pool_id"] for r in fee_rows if r["window"] == w and not r["partial"] and r["log_count"] > 0}) == len(pool_contexts)
    )
    verdict_status = "PASS"
    if fee_blockers_summary["fee_ready_pool_count"] == 0:
        verdict_status = "WARN"
    if fee_blockers_summary["pool_count"] == 0:
        verdict_status = "FAIL"
    final_verdict = build_final_verdict(
        run_id,
        selected_rows,
        fee_blockers_summary,
        fee_rows,
        summary_rows,
        econ_agg,
        windows_completed,
        pool_code_rows,
    )
    final_verdict["status"] = verdict_status
    final_verdict["window_count"] = len(windows)
    write_json(final_dir / "FINAL_VERDICT.json", final_verdict)
    write_text(
        final_dir / "ONEPAGE_CN.md",
        "# BSC Fee Velocity Overnight Backfill Onepage\n\n"
        + f"- status: `{final_verdict['status']}`\n"
        + f"- stage: `{final_verdict['stage']}`\n"
        + f"- run_id: `{run_id}`\n"
        + f"- selected_pool_count: `{final_verdict['selected_pool_count']}`\n"
        + f"- windows_completed: `{final_verdict['windows_completed']}`\n"
        + f"- fee_ready_pool_count: `{final_verdict['fee_ready_pool_count']}`\n"
        + f"- swap_log_pool_count: `{final_verdict['swap_log_pool_count']}`\n"
        + f"- swap_log_count: `{final_verdict['swap_log_count']}`\n"
        + f"- best_pool: `{final_verdict['best_pool']}`\n"
        + f"- best_pair: `{final_verdict['best_pair']}`\n"
        + f"- best_fee_tier: `{final_verdict['best_fee_tier']}`\n"
        + f"- best_hold_window: `{final_verdict['best_hold_window']}`\n"
        + f"- best_net_ev_proxy_usd: `{fmt(final_verdict['best_net_ev_proxy_usd'])}`\n"
        + f"- recommended_next_stage: `{final_verdict['recommended_next_stage']}`\n"
        + f"- tiny_canary_allowed: `no`\n",
    )
    artifact_files = [
        "BSC_FEE_VELOCITY_OVERNIGHT_RESULTS_CN.md",
        "bsc_fee_velocity_overnight_results.csv",
        "bsc_fee_velocity_overnight_results.json",
        "BSC_FEE_VELOCITY_BLOCKER_DIAGNOSIS_CN.md",
        "bsc_fee_velocity_blocker_diagnosis.csv",
        "bsc_fee_velocity_blocker_diagnosis.json",
        "BSC_ECONOMICS_PREVIEW_WITH_OVERNIGHT_FEE_CN.md",
        "bsc_economics_preview_with_overnight_fee.csv",
        "bsc_economics_preview_with_overnight_fee.json",
        "FINAL_VERDICT.json",
        "ONEPAGE_CN.md",
        "ARTIFACT_INDEX.md",
        "BSC_RPC_READINESS_CN.md",
        "bsc_rpc_readiness.json",
        "INPUT_ARTIFACT_AUDIT_CN.md",
        "input_artifact_audit.json",
        "BSC_OVERNIGHT_START_SAFETY_AUDIT_CN.md",
        "bsc_overnight_start_safety_audit.json",
        "BSC_CANDIDATE_REVIEW_MATRIX_CN.md",
        "bsc_candidate_review_matrix.csv",
        "bsc_candidate_review_matrix.json",
        "data/swap_logs_decoded.csv",
        "data/pool_fee_velocity.csv",
        "data/pool_fee_velocity_summary.json",
        "checkpoint/state.json",
    ]
    write_text(final_dir / "ARTIFACT_INDEX.md", "# BSC Fee Velocity Overnight Artifact Index\n\n" + "\n".join(f"- `{a}`" for a in artifact_files) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
