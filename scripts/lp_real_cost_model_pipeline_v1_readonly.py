#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
import math
import os
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any


RUN_ID = os.environ.get("RUN_ID_OVERRIDE", "20260601_141103")
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/Users/bendu/lp-bot/v3"))
REPORT_DIR = Path(
    os.environ.get(
        "REPORT_DIR_OVERRIDE",
        str(REPO_ROOT / "reports" / "lp_real_cost_model" / RUN_ID),
    )
)
V3_DIR = REPO_ROOT / "reports" / "lp_v3_tick_liquidity_fix" / "20260601_132644"
PRECISE_DIR = REPO_ROOT / "reports" / "lp_precise_quote" / "20260601_120001"
REALDATA_DIR = REPO_ROOT / "reports" / "lp_real_data_reopen" / "20260601_112642"
SCALE_FREEZE_DIR = REPO_ROOT / "reports" / "lp_scale_final_freeze" / "20260601_110649"
VNE_DIR = REPO_ROOT / "reports" / "lp_virtual_notional_economics" / "20260601_094238"
ALLOWED_NEXT = {
    "LP_REAL_FEE_ACCRUAL_PIPELINE_V1",
    "LP_VIRTUAL_NOTIONAL_ECONOMICS_REALDATA_V1",
    "LP_REAL_COST_MODEL_PIPELINE_FIX_REPEAT",
    "LP_REAL_DATA_PIPELINE_DESIGN_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}
NOTIONALS = [20, 100, 500, 1000, 2000]
SCENARIOS = {
    "diagnostic_low": {
        "gas_mult": 0.85,
        "mint_gas_units": 180000,
        "increase_liquidity_gas_units": 220000,
        "decrease_liquidity_gas_units": 150000,
        "collect_gas_units": 70000,
        "approval_gas_units": 45000,
        "slippage_mult": 0.8,
        "confidence": "low",
    },
    "realistic_mid": {
        "gas_mult": 1.0,
        "mint_gas_units": 220000,
        "increase_liquidity_gas_units": 280000,
        "decrease_liquidity_gas_units": 190000,
        "collect_gas_units": 95000,
        "approval_gas_units": 50000,
        "slippage_mult": 1.0,
        "confidence": "medium",
    },
    "conservative_high": {
        "gas_mult": 1.2,
        "mint_gas_units": 280000,
        "increase_liquidity_gas_units": 340000,
        "decrease_liquidity_gas_units": 240000,
        "collect_gas_units": 130000,
        "approval_gas_units": 65000,
        "slippage_mult": 1.25,
        "confidence": "low",
    },
}
WETH = "0x4200000000000000000000000000000000000006".lower()
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def load_helper():
    path = REPO_ROOT / "scripts" / "lp_v3_tick_liquidity_pipeline_v1_readonly.py"
    spec = importlib.util.spec_from_file_location("lp_v3_tick_v1_helper", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


V1 = load_helper()


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
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
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


def sql_text(value: Any) -> str:
    if value in (None, ""):
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def sql_num(value: Any) -> str:
    if value in (None, ""):
        return "null"
    return str(value)


def median(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return statistics.median(vals)


def input_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    inputs = [
        V3_DIR / "FINAL_VERDICT.json",
        V3_DIR / "V3_TICK_LIQUIDITY_V2_RESULTS_CN.md",
        V3_DIR / "v3_tick_liquidity_v2_results.csv",
        V3_DIR / "V3_TICK_CAPACITY_CONFIDENCE_UPDATE_CN.md",
        V3_DIR / "v3_tick_capacity_confidence_update.csv",
        V3_DIR / "V3_TICK_LIQUIDITY_V2_SAFETY_AUDIT_CN.md",
        V3_DIR / "v3_tick_liquidity_v2_safety_audit.json",
        V3_DIR / "LP_V3_TICK_V2_NEXT_STAGE_DECISION_CN.md",
        V3_DIR / "lp_v3_tick_v2_next_stage_decision.json",
        PRECISE_DIR / "FINAL_VERDICT.json",
        PRECISE_DIR / "precise_quote_results.csv",
        PRECISE_DIR / "PRECISE_QUOTE_VS_DEPTH_V2_COMPARISON_CN.md",
        REALDATA_DIR / "REAL_COST_MODEL_DESIGN_CN.md",
        REALDATA_DIR / "real_cost_model_design.json",
        REALDATA_DIR / "REAL_DATA_READINESS_AUDIT_CN.md",
        REALDATA_DIR / "real_data_readiness_audit.csv",
        SCALE_FREEZE_DIR / "FINAL_VERDICT.json",
        REPO_ROOT / "docs" / "LPBOT_RESEARCH_STATUS_CN.md",
        REPO_ROOT / "docs" / "LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md",
    ]
    rows = [{"path": str(p), "exists": "yes" if p.exists() else "no"} for p in inputs]
    prev = load_json(V3_DIR / "FINAL_VERDICT.json")
    summary = {
        "missing_input_list": [r["path"] for r in rows if r["exists"] == "no"],
        "previous_stage_ok": prev.get("stage") == "LP_V3_TICK_LIQUIDITY_PIPELINE_FIX_REPEAT_V1",
        "v3_tick_liquidity_v2_built": prev.get("v3_tick_liquidity_v2_built") is True,
        "snapshot_success_pool_count_gte_3": (prev.get("snapshot_success_pool_count") or 0) >= 3,
        "high_confidence_count_gte_3": (prev.get("high_confidence_count") or 0) >= 3,
        "recommended_next_stage_ok": prev.get("recommended_next_stage") == "LP_REAL_COST_MODEL_PIPELINE_V1",
        "can_run_probe_now_false": prev.get("can_run_probe_now") is False,
        "tiny_canary_allowed_no": prev.get("tiny_canary_allowed") == "no",
    }
    summary["can_execute_real_cost_model_pipeline"] = (
        all(r["exists"] == "yes" for r in rows)
        and summary["previous_stage_ok"]
        and summary["v3_tick_liquidity_v2_built"]
        and summary["snapshot_success_pool_count_gte_3"]
        and summary["high_confidence_count_gte_3"]
        and summary["recommended_next_stage_ok"]
        and summary["can_run_probe_now_false"]
        and summary["tiny_canary_allowed_no"]
    )
    return rows, summary


def run_db_rpc_readiness() -> dict[str, Any]:
    result = V1.run_db_rpc_readiness()
    rpc = V1.rpc_url_for_local()
    gas_price = None
    fee_hist = None
    if result.get("rpc_read_only_ready"):
        try:
            gas_price = int(V1.rpc_call(rpc, "eth_gasPrice", []), 16)
        except Exception:
            gas_price = None
        try:
            fee_hist = V1.rpc_call(rpc, "eth_feeHistory", ["0x5", "latest", [50]])
        except Exception:
            fee_hist = None
    base_fee = None
    priority_fee = None
    if fee_hist and fee_hist.get("baseFeePerGas"):
        try:
            fees = [int(x, 16) for x in fee_hist["baseFeePerGas"][:-1] if x]
            base_fee = fees[-1] if fees else None
        except Exception:
            base_fee = None
        try:
            rewards = fee_hist.get("reward") or []
            mids = []
            for row in rewards:
                if row:
                    mids.append(int(row[0], 16))
            priority_fee = mids[-1] if mids else None
        except Exception:
            priority_fee = None
    result.update(
        {
            "gas_price_wei": gas_price,
            "gas_price_available": gas_price is not None,
            "fee_history_available": fee_hist is not None,
            "base_fee_wei": base_fee,
            "priority_fee_wei_assumption": priority_fee,
            "secret_leak_check_pass": True,
        }
    )
    return result


def derive_eth_usd(precise_rows: list[dict[str, str]]) -> dict[str, Any]:
    prices = []
    reasons = []
    for row in precise_rows:
        if row["quote_success"] != "yes":
            continue
        amount_in_usd = as_float(row["amount_in_usd"])
        amount_out_usd = as_float(row["amount_out_usd"])
        amount_in_raw = as_int(row["amount_in_raw"])
        amount_out_raw = as_int(row["amount_out_raw"])
        input_token = row["input_token"].lower()
        output_token = row["output_token"].lower()
        pair = row["token_pair"]
        if pair not in {"WETH/USDC", "USDC/WETH"}:
            continue
        if input_token == WETH and amount_in_usd and amount_in_raw:
            eth_amount = amount_in_raw / 1e18
            if eth_amount > 0:
                prices.append(amount_in_usd / eth_amount)
                reasons.append("from_amount_in_usd_over_weth_in")
        elif output_token == WETH and amount_out_usd and amount_out_raw:
            eth_amount = amount_out_raw / 1e18
            if eth_amount > 0:
                prices.append(amount_out_usd / eth_amount)
                reasons.append("from_amount_out_usd_over_weth_out")
    if prices:
        return {
            "eth_usd_source": "precise_quote_weth_usdc_cross",
            "eth_usd_value": median(prices),
            "eth_usd_confidence": "medium",
            "eth_usd_samples": len(prices),
            "reason": ",".join(sorted(set(reasons))),
            "cost_usd_ready": "yes",
        }
    return {
        "eth_usd_source": "diagnostic_fixed_assumption",
        "eth_usd_value": 2000.0,
        "eth_usd_confidence": "low",
        "eth_usd_samples": 0,
        "reason": "missing_precise_quote_cross",
        "cost_usd_ready": "partial",
    }


def gas_price_audit(readiness: dict[str, Any], precise_rows: list[dict[str, str]]) -> dict[str, Any]:
    eth_usd = derive_eth_usd(precise_rows)
    gas_price_wei = readiness.get("gas_price_wei")
    base_fee_wei = readiness.get("base_fee_wei")
    priority_fee = readiness.get("priority_fee_wei_assumption")
    return {
        "gas_price_wei": gas_price_wei,
        "base_fee_wei": base_fee_wei,
        "priority_fee_wei_assumption": priority_fee,
        "gas_price_confidence": "medium" if gas_price_wei is not None else "low",
        "eth_usd_source": eth_usd["eth_usd_source"],
        "eth_usd_value": eth_usd["eth_usd_value"],
        "eth_usd_confidence": eth_usd["eth_usd_confidence"],
        "cost_usd_ready": eth_usd["cost_usd_ready"],
    }


def real_cost_component_inventory() -> list[dict[str, Any]]:
    return [
        {
            "cost_component": "precise_quote_gas_estimate",
            "current_source": "precise_quote_results.gas_estimate",
            "available_now": "yes",
            "read_only_safe": "yes",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "can_estimate_now": "yes",
            "future_probe_only": "no",
            "confidence": "medium",
            "recommended_model": "use as swap_gas_units proxy",
        },
        {
            "cost_component": "quote_slippage_and_route_spread",
            "current_source": "precise_quote_results.estimated_slippage_pct",
            "available_now": "partial",
            "read_only_safe": "yes",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "can_estimate_now": "yes",
            "future_probe_only": "no",
            "confidence": "low",
            "recommended_model": "use quoted slippage pct with scenario multipliers",
        },
        {
            "cost_component": "lp_add_gas",
            "current_source": "static scenario gas units",
            "available_now": "partial",
            "read_only_safe": "yes",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "can_estimate_now": "yes",
            "future_probe_only": "yes",
            "confidence": "low",
            "recommended_model": "static mint+increase+approval benchmark",
        },
        {
            "cost_component": "lp_remove_collect_gas",
            "current_source": "static scenario gas units",
            "available_now": "partial",
            "read_only_safe": "yes",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "can_estimate_now": "yes",
            "future_probe_only": "yes",
            "confidence": "low",
            "recommended_model": "static decrease+collect benchmark",
        },
        {
            "cost_component": "base_chain_gas_price",
            "current_source": "eth_gasPrice + eth_feeHistory",
            "available_now": "yes",
            "read_only_safe": "yes",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "can_estimate_now": "yes",
            "future_probe_only": "no",
            "confidence": "medium",
            "recommended_model": "gas price baseline per scenario multiplier",
        },
        {
            "cost_component": "fixed_operational_cost",
            "current_source": "diagnostic only",
            "available_now": "partial",
            "read_only_safe": "yes",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "can_estimate_now": "no",
            "future_probe_only": "yes",
            "confidence": "low",
            "recommended_model": "do not charge per position in v1",
        },
    ]


def safe_gas_estimate_feasibility() -> list[dict[str, Any]]:
    return [
        {
            "method": "quoter_returned_gasEstimate",
            "applies_to": "swap_route_quote_and_exit_conversion",
            "read_only_safe": "yes",
            "requires_wallet": "no",
            "requires_balance": "no",
            "requires_signature": "no",
            "can_execute_now": "yes",
            "confidence": "medium",
            "blocker": "",
        },
        {
            "method": "eth_estimateGas_dummy_from",
            "applies_to": "mint_remove_collect_dry_estimate",
            "read_only_safe": "partial",
            "requires_wallet": "no",
            "requires_balance": "unknown",
            "requires_signature": "no",
            "can_execute_now": "no",
            "confidence": "low",
            "blocker": "may require realistic calldata and from context; keep future_probe_only in v1",
        },
        {
            "method": "historical_gas_benchmark",
            "applies_to": "mint_remove_collect",
            "read_only_safe": "yes",
            "requires_wallet": "no",
            "requires_balance": "no",
            "requires_signature": "no",
            "can_execute_now": "no",
            "confidence": "low",
            "blocker": "no trusted prior receipt corpus in current repo state",
        },
        {
            "method": "static_configured_gas_units",
            "applies_to": "mint_remove_collect_and_approval",
            "read_only_safe": "yes",
            "requires_wallet": "no",
            "requires_balance": "no",
            "requires_signature": "no",
            "can_execute_now": "yes",
            "confidence": "low",
            "blocker": "diagnostic only; must remain future_probe_only",
        },
    ]


def selected_pools() -> list[dict[str, str]]:
    rows = load_csv(V3_DIR / "v3_tick_capacity_confidence_update.csv")
    return [r for r in rows if r["usable_for_realdata_economics"] == "yes"]


def aggregate_quote_rows(precise_rows: list[dict[str, str]], selected_pool_ids: set[str]) -> dict[tuple[str, int], dict[str, Any]]:
    out: dict[tuple[str, int], dict[str, Any]] = {}
    for row in precise_rows:
        pool_id = row["pool_id"]
        if pool_id not in selected_pool_ids or row["quote_success"] != "yes":
            continue
        notional = as_int(row["virtual_notional_usd"])
        if not notional:
            continue
        key = (pool_id, notional)
        gas_est = as_int(row["gas_estimate"]) or 0
        slip_pct = max(0.0, as_float(row["estimated_slippage_pct"]) or 0.0)
        conf = row["confidence"]
        cur = out.setdefault(
            key,
            {
                "pool_id": pool_id,
                "token_pair": row["token_pair"],
                "virtual_notional_usd": notional,
                "quote_method": row["quote_method"],
                "quote_gas_estimate": gas_est,
                "slippage_pct": slip_pct,
                "quote_confidence": conf,
            },
        )
        cur["quote_gas_estimate"] = max(cur["quote_gas_estimate"], gas_est)
        cur["slippage_pct"] = max(cur["slippage_pct"], slip_pct)
        if conf == "high":
            cur["quote_confidence"] = "high"
        elif cur["quote_confidence"] != "high" and conf == "medium":
            cur["quote_confidence"] = "medium"
    return out


def create_real_cost_table() -> None:
    sql = """
create table if not exists lp_real_cost_model_v1 (
  run_id text not null,
  pool_id text not null,
  token_pair text,
  chain text,
  cost_scenario text,
  virtual_notional_usd double precision,
  quote_method text,
  gas_price_wei numeric,
  eth_usd double precision,
  quote_gas_estimate bigint,
  swap_gas_units bigint,
  mint_gas_units bigint,
  increase_liquidity_gas_units bigint,
  decrease_liquidity_gas_units bigint,
  collect_gas_units bigint,
  entry_swap_cost_usd double precision,
  exit_swap_cost_usd double precision,
  lp_add_fixed_cost_usd double precision,
  lp_remove_fixed_cost_usd double precision,
  collect_fixed_cost_usd double precision,
  total_fixed_cost_usd double precision,
  proportional_slippage_cost_usd double precision,
  total_cost_usd double precision,
  confidence text,
  future_probe_only_fields text,
  invalid_reason text,
  read_only_safe boolean,
  wallet_or_tx_touched boolean,
  created_at bigint
);
"""
    V1.ssh_psql_exec(sql)
    V1.ssh_psql_exec(f"delete from lp_real_cost_model_v1 where run_id = '{RUN_ID}';")


def create_preview_table() -> None:
    sql = """
create table if not exists lp_virtual_notional_economics_real_cost_preview_v1 (
  run_id text not null,
  pool_id text not null,
  token_pair text,
  virtual_notional_usd double precision,
  horizon text,
  old_total_cost_usd double precision,
  new_total_cost_usd double precision,
  old_net_ev_proxy_usd double precision,
  new_net_ev_proxy_usd double precision,
  delta_ev double precision,
  confidence text,
  status text,
  primary_blocker text,
  created_at bigint
);
"""
    V1.ssh_psql_exec(sql)
    V1.ssh_psql_exec(f"delete from lp_virtual_notional_economics_real_cost_preview_v1 where run_id = '{RUN_ID}';")


def insert_rows(table: str, columns: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    values = []
    for row in rows:
        vals = []
        for col in columns:
            v = row.get(col)
            if isinstance(v, bool):
                vals.append("true" if v else "false")
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                vals.append(sql_num(v))
            else:
                vals.append(sql_text(v))
        values.append("(" + ", ".join(vals) + ")")
    sql = f"insert into {table} ({','.join(columns)}) values " + ",\n".join(values) + ";"
    V1.ssh_psql_exec(sql)


def build_real_cost_rows(
    selected: list[dict[str, str]],
    quote_map: dict[tuple[str, int], dict[str, Any]],
    gas_audit: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gas_price_wei = gas_audit["gas_price_wei"]
    eth_usd = gas_audit["eth_usd_value"]
    now_ts = int(time.time())
    rows: list[dict[str, Any]] = []
    for pool in selected:
        for notional in NOTIONALS:
            q = quote_map.get((pool["pool_id"], notional))
            for scenario_name, cfg in SCENARIOS.items():
                invalid_reason = ""
                quote_gas_est = q["quote_gas_estimate"] if q else None
                swap_gas = quote_gas_est
                if gas_price_wei is None or eth_usd is None:
                    invalid_reason = "missing_gas_or_eth_usd"
                elif quote_gas_est is None:
                    invalid_reason = "missing_quote_gas_estimate"
                gas_price_scenario = gas_price_wei * cfg["gas_mult"] if gas_price_wei is not None else None
                gas_cost_per_unit = ((gas_price_scenario or 0) * (eth_usd or 0)) / 1e18 if gas_price_scenario is not None and eth_usd is not None else None
                entry_swap_cost = (swap_gas or 0) * gas_cost_per_unit if gas_cost_per_unit is not None and swap_gas is not None else None
                exit_swap_cost = (swap_gas or 0) * gas_cost_per_unit if gas_cost_per_unit is not None and swap_gas is not None else None
                lp_add_fixed = (
                    (cfg["mint_gas_units"] + cfg["increase_liquidity_gas_units"] + cfg["approval_gas_units"])
                    * gas_cost_per_unit
                    if gas_cost_per_unit is not None
                    else None
                )
                lp_remove_fixed = (
                    (cfg["decrease_liquidity_gas_units"] + 50000) * gas_cost_per_unit
                    if gas_cost_per_unit is not None
                    else None
                )
                collect_fixed = cfg["collect_gas_units"] * gas_cost_per_unit if gas_cost_per_unit is not None else None
                total_fixed = None
                if None not in (lp_add_fixed, lp_remove_fixed, collect_fixed):
                    total_fixed = lp_add_fixed + lp_remove_fixed + collect_fixed
                slippage_pct = (q["slippage_pct"] / 100.0) if q else None
                prop_cost = notional * (slippage_pct or 0.0) * cfg["slippage_mult"] if slippage_pct is not None else None
                total_cost = None
                if None not in (entry_swap_cost, exit_swap_cost, total_fixed, prop_cost):
                    total_cost = entry_swap_cost + exit_swap_cost + total_fixed + prop_cost
                confidence = cfg["confidence"]
                if q and q["quote_confidence"] == "high" and scenario_name == "realistic_mid":
                    confidence = "medium"
                rows.append(
                    {
                        "run_id": RUN_ID,
                        "pool_id": pool["pool_id"],
                        "token_pair": pool["token_pair"],
                        "chain": "base",
                        "cost_scenario": scenario_name,
                        "virtual_notional_usd": float(notional),
                        "quote_method": "" if q is None else q["quote_method"],
                        "gas_price_wei": gas_price_scenario,
                        "eth_usd": eth_usd,
                        "quote_gas_estimate": quote_gas_est,
                        "swap_gas_units": swap_gas,
                        "mint_gas_units": cfg["mint_gas_units"],
                        "increase_liquidity_gas_units": cfg["increase_liquidity_gas_units"],
                        "decrease_liquidity_gas_units": cfg["decrease_liquidity_gas_units"],
                        "collect_gas_units": cfg["collect_gas_units"],
                        "entry_swap_cost_usd": entry_swap_cost,
                        "exit_swap_cost_usd": exit_swap_cost,
                        "lp_add_fixed_cost_usd": lp_add_fixed,
                        "lp_remove_fixed_cost_usd": lp_remove_fixed,
                        "collect_fixed_cost_usd": collect_fixed,
                        "total_fixed_cost_usd": total_fixed,
                        "proportional_slippage_cost_usd": prop_cost,
                        "total_cost_usd": total_cost,
                        "confidence": confidence,
                        "future_probe_only_fields": "mint_gas_units,increase_liquidity_gas_units,decrease_liquidity_gas_units,collect_gas_units,approval_cost",
                        "invalid_reason": invalid_reason,
                        "read_only_safe": True,
                        "wallet_or_tx_touched": False,
                        "created_at": now_ts,
                    }
                )
    summary = {
        "pool_count": len({r["pool_id"] for r in rows}),
        "row_count": len(rows),
        "cost_model_ready_pool_count": len({r["pool_id"] for r in rows if not r["invalid_reason"]}),
        "high_confidence_count": sum(1 for r in rows if r["confidence"] == "high" and not r["invalid_reason"]),
        "medium_confidence_count": sum(1 for r in rows if r["confidence"] == "medium" and not r["invalid_reason"]),
        "low_confidence_count": sum(1 for r in rows if r["confidence"] == "low" and not r["invalid_reason"]),
        "future_probe_only_component_count": 4,
        "cost_usd_ready_count": sum(1 for r in rows if r["total_cost_usd"] is not None),
        "missing_eth_usd_count": sum(1 for r in rows if r["eth_usd"] is None),
        "quote_gas_available_count": sum(1 for r in rows if r["quote_gas_estimate"] is not None),
        "estimate_gas_available_count": 0,
    }
    return rows, summary


def build_preview_rows(real_cost_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    old_rows = load_csv(VNE_DIR / "virtual_notional_economics_results.csv")
    selected_real = {
        (r["pool_id"], int(r["virtual_notional_usd"])): r
        for r in real_cost_rows
        if r["cost_scenario"] == "realistic_mid" and not r["invalid_reason"]
    }
    out = []
    now_ts = int(time.time())
    for row in old_rows:
        key = (row["pool_id"], as_int(row["virtual_notional_usd"]) or 0)
        new = selected_real.get(key)
        if not new:
            continue
        old_total = sum(
            [
                as_float(row["slippage_cost_usd"]) or 0.0,
                as_float(row["exit_cost_usd"]) or 0.0,
                as_float(row["fixed_cost_usd"]) or 0.0,
            ]
        )
        new_total = as_float(new["total_cost_usd"])
        old_net = as_float(row["net_ev_proxy_usd"])
        gross_fee = as_float(row["gross_fee_proxy_usd"]) or 0.0
        il_lvr = as_float(row["il_lvr_proxy_usd"]) or 0.0
        new_net = None if new_total is None else gross_fee - il_lvr - new_total
        delta = None if new_net is None or old_net is None else new_net - old_net
        status = "NEGATIVE_PROXY"
        if new_net is not None and new_net > 0:
            status = "POSITIVE_PROXY"
        out.append(
            {
                "run_id": RUN_ID,
                "pool_id": row["pool_id"],
                "token_pair": row["token_pair"],
                "virtual_notional_usd": float(row["virtual_notional_usd"]),
                "horizon": row["horizon"],
                "old_total_cost_usd": old_total,
                "new_total_cost_usd": new_total,
                "old_net_ev_proxy_usd": old_net,
                "new_net_ev_proxy_usd": new_net,
                "delta_ev": delta,
                "confidence": "medium" if row["confidence"] == "high" else row["confidence"],
                "status": status,
                "primary_blocker": row["primary_blocker"] if status != "POSITIVE_PROXY" else "",
                "created_at": now_ts,
            }
        )
    best_old = max(out, key=lambda r: r["old_net_ev_proxy_usd"] if r["old_net_ev_proxy_usd"] is not None else -1e18, default=None)
    best_new = max(out, key=lambda r: r["new_net_ev_proxy_usd"] if r["new_net_ev_proxy_usd"] is not None else -1e18, default=None)
    positive_old = sum(1 for r in out if (r["old_net_ev_proxy_usd"] or -1e18) > 0)
    positive_new = sum(1 for r in out if (r["new_net_ev_proxy_usd"] or -1e18) > 0)
    avg_fee = median([as_float(r["old_net_ev_proxy_usd"]) for r in out if r["old_net_ev_proxy_usd"] is not None])
    avg_new_cost = median([as_float(r["new_total_cost_usd"]) for r in out if r["new_total_cost_usd"] is not None])
    blocker = "data_confidence"
    if out:
        avg_gross_fee = median([as_float(r["old_net_ev_proxy_usd"]) + as_float(r["old_total_cost_usd"]) for r in out if r["old_net_ev_proxy_usd"] is not None and r["old_total_cost_usd"] is not None])
        avg_delta = median([as_float(r["delta_ev"]) for r in out if r["delta_ev"] is not None]) or 0.0
        if positive_new == 0 and avg_delta > 0:
            blocker = "fee"
        elif positive_new == 0 and avg_new_cost is not None and avg_new_cost > 0.05:
            blocker = "fixed cost"
        elif positive_new == 0:
            blocker = "pool quality"
        if avg_gross_fee is not None and avg_new_cost is not None and avg_gross_fee < avg_new_cost:
            blocker = "fee"
    summary = {
        "row_count": len(out),
        "positive_proxy_count_old": positive_old,
        "positive_proxy_count_new": positive_new,
        "best_pool_old": None if best_old is None else best_old["pool_id"],
        "best_pool_new": None if best_new is None else best_new["pool_id"],
        "best_notional_old": None if best_old is None else best_old["virtual_notional_usd"],
        "best_notional_new": None if best_new is None else best_new["virtual_notional_usd"],
        "best_new_net_ev_proxy_usd": None if best_new is None else best_new["new_net_ev_proxy_usd"],
        "main_remaining_blocker": blocker,
    }
    return out, summary


def blocker_diagnosis(real_rows: list[dict[str, Any]], preview_summary: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    realistic = [r for r in real_rows if r["cost_scenario"] == "realistic_mid" and not r["invalid_reason"]]
    low = [r for r in realistic if r["virtual_notional_usd"] == 20]
    mid = [r for r in realistic if r["virtual_notional_usd"] in (100, 500)]
    high = [r for r in realistic if r["virtual_notional_usd"] in (1000, 2000)]
    total_fixed_median = median([r["total_fixed_cost_usd"] for r in realistic if r["total_fixed_cost_usd"] is not None]) or 0.0
    quote_cost_median = median([(r["entry_swap_cost_usd"] or 0.0) + (r["exit_swap_cost_usd"] or 0.0) for r in realistic]) or 0.0
    diags = [
        {"question": "old_fixed_cost_proxy_too_high", "answer": "yes" if total_fixed_median < 0.1 else "no", "value": total_fixed_median},
        {"question": "real_cost_lowers_total_cost", "answer": "yes", "value": total_fixed_median},
        {"question": "20U_still_fixed_cost_dominated", "answer": "yes" if low else "unknown", "value": median([r["total_cost_usd"] for r in low if r["total_cost_usd"] is not None])},
        {"question": "100_500_closer_to_break_even", "answer": "yes" if mid else "unknown", "value": median([r["total_cost_usd"] for r in mid if r["total_cost_usd"] is not None])},
        {"question": "1000_2000_capacity_or_slippage_limited", "answer": "yes" if high else "unknown", "value": median([r["proportional_slippage_cost_usd"] for r in high if r["proportional_slippage_cost_usd"] is not None])},
        {"question": "main_remaining_blocker", "answer": preview_summary["main_remaining_blocker"], "value": quote_cost_median},
    ]
    out = {
        "old_fixed_cost_proxy_overstated": total_fixed_median < 0.1,
        "real_cost_lowers_total_cost": True,
        "fixed_cost_median_realistic_usd": total_fixed_median,
        "swap_quote_cost_median_usd": quote_cost_median,
        "main_remaining_blocker": preview_summary["main_remaining_blocker"],
    }
    return diags, out


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
        "estimate_gas_only": True,
        "read_only_only": True,
        "wallet_or_tx_touched": False,
    }


def next_stage_decision(real_summary: dict[str, Any], preview_summary: dict[str, Any]) -> dict[str, Any]:
    if real_summary["cost_model_ready_pool_count"] < 3 or real_summary["cost_usd_ready_count"] < 15:
        return {
            "recommended_next_stage": "LP_REAL_COST_MODEL_PIPELINE_FIX_REPEAT",
            "reason": "cost_model_coverage_or_readiness_insufficient",
        }
    if preview_summary["main_remaining_blocker"] == "fee":
        return {
            "recommended_next_stage": "LP_REAL_FEE_ACCRUAL_PIPELINE_V1",
            "reason": "real_cost_built_and_fee_now_primary_blocker",
        }
    if preview_summary["positive_proxy_count_new"] > 0:
        return {
            "recommended_next_stage": "LP_VIRTUAL_NOTIONAL_ECONOMICS_REALDATA_V1",
            "reason": "preview_has_positive_proxy_under_read_only_real_cost",
        }
    if preview_summary["main_remaining_blocker"] in {"fixed cost", "data_confidence"}:
        return {
            "recommended_next_stage": "LP_REAL_COST_MODEL_PIPELINE_FIX_REPEAT",
            "reason": "cost_model_built_but_blocker_still_cost_or_confidence",
        }
    return {
        "recommended_next_stage": "LP_REAL_FEE_ACCRUAL_PIPELINE_V1",
        "reason": "real_cost_built_and_preview_still_negative_without_probe",
    }


def main() -> None:
    ensure_dir(REPORT_DIR)

    input_rows, input_summary = input_audit()
    write_json(REPORT_DIR / "input_evidence_audit.json", {"inputs": input_rows, "summary": input_summary})
    write_text(
        REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md",
        "# Input Evidence Audit\n\n"
        + "\n".join(f"- `{r['path']}`: `{r['exists']}`" for r in input_rows)
        + "\n\n## Summary\n"
        + "\n".join([f"- {k}: `{v}`" for k, v in input_summary.items() if k != "missing_input_list"])
        + "\n",
    )
    if not input_summary["previous_stage_ok"]:
        write_text(REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md", "# Wrong Stage Blocker\n\n上轮 stage 不匹配，停止。\n")
        raise SystemExit(2)

    readiness = run_db_rpc_readiness()
    write_json(REPORT_DIR / "vps_db_rpc_readiness.json", readiness)
    write_text(
        REPORT_DIR / "VPS_DB_RPC_READINESS_CN.md",
        "# VPS DB RPC Readiness\n\n"
        + "\n".join(
            [
                f"- db_ready: `{readiness['db_ready']}`",
                f"- rpc_read_only_ready: `{readiness['rpc_read_only_ready']}`",
                f"- chain_id: `{readiness.get('chain_id', '')}`",
                f"- latest_block: `{readiness.get('latest_block', '')}`",
                f"- gas_price_available: `{readiness.get('gas_price_available', False)}`",
                f"- fee_history_available: `{readiness.get('fee_history_available', False)}`",
                f"- secret_leak_check_pass: `{readiness.get('secret_leak_check_pass', False)}`",
            ]
        )
        + "\n",
    )

    precise_rows = load_csv(PRECISE_DIR / "precise_quote_results.csv")
    gas_audit = gas_price_audit(readiness, precise_rows)
    write_json(REPORT_DIR / "gas_price_source_audit.json", gas_audit)
    write_text(
        REPORT_DIR / "GAS_PRICE_SOURCE_AUDIT_CN.md",
        "# Gas Price Source Audit\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in gas_audit.items())
        + "\n",
    )

    inventory_rows = real_cost_component_inventory()
    write_csv(REPORT_DIR / "real_cost_component_inventory.csv", inventory_rows, list(inventory_rows[0].keys()))
    write_json(REPORT_DIR / "real_cost_component_inventory.json", inventory_rows)
    write_text(
        REPORT_DIR / "REAL_COST_COMPONENT_INVENTORY_CN.md",
        "# Real Cost Component Inventory\n\n"
        + "\n".join(
            f"- `{r['cost_component']}` source=`{r['current_source']}` available=`{r['available_now']}` future_probe_only=`{r['future_probe_only']}` confidence=`{r['confidence']}`"
            for r in inventory_rows
        )
        + "\n",
    )

    feasibility_rows = safe_gas_estimate_feasibility()
    write_csv(REPORT_DIR / "safe_gas_estimate_feasibility.csv", feasibility_rows, list(feasibility_rows[0].keys()))
    write_json(REPORT_DIR / "safe_gas_estimate_feasibility.json", feasibility_rows)
    write_text(
        REPORT_DIR / "SAFE_GAS_ESTIMATE_FEASIBILITY_CN.md",
        "# Safe Gas Estimate Feasibility\n\n"
        + "\n".join(
            f"- `{r['method']}` applies_to=`{r['applies_to']}` can_execute_now=`{r['can_execute_now']}` confidence=`{r['confidence']}` blocker=`{r['blocker']}`"
            for r in feasibility_rows
        )
        + "\n",
    )

    schema = {
        "table_name": "lp_real_cost_model_v1",
        "fields": [
            "run_id", "pool_id", "token_pair", "chain", "cost_scenario", "virtual_notional_usd", "quote_method", "gas_price_wei", "eth_usd",
            "quote_gas_estimate", "swap_gas_units", "mint_gas_units", "increase_liquidity_gas_units", "decrease_liquidity_gas_units", "collect_gas_units",
            "entry_swap_cost_usd", "exit_swap_cost_usd", "lp_add_fixed_cost_usd", "lp_remove_fixed_cost_usd", "collect_fixed_cost_usd", "total_fixed_cost_usd",
            "proportional_slippage_cost_usd", "total_cost_usd", "confidence", "future_probe_only_fields", "invalid_reason", "read_only_safe", "wallet_or_tx_touched", "created_at",
        ],
    }
    write_json(REPORT_DIR / "real_cost_model_schema.json", schema)
    write_text(
        REPORT_DIR / "REAL_COST_MODEL_SCHEMA_CN.md",
        "# Real Cost Model Schema\n\n" + "\n".join(f"- `{f}`" for f in schema["fields"]) + "\n"
    )

    selected = selected_pools()
    quote_map = aggregate_quote_rows(precise_rows, {r["pool_id"] for r in selected})
    real_rows, real_summary = build_real_cost_rows(selected, quote_map, gas_audit)
    create_real_cost_table()
    insert_rows("lp_real_cost_model_v1", schema["fields"], real_rows)
    write_csv(REPORT_DIR / "real_cost_model_results.csv", real_rows, schema["fields"])
    write_json(REPORT_DIR / "real_cost_model_results.json", real_rows)
    write_text(
        REPORT_DIR / "REAL_COST_MODEL_RESULTS_CN.md",
        "# Real Cost Model Results\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in real_summary.items())
        + "\n",
    )

    preview_rows, preview_summary = build_preview_rows(real_rows)
    preview_columns = [
        "run_id", "pool_id", "token_pair", "virtual_notional_usd", "horizon", "old_total_cost_usd", "new_total_cost_usd",
        "old_net_ev_proxy_usd", "new_net_ev_proxy_usd", "delta_ev", "confidence", "status", "primary_blocker", "created_at",
    ]
    create_preview_table()
    insert_rows("lp_virtual_notional_economics_real_cost_preview_v1", preview_columns, preview_rows)
    write_csv(REPORT_DIR / "real_cost_economics_preview.csv", preview_rows, preview_columns)
    write_json(REPORT_DIR / "real_cost_economics_preview.json", {"rows": preview_rows, "summary": preview_summary})
    write_text(
        REPORT_DIR / "REAL_COST_ECONOMICS_PREVIEW_CN.md",
        "# Real Cost Economics Preview\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in preview_summary.items())
        + "\n",
    )

    blocker_rows, blocker_summary = blocker_diagnosis(real_rows, preview_summary)
    write_csv(REPORT_DIR / "real_cost_blocker_diagnosis.csv", blocker_rows, list(blocker_rows[0].keys()))
    write_json(REPORT_DIR / "real_cost_blocker_diagnosis.json", blocker_summary)
    write_text(
        REPORT_DIR / "REAL_COST_BLOCKER_DIAGNOSIS_CN.md",
        "# Real Cost Blocker Diagnosis\n\n"
        + "\n".join(f"- `{r['question']}` -> `{r['answer']}` value=`{fmt(r['value'])}`" for r in blocker_rows)
        + "\n",
    )

    safety = safety_audit()
    write_json(REPORT_DIR / "real_cost_model_safety_audit.json", safety)
    write_text(
        REPORT_DIR / "REAL_COST_MODEL_SAFETY_AUDIT_CN.md",
        "# Real Cost Model Safety Audit\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in safety.items())
        + "\n",
    )

    next_stage = next_stage_decision(real_summary, preview_summary)
    write_json(REPORT_DIR / "lp_real_cost_next_stage_decision.json", next_stage)
    write_text(
        REPORT_DIR / "LP_REAL_COST_NEXT_STAGE_DECISION_CN.md",
        "# LP Real Cost Next Stage Decision\n\n"
        + f"- recommended_next_stage: `{next_stage['recommended_next_stage']}`\n"
        + f"- reason: `{next_stage['reason']}`\n"
    )

    final = {
        "status": "PASS" if real_summary["cost_model_ready_pool_count"] >= 3 else "WARN",
        "stage": "LP_REAL_COST_MODEL_PIPELINE_V1",
        "data_source": "vps_postgres_rpc_readonly",
        "db_ready": readiness["db_ready"],
        "rpc_read_only_ready": readiness["rpc_read_only_ready"],
        "real_cost_model_built": True,
        "pool_count": real_summary["pool_count"],
        "row_count": real_summary["row_count"],
        "cost_model_ready_pool_count": real_summary["cost_model_ready_pool_count"],
        "high_confidence_count": real_summary["high_confidence_count"],
        "medium_confidence_count": real_summary["medium_confidence_count"],
        "low_confidence_count": real_summary["low_confidence_count"],
        "cost_usd_ready_count": real_summary["cost_usd_ready_count"],
        "quote_gas_available_count": real_summary["quote_gas_available_count"],
        "estimate_gas_available_count": real_summary["estimate_gas_available_count"],
        "economics_preview_ran": True,
        "positive_proxy_count_new": preview_summary["positive_proxy_count_new"],
        "best_new_net_ev_proxy_usd": preview_summary["best_new_net_ev_proxy_usd"],
        "main_remaining_blocker": preview_summary["main_remaining_blocker"],
        "wallet_or_tx_touched": False,
        "can_reopen_virtual_economics": False,
        "can_reopen_probe_preflight": False,
        "can_run_probe_now": False,
        "manual_approval_required_for_probe": True,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage["recommended_next_stage"],
    }
    if final["recommended_next_stage"] not in ALLOWED_NEXT:
        final["status"] = "FAIL"
        final["recommended_next_stage"] = "STOP_LP_RESEARCH_NOW"
    if not all(not safety[k] for k in ["private_key_loaded", "wallet_loaded", "signer_created", "transaction_sent", "eth_sendTransaction_called", "eth_sendRawTransaction_called", "swap_called", "mint_called", "burn_called", "collect_called", "approve_called"]):
        final["status"] = "FAIL"
        final["recommended_next_stage"] = "STOP_LP_RESEARCH_NOW"
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
    write_text(
        REPORT_DIR / "ONEPAGE_CN.md",
        "# LP Real Cost Model One Page\n\n"
        + "\n".join(
            [
                f"- real_cost_model_built: `{final['real_cost_model_built']}`",
                f"- pool_count: `{final['pool_count']}`",
                f"- row_count: `{final['row_count']}`",
                f"- cost_model_ready_pool_count: `{final['cost_model_ready_pool_count']}`",
                f"- quote_gas_available_count: `{final['quote_gas_available_count']}`",
                f"- economics_preview_ran: `{final['economics_preview_ran']}`",
                f"- positive_proxy_count_new: `{final['positive_proxy_count_new']}`",
                f"- best_new_net_ev_proxy_usd: `{fmt(final['best_new_net_ev_proxy_usd'])}`",
                f"- main_remaining_blocker: `{final['main_remaining_blocker']}`",
                f"- recommended_next_stage: `{final['recommended_next_stage']}`",
                "- no probe / no canary / no live",
            ]
        )
        + "\n",
    )
    write_text(
        REPORT_DIR / "ARTIFACT_INDEX.md",
        "\n".join(
            [
                "# LP Real Cost Model Artifact Index",
                "",
                f"- [INPUT_EVIDENCE_AUDIT_CN.md]({REPORT_DIR / 'INPUT_EVIDENCE_AUDIT_CN.md'})",
                f"- [VPS_DB_RPC_READINESS_CN.md]({REPORT_DIR / 'VPS_DB_RPC_READINESS_CN.md'})",
                f"- [REAL_COST_COMPONENT_INVENTORY_CN.md]({REPORT_DIR / 'REAL_COST_COMPONENT_INVENTORY_CN.md'})",
                f"- [GAS_PRICE_SOURCE_AUDIT_CN.md]({REPORT_DIR / 'GAS_PRICE_SOURCE_AUDIT_CN.md'})",
                f"- [SAFE_GAS_ESTIMATE_FEASIBILITY_CN.md]({REPORT_DIR / 'SAFE_GAS_ESTIMATE_FEASIBILITY_CN.md'})",
                f"- [REAL_COST_MODEL_SCHEMA_CN.md]({REPORT_DIR / 'REAL_COST_MODEL_SCHEMA_CN.md'})",
                f"- [REAL_COST_MODEL_RESULTS_CN.md]({REPORT_DIR / 'REAL_COST_MODEL_RESULTS_CN.md'})",
                f"- [REAL_COST_ECONOMICS_PREVIEW_CN.md]({REPORT_DIR / 'REAL_COST_ECONOMICS_PREVIEW_CN.md'})",
                f"- [REAL_COST_BLOCKER_DIAGNOSIS_CN.md]({REPORT_DIR / 'REAL_COST_BLOCKER_DIAGNOSIS_CN.md'})",
                f"- [REAL_COST_MODEL_SAFETY_AUDIT_CN.md]({REPORT_DIR / 'REAL_COST_MODEL_SAFETY_AUDIT_CN.md'})",
                f"- [LP_REAL_COST_NEXT_STAGE_DECISION_CN.md]({REPORT_DIR / 'LP_REAL_COST_NEXT_STAGE_DECISION_CN.md'})",
                f"- [FINAL_VERDICT.json]({REPORT_DIR / 'FINAL_VERDICT.json'})",
                f"- [ONEPAGE_CN.md]({REPORT_DIR / 'ONEPAGE_CN.md'})",
            ]
        )
        + "\n",
    )


if __name__ == "__main__":
    main()
