#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import shlex
import subprocess
from pathlib import Path
from typing import Any


RUN_ID = "20260601_082100"
REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
REPORT_DIR = REPO_ROOT / "reports" / "lp_scale_economics" / RUN_ID
WORKSPACE = "/opt/lpbot/lp-bot-v3-origin-check"
NOTIONALS = [20, 100, 500, 1000, 2000]

INPUTS = [
    "reports/final_freeze/20260531_124000/FINAL_VERDICT.json",
    "reports/final_freeze/20260531_124000/LPBOT_FINAL_ONEPAGE_CN.md",
    "reports/final_freeze/20260531_124000/STRATEGY_LINE_FREEZE_MATRIX_CN.md",
    "reports/final_freeze/20260531_124000/WHY_NO_CANARY_CN.md",
    "reports/final_freeze/20260531_124000/REOPEN_CONDITIONS_CN.md",
    "reports/final_freeze/20260531_124000/NEXT_PROJECT_OPTIONS_CN.md",
    "reports/fee_velocity_rule_fix/20260531_122413/FINAL_VERDICT.json",
    "reports/fee_velocity_exit_depth/20260531_115101/FINAL_VERDICT.json",
    "reports/pool_regime_rule_fix/20260531_113056/FINAL_VERDICT.json",
    "reports/risk_signal_definition_fix/20260531_080614/FINAL_VERDICT.json",
    "reports/tierc_shadow/20260529_155854/TIER_C_BATCH_FINAL_FREEZE_VERDICT.json",
    "reports/tierb_data_fix/20260530_125453/FINAL_VERDICT.json",
    "reports/portfolio_status/20260529_160811/FINAL_VERDICT.json",
]


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


def fmt(v: Any, digits: int = 6) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return ""
        return f"{v:.{digits}f}".rstrip("0").rstrip(".")
    return str(v)


def num(v: Any) -> float | None:
    if v in (None, "", "null", "None"):
        return None
    try:
        return float(v)
    except Exception:
        return None


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def median(vals: list[float]) -> float | None:
    seq = sorted(v for v in vals if v is not None)
    if not seq:
        return None
    n = len(seq)
    mid = n // 2
    if n % 2:
        return seq[mid]
    return (seq[mid - 1] + seq[mid]) / 2.0


def percentile(vals: list[float], p: float) -> float | None:
    seq = sorted(v for v in vals if v is not None)
    if not seq:
        return None
    idx = max(0, min(len(seq) - 1, round((len(seq) - 1) * p)))
    return seq[idx]


def safe_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


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
    remote_script = "\n".join(
        [
            "set -a",
            "source .env 2>/dev/null || true",
            "source .env.chain 2>/dev/null || true",
            "source .runtime.shadow.env 2>/dev/null || true",
            "set +a",
            "python3 - <<'PY'",
            remote_python,
            "PY",
        ]
    )
    remote_cmd = f"cd {shlex.quote(WORKSPACE)} && bash -lc {shlex.quote(remote_script)}"
    proc = subprocess.run(["ssh", "vps", remote_cmd], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ssh_psql_failed: {proc.stderr.strip() or proc.stdout.strip()}")
    text = proc.stdout.strip()
    if not text:
        return []
    return list(csv.DictReader(text.splitlines()))


def build_input_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    missing = []
    for rel in INPUTS:
        path = REPO_ROOT / rel
        exists = path.exists()
        rows.append({"path": rel, "exists": exists})
        if not exists:
            missing.append(rel)
    freeze = load_json(REPO_ROOT / "reports/final_freeze/20260531_124000/FINAL_VERDICT.json")
    old_stopped = (
        freeze.get("research_freeze_complete") is True
        and freeze.get("current_full_strategy") == "FAIL"
        and freeze.get("fixed_horizon_position_lifecycle") == "STOP"
        and freeze.get("intent_lifecycle") == "STOP"
        and freeze.get("tier_c") == "BATCH_REJECTED"
    )
    audit = {
        "input_count": len(INPUTS),
        "missing_count": len(missing),
        "missing_inputs": missing,
        "final_freeze_completed": freeze.get("research_freeze_complete") is True,
        "old_strategy_lines_stopped": old_stopped,
        "new_framework_not_old_restart": True,
        "sufficient_to_design_scale_economics_model": len(missing) == 0,
    }
    return rows, audit


def build_local_support_maps() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    tierb_reclass = {
        row["pool_id"]: row
        for row in load_csv(REPO_ROOT / "reports/tierb_data_fix/20260530_125453/tier_b_targeted_reclassification_v3.csv")
    }
    tierb_trader_raw = load_csv(REPO_ROOT / "reports/tierb_data_fix/20260530_125453/tier_b_trader_concentration_fix_v3.csv")
    tierb_trader: dict[str, dict[str, Any]] = {}
    for row in tierb_trader_raw:
        if row.get("window") != "24h":
            continue
        tierb_trader[row["pool_id"]] = row
    tierb_stability = {
        row["pool_id"]: row
        for row in load_csv(REPO_ROOT / "reports/tierb_data_fix/20260530_125453/tier_b_stability_fix_v3.csv")
    }
    tierc_freeze = {
        row["pool_id"]: row
        for row in load_csv(REPO_ROOT / "reports/tierc_shadow/20260529_155854/tierc_batch_final_freeze.csv")
    }
    combined = {}
    pool_ids = set(tierb_reclass) | set(tierb_trader) | set(tierb_stability) | set(tierc_freeze)
    for pool_id in pool_ids:
        combined[pool_id] = {
            "top10_holder_pct": num(tierc_freeze.get(pool_id, {}).get("top10_holder_pct"))
            if pool_id in tierc_freeze
            else num(tierb_reclass.get(pool_id, {}).get("top10_holder_pct_effective")),
            "top1_trader_share": num(tierc_freeze.get(pool_id, {}).get("top1_trader_volume_share"))
            if pool_id in tierc_freeze
            else num(tierb_trader.get(pool_id, {}).get("top1_trader_share")),
            "top5_trader_share": num(tierc_freeze.get(pool_id, {}).get("top5_trader_volume_share"))
            if pool_id in tierc_freeze
            else num(tierb_trader.get(pool_id, {}).get("top5_trader_share")),
            "buyers_24h": num(tierb_trader.get(pool_id, {}).get("buyers_24h")),
            "sellers_24h": num(tierb_trader.get(pool_id, {}).get("sellers_24h")),
            "unique_traders_24h": num(tierb_trader.get(pool_id, {}).get("unique_traders_24h")),
            "stability_status": tierc_freeze.get(pool_id, {}).get("stability_status")
            or tierb_stability.get(pool_id, {}).get("stability_status"),
            "exit_depth_status": tierc_freeze.get(pool_id, {}).get("exit_depth_status")
            or tierb_reclass.get(pool_id, {}).get("exit_depth_status"),
            "reclassification": tierb_reclass.get(pool_id, {}).get("reclassification"),
            "tierc_final_status": tierc_freeze.get(pool_id, {}).get("final_status"),
        }
    return tierb_reclass, tierb_stability, combined


def query_db() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    table_rows = ssh_psql_csv(
        """
        select t.table_name,
               coalesce(c.reltuples::bigint, 0) as row_estimate
        from information_schema.tables t
        left join pg_class c on c.relname = t.table_name
        where t.table_schema = 'public'
          and t.table_name in (
            'fee_velocity_exit_depth_counterfactual_v1',
            'fee_velocity_rule_fix_counterfactual_v1',
            'pool_regime_classifier_entry_safe_v1',
            'pool_regime_aware_short_hold_entry_safe_v1',
            'shadow_position_marks',
            'positions',
            'shadow_decision_trace'
          )
        order by t.table_name
        """
    )
    pool_rows = ssh_psql_csv(
        """
        with base as (
          select
            pool_id,
            max(token_pair) as token_pair,
            capacity_usd,
            count(*) as sample_count,
            percentile_cont(0.5) within group (order by fee_velocity_proxy) as fee_velocity_rate_med,
            percentile_cont(0.5) within group (order by fee_proxy_daily_usd) as fee_proxy_daily_usd_med,
            percentile_cont(0.5) within group (order by exit_depth_usd) as exit_depth_usd_med,
            percentile_cont(0.5) within group (order by slippage_pct) as slippage_pct_med,
            percentile_cont(0.5) within group (order by abs(price_move_15m)) as abs_price_move_15m_med,
            percentile_cont(0.5) within group (order by abs(price_move_30m)) as abs_price_move_30m_med,
            percentile_cont(0.5) within group (order by abs(price_move_1h)) as abs_price_move_1h_med,
            percentile_cont(0.5) within group (order by tvl_change_1h) as tvl_change_1h_med,
            percentile_cont(0.5) within group (order by volume_change_1h) as volume_change_1h_med,
            avg(case when data_freshness = 'fresh' then 1.0 else 0.0 end) as fresh_rate,
            avg(case when future_mark_exists then 1.0 else 0.0 end) as future_mark_rate,
            percentile_cont(0.5) within group (order by hold_to_horizon_pnl_pct) as pnl_median,
            percentile_cont(0.1) within group (order by hold_to_horizon_pnl_pct) as pnl_p10,
            percentile_cont(0.05) within group (order by hold_to_horizon_pnl_pct) as pnl_p5,
            percentile_cont(0.01) within group (order by hold_to_horizon_pnl_pct) as pnl_p1
          from fee_velocity_exit_depth_counterfactual_v1
          where run_id = '20260531_115101'
            and variant_name = 'baseline_hold_all'
            and "window" = 'recent_7d'
            and horizon = '2h'
            and proof_unit_type = 'pool_window'
            and capacity_usd in (20, 50)
            and data_quality_status = 'ok'
          group by pool_id, capacity_usd
        )
        select
          pool_id,
          max(token_pair) as token_pair,
          max(sample_count) filter (where capacity_usd = 20) as sample_count_20,
          max(sample_count) filter (where capacity_usd = 50) as sample_count_50,
          max(fee_velocity_rate_med) filter (where capacity_usd = 20) as fee_velocity_rate_20,
          max(fee_velocity_rate_med) filter (where capacity_usd = 50) as fee_velocity_rate_50,
          max(fee_proxy_daily_usd_med) filter (where capacity_usd = 20) as fee_proxy_daily_usd_20,
          max(fee_proxy_daily_usd_med) filter (where capacity_usd = 50) as fee_proxy_daily_usd_50,
          max(exit_depth_usd_med) filter (where capacity_usd = 20) as exit_depth_usd_20,
          max(exit_depth_usd_med) filter (where capacity_usd = 50) as exit_depth_usd_50,
          max(slippage_pct_med) filter (where capacity_usd = 20) as slippage_pct_20,
          max(slippage_pct_med) filter (where capacity_usd = 50) as slippage_pct_50,
          max(abs_price_move_15m_med) filter (where capacity_usd = 20) as abs_price_move_15m_med,
          max(abs_price_move_30m_med) filter (where capacity_usd = 20) as abs_price_move_30m_med,
          max(abs_price_move_1h_med) filter (where capacity_usd = 20) as abs_price_move_1h_med,
          max(tvl_change_1h_med) filter (where capacity_usd = 20) as tvl_change_1h_med,
          max(volume_change_1h_med) filter (where capacity_usd = 20) as volume_change_1h_med,
          max(fresh_rate) filter (where capacity_usd = 20) as fresh_rate,
          max(future_mark_rate) filter (where capacity_usd = 20) as future_mark_rate,
          max(pnl_median) filter (where capacity_usd = 20) as pnl_median,
          max(pnl_p10) filter (where capacity_usd = 20) as pnl_p10,
          max(pnl_p5) filter (where capacity_usd = 20) as pnl_p5,
          max(pnl_p1) filter (where capacity_usd = 20) as pnl_p1
        from base
        group by pool_id
        having coalesce(max(sample_count) filter (where capacity_usd = 20), 0) >= 5
        order by coalesce(max(sample_count) filter (where capacity_usd = 20), 0) desc, pool_id
        """
    )
    sample_rows = ssh_psql_csv(
        """
        select
          pool_id,
          token_pair,
          capacity_usd,
          fee_velocity_proxy,
          fee_proxy_daily_usd,
          exit_depth_usd,
          slippage_pct,
          fee_estimate_usd,
          exit_cost_usd,
          fee_minus_exit_cost_usd
        from fee_velocity_exit_depth_counterfactual_v1
        where run_id = '20260531_115101'
          and variant_name = 'baseline_hold_all'
          and "window" = 'recent_7d'
          and horizon = '2h'
          and capacity_usd in (20, 50)
        order by sample_start_time desc
        limit 10
        """
    )
    return table_rows, pool_rows, sample_rows


def infer_tier(exit_depth: float | None, vol: float | None, holder: float | None, top1: float | None, top5: float | None) -> str:
    if holder is not None and holder > 25:
        return "C"
    if top1 is not None and top1 > 90:
        return "C"
    if top5 is not None and top5 > 95:
        return "C"
    if exit_depth is not None and exit_depth >= 3000 and (vol is None or vol <= 1.0):
        return "A"
    return "B"


def estimate_fixed_cost(notional: int) -> float:
    if notional <= 20:
        return 0.025
    if notional <= 100:
        return 0.04
    if notional <= 500:
        return 0.08
    if notional <= 1000:
        return 0.12
    return 0.18


def estimate_capacity_limit(exit_depth_20: float | None, exit_depth_50: float | None, slip20: float | None, slip50: float | None) -> float | None:
    depth_bound = None
    if exit_depth_20 is not None or exit_depth_50 is not None:
        depth_bound = min(v for v in [exit_depth_20, exit_depth_50] if v is not None) * 0.10
    slip_bound = None
    if slip50 and slip50 > 0:
        slip_bound = 50.0 * (0.01 / slip50)
    elif slip20 and slip20 > 0:
        slip_bound = 20.0 * (0.01 / slip20)
    candidates = [v for v in [depth_bound, slip_bound] if v is not None]
    return min(candidates) if candidates else None


def score_pool(pool: dict[str, Any], support: dict[str, Any]) -> dict[str, Any]:
    fee_rate = num(pool.get("fee_velocity_rate_20")) or num(pool.get("fee_velocity_rate_50"))
    exit_depth_20 = num(pool.get("exit_depth_usd_20"))
    exit_depth_50 = num(pool.get("exit_depth_usd_50"))
    slip20 = num(pool.get("slippage_pct_20"))
    slip50 = num(pool.get("slippage_pct_50"))
    vol_1h = num(pool.get("abs_price_move_1h_med"))
    tvl_1h = num(pool.get("tvl_change_1h_med"))
    volchg_1h = num(pool.get("volume_change_1h_med"))
    fresh_rate = num(pool.get("fresh_rate"))
    pnl_p10 = num(pool.get("pnl_p10"))
    pnl_p5 = num(pool.get("pnl_p5"))
    pnl_p1 = num(pool.get("pnl_p1"))
    holder = support.get("top10_holder_pct")
    top1 = support.get("top1_trader_share")
    top5 = support.get("top5_trader_share")
    capacity_limit = estimate_capacity_limit(exit_depth_20, exit_depth_50, slip20, slip50)

    fee_velocity_score = clamp(((fee_rate or 0.0) / 0.0015) * 100.0, 0.0, 100.0)
    exit_depth_score = clamp(((capacity_limit or 0.0) / 500.0) * 100.0, 0.0, 100.0)
    slippage_score = clamp(100.0 - (((slip20 or 0.02) * 100.0) / 2.0) * 10.0, 0.0, 100.0)
    volatility_score = clamp(100.0 - ((vol_1h or 5.0) * 18.0), 0.0, 100.0)
    tvl_stability_score = clamp(100.0 - max(0.0, -(tvl_1h or -100.0)) * 2.5, 0.0, 100.0)
    volume_stability_score = clamp(100.0 - max(0.0, -(volchg_1h or -100.0)), 0.0, 100.0)
    holder_score = 40.0 if holder is None else clamp(100.0 - holder * 2.0, 0.0, 100.0)
    trader_score = 40.0 if top5 is None else clamp(100.0 - top5, 0.0, 100.0)
    freshness_score = clamp((fresh_rate or 0.0) * 100.0, 0.0, 100.0)
    tail_risk_score = clamp(100.0 + min(0.0, (pnl_p10 or -5.0) * 25.0) + min(0.0, (pnl_p1 or -10.0) * 5.0), 0.0, 100.0)

    lp_scale_score = (
        fee_velocity_score * 0.14
        + exit_depth_score * 0.18
        + slippage_score * 0.12
        + volatility_score * 0.10
        + tvl_stability_score * 0.10
        + volume_stability_score * 0.08
        + holder_score * 0.10
        + trader_score * 0.08
        + freshness_score * 0.05
        + tail_risk_score * 0.05
    )
    tier = infer_tier(max(v for v in [exit_depth_20 or 0, exit_depth_50 or 0]), vol_1h, holder, top1, top5)
    tier_fit = {"A": 80.0, "B": 70.0, "C": 40.0}[tier]
    reject_reason = []
    if holder is not None and holder > 40:
        reject_reason.append("holder_concentration_extreme")
    if top1 is not None and top1 > 90:
        reject_reason.append("top1_trader_extreme")
    if top5 is not None and top5 > 95:
        reject_reason.append("top5_trader_extreme")
    if capacity_limit is not None and capacity_limit < 20:
        reject_reason.append("capacity_limit_below_20")
    if pnl_p10 is not None and pnl_p10 < -1.0:
        reject_reason.append("tail_p10_negative")
    virtual_candidate = lp_scale_score >= 60 and not reject_reason and capacity_limit is not None and capacity_limit >= 20
    probe_candidate = False
    watch_reason = []
    if holder is None:
        watch_reason.append("holder_missing")
    if top5 is None:
        watch_reason.append("trader_concentration_missing")
    if support.get("stability_status") in {"missing", "risk_high"}:
        watch_reason.append(f"stability_{support.get('stability_status')}")
    if support.get("exit_depth_status") in {"unknown", "", None}:
        watch_reason.append("exit_depth_status_missing")
    return {
        "tier": tier,
        "tier_fit_score": tier_fit,
        "fee_velocity_score": round(fee_velocity_score, 2),
        "exit_depth_score": round(exit_depth_score, 2),
        "slippage_score": round(slippage_score, 2),
        "volatility_score": round(volatility_score, 2),
        "tvl_stability_score": round(tvl_stability_score, 2),
        "volume_stability_score": round(volume_stability_score, 2),
        "holder_concentration_score": round(holder_score, 2),
        "trader_concentration_score": round(trader_score, 2),
        "data_freshness_score": round(freshness_score, 2),
        "tail_risk_score": round(tail_risk_score, 2),
        "lp_scale_score_0_100": round(lp_scale_score, 2),
        "capacity_limit_usd": capacity_limit,
        "virtual_notional_candidate": virtual_candidate,
        "probe_candidate": probe_candidate,
        "reject_reason": ",".join(reject_reason),
        "watch_reason": ",".join(watch_reason),
    }


def slippage_rate_for_notional(notional: int, slip20: float | None, slip50: float | None) -> float | None:
    if slip20 is None and slip50 is None:
        return None
    if notional <= 20:
        return slip20 if slip20 is not None else slip50 * (20.0 / 50.0)
    if notional <= 50 and slip20 is not None and slip50 is not None:
        ratio = (notional - 20.0) / 30.0
        return slip20 + ratio * (slip50 - slip20)
    base = slip50 if slip50 is not None else slip20
    ref = 50.0 if slip50 is not None else 20.0
    exponent = 1.10
    return base * ((notional / ref) ** exponent)


def il_lvr_proxy_rate(pool: dict[str, Any]) -> float | None:
    move_1h = num(pool.get("abs_price_move_1h_med"))
    move_30m = num(pool.get("abs_price_move_30m_med"))
    if move_1h is None and move_30m is None:
        return None
    m1 = (move_1h or 0.0) / 100.0
    m30 = (move_30m or 0.0) / 100.0
    return max(0.0, m1 * 0.35 + m30 * 0.20)


def model_virtual_notional(pool: dict[str, Any], support: dict[str, Any], score: dict[str, Any]) -> list[dict[str, Any]]:
    fee_rate = num(pool.get("fee_velocity_rate_20")) or num(pool.get("fee_velocity_rate_50"))
    slip20 = num(pool.get("slippage_pct_20"))
    slip50 = num(pool.get("slippage_pct_50"))
    capacity_limit = score.get("capacity_limit_usd")
    il_rate = il_lvr_proxy_rate(pool)
    out = []
    for notional in NOTIONALS:
        fixed_cost = estimate_fixed_cost(notional)
        slip_rate = slippage_rate_for_notional(notional, slip20, slip50)
        if fee_rate is None or slip_rate is None or capacity_limit is None or il_rate is None:
            out.append(
                {
                    "pool_id": pool["pool_id"],
                    "token_pair": pool["token_pair"],
                    "virtual_notional_usd": notional,
                    "gross_fee_proxy_usd": None,
                    "il_lvr_proxy_usd": None,
                    "slippage_proxy_usd": None,
                    "fixed_cost_proxy_usd": fixed_cost,
                    "exit_cost_proxy_usd": None,
                    "net_ev_proxy_usd": None,
                    "net_ev_proxy_pct": None,
                    "break_even_notional_usd": None,
                    "capacity_limit_usd": capacity_limit,
                    "no_size_can_fix": "yes",
                    "ev_status": "DATA_INSUFFICIENT",
                    "confidence": "low",
                    "primary_blocker": "missing_core_proxy",
                }
            )
            continue
        hold_time_factor = 2.0 / 24.0
        gross_fee = notional * fee_rate * hold_time_factor
        il_lvr_cost = notional * il_rate
        slippage_cost = notional * slip_rate
        exit_cost = slippage_cost + fixed_cost
        variable_edge_rate = fee_rate * hold_time_factor - il_rate - slip_rate
        break_even = fixed_cost / variable_edge_rate if variable_edge_rate > 0 else None
        no_size_can_fix = variable_edge_rate <= 0
        net_ev = gross_fee - il_lvr_cost - slippage_cost - fixed_cost - exit_cost
        net_ev_pct = net_ev / notional if notional else None
        primary_blocker = ""
        if no_size_can_fix:
            ev_status = "NO_SIZE_CAN_FIX"
            primary_blocker = "variable_edge_non_positive"
        elif capacity_limit is not None and notional > capacity_limit:
            ev_status = "CAPACITY_FAIL"
            primary_blocker = "capacity_limit"
        elif break_even is not None and break_even > notional:
            ev_status = "BELOW_BREAK_EVEN"
            primary_blocker = "fixed_cost_above_break_even"
        elif net_ev > 0:
            ev_status = "POSITIVE_PROXY"
        else:
            ev_status = "NEGATIVE_PROXY"
            primary_blocker = "net_ev_negative"
        confidence = "medium"
        if support.get("top10_holder_pct") is None or support.get("top5_trader_share") is None:
            confidence = "low"
        if support.get("top10_holder_pct") is not None and support.get("top10_holder_pct") > 25:
            confidence = "low"
        out.append(
            {
                "pool_id": pool["pool_id"],
                "token_pair": pool["token_pair"],
                "virtual_notional_usd": notional,
                "gross_fee_proxy_usd": gross_fee,
                "il_lvr_proxy_usd": il_lvr_cost,
                "slippage_proxy_usd": slippage_cost,
                "fixed_cost_proxy_usd": fixed_cost,
                "exit_cost_proxy_usd": exit_cost,
                "net_ev_proxy_usd": net_ev,
                "net_ev_proxy_pct": net_ev_pct,
                "break_even_notional_usd": break_even,
                "capacity_limit_usd": capacity_limit,
                "no_size_can_fix": "yes" if no_size_can_fix else "no",
                "ev_status": ev_status,
                "confidence": confidence,
                "primary_blocker": primary_blocker,
            }
        )
    return out


def build_reports() -> dict[str, Any]:
    ensure_dir(REPORT_DIR)
    input_rows, input_audit = build_input_audit()
    _, _, support_map = build_local_support_maps()
    table_rows, pool_rows, sample_rows = query_db()

    fee_exit_readiness = load_csv(REPO_ROOT / "reports/fee_velocity_exit_depth/20260531_115101/fee_exit_data_readiness.csv")
    fee_exit_map = {row["feature_name"]: row for row in fee_exit_readiness}
    table_map = {row["table_name"]: int(float(row["row_estimate"])) for row in table_rows}

    scale_rows = [
        {"feature_name": "fee_velocity_data", "available": "yes" if num(fee_exit_map.get("fee_velocity_proxy", {}).get("coverage")) else "no", "source": "fee_velocity_exit_depth_counterfactual_v1", "coverage": fee_exit_map.get("fee_velocity_proxy", {}).get("coverage", ""), "confidence": "medium", "blocker": "", "can_use_for_v1": "yes", "needs_fix": "no"},
        {"feature_name": "fee_accrual_data", "available": "partial", "source": "fee_proxy_daily_usd", "coverage": fee_exit_map.get("fee_velocity_proxy", {}).get("coverage", ""), "confidence": "low", "blocker": "proxy_only_no_real_fee_accrual", "can_use_for_v1": "yes", "needs_fix": "yes"},
        {"feature_name": "exit_depth_20", "available": "yes" if num(fee_exit_map.get("exit_depth_20usd", {}).get("coverage")) else "no", "source": "fee_velocity_exit_depth_counterfactual_v1", "coverage": fee_exit_map.get("exit_depth_20usd", {}).get("coverage", ""), "confidence": "medium", "blocker": "proxy_only", "can_use_for_v1": "yes", "needs_fix": "yes"},
        {"feature_name": "exit_depth_100", "available": "partial", "source": "extrapolated_from_20_50", "coverage": "0", "confidence": "low", "blocker": "no_direct_100_quote", "can_use_for_v1": "yes", "needs_fix": "yes"},
        {"feature_name": "exit_depth_500_1000_2000", "available": "no", "source": "missing_direct_curve", "coverage": "0", "confidence": "low", "blocker": "no_direct_large_notional_depth", "can_use_for_v1": "no", "needs_fix": "yes"},
        {"feature_name": "quote_route_simulation", "available": "no", "source": "not_in_current_pipeline", "coverage": "0", "confidence": "none", "blocker": "route_api_not_materialized", "can_use_for_v1": "no", "needs_fix": "yes"},
        {"feature_name": "slippage_curve", "available": "partial", "source": "slippage_20_50_proxy", "coverage": fee_exit_map.get("slippage_20usd", {}).get("coverage", ""), "confidence": "low", "blocker": "only_small_cap_proxy_points", "can_use_for_v1": "yes", "needs_fix": "yes"},
        {"feature_name": "gas_fixed_cost_proxy", "available": "yes", "source": "research_proxy", "coverage": "1", "confidence": "low", "blocker": "proxy_not_chain_observed", "can_use_for_v1": "yes", "needs_fix": "yes"},
        {"feature_name": "il_lvr_proxy", "available": "partial", "source": "price_move_proxy", "coverage": fee_exit_map.get("price_move_1h", {}).get("coverage", fee_exit_map.get("price_move_5m", {}).get("coverage", "")), "confidence": "low", "blocker": "no_direct_lvr", "can_use_for_v1": "yes", "needs_fix": "yes"},
        {"feature_name": "price_volatility", "available": "yes", "source": "shadow_position_marks", "coverage": fee_exit_map.get("price_move_5m", {}).get("coverage", ""), "confidence": "medium", "blocker": "", "can_use_for_v1": "yes", "needs_fix": "no"},
        {"feature_name": "volume_stability", "available": "yes", "source": "shadow_position_marks", "coverage": fee_exit_map.get("volume_change_1h", {}).get("coverage", ""), "confidence": "medium", "blocker": "", "can_use_for_v1": "yes", "needs_fix": "no"},
        {"feature_name": "tvl_stability", "available": "partial", "source": "shadow_position_marks", "coverage": fee_exit_map.get("tvl_change_1h", {}).get("coverage", ""), "confidence": "medium", "blocker": "snapshot_only_partial", "can_use_for_v1": "yes", "needs_fix": "yes"},
        {"feature_name": "holder_concentration", "available": "partial", "source": "tier_b/tier_c point audits", "coverage": fmt(sum(1 for v in support_map.values() if v.get('top10_holder_pct') is not None) / max(len(support_map), 1)), "confidence": "medium", "blocker": "not_full_pool_universe", "can_use_for_v1": "yes", "needs_fix": "yes"},
        {"feature_name": "trader_concentration", "available": "partial", "source": "tier_b/tier_c point audits", "coverage": fmt(sum(1 for v in support_map.values() if v.get('top5_trader_share') is not None) / max(len(support_map), 1)), "confidence": "medium", "blocker": "not_full_pool_universe", "can_use_for_v1": "yes", "needs_fix": "yes"},
        {"feature_name": "data_freshness", "available": "yes", "source": "fee_velocity_exit_depth_counterfactual_v1", "coverage": fee_exit_map.get("data_freshness", {}).get("coverage", "1"), "confidence": "medium", "blocker": "", "can_use_for_v1": "yes", "needs_fix": "no"},
        {"feature_name": "pool_marks", "available": "yes", "source": "shadow_position_marks", "coverage": "1", "confidence": "high", "blocker": "", "can_use_for_v1": "yes", "needs_fix": "no"},
        {"feature_name": "entry_safe_timestamps", "available": "yes", "source": "pool_regime_classifier_entry_safe_v1", "coverage": "1", "confidence": "high", "blocker": "", "can_use_for_v1": "yes", "needs_fix": "no"},
    ]

    scored_pools = []
    virtual_rows = []
    for pool in pool_rows:
        support = support_map.get(pool["pool_id"], {})
        score = score_pool(pool, support)
        row = {
            "pool_id": pool["pool_id"],
            "token_pair": pool["token_pair"],
            "inferred_tier": score["tier"],
            "lp_scale_score": score["lp_scale_score_0_100"],
            "tier_fit_score": score["tier_fit_score"],
            "fee_velocity_score": score["fee_velocity_score"],
            "exit_depth_score": score["exit_depth_score"],
            "slippage_score": score["slippage_score"],
            "volatility_score": score["volatility_score"],
            "tvl_stability_score": score["tvl_stability_score"],
            "volume_stability_score": score["volume_stability_score"],
            "holder_concentration_score": score["holder_concentration_score"],
            "trader_concentration_score": score["trader_concentration_score"],
            "data_freshness_score": score["data_freshness_score"],
            "tail_risk_score": score["tail_risk_score"],
            "candidate_for_virtual_20": "yes" if score["virtual_notional_candidate"] and (score["capacity_limit_usd"] or 0) >= 20 else "no",
            "candidate_for_virtual_100": "yes" if score["virtual_notional_candidate"] and (score["capacity_limit_usd"] or 0) >= 100 else "no",
            "candidate_for_virtual_500": "yes" if score["virtual_notional_candidate"] and (score["capacity_limit_usd"] or 0) >= 500 else "no",
            "candidate_for_virtual_1000": "yes" if score["virtual_notional_candidate"] and (score["capacity_limit_usd"] or 0) >= 1000 else "no",
            "candidate_for_virtual_2000": "yes" if score["virtual_notional_candidate"] and (score["capacity_limit_usd"] or 0) >= 2000 else "no",
            "probe_candidate_10_20": "yes" if score["probe_candidate"] else "no",
            "reject_reason": score["reject_reason"],
            "watch_reason": score["watch_reason"],
        }
        scored_pools.append(row)
        virtual_rows.extend(model_virtual_notional(pool, support, score))

    feature_rows = [
        {"feature_name": "fee_velocity_score", "weight": 0.14, "higher_is_better": "yes", "notes": "short-hold fee proxy from existing research table"},
        {"feature_name": "exit_depth_score", "weight": 0.18, "higher_is_better": "yes", "notes": "capacity bound from depth/slippage proxy"},
        {"feature_name": "slippage_score", "weight": 0.12, "higher_is_better": "yes", "notes": "small-cap slippage proxy; large notional needs extrapolation"},
        {"feature_name": "volatility_score", "weight": 0.10, "higher_is_better": "yes", "notes": "abs 1h move inverse"},
        {"feature_name": "tvl_stability_score", "weight": 0.10, "higher_is_better": "yes", "notes": "1h TVL drop inverse"},
        {"feature_name": "volume_stability_score", "weight": 0.08, "higher_is_better": "yes", "notes": "1h volume collapse inverse"},
        {"feature_name": "holder_concentration_score", "weight": 0.10, "higher_is_better": "yes", "notes": "top10 holder lower is better"},
        {"feature_name": "trader_concentration_score", "weight": 0.08, "higher_is_better": "yes", "notes": "top5 trader share lower is better"},
        {"feature_name": "data_freshness_score", "weight": 0.05, "higher_is_better": "yes", "notes": "fresh mark share"},
        {"feature_name": "tail_risk_score", "weight": 0.05, "higher_is_better": "yes", "notes": "p10/p1 tail inverse"},
    ]

    candidate_pool_count = sum(
        1
        for row in scored_pools
        if "yes" in {
            row["candidate_for_virtual_20"],
            row["candidate_for_virtual_100"],
            row["candidate_for_virtual_500"],
            row["candidate_for_virtual_1000"],
            row["candidate_for_virtual_2000"],
        }
    )
    positive_proxy_count = sum(1 for row in virtual_rows if row["ev_status"] == "POSITIVE_PROXY")
    probe_candidate_count = sum(1 for row in scored_pools if row["probe_candidate_10_20"] == "yes")

    readiness_yes = sum(1 for r in scale_rows if r["available"] == "yes")
    readiness_partial = sum(1 for r in scale_rows if r["available"] == "partial")
    readiness_state = "READY" if readiness_yes >= 10 and readiness_partial <= 3 else "PARTIAL"
    can_run_probe_now = False
    recommended_next_stage = "NEW_DATA_PIPELINE_FIRST"
    if readiness_state == "READY" and candidate_pool_count > 0:
        recommended_next_stage = "LP_VIRTUAL_NOTIONAL_ECONOMICS_V1"
    if readiness_state == "PARTIAL":
        recommended_next_stage = "NEW_DATA_PIPELINE_FIRST"

    # Artifacts
    write_json(REPORT_DIR / "input_evidence_audit.json", input_audit)
    write_text(
        REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md",
        "\n".join(
            [
                "# 输入证据审计",
                "",
                f"- input_count: `{len(INPUTS)}`",
                f"- missing_count: `{input_audit['missing_count']}`",
                f"- final_freeze_completed: `{fmt(input_audit['final_freeze_completed'])}`",
                f"- old_strategy_lines_stopped: `{fmt(input_audit['old_strategy_lines_stopped'])}`",
                f"- new_framework_not_old_restart: `yes`",
                f"- sufficient_to_design_scale_economics_model: `{fmt(input_audit['sufficient_to_design_scale_economics_model'])}`",
                "",
                "## Inputs",
                *[
                    f"- `{row['path']}`: `{'yes' if row['exists'] else 'no'}`"
                    for row in input_rows
                ],
            ]
        )
        + "\n",
    )

    problem_json = {
        "old_question": "10U / 20U 小资金 LP 是否能直接正 EV",
        "new_question": "什么资金规模、退出深度、费速和 IL/LVR 组合下，LP 才可能正 EV",
        "probe_capital_role": "execution_validation_only",
        "virtual_notionals": NOTIONALS,
        "core_outputs": [
            "virtual_notional_ev",
            "break_even_notional_usd",
            "no_size_can_fix",
            "capacity_limit_usd",
            "fee_minus_cost_curve",
            "tail_risk_by_notional",
            "tier_score",
            "probe_readiness",
        ],
    }
    write_json(REPORT_DIR / "lp_scale_research_problem_definition.json", problem_json)
    write_text(
        REPORT_DIR / "LP_SCALE_RESEARCH_PROBLEM_DEFINITION_CN.md",
        "\n".join(
            [
                "# LP Scale Research Problem Definition",
                "",
                "旧问题：",
                "- 10U / 20U 小资金 LP 是否能直接正 EV？",
                "",
                "新问题：",
                "- 什么资金规模下，LP fee 能覆盖 IL/LVR、entry/exit slippage、gas/fixed cost。",
                "- 10U / 20U 真实资金只用于 probe execution，不用于收益 proof。",
                "- 20 / 100 / 500 / 1000 / 2000U 只做 virtual notional EV。",
                "- `break_even_notional_usd` 和 `capacity_limit_usd` 是主指标。",
                "- 不允许再用 10U / 20U 直接否定整个 LP 方向。",
                "",
                "核心输出：",
                *[f"- `{item}`" for item in problem_json["core_outputs"]],
            ]
        )
        + "\n",
    )

    tier_profile = {
        "Tier A": {
            "required_data": ["exit_depth", "slippage", "fee_velocity", "stability"],
            "risk_gates": ["no extreme holder concentration", "no extreme trader concentration", "capacity_limit >= 500"],
            "size_range_candidate": "500-2000",
            "expected_failure_modes": ["fee too low to clear fixed cost", "under-earning despite depth"],
            "score_weights": {"exit_depth": 0.30, "slippage": 0.20, "stability": 0.20, "fee_velocity": 0.15, "tail_risk": 0.15},
        },
        "Tier B": {
            "required_data": ["exit_depth", "fee_velocity", "price/tvl/volume stability", "trader concentration"],
            "risk_gates": ["capacity_limit >= 100", "top5_trader_share not extreme", "tail p10 not dangerous"],
            "size_range_candidate": "100-500",
            "expected_failure_modes": ["depth degrades above 100-500", "volatility wipes fee"],
            "score_weights": {"fee_velocity": 0.22, "exit_depth": 0.22, "slippage": 0.16, "stability": 0.20, "tail_risk": 0.20},
        },
        "Tier C": {
            "required_data": ["holder concentration", "trader concentration", "exit depth", "stability"],
            "risk_gates": ["top10_holder_pct <= 25", "top1_trader_share <= 90", "capacity_limit >= 20"],
            "size_range_candidate": "20-100",
            "expected_failure_modes": ["holder/trader concentration", "fragile exit depth", "tail events dominate"],
            "score_weights": {"concentration": 0.30, "exit_depth": 0.25, "slippage": 0.15, "stability": 0.15, "tail_risk": 0.15},
        },
    }
    write_json(REPORT_DIR / "tier_abc_lp_pool_profile.json", tier_profile)
    write_text(
        REPORT_DIR / "TIER_ABC_LP_POOL_PROFILE_CN.md",
        "\n".join(
            [
                "# Tier A/B/C LP Pool Profile",
                "",
                "## Tier A",
                "- high TVL / high exit depth / lower volatility / lower fee velocity / lower tail risk",
                "- suitable for larger notional",
                "- expected edge from stability and low exit cost",
                "",
                "## Tier B",
                "- medium TVL / medium-high fee velocity / acceptable exit depth / manageable volatility",
                "- likely best research target",
                "- suitable for 100U / 500U virtual notional",
                "",
                "## Tier C",
                "- low TVL or high volatility / concentration risk / fragile exit depth",
                "- only research/watch/probe, not proof of edge",
                "- only usable if exit depth, concentration and tail gates all pass",
            ]
        )
        + "\n",
    )

    score_json = {
        "score_dimensions": [row["feature_name"] for row in feature_rows],
        "lp_scale_score_0_100": "weighted_sum",
        "tier_fit_score": "tier-based fit overlay",
        "probe_candidate": "manual policy gate only",
        "virtual_notional_candidate": "score >= 60 and no hard reject and capacity >= 20",
    }
    write_json(REPORT_DIR / "lp_pool_scoring_system_v1.json", score_json)
    write_csv(REPORT_DIR / "lp_pool_score_features.csv", feature_rows, list(feature_rows[0].keys()))
    write_text(
        REPORT_DIR / "LP_POOL_SCORING_SYSTEM_V1_CN.md",
        "\n".join(
            [
                "# LP Pool Scoring System V1",
                "",
                "- `lp_scale_score_0_100` = weighted sum of fee, depth, slippage, volatility, TVL, volume, concentration, freshness, tail risk.",
                "- `tier_fit_score` = pool scale fit overlay for Tier A/B/C.",
                "- `probe_candidate` = policy flag only, not permission to trade.",
                "- `virtual_notional_candidate` = only means pool is worth dry-modeling further.",
                "",
                "评分维度：",
                *[f"- `{row['feature_name']}` weight={row['weight']}" for row in feature_rows],
            ]
        )
        + "\n",
    )

    virtual_model = {
        "virtual_notionals": NOTIONALS,
        "gross_fee_formula": "virtual_notional * fee_velocity_rate * hold_time_factor",
        "il_lvr_cost_formula": "virtual_notional * il_lvr_proxy_rate",
        "proportional_slippage_formula": "virtual_notional * slippage_rate_for_notional",
        "fixed_cost_formula": "gas/fixed execution proxy per trade",
        "exit_cost_formula": "quote/slippage proxy + fixed cost",
        "net_ev_formula": "gross_fee - il_lvr_cost - proportional_slippage - fixed_cost - exit_cost",
        "break_even_formula": "fixed_cost / variable_edge_rate if variable_edge_rate > 0 else NO_SIZE_CAN_FIX",
        "capacity_limit_formula": "min(depth bound, slippage bound)",
        "warning": "cannot linearly scale 20U observations into 100-2000U",
    }
    write_json(REPORT_DIR / "virtual_notional_economics_model.json", virtual_model)
    write_text(
        REPORT_DIR / "VIRTUAL_NOTIONAL_ECONOMICS_MODEL_CN.md",
        "\n".join(
            [
                "# Virtual Notional Economics Model",
                "",
                "- `gross_fee_usd = virtual_notional * fee_velocity_rate * hold_time_factor`",
                "- `il_lvr_cost_usd = virtual_notional * il_lvr_proxy_rate`",
                "- `proportional_slippage_usd = virtual_notional * slippage_rate_for_notional`",
                "- `fixed_cost_usd = gas/fixed execution/routing cost proxy`",
                "- `exit_cost_usd = quote/slippage proxy + fixed cost`",
                "- `net_ev_usd = gross_fee - il_lvr_cost - proportional_slippage - fixed_cost - exit_cost`",
                "- `net_ev_pct = net_ev_usd / virtual_notional`",
                "- `break_even_notional_usd = fixed_cost / variable_edge_rate if >0 else NO_SIZE_CAN_FIX`",
                "- `capacity_limit_usd = conservative min(depth bound, slippage bound)`",
                "",
                "注意：不能把 20U 结果按线性倍数扩展到 100/500/1000/2000U。",
            ]
        )
        + "\n",
    )

    probe_policy = {
        "probe_sizes": [10, 20],
        "probe_role": "execution_path_quote_accounting_fee_observation_slippage_exit_safety_logs_only",
        "not_for_edge_proof": True,
        "manual_approval_required": True,
        "recommended_future_stage": "LP_PROBE_PREFLIGHT_10_20U_V1",
        "run_now": False,
    }
    write_json(REPORT_DIR / "probe_capital_policy.json", probe_policy)
    write_text(
        REPORT_DIR / "PROBE_CAPITAL_POLICY_CN.md",
        "\n".join(
            [
                "# Probe Capital Policy",
                "",
                "- 10U / 20U probe 只验证 execution path、quotes、accounting、fee observation、slippage estimate、exit safety、logs。",
                "- 不用于证明 edge、EV 或 canary readiness。",
                "- 本任务不执行 probe。",
                "- 未来如要做，只能进入 `LP_PROBE_PREFLIGHT_10_20U_V1`，且需要人工批准。",
            ]
        )
        + "\n",
    )

    write_csv(REPORT_DIR / "scale_economics_data_readiness.csv", scale_rows, list(scale_rows[0].keys()))
    write_text(
        REPORT_DIR / "SCALE_ECONOMICS_DATA_READINESS_CN.md",
        "\n".join(
            [
                "# Scale Economics Data Readiness",
                "",
                f"- table_count_checked: `{len(table_rows)}`",
                f"- sample_pool_rows: `{len(pool_rows)}`",
                f"- sample_value_rows: `{len(sample_rows)}`",
                f"- data_readiness: `{readiness_state}`",
                "",
                "当前结论：",
                "- fee velocity / small-cap depth / mark-based stability 已有只读代理数据。",
                "- 100U 以上 exit depth、完整 slippage curve、真实 fee accrual、route quote 仍不足。",
                "- 因此可以做 first-pass dry model，但不够进入 probe 或收益证明。",
            ]
        )
        + "\n",
    )

    write_csv(REPORT_DIR / "lp_scale_candidate_pool_audit.csv", scored_pools, list(scored_pools[0].keys()) if scored_pools else ["pool_id"])
    write_text(
        REPORT_DIR / "LP_SCALE_CANDIDATE_POOL_AUDIT_CN.md",
        "\n".join(
            [
                "# LP Scale Candidate Pool Audit",
                "",
                f"- audited_pool_count: `{len(scored_pools)}`",
                f"- candidate_pool_count: `{candidate_pool_count}`",
                f"- probe_candidate_count: `{probe_candidate_count}`",
                "",
                "判定口径：",
                "- `virtual_notional_candidate` 只表示值得继续 dry-model，不代表可以 probe 或交易。",
                "- `probe_candidate_10_20` 仍受 manual approval 和 preflight 限制；本轮保持 0。",
            ]
        )
        + "\n",
    )

    write_csv(REPORT_DIR / "virtual_notional_first_pass_results.csv", virtual_rows, list(virtual_rows[0].keys()) if virtual_rows else ["pool_id"])
    write_text(
        REPORT_DIR / "VIRTUAL_NOTIONAL_FIRST_PASS_RESULTS_CN.md",
        "\n".join(
            [
                "# Virtual Notional First-Pass Results",
                "",
                f"- tested_virtual_notionals: `{NOTIONALS}`",
                f"- positive_proxy_count: `{positive_proxy_count}`",
                f"- no_size_can_fix_count: `{sum(1 for r in virtual_rows if r['ev_status'] == 'NO_SIZE_CAN_FIX')}`",
                f"- data_insufficient_count: `{sum(1 for r in virtual_rows if r['ev_status'] == 'DATA_INSUFFICIENT')}`",
                "",
                "当前 first-pass 只使用现有 short-hold fee/depth/stability proxy，不是 live economics proof。",
            ]
        )
        + "\n",
    )

    next_stage = {
        "recommended_next_stage": recommended_next_stage,
        "reason": "current proxies support framework design but not enough direct fee/depth/route evidence for 100-2000U or probe preflight",
        "can_run_probe_now": can_run_probe_now,
        "manual_approval_required_for_probe": True,
    }
    write_json(REPORT_DIR / "lp_scale_next_stage_decision.json", next_stage)
    write_text(
        REPORT_DIR / "LP_SCALE_NEXT_STAGE_DECISION_CN.md",
        "\n".join(
            [
                "# LP Scale Next Stage Decision",
                "",
                f"- recommended_next_stage: `{recommended_next_stage}`",
                f"- can_run_probe_now: `{fmt(can_run_probe_now)}`",
                "- manual_approval_required_for_probe: `yes`",
                "",
                "理由：",
                "- 旧 LP 研究线已经冻结，本轮只是新框架。",
                "- 当前可做 virtual notional dry model，但 100U+ depth、真实 fee accrual、route quote 仍不够。",
                "- 因此优先级应回到新数据管线，而不是直接 probe 或重启旧策略。",
            ]
        )
        + "\n",
    )

    final_verdict = {
        "status": "WARN",
        "stage": "LP_SCALE_ECONOMICS_AND_PROBE_DESIGN_V1",
        "old_research_line_frozen": True,
        "new_research_question_defined": True,
        "tier_abc_profile_ready": True,
        "lp_pool_scoring_ready": True,
        "virtual_notional_model_ready": True,
        "probe_policy_ready": True,
        "tested_virtual_notionals": NOTIONALS,
        "candidate_pool_count": candidate_pool_count,
        "positive_proxy_count": positive_proxy_count,
        "probe_candidate_count": probe_candidate_count,
        "data_readiness": readiness_state,
        "can_run_probe_now": False,
        "manual_approval_required_for_probe": True,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": recommended_next_stage,
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final_verdict)
    write_text(
        REPORT_DIR / "ONEPAGE_CN.md",
        "\n".join(
            [
                "# LP Scale Economics Onepage",
                "",
                f"- stage: `{final_verdict['stage']}`",
                f"- old_research_line_frozen: `yes`",
                f"- candidate_pool_count: `{candidate_pool_count}`",
                f"- positive_proxy_count: `{positive_proxy_count}`",
                f"- probe_candidate_count: `{probe_candidate_count}`",
                f"- data_readiness: `{readiness_state}`",
                "- can_run_probe_now: `no`",
                "- manual_approval_required_for_probe: `yes`",
                f"- recommended_next_stage: `{recommended_next_stage}`",
                "- edge_proven: `no`",
                "- tiny_canary_allowed: `no`",
            ]
        )
        + "\n",
    )

    artifact_lines = [
        "# Artifact Index",
        "",
        "- `INPUT_EVIDENCE_AUDIT_CN.md`",
        "- `input_evidence_audit.json`",
        "- `LP_SCALE_RESEARCH_PROBLEM_DEFINITION_CN.md`",
        "- `lp_scale_research_problem_definition.json`",
        "- `TIER_ABC_LP_POOL_PROFILE_CN.md`",
        "- `tier_abc_lp_pool_profile.json`",
        "- `LP_POOL_SCORING_SYSTEM_V1_CN.md`",
        "- `lp_pool_scoring_system_v1.json`",
        "- `lp_pool_score_features.csv`",
        "- `VIRTUAL_NOTIONAL_ECONOMICS_MODEL_CN.md`",
        "- `virtual_notional_economics_model.json`",
        "- `PROBE_CAPITAL_POLICY_CN.md`",
        "- `probe_capital_policy.json`",
        "- `SCALE_ECONOMICS_DATA_READINESS_CN.md`",
        "- `scale_economics_data_readiness.csv`",
        "- `LP_SCALE_CANDIDATE_POOL_AUDIT_CN.md`",
        "- `lp_scale_candidate_pool_audit.csv`",
        "- `VIRTUAL_NOTIONAL_FIRST_PASS_RESULTS_CN.md`",
        "- `virtual_notional_first_pass_results.csv`",
        "- `LP_SCALE_NEXT_STAGE_DECISION_CN.md`",
        "- `lp_scale_next_stage_decision.json`",
        "- `FINAL_VERDICT.json`",
        "- `ONEPAGE_CN.md`",
        "- `lp_scale_economics_and_probe_design_v1_readonly.py`",
    ]
    write_text(REPORT_DIR / "ARTIFACT_INDEX.md", "\n".join(artifact_lines) + "\n")
    return final_verdict


if __name__ == "__main__":
    verdict = build_reports()
    print(json.dumps(verdict, ensure_ascii=False))
