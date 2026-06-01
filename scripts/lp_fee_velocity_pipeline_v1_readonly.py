#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import re
import shlex
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


RUN_ID = os.environ.get("RUN_ID_OVERRIDE", "20260601_100642")
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/Users/bendu/lp-bot/v3"))
REPORT_DIR = Path(
    os.environ.get(
        "REPORT_DIR_OVERRIDE",
        str(REPO_ROOT / "reports" / "lp_fee_velocity_pipeline" / RUN_ID),
    )
)
WORKSPACE = "/opt/lpbot/lp-bot-v3-origin-check"
VNE_DIR = REPO_ROOT / "reports" / "lp_virtual_notional_economics" / "20260601_094238"
QD_DIR = REPO_ROOT / "reports" / "lp_quote_depth_curve_fix" / "20260601_091739"
PIPELINE_DIR = REPO_ROOT / "reports" / "lp_data_pipeline" / "20260601_084943"
SCALE_DIR = REPO_ROOT / "reports" / "lp_scale_economics" / "20260601_082100"
FREEZE_DIR = REPO_ROOT / "reports" / "final_freeze" / "20260531_124000"
WINDOWS = {
    "recent_24h": 24 * 3600,
    "recent_48h": 48 * 3600,
    "recent_72h": 72 * 3600,
    "recent_7d": 7 * 24 * 3600,
}
HORIZON_HOURS = {"15m": 0.25, "30m": 0.5, "1h": 1.0, "2h": 2.0}
NOTIONALS = [20, 100, 500, 1000, 2000]
ALLOWED_NEXT = {
    "LP_VIRTUAL_NOTIONAL_ECONOMICS_V2",
    "LP_IL_LVR_PIPELINE_V1",
    "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT",
    "LP_ENTRY_SAFE_SNAPSHOT_PIPELINE_V1",
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


def as_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


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
    out = proc.stdout.strip()
    if not out:
        return []
    return list(csv.DictReader(out.splitlines()))


def ssh_psql_exec(sql: str) -> None:
    remote_python = f"""
import os, psycopg2
sql = {sql!r}
dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL") or os.environ.get("SHADOW_POSTGRES_DSN")
if not dsn:
    raise SystemExit(2)
conn = psycopg2.connect(dsn)
conn.autocommit = True
cur = conn.cursor()
cur.execute(sql)
cur.close()
conn.close()
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
    parsed: dict[str, Any] = {"db_ready": False, "stdout": redact_secretish(proc.stdout), "stderr": redact_secretish(proc.stderr)}
    for line in proc.stdout.splitlines():
        if "DSN_PRESENT=" in line:
            parsed["dsn_present"] = line.split("=", 1)[1].strip()
        elif "DB_CONNECT=" in line:
            parsed["db_connect"] = line.split("=", 1)[1].strip()
        elif "DB_NAME=" in line:
            parsed["db_name"] = line.split("=", 1)[1].strip()
        elif "DB_USER=" in line:
            parsed["db_user"] = line.split("=", 1)[1].strip()
    parsed["db_ready"] = parsed.get("dsn_present") == "yes" and parsed.get("db_connect") == "ok"
    return parsed


def input_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    inputs = [
        VNE_DIR / "FINAL_VERDICT.json",
        VNE_DIR / "VIRTUAL_ECONOMICS_FORMULA_V1_CN.md",
        VNE_DIR / "VIRTUAL_ECONOMICS_DATA_JOIN_AUDIT_CN.md",
        VNE_DIR / "virtual_economics_data_join_audit.csv",
        VNE_DIR / "VIRTUAL_NOTIONAL_ECONOMICS_RESULTS_CN.md",
        VNE_DIR / "virtual_notional_economics_results.csv",
        VNE_DIR / "BREAK_EVEN_AND_CAPACITY_ANALYSIS_CN.md",
        VNE_DIR / "break_even_and_capacity_analysis.csv",
        VNE_DIR / "VIRTUAL_NOTIONAL_CANDIDATE_RANKING_CN.md",
        VNE_DIR / "virtual_notional_candidate_ranking.csv",
        VNE_DIR / "LP_VIRTUAL_NOTIONAL_NEXT_STAGE_DECISION_CN.md",
        VNE_DIR / "lp_virtual_notional_next_stage_decision.json",
        QD_DIR / "FINAL_VERDICT.json",
        QD_DIR / "QUOTE_DEPTH_CURVE_V2_RESULTS_CN.md",
        QD_DIR / "quote_depth_curve_v2_results.csv",
        PIPELINE_DIR / "FEE_DATA_SOURCE_FEASIBILITY_CN.md",
        SCALE_DIR / "VIRTUAL_NOTIONAL_ECONOMICS_MODEL_CN.md",
        SCALE_DIR / "LP_POOL_SCORING_SYSTEM_V1_CN.md",
        FREEZE_DIR / "FINAL_VERDICT.json",
    ]
    rows = []
    missing = []
    prior = load_json(VNE_DIR / "FINAL_VERDICT.json")
    for path in inputs:
        exists = path.exists()
        rows.append({"path": str(path.relative_to(REPO_ROOT)), "exists": exists})
        if not exists:
            missing.append(str(path.relative_to(REPO_ROOT)))
    audit = {
        "missing_input_list": missing,
        "previous_stage_ok": prior.get("stage") == "LP_VIRTUAL_NOTIONAL_ECONOMICS_V1",
        "positive_proxy_zero": as_int(prior.get("positive_proxy_count")) == 0,
        "recommended_next_stage_ok": prior.get("recommended_next_stage") == "LP_FEE_VELOCITY_PIPELINE_V1",
        "main_blocker_fee_proxy": True,
        "can_execute_fee_velocity_pipeline": len(missing) == 0
        and prior.get("stage") == "LP_VIRTUAL_NOTIONAL_ECONOMICS_V1"
        and as_int(prior.get("positive_proxy_count")) == 0
        and prior.get("recommended_next_stage") == "LP_FEE_VELOCITY_PIPELINE_V1",
    }
    return rows, audit


def load_prior_quote_rows() -> list[dict[str, str]]:
    return load_csv(QD_DIR / "quote_depth_curve_v2_results.csv")


def load_prior_econ_rows() -> list[dict[str, str]]:
    return load_csv(VNE_DIR / "virtual_notional_economics_results.csv")


def fee_inventory() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    queries = {
        "realized_lp_fee_accrual": "select count(*) as row_count, count(*) filter (where fee_usd is not null) as fee_rows, count(*) filter (where created_at >= extract(epoch from now() - interval '7 day')) as recent_7d_count, count(distinct pool_id) as pool_coverage from shadow_position_marks",
        "mark_volume_x_fee_tier_proxy": "select count(*) as row_count, count(*) filter (where created_at >= extract(epoch from now() - interval '7 day')) as recent_7d_count, count(distinct pool_id) as pool_coverage from shadow_position_marks",
        "pool_score_history_fee_apr_score": "select count(*) as row_count, count(*) filter (where block_time >= extract(epoch from now() - interval '7 day')) as recent_7d_count, count(distinct pool_id) as pool_coverage from pool_score_history",
        "pools_current_volume_cache": "select count(*) as row_count, count(*) filter (where updated_at >= extract(epoch from now() - interval '7 day')) as recent_7d_count, count(distinct pool_id) as pool_coverage from pools",
        "existing_fee_velocity_research": "select count(*) as row_count, count(*) filter (where created_at >= now() - interval '7 day') as recent_7d_count, count(distinct pool_id) as pool_coverage from fee_velocity_exit_depth_counterfactual_v1",
    }
    source_defs = [
        {
            "source_name": "realized_lp_fee_accrual",
            "table_or_path": "shadow_position_marks.fee_usd",
            "available": "partial",
            "time_bucket_support": "position_mark_only",
            "entry_safe_possible": "no",
            "confidence": "low",
            "limitations": "fee_usd is post-position mark accrual and not safe for entry decision timing",
            "recommended_for_v1": "no",
        },
        {
            "source_name": "mark_volume_x_fee_tier_proxy",
            "table_or_path": "shadow_position_marks.current_vol24h_usd/current_tvl_usd + pools.fee_bps",
            "available": "yes",
            "time_bucket_support": "mark_time_buckets",
            "entry_safe_possible": "yes",
            "confidence": "medium",
            "limitations": "rolling 24h volume snapshot, not raw swap logs; requires pre-cutoff mark selection",
            "recommended_for_v1": "yes",
        },
        {
            "source_name": "pool_score_history_fee_apr_score",
            "table_or_path": "pool_score_history.score_json.FeeAPRScore",
            "available": "yes",
            "time_bucket_support": "block_time_buckets",
            "entry_safe_possible": "yes",
            "confidence": "low",
            "limitations": "score-only, not raw fee amount or raw volume",
            "recommended_for_v1": "yes",
        },
        {
            "source_name": "onchain_swap_logs",
            "table_or_path": "not_present",
            "available": "no",
            "time_bucket_support": "none",
            "entry_safe_possible": "no",
            "confidence": "low",
            "limitations": "no canonical swap log table found in current VPS Postgres",
            "recommended_for_v1": "no",
        },
        {
            "source_name": "pools_current_volume_cache",
            "table_or_path": "pools.vol_24h + fee_bps",
            "available": "partial",
            "time_bucket_support": "current_snapshot_only",
            "entry_safe_possible": "no",
            "confidence": "low",
            "limitations": "current snapshot only, not sample-time safe",
            "recommended_for_v1": "diagnostic_only",
        },
        {
            "source_name": "existing_fee_velocity_research",
            "table_or_path": "fee_velocity_exit_depth_counterfactual_v1",
            "available": "partial",
            "time_bucket_support": "sample_windows",
            "entry_safe_possible": "yes",
            "confidence": "low",
            "limitations": "fee fields mostly empty in current rows",
            "recommended_for_v1": "no",
        },
        {
            "source_name": "missing_direct_fee_accrual",
            "table_or_path": "unavailable",
            "available": "no",
            "time_bucket_support": "none",
            "entry_safe_possible": "no",
            "confidence": "low",
            "limitations": "no timestamp-clean feeGrowthInside/global fee accrual source found",
            "recommended_for_v1": "no",
        },
    ]
    metrics = {}
    for name, q in queries.items():
        rows = ssh_psql_csv(q)
        metrics[name] = rows[0] if rows else {}
    out = []
    for item in source_defs:
        m = metrics.get(item["source_name"], {})
        out.append({**item, **m})
    summary = {
        "primary_recommended_source": "mark_volume_x_fee_tier_proxy",
        "fallback_source": "pool_score_history_fee_apr_score",
        "swap_logs_available": False,
    }
    return out, summary


def fee_policy() -> tuple[str, dict[str, Any]]:
    payload = {
        "sample_start_time": "entry decision time",
        "feature_cutoff_time_rule": "feature_cutoff_time <= sample_start_time",
        "previous_fully_closed_bucket_rule": True,
        "banned_future_data": [
            "future volume",
            "future fee accrual",
            "same-bucket incomplete volume",
            "unknown timestamp fee",
        ],
        "allowed_fee_features": [
            "previous bucket volume x fee tier from shadow_position_marks current_vol24h_usd/current_tvl_usd",
            "previous bucket pool_score_history FeeAPRScore",
            "previous bucket cached volume proxy only as low confidence fallback",
        ],
        "diagnostic_only_fee_features": [
            "realized fee after sample_start",
            "future volume",
            "same bucket incomplete volume",
            "unknown timestamp fee",
        ],
        "confidence_levels": {
            "high": "timestamp-safe mark volume x fee tier with stable recent coverage",
            "medium": "score_history or mark-volume proxy with partial coverage",
            "low": "external cached approximation or stale/incomplete data",
        },
    }
    md = "# Entry-Safe Fee Velocity Policy\n\n" + "\n".join([f"- `{k}`: `{v}`" if not isinstance(v, (list, dict)) else f"- `{k}`" for k, v in payload.items() if k not in {"allowed_fee_features","diagnostic_only_fee_features","confidence_levels"}]) + "\n- allowed_fee_features:\n" + "\n".join([f"  - `{x}`" for x in payload["allowed_fee_features"]]) + "\n- diagnostic_only_fee_features:\n" + "\n".join([f"  - `{x}`" for x in payload["diagnostic_only_fee_features"]]) + "\n- confidence_levels:\n" + "\n".join([f"  - `{k}`: `{v}`" for k, v in payload["confidence_levels"].items()]) + "\n"
    return md, payload


def build_fee_rows(quote_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    pool_cutoff = {}
    for row in quote_rows:
        if row["confidence"] in {"high", "medium"} and row["entry_safe"] == "yes":
            pool_cutoff.setdefault(row["pool_id"], row["feature_cutoff_time"])
    if not pool_cutoff:
        return []
    pool_ids = ",".join("'" + p.replace("'", "''") + "'" for p in pool_cutoff)
    cases = " ".join([f"when '{pid}' then {cutoff}" for pid, cutoff in pool_cutoff.items()])
    query = f"""
with cutoff(pool_id, feature_cutoff_time) as (
  values {",".join([f"('{pid}', {cutoff})" for pid, cutoff in pool_cutoff.items()])}
),
mark_base as (
  select
    spm.pool_id,
    concat(p.token0, '/', p.token1) as token_pair,
    p.chain,
    p.protocol,
    p.fee_bps,
    c.feature_cutoff_time,
    spm.mark_time,
    spm.current_vol24h_usd,
    spm.current_tvl_usd
  from shadow_position_marks spm
  join cutoff c using (pool_id)
  join pools p using (pool_id)
  where spm.pool_id in ({pool_ids})
    and spm.mark_time <= c.feature_cutoff_time
),
score_base as (
  select
    psh.pool_id,
    c.feature_cutoff_time,
    psh.block_time,
    psh.score_json::json->>'FeeAPRScore' as fee_apr_score
  from pool_score_history psh
  join cutoff c using (pool_id)
  where psh.pool_id in ({pool_ids})
    and psh.block_time <= c.feature_cutoff_time
)
select * from mark_base order by pool_id, mark_time desc limit 5000
"""
    mark_rows = ssh_psql_csv(query)
    score_query = f"""
with cutoff(pool_id, feature_cutoff_time) as (
  values {",".join([f"('{pid}', {cutoff})" for pid, cutoff in pool_cutoff.items()])}
)
select
  psh.pool_id,
  c.feature_cutoff_time,
  psh.block_time,
  psh.score_json::json->>'FeeAPRScore' as fee_apr_score
from pool_score_history psh
join cutoff c using (pool_id)
where psh.pool_id in ({pool_ids})
  and psh.block_time <= c.feature_cutoff_time
order by psh.pool_id, psh.block_time desc
limit 5000
"""
    score_rows = ssh_psql_csv(score_query)
    by_pool_marks: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in mark_rows:
        by_pool_marks[row["pool_id"]].append(row)
    by_pool_scores: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in score_rows:
        by_pool_scores[row["pool_id"]].append(row)
    out = []
    for pool_id, cutoff in pool_cutoff.items():
        marks = by_pool_marks.get(pool_id, [])
        scores = by_pool_scores.get(pool_id, [])
        base = marks[0] if marks else None
        if not base:
            # score-only fallback row per window
            token_pair = next((r["token_pair"] for r in quote_rows if r["pool_id"] == pool_id), "")
            for window, seconds in WINDOWS.items():
                score = as_float(scores[0]["fee_apr_score"]) if scores else None
                conf = "low"
                invalid = "" if score is not None else "no_mark_volume_or_score_history"
                fee_apr_proxy = None if score is None else (score / 100.0) * 0.35
                row = {
                    "run_id": RUN_ID, "pool_id": pool_id, "token_pair": token_pair, "chain": "base", "pool_type": "unknown",
                    "fee_source": "pool_score_history_fee_apr_score", "fee_tier_bps": None, "window_label": window,
                    "bucket_start": int(float(cutoff) - seconds), "bucket_end": int(float(cutoff)), "feature_cutoff_time": int(float(cutoff)),
                    "entry_safe": "yes", "volume_usd_proxy": None, "swap_count": None, "gross_fee_pool_usd_proxy": None,
                    "lp_fee_share_assumption": None, "fee_velocity_rate_15m": None if score is None else fee_apr_proxy * 0.25 / 24 / 365,
                    "fee_velocity_rate_30m": None if score is None else fee_apr_proxy * 0.5 / 24 / 365,
                    "fee_velocity_rate_1h": None if score is None else fee_apr_proxy * 1.0 / 24 / 365,
                    "fee_velocity_rate_2h": None if score is None else fee_apr_proxy * 2.0 / 24 / 365,
                    "fee_apr_proxy": fee_apr_proxy, "confidence": conf,
                    "confidence_reason": "score_history_only_low_confidence", "invalid_reason": invalid,
                }
                out.append(row)
            continue
        token_pair = base["token_pair"]
        chain = "base" if str(base["chain"]) == "1" else "unknown"
        pool_type = "concentrated_liquidity" if "v3" in (base["protocol"] or "").lower() or "slipstream" in (base["protocol"] or "").lower() else ("constant_product" if "v2" in (base["protocol"] or "").lower() else "unknown")
        fee_bps = as_float(base["fee_bps"]) or 0.0
        for window, seconds in WINDOWS.items():
            window_marks = [m for m in marks if int(float(m["mark_time"])) >= int(float(cutoff) - seconds)]
            avg_vol = None
            avg_tvl = None
            if window_marks:
                vols = [as_float(m["current_vol24h_usd"]) for m in window_marks if as_float(m["current_vol24h_usd"]) is not None]
                tvls = [as_float(m["current_tvl_usd"]) for m in window_marks if as_float(m["current_tvl_usd"]) is not None]
                if vols and tvls:
                    avg_vol = sum(vols) / len(vols)
                    avg_tvl = sum(tvls) / len(tvls)
            if avg_vol is not None and avg_tvl and avg_tvl > 0 and fee_bps > 0:
                gross_fee_pool = avg_vol * fee_bps / 10000.0
                daily_rate = gross_fee_pool / avg_tvl
                confidence = "high" if len(window_marks) >= 10 and window == "recent_7d" else "medium"
                invalid_reason = ""
                confidence_reason = "entry_safe_mark_volume_x_fee_tier"
            else:
                score = as_float(scores[0]["fee_apr_score"]) if scores else None
                gross_fee_pool = None
                daily_rate = None if score is None else (score / 100.0) * 0.002
                confidence = "low"
                invalid_reason = "" if score is not None else "missing_mark_volume_and_score"
                confidence_reason = "score_history_feeapr_fallback"
            row = {
                "run_id": RUN_ID,
                "pool_id": pool_id,
                "token_pair": token_pair,
                "chain": chain,
                "pool_type": pool_type,
                "fee_source": "mark_volume_x_fee_tier_proxy" if gross_fee_pool is not None else "pool_score_history_fee_apr_score",
                "fee_tier_bps": fee_bps if fee_bps > 0 else None,
                "window_label": window,
                "bucket_start": int(float(cutoff) - seconds),
                "bucket_end": int(float(cutoff)),
                "feature_cutoff_time": int(float(cutoff)),
                "entry_safe": "yes",
                "volume_usd_proxy": avg_vol,
                "swap_count": None,
                "gross_fee_pool_usd_proxy": gross_fee_pool,
                "lp_fee_share_assumption": None if avg_tvl is None else 1.0 / avg_tvl,
                "fee_velocity_rate_15m": None if daily_rate is None else daily_rate * 0.25 / 24.0,
                "fee_velocity_rate_30m": None if daily_rate is None else daily_rate * 0.5 / 24.0,
                "fee_velocity_rate_1h": None if daily_rate is None else daily_rate * 1.0 / 24.0,
                "fee_velocity_rate_2h": None if daily_rate is None else daily_rate * 2.0 / 24.0,
                "fee_apr_proxy": None if daily_rate is None else daily_rate * 365.0,
                "confidence": confidence,
                "confidence_reason": confidence_reason,
                "invalid_reason": invalid_reason,
            }
            out.append(row)
    return out


def create_fee_table(rows: list[dict[str, Any]]) -> None:
    run_id_sql = "'" + RUN_ID.replace("'", "''") + "'"
    def sql_text(v: str | None) -> str:
        if v is None:
            return "null"
        return "'" + str(v).replace("'", "''") + "'"
    create_sql = f"""
create table if not exists lp_fee_velocity_v1 (
  run_id text not null,
  pool_id text not null,
  token_pair text,
  chain text,
  pool_type text,
  fee_source text,
  fee_tier_bps double precision,
  window_label text,
  bucket_start bigint,
  bucket_end bigint,
  feature_cutoff_time bigint,
  entry_safe text,
  volume_usd_proxy double precision,
  swap_count integer,
  gross_fee_pool_usd_proxy double precision,
  lp_fee_share_assumption double precision,
  fee_velocity_rate_15m double precision,
  fee_velocity_rate_30m double precision,
  fee_velocity_rate_1h double precision,
  fee_velocity_rate_2h double precision,
  fee_apr_proxy double precision,
  confidence text,
  confidence_reason text,
  invalid_reason text,
  created_at timestamptz default now()
);
delete from lp_fee_velocity_v1 where run_id = {run_id_sql};
"""
    ssh_psql_exec(create_sql)
    chunks = [rows[i:i+100] for i in range(0, len(rows), 100)]
    for chunk in chunks:
        vals = []
        for r in chunk:
            vals.append("(" + ",".join([
                sql_text(RUN_ID), sql_text(r["pool_id"]), sql_text(r["token_pair"]), sql_text(r["chain"]), sql_text(r["pool_type"]),
                sql_text(r["fee_source"]), "null" if r["fee_tier_bps"] is None else str(float(r["fee_tier_bps"])), sql_text(r["window_label"]),
                str(int(r["bucket_start"])), str(int(r["bucket_end"])), str(int(r["feature_cutoff_time"])), sql_text(r["entry_safe"]),
                "null" if r["volume_usd_proxy"] is None else str(float(r["volume_usd_proxy"])),
                "null" if r["swap_count"] is None else str(int(r["swap_count"])),
                "null" if r["gross_fee_pool_usd_proxy"] is None else str(float(r["gross_fee_pool_usd_proxy"])),
                "null" if r["lp_fee_share_assumption"] is None else str(float(r["lp_fee_share_assumption"])),
                "null" if r["fee_velocity_rate_15m"] is None else str(float(r["fee_velocity_rate_15m"])),
                "null" if r["fee_velocity_rate_30m"] is None else str(float(r["fee_velocity_rate_30m"])),
                "null" if r["fee_velocity_rate_1h"] is None else str(float(r["fee_velocity_rate_1h"])),
                "null" if r["fee_velocity_rate_2h"] is None else str(float(r["fee_velocity_rate_2h"])),
                "null" if r["fee_apr_proxy"] is None else str(float(r["fee_apr_proxy"])),
                sql_text(r["confidence"]), sql_text(r["confidence_reason"]), sql_text(r["invalid_reason"]), "now()"
            ]) + ")")
        insert_sql = "insert into lp_fee_velocity_v1 (run_id,pool_id,token_pair,chain,pool_type,fee_source,fee_tier_bps,window_label,bucket_start,bucket_end,feature_cutoff_time,entry_safe,volume_usd_proxy,swap_count,gross_fee_pool_usd_proxy,lp_fee_share_assumption,fee_velocity_rate_15m,fee_velocity_rate_30m,fee_velocity_rate_1h,fee_velocity_rate_2h,fee_apr_proxy,confidence,confidence_reason,invalid_reason,created_at) values " + ",".join(vals) + ";"
        ssh_psql_exec(insert_sql)


def fee_quality_gate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_pool = defaultdict(list)
    for r in rows:
        by_pool[r["pool_id"]].append(r)
    fee_ready = []
    blockers = {}
    high = medium = low = 0
    for pool_id, pool_rows in by_pool.items():
        confs = {r["confidence"] for r in pool_rows}
        if "high" in confs:
            high += 1
        elif "medium" in confs:
            medium += 1
        else:
            low += 1
        req = []
        for window in WINDOWS:
            row = next((x for x in pool_rows if x["window_label"] == window), None)
            ok = row and row["entry_safe"] == "yes" and row["confidence"] in {"high", "medium"} and row["invalid_reason"] == ""
            req.append(bool(ok))
        if all(req):
            fee_ready.append(pool_id)
        else:
            blockers[pool_id] = "missing_medium_high_entry_safe_coverage"
    return {
        "fee_ready_pool_count": len(fee_ready),
        "fee_ready_pool_ids": fee_ready,
        "high_confidence_pool_count": high,
        "medium_confidence_pool_count": medium,
        "low_confidence_pool_count": low,
        "fee_velocity_ready": len(fee_ready) >= 3,
        "blockers": blockers,
    }


def rerun_preview(prev_rows: list[dict[str, str]], fee_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fee_map = {(r["pool_id"], r["window_label"]): r for r in fee_rows}
    preview = []
    for row in prev_rows:
        window = "recent_7d"
        fee = fee_map.get((row["pool_id"], window))
        if fee is None:
            continue
        rate_key = {
            "15m": "fee_velocity_rate_15m",
            "30m": "fee_velocity_rate_30m",
            "1h": "fee_velocity_rate_1h",
            "2h": "fee_velocity_rate_2h",
        }[row["horizon"]]
        new_fee_rate = fee.get(rate_key)
        new_fee_rate = as_float(new_fee_rate)
        old_gross = as_float(row["gross_fee_proxy_usd"]) or 0.0
        old_net = as_float(row["net_ev_proxy_usd"])
        notional = as_float(row["virtual_notional_usd"]) or 0.0
        if new_fee_rate is None:
            new_gross = None
            new_net = old_net
            new_status = row["ev_status"]
        else:
            new_gross = notional * new_fee_rate
            base_without_fee = 0.0 if old_net is None else old_net - old_gross
            new_net = base_without_fee + new_gross
            if row["capacity_pass"] != "yes":
                new_status = "CAPACITY_FAIL"
            elif new_net > 0:
                new_status = "POSITIVE_PROXY"
            elif (as_float(row["variable_edge_rate"]) or -1) <= 0:
                new_status = "NO_SIZE_CAN_FIX"
            else:
                new_status = "NEGATIVE_PROXY"
        preview.append({
            **row,
            "fee_source_v1": fee["fee_source"],
            "new_gross_fee_proxy_usd": new_gross,
            "new_net_ev_proxy_usd": new_net,
            "new_status": new_status,
            "delta_ev": None if old_net is None or new_net is None else new_net - old_net,
            "fee_confidence": fee["confidence"],
            "window_label": window,
        })
    agg = {
        "previous_positive_proxy_count": sum(1 for r in prev_rows if r["ev_status"] == "POSITIVE_PROXY"),
        "new_positive_proxy_count": sum(1 for r in preview if r["new_status"] == "POSITIVE_PROXY"),
        "previous_best_net_ev_proxy_usd": max((as_float(r["net_ev_proxy_usd"]) for r in prev_rows if as_float(r["net_ev_proxy_usd"]) is not None), default=None),
        "new_best_net_ev_proxy_usd": max((as_float(r["new_net_ev_proxy_usd"]) for r in preview if as_float(r["new_net_ev_proxy_usd"]) is not None), default=None),
        "positive_proxy_by_notional": dict(Counter(str(r["virtual_notional_usd"]) for r in preview if r["new_status"] == "POSITIVE_PROXY")),
        "positive_proxy_by_tier": dict(Counter(r["inferred_tier"] for r in preview if r["new_status"] == "POSITIVE_PROXY")),
        "no_size_can_fix_count": sum(1 for r in preview if r["new_status"] == "NO_SIZE_CAN_FIX"),
        "below_break_even_count": sum(1 for r in preview if r["new_status"] == "BELOW_BREAK_EVEN"),
        "capacity_fail_count": sum(1 for r in preview if r["new_status"] == "CAPACITY_FAIL"),
        "data_insufficient_count": sum(1 for r in preview if r["new_status"] == "DATA_INSUFFICIENT"),
    }
    return preview, agg


def blocker_diag(preview: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_pool = defaultdict(list)
    for r in preview:
        by_pool[r["pool_id"]].append(r)
    rows = []
    for pool_id, items in by_pool.items():
        best = max(items, key=lambda r: as_float(r["new_net_ev_proxy_usd"]) if as_float(r["new_net_ev_proxy_usd"]) is not None else -999999)
        old = as_float(best["net_ev_proxy_usd"])
        new = as_float(best["new_net_ev_proxy_usd"])
        if best["new_status"] == "POSITIVE_PROXY":
            blocker = ""
            action = "LP_VIRTUAL_NOTIONAL_ECONOMICS_V2"
        elif best["primary_blocker"] in {"fixed_cost_too_high", "fee_too_low"}:
            blocker = "fee_still_too_low" if best["primary_blocker"] == "fee_too_low" else "fixed_cost_now_main"
            action = "LP_IL_LVR_PIPELINE_V1" if best["primary_blocker"] == "fixed_cost_too_high" else "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT"
        else:
            blocker = best["primary_blocker"]
            action = "LP_IL_LVR_PIPELINE_V1" if blocker == "il_lvr_too_high" else "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT"
        rows.append({
            "pool_id": pool_id,
            "token_pair": best["token_pair"],
            "best_notional": best["virtual_notional_usd"],
            "old_net_ev_proxy": old,
            "new_net_ev_proxy": new,
            "delta_ev": None if old is None or new is None else new - old,
            "old_status": best["ev_status"],
            "new_status": best["new_status"],
            "primary_remaining_blocker": blocker,
            "recommended_action": action,
        })
    return rows


def next_stage_decision(agg: dict[str, Any], fee_gate: dict[str, Any], blockers: list[dict[str, Any]]) -> tuple[str, str]:
    if agg["new_positive_proxy_count"] > 0:
        return "LP_VIRTUAL_NOTIONAL_ECONOMICS_V2", "fee_velocity_v1_created_positive_proxy_preview"
    if fee_gate["fee_velocity_ready"] and any(b["primary_remaining_blocker"] in {"il_lvr_too_high", "fixed_cost_now_main"} for b in blockers):
        return "LP_IL_LVR_PIPELINE_V1", "fee_improved_but_non_fee_blocker_now_dominant"
    if fee_gate["fee_ready_pool_count"] < 3:
        return "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT", "fee_coverage_and_confidence_still_weak"
    if not fee_gate["fee_velocity_ready"]:
        return "LP_ENTRY_SAFE_SNAPSHOT_PIPELINE_V1", "entry_safe_mark_coverage_insufficient"
    return "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT", "fee_pipeline_built_but_preview_still_all_negative"


def final_verdict(fee_rows: list[dict[str, Any]], fee_gate: dict[str, Any], preview_agg: dict[str, Any], blockers: list[dict[str, Any]], next_stage: str, db: dict[str, Any]) -> dict[str, Any]:
    best = max((r for r in blockers if r["new_net_ev_proxy"] is not None), key=lambda r: r["new_net_ev_proxy"], default=None)
    source_counts = Counter(r["fee_source"] for r in fee_rows)
    main_blocker = Counter(b["primary_remaining_blocker"] for b in blockers).most_common(1)[0][0] if blockers else ""
    return {
        "status": "PASS" if fee_gate["fee_ready_pool_count"] >= 3 else "WARN",
        "stage": "LP_FEE_VELOCITY_PIPELINE_V1",
        "data_source": "vps_postgres",
        "db_ready": db["db_ready"],
        "fee_velocity_pipeline_built": True,
        "fee_ready_pool_count": fee_gate["fee_ready_pool_count"],
        "fee_source_primary": source_counts.most_common(1)[0][0] if source_counts else "",
        "high_confidence_count": sum(1 for r in fee_rows if r["confidence"] == "high"),
        "medium_confidence_count": sum(1 for r in fee_rows if r["confidence"] == "medium"),
        "low_confidence_count": sum(1 for r in fee_rows if r["confidence"] == "low"),
        "entry_safe_count": sum(1 for r in fee_rows if r["entry_safe"] == "yes"),
        "economics_preview_ran": True,
        "previous_positive_proxy_count": preview_agg["previous_positive_proxy_count"],
        "new_positive_proxy_count": preview_agg["new_positive_proxy_count"],
        "previous_best_net_ev_proxy_usd": preview_agg["previous_best_net_ev_proxy_usd"],
        "new_best_net_ev_proxy_usd": preview_agg["new_best_net_ev_proxy_usd"],
        "ev_improved": (preview_agg["new_best_net_ev_proxy_usd"] or -9999) > (preview_agg["previous_best_net_ev_proxy_usd"] or -9999),
        "main_remaining_blocker": main_blocker,
        "can_run_virtual_notional_v2_next": next_stage == "LP_VIRTUAL_NOTIONAL_ECONOMICS_V2",
        "can_run_probe_now": False,
        "manual_approval_required_for_probe": True,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage,
    }


def write_reports(input_rows, audit, db, inventory_rows, inventory_summary, policy_md, policy_json, fee_rows, fee_gate, preview_rows, preview_agg, blocker_rows, next_stage, next_reason, verdict):
    write_text(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", "# Input Artifact Audit\n\n" + "\n".join([f"- `{r['path']}`: `{'yes' if r['exists'] else 'no'}`" for r in input_rows]) + "\n")
    write_json(REPORT_DIR / "input_artifact_audit.json", audit)
    write_text(REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md", "# VPS DB Quick Check\n\n" + "\n".join([f"- `{k}`: `{fmt(v)}`" for k, v in db.items() if k in {'dsn_present','db_connect','db_name','db_user','db_ready'}]) + "\n")
    write_csv(REPORT_DIR / "fee_source_inventory.csv", inventory_rows, list(inventory_rows[0].keys()))
    write_json(REPORT_DIR / "fee_source_inventory.json", inventory_summary)
    write_text(REPORT_DIR / "FEE_SOURCE_INVENTORY_CN.md", "# Fee Source Inventory\n\n" + "\n".join([f"- `{r['source_name']}` available=`{r['available']}` confidence=`{r['confidence']}` recommended=`{r['recommended_for_v1']}`" for r in inventory_rows]) + "\n")
    write_text(REPORT_DIR / "ENTRY_SAFE_FEE_VELOCITY_POLICY_CN.md", policy_md)
    write_json(REPORT_DIR / "entry_safe_fee_velocity_policy.json", policy_json)
    schema = {"table_name":"lp_fee_velocity_v1","required_fields":["run_id","pool_id","token_pair","chain","pool_type","fee_source","fee_tier_bps","bucket_start","bucket_end","feature_cutoff_time","entry_safe","volume_usd_proxy","swap_count","gross_fee_pool_usd_proxy","lp_fee_share_assumption","fee_velocity_rate_15m","fee_velocity_rate_30m","fee_velocity_rate_1h","fee_velocity_rate_2h","fee_apr_proxy","confidence","confidence_reason","invalid_reason","created_at"]}
    write_text(REPORT_DIR / "FEE_VELOCITY_SCHEMA_CN.md", "# Fee Velocity Schema\n\n" + "\n".join([f"- `{f}`" for f in schema["required_fields"]]) + "\n")
    write_json(REPORT_DIR / "fee_velocity_schema.json", schema)
    write_csv(REPORT_DIR / "fee_velocity_results.csv", fee_rows, list(fee_rows[0].keys()))
    fee_agg = {
        "pool_count": len({r["pool_id"] for r in fee_rows}),
        "row_count": len(fee_rows),
        "fee_source_distribution": dict(Counter(r["fee_source"] for r in fee_rows)),
        "high_confidence_count": sum(1 for r in fee_rows if r["confidence"] == "high"),
        "medium_confidence_count": sum(1 for r in fee_rows if r["confidence"] == "medium"),
        "low_confidence_count": sum(1 for r in fee_rows if r["confidence"] == "low"),
        "entry_safe_count": sum(1 for r in fee_rows if r["entry_safe"] == "yes"),
        "invalid_count": sum(1 for r in fee_rows if r["invalid_reason"]),
        "pool_coverage": len({r["pool_id"] for r in fee_rows}),
        "recent_7d_coverage": len({r["pool_id"] for r in fee_rows if r["window_label"] == "recent_7d" and r["invalid_reason"] == ""}),
    }
    write_json(REPORT_DIR / "fee_velocity_results.json", fee_agg)
    write_text(REPORT_DIR / "FEE_VELOCITY_RESULTS_CN.md", "# Fee Velocity Results\n\n" + "\n".join([f"- `{k}`: `{fmt(v)}`" for k,v in fee_agg.items()]) + "\n")
    write_json(REPORT_DIR / "fee_velocity_quality_gate.json", fee_gate)
    write_text(REPORT_DIR / "FEE_VELOCITY_QUALITY_GATE_CN.md", "# Fee Velocity Quality Gate\n\n" + "\n".join([f"- `{k}`: `{fmt(v)}`" for k,v in fee_gate.items() if k != 'fee_ready_pool_ids' and k != 'blockers']) + "\n")
    write_csv(REPORT_DIR / "virtual_economics_fee_v1_preview.csv", preview_rows, list(preview_rows[0].keys()))
    write_json(REPORT_DIR / "virtual_economics_fee_v1_preview.json", preview_agg)
    write_text(REPORT_DIR / "VIRTUAL_ECONOMICS_FEE_V1_PREVIEW_CN.md", "# Virtual Economics Fee V1 Preview\n\n" + "\n".join([f"- `{k}`: `{fmt(v)}`" for k,v in preview_agg.items()]) + "\n")
    write_csv(REPORT_DIR / "fee_blocker_diagnosis.csv", blocker_rows, list(blocker_rows[0].keys()))
    write_text(REPORT_DIR / "FEE_BLOCKER_DIAGNOSIS_CN.md", "# Fee Blocker Diagnosis\n\n" + "\n".join([f"- `{r['pool_id']}` delta_ev=`{fmt(r['delta_ev'])}` new_status=`{r['new_status']}` blocker=`{r['primary_remaining_blocker']}`" for r in blocker_rows]) + "\n")
    write_json(REPORT_DIR / "lp_fee_velocity_next_stage_decision.json", {"recommended_next_stage": next_stage, "reason": next_reason})
    write_text(REPORT_DIR / "LP_FEE_VELOCITY_NEXT_STAGE_DECISION_CN.md", f"# LP Fee Velocity Next Stage Decision\n\n- recommended_next_stage: `{next_stage}`\n- reason: `{next_reason}`\n")
    write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
    write_text(REPORT_DIR / "ONEPAGE_CN.md", "# LP Fee Velocity Pipeline V1\n\n" + "\n".join([f"- `{k}`: `{fmt(v)}`" for k,v in verdict.items()]) + "\n")
    artifact_files = ["INPUT_ARTIFACT_AUDIT_CN.md","input_artifact_audit.json","VPS_DB_QUICK_CHECK_CN.md","FEE_SOURCE_INVENTORY_CN.md","fee_source_inventory.csv","fee_source_inventory.json","ENTRY_SAFE_FEE_VELOCITY_POLICY_CN.md","entry_safe_fee_velocity_policy.json","FEE_VELOCITY_SCHEMA_CN.md","fee_velocity_schema.json","FEE_VELOCITY_RESULTS_CN.md","fee_velocity_results.csv","fee_velocity_results.json","FEE_VELOCITY_QUALITY_GATE_CN.md","fee_velocity_quality_gate.json","VIRTUAL_ECONOMICS_FEE_V1_PREVIEW_CN.md","virtual_economics_fee_v1_preview.csv","virtual_economics_fee_v1_preview.json","FEE_BLOCKER_DIAGNOSIS_CN.md","fee_blocker_diagnosis.csv","LP_FEE_VELOCITY_NEXT_STAGE_DECISION_CN.md","lp_fee_velocity_next_stage_decision.json","FINAL_VERDICT.json","ONEPAGE_CN.md"]
    write_text(REPORT_DIR / "ARTIFACT_INDEX.md", "# Artifact Index\n\n" + "\n".join([f"- `{f}`" for f in artifact_files]) + "\n")


def generate() -> dict[str, Any]:
    ensure_dir(REPORT_DIR)
    input_rows, audit = input_audit()
    if not audit["previous_stage_ok"]:
        write_text(REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md", "# Wrong Stage Blocker\n\n上轮 stage 不是 `LP_VIRTUAL_NOTIONAL_ECONOMICS_V1`。\n")
        verdict = {"status":"FAIL","stage":"LP_FEE_VELOCITY_PIPELINE_V1","data_source":"vps_postgres","db_ready":False,"fee_velocity_pipeline_built":False,"fee_ready_pool_count":0,"fee_source_primary":"","high_confidence_count":0,"medium_confidence_count":0,"low_confidence_count":0,"entry_safe_count":0,"economics_preview_ran":False,"previous_positive_proxy_count":0,"new_positive_proxy_count":0,"previous_best_net_ev_proxy_usd":None,"new_best_net_ev_proxy_usd":None,"ev_improved":False,"main_remaining_blocker":"","can_run_virtual_notional_v2_next":False,"can_run_probe_now":False,"manual_approval_required_for_probe":True,"edge_proven":"no","tiny_canary_candidate":"no","tiny_canary_allowed":"no","recommended_next_stage":"LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT"}
        write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
        return verdict
    db = run_db_quick_check()
    inventory_rows, inventory_summary = fee_inventory()
    policy_md, policy_json = fee_policy()
    quote_rows = load_prior_quote_rows()
    prev_rows = load_prior_econ_rows()
    fee_rows = build_fee_rows(quote_rows)
    create_fee_table(fee_rows)
    fee_gate = fee_quality_gate(fee_rows)
    preview_rows, preview_agg = rerun_preview(prev_rows, fee_rows)
    blocker_rows = blocker_diag(preview_rows)
    next_stage, next_reason = next_stage_decision(preview_agg, fee_gate, blocker_rows)
    verdict = final_verdict(fee_rows, fee_gate, preview_agg, blocker_rows, next_stage, db)
    write_reports(input_rows, audit, db, inventory_rows, inventory_summary, policy_md, policy_json, fee_rows, fee_gate, preview_rows, preview_agg, blocker_rows, next_stage, next_reason, verdict)
    return verdict


def main() -> None:
    print(json.dumps(generate(), ensure_ascii=False))


if __name__ == "__main__":
    main()
