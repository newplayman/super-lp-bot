#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import shlex
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values


RUN_ID = "20260531_122413"
if os.environ.get("REPO_ROOT_OVERRIDE"):
    DEFAULT_REPO_ROOT = Path(os.environ["REPO_ROOT_OVERRIDE"])
else:
    resolved = Path(__file__).resolve()
    DEFAULT_REPO_ROOT = resolved.parents[3] if len(resolved.parents) > 3 else resolved.parent
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", str(DEFAULT_REPO_ROOT)))
REPORT_DIR = Path(os.environ.get("REPORT_DIR_OVERRIDE", str(REPO_ROOT / "reports" / "fee_velocity_rule_fix" / RUN_ID)))

FEE_EXIT_DIR = REPO_ROOT / "reports" / "fee_velocity_exit_depth" / "20260531_115101"
REGIME_RULE_DIR = REPO_ROOT / "reports" / "pool_regime_rule_fix" / "20260531_113056"
REGIME_REVIEW_DIR = REPO_ROOT / "reports" / "pool_regime_aware_review" / "20260531_110005"
RISK_SIGNAL_DIR = REPO_ROOT / "reports" / "risk_signal_definition_fix" / "20260531_080614"
NEW_HYP_DIR = REPO_ROOT / "reports" / "new_strategy_hypothesis" / "20260531_071724"

SOURCE_RUN_ID = "20260531_115101"
SOURCE_TABLE = "fee_velocity_exit_depth_counterfactual_v1"
TARGET_TABLE = "fee_velocity_rule_fix_counterfactual_v1"

WINDOWS = ["recent_24h", "recent_48h", "recent_72h", "recent_7d"]
HORIZONS = ["15m", "30m", "1h", "2h"]
CAPACITIES = [10, 20, 50]
PROOF_UNITS = ["pool_window"]
LEAKAGE_RISK = "LOW"

RULE_FIX_VARIANTS = [
    {
        "variant_name": "retention_floor_30pct",
        "entry_rule": "fee/depth 软筛，目标保留率 >= 30%",
        "capacity_usd": "10/20/50",
        "hard_filters": "fresh data, mark gap <= 600s, not invalid",
        "soft_scores": "fee_velocity + exit_depth + low slippage + stable price",
        "expected_opportunity_retention": ">=30%",
        "expected_risk": "medium",
        "known_limitation": "可能仍 fee<cost",
    },
    {
        "variant_name": "retention_floor_50pct",
        "entry_rule": "更宽松的 score 保留率 >= 50%",
        "capacity_usd": "10/20/50",
        "hard_filters": "fresh data only",
        "soft_scores": "low score threshold",
        "expected_opportunity_retention": ">=50%",
        "expected_risk": "high",
        "known_limitation": "tail 可能回撤",
    },
    {
        "variant_name": "false_filter_cap_50pct",
        "entry_rule": "优先降低 false filter",
        "capacity_usd": "10/20/50",
        "hard_filters": "仅剔除 stale/极端差 depth",
        "soft_scores": "none",
        "expected_opportunity_retention": ">=50%",
        "expected_risk": "medium-high",
        "known_limitation": "fee proxy 无改善",
    },
    {
        "variant_name": "missed_profit_cap_30pct",
        "entry_rule": "尽量不误杀正收益样本",
        "capacity_usd": "10/20/50",
        "hard_filters": "轻度 depth / slippage / freshness",
        "soft_scores": "balanced score",
        "expected_opportunity_retention": ">=70%",
        "expected_risk": "medium-high",
        "known_limitation": "tail 改善可能有限",
    },
    {
        "variant_name": "fee_cost_nonnegative_median",
        "entry_rule": "只保留 fee_minus_exit_cost_median 有望非负的窗口",
        "capacity_usd": "10/20/50",
        "hard_filters": "fee velocity high, depth ok",
        "soft_scores": "fee_minus_exit_cost proxy",
        "expected_opportunity_retention": "low",
        "expected_risk": "medium",
        "known_limitation": "过筛风险高",
    },
    {
        "variant_name": "fee_cost_nonnegative_p10",
        "entry_rule": "更严格要求 fee_minus_exit_cost p10 近非负",
        "capacity_usd": "10/20/50",
        "hard_filters": "high fee velocity, low slippage",
        "soft_scores": "fee cost conservative",
        "expected_opportunity_retention": "very low",
        "expected_risk": "low",
        "known_limitation": "几乎必然过筛",
    },
    {
        "variant_name": "exit_depth_soft_10usd",
        "entry_rule": "仅要求 10 USD depth 基本可出",
        "capacity_usd": "10",
        "hard_filters": "depth_10 >= 70, fresh",
        "soft_scores": "none",
        "expected_opportunity_retention": "high",
        "expected_risk": "medium-high",
        "known_limitation": "20/50 无法继承",
    },
    {
        "variant_name": "exit_depth_soft_20usd",
        "entry_rule": "20 USD depth 可出，slippage 宽松",
        "capacity_usd": "20",
        "hard_filters": "depth_20 >= 120, slippage cap relaxed",
        "soft_scores": "none",
        "expected_opportunity_retention": "medium",
        "expected_risk": "medium-high",
        "known_limitation": "可能成本仍为负",
    },
    {
        "variant_name": "fee_velocity_rank_top30",
        "entry_rule": "fee velocity 前 30%",
        "capacity_usd": "10/20/50",
        "hard_filters": "fresh",
        "soft_scores": "rank only",
        "expected_opportunity_retention": "~30%",
        "expected_risk": "medium",
        "known_limitation": "rank 不看成本",
    },
    {
        "variant_name": "fee_velocity_rank_top50",
        "entry_rule": "fee velocity 前 50%",
        "capacity_usd": "10/20/50",
        "hard_filters": "fresh",
        "soft_scores": "rank only",
        "expected_opportunity_retention": "~50%",
        "expected_risk": "medium-high",
        "known_limitation": "tail 可能接近 baseline",
    },
    {
        "variant_name": "fee_depth_balanced_score",
        "entry_rule": "fee/depth/slippage/price 风险加权",
        "capacity_usd": "10/20/50",
        "hard_filters": "fresh, not invalid",
        "soft_scores": "balanced composite score",
        "expected_opportunity_retention": "30-60%",
        "expected_risk": "medium",
        "known_limitation": "score threshold 需调参",
    },
    {
        "variant_name": "fee_depth_tail_guard",
        "entry_rule": "只过滤最差 depth/slippage tail",
        "capacity_usd": "10/20/50",
        "hard_filters": "tail guard only",
        "soft_scores": "none",
        "expected_opportunity_retention": "high",
        "expected_risk": "medium-high",
        "known_limitation": "fee proxy 不一定改善",
    },
    {
        "variant_name": "small_cap_10usd_lenient",
        "entry_rule": "10 USD 专用宽松门槛",
        "capacity_usd": "10",
        "hard_filters": "mild depth/slippage gate",
        "soft_scores": "small-cap friendly",
        "expected_opportunity_retention": "medium-high",
        "expected_risk": "medium",
        "known_limitation": "只能说明最小仓位",
    },
    {
        "variant_name": "small_cap_20usd_lenient",
        "entry_rule": "20 USD 专用宽松门槛",
        "capacity_usd": "20",
        "hard_filters": "mild depth/slippage gate",
        "soft_scores": "small-cap friendly",
        "expected_opportunity_retention": "medium",
        "expected_risk": "medium-high",
        "known_limitation": "仍可能 fee<cost",
    },
    {
        "variant_name": "hybrid_fee_depth_plus_data_freshness",
        "entry_rule": "fee/depth 主导 + freshness 软约束",
        "capacity_usd": "10/20/50",
        "hard_filters": "not stale",
        "soft_scores": "fee-depth plus freshness penalty",
        "expected_opportunity_retention": "medium",
        "expected_risk": "medium",
        "known_limitation": "不处理 regime 风险",
    },
    {
        "variant_name": "hybrid_fee_depth_plus_regime_soft",
        "entry_rule": "fee/depth 主导 + regime soft penalty",
        "capacity_usd": "10/20/50",
        "hard_filters": "not stale",
        "soft_scores": "fee-depth score with soft regime penalty",
        "expected_opportunity_retention": "medium-low",
        "expected_risk": "medium",
        "known_limitation": "soft regime 仍可能过筛",
    },
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


def parse_num(v: Any) -> float | None:
    if v in (None, "", "null", "None"):
        return None
    try:
        return float(v)
    except Exception:
        return None


def percentile(values: list[float], p: float) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    idx = max(0, min(len(vals) - 1, int((len(vals) - 1) * p)))
    return vals[idx]


def median(values: list[float]) -> float | None:
    return percentile(values, 0.5)


def sample_sufficiency(n: int) -> str:
    if n < 30:
        return "INSUFFICIENT"
    if n < 100:
        return "EARLY"
    if n < 300:
        return "PRELIMINARY"
    return "USABLE"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        try:
            parsed = shlex.split(line, posix=True)
        except Exception:
            parsed = [line]
        normalized = parsed[0] if parsed else line
        if "=" not in normalized:
            continue
        key, value = normalized.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def bootstrap_env() -> None:
    for candidate in [REPO_ROOT / ".runtime.shadow.env", REPO_ROOT / ".env", REPO_ROOT / ".env.chain"]:
        load_env_file(candidate)


def connect_db(readonly: bool = False):
    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("missing_postgres_dsn")
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=readonly, autocommit=False)
    return conn


def q(cur, sql: str, params: tuple[Any, ...] | None = None):
    cur.execute(sql, params or ())
    return cur.fetchall()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def input_audit() -> dict[str, Any]:
    inputs = [
        FEE_EXIT_DIR / "FINAL_VERDICT.json",
        FEE_EXIT_DIR / "FEE_EXIT_COUNTERFACTUAL_REPORT_CN.md",
        FEE_EXIT_DIR / "fee_exit_counterfactual_report.csv",
        FEE_EXIT_DIR / "FEE_EXIT_BEST_VARIANT_SELECTION_CN.md",
        FEE_EXIT_DIR / "fee_exit_best_variant_selection.json",
        FEE_EXIT_DIR / "SMALL_CAPACITY_AUDIT_CN.md",
        FEE_EXIT_DIR / "small_capacity_audit.csv",
        FEE_EXIT_DIR / "FEE_EXIT_VS_REGIME_AWARE_COMPARISON_CN.md",
        FEE_EXIT_DIR / "fee_exit_vs_regime_aware_comparison.csv",
        FEE_EXIT_DIR / "FEE_EXIT_ROBUSTNESS_AUDIT_CN.md",
        FEE_EXIT_DIR / "fee_exit_robustness_audit.csv",
        FEE_EXIT_DIR / "FEE_EXIT_NEXT_STAGE_DECISION_CN.md",
        FEE_EXIT_DIR / "fee_exit_next_stage_decision.json",
        REGIME_RULE_DIR / "FINAL_VERDICT.json",
        REGIME_REVIEW_DIR / "FINAL_VERDICT.json",
        RISK_SIGNAL_DIR / "FINAL_VERDICT.json",
        NEW_HYP_DIR / "FINAL_VERDICT.json",
    ]
    rows = [{"path": str(p), "exists": p.exists()} for p in inputs]
    src = load_json(FEE_EXIT_DIR / "FINAL_VERDICT.json")
    audit = {
        "previous_stage_ok": src.get("stage") == "FEE_VELOCITY_EXIT_DEPTH_COUNTERFACTUAL_V1",
        "recommended_next_stage_ok": src.get("recommended_next_stage") == "FEE_VELOCITY_RULE_FIX",
        "retention_too_low": (src.get("opportunity_retention_rate") or 0) < 0.30,
        "false_filter_too_high": (src.get("false_filter_rate") or 0) > 0.50,
        "missed_profit_too_high": (src.get("missed_profit_rate") or 0) > 0.30,
        "fee_minus_exit_cost_negative": (src.get("fee_minus_exit_cost_median") or 0) < 0,
        "enough_to_run_rule_fix": all(r["exists"] for r in rows),
        "edge_proven": "no",
    }
    md = ["# 输入工件审计", "", "| input | exists |", "|---|---|"]
    for row in rows:
        md.append(f"| `{row['path']}` | {fmt(row['exists'])} |")
    md.extend(
        [
            "",
            f"- 上轮 stage 是否正确: `{fmt(audit['previous_stage_ok'])}`",
            f"- 上轮 recommended_next_stage 是否为 FEE_VELOCITY_RULE_FIX: `{fmt(audit['recommended_next_stage_ok'])}`",
            f"- opportunity retention 过低: `{fmt(audit['retention_too_low'])}`",
            f"- false_filter / missed_profit 过高: `{fmt(audit['false_filter_too_high'])}` / `{fmt(audit['missed_profit_too_high'])}`",
            f"- fee_minus_exit_cost 为负: `{fmt(audit['fee_minus_exit_cost_negative'])}`",
            f"- 足够执行 rule fix: `{fmt(audit['enough_to_run_rule_fix'])}`",
            "- 当前不硬判 edge。",
        ]
    )
    write_text(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", "\n".join(md) + "\n")
    write_json(REPORT_DIR / "input_artifact_audit.json", {"inputs": rows, **audit})
    if not audit["previous_stage_ok"]:
        write_text(REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md", "# Wrong Stage Blocker\n\n上轮 stage 不等于 `FEE_VELOCITY_EXIT_DEPTH_COUNTERFACTUAL_V1`。\n")
        raise SystemExit(2)
    return audit


def write_vps_db_quick_check(cur) -> dict[str, Any]:
    cur.execute("select current_database(), current_user")
    db_name, db_user = cur.fetchone()
    data = {"DSN_PRESENT": "yes", "DB_CONNECT": "ok", "DB_NAME": db_name, "DB_USER": db_user}
    md = [
        "# VPS DB Quick Check",
        "",
        f"- DSN_PRESENT: `{data['DSN_PRESENT']}`",
        f"- DB_CONNECT: `{data['DB_CONNECT']}`",
        f"- DB_NAME: `{data['DB_NAME']}`",
        f"- DB_USER: `{data['DB_USER']}`",
    ]
    write_text(REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md", "\n".join(md) + "\n")
    return data


def load_baseline_rows(cur) -> list[dict[str, Any]]:
    rows = q(
        cur,
        f"""
        select run_id, sample_id, pool_id, token_pair, proof_unit_type, "window", horizon, capacity_usd,
               sample_start_time, feature_cutoff_time, fee_velocity_proxy, fee_proxy_daily_usd, exit_depth_usd,
               slippage_pct, price_move_15m, price_move_30m, price_move_1h, tvl_change_1h, volume_change_1h,
               data_freshness, pool_mark_gap_seconds, hold_to_horizon_pnl_pct, data_quality_status, invalid_reason,
               future_mark_exists, keep_flag, fee_estimate_usd, exit_cost_usd, fee_minus_exit_cost_usd
        from {SOURCE_TABLE}
        where run_id = %s
          and variant_name = 'baseline_hold_all'
          and proof_unit_type = any(%s)
        """,
        (SOURCE_RUN_ID, PROOF_UNITS),
    )
    return [dict(r) for r in rows]


def valid_row(row: dict[str, Any]) -> bool:
    return row["data_quality_status"] != "invalid" and row["hold_to_horizon_pnl_pct"] is not None


def score_row(row: dict[str, Any], regime_soft: bool = False) -> float:
    fee_vel = parse_num(row["fee_velocity_proxy"]) or 0.0
    depth = parse_num(row["exit_depth_usd"]) or 0.0
    slip = parse_num(row["slippage_pct"]) or 1.0
    p15 = abs(parse_num(row["price_move_15m"]) or 0.0)
    p30 = abs(parse_num(row["price_move_30m"]) or 0.0)
    p1h = abs(parse_num(row["price_move_1h"]) or 0.0)
    tvl = parse_num(row["tvl_change_1h"])
    vol = parse_num(row["volume_change_1h"])
    freshness_penalty = 20.0 if row["data_freshness"] == "stale" else 0.0
    instability_penalty = p15 * 12.0 + p30 * 8.0 + p1h * 5.0
    if tvl is not None and tvl < 0:
        instability_penalty += min(40.0, abs(tvl) * 1.2)
    if vol is not None and vol < 0:
        instability_penalty += min(30.0, abs(vol) * 0.5)
    score = fee_vel * 50000.0 + min(80.0, depth / 8.0) - min(70.0, slip * 2000.0) - freshness_penalty - instability_penalty
    if regime_soft:
        if row["data_freshness"] == "stale":
            score -= 10.0
        if (parse_num(row["price_move_1h"]) or 0) < -2.0:
            score -= 8.0
    return score


def compute_thresholds(rows: list[dict[str, Any]]) -> dict[tuple[str, str, int], dict[str, float]]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["window"], row["horizon"], row["capacity_usd"])].append(row)
    thresholds = {}
    for key, bucket in grouped.items():
        fee_vals = sorted(parse_num(r["fee_velocity_proxy"]) or 0.0 for r in bucket)
        score_vals = sorted(score_row(r) for r in bucket)
        def pct(vals: list[float], q: float) -> float:
            if not vals:
                return 0.0
            idx = max(0, min(len(vals) - 1, int((len(vals) - 1) * q)))
            return vals[idx]
        thresholds[key] = {
            "fee_top30": pct(fee_vals, 0.70),
            "fee_top50": pct(fee_vals, 0.50),
            "score_top70": pct(score_vals, 0.30),
            "score_top50": pct(score_vals, 0.50),
            "score_top35": pct(score_vals, 0.65),
        }
    return thresholds


def keep_rule(name: str, row: dict[str, Any], thresholds: dict[tuple[str, str, int], dict[str, float]]) -> bool:
    if row["data_quality_status"] == "invalid":
        return False
    window_key = (row["window"], row["horizon"], row["capacity_usd"])
    th = thresholds[window_key]
    fee_vel = parse_num(row["fee_velocity_proxy"]) or 0.0
    depth = parse_num(row["exit_depth_usd"]) or 0.0
    slip = parse_num(row["slippage_pct"]) or 1.0
    fee_minus = parse_num(row["fee_minus_exit_cost_usd"])
    p15 = abs(parse_num(row["price_move_15m"]) or 0.0)
    p30 = abs(parse_num(row["price_move_30m"]) or 0.0)
    p1h = abs(parse_num(row["price_move_1h"]) or 0.0)
    tvl = parse_num(row["tvl_change_1h"])
    vol = parse_num(row["volume_change_1h"])
    fresh = row["data_freshness"] != "stale" and (row["pool_mark_gap_seconds"] or 999999) <= 600
    balanced = score_row(row) >= th["score_top50"]
    loose = score_row(row) >= th["score_top35"]
    regime_soft = score_row(row, regime_soft=True) >= th["score_top50"]
    mild_stability = p15 <= 2.0 and p30 <= 3.5 and p1h <= 6.0
    strict_stability = p15 <= 1.0 and p30 <= 2.0 and p1h <= 4.0
    no_bad_drop = (tvl is None or tvl >= -20.0) and (vol is None or vol >= -40.0)
    if name == "retention_floor_30pct":
        return fresh and depth >= row["capacity_usd"] * 4 and slip <= 0.020 and mild_stability
    if name == "retention_floor_50pct":
        return row["data_freshness"] != "stale" and depth >= row["capacity_usd"] * 2 and slip <= 0.030
    if name == "false_filter_cap_50pct":
        return row["data_freshness"] != "stale" and depth >= row["capacity_usd"] * 1.5
    if name == "missed_profit_cap_30pct":
        return fresh and depth >= row["capacity_usd"] * 2 and slip <= 0.025 and no_bad_drop
    if name == "fee_cost_nonnegative_median":
        return fresh and fee_minus is not None and fee_minus >= -0.005 and depth >= row["capacity_usd"] * 5 and mild_stability
    if name == "fee_cost_nonnegative_p10":
        return fresh and fee_minus is not None and fee_minus >= 0 and depth >= row["capacity_usd"] * 6 and strict_stability
    if name == "exit_depth_soft_10usd":
        return row["capacity_usd"] == 10 and fresh and depth >= 70 and slip <= 0.025
    if name == "exit_depth_soft_20usd":
        return row["capacity_usd"] == 20 and fresh and depth >= 120 and slip <= 0.035
    if name == "fee_velocity_rank_top30":
        return fresh and fee_vel >= th["fee_top30"]
    if name == "fee_velocity_rank_top50":
        return row["data_freshness"] != "stale" and fee_vel >= th["fee_top50"]
    if name == "fee_depth_balanced_score":
        return fresh and balanced
    if name == "fee_depth_tail_guard":
        return row["data_freshness"] != "stale" and depth >= row["capacity_usd"] * 2 and slip <= 0.04 and p1h <= 8.0
    if name == "small_cap_10usd_lenient":
        return row["capacity_usd"] == 10 and row["data_freshness"] != "stale" and depth >= 60 and slip <= 0.03 and no_bad_drop
    if name == "small_cap_20usd_lenient":
        return row["capacity_usd"] == 20 and row["data_freshness"] != "stale" and depth >= 100 and slip <= 0.04 and no_bad_drop
    if name == "hybrid_fee_depth_plus_data_freshness":
        return fresh and loose and depth >= row["capacity_usd"] * 2
    if name == "hybrid_fee_depth_plus_regime_soft":
        return fresh and regime_soft and depth >= row["capacity_usd"] * 2
    return False


def materialize_variants(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    thresholds = compute_thresholds(rows)
    out = []
    for row in rows:
        for variant in RULE_FIX_VARIANTS:
            keep = keep_rule(variant["variant_name"], row, thresholds)
            new_row = dict(row)
            new_row["run_id"] = RUN_ID
            new_row["variant_name"] = variant["variant_name"]
            new_row["keep_flag"] = keep
            new_row["leakage_risk"] = LEAKAGE_RISK
            out.append(new_row)
    return out


def create_table_and_insert(conn, rows: list[dict[str, Any]]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            create table if not exists {TARGET_TABLE} (
              run_id text not null,
              sample_id text not null,
              pool_id text,
              token_pair text,
              proof_unit_type text,
              "window" text,
              horizon text,
              capacity_usd integer,
              sample_start_time timestamptz,
              feature_cutoff_time timestamptz,
              fee_velocity_proxy double precision,
              fee_proxy_daily_usd double precision,
              exit_depth_usd double precision,
              slippage_pct double precision,
              price_move_15m double precision,
              price_move_30m double precision,
              price_move_1h double precision,
              tvl_change_1h double precision,
              volume_change_1h double precision,
              data_freshness text,
              pool_mark_gap_seconds integer,
              hold_to_horizon_pnl_pct double precision,
              data_quality_status text,
              invalid_reason text,
              future_mark_exists boolean,
              fee_estimate_usd double precision,
              exit_cost_usd double precision,
              fee_minus_exit_cost_usd double precision,
              variant_name text,
              keep_flag boolean,
              leakage_risk text,
              created_at timestamptz not null default now(),
              primary key (run_id, sample_id, variant_name, horizon, capacity_usd, proof_unit_type)
            )
            """
        )
        cur.execute(f"delete from {TARGET_TABLE} where run_id = %s", (RUN_ID,))
        payload = [
            (
                r["run_id"], r["sample_id"], r["pool_id"], r["token_pair"], r["proof_unit_type"], r["window"], r["horizon"],
                r["capacity_usd"], r["sample_start_time"], r["feature_cutoff_time"], r["fee_velocity_proxy"], r["fee_proxy_daily_usd"],
                r["exit_depth_usd"], r["slippage_pct"], r["price_move_15m"], r["price_move_30m"], r["price_move_1h"],
                r["tvl_change_1h"], r["volume_change_1h"], r["data_freshness"], r["pool_mark_gap_seconds"], r["hold_to_horizon_pnl_pct"],
                r["data_quality_status"], r["invalid_reason"], r["future_mark_exists"], r["fee_estimate_usd"], r["exit_cost_usd"],
                r["fee_minus_exit_cost_usd"], r["variant_name"], r["keep_flag"], r["leakage_risk"],
            )
            for r in rows
        ]
        execute_values(
            cur,
            f"""
            insert into {TARGET_TABLE} (
              run_id, sample_id, pool_id, token_pair, proof_unit_type, "window", horizon, capacity_usd,
              sample_start_time, feature_cutoff_time, fee_velocity_proxy, fee_proxy_daily_usd, exit_depth_usd, slippage_pct,
              price_move_15m, price_move_30m, price_move_1h, tvl_change_1h, volume_change_1h, data_freshness, pool_mark_gap_seconds,
              hold_to_horizon_pnl_pct, data_quality_status, invalid_reason, future_mark_exists, fee_estimate_usd, exit_cost_usd,
              fee_minus_exit_cost_usd, variant_name, keep_flag, leakage_risk
            ) values %s
            """,
            payload,
            page_size=2000,
        )
    conn.commit()


def summarize_materialization(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["variant_name"], row["window"], row["horizon"], row["capacity_usd"])].append(row)
    out = []
    for (variant, window, horizon, cap), bucket in sorted(grouped.items()):
        raw = len(bucket)
        valid = sum(1 for r in bucket if valid_row(r))
        retained = sum(1 for r in bucket if r["keep_flag"] and valid_row(r))
        invalid = raw - valid
        filtered = valid - retained
        opp = [r for r in bucket if valid_row(r) and (r["hold_to_horizon_pnl_pct"] or 0) > 0]
        kept_opp = [r for r in bucket if valid_row(r) and r["keep_flag"] and (r["hold_to_horizon_pnl_pct"] or 0) > 0]
        dq = defaultdict(int)
        leak = defaultdict(int)
        fee_cov = sum(1 for r in bucket if parse_num(r["fee_velocity_proxy"]) is not None)
        depth_cov = sum(1 for r in bucket if parse_num(r["exit_depth_usd"]) is not None)
        for r in bucket:
            dq[r["data_quality_status"]] += 1
            leak[r["leakage_risk"]] += 1
        out.append(
            {
                "variant_name": variant,
                "window": window,
                "horizon": horizon,
                "capacity_usd": cap,
                "raw_sample_count": raw,
                "valid_sample_count": valid,
                "retained_sample_count": retained,
                "filtered_out_count": filtered,
                "invalid_count": invalid,
                "opportunity_retention_rate": (len(kept_opp) / len(opp)) if opp else None,
                "data_quality_distribution": json.dumps(dq, ensure_ascii=False, sort_keys=True),
                "fee_proxy_coverage": fee_cov / raw if raw else None,
                "exit_depth_coverage": depth_cov / raw if raw else None,
                "leakage_risk_distribution": json.dumps(leak, ensure_ascii=False, sort_keys=True),
            }
        )
    return out


def summarize_counterfactual(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["variant_name"], row["window"], row["horizon"], row["capacity_usd"])].append(row)
    out = []
    diagnosis = []
    baseline_map: dict[tuple[str, str, int], dict[str, Any]] = {}
    for key, bucket in grouped.items():
        variant, window, horizon, cap = key
        valid = [r for r in bucket if valid_row(r)]
        retained = [r for r in bucket if valid_row(r) and r["keep_flag"]]
        baseline_vals = [parse_num(r["hold_to_horizon_pnl_pct"]) for r in valid]
        retained_vals = [parse_num(r["hold_to_horizon_pnl_pct"]) for r in retained]
        positive = [r for r in valid if (r["hold_to_horizon_pnl_pct"] or 0) > 0]
        kept_positive_ids = {r["sample_id"] for r in retained if (r["hold_to_horizon_pnl_pct"] or 0) > 0}
        filtered_positive = [r for r in positive if r["sample_id"] not in kept_positive_ids]
        negative = [r for r in valid if (r["hold_to_horizon_pnl_pct"] or 0) < 0]
        kept_negative = [r for r in retained if (r["hold_to_horizon_pnl_pct"] or 0) < 0]
        loss_avoidance_rate = (1 - (len(kept_negative) / len(negative))) if negative else None
        fee_vals = [parse_num(r["fee_minus_exit_cost_usd"]) for r in retained if parse_num(r["fee_minus_exit_cost_usd"]) is not None]
        total_positive = sum((r["hold_to_horizon_pnl_pct"] or 0) for r in positive)
        pool_losses = defaultdict(float)
        retained_loss_total = sum(abs(min(parse_num(r["hold_to_horizon_pnl_pct"]) or 0, 0)) for r in retained)
        for r in retained:
            pool_losses[r["pool_id"]] += abs(min(parse_num(r["hold_to_horizon_pnl_pct"]) or 0, 0))
        worst_pool = (max(pool_losses.values()) / retained_loss_total) if retained_loss_total > 0 and pool_losses else None
        row = {
            "variant_name": variant,
            "window": window,
            "horizon": horizon,
            "capacity_usd": cap,
            "baseline_sample_count": len(valid),
            "baseline_median": median(baseline_vals),
            "baseline_p10": percentile(baseline_vals, 0.10),
            "baseline_p5": percentile(baseline_vals, 0.05),
            "baseline_p1": percentile(baseline_vals, 0.01),
            "retained_sample_count": len(retained),
            "retained_median": median(retained_vals),
            "retained_p10": percentile(retained_vals, 0.10),
            "retained_p5": percentile(retained_vals, 0.05),
            "retained_p1": percentile(retained_vals, 0.01),
            "opportunity_retention_rate": (len([r for r in retained if (r["hold_to_horizon_pnl_pct"] or 0) > 0]) / len(positive)) if positive else None,
            "false_filter_rate": (len(filtered_positive) / len(positive)) if positive else None,
            "missed_profit_rate": (sum((r["hold_to_horizon_pnl_pct"] or 0) for r in filtered_positive) / total_positive) if total_positive > 0 else None,
            "loss_avoidance_rate": loss_avoidance_rate,
            "tail_improvement_p10": (percentile(retained_vals, 0.10) - percentile(baseline_vals, 0.10)) if retained_vals else None,
            "tail_improvement_p5": (percentile(retained_vals, 0.05) - percentile(baseline_vals, 0.05)) if retained_vals else None,
            "tail_improvement_p1": (percentile(retained_vals, 0.01) - percentile(baseline_vals, 0.01)) if retained_vals else None,
            "fee_minus_exit_cost_median": median(fee_vals),
            "fee_minus_exit_cost_p10": percentile(fee_vals, 0.10),
            "worst_pool_contribution": worst_pool,
            "verdict": "INSUFFICIENT",
        }
        if len(retained) >= 30:
            tail_good = (row["tail_improvement_p10"] or -999) >= 0 and (row["tail_improvement_p5"] or -999) >= 0
            fee_ok = (row["fee_minus_exit_cost_median"] or -999) >= 0
            retention_ok = (row["opportunity_retention_rate"] or 0) >= 0.30
            if tail_good and retention_ok and fee_ok:
                row["verdict"] = "PROMISING"
            elif tail_good or retention_ok:
                row["verdict"] = "WEAK"
            else:
                row["verdict"] = "BAD"
        primary_failure_reason = "unknown"
        if variant != "baseline_hold_all":
            if (row["opportunity_retention_rate"] or 0) < 0.30:
                primary_failure_reason = "over_filtering"
            elif (row["fee_minus_exit_cost_median"] or 0) < 0:
                primary_failure_reason = "fee_minus_exit_cost_negative"
            elif cap > 10 and (row["opportunity_retention_rate"] or 0) < 0.20:
                primary_failure_reason = "capacity_too_large"
            elif (row["tail_improvement_p10"] or 0) > 0 and (row["opportunity_retention_rate"] or 0) < 0.15:
                primary_failure_reason = "tail_improved_but_opportunities_lost"
            elif (row["fee_minus_exit_cost_p10"] or 0) < 0:
                primary_failure_reason = "fee_velocity_proxy_weak"
            elif cap in {20, 50}:
                primary_failure_reason = "exit_depth_rule_too_strict"
        diagnosis.append(
            {
                "variant_name": variant,
                "capacity_usd": cap,
                "window": window,
                "horizon": horizon,
                "retained_sample_count": row["retained_sample_count"],
                "opportunity_retention_rate": row["opportunity_retention_rate"],
                "false_filter_rate": row["false_filter_rate"],
                "missed_profit_rate": row["missed_profit_rate"],
                "fee_minus_exit_cost_median": row["fee_minus_exit_cost_median"],
                "fee_minus_exit_cost_p10": row["fee_minus_exit_cost_p10"],
                "tail_improvement_p10": row["tail_improvement_p10"],
                "tail_improvement_p5": row["tail_improvement_p5"],
                "tail_improvement_p1": row["tail_improvement_p1"],
                "primary_failure_reason": primary_failure_reason,
            }
        )
        out.append(row)
        if variant == "baseline_hold_all":
            baseline_map[(window, horizon, cap)] = row
    return out, diagnosis


def write_failure_diagnosis(diagnosis: list[dict[str, Any]]) -> None:
    fieldnames = [
        "variant_name", "capacity_usd", "window", "horizon", "retained_sample_count", "opportunity_retention_rate",
        "false_filter_rate", "missed_profit_rate", "fee_minus_exit_cost_median", "fee_minus_exit_cost_p10",
        "tail_improvement_p10", "tail_improvement_p5", "tail_improvement_p1", "primary_failure_reason",
    ]
    write_csv(REPORT_DIR / "fee_exit_rule_failure_diagnosis.csv", diagnosis, fieldnames)
    src = load_json(FEE_EXIT_DIR / "FINAL_VERDICT.json")
    md = [
        "# 上一轮规则失败归因",
        "",
        f"- 上一轮 best variant: `{src['best_variant_name']}` / `{src['best_capacity_usd']} USD` / `{src['best_window']}` / `{src['best_horizon']}`",
        f"- best variant 之所以胜出: 主要因为 `tail_improvement_p10/p5/p1` 最大，但 `opportunity_retention_rate={fmt(src['opportunity_retention_rate'])}`，保留率过低。",
        f"- `false_filter_rate={fmt(src['false_filter_rate'])}` 说明规则主要靠过滤掉绝大多数正收益样本来压尾。",
        f"- `missed_profit_rate={fmt(src['missed_profit_rate'])}` 接近 1，说明几乎全部正收益被误杀。",
        f"- `fee_minus_exit_cost_median={fmt(src['fee_minus_exit_cost_median'])}` 仍为负，fee proxy 无法覆盖退出成本。",
        "- 10 USD 明显优于 20/50 USD，但仍未达到 practical。",
        "- 下面表格给出每个 variant/capacity/window/horizon 的主失败原因。",
    ]
    write_text(REPORT_DIR / "FEE_EXIT_RULE_FAILURE_DIAGNOSIS_CN.md", "\n".join(md) + "\n")


def write_variants_json() -> None:
    write_json(REPORT_DIR / "fee_velocity_rule_fix_variants.json", RULE_FIX_VARIANTS)
    md = ["# Fee Velocity Rule Fix Variants", ""]
    for row in RULE_FIX_VARIANTS:
        md.append(f"- `{row['variant_name']}`: {row['entry_rule']} | cap `{row['capacity_usd']}` | limitation `{row['known_limitation']}`")
    write_text(REPORT_DIR / "FEE_VELOCITY_RULE_FIX_VARIANTS_CN.md", "\n".join(md) + "\n")


def write_materialization_docs(rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "variant_name", "window", "horizon", "capacity_usd", "raw_sample_count", "valid_sample_count", "retained_sample_count",
        "filtered_out_count", "invalid_count", "opportunity_retention_rate", "data_quality_distribution", "fee_proxy_coverage",
        "exit_depth_coverage", "leakage_risk_distribution",
    ]
    write_csv(REPORT_DIR / "fee_rule_fix_materialization_counts.csv", rows, fieldnames)
    md = ["# Fee Rule Fix Materialization", "", f"- research table: `{TARGET_TABLE}`", f"- run_id: `{RUN_ID}`"]
    write_text(REPORT_DIR / "FEE_RULE_FIX_MATERIALIZATION_CN.md", "\n".join(md) + "\n")


def write_counterfactual_report(rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "variant_name", "window", "horizon", "capacity_usd", "baseline_sample_count", "baseline_median", "baseline_p10",
        "baseline_p5", "baseline_p1", "retained_sample_count", "retained_median", "retained_p10", "retained_p5", "retained_p1",
        "opportunity_retention_rate", "false_filter_rate", "missed_profit_rate", "loss_avoidance_rate", "tail_improvement_p10",
        "tail_improvement_p5", "tail_improvement_p1", "fee_minus_exit_cost_median", "fee_minus_exit_cost_p10",
        "worst_pool_contribution", "verdict",
    ]
    write_csv(REPORT_DIR / "fee_rule_fix_counterfactual_report.csv", rows, fieldnames)
    md = ["# Fee Rule Fix Counterfactual Report", ""]
    write_text(REPORT_DIR / "FEE_RULE_FIX_COUNTERFACTUAL_REPORT_CN.md", "\n".join(md) + "\n")


def practical_gate(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    candidates = []
    for row in rows:
        pass_gate = (
            row["retained_sample_count"] >= 100
            and (row["opportunity_retention_rate"] or 0) >= 0.30
            and (row["false_filter_rate"] or 1) <= 0.50
            and (row["missed_profit_rate"] or 1) <= 0.30
            and (row["fee_minus_exit_cost_median"] or -999) >= 0
            and (row["fee_minus_exit_cost_p10"] or -999) >= -0.005
            and (row["tail_improvement_p10"] or 0) >= -0.01
            and (row["tail_improvement_p5"] or 0) >= -0.01
            and (row["tail_improvement_p1"] or 0) >= -0.05
            and (row["worst_pool_contribution"] or 0) < 0.75
        )
        candidates.append({**row, "practical_gate_pass": pass_gate})
    passing = [r for r in candidates if r["practical_gate_pass"]]
    gate = {
        "minimum_conditions": {
            "retained_sample_count": ">=100",
            "opportunity_retention_rate": ">=0.30",
            "false_filter_rate": "<=0.50",
            "missed_profit_rate": "<=0.30",
            "fee_minus_exit_cost_median": ">=0",
            "fee_minus_exit_cost_p10": "not materially negative",
            "tail": "not worse than baseline",
            "single_pool_domination": "<0.75",
        },
        "passing_variant_count": len(passing),
        "practical_gate_any_pass": bool(passing),
    }
    write_json(REPORT_DIR / "fee_rule_practicality_gate.json", gate)
    md = ["# Fee Rule Practicality Gate", "", f"- passing_variant_count: `{len(passing)}`", f"- any pass: `{fmt(bool(passing))}`"]
    write_text(REPORT_DIR / "FEE_RULE_PRACTICALITY_GATE_CN.md", "\n".join(md) + "\n")
    return gate, candidates


def select_best_practical(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [r for r in candidates if (r["opportunity_retention_rate"] or 0) >= 0.30 and (r["fee_minus_exit_cost_median"] or -999) >= 0]
    def rank_key(r: dict[str, Any]):
        return (
            r["practical_gate_pass"],
            r["opportunity_retention_rate"] or -1,
            r["tail_improvement_p10"] or -999,
            r["tail_improvement_p5"] or -999,
            r["retained_sample_count"],
        )
    best = max(eligible, key=rank_key) if eligible else {
        "variant_name": "",
        "capacity_usd": None,
        "window": "",
        "horizon": "",
        "retained_sample_count": 0,
        "opportunity_retention_rate": None,
        "false_filter_rate": None,
        "missed_profit_rate": None,
        "fee_minus_exit_cost_median": None,
        "fee_minus_exit_cost_p10": None,
        "tail_improvement_p10": None,
        "tail_improvement_p5": None,
        "tail_improvement_p1": None,
        "practical_gate_pass": False,
        "reason": "no variant reached retention>=30% and fee_minus_exit_cost>=0 simultaneously",
    }
    if best.get("variant_name"):
        best = {
            "best_practical_variant_name": best["variant_name"],
            "best_capacity_usd": best["capacity_usd"],
            "best_window": best["window"],
            "best_horizon": best["horizon"],
            "retained_sample_count": best["retained_sample_count"],
            "opportunity_retention_rate": best["opportunity_retention_rate"],
            "false_filter_rate": best["false_filter_rate"],
            "missed_profit_rate": best["missed_profit_rate"],
            "fee_minus_exit_cost_median": best["fee_minus_exit_cost_median"],
            "fee_minus_exit_cost_p10": best["fee_minus_exit_cost_p10"],
            "tail_improvement_p10": best["tail_improvement_p10"],
            "tail_improvement_p5": best["tail_improvement_p5"],
            "tail_improvement_p1": best["tail_improvement_p1"],
            "practical_gate_pass": best["practical_gate_pass"],
            "reason": "highest-ranked practical candidate",
        }
    write_json(REPORT_DIR / "fee_rule_best_practical_variant.json", best)
    md = ["# Best Practical Variant", "", f"- best_practical_variant_name: `{best.get('best_practical_variant_name', '')}`", f"- practical_gate_pass: `{fmt(best.get('practical_gate_pass'))}`", f"- reason: {best.get('reason', '')}"]
    write_text(REPORT_DIR / "FEE_RULE_BEST_PRACTICAL_VARIANT_CN.md", "\n".join(md) + "\n")
    return best


def stop_or_continue(best: dict[str, Any]) -> dict[str, Any]:
    original = load_json(FEE_EXIT_DIR / "FINAL_VERDICT.json")
    regime = load_json(REGIME_RULE_DIR / "FINAL_VERDICT.json")
    result = {
        "original_fee_exit_best": {
            "variant_name": original["best_variant_name"],
            "opportunity_retention_rate": original["opportunity_retention_rate"],
            "false_filter_rate": original["false_filter_rate"],
            "missed_profit_rate": original["missed_profit_rate"],
            "fee_minus_exit_cost_median": original["fee_minus_exit_cost_median"],
        },
        "entry_safe_regime_aware_best": {
            "opportunity_retention_rate": regime["opportunity_retention_rate"],
            "false_quarantine_rate": regime["false_quarantine_rate"],
            "missed_profit_rate": regime["missed_profit_rate"],
        },
        "rule_fix_best_practical_variant": best,
        "rule_fix_improves_opportunity_retention": bool((best.get("opportunity_retention_rate") or 0) > (original["opportunity_retention_rate"] or 0)),
        "fee_minus_exit_cost_turns_positive": bool((best.get("fee_minus_exit_cost_median") or -999) >= 0),
        "more_practical_than_regime_aware": bool((best.get("practical_gate_pass") is True) and (best.get("opportunity_retention_rate") or 0) > (regime["opportunity_retention_rate"] or 0)),
        "should_stop_p2": not bool(best.get("practical_gate_pass")),
    }
    write_json(REPORT_DIR / "fee_rule_fix_stop_or_continue.json", result)
    md = ["# Fee Rule Fix Stop Or Continue", "", f"- rule fix 是否改善机会保留: `{fmt(result['rule_fix_improves_opportunity_retention'])}`", f"- fee_minus_exit_cost 是否转正: `{fmt(result['fee_minus_exit_cost_turns_positive'])}`", f"- 是否比 regime-aware 更实用: `{fmt(result['more_practical_than_regime_aware'])}`", f"- 是否应停止 P2: `{fmt(result['should_stop_p2'])}`"]
    write_text(REPORT_DIR / "FEE_RULE_FIX_STOP_OR_CONTINUE_CN.md", "\n".join(md) + "\n")
    return result


def next_stage(best: dict[str, Any], stop_info: dict[str, Any]) -> dict[str, Any]:
    if best.get("practical_gate_pass"):
        nxt = "FEE_VELOCITY_EXIT_DEPTH_REVIEW_V2"
    elif stop_info["fee_minus_exit_cost_turns_positive"] and stop_info["rule_fix_improves_opportunity_retention"]:
        nxt = "FEE_VELOCITY_RULE_FIX_REPEAT"
    elif best.get("best_practical_variant_name") == "":
        nxt = "NEW_STRATEGY_HYPOTHESIS_DESIGN_REPEAT"
    else:
        nxt = "STOP_RESEARCH"
    decision = {
        "best_practical_variant_name": best.get("best_practical_variant_name", ""),
        "practical_gate_pass": best.get("practical_gate_pass", False),
        "recommended_next_stage": nxt,
    }
    write_json(REPORT_DIR / "fee_rule_fix_next_stage_decision.json", decision)
    md = ["# Fee Rule Fix Next Stage Decision", "", f"- best_practical_variant_name: `{decision['best_practical_variant_name']}`", f"- practical_gate_pass: `{fmt(decision['practical_gate_pass'])}`", f"- recommended_next_stage: `{decision['recommended_next_stage']}`"]
    write_text(REPORT_DIR / "FEE_RULE_FIX_NEXT_STAGE_DECISION_CN.md", "\n".join(md) + "\n")
    return decision


def write_final(best: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    verdict = {
        "status": "FAIL" if not best.get("practical_gate_pass") else "PASS",
        "stage": "FEE_VELOCITY_RULE_FIX_V1",
        "data_source": "vps_postgres",
        "db_ready": True,
        "tested_rule_fix_variant_count": len(RULE_FIX_VARIANTS),
        "best_practical_variant_name": best.get("best_practical_variant_name", ""),
        "best_capacity_usd": best.get("best_capacity_usd"),
        "best_window": best.get("best_window", ""),
        "best_horizon": best.get("best_horizon", ""),
        "retained_sample_count": best.get("retained_sample_count", 0),
        "opportunity_retention_rate": best.get("opportunity_retention_rate"),
        "false_filter_rate": best.get("false_filter_rate"),
        "missed_profit_rate": best.get("missed_profit_rate"),
        "fee_minus_exit_cost_median": best.get("fee_minus_exit_cost_median"),
        "fee_minus_exit_cost_p10": best.get("fee_minus_exit_cost_p10"),
        "tail_improved": bool((best.get("tail_improvement_p10") or 0) >= 0 and (best.get("tail_improvement_p5") or 0) >= 0),
        "tail_improvement_p10": best.get("tail_improvement_p10"),
        "tail_improvement_p5": best.get("tail_improvement_p5"),
        "tail_improvement_p1": best.get("tail_improvement_p1"),
        "practical_gate_pass": best.get("practical_gate_pass", False),
        "small_cap_capacity_status": "PASS" if best.get("best_capacity_usd") == 10 and best.get("practical_gate_pass") else "FAIL",
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": decision["recommended_next_stage"],
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
    md = ["# Onepage", "", f"- status: `{verdict['status']}`", f"- stage: `{verdict['stage']}`", f"- best practical variant: `{verdict['best_practical_variant_name']}`", f"- recommended_next_stage: `{verdict['recommended_next_stage']}`", f"- tiny_canary_allowed: `{verdict['tiny_canary_allowed']}`"]
    write_text(REPORT_DIR / "ONEPAGE_CN.md", "\n".join(md) + "\n")
    return verdict


def write_artifact_index() -> None:
    names = [
        "INPUT_ARTIFACT_AUDIT_CN.md",
        "input_artifact_audit.json",
        "VPS_DB_QUICK_CHECK_CN.md",
        "FEE_EXIT_RULE_FAILURE_DIAGNOSIS_CN.md",
        "fee_exit_rule_failure_diagnosis.csv",
        "FEE_VELOCITY_RULE_FIX_VARIANTS_CN.md",
        "fee_velocity_rule_fix_variants.json",
        "FEE_RULE_FIX_MATERIALIZATION_CN.md",
        "fee_rule_fix_materialization_counts.csv",
        "FEE_RULE_FIX_COUNTERFACTUAL_REPORT_CN.md",
        "fee_rule_fix_counterfactual_report.csv",
        "FEE_RULE_PRACTICALITY_GATE_CN.md",
        "fee_rule_practicality_gate.json",
        "FEE_RULE_BEST_PRACTICAL_VARIANT_CN.md",
        "fee_rule_best_practical_variant.json",
        "FEE_RULE_FIX_STOP_OR_CONTINUE_CN.md",
        "fee_rule_fix_stop_or_continue.json",
        "FEE_RULE_FIX_NEXT_STAGE_DECISION_CN.md",
        "fee_rule_fix_next_stage_decision.json",
        "FINAL_VERDICT.json",
        "ONEPAGE_CN.md",
    ]
    write_text(REPORT_DIR / "ARTIFACT_INDEX.md", "# Artifact Index\n\n" + "\n".join(f"- `{n}`" for n in names) + "\n")


def main() -> None:
    ensure_dir(REPORT_DIR)
    input_audit()
    write_variants_json()
    bootstrap_env()
    conn = connect_db(readonly=False)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            write_vps_db_quick_check(cur)
            baseline_rows = load_baseline_rows(cur)
        materialized = materialize_variants(baseline_rows)
        create_table_and_insert(conn, materialized)
        mat_rows = summarize_materialization(materialized)
        write_materialization_docs(mat_rows)
        counter_rows, diagnosis = summarize_counterfactual(materialized)
        write_failure_diagnosis(diagnosis)
        write_counterfactual_report(counter_rows)
        gate, candidates = practical_gate(counter_rows)
        best = select_best_practical(candidates)
        stop_info = stop_or_continue(best)
        decision = next_stage(best, stop_info)
        write_final(best, decision)
        write_artifact_index()
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
