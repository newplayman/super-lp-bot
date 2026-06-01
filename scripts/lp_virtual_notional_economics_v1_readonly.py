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
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUN_ID = os.environ.get("RUN_ID_OVERRIDE", "20260601_094238")
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", "/Users/bendu/lp-bot/v3"))
REPORT_DIR = Path(
    os.environ.get(
        "REPORT_DIR_OVERRIDE",
        str(REPO_ROOT / "reports" / "lp_virtual_notional_economics" / RUN_ID),
    )
)
WORKSPACE = "/opt/lpbot/lp-bot-v3-origin-check"
QUOTE_FIX_DIR = REPO_ROOT / "reports" / "lp_quote_depth_curve_fix" / "20260601_091739"
SCALE_DIR = REPO_ROOT / "reports" / "lp_scale_economics" / "20260601_082100"
PIPELINE_DIR = REPO_ROOT / "reports" / "lp_data_pipeline" / "20260601_084943"
FREEZE_DIR = REPO_ROOT / "reports" / "final_freeze" / "20260531_124000"
TESTED_NOTIONALS = [20, 100, 500, 1000, 2000]
HORIZON_HOURS = {"15m": 0.25, "30m": 0.5, "1h": 1.0, "2h": 2.0}
ALLOWED_NEXT_STAGE = {
    "LP_PROBE_PREFLIGHT_10_20U_V1",
    "LP_FEE_VELOCITY_PIPELINE_V1",
    "LP_IL_LVR_PIPELINE_V1",
    "LP_QUOTE_DEPTH_CURVE_FIX_REPEAT",
    "LP_VIRTUAL_NOTIONAL_ECONOMICS_FIX_REPEAT",
    "STOP_LP_RESEARCH_NOW",
}


@dataclass
class PoolMeta:
    pool_id: str
    token_pair: str
    inferred_tier: str
    chain: str
    pool_type: str
    protocol: str
    fee_bps: float | None
    tvl_usd: float | None
    vol_24h: float | None
    fee_apr_24h: float | None
    entry_rows: int
    stale_rate: float | None
    data_quality_score: float | None
    exit_depth_score: float | None
    volatility_score: float | None
    volume_score: float | None
    tvl_score: float | None
    fee_proxy_score: float | None
    risk_score: float | None
    lookahead_safe: bool
    leakage_risk: str
    missing_features: str
    fee_proxy_direct_ready: bool


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
        QUOTE_FIX_DIR / "FINAL_VERDICT.json",
        QUOTE_FIX_DIR / "QUOTE_DEPTH_CURVE_V2_RESULTS_CN.md",
        QUOTE_FIX_DIR / "quote_depth_curve_v2_results.csv",
        QUOTE_FIX_DIR / "QUOTE_DEPTH_V2_CONFIDENCE_GATE_CN.md",
        QUOTE_FIX_DIR / "quote_depth_v2_confidence_gate.json",
        QUOTE_FIX_DIR / "QUOTE_DEPTH_V2_SANITY_AUDIT_CN.md",
        QUOTE_FIX_DIR / "quote_depth_v2_sanity_audit.json",
        QUOTE_FIX_DIR / "LP_QUOTE_DEPTH_V2_NEXT_STAGE_DECISION_CN.md",
        QUOTE_FIX_DIR / "lp_quote_depth_v2_next_stage_decision.json",
        SCALE_DIR / "FINAL_VERDICT.json",
        SCALE_DIR / "VIRTUAL_NOTIONAL_ECONOMICS_MODEL_CN.md",
        SCALE_DIR / "LP_POOL_SCORING_SYSTEM_V1_CN.md",
        SCALE_DIR / "TIER_ABC_LP_POOL_PROFILE_CN.md",
        PIPELINE_DIR / "FINAL_VERDICT.json",
        FREEZE_DIR / "FINAL_VERDICT.json",
    ]
    rows = []
    missing = []
    prior = load_json(QUOTE_FIX_DIR / "FINAL_VERDICT.json")
    for path in inputs:
        exists = path.exists()
        rows.append({"path": str(path.relative_to(REPO_ROOT)), "exists": exists})
        if not exists:
            missing.append(str(path.relative_to(REPO_ROOT)))
    audit = {
        "missing_input_list": missing,
        "previous_stage_ok": prior.get("stage") == "LP_QUOTE_DEPTH_CURVE_FIX_REPEAT_V1",
        "quote_depth_curve_v2_built": prior.get("quote_depth_curve_v2_built") is True,
        "data_ready_pool_count_ge_3": as_int(prior.get("data_ready_pool_count")) >= 3,
        "can_run_virtual_notional_next": prior.get("can_run_virtual_notional_next") is True,
        "can_run_probe_now": prior.get("can_run_probe_now") is False,
        "recommended_next_stage_ok": prior.get("recommended_next_stage") == "LP_VIRTUAL_NOTIONAL_ECONOMICS_V1",
        "can_execute_virtual_notional_economics": len(missing) == 0
        and prior.get("stage") == "LP_QUOTE_DEPTH_CURVE_FIX_REPEAT_V1"
        and prior.get("quote_depth_curve_v2_built") is True
        and as_int(prior.get("data_ready_pool_count")) >= 3
        and prior.get("can_run_virtual_notional_next") is True,
    }
    return rows, audit


def load_quote_rows() -> list[dict[str, str]]:
    return load_csv(QUOTE_FIX_DIR / "quote_depth_curve_v2_results.csv")


def query_pool_meta(pool_ids: list[str]) -> dict[str, PoolMeta]:
    quoted = ",".join("'" + p.replace("'", "''") + "'" for p in pool_ids)
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
  where run_id='20260531_113056' and pool_id in ({quoted})
  group by pool_id
),
fee as (
  select
    pool_id,
    count(*) filter (where fee_velocity_proxy is not null and fee_velocity_proxy::text <> '') as fee_proxy_rows
  from fee_velocity_exit_depth_counterfactual_v1
  where run_id='20260531_115101' and pool_id in ({quoted})
  group by pool_id
)
select
  q.pool_id,
  q.token_pair,
  q.inferred_tier,
  q.chain,
  q.pool_type,
  p.protocol,
  p.fee_bps,
  p.tvl_usd,
  p.vol_24h,
  p.fee_apr_24h,
  coalesce(e.entry_rows, 0) as entry_rows,
  e.stale_rate,
  e.data_quality_score,
  e.exit_depth_score,
  e.volatility_score,
  e.volume_score,
  e.tvl_score,
  e.fee_proxy_score,
  e.risk_score,
  coalesce(e.lookahead_safe, true) as lookahead_safe,
  coalesce(e.leakage_risk, 'LOW') as leakage_risk,
  coalesce(e.missing_features, '') as missing_features,
  coalesce(f.fee_proxy_rows, 0) > 0 as fee_proxy_direct_ready
from (
  select distinct pool_id, token_pair, inferred_tier, chain, pool_type
  from lp_quote_depth_curve_v2
  where run_id='20260601_091739' and pool_id in ({quoted})
) q
join pools p using (pool_id)
left join entry e using (pool_id)
left join fee f using (pool_id)
"""
    rows = ssh_psql_csv(query)
    out: dict[str, PoolMeta] = {}
    for row in rows:
        out[row["pool_id"]] = PoolMeta(
            pool_id=row["pool_id"],
            token_pair=row["token_pair"],
            inferred_tier=row["inferred_tier"],
            chain=row["chain"],
            pool_type=row["pool_type"],
            protocol=row.get("protocol") or "",
            fee_bps=as_float(row.get("fee_bps")),
            tvl_usd=as_float(row.get("tvl_usd")),
            vol_24h=as_float(row.get("vol_24h")),
            fee_apr_24h=as_float(row.get("fee_apr_24h")),
            entry_rows=as_int(row.get("entry_rows")),
            stale_rate=as_float(row.get("stale_rate")),
            data_quality_score=as_float(row.get("data_quality_score")),
            exit_depth_score=as_float(row.get("exit_depth_score")),
            volatility_score=as_float(row.get("volatility_score")),
            volume_score=as_float(row.get("volume_score")),
            tvl_score=as_float(row.get("tvl_score")),
            fee_proxy_score=as_float(row.get("fee_proxy_score")),
            risk_score=as_float(row.get("risk_score")),
            lookahead_safe=str(row.get("lookahead_safe")).lower() in {"t", "true", "1", "yes"},
            leakage_risk=row.get("leakage_risk") or "LOW",
            missing_features=row.get("missing_features") or "",
            fee_proxy_direct_ready=str(row.get("fee_proxy_direct_ready")).lower() in {"t", "true", "1", "yes"},
        )
    return out


def hold_time_factor(horizon: str) -> float:
    return HORIZON_HOURS[horizon] / 24.0


def fee_velocity_rate(meta: PoolMeta, horizon: str) -> tuple[float | None, str]:
    if not meta.tvl_usd or meta.tvl_usd <= 0 or not meta.vol_24h or meta.vol_24h <= 0 or not meta.fee_bps:
        return None, "missing_tvl_vol_or_fee_bps"
    turnover = meta.vol_24h / max(meta.tvl_usd, 1.0)
    efficiency = clamp(0.22 + ((meta.fee_proxy_score or 0.0) / 100.0) * 0.28, 0.18, 0.55)
    tier_mult = {"A": 1.0, "B": 0.9, "C": 0.7}.get(meta.inferred_tier, 0.75)
    daily_rate = (meta.fee_bps / 10000.0) * turnover * efficiency * tier_mult
    return max(daily_rate, 0.0), "pool_fee_bps_x_turnover_x_efficiency"


def il_lvr_proxy_rate(meta: PoolMeta, horizon: str) -> tuple[float | None, str]:
    if meta.volatility_score is None or meta.risk_score is None:
        return None, "missing_volatility_or_risk_score"
    h = HORIZON_HOURS[horizon]
    vol_component = (meta.volatility_score / 100.0) * 0.0016 * math.sqrt(max(h, 0.25) / 2.0)
    risk_component = (meta.risk_score / 100.0) * 0.0011 * (h / 2.0)
    stale_penalty = 0.0004 if (meta.stale_rate or 0.0) > 0.15 else 0.0
    return vol_component + risk_component + stale_penalty, "volatility_score_plus_risk_score_proxy"


def fixed_cost_proxy_usd(meta: PoolMeta) -> tuple[float, str]:
    base = 0.08 if meta.chain == "base" else 0.12
    pool_extra = 0.02 if meta.pool_type == "concentrated_liquidity" else 0.01
    return base + pool_extra, "base_chain_gas_and_routing_proxy"


def overall_confidence(quote_conf: str, meta: PoolMeta, all_ready: bool) -> str:
    if quote_conf == "low":
        return "low"
    if not all_ready:
        return "low"
    dq = meta.data_quality_score or 0.0
    stale = meta.stale_rate or 0.0
    if dq >= 90 and stale <= 0.1:
        return "high"
    return "medium"


def make_formula_doc() -> tuple[str, dict[str, Any]]:
    payload = {
        "gross_fee_proxy_usd": "virtual_notional * fee_velocity_rate * hold_time_factor",
        "il_lvr_proxy_usd": "virtual_notional * il_lvr_proxy_rate",
        "slippage_cost_usd": "virtual_notional * slippage_rate",
        "exit_cost_usd": "virtual_notional * exit_cost_rate",
        "fixed_cost_usd": "gas_proxy + fixed_routing_operational_cost_proxy",
        "net_ev_proxy_usd": "gross_fee_proxy_usd - il_lvr_proxy_usd - slippage_cost_usd - exit_cost_usd - fixed_cost_usd",
        "net_ev_proxy_pct": "net_ev_proxy_usd / virtual_notional",
        "variable_edge_rate": "(fee_velocity_rate * hold_time_factor) - il_lvr_proxy_rate - slippage_rate - exit_cost_rate",
        "break_even_notional_usd": "fixed_cost_usd / variable_edge_rate if variable_edge_rate > 0 else NO_SIZE_CAN_FIX",
    }
    md = "# Virtual Economics Formula V1\n\n" + "\n".join([f"- `{k} = {v}`" for k, v in payload.items()]) + "\n\n- 20U 结果不能线性外推到更大 notional。\n- 每个 notional 使用对应 quote/depth/slippage。\n- 低置信 quote 只进入 low_confidence economics。\n- 正 proxy EV 不代表 edge_proven。\n- 不允许进入 probe/canary。\n"
    return md, payload


def build_join_audit(quote_rows: list[dict[str, str]], metas: dict[str, PoolMeta]) -> list[dict[str, Any]]:
    pool_best_conf = {}
    for row in quote_rows:
        if row["virtual_notional_usd"] == "20":
            pool_best_conf[row["pool_id"]] = row["confidence"]
    out = []
    for pool_id, meta in metas.items():
        quote_ready = pool_best_conf.get(pool_id) in {"high", "medium"}
        fee_ready = meta.fee_bps is not None and meta.tvl_usd is not None and meta.vol_24h is not None
        entry_ready = meta.entry_rows > 0 and meta.lookahead_safe and meta.leakage_risk == "LOW"
        il_ready = meta.volatility_score is not None and meta.risk_score is not None
        fixed_ready = True
        all_ready = quote_ready and fee_ready and entry_ready and il_ready and fixed_ready
        blocker = ""
        if not quote_ready:
            blocker = "quote_depth_low_confidence"
        elif not fee_ready:
            blocker = "fee_velocity_proxy_missing"
        elif not entry_ready:
            blocker = "entry_snapshot_missing_or_unsafe"
        elif not il_ready:
            blocker = "il_lvr_proxy_missing"
        out.append(
            {
                "pool_id": pool_id,
                "token_pair": meta.token_pair,
                "inferred_tier": meta.inferred_tier,
                "quote_depth_ready": "yes" if quote_ready else "no",
                "fee_velocity_ready": "yes" if fee_ready else "no",
                "entry_snapshot_ready": "yes" if entry_ready else "no",
                "il_lvr_proxy_ready": "yes" if il_ready else "no",
                "fixed_cost_proxy_ready": "yes",
                "all_required_ready": "yes" if all_ready else "no",
                "confidence": pool_best_conf.get(pool_id, "low"),
                "blocker": blocker,
            }
        )
    return out


def economics_rows(quote_rows: list[dict[str, str]], metas: dict[str, PoolMeta]) -> list[dict[str, Any]]:
    out = []
    for q in quote_rows:
        meta = metas[q["pool_id"]]
        slippage_rate = (as_float(q["estimated_slippage_pct"]) or 0.0) / 100.0
        exit_cost_rate = (as_float(q["estimated_price_impact_pct"]) or 0.0) / 100.0
        capacity_pass = q["capacity_pass"] == "yes"
        quote_conf = q["confidence"]
        for horizon in HORIZON_HOURS:
            fee_rate, fee_reason = fee_velocity_rate(meta, horizon)
            il_rate, il_reason = il_lvr_proxy_rate(meta, horizon)
            fixed_usd, fixed_reason = fixed_cost_proxy_usd(meta)
            required_ready = all(v is not None for v in [fee_rate, il_rate]) and meta.entry_rows > 0 and meta.lookahead_safe
            gross_fee = None if fee_rate is None else float(q["virtual_notional_usd"]) * fee_rate * hold_time_factor(horizon)
            il_usd = None if il_rate is None else float(q["virtual_notional_usd"]) * il_rate
            slip_usd = float(q["virtual_notional_usd"]) * slippage_rate
            exit_usd = float(q["virtual_notional_usd"]) * exit_cost_rate
            if fee_rate is None or il_rate is None:
                variable_edge = None
                net_usd = None
                net_pct = None
                break_even = None
                no_size_can_fix = False
                ev_status = "DATA_INSUFFICIENT"
                primary_blocker = "fee_too_low" if fee_rate is None else "il_lvr_too_high"
            else:
                variable_edge = fee_rate * hold_time_factor(horizon) - il_rate - slippage_rate - exit_cost_rate
                no_size_can_fix = variable_edge <= 0
                break_even = None if no_size_can_fix else fixed_usd / variable_edge
                net_usd = gross_fee - il_usd - slip_usd - exit_usd - fixed_usd
                net_pct = net_usd / float(q["virtual_notional_usd"])
                if not capacity_pass:
                    ev_status = "CAPACITY_FAIL"
                    primary_blocker = "capacity_too_low"
                elif no_size_can_fix:
                    ev_status = "NO_SIZE_CAN_FIX"
                    primary_blocker = dominant_blocker(fee_rate, il_rate, slippage_rate, exit_cost_rate, fixed_usd, float(q["virtual_notional_usd"]), meta, confidence=quote_conf)
                elif net_usd > 0:
                    ev_status = "POSITIVE_PROXY"
                    primary_blocker = ""
                elif break_even and break_even > float(q["virtual_notional_usd"]):
                    ev_status = "BELOW_BREAK_EVEN"
                    primary_blocker = "fixed_cost_too_high"
                else:
                    ev_status = "NEGATIVE_PROXY"
                    primary_blocker = dominant_blocker(fee_rate, il_rate, slippage_rate, exit_cost_rate, fixed_usd, float(q["virtual_notional_usd"]), meta, confidence=quote_conf)
            if not required_ready and ev_status != "CAPACITY_FAIL":
                ev_status = "DATA_INSUFFICIENT"
                if primary_blocker == "":
                    primary_blocker = "data_confidence_low"
            conf = overall_confidence(quote_conf, meta, required_ready)
            out.append(
                {
                    "run_id": RUN_ID,
                    "pool_id": q["pool_id"],
                    "token_pair": meta.token_pair,
                    "inferred_tier": meta.inferred_tier,
                    "virtual_notional_usd": as_int(q["virtual_notional_usd"]),
                    "horizon": horizon,
                    "quote_depth_confidence": quote_conf,
                    "capacity_pass": "yes" if capacity_pass else "no",
                    "capacity_limit_usd": as_float(q["capacity_limit_usd"]),
                    "gross_fee_proxy_usd": gross_fee,
                    "fee_velocity_rate": fee_rate,
                    "il_lvr_proxy_usd": il_usd,
                    "il_lvr_proxy_rate": il_rate,
                    "slippage_cost_usd": slip_usd,
                    "slippage_rate": slippage_rate,
                    "exit_cost_usd": exit_usd,
                    "fixed_cost_usd": fixed_usd,
                    "net_ev_proxy_usd": net_usd,
                    "net_ev_proxy_pct": net_pct,
                    "variable_edge_rate": variable_edge,
                    "break_even_notional_usd": break_even,
                    "no_size_can_fix": "yes" if no_size_can_fix else "no",
                    "ev_status": ev_status,
                    "confidence": conf,
                    "primary_blocker": primary_blocker,
                    "fee_reason": fee_reason,
                    "il_reason": il_reason,
                    "fixed_reason": fixed_reason,
                    "entry_rows": meta.entry_rows,
                    "stale_rate": meta.stale_rate,
                }
            )
    return out


def dominant_blocker(fee_rate: float, il_rate: float, slip_rate: float, exit_rate: float, fixed_usd: float, notional: float, meta: PoolMeta, confidence: str) -> str:
    if confidence == "low":
        return "data_confidence_low"
    comps = {
        "fee_too_low": max(0.0, il_rate + slip_rate + exit_rate - fee_rate),
        "il_lvr_too_high": il_rate,
        "exit_cost_too_high": max(slip_rate, exit_rate),
        "fixed_cost_too_high": fixed_usd / notional,
        "capacity_too_low": 0.0,
        "data_confidence_low": 0.0,
        "no_size_can_fix": 0.0,
    }
    if meta.risk_score is not None and meta.risk_score <= 5 and fee_rate <= 0:
        return "fee_too_low"
    return max(comps.items(), key=lambda kv: kv[1])[0]


def create_research_table(rows: list[dict[str, Any]]) -> None:
    run_id_sql = "'" + RUN_ID.replace("'", "''") + "'"
    def sql_text(value: str | None) -> str:
        if value is None:
            return "null"
        return "'" + str(value).replace("'", "''") + "'"
    create_sql = """
create table if not exists lp_virtual_notional_economics_v1 (
  run_id text not null,
  pool_id text not null,
  token_pair text,
  inferred_tier text,
  virtual_notional_usd integer,
  horizon text,
  quote_depth_confidence text,
  capacity_pass text,
  capacity_limit_usd double precision,
  gross_fee_proxy_usd double precision,
  fee_velocity_rate double precision,
  il_lvr_proxy_usd double precision,
  il_lvr_proxy_rate double precision,
  slippage_cost_usd double precision,
  slippage_rate double precision,
  exit_cost_usd double precision,
  fixed_cost_usd double precision,
  net_ev_proxy_usd double precision,
  net_ev_proxy_pct double precision,
  variable_edge_rate double precision,
  break_even_notional_usd double precision,
  no_size_can_fix text,
  ev_status text,
  confidence text,
  primary_blocker text,
  created_at timestamptz default now()
);
delete from lp_virtual_notional_economics_v1 where run_id = {run_id};
""".format(run_id=run_id_sql)
    ssh_psql_exec(create_sql)
    def build_value(row: dict[str, Any]) -> str:
        return (
            "(" + ",".join([
                sql_text(RUN_ID),
                sql_text(row["pool_id"]),
                sql_text(row["token_pair"]),
                sql_text(row["inferred_tier"]),
                str(int(row["virtual_notional_usd"])),
                sql_text(row["horizon"]),
                sql_text(row["quote_depth_confidence"]),
                sql_text(row["capacity_pass"]),
                "null" if row["capacity_limit_usd"] is None else str(float(row["capacity_limit_usd"])),
                "null" if row["gross_fee_proxy_usd"] is None else str(float(row["gross_fee_proxy_usd"])),
                "null" if row["fee_velocity_rate"] is None else str(float(row["fee_velocity_rate"])),
                "null" if row["il_lvr_proxy_usd"] is None else str(float(row["il_lvr_proxy_usd"])),
                "null" if row["il_lvr_proxy_rate"] is None else str(float(row["il_lvr_proxy_rate"])),
                "null" if row["slippage_cost_usd"] is None else str(float(row["slippage_cost_usd"])),
                "null" if row["slippage_rate"] is None else str(float(row["slippage_rate"])),
                "null" if row["exit_cost_usd"] is None else str(float(row["exit_cost_usd"])),
                str(float(row["fixed_cost_usd"])),
                "null" if row["net_ev_proxy_usd"] is None else str(float(row["net_ev_proxy_usd"])),
                "null" if row["net_ev_proxy_pct"] is None else str(float(row["net_ev_proxy_pct"])),
                "null" if row["variable_edge_rate"] is None else str(float(row["variable_edge_rate"])),
                "null" if row["break_even_notional_usd"] is None else str(float(row["break_even_notional_usd"])),
                sql_text(row["no_size_can_fix"]),
                sql_text(row["ev_status"]),
                sql_text(row["confidence"]),
                sql_text(row["primary_blocker"]),
                "now()",
            ]) + ")"
        )
    batch_size = 100
    for idx in range(0, len(rows), batch_size):
        batch_values = [build_value(row) for row in rows[idx: idx + batch_size]]
        insert_sql = (
            "insert into lp_virtual_notional_economics_v1 (run_id,pool_id,token_pair,inferred_tier,virtual_notional_usd,horizon,"
            "quote_depth_confidence,capacity_pass,capacity_limit_usd,gross_fee_proxy_usd,fee_velocity_rate,il_lvr_proxy_usd,"
            "il_lvr_proxy_rate,slippage_cost_usd,slippage_rate,exit_cost_usd,fixed_cost_usd,net_ev_proxy_usd,net_ev_proxy_pct,"
            "variable_edge_rate,break_even_notional_usd,no_size_can_fix,ev_status,confidence,primary_blocker,created_at) values "
            + ",\n".join(batch_values)
            + ";"
        )
        ssh_psql_exec(insert_sql)


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    positive_proxy_by_notional = Counter()
    capacity_pass_by_notional = Counter()
    confidence_distribution = Counter()
    for row in rows:
        confidence_distribution[row["confidence"]] += 1
        if row["capacity_pass"] == "yes":
            capacity_pass_by_notional[str(row["virtual_notional_usd"])] += 1
        if row["ev_status"] == "POSITIVE_PROXY":
            positive_proxy_by_notional[str(row["virtual_notional_usd"])] += 1
    return {
        "pool_count": len({r["pool_id"] for r in rows}),
        "row_count": len(rows),
        "positive_proxy_count": sum(1 for r in rows if r["ev_status"] == "POSITIVE_PROXY"),
        "negative_proxy_count": sum(1 for r in rows if r["ev_status"] == "NEGATIVE_PROXY"),
        "below_break_even_count": sum(1 for r in rows if r["ev_status"] == "BELOW_BREAK_EVEN"),
        "capacity_fail_count": sum(1 for r in rows if r["ev_status"] == "CAPACITY_FAIL"),
        "data_insufficient_count": sum(1 for r in rows if r["ev_status"] == "DATA_INSUFFICIENT"),
        "no_size_can_fix_count": sum(1 for r in rows if r["ev_status"] == "NO_SIZE_CAN_FIX"),
        "positive_proxy_by_notional": dict(positive_proxy_by_notional),
        "capacity_pass_by_notional": dict(capacity_pass_by_notional),
        "confidence_distribution": dict(confidence_distribution),
    }


def break_even_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_pool = defaultdict(list)
    for row in rows:
        by_pool[row["pool_id"]].append(row)
    out = []
    for pool_id, pool_rows in by_pool.items():
        valid = [r for r in pool_rows if r["capacity_pass"] == "yes" and r["net_ev_proxy_usd"] is not None]
        best = max(valid, key=lambda r: r["net_ev_proxy_usd"]) if valid else pool_rows[0]
        capacity_pass_rows = [r for r in pool_rows if r["capacity_pass"] == "yes"]
        max_notional = max((r["virtual_notional_usd"] for r in capacity_pass_rows), default=0)
        limiting = best["primary_blocker"] or "unknown"
        out.append(
            {
                "pool_id": pool_id,
                "token_pair": best["token_pair"],
                "inferred_tier": best["inferred_tier"],
                "best_notional": best["virtual_notional_usd"],
                "break_even_notional_usd": best["break_even_notional_usd"],
                "capacity_limit_usd": best["capacity_limit_usd"],
                "no_size_can_fix": best["no_size_can_fix"],
                "best_ev_status": best["ev_status"],
                "best_net_ev_proxy_usd": best["net_ev_proxy_usd"],
                "best_net_ev_proxy_pct": best["net_ev_proxy_pct"],
                "max_notional_capacity_pass": max_notional,
                "primary_limiting_factor": limiting if limiting in {
                    "fee_too_low", "il_lvr_too_high", "exit_cost_too_high", "fixed_cost_too_high",
                    "capacity_too_low", "data_confidence_low", "no_size_can_fix"
                } else "unknown",
            }
        )
    return out


def ranking_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_pool = defaultdict(list)
    for row in rows:
        by_pool[row["pool_id"]].append(row)
    ranked = []
    for pool_id, pool_rows in by_pool.items():
        valid = [r for r in pool_rows if r["capacity_pass"] == "yes" and r["net_ev_proxy_usd"] is not None]
        best = max(valid, key=lambda r: r["net_ev_proxy_usd"]) if valid else pool_rows[0]
        fee_conf = "high" if best["fee_velocity_rate"] is not None else "low"
        il_conf = "high" if best["il_lvr_proxy_rate"] is not None else "low"
        overall = best["confidence"]
        if best["ev_status"] == "POSITIVE_PROXY" and overall in {"high", "medium"} and best["virtual_notional_usd"] in {20, 100}:
            status = "VIRTUAL_CANDIDATE"
            reason = "positive_proxy_under_small_notional_with_capacity"
        elif best["ev_status"] in {"POSITIVE_PROXY", "BELOW_BREAK_EVEN"} and overall == "low":
            status = "DATA_FIX"
            reason = "positive_or_near_positive_but_low_confidence"
        elif best["ev_status"] in {"POSITIVE_PROXY", "BELOW_BREAK_EVEN", "NEGATIVE_PROXY"}:
            status = "WATCH"
            reason = "economics_not_terrible_but_not_ready"
        else:
            status = "REJECT"
            reason = best["primary_blocker"] or "no_size_can_fix"
        ranked.append(
            {
                "pool_id": pool_id,
                "token_pair": best["token_pair"],
                "inferred_tier": best["inferred_tier"],
                "best_notional": best["virtual_notional_usd"],
                "best_horizon": best["horizon"],
                "net_ev_proxy_usd": best["net_ev_proxy_usd"],
                "net_ev_proxy_pct": best["net_ev_proxy_pct"],
                "break_even_notional_usd": best["break_even_notional_usd"],
                "capacity_limit_usd": best["capacity_limit_usd"],
                "quote_confidence": best["quote_depth_confidence"],
                "fee_confidence": fee_conf,
                "il_lvr_confidence": il_conf,
                "overall_confidence": overall,
                "candidate_status": status,
                "reason": reason,
            }
        )
    ranked.sort(key=lambda r: ((0 if r["candidate_status"] == "VIRTUAL_CANDIDATE" else 1), -(r["net_ev_proxy_usd"] or -9999)))
    for idx, row in enumerate(ranked, start=1):
        row["rank"] = idx
    return ranked


def probe_assessment(ranked: list[dict[str, Any]]) -> dict[str, Any]:
    probe_candidates = [
        r for r in ranked
        if r["candidate_status"] == "VIRTUAL_CANDIDATE"
        and r["best_notional"] in {20, 100}
        and r["overall_confidence"] in {"high", "medium"}
    ]
    return {
        "probe_candidate_count": len(probe_candidates),
        "probe_candidates": [r["pool_id"] for r in probe_candidates],
        "can_run_probe_now": False,
        "manual_approval_required_for_probe": True,
    }


def next_stage_decision(agg: dict[str, Any], ranked: list[dict[str, Any]], probe: dict[str, Any]) -> tuple[str, str]:
    if probe["probe_candidate_count"] >= 1:
        stage = "LP_PROBE_PREFLIGHT_10_20U_V1"
        reason = "at_least_one_small_notional_virtual_candidate_exists"
    elif agg["positive_proxy_count"] == 0 and agg["data_insufficient_count"] > agg["negative_proxy_count"]:
        stage = "LP_FEE_VELOCITY_PIPELINE_V1"
        reason = "economics_blocked_mainly_by_missing_fee_proxy"
    elif agg["positive_proxy_count"] == 0 and agg["no_size_can_fix_count"] > agg["capacity_fail_count"]:
        stage = "LP_IL_LVR_PIPELINE_V1"
        reason = "variable_edge_non_positive_on_most_rows"
    elif agg["capacity_fail_count"] > agg["positive_proxy_count"]:
        stage = "LP_VIRTUAL_NOTIONAL_ECONOMICS_FIX_REPEAT"
        reason = "model_works_but_capacity_and_cost_proxies_need_refinement"
    else:
        stage = "LP_VIRTUAL_NOTIONAL_ECONOMICS_FIX_REPEAT"
        reason = "first_pass_economics_generated_but_needs_refinement"
    return stage, reason


def write_reports(
    input_rows: list[dict[str, Any]],
    input_audit_payload: dict[str, Any],
    db_payload: dict[str, Any],
    formula_md: str,
    formula_json: dict[str, Any],
    join_rows: list[dict[str, Any]],
    econ_rows: list[dict[str, Any]],
    agg: dict[str, Any],
    break_even: list[dict[str, Any]],
    ranking: list[dict[str, Any]],
    probe: dict[str, Any],
    next_stage: str,
    next_reason: str,
    verdict: dict[str, Any],
) -> None:
    write_text(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", "# Input Artifact Audit\n\n" + "\n".join([f"- `{r['path']}`: `{'yes' if r['exists'] else 'no'}`" for r in input_rows]) + "\n")
    write_json(REPORT_DIR / "input_artifact_audit.json", input_audit_payload)
    write_text(REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md", "# VPS DB Quick Check\n\n" + "\n".join([f"- `{k}`: `{fmt(v)}`" for k, v in db_payload.items() if k in {"dsn_present", "db_connect", "db_name", "db_user", "db_ready"}]) + "\n")
    write_text(REPORT_DIR / "VIRTUAL_ECONOMICS_FORMULA_V1_CN.md", formula_md)
    write_json(REPORT_DIR / "virtual_economics_formula_v1.json", formula_json)
    write_csv(REPORT_DIR / "virtual_economics_data_join_audit.csv", join_rows, [
        "pool_id","token_pair","inferred_tier","quote_depth_ready","fee_velocity_ready","entry_snapshot_ready",
        "il_lvr_proxy_ready","fixed_cost_proxy_ready","all_required_ready","confidence","blocker"
    ])
    write_text(REPORT_DIR / "VIRTUAL_ECONOMICS_DATA_JOIN_AUDIT_CN.md", "# Virtual Economics Data Join Audit\n\n" + "\n".join([f"- `{r['pool_id']}` `{r['token_pair']}` all_required_ready=`{r['all_required_ready']}` blocker=`{r['blocker']}`" for r in join_rows]) + "\n")
    schema = {
        "table_name": "lp_virtual_notional_economics_v1",
        "required_fields": [
            "run_id","pool_id","token_pair","inferred_tier","virtual_notional_usd","horizon","quote_depth_confidence",
            "capacity_pass","capacity_limit_usd","gross_fee_proxy_usd","fee_velocity_rate","il_lvr_proxy_usd","il_lvr_proxy_rate",
            "slippage_cost_usd","slippage_rate","exit_cost_usd","fixed_cost_usd","net_ev_proxy_usd","net_ev_proxy_pct",
            "variable_edge_rate","break_even_notional_usd","no_size_can_fix","ev_status","confidence","primary_blocker","created_at"
        ]
    }
    write_text(REPORT_DIR / "VIRTUAL_NOTIONAL_ECONOMICS_SCHEMA_CN.md", "# Virtual Notional Economics Schema\n\n" + "\n".join([f"- `{f}`" for f in schema["required_fields"]]) + "\n")
    write_json(REPORT_DIR / "virtual_notional_economics_schema.json", schema)
    write_csv(REPORT_DIR / "virtual_notional_economics_results.csv", econ_rows, [
        "run_id","pool_id","token_pair","inferred_tier","virtual_notional_usd","horizon","quote_depth_confidence","capacity_pass","capacity_limit_usd",
        "gross_fee_proxy_usd","fee_velocity_rate","il_lvr_proxy_usd","il_lvr_proxy_rate","slippage_cost_usd","slippage_rate","exit_cost_usd",
        "fixed_cost_usd","net_ev_proxy_usd","net_ev_proxy_pct","variable_edge_rate","break_even_notional_usd","no_size_can_fix","ev_status",
        "confidence","primary_blocker"
    ])
    write_json(REPORT_DIR / "virtual_notional_economics_results.json", agg)
    write_text(REPORT_DIR / "VIRTUAL_NOTIONAL_ECONOMICS_RESULTS_CN.md", "# Virtual Notional Economics Results\n\n" + "\n".join([f"- `{k}`: `{fmt(v)}`" for k, v in agg.items()]) + "\n")
    write_csv(REPORT_DIR / "break_even_and_capacity_analysis.csv", break_even, list(break_even[0].keys()) if break_even else [
        "pool_id","token_pair","inferred_tier","best_notional","break_even_notional_usd","capacity_limit_usd","no_size_can_fix",
        "best_ev_status","best_net_ev_proxy_usd","best_net_ev_proxy_pct","max_notional_capacity_pass","primary_limiting_factor"
    ])
    write_text(REPORT_DIR / "BREAK_EVEN_AND_CAPACITY_ANALYSIS_CN.md", "# Break Even And Capacity Analysis\n\n" + "\n".join([f"- `{r['pool_id']}` best_notional=`{r['best_notional']}` best_ev_status=`{r['best_ev_status']}` limiting=`{r['primary_limiting_factor']}`" for r in break_even]) + "\n")
    write_csv(REPORT_DIR / "virtual_notional_candidate_ranking.csv", ranking, [
        "rank","pool_id","token_pair","inferred_tier","best_notional","best_horizon","net_ev_proxy_usd","net_ev_proxy_pct",
        "break_even_notional_usd","capacity_limit_usd","quote_confidence","fee_confidence","il_lvr_confidence","overall_confidence","candidate_status","reason"
    ])
    write_text(REPORT_DIR / "VIRTUAL_NOTIONAL_CANDIDATE_RANKING_CN.md", "# Virtual Notional Candidate Ranking\n\n" + "\n".join([f"- `#{r['rank']}` `{r['pool_id']}` status=`{r['candidate_status']}` best_notional=`{r['best_notional']}` net_ev=`{fmt(r['net_ev_proxy_usd'])}`" for r in ranking]) + "\n")
    write_json(REPORT_DIR / "probe_readiness_assessment.json", probe)
    write_text(REPORT_DIR / "PROBE_READINESS_ASSESSMENT_CN.md", "# Probe Readiness Assessment\n\n" + "\n".join([f"- `{k}`: `{fmt(v)}`" for k, v in probe.items() if k != "probe_candidates"]) + "\n")
    write_json(REPORT_DIR / "lp_virtual_notional_next_stage_decision.json", {"recommended_next_stage": next_stage, "reason": next_reason, **probe})
    write_text(REPORT_DIR / "LP_VIRTUAL_NOTIONAL_NEXT_STAGE_DECISION_CN.md", "# LP Virtual Notional Next Stage Decision\n\n" + f"- recommended_next_stage: `{next_stage}`\n- reason: `{next_reason}`\n- can_run_probe_now: `{fmt(probe['can_run_probe_now'])}`\n- manual_approval_required_for_probe: `{fmt(probe['manual_approval_required_for_probe'])}`\n")
    write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
    write_text(REPORT_DIR / "ONEPAGE_CN.md", "# LP Virtual Notional Economics V1\n\n" + "\n".join([f"- `{k}`: `{fmt(v)}`" for k, v in verdict.items()]) + "\n")
    artifact_files = [
        "INPUT_ARTIFACT_AUDIT_CN.md","input_artifact_audit.json","VPS_DB_QUICK_CHECK_CN.md","VIRTUAL_ECONOMICS_FORMULA_V1_CN.md",
        "virtual_economics_formula_v1.json","VIRTUAL_ECONOMICS_DATA_JOIN_AUDIT_CN.md","virtual_economics_data_join_audit.csv",
        "VIRTUAL_NOTIONAL_ECONOMICS_SCHEMA_CN.md","virtual_notional_economics_schema.json","VIRTUAL_NOTIONAL_ECONOMICS_RESULTS_CN.md",
        "virtual_notional_economics_results.csv","virtual_notional_economics_results.json","BREAK_EVEN_AND_CAPACITY_ANALYSIS_CN.md",
        "break_even_and_capacity_analysis.csv","VIRTUAL_NOTIONAL_CANDIDATE_RANKING_CN.md","virtual_notional_candidate_ranking.csv",
        "PROBE_READINESS_ASSESSMENT_CN.md","probe_readiness_assessment.json","LP_VIRTUAL_NOTIONAL_NEXT_STAGE_DECISION_CN.md",
        "lp_virtual_notional_next_stage_decision.json","FINAL_VERDICT.json","ONEPAGE_CN.md",
    ]
    write_text(REPORT_DIR / "ARTIFACT_INDEX.md", "# Artifact Index\n\n" + "\n".join([f"- `{f}`" for f in artifact_files]) + "\n")


def final_verdict(agg: dict[str, Any], ranking: list[dict[str, Any]], probe: dict[str, Any], db: dict[str, Any], next_stage: str) -> dict[str, Any]:
    best = max((r for r in ranking if r["net_ev_proxy_usd"] is not None), key=lambda r: r["net_ev_proxy_usd"], default=None)
    virtual_candidate_count = sum(1 for r in ranking if r["candidate_status"] == "VIRTUAL_CANDIDATE")
    status = "PASS" if agg["positive_proxy_count"] > 0 else "WARN"
    if not db["db_ready"]:
        status = "FAIL"
    return {
        "status": status,
        "stage": "LP_VIRTUAL_NOTIONAL_ECONOMICS_V1",
        "data_source": "vps_postgres",
        "db_ready": db["db_ready"],
        "tested_virtual_notionals": TESTED_NOTIONALS,
        "pool_count": agg["pool_count"],
        "row_count": agg["row_count"],
        "positive_proxy_count": agg["positive_proxy_count"],
        "virtual_candidate_count": virtual_candidate_count,
        "probe_candidate_count": probe["probe_candidate_count"],
        "best_pool_id": best["pool_id"] if best else "",
        "best_notional_usd": best["best_notional"] if best else None,
        "best_net_ev_proxy_usd": best["net_ev_proxy_usd"] if best else None,
        "best_net_ev_proxy_pct": best["net_ev_proxy_pct"] if best else None,
        "break_even_notional_usd": best["break_even_notional_usd"] if best else None,
        "capacity_limit_usd": best["capacity_limit_usd"] if best else None,
        "data_confidence": best["overall_confidence"] if best else "",
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
        write_text(REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md", "# Wrong Stage Blocker\n\n上轮 stage 不是 `LP_QUOTE_DEPTH_CURVE_FIX_REPEAT_V1`。\n")
        verdict = {
            "status": "FAIL","stage": "LP_VIRTUAL_NOTIONAL_ECONOMICS_V1","data_source": "vps_postgres","db_ready": False,
            "tested_virtual_notionals": TESTED_NOTIONALS,"pool_count": 0,"row_count": 0,"positive_proxy_count": 0,"virtual_candidate_count": 0,
            "probe_candidate_count": 0,"best_pool_id": "","best_notional_usd": None,"best_net_ev_proxy_usd": None,"best_net_ev_proxy_pct": None,
            "break_even_notional_usd": None,"capacity_limit_usd": None,"data_confidence": "","can_run_probe_now": False,
            "manual_approval_required_for_probe": True,"edge_proven": "no","tiny_canary_candidate": "no","tiny_canary_allowed": "no",
            "recommended_next_stage": "LP_VIRTUAL_NOTIONAL_ECONOMICS_FIX_REPEAT"
        }
        write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
        return verdict
    db = run_db_quick_check()
    if not db["db_ready"]:
        verdict = {
            "status": "FAIL","stage": "LP_VIRTUAL_NOTIONAL_ECONOMICS_V1","data_source": "vps_postgres","db_ready": False,
            "tested_virtual_notionals": TESTED_NOTIONALS,"pool_count": 0,"row_count": 0,"positive_proxy_count": 0,"virtual_candidate_count": 0,
            "probe_candidate_count": 0,"best_pool_id": "","best_notional_usd": None,"best_net_ev_proxy_usd": None,"best_net_ev_proxy_pct": None,
            "break_even_notional_usd": None,"capacity_limit_usd": None,"data_confidence": "","can_run_probe_now": False,
            "manual_approval_required_for_probe": True,"edge_proven": "no","tiny_canary_candidate": "no","tiny_canary_allowed": "no",
            "recommended_next_stage": "LP_FEE_VELOCITY_PIPELINE_V1"
        }
        write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
        return verdict
    formula_md, formula_json = make_formula_doc()
    quote_rows = load_quote_rows()
    metas = query_pool_meta(sorted({r["pool_id"] for r in quote_rows}))
    join_rows = build_join_audit(quote_rows, metas)
    econ_rows = economics_rows(quote_rows, metas)
    create_research_table(econ_rows)
    agg = aggregate(econ_rows)
    break_even = break_even_rows(econ_rows)
    ranking = ranking_rows(econ_rows)
    probe = probe_assessment(ranking)
    next_stage, next_reason = next_stage_decision(agg, ranking, probe)
    verdict = final_verdict(agg, ranking, probe, db, next_stage)
    write_reports(input_rows, audit, db, formula_md, formula_json, join_rows, econ_rows, agg, break_even, ranking, probe, next_stage, next_reason, verdict)
    return verdict


def main() -> None:
    print(json.dumps(generate(), ensure_ascii=False))


if __name__ == "__main__":
    main()
