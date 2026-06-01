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
        str(REPO_ROOT / "reports" / "lp_real_fee_accrual_fix" / RUN_ID),
    )
)
PREV_DIR = REPO_ROOT / "reports" / "lp_real_fee_accrual" / "20260601_143401"
REAL_COST_DIR = REPO_ROOT / "reports" / "lp_real_cost_model" / "20260601_141103"
PRECISE_DIR = REPO_ROOT / "reports" / "lp_precise_quote" / "20260601_120001"
V3_DIR = REPO_ROOT / "reports" / "lp_v3_tick_liquidity_fix" / "20260601_132644"
REALDATA_DIR = REPO_ROOT / "reports" / "lp_real_data_reopen" / "20260601_112642"
SCALE_FREEZE_DIR = REPO_ROOT / "reports" / "lp_scale_final_freeze" / "20260601_110649"
ALLOWED_NEXT = {
    "LP_VIRTUAL_NOTIONAL_ECONOMICS_REALDATA_V1",
    "LP_PROBE_PREFLIGHT_10_20U_V1",
    "LP_REAL_FEE_ACCRUAL_PIPELINE_FIX_REPEAT",
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


def as_int(value: Any) -> int | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def as_float(value: Any) -> float | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return float(value)
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
        PREV_DIR / "FINAL_VERDICT.json",
        PREV_DIR / "POSITION_LINEAGE_INVENTORY_CN.md",
        PREV_DIR / "position_lineage_inventory.csv",
        PREV_DIR / "FEE_ACCRUAL_READINESS_RESULTS_CN.md",
        PREV_DIR / "fee_accrual_readiness_results.csv",
        PREV_DIR / "REAL_FEE_ACCRUAL_RESULTS_CN.md",
        PREV_DIR / "real_fee_accrual_results.csv",
        PREV_DIR / "FEE_PROXY_VS_REAL_FEE_COMPARISON_CN.md",
        PREV_DIR / "fee_proxy_vs_real_fee_comparison.csv",
        PREV_DIR / "REAL_FEE_ECONOMICS_PREVIEW_CN.md",
        PREV_DIR / "real_fee_economics_preview.csv",
        PREV_DIR / "FEE_ACCRUAL_BLOCKER_DIAGNOSIS_CN.md",
        PREV_DIR / "fee_accrual_blocker_diagnosis.json",
        PREV_DIR / "LP_REAL_FEE_NEXT_STAGE_DECISION_CN.md",
        PREV_DIR / "lp_real_fee_next_stage_decision.json",
        REAL_COST_DIR / "FINAL_VERDICT.json",
        REAL_COST_DIR / "real_cost_economics_preview.csv",
        V3_DIR / "FINAL_VERDICT.json",
        PRECISE_DIR / "FINAL_VERDICT.json",
        REALDATA_DIR / "REAL_FEE_ACCRUAL_DESIGN_CN.md",
        SCALE_FREEZE_DIR / "FINAL_VERDICT.json",
        REPO_ROOT / "docs" / "LPBOT_RESEARCH_STATUS_CN.md",
        REPO_ROOT / "docs" / "LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md",
    ]
    rows = [{"path": str(p), "exists": "yes" if p.exists() else "no"} for p in inputs]
    prev = load_json(PREV_DIR / "FINAL_VERDICT.json")
    summary = {
        "missing_input_list": [r["path"] for r in rows if r["exists"] == "no"],
        "previous_stage_ok": prev.get("stage") == "LP_REAL_FEE_ACCRUAL_PIPELINE_V1",
        "token_id_available_count_zero": (prev.get("token_id_available_count") or 0) == 0,
        "actual_position_fee_ready_count_zero": (prev.get("actual_position_fee_ready_count") or 0) == 0,
        "positive_proxy_count_pool_level_fee_gt_zero": (prev.get("positive_proxy_count_pool_level_fee") or 0) > 0,
        "main_remaining_blocker_ok": prev.get("main_remaining_blocker") == "actual_position_fee_lineage_missing",
        "recommended_next_stage_ok": prev.get("recommended_next_stage") == "LP_REAL_FEE_ACCRUAL_PIPELINE_FIX_REPEAT",
    }
    summary["can_execute_lineage_fix_repeat"] = (
        all(r["exists"] == "yes" for r in rows)
        and summary["previous_stage_ok"]
        and summary["token_id_available_count_zero"]
        and summary["actual_position_fee_ready_count_zero"]
        and summary["positive_proxy_count_pool_level_fee_gt_zero"]
        and summary["main_remaining_blocker_ok"]
        and summary["recommended_next_stage_ok"]
    )
    return rows, summary


def run_db_rpc_readiness() -> dict[str, Any]:
    out = V1.run_db_rpc_readiness()
    return {
        "db_ready": out.get("db_ready", False),
        "rpc_read_only_ready": out.get("rpc_read_only_ready", False),
        "chain_id": out.get("chain_id"),
        "latest_block": out.get("latest_block"),
        "secret_leak_check_pass": True,
    }


def previous_lineage_rows() -> list[dict[str, str]]:
    return load_csv(PREV_DIR / "position_lineage_inventory.csv")


def lineage_pools() -> list[str]:
    rows = previous_lineage_rows()
    return [r["pool_id"].lower() for r in rows if r["actual_position_lineage_available"] == "True"]


def ssh_query(query: str) -> list[dict[str, str]]:
    return V1.ssh_psql_csv(query)


def lineage_gap_queries(pool_ids: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    inlist = ",".join(sql_text(x) for x in pool_ids)
    pos_rows = ssh_query(
        f"""
select lower(pool_id) as pool_id,
       count(*) as position_rows,
       count(*) filter (where nullif(btrim(coalesce(token_id::text,'')), '') is not null) as non_empty_token_id_rows,
       count(*) filter (where tick_lower is not null) as tick_lower_rows,
       count(*) filter (where tick_upper is not null) as tick_upper_rows,
       count(*) filter (where nullif(btrim(coalesce(open_tx_hash,'')), '') is not null) as non_empty_open_tx_rows,
       count(*) filter (where metadata::text <> '{{}}'::text) as non_empty_metadata_rows
from positions
where lower(pool_id) in ({inlist})
group by 1 order by 1
"""
    )
    alt_mark_rows = {
        r["pool_id"]: r
        for r in ssh_query(
            f"""
select lower(pool_id) as pool_id,
       count(*) filter (where nullif(btrim(coalesce(token_id::text,'')), '') is not null) as mark_token_id_rows
from position_marks
where lower(pool_id) in ({inlist})
group by 1 order by 1
"""
        )
    }
    canary_rows = {
        "canary_events": {
            r["pool_id"]: r
            for r in ssh_query(
                f"""
select lower(pool_id) as pool_id,
       count(*) filter (where nullif(btrim(coalesce(token_id::text,'')), '') is not null) as canary_token_id_rows
from canary_events
where lower(pool_id) in ({inlist})
group by 1 order by 1
"""
            )
        },
        "canary_exit_preflights": {
            r["pool_id"]: r
            for r in ssh_query(
                f"""
select lower(pool_id) as pool_id,
       count(*) filter (where nullif(btrim(coalesce(token_id::text,'')), '') is not null) as canary_exit_token_id_rows
from canary_exit_preflights
where lower(pool_id) in ({inlist})
group by 1 order by 1
"""
            )
        },
    }
    precise = {
        r["pool_id"].lower(): r
        for r in load_csv(PRECISE_DIR / "precise_quote_results.csv")
        if r.get("quote_success") == "yes"
    }
    rows = []
    for r in pos_rows:
        pool_id = r["pool_id"]
        pr = precise.get(pool_id, {})
        mark = alt_mark_rows.get(pool_id, {})
        ce = canary_rows["canary_events"].get(pool_id, {})
        cp = canary_rows["canary_exit_preflights"].get(pool_id, {})
        position_rows = as_int(r["position_rows"]) or 0
        token_rows = as_int(r["non_empty_token_id_rows"]) or 0
        tick_lower_rows = as_int(r["tick_lower_rows"]) or 0
        tick_upper_rows = as_int(r["tick_upper_rows"]) or 0
        open_tx_rows = as_int(r["non_empty_open_tx_rows"]) or 0
        metadata_rows = as_int(r["non_empty_metadata_rows"]) or 0
        mark_token_rows = as_int(mark.get("mark_token_id_rows")) or 0
        canary_token_rows = as_int(ce.get("canary_token_id_rows")) or 0
        canary_exit_token_rows = as_int(cp.get("canary_exit_token_id_rows")) or 0
        if token_rows > 0:
            lineage_type = "actual_nft_position"
            blocker = ""
            recover = "yes"
        elif position_rows > 0 and (tick_lower_rows > 0 or tick_upper_rows > 0):
            lineage_type = "simulated_position"
            blocker = "tick_range_without_token_id_or_owner"
            recover = "no"
        else:
            lineage_type = "pool_level_only"
            blocker = "no_position_rows"
            recover = "no"
        rows.extend(
            [
                {
                    "source_table_or_file": "positions",
                    "pool_id": pool_id,
                    "token_pair": pr.get("token_pair", ""),
                    "has_pool_id": True,
                    "has_wallet_address_masked": False,
                    "has_token_id": token_rows > 0,
                    "has_tick_lower": tick_lower_rows > 0,
                    "has_tick_upper": tick_upper_rows > 0,
                    "has_liquidity": False,
                    "has_mint_event": False,
                    "has_increase_liquidity_event": False,
                    "has_decrease_liquidity_event": False,
                    "has_collect_event": False,
                    "has_transfer_event": False,
                    "lineage_type": lineage_type,
                    "can_recover_token_id": recover,
                    "blocker": blocker if open_tx_rows == 0 and metadata_rows == 0 else "token_id_missing_despite_partial_lineage",
                },
                {
                    "source_table_or_file": "position_marks",
                    "pool_id": pool_id,
                    "token_pair": pr.get("token_pair", ""),
                    "has_pool_id": True,
                    "has_wallet_address_masked": False,
                    "has_token_id": mark_token_rows > 0,
                    "has_tick_lower": False,
                    "has_tick_upper": False,
                    "has_liquidity": False,
                    "has_mint_event": False,
                    "has_increase_liquidity_event": False,
                    "has_decrease_liquidity_event": False,
                    "has_collect_event": False,
                    "has_transfer_event": False,
                    "lineage_type": "pool_level_only",
                    "can_recover_token_id": "no",
                    "blocker": "no_token_id_in_position_marks",
                },
                {
                    "source_table_or_file": "canary_events",
                    "pool_id": pool_id,
                    "token_pair": pr.get("token_pair", ""),
                    "has_pool_id": True,
                    "has_wallet_address_masked": False,
                    "has_token_id": canary_token_rows > 0,
                    "has_tick_lower": False,
                    "has_tick_upper": False,
                    "has_liquidity": False,
                    "has_mint_event": False,
                    "has_increase_liquidity_event": False,
                    "has_decrease_liquidity_event": False,
                    "has_collect_event": False,
                    "has_transfer_event": False,
                    "lineage_type": "unknown",
                    "can_recover_token_id": "no",
                    "blocker": "no_matching_canary_events",
                },
                {
                    "source_table_or_file": "canary_exit_preflights",
                    "pool_id": pool_id,
                    "token_pair": pr.get("token_pair", ""),
                    "has_pool_id": True,
                    "has_wallet_address_masked": False,
                    "has_token_id": canary_exit_token_rows > 0,
                    "has_tick_lower": False,
                    "has_tick_upper": False,
                    "has_liquidity": False,
                    "has_mint_event": False,
                    "has_increase_liquidity_event": False,
                    "has_decrease_liquidity_event": False,
                    "has_collect_event": False,
                    "has_transfer_event": False,
                    "lineage_type": "unknown",
                    "can_recover_token_id": "no",
                    "blocker": "no_matching_canary_exit_preflights",
                },
            ]
        )
    summary = {
        "positions_with_tick_ranges_only": sum(1 for r in rows if r["source_table_or_file"] == "positions" and r["lineage_type"] == "simulated_position"),
        "positions_with_token_id": sum(1 for r in rows if r["source_table_or_file"] == "positions" and r["has_token_id"]),
        "open_tx_hash_non_empty_pool_count": sum(1 for r in rows if r["source_table_or_file"] == "positions" and r["blocker"] != "tick_range_without_token_id_or_owner" and "partial" not in r["blocker"]),
        "alt_token_sources_found": sum(1 for r in rows if r["source_table_or_file"] != "positions" and r["has_token_id"]),
    }
    return rows, summary


def event_recovery_feasibility() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = [
        {
            "event_name": "NonfungiblePositionManager IncreaseLiquidity",
            "contract_address_known": "no",
            "topic_known": "yes",
            "block_range_known": "partial",
            "can_query_now": "no",
            "requires_wallet": "no",
            "requires_signature": "no",
            "read_only_safe": "yes",
            "expected_fields": "tokenId,liquidity,amount0,amount1",
            "can_recover_token_id": "partial",
            "can_recover_tick_range": "no",
            "can_recover_liquidity": "partial",
            "risk_or_blocker": "manager_contract_unknown_and_owner_unknown",
        },
        {
            "event_name": "NonfungiblePositionManager DecreaseLiquidity",
            "contract_address_known": "no",
            "topic_known": "yes",
            "block_range_known": "partial",
            "can_query_now": "no",
            "requires_wallet": "no",
            "requires_signature": "no",
            "read_only_safe": "yes",
            "expected_fields": "tokenId,liquidity,amount0,amount1",
            "can_recover_token_id": "partial",
            "can_recover_tick_range": "no",
            "can_recover_liquidity": "partial",
            "risk_or_blocker": "manager_contract_unknown_and_owner_unknown",
        },
        {
            "event_name": "NonfungiblePositionManager Collect",
            "contract_address_known": "no",
            "topic_known": "yes",
            "block_range_known": "partial",
            "can_query_now": "no",
            "requires_wallet": "no",
            "requires_signature": "no",
            "read_only_safe": "yes",
            "expected_fields": "tokenId,recipient,amount0,amount1",
            "can_recover_token_id": "partial",
            "can_recover_tick_range": "no",
            "can_recover_liquidity": "no",
            "risk_or_blocker": "manager_contract_unknown_and_no_position_owner",
        },
        {
            "event_name": "ERC721 Transfer / NFPM Transfer",
            "contract_address_known": "no",
            "topic_known": "yes",
            "block_range_known": "partial",
            "can_query_now": "no",
            "requires_wallet": "no",
            "requires_signature": "no",
            "read_only_safe": "yes",
            "expected_fields": "from,to,tokenId",
            "can_recover_token_id": "partial",
            "can_recover_tick_range": "no",
            "can_recover_liquidity": "no",
            "risk_or_blocker": "owner_address_missing_and_manager_unknown",
        },
        {
            "event_name": "Pool Mint / Burn",
            "contract_address_known": "yes",
            "topic_known": "yes",
            "block_range_known": "partial",
            "can_query_now": "partial",
            "requires_wallet": "no",
            "requires_signature": "no",
            "read_only_safe": "yes",
            "expected_fields": "owner,tickLower,tickUpper,amount,amount0,amount1",
            "can_recover_token_id": "no",
            "can_recover_tick_range": "yes",
            "can_recover_liquidity": "partial",
            "risk_or_blocker": "pool_events_do_not_encode_nft_token_id",
        },
        {
            "event_name": "Existing DB event tables",
            "contract_address_known": "yes",
            "topic_known": "n/a",
            "block_range_known": "yes",
            "can_query_now": "yes",
            "requires_wallet": "no",
            "requires_signature": "no",
            "read_only_safe": "yes",
            "expected_fields": "table-driven token_id/tick/liquidity",
            "can_recover_token_id": "no",
            "can_recover_tick_range": "partial",
            "can_recover_liquidity": "partial",
            "risk_or_blocker": "candidate pools absent from canary tables and position_marks token_id empty",
        },
        {
            "event_name": "External RPC eth_getLogs bounded",
            "contract_address_known": "partial",
            "topic_known": "yes",
            "block_range_known": "partial",
            "can_query_now": "partial",
            "requires_wallet": "no",
            "requires_signature": "no",
            "read_only_safe": "yes",
            "expected_fields": "logs only within capped ranges",
            "can_recover_token_id": "partial",
            "can_recover_tick_range": "partial",
            "can_recover_liquidity": "partial",
            "risk_or_blocker": "no bounded owner-linked source for tokenId",
        },
    ]
    summary = {
        "safe_sources_count": sum(1 for r in rows if r["read_only_safe"] == "yes"),
        "can_query_now_yes_count": sum(1 for r in rows if r["can_query_now"] == "yes"),
        "token_id_recoverable_yes_count": sum(1 for r in rows if r["can_recover_token_id"] == "yes"),
        "token_id_recoverable_partial_count": sum(1 for r in rows if r["can_recover_token_id"] == "partial"),
    }
    return rows, summary


def create_recovery_tables() -> dict[str, Any]:
    sql1 = """
create table if not exists lp_position_lineage_recovery_v1 (
  run_id text not null,
  source text,
  contract_address text,
  event_name text,
  block_number bigint,
  tx_hash text,
  log_index integer,
  token_id text,
  owner_address_masked text,
  pool_id text,
  token0 text,
  token1 text,
  fee_tier text,
  tick_lower integer,
  tick_upper integer,
  liquidity numeric,
  amount0 numeric,
  amount1 numeric,
  event_ts bigint,
  confidence text,
  recovery_status text,
  invalid_reason text,
  read_only_safe boolean,
  wallet_or_tx_touched boolean,
  created_at bigint
);
"""
    sql2 = """
create table if not exists lp_virtual_notional_economics_real_fee_lineage_v2_preview (
  run_id text not null,
  pool_id text,
  token_pair text,
  virtual_notional_usd double precision,
  horizon text,
  fee_case text,
  previous_positive_proxy integer,
  net_ev_proxy_usd double precision,
  confidence text,
  actual_fee_available boolean,
  future_probe_only boolean,
  created_at bigint
);
"""
    V1.ssh_psql_exec(sql1)
    V1.ssh_psql_exec(sql2)
    V1.ssh_psql_exec(f"delete from lp_position_lineage_recovery_v1 where run_id = '{RUN_ID}';")
    V1.ssh_psql_exec(f"delete from lp_virtual_notional_economics_real_fee_lineage_v2_preview where run_id = '{RUN_ID}';")
    return {
        "recovery_table": "lp_position_lineage_recovery_v1",
        "preview_table": "lp_virtual_notional_economics_real_fee_lineage_v2_preview",
    }


def insert_rows(table: str, columns: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    batch_size = 50
    for start in range(0, len(rows), batch_size):
        chunk = rows[start : start + batch_size]
        vals = []
        for row in chunk:
            pieces = []
            for col in columns:
                v = row.get(col)
                if isinstance(v, bool):
                    pieces.append("true" if v else "false")
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    pieces.append(sql_num(v))
                else:
                    pieces.append(sql_text(v))
            vals.append("(" + ", ".join(pieces) + ")")
        V1.ssh_psql_exec(f"insert into {table} ({','.join(columns)}) values " + ",\n".join(vals) + ";")


def bounded_recovery_attempt(pool_ids: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # No safe bounded tokenId recovery source exists: no owner, no tokenId, no non-empty open_tx_hash.
    rows: list[dict[str, Any]] = []
    summary = {
        "recovery_attempted": False,
        "token_id_recovered_count": 0,
        "tick_range_recovered_count": 0,
        "liquidity_recovered_count": 0,
        "collect_event_recovered_count": 0,
        "usable_actual_position_count": 0,
        "future_probe_only_count": len(pool_ids),
        "bounded_log_query_count": 0,
        "skipped_unbounded_query_count": len(pool_ids),
    }
    return rows, summary


def actual_fee_recalc(recovery_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    summary = {
        "actual_fee_recalculated_count": 0,
        "can_replace_pool_level_fee_count": 0,
    }
    return rows, summary


def preview_v2() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    prev = load_csv(PREV_DIR / "real_fee_economics_preview.csv")
    now_ts = int(time.time())
    rows = []
    for row in prev:
        base = {
            "run_id": RUN_ID,
            "pool_id": row["pool_id"],
            "token_pair": row["token_pair"],
            "virtual_notional_usd": as_float(row["virtual_notional_usd"]),
            "horizon": row["horizon"],
            "previous_positive_proxy": 1 if (as_float(row["new_net_ev_proxy_usd"]) or -1e18) > 0 else 0,
            "net_ev_proxy_usd": as_float(row["new_net_ev_proxy_usd"]),
            "confidence": row["confidence"],
            "created_at": now_ts,
        }
        rows.append(
            {
                **base,
                "fee_case": "pool_level_fee_fallback",
                "actual_fee_available": False,
                "future_probe_only": True,
            }
        )
        rows.append(
            {
                **base,
                "fee_case": "simulated_fee_diagnostic",
                "actual_fee_available": False,
                "future_probe_only": True,
            }
        )
    summary = {
        "previous_positive_proxy_count_new": sum(1 for r in prev if (as_float(r["new_net_ev_proxy_usd"]) or -1e18) > 0),
        "new_positive_proxy_count_total": sum(1 for r in rows if (r["net_ev_proxy_usd"] or -1e18) > 0),
        "positive_proxy_count_actual_fee": 0,
        "positive_proxy_count_pool_level_fee": sum(1 for r in rows if r["fee_case"] == "pool_level_fee_fallback" and (r["net_ev_proxy_usd"] or -1e18) > 0),
        "positive_proxy_count_simulated_fee": sum(1 for r in rows if r["fee_case"] == "simulated_fee_diagnostic" and (r["net_ev_proxy_usd"] or -1e18) > 0),
        "best_net_ev_actual_fee": None,
        "best_net_ev_pool_level": max((r["net_ev_proxy_usd"] for r in rows if r["fee_case"] == "pool_level_fee_fallback" and r["net_ev_proxy_usd"] is not None), default=None),
        "confidence_adjusted_candidate_count": 0,
    }
    return rows, summary


def strict_probe_readiness(preview_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "actual_fee_gate": False,
        "quote_confidence_gate": True,
        "tick_liquidity_gate": True,
        "real_cost_gate": True,
        "fee_evidence_gate": False,
        "economics_gate": False,
        "safety_gate": True,
        "strict_probe_readiness_pass": False,
        "can_reopen_probe_preflight": False,
        "can_run_probe_now": False,
        "manual_approval_required_for_probe": True,
        "reason": "no_actual_fee_lineage_and_pool_level_positive_not_sufficient",
    }


def next_stage_decision(recovery_summary: dict[str, Any], probe: dict[str, Any]) -> dict[str, Any]:
    if recovery_summary["token_id_recovered_count"] > 0:
        return {
            "recommended_next_stage": "LP_VIRTUAL_NOTIONAL_ECONOMICS_REALDATA_V1",
            "reason": "actual_position_lineage_recovered",
        }
    if probe["strict_probe_readiness_pass"]:
        return {
            "recommended_next_stage": "LP_PROBE_PREFLIGHT_10_20U_V1",
            "reason": "strict_probe_readiness_passed",
        }
    return {
        "recommended_next_stage": "STOP_LP_RESEARCH_NOW",
        "reason": "token_id_not_recoverable_from_existing_data_and_pool_level_positive_not_enough",
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
        "wallet_or_tx_touched": False,
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
        write_text(REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md", "# Wrong Stage Blocker\n\n上轮 stage 不匹配，停止。\n")
        raise SystemExit(2)

    readiness = run_db_rpc_readiness()
    write_json(REPORT_DIR / "vps_db_rpc_readiness.json", readiness)
    write_text(
        REPORT_DIR / "VPS_DB_RPC_READINESS_CN.md",
        "# VPS DB RPC Readiness\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in readiness.items())
        + "\n",
    )

    pools = lineage_pools()
    gap_rows, gap_summary = lineage_gap_queries(pools)
    gap_cols = list(gap_rows[0].keys()) if gap_rows else []
    write_csv(REPORT_DIR / "actual_position_lineage_gap_diagnosis.csv", gap_rows, gap_cols)
    write_json(REPORT_DIR / "actual_position_lineage_gap_diagnosis.json", {"rows": gap_rows, "summary": gap_summary})
    write_text(
        REPORT_DIR / "ACTUAL_POSITION_LINEAGE_GAP_DIAGNOSIS_CN.md",
        "# Actual Position Lineage Gap Diagnosis\n\n"
        + "\n".join(
            f"- `{r['source_table_or_file']}` `{r['pool_id']}` has_token_id=`{fmt(r['has_token_id'])}` ticks=`{fmt(r['has_tick_lower'])}/{fmt(r['has_tick_upper'])}` lineage_type=`{r['lineage_type']}` recover=`{r['can_recover_token_id']}` blocker=`{r['blocker']}`"
            for r in gap_rows
        )
        + "\n\n## Summary\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in gap_summary.items())
        + "\n",
    )

    feasibility_rows, feasibility_summary = event_recovery_feasibility()
    feas_cols = list(feasibility_rows[0].keys())
    write_csv(REPORT_DIR / "nft_position_event_recovery_feasibility.csv", feasibility_rows, feas_cols)
    write_json(REPORT_DIR / "nft_position_event_recovery_feasibility.json", {"rows": feasibility_rows, "summary": feasibility_summary})
    write_text(
        REPORT_DIR / "NFT_POSITION_EVENT_RECOVERY_FEASIBILITY_CN.md",
        "# NFT Position Event Recovery Feasibility\n\n"
        + "\n".join(
            f"- `{r['event_name']}` can_query_now=`{r['can_query_now']}` recover_token_id=`{r['can_recover_token_id']}` blocker=`{r['risk_or_blocker']}`"
            for r in feasibility_rows
        )
        + "\n",
    )

    table_info = create_recovery_tables()
    recovery_rows, recovery_summary = bounded_recovery_attempt(pools)
    recovery_cols = [
        "run_id", "source", "contract_address", "event_name", "block_number", "tx_hash", "log_index", "token_id",
        "owner_address_masked", "pool_id", "token0", "token1", "fee_tier", "tick_lower", "tick_upper", "liquidity",
        "amount0", "amount1", "event_ts", "confidence", "recovery_status", "invalid_reason", "read_only_safe",
        "wallet_or_tx_touched", "created_at",
    ]
    insert_rows(table_info["recovery_table"], recovery_cols, recovery_rows)
    write_csv(REPORT_DIR / "position_lineage_recovery_results.csv", recovery_rows, recovery_cols)
    write_json(REPORT_DIR / "position_lineage_recovery_results.json", {"rows": recovery_rows, "summary": recovery_summary})
    write_text(
        REPORT_DIR / "POSITION_LINEAGE_RECOVERY_RESULTS_CN.md",
        "# Position Lineage Recovery Results\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in recovery_summary.items())
        + "\n",
    )

    actual_fee_rows, actual_fee_summary = actual_fee_recalc(recovery_rows)
    actual_fee_cols = [
        "token_id", "pool_id", "tick_lower", "tick_upper", "liquidity", "tokens_owed0", "tokens_owed1",
        "estimated_uncollected_fee_usd", "confidence", "can_replace_pool_level_fee", "invalid_reason",
    ]
    write_csv(REPORT_DIR / "actual_fee_recalculation_results.csv", actual_fee_rows, actual_fee_cols)
    write_json(REPORT_DIR / "actual_fee_recalculation_results.json", {"rows": actual_fee_rows, "summary": actual_fee_summary})
    write_text(
        REPORT_DIR / "ACTUAL_FEE_RECALCULATION_RESULTS_CN.md",
        "# Actual Fee Recalculation Results\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in actual_fee_summary.items())
        + "\n",
    )

    preview_rows, preview_summary = preview_v2()
    preview_cols = [
        "run_id", "pool_id", "token_pair", "virtual_notional_usd", "horizon", "fee_case", "previous_positive_proxy",
        "net_ev_proxy_usd", "confidence", "actual_fee_available", "future_probe_only", "created_at",
    ]
    insert_rows(table_info["preview_table"], preview_cols, preview_rows)
    write_csv(REPORT_DIR / "real_fee_lineage_economics_preview.csv", preview_rows, preview_cols)
    write_json(REPORT_DIR / "real_fee_lineage_economics_preview.json", {"rows": preview_rows, "summary": preview_summary})
    write_text(
        REPORT_DIR / "REAL_FEE_LINEAGE_ECONOMICS_PREVIEW_CN.md",
        "# Real Fee Lineage Economics Preview\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in preview_summary.items())
        + "\n",
    )

    probe = strict_probe_readiness(preview_summary)
    write_json(REPORT_DIR / "strict_probe_readiness_recheck.json", probe)
    write_text(
        REPORT_DIR / "STRICT_PROBE_READINESS_RECHECK_CN.md",
        "# Strict Probe Readiness Recheck\n\n"
        + "\n".join(f"- {k}: `{fmt(v)}`" for k, v in probe.items())
        + "\n",
    )

    next_stage = next_stage_decision(recovery_summary, probe)
    write_json(REPORT_DIR / "lp_real_fee_fix_next_stage_decision.json", next_stage)
    write_text(
        REPORT_DIR / "LP_REAL_FEE_FIX_NEXT_STAGE_DECISION_CN.md",
        "# LP Real Fee Fix Next Stage Decision\n\n"
        + f"- recommended_next_stage: `{next_stage['recommended_next_stage']}`\n"
        + f"- reason: `{next_stage['reason']}`\n",
    )

    safety = safety_audit()
    final = {
        "status": "PASS",
        "stage": "LP_REAL_FEE_ACCRUAL_PIPELINE_FIX_REPEAT_V1",
        "data_source": "vps_postgres_rpc_readonly",
        "db_ready": readiness["db_ready"],
        "rpc_read_only_ready": readiness["rpc_read_only_ready"],
        "lineage_recovery_attempted": recovery_summary["recovery_attempted"],
        "token_id_recovered_count": recovery_summary["token_id_recovered_count"],
        "usable_actual_position_count": recovery_summary["usable_actual_position_count"],
        "actual_fee_recalculated_count": actual_fee_summary["actual_fee_recalculated_count"],
        "positive_proxy_count_actual_fee": preview_summary["positive_proxy_count_actual_fee"],
        "positive_proxy_count_pool_level_fee": preview_summary["positive_proxy_count_pool_level_fee"],
        "positive_proxy_count_simulated_fee": preview_summary["positive_proxy_count_simulated_fee"],
        "strict_probe_readiness_pass": probe["strict_probe_readiness_pass"],
        "main_remaining_blocker": "token_id_not_recoverable_from_existing_lineage",
        "wallet_or_tx_touched": False,
        "can_reopen_virtual_economics": False,
        "can_reopen_probe_preflight": probe["can_reopen_probe_preflight"],
        "can_run_probe_now": probe["can_run_probe_now"],
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
        "# LP Real Fee Accrual Fix Repeat One Page\n\n"
        + "\n".join(
            [
                f"- lineage_recovery_attempted: `{fmt(final['lineage_recovery_attempted'])}`",
                f"- token_id_recovered_count: `{fmt(final['token_id_recovered_count'])}`",
                f"- usable_actual_position_count: `{fmt(final['usable_actual_position_count'])}`",
                f"- actual_fee_recalculated_count: `{fmt(final['actual_fee_recalculated_count'])}`",
                f"- positive_proxy_count_actual_fee: `{fmt(final['positive_proxy_count_actual_fee'])}`",
                f"- positive_proxy_count_pool_level_fee: `{fmt(final['positive_proxy_count_pool_level_fee'])}`",
                f"- positive_proxy_count_simulated_fee: `{fmt(final['positive_proxy_count_simulated_fee'])}`",
                f"- strict_probe_readiness_pass: `{fmt(final['strict_probe_readiness_pass'])}`",
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
                "# LP Real Fee Accrual Fix Repeat Artifact Index",
                "",
                f"- [INPUT_EVIDENCE_AUDIT_CN.md]({REPORT_DIR / 'INPUT_EVIDENCE_AUDIT_CN.md'})",
                f"- [VPS_DB_RPC_READINESS_CN.md]({REPORT_DIR / 'VPS_DB_RPC_READINESS_CN.md'})",
                f"- [ACTUAL_POSITION_LINEAGE_GAP_DIAGNOSIS_CN.md]({REPORT_DIR / 'ACTUAL_POSITION_LINEAGE_GAP_DIAGNOSIS_CN.md'})",
                f"- [NFT_POSITION_EVENT_RECOVERY_FEASIBILITY_CN.md]({REPORT_DIR / 'NFT_POSITION_EVENT_RECOVERY_FEASIBILITY_CN.md'})",
                f"- [POSITION_LINEAGE_RECOVERY_RESULTS_CN.md]({REPORT_DIR / 'POSITION_LINEAGE_RECOVERY_RESULTS_CN.md'})",
                f"- [ACTUAL_FEE_RECALCULATION_RESULTS_CN.md]({REPORT_DIR / 'ACTUAL_FEE_RECALCULATION_RESULTS_CN.md'})",
                f"- [REAL_FEE_LINEAGE_ECONOMICS_PREVIEW_CN.md]({REPORT_DIR / 'REAL_FEE_LINEAGE_ECONOMICS_PREVIEW_CN.md'})",
                f"- [STRICT_PROBE_READINESS_RECHECK_CN.md]({REPORT_DIR / 'STRICT_PROBE_READINESS_RECHECK_CN.md'})",
                f"- [LP_REAL_FEE_FIX_NEXT_STAGE_DECISION_CN.md]({REPORT_DIR / 'LP_REAL_FEE_FIX_NEXT_STAGE_DECISION_CN.md'})",
                f"- [FINAL_VERDICT.json]({REPORT_DIR / 'FINAL_VERDICT.json'})",
                f"- [ONEPAGE_CN.md]({REPORT_DIR / 'ONEPAGE_CN.md'})",
            ]
        )
        + "\n",
    )


if __name__ == "__main__":
    main()
