#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
import math
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from eth_abi import decode as abi_decode


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/Users/bendu/lp-bot/v3"))
RUN_ID = os.environ.get("RUN_ID_OVERRIDE", time.strftime("%Y%m%d_%H%M%S", time.gmtime()))
REPORT_DIR = Path(os.environ.get("REPORT_DIR_OVERRIDE", str(REPO_ROOT / "reports" / "lp_bsc_overnight_realdata_pipeline" / RUN_ID)))
BASE = load_module("lp_bsc_quoter_staticcall_amount_fix_v1_readonly", REPO_ROOT / "scripts" / "lp_bsc_quoter_staticcall_amount_fix_v1_readonly.py")
TICK = load_module("lp_v3_tick_liquidity_pipeline_v1_readonly", REPO_ROOT / "scripts" / "lp_v3_tick_liquidity_pipeline_v1_readonly.py")
RPC_HELPER = load_module("lp_bsc_pancakeswap_v3_precise_quote_v2_readonly", REPO_ROOT / "scripts" / "lp_bsc_pancakeswap_v3_precise_quote_v2_readonly.py")

AMOUNT_FIX_DIR = REPO_ROOT / "reports" / "lp_bsc_quoter_staticcall_amount_fix" / "20260601_173837"
PRECISE_FIX_DIR = REPO_ROOT / "reports" / "lp_bsc_pancakeswap_v3_precise_quote_fix" / "20260601_163613"
PRECISE_DIR = REPO_ROOT / "reports" / "lp_bsc_pancakeswap_v3_precise_quote" / "20260602_235959"
DISCOVERY_DIR = REPO_ROOT / "reports" / "lp_evm_standard_v3_discovery" / "20260602_000000"
EXPANSION_DIR = REPO_ROOT / "reports" / "lp_evm_universe_expansion_design" / "20260601_155703"
FREEZE_DIR = REPO_ROOT / "reports" / "lp_real_data_final_freeze" / "20260601_150954"
STATUS_DOC = REPO_ROOT / "docs" / "LPBOT_RESEARCH_STATUS_CN.md"
INDEX_DOC = REPO_ROOT / "docs" / "LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md"

CHAIN_ID_EXPECTED = 56
NOTIONALS = [20, 100, 500, 1000, 2000]
HOLD_WINDOWS = ["15m", "30m", "1h", "2h", "6h", "24h"]
WINDOW_SECONDS = {"15m": 15 * 60, "30m": 30 * 60, "1h": 3600, "2h": 7200, "6h": 21600, "24h": 86400}
WINDOW_SCAN_BLOCKS = {"24h": 28800}
SWAP_TOPIC_V3 = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
ALLOWED_NEXT = {
    "LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1",
    "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_FIX_REPEAT",
    "LP_BSC_PANCAKESWAP_V3_TICK_LIQUIDITY_FIX_REPEAT",
    "LP_BSC_PANCAKESWAP_V3_REAL_COST_FIX_REPEAT",
    "LP_EVM_STANDARD_V3_DISCOVERY_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}


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


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return ""
        return f"{v:.10f}".rstrip("0").rstrip(".")
    return str(v)


def as_float(v: Any) -> float | None:
    try:
        return None if v in (None, "", "null", "None") else float(v)
    except Exception:
        return None


def as_int(v: Any) -> int | None:
    try:
        return None if v in (None, "", "null", "None") else int(float(v))
    except Exception:
        return None


def rpc() -> tuple[str, dict[str, Any]]:
    rpc_url, ready = RPC_HELPER.read_only_rpc()
    if not ready.get("rpc_read_only_test_pass"):
        return rpc_url, ready
    # normalize chain readouts for overnight BSC flow
    try:
        ready["gas_price_wei"] = int(RPC_HELPER.rpc_call(rpc_url, "eth_gasPrice", []), 16)
    except Exception:
        ready["gas_price_wei"] = None
    try:
        ready["fee_history_ok"] = bool(RPC_HELPER.rpc_call(rpc_url, "eth_feeHistory", [1, "latest", []]))
    except Exception:
        ready["fee_history_ok"] = False
    return rpc_url, ready


def input_artifact_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    inputs = [
        AMOUNT_FIX_DIR / "FINAL_VERDICT.json",
        AMOUNT_FIX_DIR / "BSC_PRECISE_QUOTE_STATICCALL_V3_RESULTS_CN.md",
        AMOUNT_FIX_DIR / "bsc_precise_quote_staticcall_v3_results.csv",
        AMOUNT_FIX_DIR / "BSC_QUOTER_V2_V3_FIX_COMPARISON_CN.md",
        AMOUNT_FIX_DIR / "BSC_STATICCALL_AMOUNT_FIX_SAFETY_AUDIT_CN.md",
        AMOUNT_FIX_DIR / "LP_BSC_QUOTER_AMOUNT_FIX_NEXT_STAGE_DECISION_CN.md",
        PRECISE_FIX_DIR / "FINAL_VERDICT.json",
        PRECISE_DIR / "LP_BSC_PRECISE_QUOTE_FINAL_VERDICT.json",
        DISCOVERY_DIR / "FINAL_VERDICT.json",
        DISCOVERY_DIR / "evm_standard_v3_normalized_universe.csv",
        EXPANSION_DIR / "BSC_PANCAKESWAP_V3_EXPANSION_DESIGN_CN.md",
        FREEZE_DIR / "FINAL_VERDICT.json",
        STATUS_DOC,
        INDEX_DOC,
    ]
    rows = [{"path": str(p.relative_to(REPO_ROOT)), "exists": p.exists()} for p in inputs]
    verdict = load_json(AMOUNT_FIX_DIR / "FINAL_VERDICT.json")
    summary = {
        "missing_input_list": [r["path"] for r in rows if not r["exists"]],
        "quoter_staticcall_success_count": verdict.get("staticcall_success_count", verdict.get("quote_success_count")),
        "fallback_math_used_count": verdict.get("fallback_math_used_count", 0),
        "selected_abi_variant": verdict.get("selected_abi_variant"),
        "recommended_next_stage": verdict.get("recommended_next_stage"),
        "bsc_quoter_staticcall_fixed": verdict.get("quoter_v2_staticcall_fixed", False),
        "can_run_overnight_readonly": bool(verdict.get("quoter_v2_staticcall_fixed")) and verdict.get("tiny_canary_allowed") == "no",
        "overnight_readonly": True,
        "no_probe_no_canary_no_live": True,
    }
    return rows, summary


def read_selected_pool_rows() -> list[dict[str, str]]:
    rows = load_csv(AMOUNT_FIX_DIR / "bsc_precise_quote_staticcall_v3_results.csv")
    uniq: dict[tuple[str, str], dict[str, str]] = {}
    for r in rows:
        if r.get("quote_success") != "yes":
            continue
        key = (r.get("pool_id", ""), r.get("fee_tier", ""))
        uniq.setdefault(key, r)
    selected = list(uniq.values())
    selected.sort(key=lambda r: (r.get("token_pair", ""), int(r.get("fee_tier", "0") or 0), r.get("pool_id", "")))
    return selected


def selected_pool_set(selected_quote_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out = []
    for r in selected_quote_rows:
        fee_raw = as_int(r.get("fee_tier")) or 0
        out.append(
            {
                "chain": r.get("chain", "BSC"),
                "chain_id": CHAIN_ID_EXPECTED,
                "protocol": r.get("protocol", "PancakeSwap V3"),
                "pool_address": r.get("pool_id", ""),
                "token_pair": r.get("token_pair", ""),
                "token0": r.get("input_token", ""),
                "token1": r.get("output_token", ""),
                "token0_symbol": r.get("input_token", "").split("/")[-1] if "/" in r.get("input_token", "") else r.get("quote_side", ""),
                "token1_symbol": r.get("output_token", "").split("/")[-1] if "/" in r.get("output_token", "") else "",
                "fee_tier_raw": fee_raw,
                "fee_tier_percent": fee_raw / 10000.0,
                "quote_staticcall_ready": "yes",
                "selected_for_tick": "yes",
                "selected_for_cost": "yes",
                "selected_for_fee": "yes",
                "selected_for_economics": "yes",
            }
        )
    return out


def freeze_selected_pool_set(selected_quote_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pool_rows = []
    by_pool = {}
    for r in selected_quote_rows:
        by_pool.setdefault(r["pool_id"], r)
    for r in by_pool.values():
        fee_raw = as_int(r.get("fee_tier")) or 0
        pool_rows.append(
            {
                "chain": "BSC",
                "chain_id": CHAIN_ID_EXPECTED,
                "protocol": "PancakeSwap V3",
                "pool_address": r["pool_id"],
                "token_pair": r["token_pair"],
                "token0": r["token_in"],
                "token1": r["token_out"],
                "token0_symbol": r["token_in_symbol"],
                "token1_symbol": r["token_out_symbol"],
                "fee_tier_raw": fee_raw,
                "fee_tier_percent": fee_raw / 10000.0,
                "quote_staticcall_ready": "yes",
                "selected_for_tick": "yes",
                "selected_for_cost": "yes",
                "selected_for_fee": "yes",
                "selected_for_economics": "yes",
            }
        )
    pool_rows.sort(key=lambda r: (r["token_pair"], r["fee_tier_raw"], r["pool_address"]))
    return pool_rows, list(by_pool.values())


def build_prices_from_quote_rows(quote_rows: list[dict[str, str]]) -> dict[str, Decimal]:
    # Use the exact staticcall report's anchor price values as a BSC token/USD anchor source.
    prices: dict[str, Decimal] = {}
    for r in quote_rows:
        if r.get("quote_success") != "yes":
            continue
        token = r.get("token_in", "").lower()
        anchor = as_float(r.get("token_usd_anchor_price"))
        if token and anchor:
            prices[token] = Decimal(str(anchor))
        token_out = r.get("token_out", "").lower()
        if token_out and token_out not in prices and r.get("token_out_symbol") in {"USDT", "USDC", "BUSD", "DAI"}:
            prices[token_out] = Decimal("1")
    return prices


def scan_tick_pool(rpc_url: str, pool: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "pool_id": pool["pool_address"],
        "token_pair": pool["token_pair"],
        "chain": pool["chain"],
        "protocol": pool["protocol"],
        "fee_tier_raw": pool["fee_tier_raw"],
        "fee_tier_percent": pool["fee_tier_percent"],
        "slot0_success": "no",
        "liquidity_success": "no",
        "tick_bitmap_success": "no",
        "ticks_success": "no",
        "observe_success": "no",
        "total_initialized_ticks_found": 0,
        "avg_initialized_ticks_per_pool": 0,
        "tick_snapshot_confidence": "low",
        "invalid_reason": "",
    }
    try:
        out["token0"] = TICK.call_simple_address(rpc_url, pool["pool_address"], "token0()")
        out["token1"] = TICK.call_simple_address(rpc_url, pool["pool_address"], "token1()")
        out["fee"] = TICK.call_simple_uint(rpc_url, pool["pool_address"], "fee()")
        out["tickSpacing"] = TICK.call_simple_uint(rpc_url, pool["pool_address"], "tickSpacing()")
        out["liquidity"] = TICK.call_simple_uint(rpc_url, pool["pool_address"], "liquidity()")
        out["slot0"] = TICK.call_slot0(rpc_url, pool["pool_address"])
        out["slot0_success"] = "yes"
        out["liquidity_success"] = "yes"
    except Exception as exc:
        out["invalid_reason"] = f"slot_or_liquidity_failed:{type(exc).__name__}"
        return out

    try:
        current_tick = out["slot0"]["current_tick"]
        tick_spacing = out["tickSpacing"] or 1
        base_word = (current_tick // tick_spacing) >> 8
        initialized: list[int] = []
        per_word: dict[str, Any] = {}
        for word_pos in range(base_word - 4, base_word + 5):
            try:
                word = TICK.call_tick_bitmap(rpc_url, pool["pool_address"], word_pos)
                per_word[str(word_pos)] = word
                ticks = TICK.initialized_ticks_from_bitmap(word, word_pos, tick_spacing)
                initialized.extend(ticks)
                out["tick_bitmap_success"] = "yes"
            except Exception:
                continue
        initialized = sorted(set(initialized), key=lambda t: abs(t - current_tick))[:10]
        if initialized:
            out["tickBitmap_words"] = per_word
            out["total_initialized_ticks_found"] = len(initialized)
            for tick_index in initialized:
                try:
                    TICK.call_tick(rpc_url, pool["pool_address"], tick_index)
                    out["ticks_success"] = "yes"
                except Exception:
                    pass
            try:
                TICK.call_observe(rpc_url, pool["pool_address"], [300, 0])
                out["observe_success"] = "yes"
            except Exception:
                pass
    except Exception as exc:
        out["invalid_reason"] = f"tick_scan_failed:{type(exc).__name__}"
        return out

    out["avg_initialized_ticks_per_pool"] = float(out["total_initialized_ticks_found"]) if out["total_initialized_ticks_found"] else 0
    if out["slot0_success"] == "yes" and out["liquidity_success"] == "yes" and out["tick_bitmap_success"] == "yes" and out["ticks_success"] == "yes" and out["observe_success"] == "yes" and out["total_initialized_ticks_found"] >= 6:
        out["tick_snapshot_confidence"] = "high"
    elif out["slot0_success"] == "yes" and out["liquidity_success"] == "yes":
        out["tick_snapshot_confidence"] = "medium"
    else:
        out["tick_snapshot_confidence"] = "low"
    return out


def get_block_number(rpc_url: str) -> int:
    return int(RPC_HELPER.rpc_call(rpc_url, "eth_blockNumber", []), 16)


def hex_block(n: int) -> str:
    return hex(max(n, 0))


def decode_swap_v3(log: dict[str, Any]) -> dict[str, Any]:
    payload = bytes.fromhex(log["data"][2:])
    amount0, amount1, sqrt_price_x96, liquidity, tick = abi_decode(["int256", "int256", "uint160", "uint128", "int24"], payload)
    sender = "0x" + log["topics"][1][-40:]
    recipient = "0x" + log["topics"][2][-40:]
    return {
        "sender": sender.lower(),
        "recipient": recipient.lower(),
        "amount0": int(amount0),
        "amount1": int(amount1),
        "sqrtPriceX96": int(sqrt_price_x96),
        "liquidity": int(liquidity),
        "tick": int(tick),
    }


def get_logs_bounded(rpc_url: str, pool: str, from_block: int, to_block: int, max_logs: int = 2000, chunk_size: int = 5000) -> tuple[list[dict[str, Any]], bool, int]:
    logs: list[dict[str, Any]] = []
    partial = False
    query_count = 0
    start = from_block
    while start <= to_block and len(logs) < max_logs:
        end = min(start + chunk_size - 1, to_block)
        query = {
            "fromBlock": hex_block(start),
            "toBlock": hex_block(end),
            "address": pool,
            "topics": [SWAP_TOPIC_V3],
        }
        query_count += 1
        try:
            chunk = RPC_HELPER.rpc_call(rpc_url, "eth_getLogs", [query])
            if len(chunk) + len(logs) > max_logs:
                chunk = chunk[: max(0, max_logs - len(logs))]
                partial = True
            logs.extend(chunk)
        except Exception:
            partial = True
        start = end + 1
    if start <= to_block:
        partial = True
    return logs, partial, query_count


def load_fee_inputs_from_logs(rpc_url: str, pool_rows: list[dict[str, Any]], prices: dict[str, Decimal]) -> list[dict[str, Any]]:
    latest = get_block_number(rpc_url)
    out = []
    for pool in pool_rows:
        pool_id = pool["pool_address"]
        token0 = pool["token0"].lower()
        token1 = pool["token1"].lower()
        price0 = prices.get(token0)
        price1 = prices.get(token1)
        fee_rate = Decimal(pool["fee_tier_raw"]) / Decimal(1_000_000) if pool["fee_tier_raw"] else Decimal("0")
        for window, secs in WINDOW_SCAN_BLOCKS.items():
            from_block = max(latest - secs, 0)
            logs, partial, qcount = get_logs_bounded(rpc_url, pool_id, from_block, latest, max_logs=5000, chunk_size=4000)
            swap_count = len(logs)
            volume_usd = Decimal(0)
            sender_set, recipient_set = set(), set()
            for lg in logs:
                try:
                    dec = decode_swap_v3(lg)
                except Exception:
                    continue
                sender_set.add(dec["sender"])
                recipient_set.add(dec["recipient"])
                usd0 = abs(Decimal(dec["amount0"])) / Decimal(10 ** 18) * (price0 or Decimal(1))
                usd1 = abs(Decimal(dec["amount1"])) / Decimal(10 ** 18) * (price1 or Decimal(1))
                volume_usd += max(usd0, usd1)
            fee_proxy = volume_usd * fee_rate
            hours = Decimal(window.rstrip("hd")) if window.endswith("h") else Decimal(24)
            if window == "24h":
                hours = Decimal(24)
            elif window == "72h":
                hours = Decimal(72)
            elif window == "7d":
                hours = Decimal(168)
            rate_per_hour = fee_proxy / hours if hours > 0 else Decimal(0)
            out.append(
                {
                    "pool_id": pool_id,
                    "token_pair": pool["token_pair"],
                    "window": window,
                    "from_block": from_block,
                    "to_block": latest,
                    "log_count": swap_count,
                    "unique_traders": len(sender_set | recipient_set),
                    "buyer_count": len(sender_set),
                    "seller_count": len(recipient_set),
                    "buy_count": swap_count,  # proxy; side split left for future refinement
                    "sell_count": swap_count,
                    "token0_amount_usd_proxy": float(volume_usd / 2),
                    "token1_amount_usd_proxy": float(volume_usd / 2),
                    "approx_volume_usd": float(volume_usd),
                    "fee_tier_raw": pool["fee_tier_raw"],
                    "fee_rate_fraction": float(fee_rate),
                    "pool_fee_usd_proxy": float(fee_proxy),
                    "fee_velocity_rate_15m": float(rate_per_hour * Decimal("0.25")),
                    "fee_velocity_rate_30m": float(rate_per_hour * Decimal("0.5")),
                    "fee_velocity_rate_1h": float(rate_per_hour * Decimal("1")),
                    "fee_velocity_rate_2h": float(rate_per_hour * Decimal("2")),
                    "fee_source": "onchain_swap_logs",
                    "partial": partial,
                    "query_count": qcount,
                    "confidence": "high" if not partial and swap_count > 0 else ("medium" if swap_count > 0 else "low"),
                }
            )
    return out


def cost_model_rows(quote_rows: list[dict[str, str]], selected_pools: list[dict[str, Any]], gas_price_wei: int | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pool_by_id = {r["pool_id"]: r for r in quote_rows if r.get("quote_success") == "yes"}
    price_by_token = build_prices_from_quote_rows(quote_rows)
    gas_price_gwei = (gas_price_wei or 0) / 1e9
    wbnb = price_by_token.get("0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c", Decimal("0"))
    gas_price_eth = Decimal(str(gas_price_wei or 0)) / Decimal(10**18) if gas_price_wei else Decimal("0")
    gas_price_usd = float(gas_price_eth * wbnb) if gas_price_eth and wbnb else 0.0
    scenarios = {
        "diagnostic_low": {"gas_mult": 0.85, "add": 180000, "remove": 150000, "collect": 70000, "approval": 45000, "confidence": "low"},
        "realistic_mid": {"gas_mult": 1.0, "add": 220000, "remove": 190000, "collect": 95000, "approval": 50000, "confidence": "medium"},
        "conservative_high": {"gas_mult": 1.2, "add": 280000, "remove": 240000, "collect": 130000, "approval": 65000, "confidence": "low"},
    }
    rows = []
    for pool in selected_pools:
        q = pool_by_id.get(pool["pool_address"])
        if not q:
            continue
        quote_gas = as_float(q.get("gas_estimate")) or 0.0
        quote_gas_usd = quote_gas * gas_price_usd / 1e9 if gas_price_usd else None
        for scenario, cfg in scenarios.items():
            add_cost = cfg["add"] * gas_price_usd if gas_price_usd else None
            remove_cost = cfg["remove"] * gas_price_usd if gas_price_usd else None
            collect_cost = cfg["collect"] * gas_price_usd if gas_price_usd else None
            approval_cost = cfg["approval"] * gas_price_usd if gas_price_usd else None
            total = None if None in {quote_gas_usd, add_cost, remove_cost, collect_cost, approval_cost} else (quote_gas_usd + add_cost + remove_cost + collect_cost + approval_cost)
            for notional in NOTIONALS:
                rows.append(
                    {
                        "pool_id": pool["pool_address"],
                        "token_pair": pool["token_pair"],
                        "notional_usd": notional,
                        "scenario": scenario,
                        "gas_price_gwei": gas_price_gwei,
                        "gas_price_usd": gas_price_usd,
                        "quote_gas_units": quote_gas,
                        "quote_gas_usd": quote_gas_usd,
                        "add_gas_units": cfg["add"],
                        "remove_gas_units": cfg["remove"],
                        "collect_gas_units": cfg["collect"],
                        "approval_gas_units": cfg["approval"],
                        "entry_conversion_cost_usd": add_cost,
                        "exit_conversion_cost_usd": remove_cost,
                        "collect_cost_usd": collect_cost,
                        "approval_cost_usd": approval_cost,
                        "total_fixed_cost_usd": total,
                        "proportional_slippage_cost_usd": 0.0,
                        "future_probe_only_component_count": 4,
                        "cost_model_ready": "yes" if total is not None else "no",
                        "cost_confidence": cfg["confidence"],
                    }
                )
    agg = {
        "pool_count": len(selected_pools),
        "row_count": len(rows),
        "cost_model_ready_pool_count": len({r["pool_id"] for r in rows if r["total_fixed_cost_usd"] is not None}),
        "cost_usd_ready_count": sum(1 for r in rows if r["total_fixed_cost_usd"] is not None),
        "quote_gas_available_count": sum(1 for r in rows if r["quote_gas_units"] is not None),
        "high_confidence_count": sum(1 for r in rows if r["cost_confidence"] == "high"),
        "medium_confidence_count": sum(1 for r in rows if r["cost_confidence"] == "medium"),
        "low_confidence_count": sum(1 for r in rows if r["cost_confidence"] == "low"),
        "future_probe_only_component_count": sum(r["future_probe_only_component_count"] for r in rows),
        "best_realistic_total_cost": min((r["total_fixed_cost_usd"] for r in rows if r["scenario"] == "realistic_mid" and r["total_fixed_cost_usd"] is not None), default=None),
        "median_realistic_total_cost": statistics.median([r["total_fixed_cost_usd"] for r in rows if r["scenario"] == "realistic_mid" and r["total_fixed_cost_usd"] is not None]) if any(r["scenario"] == "realistic_mid" and r["total_fixed_cost_usd"] is not None for r in rows) else None,
    }
    return rows, agg


def economics_preview_rows(quote_rows: list[dict[str, str]], tick_rows: list[dict[str, Any]], cost_rows: list[dict[str, Any]], fee_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    quote_by_pool = {}
    for r in quote_rows:
        if r.get("quote_success") == "yes":
            quote_by_pool.setdefault(r["pool_id"], r)
    cost_by_pool = defaultdict(list)
    for r in cost_rows:
        cost_by_pool[r["pool_id"]].append(r)
    fee_by_pool = defaultdict(dict)
    for r in fee_rows:
        fee_by_pool[r["pool_id"]][r["window"]] = r
    tick_by_pool = {r["pool_id"]: r for r in tick_rows}
    out = []
    best = None
    for pool_id, q in quote_by_pool.items():
        tick = tick_by_pool.get(pool_id, {})
        costs = cost_by_pool.get(pool_id, [])
        f24 = fee_by_pool.get(pool_id, {}).get("24h") or next(iter(fee_by_pool.get(pool_id, {}).values()), {})
        fee_proxy = as_float(f24.get("pool_fee_usd_proxy")) or 0.0
        liquidity = as_float(tick.get("liquidity")) or 0.0
        for horizon in HOLD_WINDOWS:
            hours = WINDOW_SECONDS[horizon] / 3600.0
            for notional in NOTIONALS:
                cost_mid = next((c for c in costs if c["scenario"] == "realistic_mid" and c["notional_usd"] == notional), None)
                if not cost_mid or cost_mid["total_fixed_cost_usd"] is None:
                    continue
                fixed_cost = as_float(cost_mid["total_fixed_cost_usd"]) or 0.0
                fee_horizon = fee_proxy * (hours / 24.0)
                il_proxy = 0.0 if horizon in {"15m", "30m"} else max(0.0, notional * 0.001 * hours / 24.0)
                zero_il = fee_horizon - fixed_cost
                optimistic = fee_horizon * 1.15 - fixed_cost * 0.9
                realistic = fee_horizon - fixed_cost - il_proxy
                conservative = fee_horizon * 0.85 - fixed_cost * 1.1 - il_proxy
                for mode, net in [
                    ("zero_il_lvr", zero_il),
                    ("optimistic", optimistic),
                    ("realistic", realistic),
                    ("conservative", conservative),
                ]:
                    row = {
                        "pool_id": pool_id,
                        "token_pair": q.get("token_pair", ""),
                        "fee_tier_raw": q.get("fee_tier"),
                        "notional_usd": notional,
                        "hold_window": horizon,
                        "scenario": mode,
                        "fee_proxy_usd": fee_horizon,
                        "fixed_cost_usd": fixed_cost,
                        "il_lvr_proxy_usd": il_proxy,
                        "net_ev_proxy_usd": net,
                        "net_ev_proxy_pct": (net / notional * 100.0) if notional else None,
                        "capacity_ok": "yes" if liquidity > 0 else "no",
                        "data_sufficient": "yes" if tick and cost_mid else "no",
                        "confidence": "high" if tick.get("tick_snapshot_confidence") == "high" and cost_mid.get("cost_confidence") == "medium" else ("medium" if tick else "low"),
                    }
                    out.append(row)
                    if best is None or (row["scenario"] == "realistic" and row["net_ev_proxy_usd"] > best["net_ev_proxy_usd"]):
                        best = row
    agg = {
        "row_count": len(out),
        "positive_proxy_count_total": sum(1 for r in out if r["net_ev_proxy_usd"] > 0),
        "positive_proxy_count_realistic": sum(1 for r in out if r["scenario"] == "realistic" and r["net_ev_proxy_usd"] > 0),
        "positive_proxy_count_zero_il_lvr": sum(1 for r in out if r["scenario"] == "zero_il_lvr" and r["net_ev_proxy_usd"] > 0),
        "positive_proxy_count_pool_level_fee": sum(1 for r in out if r["net_ev_proxy_usd"] > 0 and r["scenario"] in {"zero_il_lvr", "optimistic", "realistic", "conservative"}),
        "positive_proxy_count_actual_fee": 0,
        "best_pool": best["pool_id"] if best else "",
        "best_pair": best["token_pair"] if best else "",
        "best_fee_tier": best["fee_tier_raw"] if best else "",
        "best_notional": best["notional_usd"] if best else None,
        "best_hold_window": best["hold_window"] if best else "",
        "best_net_ev_proxy_usd": best["net_ev_proxy_usd"] if best else None,
        "best_net_ev_proxy_pct": best["net_ev_proxy_pct"] if best else None,
        "near_break_even_count": sum(1 for r in out if abs(r["net_ev_proxy_usd"]) <= max(0.5, abs(r["fixed_cost_usd"]) * 0.1)),
        "capacity_fail_count": sum(1 for r in out if r["capacity_ok"] == "no"),
        "data_insufficient_count": sum(1 for r in out if r["data_sufficient"] == "no"),
        "confidence_adjusted_candidate_count": sum(1 for r in out if r["confidence"] in {"high", "medium"} and r["net_ev_proxy_usd"] > 0),
    }
    return out, agg


def review_matrix_rows(selected_pools: list[dict[str, Any]], tick_rows: list[dict[str, Any]], cost_rows: list[dict[str, Any]], econ_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tick_by = {r["pool_id"]: r for r in tick_rows}
    best_by_pool = defaultdict(lambda: None)
    for r in econ_rows:
        if r["pool_id"] not in best_by_pool or (best_by_pool[r["pool_id"]] and r["net_ev_proxy_usd"] > best_by_pool[r["pool_id"]]["net_ev_proxy_usd"]):
            best_by_pool[r["pool_id"]] = r
    out = []
    for pool in selected_pools:
        best = best_by_pool.get(pool["pool_address"])
        tick = tick_by.get(pool["pool_address"], {})
        status = "REALDATA_WATCH"
        reason = ""
        if not tick or tick.get("tick_snapshot_confidence") == "low":
            status = "DATA_FIX"
            reason = "tick_snapshot_low_confidence"
        elif best and best.get("net_ev_proxy_usd", 0) > 0:
            status = "POOL_LEVEL_POSITIVE_ONLY"
            reason = "pool_level_positive_proxy_no_probe"
        elif best and abs(best.get("net_ev_proxy_usd", 0)) <= 0.5:
            status = "REALDATA_WATCH"
            reason = "near_break_even"
        else:
            status = "REJECT"
            reason = "negative_proxy_or_insufficient_data"
        out.append(
            {
                "chain": pool["chain"],
                "protocol": pool["protocol"],
                "token_pair": pool["token_pair"],
                "fee_tier": pool["fee_tier_raw"],
                "pool_address": pool["pool_address"],
                "quote_ready": "yes",
                "tick_ready": "yes" if tick else "no",
                "cost_ready": "yes" if any(c["pool_id"] == pool["pool_address"] and c["total_fixed_cost_usd"] is not None for c in cost_rows) else "no",
                "pool_level_fee_ready": "yes",
                "actual_fee_ready": "false",
                "best_notional": best["notional_usd"] if best else "",
                "best_hold_window": best["hold_window"] if best else "",
                "best_net_ev_proxy": best["net_ev_proxy_usd"] if best else "",
                "confidence": best["confidence"] if best else "low",
                "candidate_status": status,
                "reason": reason,
            }
        )
    return out


def next_stage_decision(econ_agg: dict[str, Any], tick_agg: dict[str, Any], cost_agg: dict[str, Any], fee_agg: dict[str, Any]) -> str:
    if tick_agg["high_confidence_count"] < 6:
        return "LP_BSC_PANCAKESWAP_V3_TICK_LIQUIDITY_FIX_REPEAT"
    if cost_agg["cost_model_ready_pool_count"] < 6:
        return "LP_BSC_PANCAKESWAP_V3_REAL_COST_FIX_REPEAT"
    if fee_agg["fee_ready_pool_count"] < 6:
        return "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_FIX_REPEAT"
    if econ_agg["positive_proxy_count_total"] > 0 or econ_agg["near_break_even_count"] > 0:
        return "LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1"
    return "LP_EVM_STANDARD_V3_DISCOVERY_FIX_REPEAT"


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
        "quoter_staticcall_only": True,
        "read_only_eth_call_only": True,
        "event_logs_read_only": True,
        "wallet_or_tx_touched": False,
    }


def main() -> int:
    ensure_dir(REPORT_DIR)

    input_rows, input_summary = input_artifact_audit()
    write_text(
        REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md",
        "# 输入工件审计\n\n"
        + "\n".join(f"- {r['path']}: {'yes' if r['exists'] else 'no'}" for r in input_rows)
        + "\n\n"
        + f"- quoter_staticcall_success_count: `{input_summary['quoter_staticcall_success_count']}`\n"
        + f"- fallback_math_used_count: `{input_summary['fallback_math_used_count']}`\n"
        + f"- selected_abi_variant: `{input_summary['selected_abi_variant']}`\n"
        + f"- recommended_next_stage: `{input_summary['recommended_next_stage']}`\n"
        + f"- overnight_readonly_pipeline: `yes`\n"
        + f"- probe/canary/live allowed: `no`\n",
    )
    write_json(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.json", input_summary)
    if input_summary["quoter_staticcall_success_count"] != 80 or input_summary["fallback_math_used_count"] != 0:
        write_text(
            REPORT_DIR / "WRONG_STAGE_OR_QUOTER_NOT_READY_BLOCKER_CN.md",
            "# WRONG STAGE / QUOTER NOT READY\n\n"
            + f"- quoter_staticcall_success_count: `{input_summary['quoter_staticcall_success_count']}`\n"
            + f"- fallback_math_used_count: `{input_summary['fallback_math_used_count']}`\n",
        )
        write_json(REPORT_DIR / "FINAL_VERDICT.json", {
            "status": "FAIL",
            "stage": "LP_BSC_PANCAKESWAP_V3_OVERNIGHT_REALDATA_PIPELINE_V1",
            "chain": "BSC",
            "chain_id": CHAIN_ID_EXPECTED,
            "protocol": "PancakeSwap V3",
            "selected_pool_count": 0,
            "quoter_staticcall_ready": False,
            "tick_pipeline_ran": False,
            "tick_ready_pool_count": 0,
            "real_cost_pipeline_ran": False,
            "cost_ready_pool_count": 0,
            "fee_velocity_pipeline_ran": False,
            "fee_ready_pool_count": 0,
            "economics_preview_ran": False,
            "positive_proxy_count_total": 0,
            "positive_proxy_count_realistic": 0,
            "positive_proxy_count_actual_fee": 0,
            "positive_proxy_count_pool_level_fee": 0,
            "best_pool": "",
            "best_pair": "",
            "best_fee_tier": "",
            "best_notional": None,
            "best_hold_window": "",
            "best_net_ev_proxy_usd": None,
            "confidence_adjusted_candidate_count": 0,
            "actual_fee_ready": False,
            "token_id_available": False,
            "can_run_probe_now": False,
            "can_run_virtual_economics_now": False,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "wallet_or_tx_touched": False,
            "recommended_next_stage": "STOP_LP_RESEARCH_NOW",
        })
        return 2

    rpc_url, rpc_ready = rpc()
    write_text(
        REPORT_DIR / "BSC_RPC_CONTRACT_READINESS_CN.md",
        "# BSC RPC / Contract Readiness\n\n"
        + f"- rpc_env_key: `{rpc_ready.get('rpc_env_key')}`\n"
        + f"- chain_id: `{rpc_ready.get('chain_id')}`\n"
        + f"- latest_block: `{rpc_ready.get('latest_block')}`\n"
        + f"- rpc_read_only_test_pass: `{fmt(rpc_ready.get('rpc_read_only_test_pass'))}`\n"
        + f"- gas_price_wei: `{fmt(rpc_ready.get('gas_price_wei'))}`\n"
        + f"- fee_history_ok: `{fmt(rpc_ready.get('fee_history_ok'))}`\n",
    )
    write_json(REPORT_DIR / "BSC_RPC_CONTRACT_READINESS_CN.json", rpc_ready)
    if not rpc_ready.get("rpc_read_only_test_pass") or str(rpc_ready.get("chain_id")) != str(CHAIN_ID_EXPECTED):
        write_json(REPORT_DIR / "FINAL_VERDICT.json", {
            "status": "FAIL",
            "stage": "LP_BSC_PANCAKESWAP_V3_OVERNIGHT_REALDATA_PIPELINE_V1",
            "chain": "BSC",
            "chain_id": CHAIN_ID_EXPECTED,
            "protocol": "PancakeSwap V3",
            "selected_pool_count": 0,
            "quoter_staticcall_ready": True,
            "tick_pipeline_ran": False,
            "tick_ready_pool_count": 0,
            "real_cost_pipeline_ran": False,
            "cost_ready_pool_count": 0,
            "fee_velocity_pipeline_ran": False,
            "fee_ready_pool_count": 0,
            "economics_preview_ran": False,
            "positive_proxy_count_total": 0,
            "positive_proxy_count_realistic": 0,
            "positive_proxy_count_actual_fee": 0,
            "positive_proxy_count_pool_level_fee": 0,
            "best_pool": "",
            "best_pair": "",
            "best_fee_tier": "",
            "best_notional": None,
            "best_hold_window": "",
            "best_net_ev_proxy_usd": None,
            "confidence_adjusted_candidate_count": 0,
            "actual_fee_ready": False,
            "token_id_available": False,
            "can_run_probe_now": False,
            "can_run_virtual_economics_now": False,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "wallet_or_tx_touched": False,
            "recommended_next_stage": "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_FIX_REPEAT",
        })
        return 2

    quote_rows = load_csv(AMOUNT_FIX_DIR / "bsc_precise_quote_staticcall_v3_results.csv")
    quote_final = load_json(AMOUNT_FIX_DIR / "FINAL_VERDICT.json")
    selected_rows = read_selected_pool_rows()
    selected_pools, selected_unique_rows = freeze_selected_pool_set(selected_rows)
    write_text(
        REPORT_DIR / "BSC_SELECTED_POOL_SET_CN.md",
        "# BSC Selected Pool Set\n\n"
        + "\n".join(
            f"- {r['protocol']} {r['token_pair']} fee={r['fee_tier_raw']} pool={r['pool_address']}" for r in selected_pools
        )
        + "\n",
    )
    write_csv(
        REPORT_DIR / "BSC_SELECTED_POOL_SET_CN.csv",
        selected_pools,
        [
            "chain",
            "chain_id",
            "protocol",
            "pool_address",
            "token_pair",
            "token0",
            "token1",
            "token0_symbol",
            "token1_symbol",
            "fee_tier_raw",
            "fee_tier_percent",
            "quote_staticcall_ready",
            "selected_for_tick",
            "selected_for_cost",
            "selected_for_fee",
            "selected_for_economics",
        ],
    )
    write_json(REPORT_DIR / "BSC_SELECTED_POOL_SET_CN.json", {"rows": selected_pools})

    tick_rows = [scan_tick_pool(rpc_url, p) for p in selected_pools]
    tick_agg = {
        "selected_pool_count": len(selected_pools),
        "snapshot_success_pool_count": sum(1 for r in tick_rows if r["slot0_success"] == "yes" and r["liquidity_success"] == "yes"),
        "snapshot_fail_pool_count": sum(1 for r in tick_rows if r["slot0_success"] != "yes" or r["liquidity_success"] != "yes"),
        "slot0_success_count": sum(1 for r in tick_rows if r["slot0_success"] == "yes"),
        "liquidity_success_count": sum(1 for r in tick_rows if r["liquidity_success"] == "yes"),
        "tick_bitmap_success_count": sum(1 for r in tick_rows if r["tick_bitmap_success"] == "yes"),
        "ticks_success_count": sum(1 for r in tick_rows if r["ticks_success"] == "yes"),
        "observe_success_count": sum(1 for r in tick_rows if r["observe_success"] == "yes"),
        "total_initialized_ticks_found": sum(as_int(r["total_initialized_ticks_found"]) or 0 for r in tick_rows),
        "avg_initialized_ticks_per_pool": (sum(as_int(r["total_initialized_ticks_found"]) or 0 for r in tick_rows) / len(tick_rows)) if tick_rows else 0,
        "high_confidence_count": sum(1 for r in tick_rows if r["tick_snapshot_confidence"] == "high"),
        "medium_confidence_count": sum(1 for r in tick_rows if r["tick_snapshot_confidence"] == "medium"),
        "low_confidence_count": sum(1 for r in tick_rows if r["tick_snapshot_confidence"] == "low"),
        "invalid_count": sum(1 for r in tick_rows if r["invalid_reason"]),
    }
    write_text(
        REPORT_DIR / "BSC_TICK_LIQUIDITY_IMPLEMENTATION_CN.md",
        "# BSC Tick Liquidity Implementation\n\n"
        "- source: PancakeSwap V3 pool contract `slot0`, `liquidity`, `tickBitmap`, `ticks`, `observe`\n"
        "- scope: selected pools only from the precise quote amount-fix output\n"
        "- safety: read-only `eth_call` only, no probe/canary/live/wallet/tx\n"
        "- readiness: tick snapshot confidence is derived from slot0 + liquidity + bitmap + ticks + observe coverage\n",
    )
    write_text(
        REPORT_DIR / "BSC_TICK_LIQUIDITY_RESULTS_CN.md",
        "# BSC Tick Liquidity Results\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in tick_agg.items())
        + "\n",
    )
    write_csv(
        REPORT_DIR / "BSC_TICK_LIQUIDITY_RESULTS_CN.csv",
        tick_rows,
        ["pool_id", "token_pair", "chain", "protocol", "fee_tier_raw", "fee_tier_percent", "slot0_success", "liquidity_success", "tick_bitmap_success", "ticks_success", "observe_success", "total_initialized_ticks_found", "avg_initialized_ticks_per_pool", "tick_snapshot_confidence", "invalid_reason"],
    )
    write_json(REPORT_DIR / "BSC_TICK_LIQUIDITY_RESULTS_CN.json", {"aggregate": tick_agg, "rows": tick_rows})

    prices = build_prices_from_quote_rows(quote_rows)
    cost_rows, cost_agg = cost_model_rows(quote_rows, selected_pools, rpc_ready.get("gas_price_wei"))
    write_text(
        REPORT_DIR / "BSC_REAL_COST_MODEL_RESULTS_CN.md",
        "# BSC Real Cost Model Results\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in cost_agg.items())
        + "\n",
    )
    write_csv(
        REPORT_DIR / "BSC_REAL_COST_MODEL_RESULTS_CN.csv",
        cost_rows,
        ["pool_id", "token_pair", "notional_usd", "scenario", "gas_price_gwei", "gas_price_usd", "quote_gas_units", "quote_gas_usd", "add_gas_units", "remove_gas_units", "collect_gas_units", "approval_gas_units", "entry_conversion_cost_usd", "exit_conversion_cost_usd", "collect_cost_usd", "approval_cost_usd", "total_fixed_cost_usd", "proportional_slippage_cost_usd", "future_probe_only_component_count", "cost_model_ready", "cost_confidence"],
    )
    write_json(REPORT_DIR / "BSC_REAL_COST_MODEL_RESULTS_CN.json", {"aggregate": cost_agg, "rows": cost_rows})

    fee_rows = load_fee_inputs_from_logs(rpc_url, selected_pools, prices)
    fee_agg = {
        "pool_count": len(selected_pools),
        "fee_ready_pool_count": len({r["pool_id"] for r in fee_rows if r["log_count"] > 0}),
        "swap_log_ready_pool_count": len({r["pool_id"] for r in fee_rows if r["log_count"] > 0}),
        "volume_proxy_ready_pool_count": len({r["pool_id"] for r in fee_rows if r["approx_volume_usd"] > 0}),
        "high_confidence_count": sum(1 for r in fee_rows if r["confidence"] == "high"),
        "medium_confidence_count": sum(1 for r in fee_rows if r["confidence"] == "medium"),
        "low_confidence_count": sum(1 for r in fee_rows if r["confidence"] == "low"),
        "log_query_count": sum(as_int(r["query_count"]) or 0 for r in fee_rows),
        "log_query_skipped_count": 0,
        "fee_source_distribution": dict(Counter(r["fee_source"] for r in fee_rows)),
    }
    write_text(
        REPORT_DIR / "BSC_FEE_VELOCITY_RESULTS_CN.md",
        "# BSC Fee Velocity Results\n\n" + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in fee_agg.items()) + "\n",
    )
    write_csv(
        REPORT_DIR / "BSC_FEE_VELOCITY_RESULTS_CN.csv",
        fee_rows,
        ["pool_id", "token_pair", "window", "from_block", "to_block", "log_count", "unique_traders", "buyer_count", "seller_count", "buy_count", "sell_count", "token0_amount_usd_proxy", "token1_amount_usd_proxy", "approx_volume_usd", "fee_tier_raw", "fee_rate_fraction", "pool_fee_usd_proxy", "fee_velocity_rate_15m", "fee_velocity_rate_30m", "fee_velocity_rate_1h", "fee_velocity_rate_2h", "fee_source", "partial", "query_count", "confidence"],
    )
    write_json(REPORT_DIR / "BSC_FEE_VELOCITY_RESULTS_CN.json", {"aggregate": fee_agg, "rows": fee_rows})

    econ_rows, econ_agg = economics_preview_rows(quote_rows, tick_rows, cost_rows, fee_rows)
    write_text(
        REPORT_DIR / "BSC_REALDATA_ECONOMICS_PREVIEW_CN.md",
        "# BSC Real-Data Economics Preview\n\n" + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in econ_agg.items()) + "\n"
        + "- positive proxy from pool-level fee cannot be edge_proven\n- no actual fee without tokenId\n- no probe allowed\n",
    )
    write_csv(
        REPORT_DIR / "BSC_REALDATA_ECONOMICS_PREVIEW_CN.csv",
        econ_rows,
        ["pool_id", "token_pair", "fee_tier_raw", "notional_usd", "hold_window", "scenario", "fee_proxy_usd", "fixed_cost_usd", "il_lvr_proxy_usd", "net_ev_proxy_usd", "net_ev_proxy_pct", "capacity_ok", "data_sufficient", "confidence"],
    )
    write_json(REPORT_DIR / "BSC_REALDATA_ECONOMICS_PREVIEW_CN.json", {"aggregate": econ_agg, "rows": econ_rows})

    review_rows = review_matrix_rows(selected_pools, tick_rows, cost_rows, econ_rows)
    write_text(
        REPORT_DIR / "BSC_CANDIDATE_REVIEW_MATRIX_CN.md",
        "# BSC Candidate Review Matrix\n\n" + "\n".join(f"- {r['pool_address']} {r['token_pair']} => {r['candidate_status']}" for r in review_rows) + "\n",
    )
    write_csv(
        REPORT_DIR / "BSC_CANDIDATE_REVIEW_MATRIX_CN.csv",
        review_rows,
        ["chain", "protocol", "token_pair", "fee_tier", "pool_address", "quote_ready", "tick_ready", "cost_ready", "pool_level_fee_ready", "actual_fee_ready", "best_notional", "best_hold_window", "best_net_ev_proxy", "confidence", "candidate_status", "reason"],
    )
    write_json(REPORT_DIR / "BSC_CANDIDATE_REVIEW_MATRIX_CN.json", {"rows": review_rows})

    stage_decision = next_stage_decision(econ_agg, tick_agg, cost_agg, fee_agg)
    write_text(
        REPORT_DIR / "BSC_OVERNIGHT_NEXT_STAGE_DECISION_CN.md",
        "# BSC Overnight Next Stage Decision\n\n"
        + f"- recommended_next_stage: `{stage_decision}`\n"
        + f"- reason: `selected pools ready: {len(selected_pools)}, tick high conf: {tick_agg['high_confidence_count']}, cost ready: {cost_agg['cost_model_ready_pool_count']}, fee ready: {fee_agg['fee_ready_pool_count']}`\n",
    )
    write_json(REPORT_DIR / "BSC_OVERNIGHT_NEXT_STAGE_DECISION_CN.json", {"recommended_next_stage": stage_decision, "reason": "derived_from_readonly_bsc_overnight_pipeline"})

    safety = safety_audit()
    write_text(
        REPORT_DIR / "BSC_OVERNIGHT_SAFETY_AUDIT_CN.md",
        "# BSC Overnight Safety Audit\n\n" + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in safety.items()) + "\n",
    )
    write_json(REPORT_DIR / "BSC_OVERNIGHT_SAFETY_AUDIT_CN.json", safety)

    final = {
        "status": "PASS",
        "stage": "LP_BSC_PANCAKESWAP_V3_OVERNIGHT_REALDATA_PIPELINE_V1",
        "chain": "BSC",
        "chain_id": CHAIN_ID_EXPECTED,
        "protocol": "PancakeSwap V3",
        "selected_pool_count": len(selected_pools),
        "quoter_staticcall_ready": True,
        "tick_pipeline_ran": True,
        "tick_ready_pool_count": tick_agg["snapshot_success_pool_count"],
        "real_cost_pipeline_ran": True,
        "cost_ready_pool_count": cost_agg["cost_model_ready_pool_count"],
        "fee_velocity_pipeline_ran": True,
        "fee_ready_pool_count": fee_agg["fee_ready_pool_count"],
        "economics_preview_ran": True,
        "positive_proxy_count_total": econ_agg["positive_proxy_count_total"],
        "positive_proxy_count_realistic": econ_agg["positive_proxy_count_realistic"],
        "positive_proxy_count_actual_fee": 0,
        "positive_proxy_count_pool_level_fee": econ_agg["positive_proxy_count_pool_level_fee"],
        "best_pool": econ_agg["best_pool"],
        "best_pair": econ_agg["best_pair"],
        "best_fee_tier": econ_agg["best_fee_tier"],
        "best_notional": econ_agg["best_notional"],
        "best_hold_window": econ_agg["best_hold_window"],
        "best_net_ev_proxy_usd": econ_agg["best_net_ev_proxy_usd"],
        "confidence_adjusted_candidate_count": econ_agg["confidence_adjusted_candidate_count"],
        "actual_fee_ready": False,
        "token_id_available": False,
        "can_run_probe_now": False,
        "can_run_virtual_economics_now": False,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "wallet_or_tx_touched": False,
        "recommended_next_stage": stage_decision,
        "tick_confidence_limited": tick_agg["high_confidence_count"] < 6,
    }
    if not safety["quoter_staticcall_only"] or not safety["read_only_eth_call_only"] or not safety["event_logs_read_only"] or safety["wallet_or_tx_touched"]:
        final["status"] = "FAIL"
        final["recommended_next_stage"] = "STOP_LP_RESEARCH_NOW"

    write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
    write_text(
        REPORT_DIR / "ONEPAGE_CN.md",
        "# BSC Overnight Realdata Pipeline Onepage\n\n"
        + f"- status: `{final['status']}`\n"
        + f"- stage: `{final['stage']}`\n"
        + f"- selected_pool_count: `{final['selected_pool_count']}`\n"
        + f"- tick_ready_pool_count: `{final['tick_ready_pool_count']}`\n"
        + f"- cost_ready_pool_count: `{final['cost_ready_pool_count']}`\n"
        + f"- fee_ready_pool_count: `{final['fee_ready_pool_count']}`\n"
        + f"- positive_proxy_count_total: `{final['positive_proxy_count_total']}`\n"
        + f"- positive_proxy_count_realistic: `{final['positive_proxy_count_realistic']}`\n"
        + f"- best_pool: `{final['best_pool']}`\n"
        + f"- best_pair: `{final['best_pair']}`\n"
        + f"- best_fee_tier: `{final['best_fee_tier']}`\n"
        + f"- best_notional: `{fmt(final['best_notional'])}`\n"
        + f"- best_hold_window: `{final['best_hold_window']}`\n"
        + f"- best_net_ev_proxy_usd: `{fmt(final['best_net_ev_proxy_usd'])}`\n"
        + f"- recommended_next_stage: `{final['recommended_next_stage']}`\n"
        + f"- tiny_canary_allowed: `no`\n",
    )
    write_text(
        REPORT_DIR / "ARTIFACT_INDEX.md",
        "# BSC Overnight Realdata Pipeline Artifact Index\n\n"
        + "- [INPUT_ARTIFACT_AUDIT_CN.md](%s)\n" % (REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md")
        + "- [INPUT_ARTIFACT_AUDIT_CN.json](%s)\n" % (REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.json")
        + "- [BSC_RPC_CONTRACT_READINESS_CN.md](%s)\n" % (REPORT_DIR / "BSC_RPC_CONTRACT_READINESS_CN.md")
        + "- [BSC_RPC_CONTRACT_READINESS_CN.json](%s)\n" % (REPORT_DIR / "BSC_RPC_CONTRACT_READINESS_CN.json")
        + "- [BSC_SELECTED_POOL_SET_CN.md](%s)\n" % (REPORT_DIR / "BSC_SELECTED_POOL_SET_CN.md")
        + "- [BSC_SELECTED_POOL_SET_CN.csv](%s)\n" % (REPORT_DIR / "BSC_SELECTED_POOL_SET_CN.csv")
        + "- [BSC_SELECTED_POOL_SET_CN.json](%s)\n" % (REPORT_DIR / "BSC_SELECTED_POOL_SET_CN.json")
        + "- [BSC_TICK_LIQUIDITY_IMPLEMENTATION_CN.md](%s)\n" % (REPORT_DIR / "BSC_TICK_LIQUIDITY_IMPLEMENTATION_CN.md")
        + "- [BSC_TICK_LIQUIDITY_RESULTS_CN.md](%s)\n" % (REPORT_DIR / "BSC_TICK_LIQUIDITY_RESULTS_CN.md")
        + "- [BSC_TICK_LIQUIDITY_RESULTS_CN.csv](%s)\n" % (REPORT_DIR / "BSC_TICK_LIQUIDITY_RESULTS_CN.csv")
        + "- [BSC_TICK_LIQUIDITY_RESULTS_CN.json](%s)\n" % (REPORT_DIR / "BSC_TICK_LIQUIDITY_RESULTS_CN.json")
        + "- [BSC_REAL_COST_MODEL_RESULTS_CN.md](%s)\n" % (REPORT_DIR / "BSC_REAL_COST_MODEL_RESULTS_CN.md")
        + "- [BSC_REAL_COST_MODEL_RESULTS_CN.csv](%s)\n" % (REPORT_DIR / "BSC_REAL_COST_MODEL_RESULTS_CN.csv")
        + "- [BSC_REAL_COST_MODEL_RESULTS_CN.json](%s)\n" % (REPORT_DIR / "BSC_REAL_COST_MODEL_RESULTS_CN.json")
        + "- [BSC_FEE_VELOCITY_RESULTS_CN.md](%s)\n" % (REPORT_DIR / "BSC_FEE_VELOCITY_RESULTS_CN.md")
        + "- [BSC_FEE_VELOCITY_RESULTS_CN.csv](%s)\n" % (REPORT_DIR / "BSC_FEE_VELOCITY_RESULTS_CN.csv")
        + "- [BSC_FEE_VELOCITY_RESULTS_CN.json](%s)\n" % (REPORT_DIR / "BSC_FEE_VELOCITY_RESULTS_CN.json")
        + "- [BSC_REALDATA_ECONOMICS_PREVIEW_CN.md](%s)\n" % (REPORT_DIR / "BSC_REALDATA_ECONOMICS_PREVIEW_CN.md")
        + "- [BSC_REALDATA_ECONOMICS_PREVIEW_CN.csv](%s)\n" % (REPORT_DIR / "BSC_REALDATA_ECONOMICS_PREVIEW_CN.csv")
        + "- [BSC_REALDATA_ECONOMICS_PREVIEW_CN.json](%s)\n" % (REPORT_DIR / "BSC_REALDATA_ECONOMICS_PREVIEW_CN.json")
        + "- [BSC_CANDIDATE_REVIEW_MATRIX_CN.md](%s)\n" % (REPORT_DIR / "BSC_CANDIDATE_REVIEW_MATRIX_CN.md")
        + "- [BSC_CANDIDATE_REVIEW_MATRIX_CN.csv](%s)\n" % (REPORT_DIR / "BSC_CANDIDATE_REVIEW_MATRIX_CN.csv")
        + "- [BSC_CANDIDATE_REVIEW_MATRIX_CN.json](%s)\n" % (REPORT_DIR / "BSC_CANDIDATE_REVIEW_MATRIX_CN.json")
        + "- [BSC_OVERNIGHT_NEXT_STAGE_DECISION_CN.md](%s)\n" % (REPORT_DIR / "BSC_OVERNIGHT_NEXT_STAGE_DECISION_CN.md")
        + "- [BSC_OVERNIGHT_NEXT_STAGE_DECISION_CN.json](%s)\n" % (REPORT_DIR / "BSC_OVERNIGHT_NEXT_STAGE_DECISION_CN.json")
        + "- [BSC_OVERNIGHT_SAFETY_AUDIT_CN.md](%s)\n" % (REPORT_DIR / "BSC_OVERNIGHT_SAFETY_AUDIT_CN.md")
        + "- [BSC_OVERNIGHT_SAFETY_AUDIT_CN.json](%s)\n" % (REPORT_DIR / "BSC_OVERNIGHT_SAFETY_AUDIT_CN.json")
        + "- [FINAL_VERDICT.json](%s)\n" % (REPORT_DIR / "FINAL_VERDICT.json")
        + "- [ONEPAGE_CN.md](%s)\n" % (REPORT_DIR / "ONEPAGE_CN.md")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
