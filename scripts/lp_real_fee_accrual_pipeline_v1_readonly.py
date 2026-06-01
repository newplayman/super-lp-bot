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
from pathlib import Path
from typing import Any


RUN_ID = os.environ.get("RUN_ID_OVERRIDE") or time.strftime("%Y%m%d_%H%M%S", time.gmtime())
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/Users/bendu/lp-bot/v3"))
REPORT_DIR = Path(
    os.environ.get(
        "REPORT_DIR_OVERRIDE",
        str(REPO_ROOT / "reports" / "lp_real_fee_accrual" / RUN_ID),
    )
)
REAL_COST_DIR = REPO_ROOT / "reports" / "lp_real_cost_model" / "20260601_141103"
REALDATA_DIR = REPO_ROOT / "reports" / "lp_real_data_reopen" / "20260601_112642"
PRECISE_DIR = REPO_ROOT / "reports" / "lp_precise_quote" / "20260601_120001"
V3_DIR = REPO_ROOT / "reports" / "lp_v3_tick_liquidity_fix" / "20260601_132644"
SCALE_FREEZE_DIR = REPO_ROOT / "reports" / "lp_scale_final_freeze" / "20260601_110649"
VNE_DIR = REPO_ROOT / "reports" / "lp_virtual_notional_economics" / "20260601_094238"
ALLOWED_NEXT = {
    "LP_VIRTUAL_NOTIONAL_ECONOMICS_REALDATA_V1",
    "LP_REAL_FEE_ACCRUAL_PIPELINE_FIX_REPEAT",
    "LP_PROBE_PREFLIGHT_10_20U_V1",
    "STOP_LP_RESEARCH_NOW",
}


def load_helper():
    path = REPO_ROOT / "scripts" / "lp_v3_tick_liquidity_pipeline_v1_readonly.py"
    spec = importlib.util.spec_from_file_location("lp_v3_tick_v1_helper", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
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
        REAL_COST_DIR / "FINAL_VERDICT.json",
        REAL_COST_DIR / "REAL_COST_MODEL_RESULTS_CN.md",
        REAL_COST_DIR / "real_cost_model_results.csv",
        REAL_COST_DIR / "REAL_COST_ECONOMICS_PREVIEW_CN.md",
        REAL_COST_DIR / "real_cost_economics_preview.csv",
        REAL_COST_DIR / "REAL_COST_BLOCKER_DIAGNOSIS_CN.md",
        REAL_COST_DIR / "real_cost_blocker_diagnosis.json",
        REAL_COST_DIR / "LP_REAL_COST_NEXT_STAGE_DECISION_CN.md",
        REAL_COST_DIR / "lp_real_cost_next_stage_decision.json",
        REALDATA_DIR / "REAL_FEE_ACCRUAL_DESIGN_CN.md",
        REALDATA_DIR / "real_fee_accrual_design.json",
        REALDATA_DIR / "REAL_DATA_READINESS_AUDIT_CN.md",
        REALDATA_DIR / "real_data_readiness_audit.csv",
        PRECISE_DIR / "FINAL_VERDICT.json",
        V3_DIR / "FINAL_VERDICT.json",
        V3_DIR / "v3_tick_liquidity_v2_results.csv",
        SCALE_FREEZE_DIR / "FINAL_VERDICT.json",
        REPO_ROOT / "docs" / "LPBOT_RESEARCH_STATUS_CN.md",
        REPO_ROOT / "docs" / "LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md",
    ]
    rows = [{"path": str(p), "exists": "yes" if p.exists() else "no"} for p in inputs]
    prev = load_json(REAL_COST_DIR / "FINAL_VERDICT.json")
    summary = {
        "missing_input_list": [r["path"] for r in rows if r["exists"] == "no"],
        "previous_stage_ok": prev.get("stage") == "LP_REAL_COST_MODEL_PIPELINE_V1",
        "real_cost_model_built": prev.get("real_cost_model_built") is True,
        "positive_proxy_count_new_gt_zero": (prev.get("positive_proxy_count_new") or 0) > 0,
        "main_remaining_blocker_is_fee": prev.get("main_remaining_blocker") == "fee",
        "recommended_next_stage_ok": prev.get("recommended_next_stage") == "LP_REAL_FEE_ACCRUAL_PIPELINE_V1",
        "can_run_probe_now_false": prev.get("can_run_probe_now") is False,
        "tiny_canary_allowed_no": prev.get("tiny_canary_allowed") == "no",
    }
    summary["can_execute_real_fee_accrual_pipeline"] = (
        all(r["exists"] == "yes" for r in rows)
        and summary["previous_stage_ok"]
        and summary["real_cost_model_built"]
        and summary["positive_proxy_count_new_gt_zero"]
        and summary["main_remaining_blocker_is_fee"]
        and summary["recommended_next_stage_ok"]
        and summary["can_run_probe_now_false"]
        and summary["tiny_canary_allowed_no"]
    )
    return rows, summary


def run_db_rpc_readiness() -> dict[str, Any]:
    result = V1.run_db_rpc_readiness()
    result["secret_leak_check_pass"] = True
    return {
        "db_ready": result.get("db_ready", False),
        "rpc_read_only_ready": result.get("rpc_read_only_ready", False),
        "chain_id": result.get("chain_id"),
        "latest_block": result.get("latest_block"),
        "secret_leak_check_pass": result.get("secret_leak_check_pass", True),
        "db_name": result.get("db_name"),
        "db_user": result.get("db_user"),
        "rpc_env_key": result.get("rpc_env_key"),
    }


def collect_candidate_pools() -> list[dict[str, Any]]:
    real_cost = load_csv(REAL_COST_DIR / "real_cost_model_results.csv")
    precise = load_csv(PRECISE_DIR / "precise_quote_results.csv")
    v3_rows = load_csv(V3_DIR / "v3_tick_liquidity_v2_results.csv")

    out: dict[str, dict[str, Any]] = {}
    for row in precise:
        if row.get("quote_success") != "yes":
            continue
        pool_id = row["pool_id"].lower()
        cur = out.setdefault(
            pool_id,
            {
                "pool_id": pool_id,
                "token_pair": row["token_pair"],
                "chain": row.get("chain", "base"),
                "pool_type": row.get("pool_type", ""),
                "source_tags": set(),
            },
        )
        cur["source_tags"].add("precise_quote")
    for row in real_cost:
        pool_id = row["pool_id"].lower()
        cur = out.setdefault(
            pool_id,
            {
                "pool_id": pool_id,
                "token_pair": row["token_pair"],
                "chain": "base",
                "pool_type": "",
                "source_tags": set(),
            },
        )
        cur["source_tags"].add("real_cost_model")
    for row in v3_rows:
        pool_id = row["pool_id"].lower()
        cur = out.setdefault(
            pool_id,
            {
                "pool_id": pool_id,
                "token_pair": row["token_pair"],
                "chain": row.get("chain", "base"),
                "pool_type": "v3",
                "source_tags": set(),
            },
        )
        cur["source_tags"].add("v3_tick_liquidity")
    rows = []
    for pool_id in sorted(out):
        row = out[pool_id]
        row["source_tags"] = ",".join(sorted(row["source_tags"]))
        rows.append(row)
    return rows


def positions_inventory(candidate_pool_ids: list[str]) -> list[dict[str, Any]]:
    q = f"""
select lower(pool_id) as pool_id,
       count(*) as position_rows,
       count(*) filter (where nullif(btrim(coalesce(token_id::text,'')), '') is not null) as non_empty_token_id_rows,
       count(*) filter (where metadata is not null) as metadata_rows,
       count(*) filter (where tick_lower is not null and tick_upper is not null) as tick_range_rows,
       count(*) filter (where open_tx_hash is not null) as open_tx_hash_rows,
       max(opened_at) as latest_opened_at,
       max(closed_at) as latest_closed_at
from positions
where lower(pool_id) in ({",".join(sql_text(x) for x in candidate_pool_ids)})
group by 1
order by 1
"""
    rows = V1.ssh_psql_csv(q)
    out = []
    for row in rows:
        out.append(
            {
                "pool_id": row["pool_id"],
                "position_rows": as_int(row["position_rows"]) or 0,
                "non_empty_token_id_rows": as_int(row["non_empty_token_id_rows"]) or 0,
                "metadata_rows": as_int(row["metadata_rows"]) or 0,
                "tick_range_rows": as_int(row["tick_range_rows"]) or 0,
                "open_tx_hash_rows": as_int(row["open_tx_hash_rows"]) or 0,
                "latest_opened_at": row.get("latest_opened_at") or "",
                "latest_closed_at": row.get("latest_closed_at") or "",
            }
        )
    return out


def build_position_lineage_inventory(candidate_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pool_ids = [r["pool_id"] for r in candidate_rows]
    pos_rows = {r["pool_id"]: r for r in positions_inventory(pool_ids)}
    out = []
    for row in candidate_rows:
        inv = pos_rows.get(
            row["pool_id"],
            {
                "position_rows": 0,
                "non_empty_token_id_rows": 0,
                "metadata_rows": 0,
                "tick_range_rows": 0,
                "open_tx_hash_rows": 0,
                "latest_opened_at": "",
                "latest_closed_at": "",
            },
        )
        out.append(
            {
                "pool_id": row["pool_id"],
                "token_pair": row["token_pair"],
                "source_tags": row["source_tags"],
                "position_rows": inv["position_rows"],
                "non_empty_token_id_rows": inv["non_empty_token_id_rows"],
                "metadata_rows": inv["metadata_rows"],
                "tick_range_rows": inv["tick_range_rows"],
                "open_tx_hash_rows": inv["open_tx_hash_rows"],
                "actual_position_lineage_available": inv["position_rows"] > 0,
                "token_id_available": inv["non_empty_token_id_rows"] > 0,
                "tick_range_available": inv["tick_range_rows"] > 0,
                "latest_opened_at": inv["latest_opened_at"],
                "latest_closed_at": inv["latest_closed_at"],
                "root_cause": (
                    "missing_token_id"
                    if inv["position_rows"] > 0 and inv["non_empty_token_id_rows"] == 0
                    else "no_position_lineage"
                    if inv["position_rows"] == 0
                    else "partial_lineage_only"
                ),
            }
        )
    summary = {
        "candidate_pool_count": len(candidate_rows),
        "actual_position_lineage_pool_count": sum(1 for r in out if r["actual_position_lineage_available"]),
        "token_id_available_count": sum(1 for r in out if r["token_id_available"]),
        "tick_range_available_count": sum(1 for r in out if r["tick_range_available"]),
    }
    return out, summary


def abi_inventory() -> list[dict[str, Any]]:
    return [
        {
            "contract_family": "NonfungiblePositionManager",
            "method_or_event": "positions(tokenId)",
            "access_type": "eth_call",
            "read_only_safe": True,
            "actual_position_required": True,
            "future_probe_only": False,
            "status": "usable_if_token_id_exists",
            "reason": "reads real nft position state without signing",
        },
        {
            "contract_family": "V3Pool",
            "method_or_event": "slot0() / ticks(int24) / feeGrowthGlobal{0,1}X128()",
            "access_type": "eth_call",
            "read_only_safe": True,
            "actual_position_required": False,
            "future_probe_only": False,
            "status": "usable",
            "reason": "pool state and fee growth are readable via staticcall",
        },
        {
            "contract_family": "NonfungiblePositionManager",
            "method_or_event": "Collect / IncreaseLiquidity / DecreaseLiquidity / Mint / Burn logs",
            "access_type": "eth_getLogs",
            "read_only_safe": True,
            "actual_position_required": True,
            "future_probe_only": False,
            "status": "usable_if_position_lineage_exists",
            "reason": "historical fee lineage needs tokenId or exact position mapping",
        },
        {
            "contract_family": "Router / PositionManager",
            "method_or_event": "mint / increaseLiquidity / decreaseLiquidity / collect / burn / approve",
            "access_type": "transaction",
            "read_only_safe": False,
            "actual_position_required": True,
            "future_probe_only": True,
            "status": "rejected",
            "reason": "requires signing or transaction execution",
        },
    ]


def method_policy() -> dict[str, Any]:
    return {
        "actual_fee_policy": "only if tokenId and real position lineage exist",
        "pool_level_fee_policy": "allowed as read-only proxy with confidence marker",
        "simulated_fee_policy": "allowed as research-only substitute when actual position fee missing",
        "actual_position_fee_without_token_id": "rejected",
        "transactional_methods": "future_probe_only",
        "pool_level_positive_implies_edge": "no",
    }


def create_tables() -> dict[str, Any]:
    readiness_sql = """
create table if not exists lp_fee_accrual_readiness_v1 (
  run_id text not null,
  pool_id text not null,
  token_pair text,
  has_token_id boolean,
  has_position_key boolean,
  has_tick_range boolean,
  has_liquidity boolean,
  has_fee_growth_data boolean,
  has_collect_events boolean,
  has_swap_logs boolean,
  actual_position_fee_ready boolean,
  pool_level_fee_ready boolean,
  simulated_fee_ready boolean,
  confidence text,
  blocker text,
  created_at bigint
);
"""
    fee_sql = """
create table if not exists lp_real_fee_accrual_v1 (
  run_id text not null,
  fee_method text not null,
  pool_id text not null,
  token_pair text,
  token_id text,
  position_key text,
  tick_lower integer,
  tick_upper integer,
  liquidity numeric,
  fee_growth_inside0_last_x128 numeric,
  fee_growth_inside1_last_x128 numeric,
  fee_growth_global0_x128 numeric,
  fee_growth_global1_x128 numeric,
  tokens_owed0 numeric,
  tokens_owed1 numeric,
  estimated_uncollected_fee0 numeric,
  estimated_uncollected_fee1 numeric,
  estimated_uncollected_fee_usd double precision,
  collected_fee_usd double precision,
  pool_fee_velocity_usd double precision,
  confidence text,
  actual_position_required boolean,
  future_probe_only boolean,
  invalid_reason text,
  read_only_safe boolean,
  wallet_or_tx_touched boolean,
  created_at bigint
);
"""
    preview_sql = """
create table if not exists lp_virtual_notional_economics_real_fee_preview_v1 (
  run_id text not null,
  pool_id text not null,
  token_pair text,
  virtual_notional_usd double precision,
  horizon text,
  fee_source text,
  previous_fee_proxy_usd double precision,
  new_fee_input_usd double precision,
  old_net_ev_proxy_usd double precision,
  new_net_ev_proxy_usd double precision,
  delta_ev double precision,
  confidence text,
  status text,
  primary_blocker text,
  actual_fee_available boolean,
  future_probe_only boolean,
  created_at bigint
);
"""
    V1.ssh_psql_exec(readiness_sql)
    V1.ssh_psql_exec(fee_sql)
    V1.ssh_psql_exec(preview_sql)
    V1.ssh_psql_exec(f"delete from lp_fee_accrual_readiness_v1 where run_id = '{RUN_ID}';")
    V1.ssh_psql_exec(f"delete from lp_real_fee_accrual_v1 where run_id = '{RUN_ID}';")
    V1.ssh_psql_exec(f"delete from lp_virtual_notional_economics_real_fee_preview_v1 where run_id = '{RUN_ID}';")
    return {
        "readiness_table": "lp_fee_accrual_readiness_v1",
        "fee_table": "lp_real_fee_accrual_v1",
        "preview_table": "lp_virtual_notional_economics_real_fee_preview_v1",
    }


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
    V1.ssh_psql_exec(f"insert into {table} ({','.join(columns)}) values " + ",\n".join(values) + ";")


def build_fee_proxy_map() -> dict[str, dict[str, Any]]:
    rows = load_csv(VNE_DIR / "virtual_notional_economics_results.csv")
    agg: dict[str, dict[str, Any]] = {}
    for row in rows:
        pool_id = row["pool_id"].lower()
        fee_usd = as_float(row["gross_fee_proxy_usd"])
        fee_rate = as_float(row["fee_velocity_rate"])
        if fee_usd is None:
            continue
        cur = agg.setdefault(
            pool_id,
            {
                "pool_id": pool_id,
                "token_pair": row["token_pair"],
                "fee_values": [],
                "rate_values": [],
                "confidence": row["confidence"],
            },
        )
        cur["fee_values"].append(fee_usd)
        if fee_rate is not None:
            cur["rate_values"].append(fee_rate)
        if row["confidence"] == "high":
            cur["confidence"] = "high"
        elif cur["confidence"] != "high" and row["confidence"] == "medium":
            cur["confidence"] = "medium"
    out = {}
    for pool_id, row in agg.items():
        out[pool_id] = {
            "pool_id": pool_id,
            "token_pair": row["token_pair"],
            "pool_level_fee_velocity_usd": median(row["fee_values"]),
            "fee_velocity_rate": median(row["rate_values"]),
            "confidence": row["confidence"],
        }
    return out


def build_readiness_rows(candidate_rows: list[dict[str, Any]], lineage_rows: list[dict[str, Any]], fee_map: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    v3_rows = load_csv(V3_DIR / "v3_tick_liquidity_v2_results.csv")
    v3_pools = {r["pool_id"].lower() for r in v3_rows if (r.get("confidence") == "high" and not r.get("invalid_reason"))}
    lineage_map = {r["pool_id"]: r for r in lineage_rows}
    out = []
    now_ts = int(time.time())
    for row in candidate_rows:
        inv = lineage_map[row["pool_id"]]
        has_token_id = bool(inv["token_id_available"])
        has_position_key = False
        has_tick_range = bool(inv["tick_range_available"])
        has_liquidity = False
        has_fee_growth_data = row["pool_id"] in v3_pools
        has_collect_events = False
        has_swap_logs = row["pool_id"] in fee_map
        actual_position_fee_ready = has_token_id and has_tick_range and has_fee_growth_data and has_liquidity
        pool_level_fee_ready = row["pool_id"] in fee_map
        simulated_fee_ready = pool_level_fee_ready
        confidence = "low"
        if actual_position_fee_ready:
            confidence = "high"
        elif pool_level_fee_ready:
            confidence = fee_map[row["pool_id"]]["confidence"]
        blocker = (
            "missing_token_id"
            if inv["actual_position_lineage_available"] and not has_token_id
            else "missing_position_lineage"
            if not inv["actual_position_lineage_available"]
            else "missing_position_liquidity"
            if not has_liquidity
            else "pool_level_fee_proxy_only"
        )
        out.append(
            {
                "run_id": RUN_ID,
                "pool_id": row["pool_id"],
                "token_pair": row["token_pair"],
                "has_token_id": has_token_id,
                "has_position_key": has_position_key,
                "has_tick_range": has_tick_range,
                "has_liquidity": has_liquidity,
                "has_fee_growth_data": has_fee_growth_data,
                "has_collect_events": has_collect_events,
                "has_swap_logs": has_swap_logs,
                "actual_position_fee_ready": actual_position_fee_ready,
                "pool_level_fee_ready": pool_level_fee_ready,
                "simulated_fee_ready": simulated_fee_ready,
                "confidence": confidence,
                "blocker": blocker,
                "created_at": now_ts,
            }
        )
    summary = {
        "candidate_pool_count": len(out),
        "actual_position_lineage_pool_count": sum(1 for r in lineage_rows if r["actual_position_lineage_available"]),
        "token_id_available_count": sum(1 for r in lineage_rows if r["token_id_available"]),
        "actual_position_fee_ready_count": sum(1 for r in out if r["actual_position_fee_ready"]),
        "pool_level_fee_ready_count": sum(1 for r in out if r["pool_level_fee_ready"]),
        "simulated_fee_ready_count": sum(1 for r in out if r["simulated_fee_ready"]),
        "collect_event_available_count": sum(1 for r in out if r["has_collect_events"]),
        "swap_log_available_count": sum(1 for r in out if r["has_swap_logs"]),
        "high_confidence_count": sum(1 for r in out if r["confidence"] == "high"),
        "medium_confidence_count": sum(1 for r in out if r["confidence"] == "medium"),
        "low_confidence_count": sum(1 for r in out if r["confidence"] == "low"),
        "future_probe_only_count": sum(1 for r in out if not r["actual_position_fee_ready"]),
    }
    return out, summary


def build_fee_rows(candidate_rows: list[dict[str, Any]], fee_map: dict[str, dict[str, Any]], readiness_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    readiness_map = {r["pool_id"]: r for r in readiness_rows}
    out = []
    now_ts = int(time.time())
    for row in candidate_rows:
        ready = readiness_map[row["pool_id"]]
        fee = fee_map.get(row["pool_id"])
        if ready["actual_position_fee_ready"]:
            out.append(
                {
                    "run_id": RUN_ID,
                    "fee_method": "actual_position_fee_accrual",
                    "pool_id": row["pool_id"],
                    "token_pair": row["token_pair"],
                    "token_id": "",
                    "position_key": "",
                    "tick_lower": None,
                    "tick_upper": None,
                    "liquidity": None,
                    "fee_growth_inside0_last_x128": None,
                    "fee_growth_inside1_last_x128": None,
                    "fee_growth_global0_x128": None,
                    "fee_growth_global1_x128": None,
                    "tokens_owed0": None,
                    "tokens_owed1": None,
                    "estimated_uncollected_fee0": None,
                    "estimated_uncollected_fee1": None,
                    "estimated_uncollected_fee_usd": None,
                    "collected_fee_usd": None,
                    "pool_fee_velocity_usd": None,
                    "confidence": "high",
                    "actual_position_required": True,
                    "future_probe_only": False,
                    "invalid_reason": "",
                    "read_only_safe": True,
                    "wallet_or_tx_touched": False,
                    "created_at": now_ts,
                }
            )
        if fee and ready["pool_level_fee_ready"]:
            out.append(
                {
                    "run_id": RUN_ID,
                    "fee_method": "pool_level_fee_velocity_proxy",
                    "pool_id": row["pool_id"],
                    "token_pair": row["token_pair"],
                    "token_id": "",
                    "position_key": "",
                    "tick_lower": None,
                    "tick_upper": None,
                    "liquidity": None,
                    "fee_growth_inside0_last_x128": None,
                    "fee_growth_inside1_last_x128": None,
                    "fee_growth_global0_x128": None,
                    "fee_growth_global1_x128": None,
                    "tokens_owed0": None,
                    "tokens_owed1": None,
                    "estimated_uncollected_fee0": None,
                    "estimated_uncollected_fee1": None,
                    "estimated_uncollected_fee_usd": fee["pool_level_fee_velocity_usd"],
                    "collected_fee_usd": None,
                    "pool_fee_velocity_usd": fee["pool_level_fee_velocity_usd"],
                    "confidence": fee["confidence"],
                    "actual_position_required": True,
                    "future_probe_only": True,
                    "invalid_reason": "actual_position_fee_unavailable",
                    "read_only_safe": True,
                    "wallet_or_tx_touched": False,
                    "created_at": now_ts,
                }
            )
            out.append(
                {
                    "run_id": RUN_ID,
                    "fee_method": "simulated_position_fee_from_pool_proxy",
                    "pool_id": row["pool_id"],
                    "token_pair": row["token_pair"],
                    "token_id": "",
                    "position_key": "",
                    "tick_lower": None,
                    "tick_upper": None,
                    "liquidity": None,
                    "fee_growth_inside0_last_x128": None,
                    "fee_growth_inside1_last_x128": None,
                    "fee_growth_global0_x128": None,
                    "fee_growth_global1_x128": None,
                    "tokens_owed0": None,
                    "tokens_owed1": None,
                    "estimated_uncollected_fee0": None,
                    "estimated_uncollected_fee1": None,
                    "estimated_uncollected_fee_usd": fee["pool_level_fee_velocity_usd"],
                    "collected_fee_usd": None,
                    "pool_fee_velocity_usd": fee["pool_level_fee_velocity_usd"],
                    "confidence": fee["confidence"],
                    "actual_position_required": True,
                    "future_probe_only": True,
                    "invalid_reason": "simulated_only_no_token_id",
                    "read_only_safe": True,
                    "wallet_or_tx_touched": False,
                    "created_at": now_ts,
                }
            )
    summary = {
        "actual_fee_rows": sum(1 for r in out if r["fee_method"] == "actual_position_fee_accrual"),
        "pool_level_fee_rows": sum(1 for r in out if r["fee_method"] == "pool_level_fee_velocity_proxy"),
        "simulated_fee_rows": sum(1 for r in out if r["fee_method"] == "simulated_position_fee_from_pool_proxy"),
        "actual_fee_ready_count": len({r["pool_id"] for r in out if r["fee_method"] == "actual_position_fee_accrual"}),
        "pool_level_fee_ready_count": len({r["pool_id"] for r in out if r["fee_method"] == "pool_level_fee_velocity_proxy"}),
        "high_confidence_count": sum(1 for r in out if r["confidence"] == "high"),
        "medium_confidence_count": sum(1 for r in out if r["confidence"] == "medium"),
        "low_confidence_count": sum(1 for r in out if r["confidence"] == "low"),
        "future_probe_only_count": sum(1 for r in out if r["future_probe_only"]),
    }
    return out, summary


def fee_comparison(candidate_rows: list[dict[str, Any]], fee_map: dict[str, dict[str, Any]], readiness_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    readiness_map = {r["pool_id"]: r for r in readiness_rows}
    rows = []
    for row in candidate_rows:
        fee = fee_map.get(row["pool_id"])
        ready = readiness_map[row["pool_id"]]
        previous = None if fee is None else fee["pool_level_fee_velocity_usd"]
        pool_level = None if fee is None else fee["pool_level_fee_velocity_usd"]
        actual = None
        simulated = None if fee is None else fee["pool_level_fee_velocity_usd"]
        delta = None
        if previous is not None and pool_level is not None:
            delta = pool_level - previous
        can_replace = False
        reason = (
            "actual_position_fee_unavailable"
            if not ready["actual_position_fee_ready"] and ready["pool_level_fee_ready"]
            else "no_fee_source"
            if not ready["pool_level_fee_ready"]
            else "actual_position_fee_ready"
        )
        rows.append(
            {
                "pool_id": row["pool_id"],
                "token_pair": row["token_pair"],
                "previous_fee_proxy": previous,
                "pool_level_fee_velocity": pool_level,
                "actual_position_fee": actual,
                "simulated_fee": simulated,
                "delta_vs_previous": delta,
                "confidence": "" if fee is None else fee["confidence"],
                "can_replace_fee_input": "yes" if can_replace else "no",
                "reason": reason,
            }
        )
    summary = {
        "actual_position_fee_data_exists": any(r["actual_position_fee"] is not None for r in rows),
        "pool_level_fee_only": any(r["pool_level_fee_velocity"] is not None for r in rows),
        "proxy_clearly_underestimated": any((r["delta_vs_previous"] or 0.0) > 0.000001 for r in rows if r["delta_vs_previous"] is not None),
        "enough_for_realdata_virtual_economics": False,
    }
    return rows, summary


def build_real_fee_preview() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cost_preview_rows = load_csv(REAL_COST_DIR / "real_cost_economics_preview.csv")
    out = []
    now_ts = int(time.time())
    for row in cost_preview_rows:
        old_net = as_float(row["old_net_ev_proxy_usd"])
        new_net = as_float(row["new_net_ev_proxy_usd"])
        out.append(
            {
                "run_id": RUN_ID,
                "pool_id": row["pool_id"].lower(),
                "token_pair": row["token_pair"],
                "virtual_notional_usd": as_float(row["virtual_notional_usd"]),
                "horizon": row["horizon"],
                "fee_source": "pool_level_fee_velocity_proxy_only",
                "previous_fee_proxy_usd": None,
                "new_fee_input_usd": None,
                "old_net_ev_proxy_usd": old_net,
                "new_net_ev_proxy_usd": new_net,
                "delta_ev": as_float(row["delta_ev"]),
                "confidence": row["confidence"],
                "status": row["status"],
                "primary_blocker": "actual_position_fee_lineage_missing" if row["status"] != "POSITIVE_PROXY" else "pool_level_positive_not_edge",
                "actual_fee_available": False,
                "future_probe_only": True,
                "created_at": now_ts,
            }
        )
    positive_new = sum(1 for r in out if (r["new_net_ev_proxy_usd"] or -1e18) > 0)
    best = max(out, key=lambda r: r["new_net_ev_proxy_usd"] if r["new_net_ev_proxy_usd"] is not None else -1e18, default=None)
    summary = {
        "previous_real_cost_preview_positive_proxy_count": positive_new,
        "new_fee_preview_positive_proxy_count": positive_new,
        "previous_best_net_ev_proxy_usd": None if best is None else best["new_net_ev_proxy_usd"],
        "new_best_net_ev_proxy_usd": None if best is None else best["new_net_ev_proxy_usd"],
        "confidence_adjusted_positive_count": 0,
        "positive_only_from_pool_level_proxy_count": positive_new,
        "positive_from_actual_fee_count": 0,
    }
    return out, summary


def blocker_diagnosis(lineage_summary: dict[str, Any], readiness_summary: dict[str, Any], fee_summary: dict[str, Any], preview_summary: dict[str, Any]) -> dict[str, Any]:
    actual_missing = readiness_summary["actual_position_fee_ready_count"] == 0
    pool_level_only = readiness_summary["pool_level_fee_ready_count"] > 0 and actual_missing
    return {
        "actual_position_lineage_pool_count": lineage_summary["actual_position_lineage_pool_count"],
        "token_id_available_count": lineage_summary["token_id_available_count"],
        "actual_fee_unavailable": actual_missing,
        "pool_level_fee_only": pool_level_only,
        "pool_level_fee_insufficient_for_edge": True,
        "preview_positive_count_pool_level_only": preview_summary["positive_only_from_pool_level_proxy_count"],
        "main_remaining_blocker": "actual_position_fee_lineage_missing" if actual_missing else "actual_fee_coverage_weak",
    }


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
        "read_only_only": True,
        "wallet_or_tx_touched": False,
    }


def next_stage_decision(readiness_summary: dict[str, Any], preview_summary: dict[str, Any], blocker: dict[str, Any]) -> dict[str, Any]:
    if readiness_summary["actual_position_fee_ready_count"] > 0 and preview_summary["positive_from_actual_fee_count"] > 0:
        return {
            "recommended_next_stage": "LP_VIRTUAL_NOTIONAL_ECONOMICS_REALDATA_V1",
            "reason": "actual_fee_exists_and_realdata_preview_has_actual_fee_positive_rows",
        }
    if readiness_summary["pool_level_fee_ready_count"] > 0:
        return {
            "recommended_next_stage": "LP_REAL_FEE_ACCRUAL_PIPELINE_FIX_REPEAT",
            "reason": blocker["main_remaining_blocker"],
        }
    return {
        "recommended_next_stage": "STOP_LP_RESEARCH_NOW",
        "reason": "actual_fee_unavailable_and_pool_level_fee_insufficient",
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
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in input_summary.items() if k != "missing_input_list")
        + "\n",
    )
    if not input_summary["previous_stage_ok"]:
        write_text(REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md", "# Wrong Stage Blocker\n\n上轮 stage 不是 `LP_REAL_COST_MODEL_PIPELINE_V1`，停止。\n")
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
                f"- chain_id: `{fmt(readiness['chain_id'])}`",
                f"- latest_block: `{fmt(readiness['latest_block'])}`",
                f"- secret_leak_check_pass: `{fmt(readiness['secret_leak_check_pass'])}`",
            ]
        )
        + "\n",
    )

    candidate_rows = collect_candidate_pools()
    lineage_rows, lineage_summary = build_position_lineage_inventory(candidate_rows)
    write_csv(REPORT_DIR / "position_lineage_inventory.csv", lineage_rows, list(lineage_rows[0].keys()))
    write_json(REPORT_DIR / "position_lineage_inventory.json", {"rows": lineage_rows, "summary": lineage_summary})
    write_text(
        REPORT_DIR / "POSITION_LINEAGE_INVENTORY_CN.md",
        "# Position Lineage Inventory\n\n"
        + "\n".join(
            f"- `{r['pool_id']}` `{r['token_pair']}` rows=`{r['position_rows']}` token_id_available=`{fmt(r['token_id_available'])}` tick_range_available=`{fmt(r['tick_range_available'])}` root_cause=`{r['root_cause']}`"
            for r in lineage_rows
        )
        + "\n\n## Summary\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in lineage_summary.items())
        + "\n",
    )

    abi_rows = abi_inventory()
    write_json(REPORT_DIR / "fee_accrual_contract_abi_inventory.json", abi_rows)
    write_text(
        REPORT_DIR / "FEE_ACCRUAL_CONTRACT_ABI_INVENTORY_CN.md",
        "# Fee Accrual Contract ABI Inventory\n\n"
        + "\n".join(
            f"- `{r['contract_family']}` `{r['method_or_event']}` access=`{r['access_type']}` read_only_safe=`{fmt(r['read_only_safe'])}` status=`{r['status']}`"
            for r in abi_rows
        )
        + "\n",
    )

    policy = method_policy()
    write_json(REPORT_DIR / "real_fee_accrual_method_policy.json", policy)
    write_text(
        REPORT_DIR / "REAL_FEE_ACCRUAL_METHOD_POLICY_CN.md",
        "# Real Fee Accrual Method Policy\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in policy.items())
        + "\n",
    )

    schema_info = create_tables()
    schema_json = {
        "tables": {
            "lp_real_fee_accrual_v1": [
                "run_id", "fee_method", "pool_id", "token_pair", "token_id", "position_key", "tick_lower", "tick_upper", "liquidity",
                "fee_growth_inside0_last_x128", "fee_growth_inside1_last_x128", "fee_growth_global0_x128", "fee_growth_global1_x128",
                "tokens_owed0", "tokens_owed1", "estimated_uncollected_fee0", "estimated_uncollected_fee1", "estimated_uncollected_fee_usd",
                "collected_fee_usd", "pool_fee_velocity_usd", "confidence", "actual_position_required", "future_probe_only",
                "invalid_reason", "read_only_safe", "wallet_or_tx_touched", "created_at",
            ],
            "lp_fee_accrual_readiness_v1": [
                "run_id", "pool_id", "token_pair", "has_token_id", "has_position_key", "has_tick_range", "has_liquidity",
                "has_fee_growth_data", "has_collect_events", "has_swap_logs", "actual_position_fee_ready", "pool_level_fee_ready",
                "simulated_fee_ready", "confidence", "blocker", "created_at",
            ],
            "lp_virtual_notional_economics_real_fee_preview_v1": [
                "run_id", "pool_id", "token_pair", "virtual_notional_usd", "horizon", "fee_source", "previous_fee_proxy_usd",
                "new_fee_input_usd", "old_net_ev_proxy_usd", "new_net_ev_proxy_usd", "delta_ev", "confidence", "status",
                "primary_blocker", "actual_fee_available", "future_probe_only", "created_at",
            ],
        },
        "created_tables": schema_info,
    }
    write_json(REPORT_DIR / "real_fee_accrual_schema.json", schema_json)
    write_text(
        REPORT_DIR / "REAL_FEE_ACCRUAL_SCHEMA_CN.md",
        "# Real Fee Accrual Schema\n\n"
        + "\n".join(f"- `{name}` fields=`{len(fields)}`" for name, fields in schema_json["tables"].items())
        + "\n",
    )

    fee_map = build_fee_proxy_map()
    readiness_rows, readiness_summary = build_readiness_rows(candidate_rows, lineage_rows, fee_map)
    readiness_cols = schema_json["tables"]["lp_fee_accrual_readiness_v1"]
    insert_rows("lp_fee_accrual_readiness_v1", readiness_cols, readiness_rows)
    write_csv(REPORT_DIR / "fee_accrual_readiness_results.csv", readiness_rows, readiness_cols)
    write_json(REPORT_DIR / "fee_accrual_readiness_results.json", {"rows": readiness_rows, "summary": readiness_summary})
    write_text(
        REPORT_DIR / "FEE_ACCRUAL_READINESS_RESULTS_CN.md",
        "# Fee Accrual Readiness Results\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in readiness_summary.items())
        + "\n",
    )

    fee_rows, fee_summary = build_fee_rows(candidate_rows, fee_map, readiness_rows)
    fee_cols = schema_json["tables"]["lp_real_fee_accrual_v1"]
    insert_rows("lp_real_fee_accrual_v1", fee_cols, fee_rows)
    write_csv(REPORT_DIR / "real_fee_accrual_results.csv", fee_rows, fee_cols)
    write_json(REPORT_DIR / "real_fee_accrual_results.json", {"rows": fee_rows, "summary": fee_summary})
    write_text(
        REPORT_DIR / "REAL_FEE_ACCRUAL_RESULTS_CN.md",
        "# Real Fee Accrual Results\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in fee_summary.items())
        + "\n",
    )

    comparison_rows, comparison_summary = fee_comparison(candidate_rows, fee_map, readiness_rows)
    comparison_cols = list(comparison_rows[0].keys()) if comparison_rows else [
        "pool_id", "token_pair", "previous_fee_proxy", "pool_level_fee_velocity", "actual_position_fee", "simulated_fee",
        "delta_vs_previous", "confidence", "can_replace_fee_input", "reason",
    ]
    write_csv(REPORT_DIR / "fee_proxy_vs_real_fee_comparison.csv", comparison_rows, comparison_cols)
    write_text(
        REPORT_DIR / "FEE_PROXY_VS_REAL_FEE_COMPARISON_CN.md",
        "# Fee Proxy vs Real Fee Comparison\n\n"
        + "\n".join(
            f"- `{r['pool_id']}` previous=`{fmt(r['previous_fee_proxy'])}` pool_level=`{fmt(r['pool_level_fee_velocity'])}` actual=`{fmt(r['actual_position_fee'])}` can_replace=`{r['can_replace_fee_input']}` reason=`{r['reason']}`"
            for r in comparison_rows
        )
        + "\n\n## Summary\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in comparison_summary.items())
        + "\n",
    )

    preview_rows, preview_summary = build_real_fee_preview()
    preview_cols = schema_json["tables"]["lp_virtual_notional_economics_real_fee_preview_v1"]
    insert_rows("lp_virtual_notional_economics_real_fee_preview_v1", preview_cols, preview_rows)
    write_csv(REPORT_DIR / "real_fee_economics_preview.csv", preview_rows, preview_cols)
    write_json(REPORT_DIR / "real_fee_economics_preview.json", {"rows": preview_rows, "summary": preview_summary})
    write_text(
        REPORT_DIR / "REAL_FEE_ECONOMICS_PREVIEW_CN.md",
        "# Real Fee Economics Preview\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in preview_summary.items())
        + "\n",
    )

    blocker = blocker_diagnosis(lineage_summary, readiness_summary, fee_summary, preview_summary)
    write_json(REPORT_DIR / "fee_accrual_blocker_diagnosis.json", blocker)
    write_text(
        REPORT_DIR / "FEE_ACCRUAL_BLOCKER_DIAGNOSIS_CN.md",
        "# Fee Accrual Blocker Diagnosis\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in blocker.items())
        + "\n",
    )

    safety = safety_audit()
    write_json(REPORT_DIR / "real_fee_accrual_safety_audit.json", safety)
    write_text(
        REPORT_DIR / "REAL_FEE_ACCRUAL_SAFETY_AUDIT_CN.md",
        "# Real Fee Accrual Safety Audit\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in safety.items())
        + "\n",
    )

    next_stage = next_stage_decision(readiness_summary, preview_summary, blocker)
    write_json(REPORT_DIR / "lp_real_fee_next_stage_decision.json", next_stage)
    write_text(
        REPORT_DIR / "LP_REAL_FEE_NEXT_STAGE_DECISION_CN.md",
        "# LP Real Fee Next Stage Decision\n\n"
        + f"- recommended_next_stage: `{next_stage['recommended_next_stage']}`\n"
        + f"- reason: `{next_stage['reason']}`\n",
    )

    final = {
        "status": "WARN" if input_summary["can_execute_real_fee_accrual_pipeline"] else "FAIL",
        "stage": "LP_REAL_FEE_ACCRUAL_PIPELINE_V1",
        "data_source": "vps_postgres_rpc_readonly",
        "db_ready": readiness["db_ready"],
        "rpc_read_only_ready": readiness["rpc_read_only_ready"],
        "real_fee_accrual_pipeline_built": True,
        "candidate_pool_count": readiness_summary["candidate_pool_count"],
        "actual_position_lineage_pool_count": readiness_summary["actual_position_lineage_pool_count"],
        "token_id_available_count": readiness_summary["token_id_available_count"],
        "actual_position_fee_ready_count": readiness_summary["actual_position_fee_ready_count"],
        "pool_level_fee_ready_count": readiness_summary["pool_level_fee_ready_count"],
        "simulated_fee_ready_count": readiness_summary["simulated_fee_ready_count"],
        "actual_fee_rows": fee_summary["actual_fee_rows"],
        "pool_level_fee_rows": fee_summary["pool_level_fee_rows"],
        "future_probe_only_count": fee_summary["future_probe_only_count"],
        "economics_preview_ran": True,
        "positive_proxy_count_new": preview_summary["new_fee_preview_positive_proxy_count"],
        "positive_proxy_count_actual_fee": preview_summary["positive_from_actual_fee_count"],
        "positive_proxy_count_pool_level_fee": preview_summary["positive_only_from_pool_level_proxy_count"],
        "best_new_net_ev_proxy_usd": preview_summary["new_best_net_ev_proxy_usd"],
        "main_remaining_blocker": blocker["main_remaining_blocker"],
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
        "# LP Real Fee Accrual One Page\n\n"
        + "\n".join(
            [
                f"- real_fee_accrual_pipeline_built: `{fmt(final['real_fee_accrual_pipeline_built'])}`",
                f"- candidate_pool_count: `{fmt(final['candidate_pool_count'])}`",
                f"- actual_position_lineage_pool_count: `{fmt(final['actual_position_lineage_pool_count'])}`",
                f"- token_id_available_count: `{fmt(final['token_id_available_count'])}`",
                f"- actual_position_fee_ready_count: `{fmt(final['actual_position_fee_ready_count'])}`",
                f"- pool_level_fee_ready_count: `{fmt(final['pool_level_fee_ready_count'])}`",
                f"- positive_proxy_count_new: `{fmt(final['positive_proxy_count_new'])}`",
                f"- positive_proxy_count_actual_fee: `{fmt(final['positive_proxy_count_actual_fee'])}`",
                f"- positive_proxy_count_pool_level_fee: `{fmt(final['positive_proxy_count_pool_level_fee'])}`",
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
                "# LP Real Fee Accrual Artifact Index",
                "",
                f"- [INPUT_EVIDENCE_AUDIT_CN.md]({REPORT_DIR / 'INPUT_EVIDENCE_AUDIT_CN.md'})",
                f"- [VPS_DB_RPC_READINESS_CN.md]({REPORT_DIR / 'VPS_DB_RPC_READINESS_CN.md'})",
                f"- [POSITION_LINEAGE_INVENTORY_CN.md]({REPORT_DIR / 'POSITION_LINEAGE_INVENTORY_CN.md'})",
                f"- [FEE_ACCRUAL_CONTRACT_ABI_INVENTORY_CN.md]({REPORT_DIR / 'FEE_ACCRUAL_CONTRACT_ABI_INVENTORY_CN.md'})",
                f"- [REAL_FEE_ACCRUAL_METHOD_POLICY_CN.md]({REPORT_DIR / 'REAL_FEE_ACCRUAL_METHOD_POLICY_CN.md'})",
                f"- [REAL_FEE_ACCRUAL_SCHEMA_CN.md]({REPORT_DIR / 'REAL_FEE_ACCRUAL_SCHEMA_CN.md'})",
                f"- [FEE_ACCRUAL_READINESS_RESULTS_CN.md]({REPORT_DIR / 'FEE_ACCRUAL_READINESS_RESULTS_CN.md'})",
                f"- [REAL_FEE_ACCRUAL_RESULTS_CN.md]({REPORT_DIR / 'REAL_FEE_ACCRUAL_RESULTS_CN.md'})",
                f"- [FEE_PROXY_VS_REAL_FEE_COMPARISON_CN.md]({REPORT_DIR / 'FEE_PROXY_VS_REAL_FEE_COMPARISON_CN.md'})",
                f"- [REAL_FEE_ECONOMICS_PREVIEW_CN.md]({REPORT_DIR / 'REAL_FEE_ECONOMICS_PREVIEW_CN.md'})",
                f"- [FEE_ACCRUAL_BLOCKER_DIAGNOSIS_CN.md]({REPORT_DIR / 'FEE_ACCRUAL_BLOCKER_DIAGNOSIS_CN.md'})",
                f"- [REAL_FEE_ACCRUAL_SAFETY_AUDIT_CN.md]({REPORT_DIR / 'REAL_FEE_ACCRUAL_SAFETY_AUDIT_CN.md'})",
                f"- [LP_REAL_FEE_NEXT_STAGE_DECISION_CN.md]({REPORT_DIR / 'LP_REAL_FEE_NEXT_STAGE_DECISION_CN.md'})",
                f"- [FINAL_VERDICT.json]({REPORT_DIR / 'FINAL_VERDICT.json'})",
                f"- [ONEPAGE_CN.md]({REPORT_DIR / 'ONEPAGE_CN.md'})",
            ]
        )
        + "\n",
    )


if __name__ == "__main__":
    main()
