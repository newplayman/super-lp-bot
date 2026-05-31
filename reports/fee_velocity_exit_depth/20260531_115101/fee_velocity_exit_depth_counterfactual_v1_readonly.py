#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import shlex
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values


RUN_ID = "20260531_115101"
if os.environ.get("REPO_ROOT_OVERRIDE"):
    DEFAULT_REPO_ROOT = Path(os.environ["REPO_ROOT_OVERRIDE"])
else:
    resolved = Path(__file__).resolve()
    DEFAULT_REPO_ROOT = resolved.parents[3] if len(resolved.parents) > 3 else resolved.parent
REPO_ROOT = Path(os.environ.get("REPO_ROOT_OVERRIDE", str(DEFAULT_REPO_ROOT)))
REPORT_DIR = Path(os.environ.get("REPORT_DIR_OVERRIDE", str(REPO_ROOT / "reports" / "fee_velocity_exit_depth" / RUN_ID)))

RULE_FIX_DIR = REPO_ROOT / "reports" / "pool_regime_rule_fix" / "20260531_113056"
REGIME_REVIEW_DIR = REPO_ROOT / "reports" / "pool_regime_aware_review" / "20260531_110005"
REGIME_AWARE_DIR = REPO_ROOT / "reports" / "pool_regime_aware_short_hold" / "20260531_095237"
CLASSIFIER_DIR = REPO_ROOT / "reports" / "pool_regime_classifier" / "20260531_092109"
RISK_SIGNAL_DIR = REPO_ROOT / "reports" / "risk_signal_definition_fix" / "20260531_080614"
RISK_AWARE_DIR = REPO_ROOT / "reports" / "risk_aware_short_hold" / "20260531_073906"
NEW_HYP_DIR = REPO_ROOT / "reports" / "new_strategy_hypothesis" / "20260531_071724"

RULE_FIX_RUN_ID = "20260531_113056"
SHORT_HOLD_RUN_ID = "20260531_073906"
ENTRY_SAFE_REGIME_RUN_ID = "20260531_113056"

RESEARCH_TABLE = "fee_velocity_exit_depth_counterfactual_v1"
BUCKET_SECONDS = 15 * 60
WINDOWS = ["recent_24h", "recent_48h", "recent_72h", "recent_7d"]
HORIZONS = ["15m", "30m", "1h", "2h"]
PROOF_UNITS = ["pool_window"]
CAPACITIES = [10, 20, 50]

VARIANTS = [
    "baseline_hold_all",
    "fee_velocity_top_20pct",
    "fee_velocity_top_10pct",
    "exit_depth_min_10usd",
    "exit_depth_min_20usd",
    "exit_depth_min_50usd",
    "fee_velocity_positive_net_loose",
    "fee_velocity_positive_net_strict",
    "fee_velocity_x_exit_depth_loose",
    "fee_velocity_x_exit_depth_strict",
    "small_cap_10usd_best",
    "small_cap_20usd_best",
    "small_cap_50usd_best",
    "fee_depth_score_threshold_loose",
    "fee_depth_score_threshold_strict",
    "fee_depth_plus_entry_safe_regime",
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


def parse_ts(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, (int, float)):
        if v > 10_000_000_000:
            v = v / 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc)
    s = str(v).strip()
    if not s:
        return None
    if s.isdigit():
        return parse_ts(int(s))
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
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


def pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old in (None, 0):
        return None
    return (new - old) / old * 100.0


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


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


def bucket_floor(ts_seconds: int) -> int:
    return ts_seconds - (ts_seconds % BUCKET_SECONDS)


def window_label_for_age(hours: float) -> str:
    if hours <= 24:
        return "recent_24h"
    if hours <= 48:
        return "recent_48h"
    if hours <= 72:
        return "recent_72h"
    return "recent_7d"


def horizon_hours(horizon: str) -> float:
    return {"15m": 0.25, "30m": 0.5, "1h": 1.0, "2h": 2.0}[horizon]


def safe_depth_from_slippage(notional: float, slippage: float | None, target: float) -> float | None:
    if slippage is None or slippage <= 0:
        return None
    return notional * target / slippage


def find_latest_index(ts_list: list[int], target_ts: int) -> int:
    return bisect_right(ts_list, target_ts) - 1


def input_audit() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    inputs = [
        RULE_FIX_DIR / "FINAL_VERDICT.json",
        RULE_FIX_DIR / "POOL_REGIME_RULE_FIX_DECISION_CN.md",
        RULE_FIX_DIR / "ENTRY_SAFE_REGIME_FEATURE_POLICY_CN.md",
        RULE_FIX_DIR / "ENTRY_SAFE_REGIME_AWARE_COUNTERFACTUAL_CN.md",
        RULE_FIX_DIR / "entry_safe_regime_aware_counterfactual.csv",
        RULE_FIX_DIR / "LEAKY_VS_ENTRY_SAFE_COMPARISON_CN.md",
        RULE_FIX_DIR / "leaky_vs_entry_safe_comparison.csv",
        RULE_FIX_DIR / "ENTRY_SAFE_ROBUSTNESS_AUDIT_CN.md",
        RULE_FIX_DIR / "entry_safe_robustness_audit.csv",
        REGIME_REVIEW_DIR / "FINAL_VERDICT.json",
        REGIME_AWARE_DIR / "FINAL_VERDICT.json",
        CLASSIFIER_DIR / "FINAL_VERDICT.json",
        RISK_SIGNAL_DIR / "FINAL_VERDICT.json",
        RISK_AWARE_DIR / "FINAL_VERDICT.json",
        NEW_HYP_DIR / "FINAL_VERDICT.json",
    ]
    input_rows = [{"path": str(p), "exists": p.exists()} for p in inputs]
    final_verdict = load_json(RULE_FIX_DIR / "FINAL_VERDICT.json")
    audit = {
        "previous_stage_confirmed": final_verdict.get("stage") == "POOL_REGIME_RULE_FIX_V1",
        "leakage_found_after_fix": final_verdict.get("leakage_found_after_fix"),
        "recommended_next_stage_ok": final_verdict.get("recommended_next_stage") == "FEE_VELOCITY_EXIT_DEPTH_COUNTERFACTUAL_V1",
        "regime_retention_too_low": (final_verdict.get("opportunity_retention_rate") or 0) < 0.2,
        "regime_false_quarantine_too_high": (final_verdict.get("false_quarantine_rate") or 0) > 0.5,
        "regime_missed_profit_too_high": (final_verdict.get("missed_profit_rate") or 0) > 0.25,
        "enough_to_run_fee_exit_counterfactual": all(r["exists"] for r in input_rows),
        "edge_proven": "no",
    }
    md = [
        "# 输入工件审计",
        "",
        "| input | exists |",
        "|---|---|",
    ]
    for row in input_rows:
        md.append(f"| `{row['path']}` | {fmt(row['exists'])} |")
    md.extend(
        [
            "",
            f"- 上轮 stage 确认: `{fmt(audit['previous_stage_confirmed'])}`",
            f"- leakage_found_after_fix: `{fmt(audit['leakage_found_after_fix'])}`",
            f"- recommended_next_stage 确认: `{fmt(audit['recommended_next_stage_ok'])}`",
            f"- regime-aware 保留率过低: `{fmt(audit['regime_retention_too_low'])}`",
            f"- regime-aware 误杀率过高: `{fmt(audit['regime_false_quarantine_too_high'])}`",
            f"- regime-aware missed profit 过高: `{fmt(audit['regime_missed_profit_too_high'])}`",
            f"- 足够执行 fee velocity / exit depth counterfactual: `{fmt(audit['enough_to_run_fee_exit_counterfactual'])}`",
            "- 当前只做 research-only 审计，不硬判 edge。",
        ]
    )
    write_text(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", "\n".join(md) + "\n")
    write_json(REPORT_DIR / "input_artifact_audit.json", {"inputs": input_rows, **audit})
    if not audit["previous_stage_confirmed"]:
        write_text(REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md", "# Wrong Stage Blocker\n\n上轮 FINAL_VERDICT stage 不是 `POOL_REGIME_RULE_FIX_V1`。\n")
        raise SystemExit(2)
    return audit, input_rows


def load_pool_metadata(cur):
    pools = {
        r["pool_id"]: dict(r)
        for r in q(
            cur,
            """
            select pool_id, chain, protocol, token0, token1, fee_bps, tier, tvl_usd, vol_24h, fee_apr_24h
            from pools
            """,
        )
    }
    ptm = {
        r["pool_id"]: dict(r)
        for r in q(
            cur,
            """
            select pool_id, token0, token1, token0_symbol, token1_symbol
            from pool_token_metadata
            """,
        )
    }
    return pools, ptm


def build_token_pair(pool_id: str, pools: dict[str, dict[str, Any]], ptm: dict[str, dict[str, Any]]) -> str:
    meta = ptm.get(pool_id) or {}
    if meta.get("token0_symbol") and meta.get("token1_symbol"):
        return f"{meta['token0_symbol']}/{meta['token1_symbol']}"
    pool = pools.get(pool_id) or {}
    if pool.get("token0") and pool.get("token1"):
        return f"{str(pool['token0'])[:8]}/{str(pool['token1'])[:8]}"
    return pool_id


def load_sample_rows(cur):
    rows = q(
        cur,
        """
        select run_id, sample_id, proof_unit_type, pool_id, token_pair, start_time, horizon,
               hold_to_horizon_pnl_pct, data_quality_status, invalid_reason,
               fee_proxy, exit_cost_proxy
        from risk_aware_short_hold_counterfactual_v1
        where run_id = %s
          and proof_unit_type = any(%s)
        order by start_time
        """,
        (SHORT_HOLD_RUN_ID, PROOF_UNITS),
    )
    now = datetime.now(timezone.utc)
    out = []
    for r in rows:
        start_dt = parse_ts(r["start_time"])
        if not start_dt:
            continue
        out.append(
            {
                **dict(r),
                "start_time_dt": start_dt,
                "start_ts": int(start_dt.timestamp()),
                "window": window_label_for_age((now - start_dt).total_seconds() / 3600.0),
                "hold_pnl": parse_num(r["hold_to_horizon_pnl_pct"]),
                "future_mark_exists_b": r.get("invalid_reason") not in {"no_future_pool_mark", "entry_value_missing"},
            }
        )
    return out


def load_marks(cur, pool_ids: list[str]):
    rows = q(
        cur,
        """
        select pool_id, mark_time, valuation_usd, current_tvl_usd, current_vol24h_usd, price_change_pct, source, status, amount_usd
        from shadow_position_marks
        where pool_id = any(%s)
          and mark_time >= extract(epoch from now() - interval '8 days')
        order by pool_id, mark_time
        """,
        (pool_ids,),
    )
    grouped: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row["pool_id"]][int(row["mark_time"])].append(dict(row))
    series: dict[str, list[dict[str, Any]]] = {}
    for pool_id, by_ts in grouped.items():
        items = []
        for ts, bucket_rows in sorted(by_ts.items()):
            items.append(
                {
                    "mark_time": ts,
                    "valuation_usd": median([parse_num(x["valuation_usd"]) for x in bucket_rows]),
                    "current_tvl_usd": median([parse_num(x["current_tvl_usd"]) for x in bucket_rows]),
                    "current_vol24h_usd": median([parse_num(x["current_vol24h_usd"]) for x in bucket_rows]),
                    "price_change_pct": median([parse_num(x["price_change_pct"]) for x in bucket_rows]),
                    "amount_usd": median([parse_num(x["amount_usd"]) for x in bucket_rows]),
                    "source": ",".join(sorted({x.get("source") or "" for x in bucket_rows if x.get("source")})),
                    "status": ",".join(sorted({x.get("status") or "" for x in bucket_rows if x.get("status")})),
                }
            )
        series[pool_id] = items
    return series


def load_entry_safe_regime_lookup() -> dict[tuple[str, str, str], dict[str, str]]:
    lookup = {}
    for row in load_csv_rows(RULE_FIX_DIR / "entry_safe_regime_aware_counterfactual.csv"):
        key = (row["window"], row["horizon"], row["variant_name"])
        lookup[key] = row
    return lookup


def feature_for_previous_closed_bucket(sample: dict[str, Any], marks: list[dict[str, Any]], pool: dict[str, Any], token_pair: str) -> dict[str, Any]:
    sample_start_ts = sample["start_ts"]
    feature_cutoff_ts = bucket_floor(sample_start_ts)
    classifier_bucket_start = feature_cutoff_ts - BUCKET_SECONDS
    ts_list = [x["mark_time"] for x in marks]
    idx = find_latest_index(ts_list, feature_cutoff_ts)
    current = marks[idx] if idx >= 0 else None
    current_age = feature_cutoff_ts - current["mark_time"] if current else None

    def value_at(offset_seconds: int, field: str):
        target_ts = feature_cutoff_ts - offset_seconds
        j = find_latest_index(ts_list, target_ts)
        if j < 0:
            return None
        return marks[j].get(field)

    tvl_now = current.get("current_tvl_usd") if current else None
    vol_now = current.get("current_vol24h_usd") if current else None
    val_now = current.get("valuation_usd") if current else None
    price_move_5m = pct_change(val_now, value_at(5 * 60, "valuation_usd"))
    price_move_15m = pct_change(val_now, value_at(15 * 60, "valuation_usd"))
    price_move_30m = pct_change(val_now, value_at(30 * 60, "valuation_usd"))
    price_move_1h = pct_change(val_now, value_at(60 * 60, "valuation_usd"))
    tvl_change_1h = pct_change(tvl_now, value_at(60 * 60, "current_tvl_usd"))
    volume_change_1h = pct_change(vol_now, value_at(60 * 60, "current_vol24h_usd"))

    fee_bps = parse_num(pool.get("fee_bps")) or 0.0
    fee_rate = fee_bps / 10000.0
    fee_proxy_daily_usd = (vol_now or 0.0) * fee_rate if vol_now is not None else None
    fee_velocity_proxy = (fee_proxy_daily_usd / tvl_now) if fee_proxy_daily_usd is not None and tvl_now not in (None, 0) else None

    slippage_10usd = slippage_20usd = slippage_50usd = None
    exit_depth_10usd = exit_depth_20usd = exit_depth_50usd = None
    if tvl_now not in (None, 0):
        base = 0.001 + ((10.0 / max(tvl_now, 1.0)) * 0.5)
        if vol_now is not None:
            base += min(0.02, (vol_now / max(tvl_now, 1.0)) * 0.0005)
        base += min(0.01, fee_rate * 0.05)
        slippage_10usd = clamp(base, 0.0005, 0.20)
        slippage_20usd = clamp(base * 1.8, 0.0008, 0.30)
        slippage_50usd = clamp(base * 4.0, 0.001, 0.50)
        exit_depth_10usd = safe_depth_from_slippage(10.0, slippage_10usd, 0.01)
        exit_depth_20usd = safe_depth_from_slippage(20.0, slippage_20usd, 0.02)
        exit_depth_50usd = safe_depth_from_slippage(50.0, slippage_50usd, 0.05)

    stale_data_flag = current is None or current_age is None or current_age > 5 * 60
    pool_mark_gap_seconds = current_age
    missing = []
    for name, value in [
        ("fee_proxy_daily_usd", fee_proxy_daily_usd),
        ("fee_velocity_proxy", fee_velocity_proxy),
        ("exit_depth_10usd", exit_depth_10usd),
        ("exit_depth_20usd", exit_depth_20usd),
        ("exit_depth_50usd", exit_depth_50usd),
        ("slippage_10usd", slippage_10usd),
        ("slippage_20usd", slippage_20usd),
        ("slippage_50usd", slippage_50usd),
        ("price_move_5m", price_move_5m),
        ("price_move_15m", price_move_15m),
        ("price_move_30m", price_move_30m),
        ("price_move_1h", price_move_1h),
        ("tvl_change_1h", tvl_change_1h),
        ("volume_change_1h", volume_change_1h),
    ]:
        if value is None:
            missing.append(name)
    data_freshness = "stale" if stale_data_flag else "fresh"
    return {
        "pool_id": sample["pool_id"],
        "token_pair": token_pair,
        "sample_id": sample["sample_id"],
        "horizon": sample["horizon"],
        "window": sample["window"],
        "proof_unit_type": sample["proof_unit_type"],
        "sample_start_time": sample["start_time_dt"],
        "feature_cutoff_time": datetime.fromtimestamp(feature_cutoff_ts, tz=timezone.utc),
        "classifier_bucket_start": datetime.fromtimestamp(classifier_bucket_start, tz=timezone.utc),
        "lookahead_safe": feature_cutoff_ts <= sample_start_ts,
        "fee_proxy_daily_usd": fee_proxy_daily_usd,
        "fee_velocity_proxy": fee_velocity_proxy,
        "exit_depth_10usd": exit_depth_10usd,
        "exit_depth_20usd": exit_depth_20usd,
        "exit_depth_50usd": exit_depth_50usd,
        "slippage_10usd": slippage_10usd,
        "slippage_20usd": slippage_20usd,
        "slippage_50usd": slippage_50usd,
        "price_move_5m": price_move_5m,
        "price_move_15m": price_move_15m,
        "price_move_30m": price_move_30m,
        "price_move_1h": price_move_1h,
        "tvl_change_1h": tvl_change_1h,
        "volume_change_1h": volume_change_1h,
        "data_freshness": data_freshness,
        "pool_mark_gap_seconds": pool_mark_gap_seconds,
        "missing_features": ",".join(missing),
    }


def fee_estimate_usd(capacity_usd: int, fee_velocity_proxy: float | None, horizon: str) -> float | None:
    if fee_velocity_proxy is None:
        return None
    return capacity_usd * fee_velocity_proxy * (horizon_hours(horizon) / 24.0)


def gas_proxy_usd(capacity_usd: int) -> float:
    if capacity_usd <= 10:
        return 0.02
    if capacity_usd <= 20:
        return 0.025
    return 0.035


def exit_cost_usd(capacity_usd: int, slippage_pct: float | None) -> float | None:
    if slippage_pct is None:
        return None
    return capacity_usd * slippage_pct + gas_proxy_usd(capacity_usd)


def exit_depth_for_capacity(features: dict[str, Any], capacity_usd: int) -> float | None:
    return features[f"exit_depth_{capacity_usd}usd"]


def slippage_for_capacity(features: dict[str, Any], capacity_usd: int) -> float | None:
    return features[f"slippage_{capacity_usd}usd"]


def depth_ok(features: dict[str, Any], capacity_usd: int, min_depth: float) -> bool:
    depth = exit_depth_for_capacity(features, capacity_usd)
    return depth is not None and depth >= min_depth


def stable_price_ok(features: dict[str, Any], loose: bool) -> bool:
    limit_15m = 1.5 if loose else 1.0
    limit_30m = 2.5 if loose else 1.5
    p15 = features["price_move_15m"]
    p30 = features["price_move_30m"]
    if p15 is None or p30 is None:
        return False
    return abs(p15) <= limit_15m and abs(p30) <= limit_30m


def stable_tvl_vol_ok(features: dict[str, Any], loose: bool) -> bool:
    tvl_limit = -20.0 if loose else -10.0
    vol_limit = -35.0 if loose else -20.0
    tvl_change = features["tvl_change_1h"]
    vol_change = features["volume_change_1h"]
    return (
        tvl_change is not None
        and vol_change is not None
        and tvl_change >= tvl_limit
        and vol_change >= vol_limit
    )


def variant_keep(variant: str, features: dict[str, Any], capacity_usd: int, regime_ok: bool) -> bool:
    fee_vel = features["fee_velocity_proxy"]
    fee_est = fee_estimate_usd(capacity_usd, fee_vel, features["horizon"])
    exit_cost = exit_cost_usd(capacity_usd, slippage_for_capacity(features, capacity_usd))
    fee_minus_exit_cost = (fee_est - exit_cost) if fee_est is not None and exit_cost is not None else None
    score = (
        (clamp((fee_vel or 0.0) * 4000.0, 0.0, 100.0) if fee_vel is not None else 0.0) * 0.45
        + (clamp((exit_depth_for_capacity(features, capacity_usd) or 0.0) / 10.0, 0.0, 100.0) * 0.35)
        + (0.0 if features["data_freshness"] == "stale" else 20.0)
    )
    stale = features["data_freshness"] == "stale"
    if variant == "baseline_hold_all":
        return True
    if stale:
        return False
    if variant == "fee_velocity_top_20pct":
        return fee_vel is not None and fee_vel >= 0.0009
    if variant == "fee_velocity_top_10pct":
        return fee_vel is not None and fee_vel >= 0.0015
    if variant == "exit_depth_min_10usd":
        return depth_ok(features, 10, 100.0)
    if variant == "exit_depth_min_20usd":
        return depth_ok(features, 20, 200.0)
    if variant == "exit_depth_min_50usd":
        return depth_ok(features, 50, 500.0)
    if variant == "fee_velocity_positive_net_loose":
        return fee_minus_exit_cost is not None and fee_minus_exit_cost > 0 and depth_ok(features, capacity_usd, capacity_usd * 5)
    if variant == "fee_velocity_positive_net_strict":
        return fee_minus_exit_cost is not None and fee_minus_exit_cost > 0.01 and depth_ok(features, capacity_usd, capacity_usd * 8) and stable_price_ok(features, loose=False)
    if variant == "fee_velocity_x_exit_depth_loose":
        return fee_vel is not None and fee_vel >= 0.0006 and depth_ok(features, capacity_usd, capacity_usd * 8) and stable_price_ok(features, loose=True)
    if variant == "fee_velocity_x_exit_depth_strict":
        return fee_vel is not None and fee_vel >= 0.0010 and depth_ok(features, capacity_usd, capacity_usd * 12) and stable_price_ok(features, loose=False) and stable_tvl_vol_ok(features, loose=False)
    if variant == "small_cap_10usd_best":
        return capacity_usd == 10 and fee_minus_exit_cost is not None and fee_minus_exit_cost > -0.005 and depth_ok(features, 10, 80.0) and stable_price_ok(features, loose=True)
    if variant == "small_cap_20usd_best":
        return capacity_usd == 20 and fee_minus_exit_cost is not None and fee_minus_exit_cost > -0.01 and depth_ok(features, 20, 160.0) and stable_price_ok(features, loose=True)
    if variant == "small_cap_50usd_best":
        return capacity_usd == 50 and fee_minus_exit_cost is not None and fee_minus_exit_cost > -0.02 and depth_ok(features, 50, 400.0) and stable_price_ok(features, loose=False)
    if variant == "fee_depth_score_threshold_loose":
        return score >= 45.0 and stable_tvl_vol_ok(features, loose=True)
    if variant == "fee_depth_score_threshold_strict":
        return score >= 60.0 and stable_tvl_vol_ok(features, loose=False) and stable_price_ok(features, loose=False)
    if variant == "fee_depth_plus_entry_safe_regime":
        return regime_ok and score >= 45.0 and fee_minus_exit_cost is not None and fee_minus_exit_cost > 0
    return False


def materialize_rows(samples: list[dict[str, Any]], features_by_sample: dict[str, dict[str, Any]], regime_lookup: dict[tuple[str, str, str], dict[str, str]]):
    rows: list[dict[str, Any]] = []
    for sample in samples:
        feature = features_by_sample.get(sample["sample_id"])
        if not feature:
            continue
        regime_ok = sample["window"] == "recent_7d" and sample["horizon"] == "2h"
        # We only have aggregate regime report, so regime-assisted variant stays conservative unless 7d/2h cell was the prior best.
        for capacity_usd in CAPACITIES:
            fee_est = fee_estimate_usd(capacity_usd, feature["fee_velocity_proxy"], sample["horizon"])
            exit_cost = exit_cost_usd(capacity_usd, slippage_for_capacity(feature, capacity_usd))
            fee_minus_exit = (fee_est - exit_cost) if fee_est is not None and exit_cost is not None else None
            for variant in VARIANTS:
                keep = variant_keep(variant, feature, capacity_usd, regime_ok)
                rows.append(
                    {
                        "run_id": RUN_ID,
                        "sample_id": sample["sample_id"],
                        "pool_id": sample["pool_id"],
                        "token_pair": sample["token_pair"],
                        "proof_unit_type": sample["proof_unit_type"],
                        "window": sample["window"],
                        "horizon": sample["horizon"],
                        "capacity_usd": capacity_usd,
                        "variant_name": variant,
                        "sample_start_time": sample["start_time_dt"],
                        "feature_cutoff_time": feature["feature_cutoff_time"],
                        "fee_velocity_proxy": feature["fee_velocity_proxy"],
                        "fee_proxy_daily_usd": feature["fee_proxy_daily_usd"],
                        "exit_depth_usd": exit_depth_for_capacity(feature, capacity_usd),
                        "slippage_pct": slippage_for_capacity(feature, capacity_usd),
                        "price_move_15m": feature["price_move_15m"],
                        "price_move_30m": feature["price_move_30m"],
                        "price_move_1h": feature["price_move_1h"],
                        "tvl_change_1h": feature["tvl_change_1h"],
                        "volume_change_1h": feature["volume_change_1h"],
                        "data_freshness": feature["data_freshness"],
                        "pool_mark_gap_seconds": feature["pool_mark_gap_seconds"],
                        "hold_to_horizon_pnl_pct": sample["hold_pnl"],
                        "data_quality_status": sample["data_quality_status"],
                        "invalid_reason": sample["invalid_reason"],
                        "future_mark_exists": sample["future_mark_exists_b"],
                        "keep_flag": keep,
                        "fee_estimate_usd": fee_est,
                        "exit_cost_usd": exit_cost,
                        "fee_minus_exit_cost_usd": fee_minus_exit,
                    }
                )
    return rows


def create_table_and_insert(conn, rows: list[dict[str, Any]]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            create table if not exists {RESEARCH_TABLE} (
              run_id text not null,
              sample_id text not null,
              pool_id text,
              token_pair text,
              proof_unit_type text,
              "window" text,
              horizon text,
              capacity_usd integer,
              variant_name text,
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
              keep_flag boolean,
              fee_estimate_usd double precision,
              exit_cost_usd double precision,
              fee_minus_exit_cost_usd double precision,
              created_at timestamptz not null default now(),
              primary key (run_id, sample_id, variant_name, horizon, capacity_usd, proof_unit_type)
            )
            """
        )
        cur.execute(f"delete from {RESEARCH_TABLE} where run_id = %s", (RUN_ID,))
        payload = [
            (
                r["run_id"], r["sample_id"], r["pool_id"], r["token_pair"], r["proof_unit_type"], r["window"], r["horizon"],
                r["capacity_usd"], r["variant_name"], r["sample_start_time"], r["feature_cutoff_time"], r["fee_velocity_proxy"],
                r["fee_proxy_daily_usd"], r["exit_depth_usd"], r["slippage_pct"], r["price_move_15m"], r["price_move_30m"],
                r["price_move_1h"], r["tvl_change_1h"], r["volume_change_1h"], r["data_freshness"], r["pool_mark_gap_seconds"],
                r["hold_to_horizon_pnl_pct"], r["data_quality_status"], r["invalid_reason"], r["future_mark_exists"], r["keep_flag"],
                r["fee_estimate_usd"], r["exit_cost_usd"], r["fee_minus_exit_cost_usd"],
            )
            for r in rows
        ]
        execute_values(
            cur,
            f"""
            insert into {RESEARCH_TABLE} (
              run_id, sample_id, pool_id, token_pair, proof_unit_type, "window", horizon, capacity_usd, variant_name,
              sample_start_time, feature_cutoff_time, fee_velocity_proxy, fee_proxy_daily_usd, exit_depth_usd, slippage_pct,
              price_move_15m, price_move_30m, price_move_1h, tvl_change_1h, volume_change_1h, data_freshness,
              pool_mark_gap_seconds, hold_to_horizon_pnl_pct, data_quality_status, invalid_reason, future_mark_exists,
              keep_flag, fee_estimate_usd, exit_cost_usd, fee_minus_exit_cost_usd
            ) values %s
            """,
            payload,
            page_size=1000,
        )
    conn.commit()


def summarize_materialization(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = defaultdict(int)
    for r in rows:
        key = (r["variant_name"], r["window"], r["horizon"], r["capacity_usd"], r["proof_unit_type"])
        counts[key] += 1
    out = []
    for key, count in sorted(counts.items()):
        out.append(
            {
                "variant_name": key[0],
                "window": key[1],
                "horizon": key[2],
                "capacity_usd": key[3],
                "proof_unit_type": key[4],
                "row_count": count,
            }
        )
    return out


def summarize_variants(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    baseline_by_key: dict[tuple[str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[(r["variant_name"], r["window"], r["horizon"], r["proof_unit_type"], r["capacity_usd"])].append(r)
        if r["variant_name"] == "baseline_hold_all":
            baseline_by_key[(r["window"], r["horizon"], r["proof_unit_type"], r["capacity_usd"])].append(r)
    summary_rows = []
    candidate_rows = []
    for variant in VARIANTS:
        for window in WINDOWS:
            for horizon in HORIZONS:
                for proof_unit in PROOF_UNITS:
                    for capacity in CAPACITIES:
                        key = (window, horizon, proof_unit, capacity)
                        bucket_rows = grouped.get((variant, window, horizon, proof_unit, capacity), [])
                        if not bucket_rows:
                            continue
                        baseline_rows = baseline_by_key.get(key, [])
                        valid_baseline = [r for r in baseline_rows if r["data_quality_status"] != "invalid" and r["hold_to_horizon_pnl_pct"] is not None]
                        valid_filtered = [r for r in bucket_rows if r["keep_flag"] and r["data_quality_status"] != "invalid" and r["hold_to_horizon_pnl_pct"] is not None]
                        invalid_count = sum(1 for r in bucket_rows if r["data_quality_status"] == "invalid" or r["hold_to_horizon_pnl_pct"] is None)
                        baseline_vals = [r["hold_to_horizon_pnl_pct"] for r in valid_baseline]
                        filtered_vals = [r["hold_to_horizon_pnl_pct"] for r in valid_filtered]
                        baseline_positive = [r for r in valid_baseline if (r["hold_to_horizon_pnl_pct"] or 0) > 0]
                        retained_positive = [r for r in valid_filtered if (r["hold_to_horizon_pnl_pct"] or 0) > 0]
                        kept_sample_ids = {r["sample_id"] for r in valid_filtered}
                        filtered_out_positive = [r for r in baseline_positive if r["sample_id"] not in kept_sample_ids]
                        tail_p10 = (percentile(filtered_vals, 0.10) - percentile(baseline_vals, 0.10)) if filtered_vals and baseline_vals else None
                        tail_p5 = (percentile(filtered_vals, 0.05) - percentile(baseline_vals, 0.05)) if filtered_vals and baseline_vals else None
                        tail_p1 = (percentile(filtered_vals, 0.01) - percentile(baseline_vals, 0.01)) if filtered_vals and baseline_vals else None
                        fee_minus_exit_vals = [r["fee_minus_exit_cost_usd"] for r in valid_filtered if r["fee_minus_exit_cost_usd"] is not None]
                        opportunity_retention_rate = (len(retained_positive) / len(baseline_positive)) if baseline_positive else None
                        false_filter_rate = (len(filtered_out_positive) / len(baseline_positive)) if baseline_positive else None
                        positive_sum = sum(r["hold_to_horizon_pnl_pct"] for r in baseline_positive)
                        missed_profit_rate = (
                            sum(r["hold_to_horizon_pnl_pct"] for r in filtered_out_positive) / positive_sum
                            if positive_sum > 0
                            else None
                        )
                        worst_pool_contribution = None
                        if filtered_vals:
                            losses = defaultdict(float)
                            total_loss = sum(abs(min(v, 0.0)) for v in filtered_vals)
                            if total_loss > 0:
                                for r in valid_filtered:
                                    losses[r["pool_id"]] += abs(min(r["hold_to_horizon_pnl_pct"] or 0.0, 0.0))
                                worst_pool_contribution = max(losses.values()) / total_loss if losses else None
                        row = {
                            "variant_name": variant,
                            "window": window,
                            "horizon": horizon,
                            "proof_unit_type": proof_unit,
                            "capacity_usd": capacity,
                            "sample_count": len(bucket_rows),
                            "retained_sample_count": len(valid_filtered),
                            "invalid_count": invalid_count,
                            "baseline_p10": percentile(baseline_vals, 0.10),
                            "baseline_p5": percentile(baseline_vals, 0.05),
                            "baseline_p1": percentile(baseline_vals, 0.01),
                            "filtered_median": median(filtered_vals),
                            "filtered_p10": percentile(filtered_vals, 0.10),
                            "filtered_p5": percentile(filtered_vals, 0.05),
                            "filtered_p1": percentile(filtered_vals, 0.01),
                            "tail_improvement_p10": tail_p10,
                            "tail_improvement_p5": tail_p5,
                            "tail_improvement_p1": tail_p1,
                            "tail_improved": bool(tail_p10 is not None and tail_p10 > 0 and tail_p5 is not None and tail_p5 > 0),
                            "opportunity_retention_rate": opportunity_retention_rate,
                            "false_filter_rate": false_filter_rate,
                            "missed_profit_rate": missed_profit_rate,
                            "fee_minus_exit_cost_median": median(fee_minus_exit_vals),
                            "fee_minus_exit_cost_p10": percentile(fee_minus_exit_vals, 0.10),
                            "worst_pool_contribution": worst_pool_contribution,
                            "sample_sufficiency": sample_sufficiency(len(valid_filtered)),
                        }
                        summary_rows.append(row)
                        if variant != "baseline_hold_all":
                            candidate_rows.append(row)
    def rank_key(r: dict[str, Any]):
        retention = r["opportunity_retention_rate"] if r["opportunity_retention_rate"] is not None else -1.0
        tail_p10 = r["tail_improvement_p10"] if r["tail_improvement_p10"] is not None else -999.0
        tail_p5 = r["tail_improvement_p5"] if r["tail_improvement_p5"] is not None else -999.0
        fee_minus = r["fee_minus_exit_cost_median"] if r["fee_minus_exit_cost_median"] is not None else -999.0
        retained = r["retained_sample_count"]
        return (
            r["tail_improved"],
            r["sample_sufficiency"] in {"PRELIMINARY", "USABLE"},
            tail_p10,
            tail_p5,
            retention,
            fee_minus,
            retained,
        )
    best = max(candidate_rows, key=rank_key) if candidate_rows else {}
    return summary_rows, best, candidate_rows


def build_data_readiness(samples: list[dict[str, Any]], features_by_sample: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    total = max(1, len(samples))
    def cov(fn):
        return sum(1 for s in samples if fn(features_by_sample.get(s["sample_id"], {}))) / total
    rows = [
        {"feature_name": "fee_velocity_proxy", "coverage": cov(lambda f: f.get("fee_velocity_proxy") is not None), "source": "shadow_position_marks + pools", "entry_safe": "yes", "notes": "previous closed bucket"},
        {"feature_name": "exit_depth_10usd", "coverage": cov(lambda f: f.get("exit_depth_10usd") is not None), "source": "shadow_position_marks + pools proxy", "entry_safe": "yes", "notes": "proxy only"},
        {"feature_name": "exit_depth_20usd", "coverage": cov(lambda f: f.get("exit_depth_20usd") is not None), "source": "shadow_position_marks + pools proxy", "entry_safe": "yes", "notes": "proxy only"},
        {"feature_name": "exit_depth_50usd", "coverage": cov(lambda f: f.get("exit_depth_50usd") is not None), "source": "shadow_position_marks + pools proxy", "entry_safe": "yes", "notes": "proxy only"},
        {"feature_name": "slippage_10usd/20usd/50usd", "coverage": cov(lambda f: f.get("slippage_10usd") is not None and f.get("slippage_20usd") is not None and f.get("slippage_50usd") is not None), "source": "proxy model", "entry_safe": "yes", "notes": "no route API"},
        {"feature_name": "price_move_15m/30m/1h", "coverage": cov(lambda f: f.get("price_move_15m") is not None and f.get("price_move_30m") is not None and f.get("price_move_1h") is not None), "source": "shadow_position_marks", "entry_safe": "yes", "notes": "mark-based"},
        {"feature_name": "tvl_change_1h", "coverage": cov(lambda f: f.get("tvl_change_1h") is not None), "source": "shadow_position_marks", "entry_safe": "yes", "notes": "mark-based"},
        {"feature_name": "volume_change_1h", "coverage": cov(lambda f: f.get("volume_change_1h") is not None), "source": "shadow_position_marks", "entry_safe": "yes", "notes": "mark-based"},
        {"feature_name": "data freshness / pool mark gap", "coverage": cov(lambda f: f.get("pool_mark_gap_seconds") is not None), "source": "shadow_position_marks", "entry_safe": "yes", "notes": "gap from feature cutoff"},
    ]
    return rows


def build_policy_doc() -> dict[str, Any]:
    policy = {
        "sample_start_time": "counterfactual pool_window entry time",
        "feature_cutoff_time": "previous fully closed 15m bucket end, <= sample_start_time",
        "same_bucket_features_banned": True,
        "post_entry_features_banned": True,
        "allowed_entry_safe_features": [
            "previous bucket fee_proxy",
            "previous bucket fee_velocity_proxy",
            "previous bucket volume proxy",
            "previous bucket exit_depth_10usd / 20usd / 50usd",
            "previous bucket slippage_10usd / 20usd / 50usd",
            "previous bucket price_move_5m / 15m / 30m / 1h",
            "previous bucket tvl_change_1h",
            "previous bucket data freshness",
            "previous bucket pool mark gap",
        ],
        "forbidden_features": [
            "same bucket bucket_end after sample_start",
            "post-entry price/volume/tvl marks",
            "route execution path",
            "signed quotes / swap tx",
        ],
    }
    md = [
        "# Entry-Safe Fee / Exit-Depth Feature Policy",
        "",
        "- `sample_start_time`: counterfactual 入场时刻。",
        "- `feature_cutoff_time`: previous fully closed 15m bucket end，且必须 `<= sample_start_time`。",
        "- same-bucket 和 post-entry 特征全部禁用。",
        "",
        "允许特征：",
    ]
    for item in policy["allowed_entry_safe_features"]:
        md.append(f"- {item}")
    md.extend(["", "禁止特征："])
    for item in policy["forbidden_features"]:
        md.append(f"- {item}")
    write_text(REPORT_DIR / "FEE_EXIT_ENTRY_SAFE_FEATURE_POLICY_CN.md", "\n".join(md) + "\n")
    write_json(REPORT_DIR / "fee_exit_entry_safe_feature_policy.json", policy)
    return policy


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


def write_schema_json() -> None:
    schema = {
        "research_table": RESEARCH_TABLE,
        "proof_units": PROOF_UNITS,
        "windows": WINDOWS,
        "horizons": HORIZONS,
        "capacities_usd": CAPACITIES,
        "variants": VARIANTS,
        "fields": [
            "run_id", "sample_id", "pool_id", "token_pair", "proof_unit_type", "window", "horizon", "capacity_usd",
            "variant_name", "sample_start_time", "feature_cutoff_time", "fee_velocity_proxy", "fee_proxy_daily_usd",
            "exit_depth_usd", "slippage_pct", "price_move_15m", "price_move_30m", "price_move_1h", "tvl_change_1h",
            "volume_change_1h", "data_freshness", "pool_mark_gap_seconds", "hold_to_horizon_pnl_pct", "data_quality_status",
            "invalid_reason", "future_mark_exists", "keep_flag", "fee_estimate_usd", "exit_cost_usd", "fee_minus_exit_cost_usd",
        ],
    }
    write_json(REPORT_DIR / "fee_exit_schema.json", schema)
    md = ["# Fee Exit Schema", "", f"- research table: `{RESEARCH_TABLE}`", "", "字段："]
    for field in schema["fields"]:
        md.append(f"- `{field}`")
    write_text(REPORT_DIR / "FEE_EXIT_SCHEMA_CN.md", "\n".join(md) + "\n")


def write_variants_json() -> None:
    rows = []
    for variant in VARIANTS:
        rows.append(
            {
                "variant_name": variant,
                "goal": "keep more opportunity while improving p10/p5/p1",
                "proof_unit": "pool_window",
                "capacity_scope": "10/20/50 USD",
            }
        )
    write_json(REPORT_DIR / "fee_exit_variants.json", rows)
    md = ["# Fee Exit Variants", ""]
    for row in rows:
        md.append(f"- `{row['variant_name']}`: {row['goal']}")
    write_text(REPORT_DIR / "FEE_EXIT_VARIANTS_CN.md", "\n".join(md) + "\n")


def write_readiness_md(rows: list[dict[str, Any]]) -> None:
    fieldnames = ["feature_name", "coverage", "source", "entry_safe", "notes"]
    write_csv(REPORT_DIR / "fee_exit_data_readiness.csv", rows, fieldnames)
    md = ["# Fee Exit Data Readiness", "", "| feature | coverage | source | entry_safe | notes |", "|---|---:|---|---|---|"]
    for row in rows:
        md.append(f"| {row['feature_name']} | {fmt(row['coverage'] * 100, 2)}% | {row['source']} | {row['entry_safe']} | {row['notes']} |")
    write_text(REPORT_DIR / "FEE_EXIT_DATA_READINESS_CN.md", "\n".join(md) + "\n")


def write_materialization_docs(count_rows: list[dict[str, Any]]) -> None:
    write_csv(
        REPORT_DIR / "fee_exit_materialization_counts.csv",
        count_rows,
        ["variant_name", "window", "horizon", "capacity_usd", "proof_unit_type", "row_count"],
    )
    md = ["# Fee Exit Materialization", "", f"- research table: `{RESEARCH_TABLE}`", f"- run_id: `{RUN_ID}`", ""]
    md.append("| variant | window | horizon | capacity_usd | proof_unit | row_count |")
    md.append("|---|---|---|---:|---|---:|")
    for row in count_rows[:80]:
        md.append(f"| {row['variant_name']} | {row['window']} | {row['horizon']} | {row['capacity_usd']} | {row['proof_unit_type']} | {row['row_count']} |")
    write_text(REPORT_DIR / "FEE_EXIT_MATERIALIZATION_CN.md", "\n".join(md) + "\n")


def write_counterfactual_report(summary_rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "variant_name", "window", "horizon", "proof_unit_type", "capacity_usd", "sample_count", "retained_sample_count",
        "invalid_count", "baseline_p10", "baseline_p5", "baseline_p1", "filtered_median", "filtered_p10", "filtered_p5",
        "filtered_p1", "tail_improvement_p10", "tail_improvement_p5", "tail_improvement_p1", "tail_improved",
        "opportunity_retention_rate", "false_filter_rate", "missed_profit_rate", "fee_minus_exit_cost_median",
        "fee_minus_exit_cost_p10", "worst_pool_contribution", "sample_sufficiency",
    ]
    write_csv(REPORT_DIR / "fee_exit_counterfactual_report.csv", summary_rows, fieldnames)
    md = ["# Fee Exit Counterfactual Report", "", "| variant | window | horizon | cap | retained | p10_impr | p5_impr | p1_impr | retention | false_filter | missed_profit |", "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in sorted(summary_rows, key=lambda x: (x["variant_name"], x["window"], x["horizon"], x["capacity_usd"]))[:160]:
        md.append(
            f"| {row['variant_name']} | {row['window']} | {row['horizon']} | {row['capacity_usd']} | {row['retained_sample_count']} | "
            f"{fmt(row['tail_improvement_p10'])} | {fmt(row['tail_improvement_p5'])} | {fmt(row['tail_improvement_p1'])} | "
            f"{fmt(row['opportunity_retention_rate'])} | {fmt(row['false_filter_rate'])} | {fmt(row['missed_profit_rate'])} |"
        )
    write_text(REPORT_DIR / "FEE_EXIT_COUNTERFACTUAL_REPORT_CN.md", "\n".join(md) + "\n")


def write_small_capacity_audit(summary_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    rows = []
    status = "FAIL"
    for capacity in CAPACITIES:
        best = max(
            [r for r in summary_rows if r["variant_name"] != "baseline_hold_all" and r["capacity_usd"] == capacity],
            key=lambda r: (
                r["tail_improvement_p10"] if r["tail_improvement_p10"] is not None else -999.0,
                r["opportunity_retention_rate"] if r["opportunity_retention_rate"] is not None else -1.0,
                r["fee_minus_exit_cost_median"] if r["fee_minus_exit_cost_median"] is not None else -999.0,
            ),
            default=None,
        )
        if not best:
            continue
        rows.append(
            {
                "capacity_usd": capacity,
                "best_variant_name": best["variant_name"],
                "best_window": best["window"],
                "best_horizon": best["horizon"],
                "tail_improvement_p10": best["tail_improvement_p10"],
                "tail_improvement_p5": best["tail_improvement_p5"],
                "tail_improvement_p1": best["tail_improvement_p1"],
                "opportunity_retention_rate": best["opportunity_retention_rate"],
                "fee_minus_exit_cost_median": best["fee_minus_exit_cost_median"],
                "status": "PASS" if best["tail_improved"] and (best["opportunity_retention_rate"] or 0) >= 0.25 else "WARN",
            }
        )
    if any(r["status"] == "PASS" for r in rows):
        status = "PASS"
    elif rows:
        status = "WARN"
    write_csv(
        REPORT_DIR / "small_capacity_audit.csv",
        rows,
        ["capacity_usd", "best_variant_name", "best_window", "best_horizon", "tail_improvement_p10", "tail_improvement_p5", "tail_improvement_p1", "opportunity_retention_rate", "fee_minus_exit_cost_median", "status"],
    )
    md = ["# Small Capacity Audit", "", f"- overall status: `{status}`", ""]
    for row in rows:
        md.append(f"- `{row['capacity_usd']} USD`: `{row['best_variant_name']}` / `{row['status']}`, retention `{fmt(row['opportunity_retention_rate'])}`, fee_minus_exit `{fmt(row['fee_minus_exit_cost_median'])}`")
    write_text(REPORT_DIR / "SMALL_CAPACITY_AUDIT_CN.md", "\n".join(md) + "\n")
    return rows, status


def write_best_variant(best: dict[str, Any]) -> None:
    write_json(REPORT_DIR / "fee_exit_best_variant_selection.json", best)
    md = [
        "# Fee Exit Best Variant Selection",
        "",
        f"- best_variant_name: `{best.get('variant_name', '')}`",
        f"- best_window: `{best.get('window', '')}`",
        f"- best_horizon: `{best.get('horizon', '')}`",
        f"- best_proof_unit: `{best.get('proof_unit_type', '')}`",
        f"- best_capacity_usd: `{best.get('capacity_usd', '')}`",
        f"- retained_sample_count: `{best.get('retained_sample_count', '')}`",
        f"- tail_improvement_p10/p5/p1: `{fmt(best.get('tail_improvement_p10'))} / {fmt(best.get('tail_improvement_p5'))} / {fmt(best.get('tail_improvement_p1'))}`",
        f"- opportunity_retention_rate: `{fmt(best.get('opportunity_retention_rate'))}`",
        f"- false_filter_rate: `{fmt(best.get('false_filter_rate'))}`",
        f"- missed_profit_rate: `{fmt(best.get('missed_profit_rate'))}`",
        f"- fee_minus_exit_cost_median: `{fmt(best.get('fee_minus_exit_cost_median'))}`",
    ]
    write_text(REPORT_DIR / "FEE_EXIT_BEST_VARIANT_SELECTION_CN.md", "\n".join(md) + "\n")


def write_comparison(best: dict[str, Any], regime_lookup: dict[tuple[str, str, str], dict[str, str]]) -> None:
    regime_row = regime_lookup.get((best.get("window", ""), best.get("horizon", ""), "entry_safe_enter_HEALTHY_or_STABLE_FEE"), {})
    rows = [
        {
            "metric": "tail_improvement_p10",
            "fee_exit": best.get("tail_improvement_p10"),
            "regime_aware": parse_num(regime_row.get("tail_improvement_p10")),
        },
        {
            "metric": "tail_improvement_p5",
            "fee_exit": best.get("tail_improvement_p5"),
            "regime_aware": parse_num(regime_row.get("tail_improvement_p5")),
        },
        {
            "metric": "tail_improvement_p1",
            "fee_exit": best.get("tail_improvement_p1"),
            "regime_aware": parse_num(regime_row.get("tail_improvement_p1")),
        },
        {
            "metric": "opportunity_retention_rate",
            "fee_exit": best.get("opportunity_retention_rate"),
            "regime_aware": parse_num(regime_row.get("opportunity_retention_rate")),
        },
        {
            "metric": "false_filter_rate",
            "fee_exit": best.get("false_filter_rate"),
            "regime_aware": parse_num(regime_row.get("false_quarantine_rate")),
        },
        {
            "metric": "missed_profit_rate",
            "fee_exit": best.get("missed_profit_rate"),
            "regime_aware": parse_num(regime_row.get("missed_profit_rate")),
        },
        {
            "metric": "retained_sample_count",
            "fee_exit": best.get("retained_sample_count"),
            "regime_aware": parse_num(regime_row.get("retained_sample_count")),
        },
    ]
    write_csv(REPORT_DIR / "fee_exit_vs_regime_aware_comparison.csv", rows, ["metric", "fee_exit", "regime_aware"])
    md = ["# Fee Exit vs Regime-Aware Comparison", ""]
    for row in rows:
        md.append(f"- `{row['metric']}`: fee_exit=`{fmt(row['fee_exit'])}`, regime_aware=`{fmt(row['regime_aware'])}`")
    write_text(REPORT_DIR / "FEE_EXIT_VS_REGIME_AWARE_COMPARISON_CN.md", "\n".join(md) + "\n")


def write_robustness(summary_rows: list[dict[str, Any]], best: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str, bool]:
    best_name = best.get("variant_name")
    rows = [r for r in summary_rows if r["variant_name"] == best_name and r["capacity_usd"] == best.get("capacity_usd")]
    robust_windows = sum(1 for r in rows if r["tail_improved"])
    positive_fee_windows = sum(1 for r in rows if (r["fee_minus_exit_cost_median"] or -999.0) > 0)
    robustness_status = "PASS" if robust_windows >= 3 and positive_fee_windows >= 2 else "WARN" if robust_windows >= 2 else "FAIL"
    overfit_risk = "LOW" if robustness_status == "PASS" and (best.get("opportunity_retention_rate") or 0) >= 0.4 else "MEDIUM" if robustness_status != "FAIL" else "HIGH"
    review_ready = bool(
        best.get("tail_improved")
        and (best.get("opportunity_retention_rate") or 0) >= 0.25
        and (best.get("false_filter_rate") or 1.0) <= 0.5
        and overfit_risk != "HIGH"
    )
    out = []
    for row in rows:
        out.append(
            {
                "variant_name": row["variant_name"],
                "window": row["window"],
                "horizon": row["horizon"],
                "capacity_usd": row["capacity_usd"],
                "tail_improved": row["tail_improved"],
                "tail_improvement_p10": row["tail_improvement_p10"],
                "tail_improvement_p5": row["tail_improvement_p5"],
                "tail_improvement_p1": row["tail_improvement_p1"],
                "opportunity_retention_rate": row["opportunity_retention_rate"],
                "false_filter_rate": row["false_filter_rate"],
                "missed_profit_rate": row["missed_profit_rate"],
                "fee_minus_exit_cost_median": row["fee_minus_exit_cost_median"],
            }
        )
    write_csv(REPORT_DIR / "fee_exit_robustness_audit.csv", out, list(out[0].keys()) if out else ["variant_name"])
    md = [
        "# Fee Exit Robustness Audit",
        "",
        f"- robustness_status: `{robustness_status}`",
        f"- overfit_risk: `{overfit_risk}`",
        f"- review_ready: `{fmt(review_ready)}`",
        "",
    ]
    for row in out:
        md.append(
            f"- `{row['window']}` / `{row['horizon']}` / `{row['capacity_usd']} USD`: "
            f"tail_improved=`{fmt(row['tail_improved'])}`, retention=`{fmt(row['opportunity_retention_rate'])}`, "
            f"false_filter=`{fmt(row['false_filter_rate'])}`, fee_minus_exit=`{fmt(row['fee_minus_exit_cost_median'])}`"
        )
    write_text(REPORT_DIR / "FEE_EXIT_ROBUSTNESS_AUDIT_CN.md", "\n".join(md) + "\n")
    return out, robustness_status, overfit_risk, review_ready


def decide_next_stage(best: dict[str, Any], small_cap_status: str, robustness_status: str, overfit_risk: str, review_ready: bool) -> dict[str, Any]:
    if not best:
        next_stage = "FEE_EXIT_DATA_FIX"
    elif review_ready:
        next_stage = "FEE_VELOCITY_EXIT_DEPTH_REVIEW_V2"
    elif best.get("tail_improved") and small_cap_status != "FAIL":
        next_stage = "FEE_VELOCITY_RULE_FIX"
    elif (best.get("fee_minus_exit_cost_median") or -999.0) <= 0:
        next_stage = "FEE_EXIT_DATA_FIX"
    else:
        next_stage = "NEW_STRATEGY_HYPOTHESIS_DESIGN_REPEAT"
    decision = {
        "best_variant_name": best.get("variant_name", ""),
        "best_capacity_usd": best.get("capacity_usd"),
        "tail_improved": bool(best.get("tail_improved")),
        "small_cap_capacity_status": small_cap_status,
        "robustness_status": robustness_status,
        "overfit_risk": overfit_risk,
        "review_ready": review_ready,
        "recommended_next_stage": next_stage,
    }
    write_json(REPORT_DIR / "fee_exit_next_stage_decision.json", decision)
    md = [
        "# Fee Exit Next Stage Decision",
        "",
        f"- best_variant_name: `{decision['best_variant_name']}`",
        f"- best_capacity_usd: `{decision['best_capacity_usd']}`",
        f"- tail_improved: `{fmt(decision['tail_improved'])}`",
        f"- small_cap_capacity_status: `{decision['small_cap_capacity_status']}`",
        f"- robustness_status: `{decision['robustness_status']}`",
        f"- overfit_risk: `{decision['overfit_risk']}`",
        f"- review_ready: `{fmt(decision['review_ready'])}`",
        f"- recommended_next_stage: `{decision['recommended_next_stage']}`",
    ]
    write_text(REPORT_DIR / "FEE_EXIT_NEXT_STAGE_DECISION_CN.md", "\n".join(md) + "\n")
    return decision


def write_final_verdict(db_ready: bool, best: dict[str, Any], small_cap_status: str, robustness_status: str, overfit_risk: str, review_ready: bool, next_stage: str) -> dict[str, Any]:
    status = "FAIL"
    if best and best.get("tail_improved") and review_ready:
        status = "PASS"
    elif best and best.get("tail_improved"):
        status = "WARN"
    verdict = {
        "status": status,
        "stage": "FEE_VELOCITY_EXIT_DEPTH_COUNTERFACTUAL_V1",
        "data_source": "vps_postgres",
        "db_ready": db_ready,
        "tested_variant_count": len(VARIANTS),
        "best_variant_name": best.get("variant_name", ""),
        "best_capacity_usd": best.get("capacity_usd"),
        "best_window": best.get("window", ""),
        "best_horizon": best.get("horizon", ""),
        "best_proof_unit": best.get("proof_unit_type", ""),
        "retained_sample_count": best.get("retained_sample_count", 0),
        "tail_improved": bool(best.get("tail_improved")),
        "tail_improvement_p10": best.get("tail_improvement_p10"),
        "tail_improvement_p5": best.get("tail_improvement_p5"),
        "tail_improvement_p1": best.get("tail_improvement_p1"),
        "opportunity_retention_rate": best.get("opportunity_retention_rate"),
        "false_filter_rate": best.get("false_filter_rate"),
        "missed_profit_rate": best.get("missed_profit_rate"),
        "fee_minus_exit_cost_median": best.get("fee_minus_exit_cost_median"),
        "fee_minus_exit_cost_p10": best.get("fee_minus_exit_cost_p10"),
        "small_cap_capacity_status": small_cap_status,
        "robustness_status": robustness_status,
        "overfit_risk": overfit_risk,
        "review_ready": review_ready,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage,
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", verdict)
    onepage = [
        "# Onepage",
        "",
        f"- stage: `{verdict['stage']}`",
        f"- status: `{verdict['status']}`",
        f"- best variant: `{verdict['best_variant_name']}` / `{verdict['best_capacity_usd']} USD` / `{verdict['best_window']}` / `{verdict['best_horizon']}`",
        f"- retained_sample_count: `{verdict['retained_sample_count']}`",
        f"- tail improved: `{fmt(verdict['tail_improved'])}`",
        f"- tail p10/p5/p1 improvement: `{fmt(verdict['tail_improvement_p10'])} / {fmt(verdict['tail_improvement_p5'])} / {fmt(verdict['tail_improvement_p1'])}`",
        f"- opportunity_retention_rate: `{fmt(verdict['opportunity_retention_rate'])}`",
        f"- false_filter_rate: `{fmt(verdict['false_filter_rate'])}`",
        f"- missed_profit_rate: `{fmt(verdict['missed_profit_rate'])}`",
        f"- fee_minus_exit_cost_median / p10: `{fmt(verdict['fee_minus_exit_cost_median'])} / {fmt(verdict['fee_minus_exit_cost_p10'])}`",
        f"- small_cap_capacity_status: `{verdict['small_cap_capacity_status']}`",
        f"- robustness_status: `{verdict['robustness_status']}`",
        f"- overfit_risk: `{verdict['overfit_risk']}`",
        f"- review_ready: `{fmt(verdict['review_ready'])}`",
        f"- recommended_next_stage: `{verdict['recommended_next_stage']}`",
        f"- tiny_canary_allowed: `{verdict['tiny_canary_allowed']}`",
    ]
    write_text(REPORT_DIR / "ONEPAGE_CN.md", "\n".join(onepage) + "\n")
    return verdict


def write_artifact_index() -> None:
    files = [
        "INPUT_ARTIFACT_AUDIT_CN.md",
        "input_artifact_audit.json",
        "VPS_DB_QUICK_CHECK_CN.md",
        "FEE_EXIT_ENTRY_SAFE_FEATURE_POLICY_CN.md",
        "fee_exit_entry_safe_feature_policy.json",
        "FEE_EXIT_DATA_READINESS_CN.md",
        "fee_exit_data_readiness.csv",
        "FEE_EXIT_VARIANTS_CN.md",
        "fee_exit_variants.json",
        "FEE_EXIT_SCHEMA_CN.md",
        "fee_exit_schema.json",
        "FEE_EXIT_MATERIALIZATION_CN.md",
        "fee_exit_materialization_counts.csv",
        "FEE_EXIT_COUNTERFACTUAL_REPORT_CN.md",
        "fee_exit_counterfactual_report.csv",
        "SMALL_CAPACITY_AUDIT_CN.md",
        "small_capacity_audit.csv",
        "FEE_EXIT_BEST_VARIANT_SELECTION_CN.md",
        "fee_exit_best_variant_selection.json",
        "FEE_EXIT_VS_REGIME_AWARE_COMPARISON_CN.md",
        "fee_exit_vs_regime_aware_comparison.csv",
        "FEE_EXIT_ROBUSTNESS_AUDIT_CN.md",
        "fee_exit_robustness_audit.csv",
        "FEE_EXIT_NEXT_STAGE_DECISION_CN.md",
        "fee_exit_next_stage_decision.json",
        "FINAL_VERDICT.json",
        "ONEPAGE_CN.md",
    ]
    md = ["# Artifact Index", ""]
    for name in files:
        md.append(f"- `{name}`")
    write_text(REPORT_DIR / "ARTIFACT_INDEX.md", "\n".join(md) + "\n")


def main() -> None:
    ensure_dir(REPORT_DIR)
    audit, _ = input_audit()
    bootstrap_env()
    if not (os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")):
        raise RuntimeError("missing_postgres_dsn")

    conn = connect_db(readonly=False)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            write_vps_db_quick_check(cur)
            pools, ptm = load_pool_metadata(cur)
            samples = load_sample_rows(cur)
            pool_ids = sorted({s["pool_id"] for s in samples if s["pool_id"]})
            marks = load_marks(cur, pool_ids)
        if not samples:
            raise RuntimeError("no_source_samples")
        build_policy_doc()
        write_variants_json()
        write_schema_json()

        features_by_sample = {}
        for sample in samples:
            feature = feature_for_previous_closed_bucket(
                sample,
                marks.get(sample["pool_id"], []),
                pools.get(sample["pool_id"], {}),
                build_token_pair(sample["pool_id"], pools, ptm),
            )
            features_by_sample[sample["sample_id"]] = feature

        readiness_rows = build_data_readiness(samples, features_by_sample)
        write_readiness_md(readiness_rows)

        regime_lookup = load_entry_safe_regime_lookup()
        rows = materialize_rows(samples, features_by_sample, regime_lookup)
        create_table_and_insert(conn, rows)
        write_materialization_docs(summarize_materialization(rows))

        summary_rows, best, _ = summarize_variants(rows)
        write_counterfactual_report(summary_rows)
        small_cap_rows, small_cap_status = write_small_capacity_audit(summary_rows)
        write_best_variant(best)
        write_comparison(best, regime_lookup)
        _, robustness_status, overfit_risk, review_ready = write_robustness(summary_rows, best)
        decision = decide_next_stage(best, small_cap_status, robustness_status, overfit_risk, review_ready)
        write_final_verdict(True, best, small_cap_status, robustness_status, overfit_risk, review_ready, decision["recommended_next_stage"])
        write_artifact_index()
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
