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


RUN_ID = os.environ.get("RUN_ID_OVERRIDE", "20260601_103248")
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/Users/bendu/lp-bot/v3"))
REPORT_DIR = Path(
    os.environ.get(
        "REPORT_DIR_OVERRIDE",
        str(REPO_ROOT / "reports" / "lp_fee_velocity_fix_repeat" / RUN_ID),
    )
)
WORKSPACE = "/opt/lpbot/lp-bot-v3-origin-check"
FEE_V1_DIR = REPO_ROOT / "reports" / "lp_fee_velocity_pipeline" / "20260601_100642"
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
HORIZON_RATE_KEY = {
    "15m": "fee_velocity_rate_15m",
    "30m": "fee_velocity_rate_30m",
    "1h": "fee_velocity_rate_1h",
    "2h": "fee_velocity_rate_2h",
}
FIXED_COST_SCENARIOS = [0.0, 0.02, 0.05, 0.10, 0.20, 0.50]
ALLOWED_NEXT = {
    "LP_VIRTUAL_NOTIONAL_ECONOMICS_V2",
    "LP_FIXED_COST_MODEL_REVIEW_V1",
    "LP_IL_LVR_PIPELINE_V1",
    "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}
ENTRY_SAFE_RULES = {
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
        FEE_V1_DIR / "FINAL_VERDICT.json",
        FEE_V1_DIR / "FEE_SOURCE_INVENTORY_CN.md",
        FEE_V1_DIR / "fee_source_inventory.csv",
        FEE_V1_DIR / "ENTRY_SAFE_FEE_VELOCITY_POLICY_CN.md",
        FEE_V1_DIR / "FEE_VELOCITY_RESULTS_CN.md",
        FEE_V1_DIR / "fee_velocity_results.csv",
        FEE_V1_DIR / "FEE_VELOCITY_QUALITY_GATE_CN.md",
        FEE_V1_DIR / "fee_velocity_quality_gate.json",
        FEE_V1_DIR / "VIRTUAL_ECONOMICS_FEE_V1_PREVIEW_CN.md",
        FEE_V1_DIR / "virtual_economics_fee_v1_preview.csv",
        FEE_V1_DIR / "FEE_BLOCKER_DIAGNOSIS_CN.md",
        FEE_V1_DIR / "fee_blocker_diagnosis.csv",
        FEE_V1_DIR / "LP_FEE_VELOCITY_NEXT_STAGE_DECISION_CN.md",
        FEE_V1_DIR / "lp_fee_velocity_next_stage_decision.json",
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
    prior = load_json(FEE_V1_DIR / "FINAL_VERDICT.json")
    audit = {
        "missing_input_list": missing,
        "all_inputs_ready": len(missing) == 0,
        "previous_stage": prior.get("stage"),
        "previous_stage_ok": prior.get("stage") == "LP_FEE_VELOCITY_PIPELINE_V1",
        "fee_velocity_pipeline_built": prior.get("fee_velocity_pipeline_built") is True,
        "fee_ready_pool_count_is_1": prior.get("fee_ready_pool_count") == 1,
        "new_positive_proxy_count_is_0": prior.get("new_positive_proxy_count") == 0,
        "main_remaining_blocker_fixed_cost_now_main": prior.get("main_remaining_blocker") == "fixed_cost_now_main",
        "recommended_next_stage_ok": prior.get("recommended_next_stage") == "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT",
        "enough_to_execute_repeat": len(missing) == 0
        and prior.get("stage") == "LP_FEE_VELOCITY_PIPELINE_V1"
        and prior.get("recommended_next_stage") == "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT",
    }
    return rows, audit


def load_targets() -> list[dict[str, Any]]:
    quote_rows = load_csv(QD_DIR / "quote_depth_curve_v2_results.csv")
    by_pool: dict[str, dict[str, Any]] = {}
    for row in quote_rows:
        if row["virtual_notional_usd"] != "20":
            continue
        current = by_pool.get(row["pool_id"])
        score = {"high": 2, "medium": 1, "low": 0}.get(row["confidence"], -1)
        if current is None or score > current["_score"]:
            by_pool[row["pool_id"]] = {
                "pool_id": row["pool_id"],
                "token_pair": row["token_pair"],
                "inferred_tier": row["inferred_tier"],
                "chain": row["chain"],
                "pool_type": row["pool_type"],
                "quote_confidence": row["confidence"],
                "feature_cutoff_time": as_int(row["feature_cutoff_time"]),
                "entry_safe": row["entry_safe"],
                "_score": score,
            }
    return list(by_pool.values())


def fetch_pool_context(targets: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]], list[dict[str, str]]]:
    values = ",".join(
        "('{}', {})".format(t["pool_id"].replace("'", "''"), t["feature_cutoff_time"]) for t in targets
    )
    pool_ids = ",".join("'{}'".format(t["pool_id"].replace("'", "''")) for t in targets)
    pool_rows = ssh_query_rows(
        f"""
select
  p.pool_id,
  p.chain,
  p.protocol,
  p.fee_bps,
  p.tier,
  p.tvl_usd,
  p.vol_24h,
  p.fee_apr_24h
from pools p
where p.pool_id in ({pool_ids})
order by p.pool_id
"""
    )
    mark_rows = ssh_query_rows(
        f"""
with cutoff(pool_id, cutoff_epoch) as (
  values {values}
)
select
  spm.pool_id,
  spm.mark_time,
  spm.current_vol24h_usd,
  spm.current_tvl_usd,
  spm.fee_usd
from shadow_position_marks spm
join cutoff c on c.pool_id = spm.pool_id
where spm.mark_time <= c.cutoff_epoch
order by spm.pool_id, spm.mark_time desc
"""
    )
    score_rows = ssh_query_rows(
        f"""
with cutoff(pool_id, cutoff_epoch) as (
  values {values}
)
select
  psh.pool_id,
  psh.block_time as block_time_epoch,
  psh.score_json::jsonb ->> 'FeeAPRScore' as fee_apr_score,
  psh.score_json::jsonb ->> 'VolScore' as vol_score
from pool_score_history psh
join cutoff c on c.pool_id = psh.pool_id
where psh.block_time <= c.cutoff_epoch
order by psh.pool_id, psh.block_time desc
"""
    )
    return {r["pool_id"]: r for r in pool_rows}, mark_rows, score_rows


def fee_gap_diag(
    targets: list[dict[str, Any]],
    v1_rows: list[dict[str, str]],
    pool_meta: dict[str, dict[str, Any]],
    mark_rows: list[dict[str, str]],
    score_rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    v1_by_pool = {}
    for row in v1_rows:
        if row["window_label"] == "recent_7d":
            v1_by_pool[row["pool_id"]] = row
    marks_by_pool: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in mark_rows:
        marks_by_pool[row["pool_id"]].append(row)
    scores_by_pool: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in score_rows:
        scores_by_pool[row["pool_id"]].append(row)
    rows = []
    for target in targets:
        pool_id = target["pool_id"]
        meta = pool_meta.get(pool_id, {})
        current = v1_by_pool.get(pool_id, {})
        marks = marks_by_pool.get(pool_id, [])
        scores = scores_by_pool.get(pool_id, [])
        has_fee_tier = as_float(meta.get("fee_bps")) is not None or meta.get("tier") not in (None, "")
        has_volume_proxy = any(as_float(r.get("current_vol24h_usd")) is not None and as_float(r.get("current_tvl_usd")) is not None for r in marks)
        has_swap_log_proxy = False
        has_entry_safe_timestamp = bool(marks or scores)
        recommended = "mark_volume_x_fee_tier_proxy" if has_fee_tier and has_volume_proxy else ("pool_score_history_fee_apr_score" if scores else "diagnostic_only_snapshot")
        blocker_bits = []
        if not has_fee_tier:
            blocker_bits.append("missing_fee_tier")
        if not has_volume_proxy:
            blocker_bits.append("missing_mark_volume")
        if not scores:
            blocker_bits.append("missing_score_history")
        if not has_entry_safe_timestamp:
            blocker_bits.append("missing_entry_safe_timestamp")
        rows.append(
            {
                "pool_id": pool_id,
                "token_pair": target["token_pair"],
                "current_fee_source": current.get("fee_source", ""),
                "current_confidence": current.get("confidence", ""),
                "has_fee_tier": "yes" if has_fee_tier else "no",
                "has_volume_proxy": "yes" if has_volume_proxy else "no",
                "has_swap_log_proxy": "yes" if has_swap_log_proxy else "no",
                "has_entry_safe_timestamp": "yes" if has_entry_safe_timestamp else "no",
                "can_upgrade_confidence": "yes" if (current.get("confidence") == "low" and has_fee_tier and (has_volume_proxy or len(scores) >= 5)) else "no",
                "recommended_fee_source": recommended,
                "blocker": ",".join(blocker_bits) if blocker_bits else "",
            }
        )
    summary = {
        "pool_count": len(rows),
        "upgradeable_pool_count": sum(1 for r in rows if r["can_upgrade_confidence"] == "yes"),
        "missing_fee_tier_count": sum(1 for r in rows if r["has_fee_tier"] == "no"),
        "missing_volume_proxy_count": sum(1 for r in rows if r["has_volume_proxy"] == "no"),
        "missing_timestamp_safe_count": sum(1 for r in rows if r["has_entry_safe_timestamp"] == "no"),
        "diagnostic_only_count": sum(1 for r in rows if r["recommended_fee_source"] == "diagnostic_only_snapshot"),
        "score_history_reliability": "medium_if_history_dense_else_low",
    }
    return rows, summary


def fixed_cost_model_audit(targets: list[dict[str, Any]], econ_rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    unique_fixed = sorted({as_float(r["fixed_cost_usd"]) for r in econ_rows if as_float(r["fixed_cost_usd"]) is not None})
    components = [
        {
            "fixed_cost_component": "gas_proxy",
            "current_value_usd": 0.08,
            "source": "lp_virtual_notional_economics_v1.base_chain_gas_proxy",
            "confidence": "medium",
            "applies_to_virtual": "yes",
            "applies_to_probe": "no",
            "maybe_overconservative": "yes",
            "recommended_range_low": 0.00,
            "recommended_range_mid": 0.02,
            "recommended_range_high": 0.08,
        },
        {
            "fixed_cost_component": "fixed_routing_cost_concentrated",
            "current_value_usd": 0.02,
            "source": "lp_virtual_notional_economics_v1.pool_type_extra",
            "confidence": "low",
            "applies_to_virtual": "yes",
            "applies_to_probe": "no",
            "maybe_overconservative": "yes",
            "recommended_range_low": 0.00,
            "recommended_range_mid": 0.02,
            "recommended_range_high": 0.05,
        },
        {
            "fixed_cost_component": "fixed_routing_cost_non_cl",
            "current_value_usd": 0.01,
            "source": "lp_virtual_notional_economics_v1.pool_type_extra",
            "confidence": "low",
            "applies_to_virtual": "yes",
            "applies_to_probe": "no",
            "maybe_overconservative": "yes",
            "recommended_range_low": 0.00,
            "recommended_range_mid": 0.01,
            "recommended_range_high": 0.03,
        },
        {
            "fixed_cost_component": "operational_cost",
            "current_value_usd": 0.0,
            "source": "not_separately_modeled_in_v1",
            "confidence": "low",
            "applies_to_virtual": "no",
            "applies_to_probe": "no",
            "maybe_overconservative": "no",
            "recommended_range_low": 0.0,
            "recommended_range_mid": 0.0,
            "recommended_range_high": 0.0,
        },
        {
            "fixed_cost_component": "probe_execution_fixed_cost",
            "current_value_usd": 0.0,
            "source": "out_of_scope_this_stage",
            "confidence": "low",
            "applies_to_virtual": "no",
            "applies_to_probe": "yes",
            "maybe_overconservative": "no",
            "recommended_range_low": 0.02,
            "recommended_range_mid": 0.05,
            "recommended_range_high": 0.20,
        },
        {
            "fixed_cost_component": "live_trading_fixed_cost",
            "current_value_usd": 0.0,
            "source": "forbidden_this_stage",
            "confidence": "none",
            "applies_to_virtual": "no",
            "applies_to_probe": "no",
            "maybe_overconservative": "no",
            "recommended_range_low": 0.0,
            "recommended_range_mid": 0.0,
            "recommended_range_high": 0.0,
        },
    ]
    per_pool = []
    seen = set()
    for row in econ_rows:
        pid = row["pool_id"]
        if pid in seen or row["virtual_notional_usd"] != "20" or row["horizon"] != "2h":
            continue
        seen.add(pid)
        fixed = as_float(row["fixed_cost_usd"]) or 0.0
        var = as_float(row["variable_edge_rate"]) or 0.0
        per_pool.append(
            {
                "pool_id": pid,
                "token_pair": row["token_pair"],
                "fixed_cost_usd": fixed,
                "fixed_cost_pct_at_20": fixed / 20.0,
                "fixed_cost_pct_at_100": fixed / 100.0,
                "fixed_cost_pct_at_500": fixed / 500.0,
                "variable_edge_rate": var,
                "still_negative_at_100_if_no_fixed": "yes" if var <= 0 else "no",
                "still_negative_at_500_if_no_fixed": "yes" if var <= 0 else "no",
            }
        )
    summary = {
        "current_fixed_cost_values": unique_fixed,
        "fixed_cost_now_main_is_plausible": True,
        "fixed_cost_maybe_overconservative": True,
        "twenty_u_fixed_cost_pct_is_high": True,
        "hundred_five_hundred_should_dilute_fixed_cost": True,
        "if_100_500_still_negative_variable_edge_insufficient": True,
    }
    return components, summary, per_pool


def compute_fee_v2(
    targets: list[dict[str, Any]],
    v1_rows: list[dict[str, str]],
    pool_meta: dict[str, dict[str, Any]],
    mark_rows: list[dict[str, str]],
    score_rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    v1_recent = {r["pool_id"]: r for r in v1_rows if r["window_label"] == "recent_7d"}
    marks_by_pool: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in mark_rows:
        marks_by_pool[row["pool_id"]].append(row)
    scores_by_pool: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in score_rows:
        scores_by_pool[row["pool_id"]].append(row)
    rows: list[dict[str, Any]] = []
    for target in targets:
        pool_id = target["pool_id"]
        meta = pool_meta.get(pool_id, {})
        marks = marks_by_pool.get(pool_id, [])
        scores = scores_by_pool.get(pool_id, [])
        fee_bps = as_float(meta.get("fee_bps"))
        if fee_bps is None:
            fee_bps = as_float(meta.get("tier"))
        cutoff = target["feature_cutoff_time"]
        for window, seconds in WINDOWS.items():
            bucket_start = cutoff - seconds
            window_marks = [m for m in marks if as_int(m["mark_time"]) >= bucket_start]
            valid_marks = [
                m
                for m in window_marks
                if as_float(m.get("current_vol24h_usd")) is not None and as_float(m.get("current_tvl_usd")) not in (None, 0.0)
            ]
            source = ""
            confidence = "low"
            invalid_reason = ""
            volume_proxy = None
            gross_pool_fee = None
            fee_apr_proxy = None
            conf_reason = ""
            if fee_bps is not None and valid_marks:
                avg_vol = sum(as_float(m["current_vol24h_usd"]) or 0.0 for m in valid_marks) / len(valid_marks)
                avg_tvl = sum(as_float(m["current_tvl_usd"]) or 0.0 for m in valid_marks) / len(valid_marks)
                if avg_tvl > 0:
                    gross_pool_fee = avg_vol * fee_bps / 10000.0
                    daily_rate = gross_pool_fee / avg_tvl
                    fee_apr_proxy = daily_rate * 365.0
                    volume_proxy = avg_vol
                    source = "entry_safe_mark_volume_x_fee_tier_proxy"
                    if len(valid_marks) >= 12 and window in {"recent_72h", "recent_7d"}:
                        confidence = "high"
                        conf_reason = "dense_mark_volume_before_cutoff"
                    else:
                        confidence = "medium"
                        conf_reason = "sparse_but_valid_mark_volume_before_cutoff"
                else:
                    invalid_reason = "avg_tvl_zero"
            if source == "" and scores:
                dense_scores = [s for s in scores if as_float(s.get("fee_apr_score")) is not None]
                if dense_scores:
                    score = max(as_float(s["fee_apr_score"]) or 0.0 for s in dense_scores)
                    fee_apr_proxy = max(0.0, score / 100.0 * 0.35)
                    daily_rate = fee_apr_proxy / 365.0
                    source = "pool_score_history_fee_apr_score"
                    confidence = "medium" if len(dense_scores) >= 5 else "low"
                    conf_reason = "score_history_fee_aprscore_before_cutoff"
                else:
                    invalid_reason = "score_history_without_fee_apr"
            elif source == "" and as_float(meta.get("vol_24h")) is not None and as_float(meta.get("tvl_usd")) not in (None, 0.0) and fee_bps is not None:
                volume_proxy = as_float(meta.get("vol_24h"))
                gross_pool_fee = volume_proxy * fee_bps / 10000.0
                daily_rate = gross_pool_fee / (as_float(meta.get("tvl_usd")) or 1.0)
                fee_apr_proxy = daily_rate * 365.0
                source = "external_cached_volume_proxy_diagnostic"
                confidence = "low"
                conf_reason = "current_snapshot_not_entry_safe"
                invalid_reason = "not_entry_safe_current_snapshot"
            else:
                daily_rate = None
            if source == "":
                source = "missing_direct_fee_accrual"
                conf_reason = conf_reason or "no_entry_safe_fee_source"
                if not invalid_reason:
                    invalid_reason = "no_fee_source"
            entry_safe = "yes" if source != "external_cached_volume_proxy_diagnostic" and target["entry_safe"] == "yes" else "no"
            rows.append(
                {
                    "run_id": RUN_ID,
                    "pool_id": pool_id,
                    "token_pair": target["token_pair"],
                    "fee_source_v1": v1_recent.get(pool_id, {}).get("fee_source", ""),
                    "fee_source_v2": source,
                    "confidence_v1": v1_recent.get(pool_id, {}).get("confidence", ""),
                    "confidence_v2": confidence,
                    "window_label": window,
                    "fee_velocity_rate_15m": None if daily_rate is None else daily_rate * (0.25 / 24.0),
                    "fee_velocity_rate_30m": None if daily_rate is None else daily_rate * (0.50 / 24.0),
                    "fee_velocity_rate_1h": None if daily_rate is None else daily_rate * (1.0 / 24.0),
                    "fee_velocity_rate_2h": None if daily_rate is None else daily_rate * (2.0 / 24.0),
                    "fee_apr_proxy": fee_apr_proxy,
                    "entry_safe": entry_safe,
                    "invalid_reason": invalid_reason,
                    "confidence_reason": conf_reason,
                }
            )
    pool_upgrade = defaultdict(lambda: {"v1": "low", "v2": "low"})
    for row in rows:
        pid = row["pool_id"]
        if row["confidence_v1"] == "high":
            pool_upgrade[pid]["v1"] = "high"
        elif row["confidence_v1"] == "medium" and pool_upgrade[pid]["v1"] != "high":
            pool_upgrade[pid]["v1"] = "medium"
        if row["confidence_v2"] == "high":
            pool_upgrade[pid]["v2"] = "high"
        elif row["confidence_v2"] == "medium" and pool_upgrade[pid]["v2"] != "high":
            pool_upgrade[pid]["v2"] = "medium"
    ready_pools = []
    for pid in {r["pool_id"] for r in rows}:
        per = [r for r in rows if r["pool_id"] == pid]
        ok = all(r["entry_safe"] == "yes" and r["confidence_v2"] in {"high", "medium"} and r["invalid_reason"] == "" for r in per)
        if ok:
            ready_pools.append(pid)
    summary = {
        "pool_count": len({r["pool_id"] for r in rows}),
        "row_count": len(rows),
        "fee_ready_pool_count": len(ready_pools),
        "fee_ready_pool_ids": ready_pools,
        "high_confidence_count": len({r["pool_id"] for r in rows if r["confidence_v2"] == "high"}),
        "medium_confidence_count": len({r["pool_id"] for r in rows if r["confidence_v2"] == "medium"}),
        "low_confidence_count": len({r["pool_id"] for r in rows if r["confidence_v2"] == "low"}),
        "upgraded_pool_count": sum(1 for v in pool_upgrade.values() if {"low": 0, "medium": 1, "high": 2}[v["v2"]] > {"low": 0, "medium": 1, "high": 2}[v["v1"]]),
        "unchanged_pool_count": sum(1 for v in pool_upgrade.values() if v["v2"] == v["v1"]),
        "invalid_count": sum(1 for r in rows if r["invalid_reason"] != ""),
        "source_distribution": dict(Counter(r["fee_source_v2"] for r in rows)),
        "confidence_distribution": dict(Counter(r["confidence_v2"] for r in rows)),
    }
    return rows, summary


def create_fee_v2_table(rows: list[dict[str, Any]]) -> None:
    run_id_sql = "'" + RUN_ID.replace("'", "''") + "'"
    def sql_text(value: Any) -> str:
        if value is None:
            return "null"
        return "'" + str(value).replace("'", "''") + "'"
    create_sql = """
create table if not exists lp_fee_velocity_v2 (
  run_id text not null,
  pool_id text not null,
  token_pair text,
  fee_source_v1 text,
  fee_source_v2 text,
  confidence_v1 text,
  confidence_v2 text,
  window_label text,
  fee_velocity_rate_15m double precision,
  fee_velocity_rate_30m double precision,
  fee_velocity_rate_1h double precision,
  fee_velocity_rate_2h double precision,
  fee_apr_proxy double precision,
  entry_safe text,
  invalid_reason text,
  confidence_reason text,
  created_at timestamptz default now()
);
delete from lp_fee_velocity_v2 where run_id = """ + run_id_sql + ";"
    ssh_exec_sql(create_sql)
    chunks = [rows[i : i + 100] for i in range(0, len(rows), 100)]
    for chunk in chunks:
        values = []
        for row in chunk:
            values.append(
                "("
                + ",".join(
                    [
                        run_id_sql,
                        sql_text(row["pool_id"]),
                        sql_text(row["token_pair"]),
                        sql_text(row["fee_source_v1"]),
                        sql_text(row["fee_source_v2"]),
                        sql_text(row["confidence_v1"]),
                        sql_text(row["confidence_v2"]),
                        sql_text(row["window_label"]),
                        "null" if row["fee_velocity_rate_15m"] is None else str(float(row["fee_velocity_rate_15m"])),
                        "null" if row["fee_velocity_rate_30m"] is None else str(float(row["fee_velocity_rate_30m"])),
                        "null" if row["fee_velocity_rate_1h"] is None else str(float(row["fee_velocity_rate_1h"])),
                        "null" if row["fee_velocity_rate_2h"] is None else str(float(row["fee_velocity_rate_2h"])),
                        "null" if row["fee_apr_proxy"] is None else str(float(row["fee_apr_proxy"])),
                        sql_text(row["entry_safe"]),
                        sql_text(row["invalid_reason"]),
                        sql_text(row["confidence_reason"]),
                    ]
                )
                + ")"
            )
        ssh_exec_sql(
            "insert into lp_fee_velocity_v2 (run_id,pool_id,token_pair,fee_source_v1,fee_source_v2,confidence_v1,confidence_v2,window_label,fee_velocity_rate_15m,fee_velocity_rate_30m,fee_velocity_rate_1h,fee_velocity_rate_2h,fee_apr_proxy,entry_safe,invalid_reason,confidence_reason) values "
            + ",".join(values)
        )


def sensitivity_preview(
    econ_rows: list[dict[str, str]],
    fee_v2_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    fee_map = {(r["pool_id"], r["window_label"]): r for r in fee_v2_rows if r["window_label"] == "recent_7d"}
    preview_rows = []
    for row in econ_rows:
        fee = fee_map.get((row["pool_id"], "recent_7d"))
        rate = None if fee is None else as_float(fee[HORIZON_RATE_KEY[row["horizon"]]])
        old_net = as_float(row["net_ev_proxy_usd"]) or 0.0
        old_gross = as_float(row["gross_fee_proxy_usd"]) or 0.0
        old_fixed = as_float(row["fixed_cost_usd"]) or 0.0
        notional = as_float(row["virtual_notional_usd"]) or 0.0
        il_usd = as_float(row["il_lvr_proxy_usd"])
        slip_usd = as_float(row["slippage_cost_usd"])
        exit_usd = as_float(row["exit_cost_usd"])
        data_ready = (
            rate is not None
            and il_usd is not None
            and slip_usd is not None
            and exit_usd is not None
            and row.get("confidence") in {"high", "medium"}
            and (fee is None or fee["confidence_v2"] in {"high", "medium"})
            and row.get("capacity_pass") == "yes"
        )
        base_without_fee_and_fixed = old_net - old_gross + old_fixed
        new_gross = None if rate is None else notional * rate
        variable_edge_rate = None if rate is None or notional == 0 else (base_without_fee_and_fixed + new_gross) / notional
        for scenario in FIXED_COST_SCENARIOS:
            if not data_ready or new_gross is None:
                new_net = None
                status = "DATA_INSUFFICIENT"
            else:
                new_net = base_without_fee_and_fixed + new_gross - scenario
                if new_net > 0:
                    status = "POSITIVE_PROXY"
                elif (variable_edge_rate or -1.0) <= 0:
                    status = "NO_SIZE_CAN_FIX"
                elif scenario == 0:
                    status = "NEGATIVE_PROXY"
                else:
                    status = "FIXED_COST_NOW_MAIN"
            preview_rows.append(
                {
                    "run_id": RUN_ID,
                    "scenario_name": f"fixed_cost_{scenario:.2f}",
                    "fixed_cost_usd": scenario,
                    "pool_id": row["pool_id"],
                    "token_pair": row["token_pair"],
                    "virtual_notional_usd": as_int(row["virtual_notional_usd"]),
                    "horizon": row["horizon"],
                    "quote_depth_confidence": row["quote_depth_confidence"],
                    "fee_confidence_v2": "" if fee is None else fee["confidence_v2"],
                    "new_gross_fee_proxy_usd": new_gross,
                    "il_lvr_proxy_usd": il_usd,
                    "slippage_cost_usd": slip_usd,
                    "exit_cost_usd": exit_usd,
                    "old_fixed_cost_usd": old_fixed,
                    "new_fixed_cost_usd": scenario,
                    "new_net_ev_proxy_usd": new_net,
                    "new_net_ev_proxy_pct": None if new_net is None or notional == 0 else new_net / notional,
                    "variable_edge_rate": variable_edge_rate,
                    "status": status,
                    "primary_remaining_blocker": (
                        "data_confidence_low"
                        if status == "DATA_INSUFFICIENT"
                        else "fixed_cost_now_main"
                        if status == "FIXED_COST_NOW_MAIN"
                        else "variable_edge_insufficient"
                        if status == "NO_SIZE_CAN_FIX"
                        else row["primary_blocker"]
                    ),
                }
            )
    scenario_rows = []
    by_scenario: dict[float, list[dict[str, Any]]] = defaultdict(list)
    for row in preview_rows:
        by_scenario[row["fixed_cost_usd"]].append(row)
    for scenario, rows in sorted(by_scenario.items()):
        positive = [r for r in rows if r["status"] == "POSITIVE_PROXY"]
        best = max((r for r in rows if r["new_net_ev_proxy_usd"] is not None), key=lambda r: r["new_net_ev_proxy_usd"], default=None)
        scenario_rows.append(
            {
                "fixed_cost_usd": scenario,
                "positive_proxy_count": len(positive),
                "best_net_ev_proxy_usd": None if best is None else best["new_net_ev_proxy_usd"],
                "best_net_ev_proxy_pct": None if best is None else best["new_net_ev_proxy_pct"],
                "positive_proxy_by_notional": dict(Counter(str(r["virtual_notional_usd"]) for r in positive)),
                "break_even_candidates": len([r for r in rows if r["status"] in {"FIXED_COST_NOW_MAIN", "POSITIVE_PROXY"}]),
                "no_size_can_fix_count": sum(1 for r in rows if r["status"] == "NO_SIZE_CAN_FIX"),
                "capacity_fail_count": sum(1 for r in rows if r["status"] == "CAPACITY_FAIL"),
                "primary_remaining_blocker": Counter(r["primary_remaining_blocker"] for r in rows).most_common(1)[0][0],
            }
        )
    realistic = next(r for r in scenario_rows if abs(r["fixed_cost_usd"] - 0.05) < 1e-9)
    summary = {
        "positive_proxy_count_fixed_cost_0": next(r["positive_proxy_count"] for r in scenario_rows if abs(r["fixed_cost_usd"] - 0.0) < 1e-9),
        "positive_proxy_count_realistic": realistic["positive_proxy_count"],
        "best_realistic_net_ev_proxy_usd": realistic["best_net_ev_proxy_usd"],
        "best_realistic_net_ev_proxy_pct": realistic["best_net_ev_proxy_pct"],
    }
    return preview_rows, scenario_rows, summary


def create_sensitivity_table(rows: list[dict[str, Any]]) -> None:
    run_id_sql = "'" + RUN_ID.replace("'", "''") + "'"
    create_sql = """
create table if not exists lp_virtual_notional_economics_fee_v2_fixedcost_sensitivity (
  run_id text not null,
  scenario_name text,
  fixed_cost_usd double precision,
  pool_id text,
  token_pair text,
  virtual_notional_usd integer,
  horizon text,
  fee_confidence_v2 text,
  new_gross_fee_proxy_usd double precision,
  il_lvr_proxy_usd double precision,
  slippage_cost_usd double precision,
  exit_cost_usd double precision,
  new_net_ev_proxy_usd double precision,
  new_net_ev_proxy_pct double precision,
  variable_edge_rate double precision,
  status text,
  primary_remaining_blocker text,
  created_at timestamptz default now()
);
delete from lp_virtual_notional_economics_fee_v2_fixedcost_sensitivity where run_id = """ + run_id_sql + ";"
    ssh_exec_sql(create_sql)
    for chunk_start in range(0, len(rows), 100):
        chunk = rows[chunk_start : chunk_start + 100]
        values = []
        for row in chunk:
            def txt(v: Any) -> str:
                if v is None:
                    return "null"
                return "'" + str(v).replace("'", "''") + "'"
            values.append(
                "("
                + ",".join(
                    [
                        run_id_sql,
                        txt(row["scenario_name"]),
                        str(float(row["fixed_cost_usd"])),
                        txt(row["pool_id"]),
                        txt(row["token_pair"]),
                        str(int(row["virtual_notional_usd"])),
                        txt(row["horizon"]),
                        txt(row["fee_confidence_v2"]),
                        "null" if row["new_gross_fee_proxy_usd"] is None else str(float(row["new_gross_fee_proxy_usd"])),
                        "null" if row["il_lvr_proxy_usd"] is None else str(float(row["il_lvr_proxy_usd"])),
                        "null" if row["slippage_cost_usd"] is None else str(float(row["slippage_cost_usd"])),
                        "null" if row["exit_cost_usd"] is None else str(float(row["exit_cost_usd"])),
                        "null" if row["new_net_ev_proxy_usd"] is None else str(float(row["new_net_ev_proxy_usd"])),
                        "null" if row["new_net_ev_proxy_pct"] is None else str(float(row["new_net_ev_proxy_pct"])),
                        "null" if row["variable_edge_rate"] is None else str(float(row["variable_edge_rate"])),
                        txt(row["status"]),
                        txt(row["primary_remaining_blocker"]),
                    ]
                )
                + ")"
            )
        ssh_exec_sql(
            "insert into lp_virtual_notional_economics_fee_v2_fixedcost_sensitivity (run_id,scenario_name,fixed_cost_usd,pool_id,token_pair,virtual_notional_usd,horizon,fee_confidence_v2,new_gross_fee_proxy_usd,il_lvr_proxy_usd,slippage_cost_usd,exit_cost_usd,new_net_ev_proxy_usd,new_net_ev_proxy_pct,variable_edge_rate,status,primary_remaining_blocker) values "
            + ",".join(values)
        )


def scenario_comparison(sensitivity_rows: list[dict[str, Any]], v1_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows = []
    conservative_best = max((r for r in v1_rows if as_float(r["net_ev_proxy_usd"]) is not None), key=lambda r: as_float(r["net_ev_proxy_usd"]), default=None)
    rows.append(
        {
            "scenario_name": "conservative",
            "positive_proxy_count": sum(1 for r in v1_rows if r["ev_status"] == "POSITIVE_PROXY"),
            "best_pool": "" if conservative_best is None else conservative_best["pool_id"],
            "best_notional": None if conservative_best is None else as_int(conservative_best["virtual_notional_usd"]),
            "best_horizon": "" if conservative_best is None else conservative_best["horizon"],
            "best_net_ev_proxy_usd": None if conservative_best is None else as_float(conservative_best["net_ev_proxy_usd"]),
            "best_net_ev_proxy_pct": None if conservative_best is None else as_float(conservative_best["net_ev_proxy_pct"]),
            "break_even_notional": None if conservative_best is None else as_float(conservative_best["break_even_notional_usd"]),
            "confidence": "high",
            "can_support_probe_preflight": "no",
        }
    )
    for name, scenario_cost, confidence in [("realistic", 0.05, "medium"), ("optimistic_diagnostic", 0.02, "low")]:
        rows_s = [r for r in sensitivity_rows if abs(r["fixed_cost_usd"] - scenario_cost) < 1e-9]
        best = max((r for r in rows_s if r["new_net_ev_proxy_usd"] is not None), key=lambda r: r["new_net_ev_proxy_usd"], default=None)
        rows.append(
            {
                "scenario_name": name,
                "positive_proxy_count": sum(1 for r in rows_s if r["status"] == "POSITIVE_PROXY"),
                "best_pool": "" if best is None else best["pool_id"],
                "best_notional": None if best is None else best["virtual_notional_usd"],
                "best_horizon": "" if best is None else best["horizon"],
                "best_net_ev_proxy_usd": None if best is None else best["new_net_ev_proxy_usd"],
                "best_net_ev_proxy_pct": None if best is None else best["new_net_ev_proxy_pct"],
                "break_even_notional": None,
                "confidence": confidence,
                "can_support_probe_preflight": "no",
            }
        )
    return rows


def next_stage_decision(
    fee_v2_summary: dict[str, Any],
    sensitivity_summary: dict[str, Any],
    scenario_rows: list[dict[str, Any]],
    blocker_rows: list[dict[str, Any]],
) -> tuple[str, str]:
    realistic_positive = sensitivity_summary["positive_proxy_count_realistic"]
    zero_positive = sensitivity_summary["positive_proxy_count_fixed_cost_0"]
    main_blocker = Counter(r["primary_remaining_blocker"] for r in blocker_rows).most_common(1)[0][0] if blocker_rows else ""
    if fee_v2_summary["fee_ready_pool_count"] >= 3 and realistic_positive > 0:
        return "LP_VIRTUAL_NOTIONAL_ECONOMICS_V2", "fee_v2_materially_improves_realistic_proxy_ev"
    if zero_positive > 0 and realistic_positive == 0:
        return "LP_FIXED_COST_MODEL_REVIEW_V1", "conclusion_changes_under_low_fixed_cost_only"
    if fee_v2_summary["fee_ready_pool_count"] >= 3 and main_blocker in {"variable_edge_insufficient", "il_lvr_too_high", "fixed_cost_now_main"}:
        return "LP_IL_LVR_PIPELINE_V1", "fee_fixed_enough_non_fee_blocker_now_dominant"
    if fee_v2_summary["fee_ready_pool_count"] < 3:
        return "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT", "fee_coverage_still_too_weak"
    return "STOP_LP_RESEARCH_NOW", "even_low_fixed_cost_not_enough_for_realistic_positive_proxy"


def write_reports(
    input_rows: list[dict[str, Any]],
    audit: dict[str, Any],
    db: dict[str, Any],
    gap_rows: list[dict[str, Any]],
    gap_summary: dict[str, Any],
    fixed_components: list[dict[str, Any]],
    fixed_summary: dict[str, Any],
    fixed_pool_rows: list[dict[str, Any]],
    fee_v2_rows: list[dict[str, Any]],
    fee_v2_summary: dict[str, Any],
    sensitivity_rows: list[dict[str, Any]],
    sensitivity_summary_rows: list[dict[str, Any]],
    sensitivity_summary: dict[str, Any],
    scenario_rows: list[dict[str, Any]],
    next_stage: str,
    next_reason: str,
    verdict: dict[str, Any],
) -> None:
    write_text(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", "# Input Artifact Audit\n\n" + "\n".join(f"- `{r['path']}`: `{'yes' if r['exists'] else 'no'}`" for r in input_rows) + "\n")
    write_json(REPORT_DIR / "input_artifact_audit.json", audit)
    write_text(REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md", "# VPS DB Quick Check\n\n" + "\n".join(f"- `{k}`: `{fmt(v)}`" for k, v in db.items() if k in {"dsn_present", "db_connect", "db_name", "db_user", "db_ready"}) + "\n")
    write_csv(REPORT_DIR / "fee_coverage_gap_diagnosis.csv", gap_rows, list(gap_rows[0].keys()))
    write_text(
        REPORT_DIR / "FEE_COVERAGE_GAP_DIAGNOSIS_CN.md",
        "# Fee Coverage Gap Diagnosis\n\n"
        + f"- fee_ready_pool_count_v1: `1`\n"
        + f"- upgradeable_pool_count: `{gap_summary['upgradeable_pool_count']}`\n"
        + f"- missing_fee_tier_count: `{gap_summary['missing_fee_tier_count']}`\n"
        + f"- missing_volume_proxy_count: `{gap_summary['missing_volume_proxy_count']}`\n"
        + f"- missing_timestamp_safe_count: `{gap_summary['missing_timestamp_safe_count']}`\n"
        + f"- score_history_reliability: `{gap_summary['score_history_reliability']}`\n",
    )
    write_csv(REPORT_DIR / "fixed_cost_model_audit.csv", fixed_pool_rows, list(fixed_pool_rows[0].keys()))
    write_json(REPORT_DIR / "fixed_cost_model_audit.json", {"components": fixed_components, "summary": fixed_summary})
    write_text(
        REPORT_DIR / "FIXED_COST_MODEL_AUDIT_CN.md",
        "# Fixed Cost Model Audit\n\n"
        + "\n".join(
            f"- `{r['fixed_cost_component']}` current=`{fmt(r['current_value_usd'])}` virtual=`{r['applies_to_virtual']}` probe=`{r['applies_to_probe']}` maybe_overconservative=`{r['maybe_overconservative']}`"
            for r in fixed_components
        )
        + "\n\n"
        + f"- current_fixed_cost_values: `{fixed_summary['current_fixed_cost_values']}`\n"
        + f"- fixed_cost_maybe_overconservative: `{fmt(fixed_summary['fixed_cost_maybe_overconservative'])}`\n",
    )
    write_csv(REPORT_DIR / "fee_velocity_v2_results.csv", fee_v2_rows, list(fee_v2_rows[0].keys()))
    write_json(REPORT_DIR / "fee_velocity_v2_results.json", fee_v2_summary)
    write_text(
        REPORT_DIR / "FEE_VELOCITY_V2_RESULTS_CN.md",
        "# Fee Velocity V2 Results\n\n"
        + f"- pool_count: `{fee_v2_summary['pool_count']}`\n"
        + f"- row_count: `{fee_v2_summary['row_count']}`\n"
        + f"- fee_ready_pool_count: `{fee_v2_summary['fee_ready_pool_count']}`\n"
        + f"- high_confidence_count: `{fee_v2_summary['high_confidence_count']}`\n"
        + f"- medium_confidence_count: `{fee_v2_summary['medium_confidence_count']}`\n"
        + f"- low_confidence_count: `{fee_v2_summary['low_confidence_count']}`\n"
        + f"- upgraded_pool_count: `{fee_v2_summary['upgraded_pool_count']}`\n"
        + f"- source_distribution: `{fee_v2_summary['source_distribution']}`\n",
    )
    write_csv(REPORT_DIR / "fixed_cost_sensitivity_economics.csv", sensitivity_rows, list(sensitivity_rows[0].keys()))
    write_json(REPORT_DIR / "fixed_cost_sensitivity_economics.json", {"scenario_summary": sensitivity_summary_rows, "summary": sensitivity_summary})
    write_text(
        REPORT_DIR / "FIXED_COST_SENSITIVITY_ECONOMICS_CN.md",
        "# Fixed Cost Sensitivity Economics\n\n"
        + "\n".join(
            f"- fixed_cost=`{fmt(r['fixed_cost_usd'])}` positive_proxy_count=`{r['positive_proxy_count']}` best_net_ev_proxy_usd=`{fmt(r['best_net_ev_proxy_usd'])}` blocker=`{r['primary_remaining_blocker']}`"
            for r in sensitivity_summary_rows
        )
        + "\n",
    )
    write_csv(REPORT_DIR / "ev_scenario_comparison.csv", scenario_rows, list(scenario_rows[0].keys()))
    write_text(
        REPORT_DIR / "EV_SCENARIO_COMPARISON_CN.md",
        "# EV Scenario Comparison\n\n"
        + "\n".join(
            f"- `{r['scenario_name']}` positive_proxy_count=`{r['positive_proxy_count']}` best_pool=`{r['best_pool']}` best_net_ev_proxy_usd=`{fmt(r['best_net_ev_proxy_usd'])}` can_support_probe_preflight=`{r['can_support_probe_preflight']}`"
            for r in scenario_rows
        )
        + "\n",
    )
    decision = {"recommended_next_stage": next_stage, "reason": next_reason}
    write_json(REPORT_DIR / "lp_fee_fix_repeat_next_stage_decision.json", decision)
    write_text(
        REPORT_DIR / "LP_FEE_FIX_REPEAT_NEXT_STAGE_DECISION_CN.md",
        "# LP Fee Fix Repeat Next Stage Decision\n\n"
        + f"- recommended_next_stage: `{next_stage}`\n"
        + f"- reason: `{next_reason}`\n",
    )
    write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
    write_text(
        REPORT_DIR / "ONEPAGE_CN.md",
        "# Onepage\n\n"
        + "\n".join(f"- `{k}`: `{fmt(v)}`" for k, v in verdict.items())
        + "\n",
    )
    artifacts = [
        "INPUT_ARTIFACT_AUDIT_CN.md",
        "input_artifact_audit.json",
        "VPS_DB_QUICK_CHECK_CN.md",
        "FEE_COVERAGE_GAP_DIAGNOSIS_CN.md",
        "fee_coverage_gap_diagnosis.csv",
        "FIXED_COST_MODEL_AUDIT_CN.md",
        "fixed_cost_model_audit.json",
        "fixed_cost_model_audit.csv",
        "FEE_VELOCITY_V2_RESULTS_CN.md",
        "fee_velocity_v2_results.csv",
        "fee_velocity_v2_results.json",
        "FIXED_COST_SENSITIVITY_ECONOMICS_CN.md",
        "fixed_cost_sensitivity_economics.csv",
        "fixed_cost_sensitivity_economics.json",
        "EV_SCENARIO_COMPARISON_CN.md",
        "ev_scenario_comparison.csv",
        "LP_FEE_FIX_REPEAT_NEXT_STAGE_DECISION_CN.md",
        "lp_fee_fix_repeat_next_stage_decision.json",
        "FINAL_VERDICT.json",
        "ONEPAGE_CN.md",
    ]
    write_text(REPORT_DIR / "ARTIFACT_INDEX.md", "# Artifact Index\n\n" + "\n".join(f"- `{name}`" for name in artifacts) + "\n")


def final_verdict(
    db: dict[str, Any],
    fee_v2_summary: dict[str, Any],
    fixed_summary: dict[str, Any],
    sensitivity_summary: dict[str, Any],
    sensitivity_rows_summary: list[dict[str, Any]],
    next_stage: str,
) -> dict[str, Any]:
    realistic = next(r for r in sensitivity_rows_summary if abs(r["fixed_cost_usd"] - 0.05) < 1e-9)
    zero = next(r for r in sensitivity_rows_summary if abs(r["fixed_cost_usd"] - 0.0) < 1e-9)
    main_blocker = realistic["primary_remaining_blocker"]
    return {
        "status": "PASS" if next_stage == "LP_VIRTUAL_NOTIONAL_ECONOMICS_V2" else "WARN" if db["db_ready"] else "FAIL",
        "stage": "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT_V1",
        "data_source": "vps_postgres",
        "db_ready": db["db_ready"],
        "fee_velocity_v2_built": True,
        "fee_ready_pool_count_v1": 1,
        "fee_ready_pool_count_v2": fee_v2_summary["fee_ready_pool_count"],
        "upgraded_pool_count": fee_v2_summary["upgraded_pool_count"],
        "fixed_cost_audit_complete": True,
        "fixed_cost_now_main_confirmed": realistic["primary_remaining_blocker"] == "fixed_cost_now_main",
        "fixed_cost_maybe_overconservative": fixed_summary["fixed_cost_maybe_overconservative"],
        "sensitivity_ran": True,
        "positive_proxy_count_fixed_cost_0": zero["positive_proxy_count"],
        "positive_proxy_count_realistic": realistic["positive_proxy_count"],
        "best_realistic_net_ev_proxy_usd": realistic["best_net_ev_proxy_usd"],
        "best_realistic_net_ev_proxy_pct": realistic["best_net_ev_proxy_pct"],
        "main_remaining_blocker": main_blocker,
        "can_run_virtual_notional_v2_next": next_stage == "LP_VIRTUAL_NOTIONAL_ECONOMICS_V2",
        "can_run_probe_now": False,
        "manual_approval_required_for_probe": True,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage,
    }


def generate() -> dict[str, Any]:
    ensure_dir(REPORT_DIR)
    input_rows, audit = input_audit()
    if not audit["previous_stage_ok"]:
        write_text(REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md", "# Wrong Stage Blocker\n\n上轮 stage 不是 `LP_FEE_VELOCITY_PIPELINE_V1`。\n")
        verdict = {
            "status": "FAIL",
            "stage": "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT_V1",
            "data_source": "vps_postgres",
            "db_ready": False,
            "fee_velocity_v2_built": False,
            "fee_ready_pool_count_v1": 1,
            "fee_ready_pool_count_v2": 0,
            "upgraded_pool_count": 0,
            "fixed_cost_audit_complete": False,
            "fixed_cost_now_main_confirmed": False,
            "fixed_cost_maybe_overconservative": False,
            "sensitivity_ran": False,
            "positive_proxy_count_fixed_cost_0": 0,
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
            "recommended_next_stage": "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT",
        }
        write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
        return verdict
    db = run_db_quick_check()
    if not db["db_ready"]:
        verdict = {
            "status": "FAIL",
            "stage": "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT_V1",
            "data_source": "vps_postgres",
            "db_ready": False,
            "fee_velocity_v2_built": False,
            "fee_ready_pool_count_v1": 1,
            "fee_ready_pool_count_v2": 0,
            "upgraded_pool_count": 0,
            "fixed_cost_audit_complete": False,
            "fixed_cost_now_main_confirmed": False,
            "fixed_cost_maybe_overconservative": False,
            "sensitivity_ran": False,
            "positive_proxy_count_fixed_cost_0": 0,
            "positive_proxy_count_realistic": 0,
            "best_realistic_net_ev_proxy_usd": None,
            "best_realistic_net_ev_proxy_pct": None,
            "main_remaining_blocker": "db_not_ready",
            "can_run_virtual_notional_v2_next": False,
            "can_run_probe_now": False,
            "manual_approval_required_for_probe": True,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "recommended_next_stage": "LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT",
        }
        write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
        return verdict
    targets = load_targets()
    v1_rows = load_csv(FEE_V1_DIR / "fee_velocity_results.csv")
    econ_rows = load_csv(VNE_DIR / "virtual_notional_economics_results.csv")
    pool_meta, mark_rows, score_rows = fetch_pool_context(targets)
    gap_rows, gap_summary = fee_gap_diag(targets, v1_rows, pool_meta, mark_rows, score_rows)
    fixed_components, fixed_summary, fixed_pool_rows = fixed_cost_model_audit(targets, econ_rows)
    fee_v2_rows, fee_v2_summary = compute_fee_v2(targets, v1_rows, pool_meta, mark_rows, score_rows)
    create_fee_v2_table(fee_v2_rows)
    sensitivity_rows, sensitivity_summary_rows, sensitivity_summary = sensitivity_preview(econ_rows, fee_v2_rows)
    create_sensitivity_table(sensitivity_rows)
    scenario_rows = scenario_comparison(sensitivity_rows, econ_rows)
    next_stage, next_reason = next_stage_decision(fee_v2_summary, sensitivity_summary, sensitivity_rows, sensitivity_rows)
    verdict = final_verdict(db, fee_v2_summary, fixed_summary, sensitivity_summary, sensitivity_summary_rows, next_stage)
    write_reports(
        input_rows,
        audit,
        db,
        gap_rows,
        gap_summary,
        fixed_components,
        fixed_summary,
        fixed_pool_rows,
        fee_v2_rows,
        fee_v2_summary,
        sensitivity_rows,
        sensitivity_summary_rows,
        sensitivity_summary,
        scenario_rows,
        next_stage,
        next_reason,
        verdict,
    )
    return verdict


def main() -> None:
    print(json.dumps(generate(), ensure_ascii=False))


if __name__ == "__main__":
    main()
