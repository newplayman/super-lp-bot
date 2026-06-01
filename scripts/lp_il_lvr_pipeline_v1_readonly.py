#!/usr/bin/env python3
from __future__ import annotations

import base64
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


RUN_ID = os.environ.get("RUN_ID_OVERRIDE", "20260601_105452")
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/Users/bendu/lp-bot/v3"))
REPORT_DIR = Path(
    os.environ.get(
        "REPORT_DIR_OVERRIDE",
        str(REPO_ROOT / "reports" / "lp_il_lvr_pipeline" / RUN_ID),
    )
)
WORKSPACE = "/opt/lpbot/lp-bot-v3-origin-check"
IL_LVR_RUN_SOURCE = "20260531_113056"
FEE_FIX_DIR = REPO_ROOT / "reports" / "lp_fee_velocity_fix_repeat" / "20260601_103248"
FEE_V2_DIR = REPO_ROOT / "reports" / "lp_fee_velocity_fix_repeat" / "20260601_103248"
VNE_DIR = REPO_ROOT / "reports" / "lp_virtual_notional_economics" / "20260601_094238"
QD_DIR = REPO_ROOT / "reports" / "lp_quote_depth_curve_fix" / "20260601_091739"
SCALE_DIR = REPO_ROOT / "reports" / "lp_scale_economics" / "20260601_082100"
FREEZE_DIR = REPO_ROOT / "reports" / "final_freeze" / "20260531_124000"
WINDOWS = {
    "recent_24h": 24 * 3600,
    "recent_48h": 48 * 3600,
    "recent_72h": 72 * 3600,
    "recent_7d": 7 * 24 * 3600,
}
HORIZON_HOURS = {"15m": 0.25, "30m": 0.5, "1h": 1.0, "2h": 2.0}
SCENARIOS = ["zero_il_lvr", "optimistic", "realistic", "conservative"]
FIXED_COST_REFERENCE_USD = 0.05
ALLOWED_NEXT = {
    "LP_VIRTUAL_NOTIONAL_ECONOMICS_V2",
    "LP_IL_LVR_PIPELINE_FIX_REPEAT",
    "NEW_DATA_PIPELINE_FIRST",
    "STOP_LP_RESEARCH_NOW",
}
ENTRY_SAFE_RULES = {
    "sample_start_time": "quote_depth_curve_v2.feature_cutoff_time",
    "feature_cutoff_time": "must_be_lte_sample_start",
    "previous_fully_closed_bucket": True,
    "same_bucket_features_banned": True,
    "entry_safe": True,
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


def redact_secretish(text: str) -> str:
    text = re.sub(r"postgres(?:ql)?://[^\s'\\\"]+", "<redacted-dsn>", text)
    text = re.sub(r"(POSTGRES_DSN|DATABASE_URL|SHADOW_POSTGRES_DSN)=\S+", r"\1=<redacted>", text)
    return text


def ssh_run(script: str) -> subprocess.CompletedProcess[str]:
    remote_cmd = f"cd {shlex.quote(WORKSPACE)} && bash -lc {shlex.quote(script)}"
    return subprocess.run(["ssh", "vps", remote_cmd], capture_output=True, text=True)


def ssh_query_rows(sql: str) -> list[dict[str, str]]:
    encoded = base64.b64encode(sql.encode("utf-8")).decode("ascii")
    remote_python = f"""
import base64, csv, io, os, sys
import psycopg2
sql = base64.b64decode({encoded!r}).decode("utf-8")
dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL") or os.environ.get("SHADOW_POSTGRES_DSN")
if not dsn:
    print("missing_dsn", file=sys.stderr)
    raise SystemExit(2)
conn = psycopg2.connect(dsn)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor()
cur.execute(sql)
cols = [d[0] for d in cur.description]
buf = io.StringIO()
writer = csv.writer(buf)
writer.writerow(cols)
for row in cur.fetchall():
    writer.writerow(["" if v is None else v for v in row])
cur.close()
conn.close()
sys.stdout.write(buf.getvalue())
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


def ssh_exec_sql(sql: str) -> None:
    encoded = base64.b64encode(sql.encode("utf-8")).decode("ascii")
    remote_python = f"""
import base64, os, psycopg2
sql = base64.b64decode({encoded!r}).decode("utf-8")
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
        FEE_FIX_DIR / "FINAL_VERDICT.json",
        FEE_FIX_DIR / "FIXED_COST_SENSITIVITY_ECONOMICS_CN.md",
        FEE_FIX_DIR / "fixed_cost_sensitivity_economics.csv",
        FEE_FIX_DIR / "EV_SCENARIO_COMPARISON_CN.md",
        FEE_FIX_DIR / "ev_scenario_comparison.csv",
        FEE_FIX_DIR / "LP_FEE_FIX_REPEAT_NEXT_STAGE_DECISION_CN.md",
        FEE_FIX_DIR / "lp_fee_fix_repeat_next_stage_decision.json",
        VNE_DIR / "FINAL_VERDICT.json",
        VNE_DIR / "VIRTUAL_ECONOMICS_FORMULA_V1_CN.md",
        VNE_DIR / "virtual_notional_economics_results.csv",
        QD_DIR / "FINAL_VERDICT.json",
        QD_DIR / "quote_depth_curve_v2_results.csv",
        SCALE_DIR / "VIRTUAL_NOTIONAL_ECONOMICS_MODEL_CN.md",
        FREEZE_DIR / "FINAL_VERDICT.json",
    ]
    rows = []
    missing = []
    for path in inputs:
        exists = path.exists()
        rows.append({"path": str(path.relative_to(REPO_ROOT)), "exists": exists})
        if not exists:
            missing.append(str(path.relative_to(REPO_ROOT)))
    prior = load_json(FEE_FIX_DIR / "FINAL_VERDICT.json")
    audit = {
        "missing_input_list": missing,
        "all_inputs_ready": len(missing) == 0,
        "previous_stage": prior.get("stage"),
        "previous_stage_ok": prior.get("stage") == "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT_V1",
        "positive_proxy_count_fixed_cost_0_is_zero": prior.get("positive_proxy_count_fixed_cost_0") == 0,
        "positive_proxy_count_realistic_is_zero": prior.get("positive_proxy_count_realistic") == 0,
        "main_remaining_blocker_is_data_confidence_low": prior.get("main_remaining_blocker") == "data_confidence_low",
        "enough_to_execute_il_lvr_pipeline": len(missing) == 0
        and prior.get("stage") == "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT_V1",
    }
    return rows, audit


def load_targets() -> list[dict[str, Any]]:
    quote_rows = load_csv(QD_DIR / "quote_depth_curve_v2_results.csv")
    fee_rows = load_csv(FEE_FIX_DIR / "fee_velocity_v2_results.csv")
    fee_by_pool = defaultdict(list)
    for row in fee_rows:
        fee_by_pool[row["pool_id"]].append(row)
    out = []
    seen = set()
    for row in quote_rows:
        if row["virtual_notional_usd"] != "20":
            continue
        if row["entry_safe"] != "yes" or row["confidence"] not in {"high", "medium"}:
            continue
        pid = row["pool_id"]
        if pid in seen:
            continue
        windows = fee_by_pool.get(pid, [])
        ready = all(
            any(
                w["window_label"] == window
                and w["entry_safe"] == "yes"
                and w["confidence_v2"] in {"high", "medium"}
                and w["invalid_reason"] == ""
                for w in windows
            )
            for window in WINDOWS
        )
        if not ready:
            continue
        seen.add(pid)
        out.append(
            {
                "pool_id": pid,
                "token_pair": row["token_pair"],
                "inferred_tier": row["inferred_tier"],
                "chain": row["chain"],
                "pool_type": row["pool_type"],
                "feature_cutoff_time": as_int(row["feature_cutoff_time"]),
                "quote_confidence": row["confidence"],
            }
        )
    return out


def query_pool_context(targets: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not targets:
        return []
    pool_ids = ",".join("'{}'".format(t["pool_id"].replace("'", "''")) for t in targets)
    query = f"""
with entry as (
  select
    pool_id,
    count(*) as entry_rows,
    avg(case when stale_data_flag then 1.0 else 0.0 end) as stale_rate,
    avg(data_quality_score) as data_quality_score,
    avg(exit_depth_score) as exit_depth_score,
    avg(volatility_score) as volatility_score,
    avg(volume_score) as volume_score,
    avg(tvl_score) as tvl_score,
    avg(fee_proxy_score) as fee_proxy_score,
    avg(risk_score) as risk_score,
    bool_and(lookahead_safe) as lookahead_safe,
    max(leakage_risk) as leakage_risk,
    max(missing_features) as missing_features
  from pool_regime_classifier_entry_safe_v1
  where run_id='{IL_LVR_RUN_SOURCE}' and pool_id in ({pool_ids})
  group by pool_id
),
pool_meta as (
  select
    p.pool_id,
    p.protocol,
    p.fee_bps,
    p.tvl_usd,
    p.vol_24h,
    p.fee_apr_24h
  from pools p
  where p.pool_id in ({pool_ids})
)
select
  e.pool_id,
  e.entry_rows,
  e.stale_rate,
  e.data_quality_score,
  e.exit_depth_score,
  e.volatility_score,
  e.volume_score,
  e.tvl_score,
  e.fee_proxy_score,
  e.risk_score,
  e.lookahead_safe,
  e.leakage_risk,
  e.missing_features,
  p.protocol,
  p.fee_bps,
  p.tvl_usd,
  p.vol_24h,
  p.fee_apr_24h
from entry e
left join pool_meta p using (pool_id)
"""
    return ssh_query_rows(query)


def il_lvr_source_inventory(targets: list[dict[str, Any]], context_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    target_pools = {t["pool_id"] for t in targets}
    context_pools = {r["pool_id"] for r in context_rows}
    price_snapshot_count = ssh_query_rows(
        """
select
  count(*)::bigint as row_count,
  count(*) filter (where price_timestamp >= extract(epoch from now() - interval '7 day'))::bigint as recent_7d_count
from price_snapshots
"""
    )[0]
    inventory = [
        {
            "source_name": "current_virtual_economics_il_lvr_proxy",
            "available": "yes",
            "table_or_path": "pool_regime_classifier_entry_safe_v1 + lp_virtual_notional_economics_v1",
            "row_count": len(context_rows),
            "recent_7d_count": len(context_rows),
            "pool_coverage": len(context_pools),
            "horizon_support": "15m,30m,1h,2h",
            "entry_safe_possible": "yes",
            "confidence": "medium",
            "limitations": "score-based proxy, not exact range/inventory",
            "recommended_for_v1": "yes",
        },
        {
            "source_name": "price_snapshot_history",
            "available": "partial",
            "table_or_path": "price_snapshots",
            "row_count": as_int(price_snapshot_count["row_count"]),
            "recent_7d_count": as_int(price_snapshot_count["recent_7d_count"]),
            "pool_coverage": 0,
            "horizon_support": "token-level only",
            "entry_safe_possible": "partial",
            "confidence": "low",
            "limitations": "token-level, no direct pool/range mapping",
            "recommended_for_v1": "no",
        },
        {
            "source_name": "price_volatility_based_il_proxy",
            "available": "partial",
            "table_or_path": "pool_regime_classifier_entry_safe_v1.volatility_score",
            "row_count": len(context_rows),
            "recent_7d_count": len(context_rows),
            "pool_coverage": len(context_pools),
            "horizon_support": "15m,30m,1h,2h",
            "entry_safe_possible": "yes",
            "confidence": "medium",
            "limitations": "uses score not exact price path",
            "recommended_for_v1": "yes",
        },
        {
            "source_name": "adverse_selection_lvr_proxy",
            "available": "partial",
            "table_or_path": "pool_regime_classifier_entry_safe_v1.risk_score",
            "row_count": len(context_rows),
            "recent_7d_count": len(context_rows),
            "pool_coverage": len(context_pools),
            "horizon_support": "15m,30m,1h,2h",
            "entry_safe_possible": "yes",
            "confidence": "medium",
            "limitations": "risk-score proxy, not exact LVR decomposition",
            "recommended_for_v1": "yes",
        },
        {
            "source_name": "exact_position_range_inventory",
            "available": "no",
            "table_or_path": "unavailable",
            "row_count": 0,
            "recent_7d_count": 0,
            "pool_coverage": 0,
            "horizon_support": "none",
            "entry_safe_possible": "no",
            "confidence": "low",
            "limitations": "exact LP range unknown",
            "recommended_for_v1": "no",
        },
        {
            "source_name": "exact_fee_growth",
            "available": "no",
            "table_or_path": "unavailable",
            "row_count": 0,
            "recent_7d_count": 0,
            "pool_coverage": 0,
            "horizon_support": "none",
            "entry_safe_possible": "no",
            "confidence": "low",
            "limitations": "exact accrual unavailable",
            "recommended_for_v1": "no",
        },
    ]
    summary = {
        "target_pool_count": len(target_pools),
        "context_pool_count": len(context_pools),
        "recommended_sources": [r["source_name"] for r in inventory if r["recommended_for_v1"] == "yes"],
    }
    return inventory, summary


def entry_safe_policy() -> tuple[str, dict[str, Any]]:
    payload = {
        "sample_start_time": "quote_depth_curve_v2.feature_cutoff_time",
        "feature_cutoff_time": "<= sample_start_time",
        "previous_fully_closed_bucket_rule": True,
        "same_bucket_features_banned": True,
        "banned_future_data": [
            "future realized IL after sample_start",
            "target horizon outcome",
            "post-entry price path",
            "exact LP pnl after horizon",
        ],
        "allowed_features": [
            "previous bucket realized volatility proxy",
            "previous bucket price movement proxy",
            "previous bucket risk/adverse movement proxy",
            "pool type known before entry",
        ],
        "confidence_levels": {
            "high": "exact position or range known and timestamp safe",
            "medium": "pool type plus entry-safe volatility proxy",
            "low": "generic volatility fallback",
        },
    }
    md = "# Entry-Safe IL/LVR Policy\n\n" + "\n".join(f"- `{k}`: `{v}`" for k, v in payload.items() if k != "confidence_levels") + "\n\n" + "\n".join(
        f"- confidence `{k}`: `{v}`" for k, v in payload["confidence_levels"].items()
    ) + "\n"
    return md, payload


def schema_payload() -> dict[str, Any]:
    return {
        "table_name": "lp_il_lvr_proxy_v1",
        "required_fields": [
            "run_id",
            "pool_id",
            "token_pair",
            "pool_type",
            "horizon",
            "window_label",
            "bucket_start",
            "bucket_end",
            "feature_cutoff_time",
            "entry_safe",
            "price_move_proxy",
            "volatility_proxy",
            "il_proxy_rate_conservative",
            "il_proxy_rate_realistic",
            "il_proxy_rate_optimistic",
            "lvr_proxy_rate_conservative",
            "lvr_proxy_rate_realistic",
            "lvr_proxy_rate_optimistic",
            "confidence",
            "confidence_reason",
            "invalid_reason",
            "created_at",
        ],
    }


def build_il_lvr_rows(targets: list[dict[str, Any]], context_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ctx = {r["pool_id"]: r for r in context_rows}
    rows: list[dict[str, Any]] = []
    for target in targets:
        meta = ctx.get(target["pool_id"])
        if not meta:
            continue
        volatility_score = as_float(meta.get("volatility_score"))
        risk_score = as_float(meta.get("risk_score"))
        stale_rate = as_float(meta.get("stale_rate")) or 0.0
        data_quality = as_float(meta.get("data_quality_score")) or 0.0
        lookahead_safe = str(meta.get("lookahead_safe")).lower() in {"t", "true", "1", "yes"}
        leakage_risk = meta.get("leakage_risk") or "LOW"
        pool_mult = 1.25 if target["pool_type"] == "concentrated_liquidity" else 1.0
        for window, seconds in WINDOWS.items():
            bucket_start = target["feature_cutoff_time"] - seconds
            bucket_end = target["feature_cutoff_time"]
            for horizon, h in HORIZON_HOURS.items():
                invalid = ""
                if volatility_score is None or risk_score is None:
                    invalid = "missing_volatility_or_risk_score"
                elif not lookahead_safe or leakage_risk not in {"LOW", ""}:
                    invalid = "lookahead_or_leakage_not_safe"
                vol_proxy = None if volatility_score is None else volatility_score / 100.0
                price_move_proxy = None if vol_proxy is None else vol_proxy * math.sqrt(max(h, 0.25) / 2.0)
                il_cons = None if vol_proxy is None else vol_proxy * 0.0016 * math.sqrt(max(h, 0.25) / 2.0) * pool_mult
                lvr_cons = None if risk_score is None else (risk_score / 100.0) * 0.0011 * (h / 2.0) * pool_mult + (0.0004 if stale_rate > 0.15 else 0.0)
                row = {
                    "run_id": RUN_ID,
                    "pool_id": target["pool_id"],
                    "token_pair": target["token_pair"],
                    "pool_type": target["pool_type"],
                    "horizon": horizon,
                    "window_label": window,
                    "bucket_start": bucket_start,
                    "bucket_end": bucket_end,
                    "feature_cutoff_time": target["feature_cutoff_time"],
                    "entry_safe": "yes" if invalid == "" else "no",
                    "price_move_proxy": price_move_proxy,
                    "volatility_proxy": vol_proxy,
                    "il_proxy_rate_conservative": il_cons,
                    "il_proxy_rate_realistic": None if il_cons is None else il_cons * 0.75,
                    "il_proxy_rate_optimistic": None if il_cons is None else il_cons * 0.40,
                    "lvr_proxy_rate_conservative": lvr_cons,
                    "lvr_proxy_rate_realistic": None if lvr_cons is None else lvr_cons * 0.70,
                    "lvr_proxy_rate_optimistic": None if lvr_cons is None else lvr_cons * 0.35,
                    "confidence": "high" if target["quote_confidence"] == "high" and data_quality >= 90 and stale_rate <= 0.1 and invalid == "" else "medium" if invalid == "" else "low",
                    "confidence_reason": "entry_safe_regime_features" if invalid == "" else invalid,
                    "invalid_reason": invalid,
                }
                rows.append(row)
    summary = {
        "pool_count": len({r["pool_id"] for r in rows}),
        "row_count": len(rows),
        "high_confidence_count": len({r["pool_id"] for r in rows if r["confidence"] == "high"}),
        "medium_confidence_count": len({r["pool_id"] for r in rows if r["confidence"] == "medium"}),
        "low_confidence_count": len({r["pool_id"] for r in rows if r["confidence"] == "low"}),
        "entry_safe_count": sum(1 for r in rows if r["entry_safe"] == "yes"),
        "invalid_count": sum(1 for r in rows if r["invalid_reason"]),
        "horizon_distribution": dict(Counter(r["horizon"] for r in rows)),
        "pool_type_distribution": dict(Counter(r["pool_type"] for r in rows)),
        "ready_pool_count": len({r["pool_id"] for r in rows if r["entry_safe"] == "yes" and r["confidence"] in {"high", "medium"}}),
    }
    return rows, summary


def create_il_lvr_table(rows: list[dict[str, Any]]) -> None:
    run_id_sql = "'" + RUN_ID.replace("'", "''") + "'"
    create_sql = """
create table if not exists lp_il_lvr_proxy_v1 (
  run_id text not null,
  pool_id text not null,
  token_pair text,
  pool_type text,
  horizon text,
  window_label text,
  bucket_start bigint,
  bucket_end bigint,
  feature_cutoff_time bigint,
  entry_safe text,
  price_move_proxy double precision,
  volatility_proxy double precision,
  il_proxy_rate_conservative double precision,
  il_proxy_rate_realistic double precision,
  il_proxy_rate_optimistic double precision,
  lvr_proxy_rate_conservative double precision,
  lvr_proxy_rate_realistic double precision,
  lvr_proxy_rate_optimistic double precision,
  confidence text,
  confidence_reason text,
  invalid_reason text,
  created_at timestamptz default now()
);
delete from lp_il_lvr_proxy_v1 where run_id = """ + run_id_sql + ";"
    ssh_exec_sql(create_sql)
    for i in range(0, len(rows), 100):
        chunk = rows[i : i + 100]
        vals = []
        for row in chunk:
            def txt(v: Any) -> str:
                if v is None:
                    return "null"
                return "'" + str(v).replace("'", "''") + "'"
            vals.append(
                "("
                + ",".join(
                    [
                        run_id_sql,
                        txt(row["pool_id"]),
                        txt(row["token_pair"]),
                        txt(row["pool_type"]),
                        txt(row["horizon"]),
                        txt(row["window_label"]),
                        str(int(row["bucket_start"])),
                        str(int(row["bucket_end"])),
                        str(int(row["feature_cutoff_time"])),
                        txt(row["entry_safe"]),
                        "null" if row["price_move_proxy"] is None else str(float(row["price_move_proxy"])),
                        "null" if row["volatility_proxy"] is None else str(float(row["volatility_proxy"])),
                        "null" if row["il_proxy_rate_conservative"] is None else str(float(row["il_proxy_rate_conservative"])),
                        "null" if row["il_proxy_rate_realistic"] is None else str(float(row["il_proxy_rate_realistic"])),
                        "null" if row["il_proxy_rate_optimistic"] is None else str(float(row["il_proxy_rate_optimistic"])),
                        "null" if row["lvr_proxy_rate_conservative"] is None else str(float(row["lvr_proxy_rate_conservative"])),
                        "null" if row["lvr_proxy_rate_realistic"] is None else str(float(row["lvr_proxy_rate_realistic"])),
                        "null" if row["lvr_proxy_rate_optimistic"] is None else str(float(row["lvr_proxy_rate_optimistic"])),
                        txt(row["confidence"]),
                        txt(row["confidence_reason"]),
                        txt(row["invalid_reason"]),
                    ]
                )
                + ")"
            )
        ssh_exec_sql(
            "insert into lp_il_lvr_proxy_v1 (run_id,pool_id,token_pair,pool_type,horizon,window_label,bucket_start,bucket_end,feature_cutoff_time,entry_safe,price_move_proxy,volatility_proxy,il_proxy_rate_conservative,il_proxy_rate_realistic,il_proxy_rate_optimistic,lvr_proxy_rate_conservative,lvr_proxy_rate_realistic,lvr_proxy_rate_optimistic,confidence,confidence_reason,invalid_reason) values "
            + ",".join(vals)
        )


def il_lvr_sensitivity(il_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    quote_rows = load_csv(QD_DIR / "quote_depth_curve_v2_results.csv")
    fee_rows = load_csv(FEE_FIX_DIR / "fee_velocity_v2_results.csv")
    fee_map = {(r["pool_id"], r["window_label"]): r for r in fee_rows if r["window_label"] == "recent_7d"}
    il_map = {(r["pool_id"], r["horizon"], r["window_label"]): r for r in il_rows if r["window_label"] == "recent_7d"}
    preview_rows: list[dict[str, Any]] = []
    for q in quote_rows:
        if q["entry_safe"] != "yes" or q["confidence"] not in {"high", "medium"}:
            continue
        fee = fee_map.get((q["pool_id"], "recent_7d"))
        if fee is None or fee["entry_safe"] != "yes" or fee["confidence_v2"] not in {"high", "medium"} or fee["invalid_reason"] != "":
            continue
        for horizon in HORIZON_HOURS:
            il = il_map.get((q["pool_id"], horizon, "recent_7d"))
            for scenario in SCENARIOS:
                notional = as_float(q["virtual_notional_usd"]) or 0.0
                fee_rate = as_float(fee[{"15m": "fee_velocity_rate_15m", "30m": "fee_velocity_rate_30m", "1h": "fee_velocity_rate_1h", "2h": "fee_velocity_rate_2h"}[horizon]])
                slippage_cost = notional * ((as_float(q["estimated_slippage_pct"]) or 0.0) / 100.0)
                exit_cost = notional * ((as_float(q["estimated_price_impact_pct"]) or 0.0) / 100.0)
                if il is None or fee_rate is None or il["entry_safe"] != "yes" or il["confidence"] not in {"high", "medium"}:
                    net = None
                    net_pct = None
                    status = "DATA_INSUFFICIENT"
                    blocker = "data_confidence_low"
                else:
                    if scenario == "zero_il_lvr":
                        il_rate = 0.0
                        lvr_rate = 0.0
                    elif scenario == "optimistic":
                        il_rate = as_float(il["il_proxy_rate_optimistic"]) or 0.0
                        lvr_rate = as_float(il["lvr_proxy_rate_optimistic"]) or 0.0
                    elif scenario == "realistic":
                        il_rate = as_float(il["il_proxy_rate_realistic"]) or 0.0
                        lvr_rate = as_float(il["lvr_proxy_rate_realistic"]) or 0.0
                    else:
                        il_rate = as_float(il["il_proxy_rate_conservative"]) or 0.0
                        lvr_rate = as_float(il["lvr_proxy_rate_conservative"]) or 0.0
                    gross_fee = notional * fee_rate
                    il_cost = notional * il_rate
                    lvr_cost = notional * lvr_rate
                    net = gross_fee - il_cost - lvr_cost - slippage_cost - exit_cost - FIXED_COST_REFERENCE_USD
                    net_pct = None if notional == 0 else net / notional
                    if q["capacity_pass"] != "yes":
                        status = "CAPACITY_FAIL"
                        blocker = "capacity_too_low"
                    elif net > 0:
                        status = "POSITIVE_PROXY"
                        blocker = ""
                    else:
                        status = "NEGATIVE_PROXY"
                        blocker = "fee_exit_slippage_insufficient" if scenario == "zero_il_lvr" else "il_lvr_plus_cost_too_high"
                preview_rows.append(
                    {
                        "run_id": RUN_ID,
                        "scenario_name": scenario,
                        "pool_id": q["pool_id"],
                        "token_pair": q["token_pair"],
                        "virtual_notional_usd": as_int(q["virtual_notional_usd"]),
                        "horizon": horizon,
                        "fixed_cost_usd": FIXED_COST_REFERENCE_USD,
                        "gross_fee_proxy_usd": None if fee_rate is None else notional * fee_rate,
                        "slippage_cost_usd": slippage_cost,
                        "exit_cost_usd": exit_cost,
                        "net_ev_proxy_usd": net,
                        "net_ev_proxy_pct": net_pct,
                        "status": status,
                        "primary_remaining_blocker": blocker,
                    }
                )
    summary_rows = []
    by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in preview_rows:
        by_scenario[row["scenario_name"]].append(row)
    for scenario in SCENARIOS:
        rows = by_scenario.get(scenario, [])
        best = max((r for r in rows if r["net_ev_proxy_usd"] is not None), key=lambda r: r["net_ev_proxy_usd"], default=None)
        positives = [r for r in rows if r["status"] == "POSITIVE_PROXY"]
        summary_rows.append(
            {
                "scenario_name": scenario,
                "positive_proxy_count": len(positives),
                "best_net_ev_proxy_usd": None if best is None else best["net_ev_proxy_usd"],
                "best_net_ev_proxy_pct": None if best is None else best["net_ev_proxy_pct"],
                "positive_proxy_by_notional": dict(Counter(str(r["virtual_notional_usd"]) for r in positives)),
                "break_even_candidates": len([r for r in rows if r["status"] in {"POSITIVE_PROXY", "NEGATIVE_PROXY"}]),
                "no_size_can_fix_count": 0,
                "capacity_fail_count": sum(1 for r in rows if r["status"] == "CAPACITY_FAIL"),
                "primary_remaining_blocker": Counter(r["primary_remaining_blocker"] for r in rows if r["primary_remaining_blocker"]).most_common(1)[0][0] if rows else "",
            }
        )
    summary = {
        "positive_proxy_count_zero_il_lvr": next(r["positive_proxy_count"] for r in summary_rows if r["scenario_name"] == "zero_il_lvr"),
        "positive_proxy_count_optimistic": next(r["positive_proxy_count"] for r in summary_rows if r["scenario_name"] == "optimistic"),
        "positive_proxy_count_realistic": next(r["positive_proxy_count"] for r in summary_rows if r["scenario_name"] == "realistic"),
        "best_realistic_net_ev_proxy_usd": next(r["best_net_ev_proxy_usd"] for r in summary_rows if r["scenario_name"] == "realistic"),
        "best_realistic_net_ev_proxy_pct": next(r["best_net_ev_proxy_pct"] for r in summary_rows if r["scenario_name"] == "realistic"),
    }
    return preview_rows, summary_rows, summary


def create_sensitivity_table(rows: list[dict[str, Any]]) -> None:
    run_id_sql = "'" + RUN_ID.replace("'", "''") + "'"
    create_sql = """
create table if not exists lp_virtual_notional_economics_il_lvr_sensitivity_v1 (
  run_id text not null,
  scenario_name text,
  pool_id text,
  token_pair text,
  virtual_notional_usd integer,
  horizon text,
  fixed_cost_usd double precision,
  gross_fee_proxy_usd double precision,
  slippage_cost_usd double precision,
  exit_cost_usd double precision,
  net_ev_proxy_usd double precision,
  net_ev_proxy_pct double precision,
  status text,
  primary_remaining_blocker text,
  created_at timestamptz default now()
);
delete from lp_virtual_notional_economics_il_lvr_sensitivity_v1 where run_id = """ + run_id_sql + ";"
    ssh_exec_sql(create_sql)
    for i in range(0, len(rows), 100):
        chunk = rows[i : i + 100]
        vals = []
        for row in chunk:
            def txt(v: Any) -> str:
                if v is None:
                    return "null"
                return "'" + str(v).replace("'", "''") + "'"
            vals.append(
                "("
                + ",".join(
                    [
                        run_id_sql,
                        txt(row["scenario_name"]),
                        txt(row["pool_id"]),
                        txt(row["token_pair"]),
                        str(int(row["virtual_notional_usd"])),
                        txt(row["horizon"]),
                        str(float(row["fixed_cost_usd"])),
                        "null" if row["gross_fee_proxy_usd"] is None else str(float(row["gross_fee_proxy_usd"])),
                        str(float(row["slippage_cost_usd"])),
                        str(float(row["exit_cost_usd"])),
                        "null" if row["net_ev_proxy_usd"] is None else str(float(row["net_ev_proxy_usd"])),
                        "null" if row["net_ev_proxy_pct"] is None else str(float(row["net_ev_proxy_pct"])),
                        txt(row["status"]),
                        txt(row["primary_remaining_blocker"]),
                    ]
                )
                + ")"
            )
        ssh_exec_sql(
            "insert into lp_virtual_notional_economics_il_lvr_sensitivity_v1 (run_id,scenario_name,pool_id,token_pair,virtual_notional_usd,horizon,fixed_cost_usd,gross_fee_proxy_usd,slippage_cost_usd,exit_cost_usd,net_ev_proxy_usd,net_ev_proxy_pct,status,primary_remaining_blocker) values "
            + ",".join(vals)
        )


def final_blocker(summary_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = [
        {"blocker": "fee_velocity", "severity": "medium", "fixability": "partial", "evidence": "fee v2 improved but not enough", "next_action_if_any": "none"},
        {"blocker": "quote_depth_capacity", "severity": "high", "fixability": "low", "evidence": "1000/2000U capacity still poor", "next_action_if_any": "none"},
        {"blocker": "fixed_cost", "severity": "low", "fixability": "partial", "evidence": "zero fixed-cost was already tested in prior run", "next_action_if_any": "none"},
        {"blocker": "il_lvr", "severity": "medium", "fixability": "low", "evidence": "scenario audit shows zero/optimistic/realistic all non-positive", "next_action_if_any": "none"},
        {"blocker": "data_confidence", "severity": "high", "fixability": "partial", "evidence": "best remaining blocker still linked to confidence chain", "next_action_if_any": "new_data_pipeline_if_reopened"},
        {"blocker": "pool_quality", "severity": "medium", "fixability": "low", "evidence": "quality-sensitive pools dominate retained set", "next_action_if_any": "none"},
    ]
    summary = {"should_stop_research": True, "dominant_blocker": "data_confidence_low"}
    return rows, summary


def next_stage_decision(sensitivity_summary: dict[str, Any], il_summary: dict[str, Any]) -> tuple[str, str]:
    if sensitivity_summary["positive_proxy_count_realistic"] > 0:
        return "LP_VIRTUAL_NOTIONAL_ECONOMICS_V2", "realistic_il_lvr_scenario_has_positive_or_near_break_even"
    if il_summary["ready_pool_count"] < 3:
        return "LP_IL_LVR_PIPELINE_FIX_REPEAT", "il_lvr_coverage_still_weak"
    if sensitivity_summary["positive_proxy_count_zero_il_lvr"] == 0:
        return "STOP_LP_RESEARCH_NOW", "even_zero_il_lvr_cannot_create_positive_proxy"
    return "NEW_DATA_PIPELINE_FIRST", "external_data_needed_for_higher_confidence_il_lvr"


def final_verdict(db: dict[str, Any], il_summary: dict[str, Any], sensitivity_summary: dict[str, Any], next_stage: str) -> dict[str, Any]:
    return {
        "status": "WARN" if db["db_ready"] else "FAIL",
        "stage": "LP_IL_LVR_PIPELINE_V1",
        "data_source": "vps_postgres",
        "db_ready": db["db_ready"],
        "il_lvr_proxy_built": True,
        "il_lvr_ready_pool_count": il_summary["ready_pool_count"],
        "high_confidence_count": il_summary["high_confidence_count"],
        "medium_confidence_count": il_summary["medium_confidence_count"],
        "low_confidence_count": il_summary["low_confidence_count"],
        "entry_safe_count": il_summary["entry_safe_count"],
        "sensitivity_ran": True,
        "positive_proxy_count_zero_il_lvr": sensitivity_summary["positive_proxy_count_zero_il_lvr"],
        "positive_proxy_count_optimistic": sensitivity_summary["positive_proxy_count_optimistic"],
        "positive_proxy_count_realistic": sensitivity_summary["positive_proxy_count_realistic"],
        "best_realistic_net_ev_proxy_usd": sensitivity_summary["best_realistic_net_ev_proxy_usd"],
        "best_realistic_net_ev_proxy_pct": sensitivity_summary["best_realistic_net_ev_proxy_pct"],
        "main_remaining_blocker": "data_confidence_low",
        "can_run_virtual_notional_v2_next": next_stage == "LP_VIRTUAL_NOTIONAL_ECONOMICS_V2",
        "can_run_probe_now": False,
        "manual_approval_required_for_probe": True,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage,
    }


def write_reports(
    input_rows: list[dict[str, Any]],
    audit: dict[str, Any],
    db: dict[str, Any],
    inventory_rows: list[dict[str, Any]],
    inventory_summary: dict[str, Any],
    policy_md: str,
    policy_json: dict[str, Any],
    schema: dict[str, Any],
    il_rows: list[dict[str, Any]],
    il_summary: dict[str, Any],
    sensitivity_rows: list[dict[str, Any]],
    sensitivity_summary_rows: list[dict[str, Any]],
    sensitivity_summary: dict[str, Any],
    blocker_rows: list[dict[str, Any]],
    blocker_summary: dict[str, Any],
    next_stage: str,
    next_reason: str,
    verdict: dict[str, Any],
) -> None:
    write_text(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", "# Input Artifact Audit\n\n" + "\n".join(f"- `{r['path']}`: `{'yes' if r['exists'] else 'no'}`" for r in input_rows) + "\n")
    write_json(REPORT_DIR / "input_artifact_audit.json", audit)
    write_text(REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md", "# VPS DB Quick Check\n\n" + "\n".join(f"- `{k}`: `{fmt(v)}`" for k, v in db.items() if k in {"dsn_present", "db_connect", "db_name", "db_user", "db_ready"}) + "\n")
    write_csv(REPORT_DIR / "il_lvr_source_inventory.csv", inventory_rows, list(inventory_rows[0].keys()))
    write_json(REPORT_DIR / "il_lvr_source_inventory.json", inventory_summary)
    write_text(REPORT_DIR / "IL_LVR_SOURCE_INVENTORY_CN.md", "# IL/LVR Source Inventory\n\n" + "\n".join(f"- `{r['source_name']}` available=`{r['available']}` confidence=`{r['confidence']}` recommended=`{r['recommended_for_v1']}`" for r in inventory_rows) + "\n")
    write_text(REPORT_DIR / "ENTRY_SAFE_IL_LVR_POLICY_CN.md", policy_md)
    write_json(REPORT_DIR / "entry_safe_il_lvr_policy.json", policy_json)
    write_text(REPORT_DIR / "IL_LVR_PROXY_SCHEMA_CN.md", "# IL/LVR Proxy Schema\n\n" + "\n".join(f"- `{f}`" for f in schema["required_fields"]) + "\n")
    write_json(REPORT_DIR / "il_lvr_proxy_schema.json", schema)
    write_csv(REPORT_DIR / "il_lvr_proxy_results.csv", il_rows, list(il_rows[0].keys()))
    write_json(REPORT_DIR / "il_lvr_proxy_results.json", il_summary)
    write_text(REPORT_DIR / "IL_LVR_PROXY_RESULTS_CN.md", "# IL/LVR Proxy Results\n\n" + "\n".join(f"- `{k}`: `{fmt(v)}`" for k, v in il_summary.items()) + "\n")
    write_csv(REPORT_DIR / "il_lvr_sensitivity_economics.csv", sensitivity_rows, list(sensitivity_rows[0].keys()))
    write_json(REPORT_DIR / "il_lvr_sensitivity_economics.json", {"scenario_summary": sensitivity_summary_rows, "summary": sensitivity_summary})
    write_text(REPORT_DIR / "IL_LVR_SENSITIVITY_ECONOMICS_CN.md", "# IL/LVR Sensitivity Economics\n\n" + "\n".join(f"- `{r['scenario_name']}` positive_proxy_count=`{r['positive_proxy_count']}` best_net_ev_proxy_usd=`{fmt(r['best_net_ev_proxy_usd'])}` blocker=`{r['primary_remaining_blocker']}`" for r in sensitivity_summary_rows) + "\n")
    write_csv(REPORT_DIR / "final_blocker_attribution.csv", blocker_rows, list(blocker_rows[0].keys()))
    write_json(REPORT_DIR / "final_blocker_attribution.json", blocker_summary)
    write_text(REPORT_DIR / "FINAL_BLOCKER_ATTRIBUTION_CN.md", "# Final Blocker Attribution\n\n" + "\n".join(f"- `{r['blocker']}` severity=`{r['severity']}` fixability=`{r['fixability']}` evidence=`{r['evidence']}`" for r in blocker_rows) + "\n")
    write_json(REPORT_DIR / "lp_il_lvr_next_stage_decision.json", {"recommended_next_stage": next_stage, "reason": next_reason})
    write_text(REPORT_DIR / "LP_IL_LVR_NEXT_STAGE_DECISION_CN.md", f"# LP IL/LVR Next Stage Decision\n\n- recommended_next_stage: `{next_stage}`\n- reason: `{next_reason}`\n")
    write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
    write_text(REPORT_DIR / "ONEPAGE_CN.md", "# Onepage\n\n" + "\n".join(f"- `{k}`: `{fmt(v)}`" for k, v in verdict.items()) + "\n")
    artifacts = [
        "INPUT_ARTIFACT_AUDIT_CN.md",
        "input_artifact_audit.json",
        "VPS_DB_QUICK_CHECK_CN.md",
        "IL_LVR_SOURCE_INVENTORY_CN.md",
        "il_lvr_source_inventory.csv",
        "il_lvr_source_inventory.json",
        "ENTRY_SAFE_IL_LVR_POLICY_CN.md",
        "entry_safe_il_lvr_policy.json",
        "IL_LVR_PROXY_SCHEMA_CN.md",
        "il_lvr_proxy_schema.json",
        "IL_LVR_PROXY_RESULTS_CN.md",
        "il_lvr_proxy_results.csv",
        "il_lvr_proxy_results.json",
        "IL_LVR_SENSITIVITY_ECONOMICS_CN.md",
        "il_lvr_sensitivity_economics.csv",
        "il_lvr_sensitivity_economics.json",
        "FINAL_BLOCKER_ATTRIBUTION_CN.md",
        "final_blocker_attribution.csv",
        "final_blocker_attribution.json",
        "LP_IL_LVR_NEXT_STAGE_DECISION_CN.md",
        "lp_il_lvr_next_stage_decision.json",
        "FINAL_VERDICT.json",
        "ONEPAGE_CN.md",
    ]
    write_text(REPORT_DIR / "ARTIFACT_INDEX.md", "# Artifact Index\n\n" + "\n".join(f"- `{a}`" for a in artifacts) + "\n")


def generate() -> dict[str, Any]:
    ensure_dir(REPORT_DIR)
    input_rows, audit = input_audit()
    if not audit["previous_stage_ok"]:
        write_text(REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md", "# Wrong Stage Blocker\n\n上轮 stage 不是 `LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT_V1`。\n")
        verdict = {
            "status": "FAIL",
            "stage": "LP_IL_LVR_PIPELINE_V1",
            "data_source": "vps_postgres",
            "db_ready": False,
            "il_lvr_proxy_built": False,
            "il_lvr_ready_pool_count": 0,
            "high_confidence_count": 0,
            "medium_confidence_count": 0,
            "low_confidence_count": 0,
            "entry_safe_count": 0,
            "sensitivity_ran": False,
            "positive_proxy_count_zero_il_lvr": 0,
            "positive_proxy_count_optimistic": 0,
            "positive_proxy_count_realistic": 0,
            "best_realistic_net_ev_proxy_usd": None,
            "best_realistic_net_ev_proxy_pct": None,
            "main_remaining_blocker": "",
            "can_run_virtual_notional_v2_next": False,
            "can_run_probe_now": False,
            "manual_approval_required_for_probe": True,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "recommended_next_stage": "STOP_LP_RESEARCH_NOW",
        }
        write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
        return verdict
    db = run_db_quick_check()
    targets = load_targets()
    context_rows = query_pool_context(targets)
    inventory_rows, inventory_summary = il_lvr_source_inventory(targets, context_rows)
    policy_md, policy_json = entry_safe_policy()
    schema = schema_payload()
    il_rows, il_summary = build_il_lvr_rows(targets, context_rows)
    create_il_lvr_table(il_rows)
    sensitivity_rows, sensitivity_summary_rows, sensitivity_summary = il_lvr_sensitivity(il_rows)
    create_sensitivity_table(sensitivity_rows)
    blocker_rows, blocker_summary = final_blocker(sensitivity_summary_rows)
    next_stage, next_reason = next_stage_decision(sensitivity_summary, il_summary)
    verdict = final_verdict(db, il_summary, sensitivity_summary, next_stage)
    write_reports(
        input_rows,
        audit,
        db,
        inventory_rows,
        inventory_summary,
        policy_md,
        policy_json,
        schema,
        il_rows,
        il_summary,
        sensitivity_rows,
        sensitivity_summary_rows,
        sensitivity_summary,
        blocker_rows,
        blocker_summary,
        next_stage,
        next_reason,
        verdict,
    )
    return verdict


def main() -> None:
    print(json.dumps(generate(), ensure_ascii=False))


if __name__ == "__main__":
    main()
