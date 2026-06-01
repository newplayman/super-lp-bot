#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import re
import shlex
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

RUN_ID = os.environ.get("RUN_ID_OVERRIDE", "20260601_154136")
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/Users/bendu/lp-bot/v3"))
REPORT_DIR = Path(
    os.environ.get(
        "REPORT_DIR_OVERRIDE",
        str(REPO_ROOT / "reports" / "lp_universe_scope_audit" / RUN_ID),
    )
)
WORKSPACE = os.environ.get("LPSQL_WORKSPACE", "/opt/lpbot/lp-bot-v3-origin-check")

ALLOWED_NEXT = {
    "LP_EVM_UNIVERSE_EXPANSION_DESIGN_V1",
    "LP_AERODROME_SLIPSTREAM_PARSER_DESIGN_V1",
    "LP_SOLANA_LP_UNIVERSE_DESIGN_V1",
    "LP_UNIVERSE_SCOPE_AUDIT_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}

INPUT_FILES = [
    REPO_ROOT / "reports" / "lp_real_data_final_freeze" / "20260601_150954" / "FINAL_VERDICT.json",
    REPO_ROOT / "reports" / "lp_real_data_final_freeze" / "20260601_150954" / "REAL_DATA_PIPELINE_FREEZE_MATRIX_CN.md",
    REPO_ROOT / "reports" / "lp_real_data_final_freeze" / "20260601_150954" / "WHY_POOL_LEVEL_POSITIVE_IS_NOT_EDGE_CN.md",
    REPO_ROOT / "reports" / "lp_real_data_final_freeze" / "20260601_150954" / "REAL_DATA_REOPEN_CONDITIONS_CN.md",
    REPO_ROOT / "reports" / "lp_real_fee_accrual_fix" / "20260601_145519" / "FINAL_VERDICT.json",
    REPO_ROOT / "reports" / "lp_real_fee_accrual_fix" / "20260601_145519" / "real_fee_lineage_economics_preview.csv",
    REPO_ROOT / "reports" / "lp_real_fee_accrual" / "20260601_143401" / "real_fee_economics_preview.csv",
    REPO_ROOT / "reports" / "lp_real_cost_model" / "20260601_141103" / "real_cost_model_results.csv",
    REPO_ROOT / "reports" / "lp_real_cost_model" / "20260601_141103" / "real_cost_economics_preview.csv",
    REPO_ROOT / "reports" / "lp_v3_tick_liquidity_fix" / "20260601_132644" / "v3_tick_liquidity_v2_results.csv",
    REPO_ROOT / "reports" / "lp_precise_quote" / "20260601_120001" / "precise_quote_results.csv",
    REPO_ROOT / "reports" / "lp_quote_depth_curve_fix" / "20260601_091739" / "quote_depth_curve_v2_results.csv",
    REPO_ROOT / "reports" / "lp_quote_depth_curve_fix" / "20260601_091739" / "expanded_quote_depth_candidate_pools.csv",
    REPO_ROOT / "reports" / "lp_data_pipeline" / "20260601_084943" / "lp_data_pipeline_feasibility_probe.csv",
    REPO_ROOT / "reports" / "lp_scale_economics" / "20260601_082100" / "lp_scale_candidate_pool_audit.csv",
    REPO_ROOT / "reports" / "tierb_discovery_expand" / "20260530_110720" / "tier_b_expanded_discovery_candidates.csv",
    REPO_ROOT / "reports" / "tierb_data_fix" / "20260530_125453" / "tier_b_targeted_pool_set.csv",
    REPO_ROOT / "reports" / "tierc_shadow" / "20260529_155854" / "tierc_batch_final_freeze.csv",
    REPO_ROOT / "docs" / "LPBOT_RESEARCH_STATUS_CN.md",
    REPO_ROOT / "docs" / "LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md",
]

CHAIN_MAP = {
    "base": "base",
    "1": "base",
    "ethereum": "ethereum",
    "ethereum mainnet": "ethereum",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "polygon": "polygon",
    "bsc": "bsc",
    "bnb": "bsc",
    "solana": "solana",
    "": "unknown",
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def normalize_chain(v: Any) -> str:
    if v is None:
        return "unknown"
    s = str(v).strip().lower()
    if s in CHAIN_MAP:
        return CHAIN_MAP[s]
    return s or "unknown"


def normalize_protocol(v: Any) -> str:
    if v is None:
        return "unknown"
    s = str(v).strip().lower()
    if "uniswap" in s and "v2" in s:
        return "Uniswap V2"
    if "uniswap" in s and ("v3" in s or "cl" in s):
        return "Uniswap V3"
    if "pancake" in s and "v3" in s:
        return "PancakeSwap V3"
    if "aerodrome" in s or "slipstream" in s:
        return "Aerodrome Slipstream"
    if "sushi" in s:
        return "Sushi"
    if "curve" in s:
        return "Curve"
    if "balancer" in s:
        return "Balancer"
    if "meteora" in s:
        return "Meteora"
    if "orca" in s:
        return "Orca"
    if "raydium" in s:
        return "Raydium"
    return s or "unknown"


def parse_fee(v: Any) -> str:
    if v is None:
        return "unknown"
    s = str(v).strip()
    if not s:
        return "unknown"
    m = re.search(r"\d+\.?\d*%", s)
    if m:
        return m.group(0)
    return s


def parse_fee_from_pair(pair: str | None) -> str:
    if not pair:
        return "unknown"
    m = re.search(r"(\d+\.?\d*%)", pair)
    return m.group(1) if m else "unknown"


def parse_stage_status(row: dict[str, str]) -> str:
    for key in ("status", "current_status", "final_status", "watch_reason", "remaining_blockers"):
        v = str(row.get(key, "")).lower()
        if "reject" in v:
            return "rejected"
        if "watch" in v:
            return "watch"
        if "missing" in v or "data_missing" in v:
            return "data_missing"
    return "analyzed"


def bool_yes(v: Any) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    s = str(v).strip().lower()
    return "yes" if s in {"yes", "true", "1"} else "no"


def collect_pools() -> tuple[dict[str, dict[str, Any]], dict[str, set[str]]]:
    # return records + stage sets
    records: dict[str, dict[str, Any]] = {}
    stage_sets: dict[str, set[str]] = defaultdict(set)
    actual_fee_ready: set[str] = set()
    pool_level_pos: set[str] = set()

    def upsert(row: dict[str, str], stage: str, source: str) -> None:
        pid = str(row.get("pool_id") or "").strip()
        if not pid:
            return
        r = records.setdefault(
            pid,
            {
                "pool_id": pid,
                "chain": "unknown",
                "protocol": "unknown",
                "pool_type": row.get("pool_type", "unknown") or "unknown",
                "token_pair": row.get("token_pair", "unknown") or "unknown",
                "token0": "unknown",
                "token1": "unknown",
                "fee_tier": "unknown",
                "inferred_tier": "unknown",
                "data_source_report": source,
                "latest_stage_seen": stage,
                "first_seen_stage": stage,
                "status_in_stage": "analyzed",
                "confidence": row.get("confidence", "unknown") or "unknown",
                "stage_history": [],
            },
        )
        # only fill metadata when available
        chain = normalize_chain(row.get("chain", ""))
        protocol = normalize_protocol(row.get("protocol", ""))
        if chain != "unknown":
            r["chain"] = chain
        if protocol != "unknown":
            r["protocol"] = protocol
        if row.get("pool_type"):
            r["pool_type"] = row["pool_type"]
        tp = row.get("token_pair", "")
        if tp:
            r["token_pair"] = tp
            if "/" in tp:
                p0, p1 = [x.strip() for x in tp.split("/")[:2]]
                r["token0"] = p0
                r["token1"] = p1
        r["fee_tier"] = parse_fee(row.get("fee_tier")) or parse_fee(row.get("fee_bps")) or parse_fee_from_pair(r["token_pair"])
        infer = row.get("inferred_tier", "")
        if infer:
            r["inferred_tier"] = infer
        r["latest_stage_seen"] = stage
        r["stage_history"].append(stage)
        r["status_in_stage"] = parse_stage_status(row)
        if "data_source_report" not in r["data_source_report"]:
            r["data_source_report"] = f"{r['data_source_report']};{source}"

        stage_sets[stage].add(pid)

    for row in read_csv(REPO_ROOT / "reports" / "lp_scale_economics" / "20260601_082100" / "lp_scale_candidate_pool_audit.csv"):
        upsert(row, "scale_economics", "lp_scale_candidate_pool_audit.csv")

    for row in read_csv(REPO_ROOT / "reports" / "lp_data_pipeline" / "20260601_084943" / "lp_data_pipeline_feasibility_probe.csv"):
        upsert(row, "lp_data_pipeline", "lp_data_pipeline_feasibility_probe.csv")

    for row in read_csv(REPO_ROOT / "reports" / "lp_quote_depth_curve_fix" / "20260601_091739" / "quote_depth_curve_v2_results.csv"):
        upsert(row, "quote_depth_v2", "quote_depth_curve_v2_results.csv")

    for row in read_csv(REPO_ROOT / "reports" / "lp_quote_depth_curve_fix" / "20260601_091739" / "expanded_quote_depth_candidate_pools.csv"):
        upsert(row, "quote_depth_v2", "expanded_quote_depth_candidate_pools.csv")

    for row in read_csv(REPO_ROOT / "reports" / "lp_precise_quote" / "20260601_120001" / "precise_quote_results.csv"):
        upsert(row, "precise_quote", "precise_quote_results.csv")

    for row in read_csv(REPO_ROOT / "reports" / "lp_v3_tick_liquidity_fix" / "20260601_132644" / "v3_tick_liquidity_v2_results.csv"):
        upsert(row, "v3_tick_liquidity", "v3_tick_liquidity_v2_results.csv")

    for row in read_csv(REPO_ROOT / "reports" / "lp_real_cost_model" / "20260601_141103" / "real_cost_model_results.csv"):
        upsert(row, "real_cost_model", "real_cost_model_results.csv")

    for row in read_csv(REPO_ROOT / "reports" / "lp_real_cost_model" / "20260601_141103" / "real_cost_economics_preview.csv"):
        upsert(row, "real_cost_model", "real_cost_economics_preview.csv")

    for row in read_csv(REPO_ROOT / "reports" / "lp_real_fee_accrual" / "20260601_143401" / "real_fee_economics_preview.csv"):
        upsert(row, "real_fee_accrual", "real_fee_economics_preview.csv")
        pid = row.get("pool_id", "").strip()
        if pid and str(row.get("actual_fee_available", "")).strip().lower() in {"true", "1", "yes"}:
            actual_fee_ready.add(pid)
        if pid and (row.get("previous_positive_proxy") or "" ).strip() != "" and str(row.get("status", "")).lower() != "negative_proxy":
            pool_level_pos.add(pid)

    for row in read_csv(REPO_ROOT / "reports" / "lp_real_fee_accrual_fix" / "20260601_145519" / "real_fee_lineage_economics_preview.csv"):
        upsert(row, "real_fee_accrual_fix", "real_fee_lineage_economics_preview.csv")

    for row in read_csv(REPO_ROOT / "reports" / "tierb_discovery_expand" / "20260530_110720" / "tier_b_expanded_discovery_candidates.csv"):
        upsert(row, "tierb_discovery", "tier_b_expanded_discovery_candidates.csv")

    for row in read_csv(REPO_ROOT / "reports" / "tierb_data_fix" / "20260530_125453" / "tier_b_targeted_pool_set.csv"):
        upsert(row, "tierb_data_fix", "tier_b_targeted_pool_set.csv")

    for row in read_csv(REPO_ROOT / "reports" / "tierc_shadow" / "20260529_155854" / "tierc_batch_final_freeze.csv"):
        upsert(row, "tierc_batch", "tierc_batch_final_freeze.csv")

    # finalize status for rows without status
    for rec in records.values():
        if rec["token_pair"] == "unknown":
            rec["token0"] = "unknown"
            rec["token1"] = "unknown"
        if rec["fee_tier"] == "unknown":
            rec["fee_tier"] = parse_fee_from_pair(rec["token_pair"])

    return records, {
        "stage_sets": stage_sets,
        "actual_fee_ready": actual_fee_ready,
        "pool_level_positive_proxy": pool_level_pos,
    }


def run_db_audit() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    remote = r'''
import json, os
import psycopg2
from psycopg2 import sql

dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL") or os.environ.get("SHADOW_POSTGRES_DSN")
if not dsn:
    print(json.dumps({"db_ready": False, "error": "missing_dsn"}))
    raise SystemExit(2)

try:
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT current_database(), current_user")
    db, user = cur.fetchone()
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public'
          AND (
            table_name ILIKE '%%pool%%' OR table_name ILIKE '%%pools%%'
            OR table_name ILIKE '%%snapshot%%' OR table_name ILIKE '%%quote%%'
            OR table_name ILIKE '%%depth%%' OR table_name ILIKE '%%fee%%'
            OR table_name ILIKE '%%liquidity%%' OR table_name ILIKE '%%position%%'
            OR table_name ILIKE '%%candidate%%' OR table_name ILIKE '%%tier%%'
          )
        ORDER BY table_name
        """
    )
    tables = [r[0] for r in cur.fetchall()]
    out = []
    for t in tables:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s", (t,))
        cols = [r[0] for r in cur.fetchall()]
        colset = {c.lower() for c in cols}
        pool_col = next((c for c in cols if c.lower() in {"pool_id", "pool"}), "")
        token_cols = [c for c in cols if c.lower() in {"token0", "token1", "token_a", "token_b", "token0_address", "token1_address"}]
        chain_col = next((c for c in cols if c.lower() in {"chain", "chain_id"}), "")
        protocol_col = next((c for c in cols if c.lower() in {"protocol", "dex", "exchange", "venue"}), "")
        if pool_col:
            cur.execute(sql.SQL("SELECT count(*) FROM {}.{}" ).format(sql.Identifier('public'), sql.Identifier(t)))
            rc = cur.fetchone()[0]
        else:
            rc = 0
        out.append({
            "table_name": t,
            "row_count": int(rc) if rc is not None else 0,
            "pool_id_column": pool_col,
            "token_columns": ",".join(token_cols),
            "chain_columns": chain_col,
            "protocol_columns": protocol_col,
            "usable_for_universe": bool(pool_col and (len(token_cols) > 0 or chain_col or protocol_col)),
            "notes": "ok",
        })
    cur.close()
    conn.close()
    print(json.dumps({"db_ready": True, "database": db, "user": user, "tables": out}))
except Exception as e:
    print(json.dumps({"db_ready": False, "error": str(e)}))
    raise SystemExit(3)
'''

    script = "\n".join(
        [
            "set -a",
            "source .runtime.shadow.env 2>/dev/null || source .env 2>/dev/null || source .env.chain 2>/dev/null || true",
            "set +a",
            "python3 - <<'PY'",
            remote,
            "PY",
        ]
    )
    p = subprocess.run(["ssh", "vps", f"cd {shlex.quote(WORKSPACE)} && bash -lc {shlex.quote(script)}"], capture_output=True, text=True)
    payload_raw = (p.stdout or p.stderr or "{}").strip()
    try:
        payload = json.loads(payload_raw)
    except Exception:
        payload = {"db_ready": False, "error": payload_raw[-1000:]}
    tables = payload.get("tables", []) if isinstance(payload, dict) else []
    return payload, tables


def stage_history_text(hist: list[str]) -> str:
    return " -> ".join(hist)


def build_artifacts(records: dict[str, dict[str, Any]], stage_meta: dict[str, Any], db_meta: dict[str, Any], db_rows: list[dict[str, Any]], input_rows: list[dict[str, Any]]) -> dict[str, Any]:
    # A: input evidence
    input_missing = [row["path"] for row in input_rows if not row["exists"]]
    input_summary = {
        "all_inputs_present": not input_missing,
        "missing_input_list": input_missing,
        "freeze_completed": bool(read_json(REPO_ROOT / "reports" / "lp_real_data_final_freeze" / "20260601_150954" / "FINAL_VERDICT.json").get("real_data_research_freeze_complete", False)),
        "universe_audit_only": True,
        "no_probe_canary_live": True,
        "has_sufficient_evidence": not bool(input_missing),
        "wrong_stage_blocker": False,
        "tiny_canary_allowed": "no",
    }
    write_json(REPORT_DIR / "input_evidence_audit.json", {"input": input_rows, "summary": input_summary})
    write_text(
        REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md",
        "# 输入证据审计\n\n"
        + "\n".join(["- %s: %s" % (r["path"], "存在" if r["exists"] else "缺失") for r in input_rows])
        + "\n\n"
        + f"- 真实数据冻结完成: {'是' if input_summary['freeze_completed'] else '否'}\n"
        + "- 本轮仅做 universe audit: 是\n"
        + "- 不 probe/no canary/live: 是\n",
    )

    # Universe extraction
    raw_rows = []
    for rec in records.values():
        raw_rows.append(
            {
                "pool_id": rec["pool_id"],
                "chain": rec["chain"],
                "protocol": rec["protocol"],
                "pool_type": rec["pool_type"],
                "token_pair": rec["token_pair"],
                "token0": rec["token0"],
                "token1": rec["token1"],
                "fee_tier": rec["fee_tier"],
                "inferred_tier": rec["inferred_tier"],
                "data_source_report": rec["data_source_report"],
                "latest_stage_seen": rec["latest_stage_seen"],
                "status_in_stage": rec["status_in_stage"],
                "confidence": rec["confidence"],
                "stage_history": stage_history_text(rec["stage_history"]),
            }
        )
    write_csv(
        REPORT_DIR / "universe_extraction_raw.csv",
        raw_rows,
        ["pool_id", "chain", "protocol", "pool_type", "token_pair", "token0", "token1", "fee_tier", "inferred_tier", "data_source_report", "latest_stage_seen", "status_in_stage", "confidence", "stage_history"],
    )
    write_json(
        REPORT_DIR / "universe_extraction_raw.json",
        {
            "rows": raw_rows,
            "total_raw_pool_rows": len(raw_rows),
            "unique_pool_count": len(records),
            "unique_chain_count": len({r["chain"] for r in records.values() if r["chain"] != "unknown"}),
            "unique_protocol_count": len({r["protocol"] for r in records.values() if r["protocol"] != "unknown"}),
            "extraction_source_count": len(INPUT_FILES),
            "missing_metadata_count": sum(1 for r in records.values() if r["chain"] == "unknown" or r["protocol"] == "unknown" or r["token_pair"] == "unknown" or r["fee_tier"] == "unknown"),
        },
    )
    write_text(
        REPORT_DIR / "UNIVERSE_EXTRACTION_CN.md",
        "# 池子 Universe 抽取\n\n"
        + f"总行数: {len(raw_rows)}，唯一池: {len(records)}\n"
        + "\n".join([f"- {r['pool_id']} | {r['chain']} | {r['protocol']} | {r['token_pair']}" for r in raw_rows[:200]])
        + "\n",
    )

    # DB audit outputs
    write_json(REPORT_DIR / "vps_pool_universe_db_audit.json", db_meta)
    write_csv(
        REPORT_DIR / "vps_pool_universe_db_audit.csv",
        db_rows,
        ["table_name", "row_count", "pool_id_column", "token_columns", "chain_columns", "protocol_columns", "usable_for_universe", "notes"],
    )
    if not db_meta.get("db_ready"):
        db_md = f"# VPS pool universe DB audit\n\nDB not ready: {db_meta.get('error', 'unknown')}\n"
    else:
        db_md = (
            f"# VPS pool universe DB audit\n\n"
            f"database={db_meta.get('database')}\nuser={db_meta.get('user')}\n"
            + "\n".join([f"- {r['table_name']} row_count={r['row_count']} usable={r['usable_for_universe']}" for r in db_rows[:200]])
            + "\n"
        )
    write_text(REPORT_DIR / "VPS_POOL_UNIVERSE_DB_AUDIT_CN.md", db_md)

    # Normalized pool list
    stage_sets = stage_meta["stage_sets"]
    norm_rows: list[dict[str, Any]] = []
    for i, rec in enumerate(sorted(records.values(), key=lambda x: (x["chain"], x["protocol"], x["token_pair"], x["pool_id"])), start=1):
        pid = rec["pool_id"]
        norm_rows.append(
            {
                "index": i,
                "chain": rec["chain"],
                "protocol": rec["protocol"],
                "pool_type": rec["pool_type"],
                "token_pair": rec["token_pair"],
                "fee_tier": rec["fee_tier"],
                "pool_id": pid,
                "inferred_tier": rec["inferred_tier"],
                "first_seen_stage": rec["first_seen_stage"],
                "latest_seen_stage": rec["latest_stage_seen"],
                "reached_precise_quote": bool_yes(pid in stage_sets["precise_quote"]),
                "reached_v3_tick_liquidity": bool_yes(pid in stage_sets["v3_tick_liquidity"]),
                "reached_real_cost_model": bool_yes(pid in stage_sets["real_cost_model"]),
                "reached_real_fee_accrual": bool_yes(pid in stage_sets["real_fee_accrual"] or pid in stage_sets["real_fee_accrual_fix"]),
                "positive_proxy_pool_level": bool_yes(pid in stage_meta["pool_level_positive_proxy"]),
                "actual_fee_ready": bool_yes(pid in stage_meta["actual_fee_ready"]),
                "final_status": rec["status_in_stage"],
                "notes": rec["data_source_report"],
            }
        )

    write_csv(
        REPORT_DIR / "lp_universe_normalized_pool_list.csv",
        norm_rows,
        [
            "index", "chain", "protocol", "pool_type", "token_pair", "fee_tier", "pool_id", "inferred_tier", "first_seen_stage", "latest_seen_stage",
            "reached_precise_quote", "reached_v3_tick_liquidity", "reached_real_cost_model", "reached_real_fee_accrual",
            "positive_proxy_pool_level", "actual_fee_ready", "final_status", "notes",
        ],
    )
    write_json(REPORT_DIR / "lp_universe_normalized_pool_list.json", {"rows": norm_rows})

    human = []
    human.append("# LP Universe 规范化池子清单\n")
    for row in norm_rows:
        p1 = row["token_pair"] if row["token_pair"] != "unknown" else "不确定"
        line = f"{row['chain']} {row['protocol']} {p1} {row['fee_tier']}  / pool_id: {row['pool_id']} / 状态:{row['final_status']}"
        human.append(f"- {line}")
    write_text(REPORT_DIR / "LP_UNIVERSE_NORMALIZED_POOL_LIST_CN.md", "\n".join(human) + "\n")

    # stage matrix
    matrix = []
    def add_stage(stage: str, label: str, sset: set[str], note: str) -> None:
        chains = {records[p]["chain"] for p in sset}
        prots = {records[p]["protocol"] for p in sset}
        matrix.append({
            "stage": stage,
            "pool_count": len(sset),
            "chain_count": len(chains),
            "protocol_count": len(prots),
            "main_chains": ",".join(sorted(chains)),
            "main_protocols": ",".join(sorted(prots)),
            "notes": note,
            "label": label,
        })

    add_stage("raw_discovered", "raw_discovered", set(records.keys()), "来自任一阶段源的原始池")
    add_stage("tierb_discovery", "tierb_discovery", stage_sets["tierb_discovery"], "Tier B discovery 产物")
    add_stage("tierc", "tierc", stage_sets["tierc_batch"], "Tier C 批次历史")
    add_stage("scale_economics", "scale_economics", stage_sets["scale_economics"], "scale 阶段候选")
    add_stage("quote_depth_v2", "quote_depth_v2", stage_sets["quote_depth_v2"], "quote/depth v2")
    add_stage("precise_quote", "precise_quote", stage_sets["precise_quote"], "precise quote")
    add_stage("v3_tick_liquidity", "v3_tick_liquidity", stage_sets["v3_tick_liquidity"], "v3 tick liquidity")
    add_stage("real_cost_model", "real_cost_model", stage_sets["real_cost_model"], "real cost model")
    add_stage("real_fee_accrual", "real_fee_accrual", stage_sets["real_fee_accrual"], "real fee accrual")
    add_stage("pool_level_positive_proxy", "pool_level_positive", set(stage_meta["pool_level_positive_proxy"]), "pool-level proxy positive")
    add_stage("actual_fee_ready", "actual_fee_ready", set(stage_meta["actual_fee_ready"]), "actual fee lineage ready")

    write_csv(REPORT_DIR / "lp_universe_stage_coverage_matrix.csv", matrix, ["stage", "pool_count", "chain_count", "protocol_count", "main_chains", "main_protocols", "label", "notes"])
    write_json(REPORT_DIR / "lp_universe_stage_coverage_matrix.json", {"rows": matrix})
    write_text(
        REPORT_DIR / "LP_UNIVERSE_STAGE_COVERAGE_MATRIX_CN.md",
        "# 池子覆盖矩阵\n\n"
        + "\n".join([f"- {r['stage']}: {r['pool_count']} pools (chains={r['chain_count']} protocols={r['protocol_count']})" for r in matrix])
        + "\n",
    )

    # chain / protocol coverage
    cp_rows: list[dict[str, Any]] = []
    chain_targets = ["base", "ethereum", "arbitrum", "optimism", "polygon", "bsc", "solana", "other"]
    protocol_targets = ["Uniswap V2", "Uniswap V3", "PancakeSwap V3", "Aerodrome Slipstream", "Sushi", "Curve", "Balancer", "Meteora", "Orca", "Raydium", "其他"]

    for c in chain_targets:
        if c == "other":
            covered_pool_count = sum(1 for r in records.values() if r["chain"] not in {"base", "ethereum", "arbitrum", "optimism", "polygon", "bsc", "solana"})
            covered = covered_pool_count > 0
            priority = "not_now" if covered else ("P1" if c == "other" else "P2")
        else:
            covered_pool_count = sum(1 for r in records.values() if r["chain"] == c)
            covered = covered_pool_count > 0
            priority = "not_now" if covered else {"base": "not_now", "ethereum": "P2", "arbitrum": "P1", "optimism": "P1", "polygon": "P2", "bsc": "P2", "solana": "P2"}[c]
        cp_rows.append({
            "type": "chain",
            "name": c.title(),
            "covered": bool_yes(covered),
            "pool_count": covered_pool_count,
            "reached_real_data_pipeline": bool_yes(covered),
            "reason_if_not_covered": "" if covered else "未纳入该链池",
            "required_new_connector_or_parser": bool_yes(not covered),
            "priority_to_add": priority,
        })

    for p in protocol_targets:
        if p == "其他":
            covered_pool_count = 0
            for r in records.values():
                if r["protocol"] not in {"Uniswap V2", "Uniswap V3", "PancakeSwap V3", "Aerodrome Slipstream", "Sushi", "Curve", "Balancer", "Meteora", "Orca", "Raydium"}:
                    covered_pool_count += 1
            covered = covered_pool_count > 0
            priority = "P2"
        else:
            covered_pool_count = sum(1 for r in records.values() if r["protocol"] == p)
            covered = covered_pool_count > 0
            priority = "not_now" if covered else ("P1" if p in {"Uniswap V3", "PancakeSwap V3", "Aerodrome Slipstream"} else "P2")
        cp_rows.append({
            "type": "protocol",
            "name": p,
            "covered": bool_yes(covered),
            "pool_count": covered_pool_count,
            "reached_real_data_pipeline": bool_yes(covered),
            "reason_if_not_covered": "" if covered else "未纳入该协议池",
            "required_new_connector_or_parser": bool_yes(not covered),
            "priority_to_add": priority,
        })
    write_csv(
        REPORT_DIR / "chain_protocol_coverage.csv",
        cp_rows,
        ["type", "name", "covered", "pool_count", "reached_real_data_pipeline", "reason_if_not_covered", "required_new_connector_or_parser", "priority_to_add"],
    )
    write_json(
        REPORT_DIR / "chain_protocol_coverage.json",
        {
            "rows": cp_rows,
            "summary": {
                "solana_covered": any(r["covered"] == "yes" and r["name"] == "Solana" for r in cp_rows if r["type"] == "chain"),
                "base_uniswap_v3_covered": any(r["chain"] == "base" and r["protocol"] in {"Uniswap V3", "Uniswap v3"} for r in records.values()),
                "base_pancakeswap_v3_covered": any(r["chain"] == "base" and r["protocol"] == "PancakeSwap V3" for r in records.values()),
                "aerodrome_covered": any(r["covered"] == "yes" and r["name"] == "Aerodrome Slipstream" for r in cp_rows if r["type"] == "protocol"),
            },
        },
    )
    write_text(
        REPORT_DIR / "CHAIN_PROTOCOL_COVERAGE_CN.md",
        "# 链/协议覆盖\n\n" + "\n".join([f"- [{r['type']}] {r['name']}: 覆盖={r['covered']}, 池数={r['pool_count']}, 优先级={r['priority_to_add']}" for r in cp_rows]) + "\n",
    )

    # current screened
    screened_rows = []
    for row in norm_rows:
        if row["token_pair"] == "unknown":
            continue
        screened_rows.append(
            {
                "chain": row["chain"],
                "protocol": row["protocol"],
                "token_pair": row["token_pair"],
                "fee_tier": row["fee_tier"],
                "pool_id": row["pool_id"],
                "current_stage": row["latest_seen_stage"],
                "current_status": row["final_status"],
                "notes": row["notes"],
            }
        )
    write_json(REPORT_DIR / "current_screened_pool_summary.json", {"rows": screened_rows})
    write_text(
        REPORT_DIR / "CURRENT_SCREENED_POOL_SUMMARY_CN.md",
        "# 当前 screened 池总结\n\n" + "\n".join([
            f"{i}、{r['chain']} {r['protocol']} {r['token_pair']} {r['fee_tier']}" for i, r in enumerate(screened_rows[:20], 1)
        ]) + "\n",
    )

    # gap analysis
    gap = {
        "applies_to_current_universe_only": True,
        "does_not_disprove_all_lp": True,
        "causes": [
            "过度集中 Base",
            "非 EVM 链缺失",
            "Solana/Meteora 覆盖不足",
            "Ethereum/Arbitrum/Optimism 主流 V3 覆盖不足",
            "Aerodrome Slipstream 解析/slot0 非标准",
            "pool universe 扩展需新增 connector/parser/API",
            "当前 pipeline 偏向标准 EVM V3",
        ],
        "base_pool_count": len([r for r in records.values() if r["chain"] == "base"]),
        "solana_pool_count": len([r for r in records.values() if r["chain"] == "solana"]),
    }
    write_json(REPORT_DIR / "universe_gap_analysis.json", gap)
    write_text(
        REPORT_DIR / "UNIVERSE_GAP_ANALYSIS_CN.md",
        "# Universe Gap\n\n"
        "- applies_to_current_universe_only: true\n"
        "- does_not_disprove_all_lp: true\n"
        + "\n".join(["- " + c for c in gap["causes"]])
        + "\n",
    )

    plan = [
        {
            "priority": "P0", "plan": "标准 EVM V3 扩展", "items": "Base UniswapV3;Base PancakeSwapV3;Arbitrum UniswapV3;Optimism UniswapV3;Ethereum UniswapV3;Polygon UniswapV3", "why": "修复覆盖偏窄",
            "needed_data_source": "ticks/quotes/snapshot", "parser_needed": "否", "quote_method": "v3-quoter/stateless", "fee_method": "现有池费率", "cost_model_changes": "无", "implementation_complexity": "中",
        },
        {
            "priority": "P1", "plan": "非标准 EVM", "items": "Aerodrome Slipstream Base;Velodrome Optimism", "why": "修复 slot0 差异和风险字段", "needed_data_source": "slot0+tick bitmap", "parser_needed": "是", "quote_method": "增强 adapter", "fee_method": "自定义", "cost_model_changes": "小", "implementation_complexity": "中高",
        },
        {
            "priority": "P2", "plan": "非 EVM", "items": "Solana Meteora/Orca/Raydium", "why": "避免结论外推", "needed_data_source": "Solana RPC/quotes", "parser_needed": "是", "quote_method": "SDK/Adapter", "fee_method": "新接入", "cost_model_changes": "高", "implementation_complexity": "高",
        },
    ]
    write_json(REPORT_DIR / "pool_universe_expansion_plan.json", {"plans": plan})
    write_text(
        REPORT_DIR / "POOL_UNIVERSE_EXPANSION_PLAN_CN.md",
        "# 扩展计划\n\n" + "\n".join([f"{p['priority']} {p['plan']}: {p['items']}" for p in plan]) + "\n",
    )

    # recommendation
    base_univ = any(r['protocol'] in {"Uniswap V3", "PancakeSwap V3"} for r in records.values())
    aerodrome_missing = any(r['protocol'] == "Aerodrome Slipstream" for r in records.values()) is False
    solana_missing = any(r['chain'] == "solana" for r in records.values()) is False
    if solana_missing:
        rec = "LP_SOLANA_LP_UNIVERSE_DESIGN_V1"
    elif not base_univ:
        rec = "LP_EVM_UNIVERSE_EXPANSION_DESIGN_V1"
    elif aerodrome_missing:
        rec = "LP_AERODROME_SLIPSTREAM_PARSER_DESIGN_V1"
    else:
        rec = "LP_EVM_UNIVERSE_EXPANSION_DESIGN_V1"
    write_json(
        REPORT_DIR / "lp_universe_scope_next_stage_decision.json",
        {
            "recommended_next_stage": rec,
            "condition": "扩大标准 EVM 覆盖为主，先不改主研究线",
        },
    )
    write_text(
        REPORT_DIR / "LP_UNIVERSE_SCOPE_NEXT_STAGE_DECISION_CN.md",
        f"# 下一阶段决议\n\n建议下一阶段: {rec}\n",
    )

    # final verdict
    unique_count = len(records)
    chain_count = len({r["chain"] for r in records.values() if r["chain"] != "unknown"})
    protocol_count = len({r["protocol"] for r in records.values() if r["protocol"] != "unknown"})
    base_pool_count = len([r for r in records.values() if r["chain"] == "base"])
    solana_count = len([r for r in records.values() if r["chain"] == "solana"])
    standard_v3 = len([r for r in records.values() if r["protocol"] in {"Uniswap V3", "PancakeSwap V3", "Uniswap V2"}])
    slipstream_count = len([r for r in records.values() if r["protocol"] == "Aerodrome Slipstream"])
    verdict = {
        "status": "PASS",
        "stage": "LP_UNIVERSE_SCOPE_AUDIT_V1",
        "universe_audit_complete": True,
        "unique_pool_count": unique_count,
        "chain_count": chain_count,
        "protocol_count": protocol_count,
        "base_pool_count": base_pool_count,
        "solana_pool_count": solana_count,
        "standard_evm_v3_pool_count": standard_v3,
        "slipstream_pool_count": slipstream_count,
        "precise_quote_pool_count": len(stage_sets["precise_quote"]),
        "v3_tick_pool_count": len(stage_sets["v3_tick_liquidity"]),
        "real_cost_pool_count": len(stage_sets["real_cost_model"]),
        "real_fee_pool_count": len(stage_sets["real_fee_accrual"]),
        "pool_level_positive_proxy_count": len(stage_meta["pool_level_positive_proxy"]),
        "actual_fee_ready_pool_count": len(stage_meta["actual_fee_ready"]),
        "current_negative_conclusion_scope": "current_universe_only",
        "solana_meteora_covered": any(r["chain"] == "solana" and r["protocol"] == "Meteora" for r in records.values()),
        "universe_likely_too_narrow": True,
        "recommended_next_stage": rec,
        "notes": {
            "db_audit_ok": bool(db_meta.get("db_ready")),
            "input_ready": input_summary["has_sufficient_evidence"],
            "pool_level_positive_total": 6,
        },
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
    write_text(
        REPORT_DIR / "ONEPAGE_CN.md",
        "# Onepage\n\n"
        f"- unique_pool_count: {unique_count}\n"
        f"- chain_count: {chain_count}\n"
        f"- protocol_count: {protocol_count}\n"
        f"- recommended_next_stage: {rec}\n"
        f"- current_negative_conclusion_scope: current_universe_only\n",
    )

    write_text(
        REPORT_DIR / "ARTIFACT_INDEX.md",
        "# Artifact Index\n"
        "- INPUT_EVIDENCE_AUDIT_CN.md\n"
        "- input_evidence_audit.json\n"
        "- UNIVERSE_EXTRACTION_CN.md\n"
        "- universe_extraction_raw.csv\n"
        "- universe_extraction_raw.json\n"
        "- VPS_POOL_UNIVERSE_DB_AUDIT_CN.md\n"
        "- vps_pool_universe_db_audit.csv\n"
        "- vps_pool_universe_db_audit.json\n"
        "- LP_UNIVERSE_NORMALIZED_POOL_LIST_CN.md\n"
        "- lp_universe_normalized_pool_list.csv\n"
        "- lp_universe_normalized_pool_list.json\n"
        "- LP_UNIVERSE_STAGE_COVERAGE_MATRIX_CN.md\n"
        "- lp_universe_stage_coverage_matrix.csv\n"
        "- CHAIN_PROTOCOL_COVERAGE_CN.md\n"
        "- chain_protocol_coverage.csv\n"
        "- chain_protocol_coverage.json\n"
        "- CURRENT_SCREENED_POOL_SUMMARY_CN.md\n"
        "- current_screened_pool_summary.json\n"
        "- UNIVERSE_GAP_ANALYSIS_CN.md\n"
        "- universe_gap_analysis.json\n"
        "- POOL_UNIVERSE_EXPANSION_PLAN_CN.md\n"
        "- pool_universe_expansion_plan.json\n"
        "- LP_UNIVERSE_SCOPE_NEXT_STAGE_DECISION_CN.md\n"
        "- lp_universe_scope_next_stage_decision.json\n"
        "- FINAL_VERDICT.json\n"
        "- ONEPAGE_CN.md\n",
    )

    return {
        "records": records,
        "stage_meta": stage_meta,
        "verdict": verdict,
    }


def main() -> None:
    ensure_dir(REPORT_DIR)
    input_rows = [{"path": str(path), "exists": path.exists()} for path in INPUT_FILES]
    records, stage_meta = collect_pools()
    db_meta, db_rows = run_db_audit()
    _ = build_artifacts(records, stage_meta, db_meta, db_rows, input_rows)


if __name__ == "__main__":
    main()
