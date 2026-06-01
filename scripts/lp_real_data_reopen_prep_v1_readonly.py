#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUN_ID = os.environ.get("RUN_ID_OVERRIDE", "20260601_112642")
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/Users/bendu/lp-bot/v3"))
REPORT_DIR = Path(
    os.environ.get(
        "REPORT_DIR_OVERRIDE",
        str(REPO_ROOT / "reports" / "lp_real_data_reopen" / RUN_ID),
    )
)
WORKSPACE = "/opt/lpbot/lp-bot-v3-origin-check"
ALLOWED_NEXT = {
    "LP_PRECISE_QUOTE_PIPELINE_V1",
    "LP_V3_TICK_LIQUIDITY_PIPELINE_V1",
    "LP_REAL_FEE_ACCRUAL_PIPELINE_V1",
    "LP_REAL_COST_MODEL_PIPELINE_V1",
    "REAL_DATA_PIPELINE_DESIGN_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}
INPUTS = [
    REPO_ROOT / "reports" / "lp_scale_final_freeze" / "20260601_110649" / "FINAL_VERDICT.json",
    REPO_ROOT / "reports" / "lp_scale_final_freeze" / "20260601_110649" / "SCALE_ECONOMICS_KEY_FINDINGS_CN.md",
    REPO_ROOT / "reports" / "lp_scale_final_freeze" / "20260601_110649" / "WHY_SCALE_DID_NOT_FIX_EV_CN.md",
    REPO_ROOT / "reports" / "lp_scale_final_freeze" / "20260601_110649" / "WHY_NO_PROBE_CN.md",
    REPO_ROOT / "reports" / "lp_scale_final_freeze" / "20260601_110649" / "SCALE_REOPEN_CONDITIONS_CN.md",
    REPO_ROOT / "reports" / "lp_il_lvr_pipeline" / "20260601_105452" / "FINAL_VERDICT.json",
    REPO_ROOT / "reports" / "lp_fee_velocity_fix_repeat" / "20260601_103248" / "FINAL_VERDICT.json",
    REPO_ROOT / "reports" / "lp_virtual_notional_economics" / "20260601_094238" / "FINAL_VERDICT.json",
    REPO_ROOT / "reports" / "lp_quote_depth_curve_fix" / "20260601_091739" / "FINAL_VERDICT.json",
    REPO_ROOT / "docs" / "LPBOT_RESEARCH_STATUS_CN.md",
    REPO_ROOT / "docs" / "LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md",
]
FREEZE_VERDICT = INPUTS[0]
IL_LVR_VERDICT = INPUTS[5]
FEE_FIX_VERDICT = INPUTS[6]
VNE_VERDICT = INPUTS[7]
QUOTE_FIX_VERDICT = INPUTS[8]
VNE_CANDIDATES_CSV = REPO_ROOT / "reports" / "lp_virtual_notional_economics" / "20260601_094238" / "virtual_notional_candidate_ranking.csv"
QUOTE_V2_RESULTS_CSV = REPO_ROOT / "reports" / "lp_quote_depth_curve_fix" / "20260601_091739" / "quote_depth_curve_v2_results.csv"
FEE_V1_RESULTS_CSV = REPO_ROOT / "reports" / "lp_fee_velocity_pipeline" / "20260601_100642" / "fee_velocity_results.csv"
IL_LVR_RESULTS_CSV = REPO_ROOT / "reports" / "lp_il_lvr_pipeline" / "20260601_105452" / "il_lvr_proxy_results.csv"


@dataclass
class PoolRow:
    pool_id: str
    token_pair: str
    pool_type: str
    inferred_tier: str
    protocol: str
    chain: str
    fee_bps: str
    tick_value: str
    liquidity_value: str


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


def fmt_bool(value: bool) -> str:
    return "yes" if value else "no"


def redact_secretish(text: str) -> str:
    text = re.sub(r"postgres(?:ql)?://[^\s'\\\"]+", "<redacted-dsn>", text)
    text = re.sub(r"(POSTGRES_DSN|DATABASE_URL|SHADOW_POSTGRES_DSN)=\S+", r"\1=<redacted>", text)
    return text


def ssh_run(script: str) -> subprocess.CompletedProcess[str]:
    remote_cmd = f"cd {shlex.quote(WORKSPACE)} && bash -lc {shlex.quote(script)}"
    return subprocess.run(["ssh", "vps", remote_cmd], capture_output=True, text=True)


def ssh_psql_csv(query: str) -> list[dict[str, str]]:
    remote_python = f"""
import os, subprocess, sys
sql = {query!r}
dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL") or os.environ.get("SHADOW_POSTGRES_DSN")
if not dsn:
    print("missing_dsn", file=sys.stderr)
    raise SystemExit(2)
cmd = ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-P", "footer=off", "-c", f"\\\\copy ({{sql}}) to stdout with csv header"]
proc = subprocess.run(cmd, text=True, capture_output=True)
sys.stderr.write(proc.stderr)
if proc.returncode != 0:
    raise SystemExit(proc.returncode)
sys.stdout.write(proc.stdout)
"""
    script = "\n".join(
        [
            "set -a",
            "source .runtime.shadow.env 2>/dev/null || source .env 2>/dev/null || source .env.chain 2>/dev/null || true",
            "set +a",
            "python3 - <<'PY'",
            remote_python,
            "PY",
        ]
    )
    proc = ssh_run(script)
    if proc.returncode != 0:
        raise RuntimeError(redact_secretish(proc.stderr.strip() or proc.stdout.strip()))
    output = proc.stdout.strip()
    if not output:
        return []
    return list(csv.DictReader(output.splitlines()))


def run_db_quick_check() -> dict[str, Any]:
    script = """
set -a
source .runtime.shadow.env 2>/dev/null || source .env 2>/dev/null || source .env.chain 2>/dev/null || true
set +a
python3 - <<'PY'
import os, sys
dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
print("DSN_PRESENT=", "yes" if dsn else "no")
if not dsn:
    sys.exit(2)
try:
    import psycopg2
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("select current_database(), current_user")
    db, user = cur.fetchone()
    print("DB_CONNECT=ok")
    print("DB_NAME=", db)
    print("DB_USER=", user)
    cur.close()
    conn.close()
except Exception as e:
    print("DB_CONNECT=fail")
    print(type(e).__name__, str(e)[:200])
    sys.exit(3)
PY
"""
    proc = ssh_run(script)
    result: dict[str, Any] = {"stdout": redact_secretish(proc.stdout), "stderr": redact_secretish(proc.stderr), "db_ready": False}
    for line in proc.stdout.splitlines():
        if "DSN_PRESENT=" in line:
            result["dsn_present"] = line.split("=", 1)[1].strip()
        elif "DB_CONNECT=" in line:
            result["db_connect"] = line.split("=", 1)[1].strip()
        elif "DB_NAME=" in line:
            result["db_name"] = line.split("=", 1)[1].strip()
        elif "DB_USER=" in line:
            result["db_user"] = line.split("=", 1)[1].strip()
    result["db_ready"] = result.get("dsn_present") == "yes" and result.get("db_connect") == "ok"
    return result


def input_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = [{"path": str(path), "exists": path.exists()} for path in INPUTS]
    missing = [row["path"] for row in rows if not row["exists"]]
    freeze = load_json(FREEZE_VERDICT) if FREEZE_VERDICT.exists() else {}
    il_lvr = load_json(IL_LVR_VERDICT) if IL_LVR_VERDICT.exists() else {}
    summary = {
        "all_inputs_present": not missing,
        "missing_input_list": missing,
        "scale_economics_frozen": freeze.get("scale_research_freeze_complete") is True,
        "freeze_next_stage_stop": freeze.get("recommended_next_stage") == "STOP_LP_RESEARCH_NOW",
        "real_data_reopen_prep_only": True,
        "can_run_probe_now": bool(il_lvr.get("can_run_probe_now")),
        "tiny_canary_allowed": il_lvr.get("tiny_canary_allowed"),
        "wrong_stage_blocker": freeze.get("stage") != "LP_SCALE_ECONOMICS_FINAL_FREEZE_V1",
    }
    return rows, summary


def infer_pool_type(protocol: str) -> str:
    p = (protocol or "").lower()
    if "slipstream" in p or "v3" in p or "cl" in p:
        return "concentrated_liquidity"
    if "v2" in p or "pair" in p:
        return "constant_product"
    if "solana" in p:
        return "solana_v3_like"
    return "unknown"


def load_candidate_pool_ids(limit: int = 50) -> list[tuple[str, str, str]]:
    seen: set[str] = set()
    pools: list[tuple[str, str, str]] = []
    for row in load_csv(VNE_CANDIDATES_CSV):
        pool_id = row["pool_id"]
        if pool_id in seen:
            continue
        seen.add(pool_id)
        pools.append((pool_id, row.get("token_pair", ""), row.get("inferred_tier", "")))
        if len(pools) >= limit:
            break
    return pools


def fetch_pool_meta(pool_ids: list[str]) -> dict[str, PoolRow]:
    sql_ids = ",".join("'" + pid.replace("'", "''") + "'" for pid in pool_ids)
    query = f"""
select
  p.pool_id,
  concat(coalesce(nullif(ptm.token0_symbol, ''), p.token0), '/', coalesce(nullif(ptm.token1_symbol, ''), p.token1)) as token_pair,
  p.protocol,
  p.chain,
  p.fee_bps,
  p.tier,
  p.tick,
  p.liquidity
from pools p
left join pool_token_metadata ptm using (pool_id)
where p.pool_id in ({sql_ids})
"""
    rows = ssh_psql_csv(query)
    out: dict[str, PoolRow] = {}
    for row in rows:
        protocol = row.get("protocol") or ""
        out[row["pool_id"]] = PoolRow(
            pool_id=row["pool_id"],
            token_pair=row.get("token_pair") or "",
            pool_type=infer_pool_type(protocol),
            inferred_tier=row.get("tier") or "",
            protocol=protocol,
            chain="base" if str(row.get("chain")) == "1" else "solana" if str(row.get("chain")) == "2" else "unknown",
            fee_bps=row.get("fee_bps") or "",
            tick_value=row.get("tick") or "",
            liquidity_value=row.get("liquidity") or "",
        )
    return out


def supporting_pool_sets() -> tuple[set[str], set[str], set[str]]:
    quote_ids = {row["pool_id"] for row in load_csv(QUOTE_V2_RESULTS_CSV)}
    fee_ids = {row["pool_id"] for row in load_csv(FEE_V1_RESULTS_CSV)}
    il_lvr_ids = {row["pool_id"] for row in load_csv(IL_LVR_RESULTS_CSV)}
    return quote_ids, fee_ids, il_lvr_ids


def build_inventory() -> list[dict[str, Any]]:
    return [
        {
            "data_source_name": "NonfungiblePositionManager.positions(tokenId)",
            "data_category": "real_fee_accrual",
            "source_type": "contract_read",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "read_only_safe": "yes",
            "available_now": "partial",
            "required_credentials": "base_rpc_readonly",
            "implementation_complexity": "medium",
            "confidence_if_available": "high",
            "blocker": "tokenId_unknown_without_real_position_nft",
            "recommended_priority": "P2",
        },
        {
            "data_source_name": "UniswapV3Pool.slot0/liquidity/ticks/tickBitmap",
            "data_category": "v3_tick_liquidity",
            "source_type": "contract_read",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "read_only_safe": "yes",
            "available_now": "yes",
            "required_credentials": "base_rpc_readonly",
            "implementation_complexity": "high",
            "confidence_if_available": "high",
            "blocker": "v3_pool_contract_mapping_needed",
            "recommended_priority": "P1",
        },
        {
            "data_source_name": "UniswapV3Pool.positions(positionKey)",
            "data_category": "real_fee_accrual",
            "source_type": "contract_read",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "read_only_safe": "yes",
            "available_now": "partial",
            "required_credentials": "base_rpc_readonly",
            "implementation_complexity": "high",
            "confidence_if_available": "high",
            "blocker": "position_key_needs_owner_and_ticks",
            "recommended_priority": "P2",
        },
        {
            "data_source_name": "Mint/Burn/Collect/IncreaseLiquidity/DecreaseLiquidity logs",
            "data_category": "real_fee_accrual",
            "source_type": "event_logs",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "read_only_safe": "yes",
            "available_now": "partial",
            "required_credentials": "base_rpc_readonly",
            "implementation_complexity": "high",
            "confidence_if_available": "medium",
            "blocker": "actual_position_linkage_missing_without_tokenId_owner",
            "recommended_priority": "P2",
        },
        {
            "data_source_name": "Swap logs",
            "data_category": "real_fee_accrual",
            "source_type": "event_logs",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "read_only_safe": "yes",
            "available_now": "yes",
            "required_credentials": "base_rpc_readonly",
            "implementation_complexity": "medium",
            "confidence_if_available": "medium",
            "blocker": "needs_pool_abi_and_window_selection",
            "recommended_priority": "P1",
        },
        {
            "data_source_name": "QuoterV2 static quote",
            "data_category": "precise_quote",
            "source_type": "rpc_call",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "read_only_safe": "yes",
            "available_now": "yes",
            "required_credentials": "base_rpc_readonly",
            "implementation_complexity": "medium",
            "confidence_if_available": "high",
            "blocker": "quoter_contract_mapping_by_protocol",
            "recommended_priority": "P0",
        },
        {
            "data_source_name": "Pool math fallback",
            "data_category": "precise_quote",
            "source_type": "existing_db",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "read_only_safe": "yes",
            "available_now": "yes",
            "required_credentials": "existing_reports_and_db",
            "implementation_complexity": "medium",
            "confidence_if_available": "medium",
            "blocker": "approximation_only",
            "recommended_priority": "P1",
        },
        {
            "data_source_name": "External aggregator dry quote",
            "data_category": "precise_quote",
            "source_type": "external_api",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "read_only_safe": "yes",
            "available_now": "partial",
            "required_credentials": "public_api_or_api_key_if_provider_requires",
            "implementation_complexity": "medium",
            "confidence_if_available": "medium",
            "blocker": "provider_selection_and_rate_limits",
            "recommended_priority": "P1",
        },
        {
            "data_source_name": "eth_feeHistory / gas oracle",
            "data_category": "real_cost_model",
            "source_type": "rpc_call",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "read_only_safe": "yes",
            "available_now": "yes",
            "required_credentials": "base_rpc_readonly",
            "implementation_complexity": "low",
            "confidence_if_available": "medium",
            "blocker": "needs_cost_scenario_policy",
            "recommended_priority": "P1",
        },
        {
            "data_source_name": "eth_estimateGas dry add/remove liquidity",
            "data_category": "real_cost_model",
            "source_type": "rpc_call",
            "requires_wallet": "no",
            "requires_signature": "no",
            "requires_transaction": "no",
            "read_only_safe": "yes",
            "available_now": "partial",
            "required_credentials": "base_rpc_readonly_and_calldata_builder",
            "implementation_complexity": "high",
            "confidence_if_available": "medium",
            "blocker": "requires_exact_calldata_and_position_params",
            "recommended_priority": "P2",
        },
        {
            "data_source_name": "Actual LP NFT fee accrual after probe",
            "data_category": "real_fee_accrual",
            "source_type": "future_probe_only",
            "requires_wallet": "yes",
            "requires_signature": "yes",
            "requires_transaction": "yes",
            "read_only_safe": "no",
            "available_now": "no",
            "required_credentials": "wallet_nft_and_position_history",
            "implementation_complexity": "high",
            "confidence_if_available": "high",
            "blocker": "future_probe_only",
            "recommended_priority": "REJECT",
        },
        {
            "data_source_name": "Actual realized entry/exit receipts",
            "data_category": "real_cost_model",
            "source_type": "future_probe_only",
            "requires_wallet": "yes",
            "requires_signature": "yes",
            "requires_transaction": "yes",
            "read_only_safe": "no",
            "available_now": "no",
            "required_credentials": "wallet_tx_history",
            "implementation_complexity": "medium",
            "confidence_if_available": "high",
            "blocker": "future_probe_only",
            "recommended_priority": "REJECT",
        },
    ]


def build_readiness_rows() -> list[dict[str, Any]]:
    candidates = load_candidate_pool_ids(limit=50)
    pool_ids = [pool_id for pool_id, _, _ in candidates]
    meta_map = fetch_pool_meta(pool_ids)
    quote_ids, fee_ids, il_lvr_ids = supporting_pool_sets()
    rows: list[dict[str, Any]] = []
    for pool_id, fallback_pair, fallback_tier in candidates:
        meta = meta_map.get(pool_id)
        if meta is None:
            meta = PoolRow(pool_id, fallback_pair, "unknown", fallback_tier, "", "unknown", "", "", "")
        has_v3 = meta.chain == "base" and meta.pool_type == "concentrated_liquidity"
        has_ticks = has_v3 and bool(meta.tick_value or meta.liquidity_value)
        has_quoter = has_v3
        has_fee_tier = bool(meta.fee_bps or meta.inferred_tier)
        has_swap_logs = pool_id in fee_ids or pool_id in il_lvr_ids
        has_position_nft_data = False
        real_fee_ready = "partial" if has_v3 else "no"
        precise_quote_ready = "partial" if (has_quoter and pool_id in quote_ids) else "no"
        tick_ready = "partial" if has_v3 else "no"
        cost_ready = "partial" if (has_swap_logs and has_quoter) else "no"
        if not has_v3:
            blocker = "pool_not_v3_ready"
            next_action = "REAL_DATA_PIPELINE_DESIGN_REPEAT"
        elif not has_position_nft_data:
            blocker = "missing_position_nft_and_real_fee_lineage"
            next_action = "LP_PRECISE_QUOTE_PIPELINE_V1"
        elif not has_fee_tier:
            blocker = "missing_fee_tier"
            next_action = "LP_PRECISE_QUOTE_PIPELINE_V1"
        else:
            blocker = "precise_quote_and_tick_snapshot_not_built"
            next_action = "LP_PRECISE_QUOTE_PIPELINE_V1"
        rows.append(
            {
                "pool_id": pool_id,
                "token_pair": meta.token_pair or fallback_pair,
                "pool_type": meta.pool_type,
                "inferred_tier": meta.inferred_tier or fallback_tier,
                "has_v3_pool_state": fmt_bool(has_v3),
                "has_tick_liquidity_access": fmt_bool(has_ticks or has_v3),
                "has_quoter_access": fmt_bool(has_quoter),
                "has_fee_tier": fmt_bool(has_fee_tier),
                "has_swap_logs": fmt_bool(has_swap_logs),
                "has_position_nft_data": fmt_bool(has_position_nft_data),
                "real_fee_accrual_ready": real_fee_ready,
                "precise_quote_ready": precise_quote_ready,
                "tick_liquidity_ready": tick_ready,
                "real_cost_model_ready": cost_ready,
                "can_reopen_virtual_economics": "no",
                "can_reopen_probe_preflight": "no",
                "primary_blocker": blocker,
                "recommended_next_action": next_action,
            }
        )
    return rows


def markdown_inventory(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# 真实数据源总览",
        "",
        "| data_source_name | category | source_type | wallet | signature | tx | read_only_safe | available_now | priority | blocker |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| `{row['data_source_name']}` | `{row['data_category']}` | `{row['source_type']}` | `{row['requires_wallet']}` | "
            f"`{row['requires_signature']}` | `{row['requires_transaction']}` | `{row['read_only_safe']}` | `{row['available_now']}` | "
            f"`{row['recommended_priority']}` | `{row['blocker']}` |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    ensure_dir(REPORT_DIR)
    db = run_db_quick_check()
    input_rows, input_summary = input_audit()
    if input_summary["wrong_stage_blocker"]:
        write_text(
            REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md",
            "# WRONG STAGE BLOCKER\n\n输入 freeze stage 不是 `LP_SCALE_ECONOMICS_FINAL_FREEZE_V1`，本轮停止。\n",
        )
        raise SystemExit(2)

    write_text(
        REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md",
        "\n".join(
            [
                "# LP Real Data Reopen 输入证据审计",
                "",
                *[f"- `{row['path']}`: `{fmt_bool(row['exists'])}`" for row in input_rows],
                "",
                f"- scale economics 已冻结: `{fmt_bool(input_summary['scale_economics_frozen'])}`",
                f"- recommended_next_stage = STOP_LP_RESEARCH_NOW: `{fmt_bool(input_summary['freeze_next_stage_stop'])}`",
                "- 本轮性质: `real data reopen prep only`",
                f"- can_run_probe_now: `{fmt_bool(input_summary['can_run_probe_now'])}`",
                f"- tiny_canary_allowed: `{input_summary['tiny_canary_allowed']}`",
            ]
        )
        + "\n",
    )
    write_json(REPORT_DIR / "input_evidence_audit.json", input_summary)

    inventory_rows = build_inventory()
    write_text(REPORT_DIR / "REAL_DATA_SOURCE_INVENTORY_CN.md", markdown_inventory(inventory_rows))
    write_json(
        REPORT_DIR / "real_data_source_inventory.json",
        {
            "stage": "LP_REAL_DATA_REOPEN_PREP_V1",
            "db_ready": db["db_ready"],
            "inventory_count": len(inventory_rows),
            "rows": inventory_rows,
        },
    )
    write_csv(
        REPORT_DIR / "real_data_source_inventory.csv",
        inventory_rows,
        [
            "data_source_name",
            "data_category",
            "source_type",
            "requires_wallet",
            "requires_signature",
            "requires_transaction",
            "read_only_safe",
            "available_now",
            "required_credentials",
            "implementation_complexity",
            "confidence_if_available",
            "blocker",
            "recommended_priority",
        ],
    )

    fee_design = {
        "before_probe": [
            "pool feeGrowth globals and ticks via eth_call",
            "swap log based fee velocity windows",
            "historical pool state snapshots without owning position",
        ],
        "requires_actual_lp_nft": [
            "NonfungiblePositionManager.positions(tokenId)",
            "actual tokenId owner linkage",
            "real claimed and unclaimed fee lineage by exact position",
        ],
        "historically_simulatable": [
            "pool-level fee velocity proxy",
            "range-free pool fee accrual approximations",
        ],
        "cannot_be_known_without_position": [
            "exact tokensOwed0/tokensOwed1 for our position",
            "exact feeGrowthInside deltas for unopened future position",
        ],
        "recommended_next_script": "LP_REAL_FEE_ACCRUAL_PIPELINE_V1",
    }
    write_text(
        REPORT_DIR / "REAL_FEE_ACCRUAL_DESIGN_CN.md",
        "# 真实 fee accrual 方案设计\n\n"
        "- before probe: pool globals、ticks、swap logs 可 read-only 获取。\n"
        "- requires actual LP NFT: `positions(tokenId)`、`tokensOwed0/1`、exact position range lineage。\n"
        "- simulated from historical positions: pool-level fee velocity proxy 与历史区间近似。\n"
        "- cannot know without owning position: exact unclaimed fees、exact feeGrowthInside deltas。\n"
        "- recommended next script: `LP_REAL_FEE_ACCRUAL_PIPELINE_V1`\n",
    )
    write_json(REPORT_DIR / "real_fee_accrual_design.json", fee_design)

    quote_design = {
        "primary_quote_method": "QuoterV2_static_eth_call",
        "fallback_quote_method": "pool_math_fallback",
        "route_simulation": ["single_pool", "multi_hop_if_readonly", "external_aggregator_dry_quote_if_safe"],
        "notionals": [20, 100, 500, 1000, 2000],
        "read_only_safe": True,
        "expected_accuracy": "high_if_quoter_supported_medium_if_fallback",
        "required_abi_contracts": ["QuoterV2", "UniswapV3Pool", "Slipstream-compatible quoter if protocol requires"],
        "required_rpc_access": ["eth_call", "eth_getLogs"],
        "wallet_signature_guarantee": "no_wallet_no_signature_no_router_submit",
        "recommended_next_script": "LP_PRECISE_QUOTE_PIPELINE_V1",
    }
    write_text(
        REPORT_DIR / "PRECISE_QUOTE_PIPELINE_DESIGN_CN.md",
        "# 精确 quote / route 方案设计\n\n"
        "- primary quote method: `QuoterV2` static `eth_call`。\n"
        "- fallback quote method: `v2 constant product / v3 tick-liquidity approximation`。\n"
        "- route simulation: single pool first, multi-hop only if still read-only。\n"
        "- notionals: `20 / 100 / 500 / 1000 / 2000U`。\n"
        "- no wallet / no signature / no router submit。\n"
        "- recommended next script: `LP_PRECISE_QUOTE_PIPELINE_V1`\n",
    )
    write_json(REPORT_DIR / "precise_quote_pipeline_design.json", quote_design)

    tick_design = {
        "slot0_fields": ["sqrtPriceX96", "tick", "observation data"],
        "pool_liquidity": "current in_range liquidity",
        "ticks_fields": ["liquidityGross", "liquidityNet", "feeGrowthOutside", "secondsOutside"],
        "tick_bitmap_usage": "capture initialized ticks around current price",
        "observe_usage": "TWAP and volatility proxy",
        "position_range_support": "actual_or_simulated_tickLower_tickUpper",
        "ticks_around_current_price": 256,
        "lookahead_guard": "only prior fully closed bucket and current eth_call snapshot",
        "capacity_slippage_goal": "improve precise exit depth and slippage estimation",
        "expected_complexity": "high",
        "recommended_next_script": "LP_V3_TICK_LIQUIDITY_PIPELINE_V1",
    }
    write_text(
        REPORT_DIR / "V3_TICK_LIQUIDITY_PIPELINE_DESIGN_CN.md",
        "# V3 tick-liquidity 方案设计\n\n"
        "- snapshot source: `slot0`, `liquidity`, `ticks`, `tickBitmap`, `observe`。\n"
        "- capture width: current price 两侧约 `256` 个 initialized tick 为第一版基线。\n"
        "- no lookahead: 只使用 entry-safe cutoff 前的窗口和调用时点快照。\n"
        "- target: 更准确的 capacity / slippage / route feasibility。\n"
        "- recommended next script: `LP_V3_TICK_LIQUIDITY_PIPELINE_V1`\n",
    )
    write_json(REPORT_DIR / "v3_tick_liquidity_pipeline_design.json", tick_design)

    cost_design = {
        "estimable_now": [
            "eth_feeHistory gas baseline",
            "Quoter gasEstimate if exposed",
            "quote-based slippage and route spread",
        ],
        "probe_only": [
            "actual add/remove liquidity receipt gas",
            "actual wallet balance path and exact settlement costs",
        ],
        "fixed_vs_proportional": {
            "fixed": ["gas", "mint/remove tx overhead"],
            "proportional": ["slippage", "route spread", "balancing swap loss"],
        },
        "scenario_ranges": {
            "conservative": "use upper gas band + wider slippage spread",
            "realistic": "use median gas + quoted slippage",
            "optimistic": "lower gas band and lower route spread",
        },
        "recommended_next_script": "LP_REAL_COST_MODEL_PIPELINE_V1",
    }
    write_text(
        REPORT_DIR / "REAL_COST_MODEL_DESIGN_CN.md",
        "# 真实成本模型设计\n\n"
        "- can estimate now: gas baseline、Quoter gasEstimate、quote slippage、route spread。\n"
        "- requires probe: actual add/remove receipts、真实钱包结算成本。\n"
        "- fixed cost: gas and tx overhead。\n"
        "- proportional cost: slippage、route spread、balancing loss。\n"
        "- recommended next script: `LP_REAL_COST_MODEL_PIPELINE_V1`\n",
    )
    write_json(REPORT_DIR / "real_cost_model_design.json", cost_design)

    schema = {
        "tables": [
            {
                "table_name": "lp_real_fee_accrual_v1",
                "purpose": "store research-only fee growth and tokens owed snapshots",
                "primary_key": ["run_id", "pool_id", "reference_key", "snapshot_time"],
                "source": "contract_read_and_event_logs",
                "read_only_guarantee": True,
                "timestamp_semantics": "snapshot_time_utc",
                "entry_safe_guarantee": "feature_cutoff_time_must_precede_eval_time",
                "future_probe_only_fields": ["token_id", "owner_address", "claimed_fee_amounts"],
                "confidence": "per-field",
            },
            {
                "table_name": "lp_precise_quote_v1",
                "purpose": "store static quotes across notionals and route variants",
                "primary_key": ["run_id", "pool_id", "notional_usd", "quote_side", "quote_method", "snapshot_time"],
                "source": "eth_call_or_external_dry_quote",
                "read_only_guarantee": True,
                "timestamp_semantics": "snapshot_time_utc",
                "entry_safe_guarantee": "quote_snapshot_before_downstream_eval",
                "future_probe_only_fields": [],
                "confidence": "quote_method_level",
            },
            {
                "table_name": "lp_v3_tick_liquidity_snapshot_v1",
                "purpose": "store local pool state snapshots around current price",
                "primary_key": ["run_id", "pool_id", "snapshot_time", "tick_index"],
                "source": "slot0_liquidity_ticks_tickbitmap",
                "read_only_guarantee": True,
                "timestamp_semantics": "snapshot_time_utc",
                "entry_safe_guarantee": "cutoff_before_eval",
                "future_probe_only_fields": ["actual_position_tick_lower", "actual_position_tick_upper"],
                "confidence": "snapshot_level",
            },
            {
                "table_name": "lp_real_cost_model_v1",
                "purpose": "store gas, slippage, route spread, and scenario costs",
                "primary_key": ["run_id", "pool_id", "notional_usd", "scenario_name", "snapshot_time"],
                "source": "gas_rpc_and_quote_pipeline",
                "read_only_guarantee": True,
                "timestamp_semantics": "snapshot_time_utc",
                "entry_safe_guarantee": "cost_inputs_before_eval",
                "future_probe_only_fields": ["actual_receipt_gas_used", "actual_settlement_cost_usd"],
                "confidence": "scenario_level",
            },
            {
                "table_name": "lp_real_data_readiness_v1",
                "purpose": "track per-pool readiness across all four real-data categories",
                "primary_key": ["run_id", "pool_id"],
                "source": "joined_inventory_and_pool_audit",
                "read_only_guarantee": True,
                "timestamp_semantics": "audit_time_utc",
                "entry_safe_guarantee": "n_a_design_table",
                "future_probe_only_fields": ["probe_only_gate_reason"],
                "confidence": "audit_level",
            },
        ]
    }
    write_text(
        REPORT_DIR / "REAL_DATA_PIPELINE_SCHEMA_PROPOSAL_CN.md",
        "# Real Data Pipeline Schema Proposal\n\n"
        "- `lp_real_fee_accrual_v1`\n"
        "- `lp_precise_quote_v1`\n"
        "- `lp_v3_tick_liquidity_snapshot_v1`\n"
        "- `lp_real_cost_model_v1`\n"
        "- `lp_real_data_readiness_v1`\n\n"
        "这些表都只属于 research-only namespace，不是 production 表。\n",
    )
    write_json(REPORT_DIR / "real_data_pipeline_schema_proposal.json", schema)

    readiness_rows = build_readiness_rows()
    write_text(
        REPORT_DIR / "REAL_DATA_READINESS_AUDIT_CN.md",
        "# 现有池子 real-data readiness 审计\n\n"
        f"- scanned_pool_count: `{len(readiness_rows)}`\n"
        f"- real_data_ready_pool_count: `{sum(1 for row in readiness_rows if row['can_reopen_virtual_economics'] == 'yes')}`\n"
        "- 结论：当前没有 pool 同时满足 real fee accrual + precise quote + tick-liquidity + cost model 全量 ready。\n",
    )
    write_csv(
        REPORT_DIR / "real_data_readiness_audit.csv",
        readiness_rows,
        [
            "pool_id",
            "token_pair",
            "pool_type",
            "inferred_tier",
            "has_v3_pool_state",
            "has_tick_liquidity_access",
            "has_quoter_access",
            "has_fee_tier",
            "has_swap_logs",
            "has_position_nft_data",
            "real_fee_accrual_ready",
            "precise_quote_ready",
            "tick_liquidity_ready",
            "real_cost_model_ready",
            "can_reopen_virtual_economics",
            "can_reopen_probe_preflight",
            "primary_blocker",
            "recommended_next_action",
        ],
    )

    priority = {
        "phase_1": {
            "name": "precise quote pipeline",
            "output": "lp_precise_quote_v1",
            "reason": "highest read-only feasibility and strongest immediate impact on economics realism",
        },
        "phase_2": {
            "name": "v3 tick-liquidity snapshot",
            "output": "lp_v3_tick_liquidity_snapshot_v1",
            "reason": "needed to replace conservative liquidity proxy and improve route/capacity realism",
        },
        "phase_3": {
            "name": "real fee accrual pipeline",
            "output": "lp_real_fee_accrual_v1",
            "reason": "valuable but blocked by tokenId / position lineage, so not first",
        },
        "phase_4": {
            "name": "real cost model",
            "output": "lp_real_cost_model_v1",
            "reason": "depends on better quote path and partial tick/liquidity support",
        },
        "phase_5": {
            "name": "rerun virtual notional with real data",
            "output": "lp_virtual_notional_economics_v2",
            "reason": "only after phases 1-4 land",
        },
    }
    write_text(
        REPORT_DIR / "REAL_DATA_IMPLEMENTATION_PRIORITY_CN.md",
        "# Real Data Implementation Priority\n\n"
        "1. `LP_PRECISE_QUOTE_PIPELINE_V1`\n"
        "2. `LP_V3_TICK_LIQUIDITY_PIPELINE_V1`\n"
        "3. `LP_REAL_FEE_ACCRUAL_PIPELINE_V1`\n"
        "4. `LP_REAL_COST_MODEL_PIPELINE_V1`\n"
        "5. rerun virtual economics with real data\n\n"
        "原因：当前最可行、最 read-only、安全且能直接改善 economics realism 的是 precise quote。\n",
    )
    write_json(REPORT_DIR / "real_data_implementation_priority.json", priority)

    next_stage = "LP_PRECISE_QUOTE_PIPELINE_V1"
    next_stage_payload = {
        "recommended_next_stage": next_stage,
        "why_not_fee_first": "exact fee accrual still blocked by tokenId and actual position lineage",
        "why_not_cost_first": "cost model depends on more realistic quote path",
        "why_not_stop_now": "read-only real-data path is feasible and still below execution threshold",
    }
    write_text(
        REPORT_DIR / "REAL_DATA_REOPEN_NEXT_STAGE_DECISION_CN.md",
        "# Real Data Reopen Next Stage Decision\n\n"
        f"- recommended_next_stage: `{next_stage}`\n"
        "- 选择理由：Quoter/static quote path feasibility 最高，且是后续 tick-liquidity、cost、economics 重算的共同前置。\n"
        "- 本轮仍不是策略重开，不允许 probe/canary/live。\n",
    )
    write_json(REPORT_DIR / "real_data_reopen_next_stage_decision.json", next_stage_payload)

    final_verdict = {
        "status": "PASS",
        "stage": "LP_REAL_DATA_REOPEN_PREP_V1",
        "old_proxy_line_frozen": True,
        "real_data_reopen_defined": True,
        "real_fee_accrual_design_ready": True,
        "precise_quote_design_ready": True,
        "v3_tick_liquidity_design_ready": True,
        "real_cost_model_design_ready": True,
        "real_data_schema_proposed": True,
        "real_data_ready_pool_count": 0,
        "can_reopen_virtual_economics": False,
        "can_reopen_probe_preflight": False,
        "can_run_probe_now": False,
        "manual_approval_required_for_probe": True,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage,
    }
    if next_stage not in ALLOWED_NEXT:
        raise SystemExit("invalid next stage")
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final_verdict)
    write_text(
        REPORT_DIR / "ONEPAGE_CN.md",
        "# LP Real Data Reopen Prep 一页纸\n\n"
        "- old proxy line: `frozen`\n"
        "- real data reopen defined: `yes`\n"
        "- fee accrual / precise quote / v3 tick-liquidity / real cost model 设计均已就绪\n"
        "- 当前 `real_data_ready_pool_count = 0`\n"
        "- 当前不能重开 virtual economics，不能重开 probe preflight\n"
        f"- recommended_next_stage: `{next_stage}`\n"
        "- tiny_canary_allowed: `no`\n",
    )
    write_text(
        REPORT_DIR / "ARTIFACT_INDEX.md",
        "\n".join(
            [
                "# LP Real Data Reopen Prep Artifact Index",
                "",
                f"- [INPUT_EVIDENCE_AUDIT_CN.md]({REPORT_DIR / 'INPUT_EVIDENCE_AUDIT_CN.md'})",
                f"- [real_data_source_inventory.json]({REPORT_DIR / 'real_data_source_inventory.json'})",
                f"- [REAL_FEE_ACCRUAL_DESIGN_CN.md]({REPORT_DIR / 'REAL_FEE_ACCRUAL_DESIGN_CN.md'})",
                f"- [PRECISE_QUOTE_PIPELINE_DESIGN_CN.md]({REPORT_DIR / 'PRECISE_QUOTE_PIPELINE_DESIGN_CN.md'})",
                f"- [V3_TICK_LIQUIDITY_PIPELINE_DESIGN_CN.md]({REPORT_DIR / 'V3_TICK_LIQUIDITY_PIPELINE_DESIGN_CN.md'})",
                f"- [REAL_COST_MODEL_DESIGN_CN.md]({REPORT_DIR / 'REAL_COST_MODEL_DESIGN_CN.md'})",
                f"- [REAL_DATA_PIPELINE_SCHEMA_PROPOSAL_CN.md]({REPORT_DIR / 'REAL_DATA_PIPELINE_SCHEMA_PROPOSAL_CN.md'})",
                f"- [REAL_DATA_READINESS_AUDIT_CN.md]({REPORT_DIR / 'REAL_DATA_READINESS_AUDIT_CN.md'})",
                f"- [REAL_DATA_IMPLEMENTATION_PRIORITY_CN.md]({REPORT_DIR / 'REAL_DATA_IMPLEMENTATION_PRIORITY_CN.md'})",
                f"- [REAL_DATA_REOPEN_NEXT_STAGE_DECISION_CN.md]({REPORT_DIR / 'REAL_DATA_REOPEN_NEXT_STAGE_DECISION_CN.md'})",
                f"- [FINAL_VERDICT.json]({REPORT_DIR / 'FINAL_VERDICT.json'})",
                f"- [ONEPAGE_CN.md]({REPORT_DIR / 'ONEPAGE_CN.md'})",
            ]
        )
        + "\n",
    )


if __name__ == "__main__":
    main()
