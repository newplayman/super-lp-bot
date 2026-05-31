#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import shlex
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values


REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
RUN_ID = "20260531_113056"
REPORT_DIR = REPO_ROOT / "reports" / "pool_regime_rule_fix" / RUN_ID

INPUT_REVIEW_DIR = REPO_ROOT / "reports" / "pool_regime_aware_review" / "20260531_110005"
LEAKY_DIR = REPO_ROOT / "reports" / "pool_regime_aware_short_hold" / "20260531_095237"
CLASSIFIER_DIR = REPO_ROOT / "reports" / "pool_regime_classifier" / "20260531_092109"
RISK_SIGNAL_DIR = REPO_ROOT / "reports" / "risk_signal_definition_fix" / "20260531_080614"
RISK_AWARE_DIR = REPO_ROOT / "reports" / "risk_aware_short_hold" / "20260531_073906"

INPUT_REVIEW_RUN_STAGE = "POOL_REGIME_AWARE_SHORT_HOLD_REVIEW_V2"
LEAKY_RUN_ID = "20260531_095237"
CLASSIFIER_RUN_ID = "20260531_092109"
SHORT_HOLD_RUN_ID = "20260531_073906"

ENTRY_SAFE_TABLE = "pool_regime_classifier_entry_safe_v1"
ENTRY_SAFE_COUNTERFACTUAL_TABLE = "pool_regime_aware_short_hold_entry_safe_v1"
BUCKET_SECONDS = 15 * 60
MAX_LOOKBACK_SECONDS = 8 * 24 * 3600

WINDOWS = ["recent_24h", "recent_48h", "recent_72h", "recent_7d"]
HORIZONS = ["15m", "30m", "1h", "2h"]
PROOF_UNITS = ["pool_window"]

BAD_REGIMES = {
    "TOXIC_FLOW",
    "EXIT_DEPTH_THIN",
    "VOLUME_COLLAPSE",
    "TVL_DROP",
    "PRICE_SPIKE_VOLATILE",
    "DATA_STALE_OR_INCOMPLETE",
    "UNKNOWN",
}

VARIANTS = [
    "baseline_hold_all",
    "entry_safe_regime_score_threshold_loose",
    "entry_safe_exclude_DATA_STALE_OR_INCOMPLETE",
    "entry_safe_enter_only_HEALTHY_SHORT_HOLD",
    "entry_safe_enter_HEALTHY_or_STABLE_FEE",
    "entry_safe_exclude_bad_all",
    "entry_safe_hybrid_regime_plus_signal",
    "entry_safe_hybrid_regime_plus_signal_plus_fee",
]

RISK_QUARANTINE_SIGNALS = {
    "price_spike_down",
    "volume_collapse",
    "tvl_drop",
    "exit_depth_drop",
    "pool_mark_gap / stale data",
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


def bootstrap_env() -> None:
    for candidate in [REPO_ROOT / ".runtime.shadow.env", REPO_ROOT / ".env", REPO_ROOT / ".env.chain"]:
        if not candidate.exists():
            continue
        for raw in candidate.read_text(errors="ignore").splitlines():
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


def connect_db(readonly: bool = True):
    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("missing_postgres_dsn")
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=readonly, autocommit=True)
    return conn


def q(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


def parse_ts(v: Any):
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


def parse_num(v: Any) -> float | None:
    if v in (None, "", "null", "None"):
        return None
    try:
        return float(v)
    except Exception:
        return None


def fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return ""
        return f"{v:.10f}".rstrip("0").rstrip(".")
    return str(v)


def median(values: list[float]) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def percentile(values: list[float], p: float) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    idx = max(0, min(len(vals) - 1, int(round((len(vals) - 1) * p))))
    return vals[idx]


def bucket_floor(ts_seconds: int) -> int:
    return ts_seconds - (ts_seconds % BUCKET_SECONDS)


def window_label_for_age(age_hours: float) -> str:
    if age_hours <= 24:
        return "recent_24h"
    if age_hours <= 48:
        return "recent_48h"
    if age_hours <= 72:
        return "recent_72h"
    return "recent_7d"


def pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old in (None, 0):
        return None
    return (new - old) / old * 100.0


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def safe_depth_from_slippage(notional: float, slippage: float | None, target: float) -> float | None:
    if slippage is None or slippage <= 0:
        return None
    return notional * target / slippage


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_inputs() -> dict[str, Path]:
    return {
        "review_final": INPUT_REVIEW_DIR / "FINAL_VERDICT.json",
        "best_variant_md": INPUT_REVIEW_DIR / "BEST_VARIANT_RECOMPUTE_CN.md",
        "best_variant_csv": INPUT_REVIEW_DIR / "best_variant_recompute.csv",
        "time_window_md": INPUT_REVIEW_DIR / "TIME_WINDOW_ROBUSTNESS_CN.md",
        "time_window_csv": INPUT_REVIEW_DIR / "time_window_robustness.csv",
        "horizon_md": INPUT_REVIEW_DIR / "HORIZON_ROBUSTNESS_CN.md",
        "horizon_csv": INPUT_REVIEW_DIR / "horizon_robustness.csv",
        "lookahead_md": INPUT_REVIEW_DIR / "LOOKAHEAD_LEAKAGE_AUDIT_CN.md",
        "lookahead_json": INPUT_REVIEW_DIR / "lookahead_leakage_audit.json",
        "decision_md": INPUT_REVIEW_DIR / "POOL_REGIME_AWARE_REVIEW_NEXT_STAGE_DECISION_CN.md",
        "decision_json": INPUT_REVIEW_DIR / "pool_regime_aware_review_next_stage_decision.json",
        "leaky_final": LEAKY_DIR / "FINAL_VERDICT.json",
        "classifier_final": CLASSIFIER_DIR / "FINAL_VERDICT.json",
        "risk_signal_final": RISK_SIGNAL_DIR / "FINAL_VERDICT.json",
        "risk_aware_final": RISK_AWARE_DIR / "FINAL_VERDICT.json",
    }


def load_pool_metadata(cur):
    pools = {
        r["pool_id"]: dict(r)
        for r in q(cur, "select pool_id, chain, protocol, token0, token1, fee_bps, tier, tvl_usd, vol_24h, fee_apr_24h from pools")
    }
    meta = {
        r["pool_id"]: dict(r)
        for r in q(cur, "select pool_id, token0, token1, token0_symbol, token1_symbol, token0_decimals, token1_decimals from pool_token_metadata")
    }
    return pools, meta


def build_token_pair(pool_id: str, pools: dict[str, dict[str, Any]], meta: dict[str, dict[str, Any]]) -> str:
    m = meta.get(pool_id) or {}
    if m.get("token0_symbol") and m.get("token1_symbol"):
        return f"{m['token0_symbol']}/{m['token1_symbol']}"
    if m.get("token0") and m.get("token1"):
        return f"{str(m['token0'])[:8]}/{str(m['token1'])[:8]}"
    p = pools.get(pool_id) or {}
    if p.get("token0") and p.get("token1"):
        return f"{str(p['token0'])[:8]}/{str(p['token1'])[:8]}"
    return pool_id


def load_marks(cur, pool_ids: list[str]):
    rows = q(
        cur,
        """
        select mark_time, pool_id, valuation_usd, current_tvl_usd, current_vol24h_usd, price_change_pct, status, source, amount_usd
        from shadow_position_marks
        where pool_id = any(%s)
          and mark_time >= extract(epoch from now() - interval '8 days')
        order by pool_id, mark_time
        """,
        (pool_ids,),
    )
    grouped = defaultdict(lambda: defaultdict(list))
    for r in rows:
        grouped[r["pool_id"]][int(r["mark_time"])].append(r)
    series = {}
    for pool_id, by_ts in grouped.items():
        items = []
        for ts, rows2 in sorted(by_ts.items()):
            items.append(
                {
                    "mark_time": ts,
                    "valuation_usd": median([parse_num(x["valuation_usd"]) for x in rows2]),
                    "current_tvl_usd": median([parse_num(x["current_tvl_usd"]) for x in rows2]),
                    "current_vol24h_usd": median([parse_num(x["current_vol24h_usd"]) for x in rows2]),
                    "price_change_pct": median([parse_num(x["price_change_pct"]) for x in rows2]),
                    "amount_usd": median([parse_num(x["amount_usd"]) for x in rows2]),
                    "source": ",".join(sorted({x.get("source") or "" for x in rows2 if x.get("source")})),
                    "status": ",".join(sorted({x.get("status") or "" for x in rows2 if x.get("status")})),
                }
            )
        series[pool_id] = items
    return series


def load_sample_rows(cur):
    rows = q(
        cur,
        """
        select run_id, sample_id, proof_unit_type, pool_id, token_pair, start_time, horizon,
               entry_value_source, entry_value, target_value_hold, risk_exit_time, risk_exit_value,
               first_risk_signal, risk_signal_severity, fee_proxy, exit_cost_proxy,
               hold_to_horizon_pnl_pct, risk_aware_exit_pnl_pct, no_entry_quarantine_pnl_pct,
               loss_saved_vs_hold, missed_profit_vs_hold, false_exit_flag, opportunity_flag,
               data_quality_status, invalid_reason, created_at
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
        start_time = parse_ts(r["start_time"])
        if not start_time:
            continue
        out.append(
            {
                **dict(r),
                "start_time_dt": start_time,
                "start_ts": int(start_time.timestamp()),
                "sample_window": window_label_for_age((now - start_time).total_seconds() / 3600.0),
                "hold_pnl": parse_num(r["hold_to_horizon_pnl_pct"]),
                "entry_value_f": parse_num(r["entry_value"]),
                "target_value_f": parse_num(r["target_value_hold"]),
                "fee_proxy_f": parse_num(r["fee_proxy"]),
                "exit_cost_proxy_f": parse_num(r["exit_cost_proxy"]),
            }
        )
    return out


def load_original_classifier(cur):
    rows = q(
        cur,
        """
        select pool_id, bucket_start, bucket_end, window_label, regime_primary, regime_secondary, regime_confidence,
               should_enter, should_quarantine, should_research_only, risk_score, exit_depth_score,
               volatility_score, volume_score, tvl_score, data_quality_score, fee_proxy_score, rule_hits, missing_features
        from pool_regime_classifier_v1
        where run_id = %s
        """,
        (CLASSIFIER_RUN_ID,),
    )
    lookup = {}
    for r in rows:
        key = (r["pool_id"], int(parse_ts(r["bucket_start"]).timestamp()), r["window_label"])
        lookup[key] = dict(r)
    return lookup


def find_latest_index(ts_list: list[int], target_ts: int) -> int:
    return bisect_right(ts_list, target_ts) - 1


def feature_for_previous_closed_bucket(
    sample: dict[str, Any],
    marks: list[dict[str, Any]],
    pool: dict[str, Any],
    token_pair: str,
) -> dict[str, Any]:
    sample_start_ts = sample["start_ts"]
    classifier_bucket_end = bucket_floor(sample_start_ts)
    classifier_bucket_start = classifier_bucket_end - BUCKET_SECONDS
    feature_lag_seconds = sample_start_ts - classifier_bucket_end

    ts_list = [s["mark_time"] for s in marks]
    idx = find_latest_index(ts_list, classifier_bucket_end)
    current = marks[idx] if idx >= 0 else None
    current_age = classifier_bucket_end - current["mark_time"] if current else None

    def value_at(offset_seconds: int, field: str):
        target = classifier_bucket_end - offset_seconds
        j = find_latest_index(ts_list, target)
        if j < 0:
            return None
        return marks[j].get(field)

    val_now = current.get("valuation_usd") if current else None
    tvl_now = current.get("current_tvl_usd") if current else None
    vol_now = current.get("current_vol24h_usd") if current else None

    val_5m = value_at(5 * 60, "valuation_usd")
    val_15m = value_at(15 * 60, "valuation_usd")
    val_30m = value_at(30 * 60, "valuation_usd")
    val_1h = value_at(60 * 60, "valuation_usd")
    tvl_15m = value_at(15 * 60, "current_tvl_usd")
    tvl_30m = value_at(30 * 60, "current_tvl_usd")
    tvl_1h = value_at(60 * 60, "current_tvl_usd")
    vol_15m = value_at(15 * 60, "current_vol24h_usd")
    vol_30m = value_at(30 * 60, "current_vol24h_usd")
    vol_1h = value_at(60 * 60, "current_vol24h_usd")

    price_move_5m = pct_change(val_now, val_5m)
    price_move_15m = pct_change(val_now, val_15m)
    price_move_30m = pct_change(val_now, val_30m)
    price_move_1h = pct_change(val_now, val_1h)
    volume_change_15m = pct_change(vol_now, vol_15m)
    volume_change_30m = pct_change(vol_now, vol_30m)
    volume_change_1h = pct_change(vol_now, vol_1h)
    tvl_change_1h = pct_change(tvl_now, tvl_1h)

    fee_bps = parse_num(pool.get("fee_bps"))
    fee_rate = (fee_bps or 0.0) / 10_000.0
    fee_proxy = (vol_now or 0.0) * fee_rate if vol_now is not None else None
    fee_velocity_proxy = (fee_proxy / tvl_now) if fee_proxy is not None and tvl_now not in (None, 0) else None

    slippage_10usd = slippage_20usd = slippage_50usd = None
    exit_depth_10usd = exit_depth_20usd = exit_depth_50usd = None
    if tvl_now not in (None, 0):
        base = 0.001 + ((10.0 / max(tvl_now, 1.0)) * 0.5)
        if vol_now is not None:
            base += min(0.02, (vol_now / max(tvl_now, 1.0)) * 0.0005)
        base += min(0.01, fee_rate * 0.05)
        slippage_10usd = clamp(base, 0.0005, 0.2)
        slippage_20usd = clamp(base * 1.8, 0.0008, 0.3)
        slippage_50usd = clamp(base * 4.0, 0.001, 0.5)
        exit_depth_10usd = safe_depth_from_slippage(10.0, slippage_10usd, 0.01)
        exit_depth_20usd = safe_depth_from_slippage(20.0, slippage_20usd, 0.02)
        exit_depth_50usd = safe_depth_from_slippage(50.0, slippage_50usd, 0.05)

    stale_data_flag = current is None or current_age is None or current_age > 5 * 60
    missing_features = []
    for name, value in [
        ("price_move_5m", price_move_5m),
        ("price_move_15m", price_move_15m),
        ("price_move_30m", price_move_30m),
        ("price_move_1h", price_move_1h),
        ("volume_change_15m", volume_change_15m),
        ("volume_change_30m", volume_change_30m),
        ("volume_change_1h", volume_change_1h),
        ("tvl_change_1h", tvl_change_1h),
        ("fee_proxy", fee_proxy),
        ("exit_depth_10usd", exit_depth_10usd),
        ("exit_depth_20usd", exit_depth_20usd),
        ("exit_depth_50usd", exit_depth_50usd),
        ("slippage_10usd", slippage_10usd),
        ("slippage_20usd", slippage_20usd),
        ("slippage_50usd", slippage_50usd),
    ]:
        if value is None:
            missing_features.append(name)
    data_quality_score = max(0.0, 100.0 - len(missing_features) * 6.0 - (25.0 if stale_data_flag else 0.0))

    abnormal_volume_spike = bool(
        (volume_change_15m is not None and volume_change_15m >= 75.0)
        or (volume_change_30m is not None and volume_change_30m >= 100.0)
        or (volume_change_1h is not None and volume_change_1h >= 150.0)
    )
    volume_collapse = bool(
        (volume_change_15m is not None and volume_change_15m <= -25.0)
        or (volume_change_30m is not None and volume_change_30m <= -35.0)
        or (volume_change_1h is not None and volume_change_1h <= -50.0)
    )
    price_spike_down = bool(
        (price_move_5m is not None and price_move_5m <= -1.0)
        or (price_move_15m is not None and price_move_15m <= -2.0)
        or (price_move_30m is not None and price_move_30m <= -3.0)
        or (price_move_1h is not None and price_move_1h <= -5.0)
    )
    price_spike_up = bool(
        (price_move_5m is not None and price_move_5m >= 1.0)
        or (price_move_15m is not None and price_move_15m >= 2.0)
        or (price_move_30m is not None and price_move_30m >= 3.0)
        or (price_move_1h is not None and price_move_1h >= 5.0)
    )
    price_spike_volatile = bool(price_spike_down or price_spike_up)
    tvl_drop = bool(tvl_change_1h is not None and tvl_change_1h <= -20.0)
    exit_depth_thin = bool(
        (slippage_10usd is not None and slippage_10usd > 0.01)
        or (slippage_20usd is not None and slippage_20usd > 0.02)
        or (slippage_50usd is not None and slippage_50usd > 0.05)
        or (exit_depth_50usd is not None and exit_depth_50usd < 100.0)
    )

    used_features = [
        name
        for name, value in [
            ("price_move_5m", price_move_5m),
            ("price_move_15m", price_move_15m),
            ("price_move_30m", price_move_30m),
            ("price_move_1h", price_move_1h),
            ("volume_change_15m", volume_change_15m),
            ("volume_change_30m", volume_change_30m),
            ("volume_change_1h", volume_change_1h),
            ("tvl_change_1h", tvl_change_1h),
            ("fee_proxy", fee_proxy),
            ("exit_depth_10usd", exit_depth_10usd),
            ("exit_depth_20usd", exit_depth_20usd),
            ("exit_depth_50usd", exit_depth_50usd),
            ("slippage_10usd", slippage_10usd),
            ("slippage_20usd", slippage_20usd),
            ("slippage_50usd", slippage_50usd),
            ("stale_data_flag", stale_data_flag),
            ("data_quality_score", data_quality_score),
        ]
        if value is not None
    ]
    diagnostic_only_features = [
        "security_score_latest",
        "concentration_proxy_latest",
        "same_bucket_price_move",
        "same_bucket_volume_change",
        "same_bucket_tvl_change",
        "same_bucket_stale_data_flag",
    ]

    exit_depth_score = clamp((exit_depth_50usd / 500.0) * 100.0, 0.0, 100.0) if exit_depth_50usd is not None else 0.0
    volatility_score = 100.0
    if price_move_1h is not None:
        volatility_score = clamp(
            100.0
            - max(
                abs(price_move_5m or 0.0) / 2.0,
                abs(price_move_15m or 0.0) / 4.0,
                abs(price_move_30m or 0.0) / 6.0,
                abs(price_move_1h or 0.0) / 10.0,
            )
            * 100.0,
            0.0,
            100.0,
        )
    volume_score = 100.0
    if volume_change_1h is not None:
        vscore = 100.0
        if volume_collapse:
            vscore -= 50.0
        if abnormal_volume_spike:
            vscore -= 25.0
        if -10.0 < volume_change_1h < 50.0:
            vscore += 5.0
        volume_score = clamp(vscore, 0.0, 100.0)
    tvl_score = 100.0
    if tvl_change_1h is not None:
        tvl_score = clamp(100.0 - max(0.0, -tvl_change_1h) * 2.5, 0.0, 100.0)
    fee_proxy_score = clamp((fee_velocity_proxy or 0.0) * 4000.0, 0.0, 100.0) if fee_velocity_proxy is not None else 0.0
    risk_score = 100.0 - (
        0.34 * exit_depth_score
        + 0.24 * volatility_score
        + 0.18 * volume_score
        + 0.12 * tvl_score
        + 0.12 * data_quality_score
    )
    risk_score = clamp(risk_score, 0.0, 100.0)

    rule_hits = []
    if stale_data_flag or data_quality_score < 70.0:
        rule_hits.append("DATA_STALE_OR_INCOMPLETE")
    if exit_depth_thin:
        rule_hits.append("EXIT_DEPTH_THIN")
    if tvl_drop:
        rule_hits.append("TVL_DROP")
    if volume_collapse:
        rule_hits.append("VOLUME_COLLAPSE")
    if abnormal_volume_spike and price_spike_volatile:
        rule_hits.append("TOXIC_FLOW")
    if price_spike_volatile and not rule_hits:
        rule_hits.append("PRICE_SPIKE_VOLATILE")
    if not rule_hits and fee_velocity_proxy is not None and fee_velocity_proxy >= 0.01 and abs(price_move_15m or 0.0) <= 1.5 and abs(price_move_30m or 0.0) <= 2.0 and not volume_collapse and not tvl_drop:
        rule_hits.append("STABLE_FEE")
    if not rule_hits and exit_depth_50usd is not None and exit_depth_50usd >= 500.0 and abs(price_move_15m or 0.0) <= 1.5 and abs(price_move_30m or 0.0) <= 2.5 and not volume_collapse and not tvl_drop:
        rule_hits.append("HEALTHY_SHORT_HOLD")
    if not rule_hits:
        rule_hits.append("UNKNOWN")
    regime_primary = rule_hits[0]
    regime_secondary = rule_hits[1] if len(rule_hits) > 1 else ""
    regime_confidence = "high" if data_quality_score >= 80 and regime_primary != "UNKNOWN" else "medium" if data_quality_score >= 60 else "low"
    should_enter = regime_primary in {"HEALTHY_SHORT_HOLD", "STABLE_FEE"} and risk_score <= 35.0
    should_quarantine = regime_primary in BAD_REGIMES

    return {
        "pool_id": sample["pool_id"],
        "token_pair": token_pair,
        "sample_start_time": sample["start_time_dt"],
        "sample_window": sample["sample_window"],
        "horizon": sample["horizon"],
        "proof_unit_type": sample["proof_unit_type"],
        "classifier_bucket_start": datetime.fromtimestamp(classifier_bucket_start, tz=timezone.utc),
        "classifier_bucket_end": datetime.fromtimestamp(classifier_bucket_end, tz=timezone.utc),
        "classifier_feature_cutoff_time": datetime.fromtimestamp(classifier_bucket_end, tz=timezone.utc),
        "feature_lag_seconds": feature_lag_seconds,
        "regime_primary": regime_primary,
        "regime_secondary": regime_secondary,
        "regime_confidence": regime_confidence,
        "rule_hits": rule_hits,
        "used_features": used_features,
        "diagnostic_only_features": diagnostic_only_features,
        "stale_data_flag": stale_data_flag,
        "data_quality_score": data_quality_score,
        "exit_depth_score": exit_depth_score,
        "volatility_score": volatility_score,
        "volume_score": volume_score,
        "tvl_score": tvl_score,
        "fee_proxy_score": fee_proxy_score,
        "risk_score": risk_score,
        "lookahead_safe": classifier_bucket_end <= sample_start_ts,
        "leakage_risk": "LOW" if classifier_bucket_end <= sample_start_ts else "HIGH",
        "missing_features": missing_features,
    }


def materialize_entry_safe(cur, rows: list[dict[str, Any]]):
    cur.execute(
        f"""
        create table if not exists {ENTRY_SAFE_TABLE} (
            run_id text not null,
            sample_id text not null,
            proof_unit_type text not null,
            horizon text not null,
            window_label text not null,
            pool_id text not null,
            token_pair text not null,
            sample_start_time timestamptz not null,
            classifier_bucket_start timestamptz not null,
            classifier_bucket_end timestamptz not null,
            classifier_feature_cutoff_time timestamptz not null,
            feature_lag_seconds integer not null,
            regime_primary text not null,
            regime_secondary text not null,
            regime_confidence text not null,
            rule_hits text not null,
            used_features text not null,
            diagnostic_only_features text not null,
            stale_data_flag boolean not null,
            data_quality_score double precision,
            exit_depth_score double precision,
            volatility_score double precision,
            volume_score double precision,
            tvl_score double precision,
            fee_proxy_score double precision,
            risk_score double precision,
            lookahead_safe boolean not null,
            leakage_risk text not null,
            missing_features text not null,
            created_at timestamptz default now()
        )
        """
    )
    cur.execute(f"delete from {ENTRY_SAFE_TABLE} where run_id = %s", (RUN_ID,))
    values = [
        (
            RUN_ID,
            r["sample_id"],
            r["proof_unit_type"],
            r["horizon"],
            r["sample_window"],
            r["pool_id"],
            r["token_pair"],
            r["sample_start_time"],
            r["classifier_bucket_start"],
            r["classifier_bucket_end"],
            r["classifier_feature_cutoff_time"],
            r["feature_lag_seconds"],
            r["regime_primary"],
            r["regime_secondary"],
            r["regime_confidence"],
            json.dumps(r["rule_hits"], ensure_ascii=False),
            json.dumps(r["used_features"], ensure_ascii=False),
            json.dumps(r["diagnostic_only_features"], ensure_ascii=False),
            r["stale_data_flag"],
            r["data_quality_score"],
            r["exit_depth_score"],
            r["volatility_score"],
            r["volume_score"],
            r["tvl_score"],
            r["fee_proxy_score"],
            r["risk_score"],
            r["lookahead_safe"],
            r["leakage_risk"],
            json.dumps(r["missing_features"], ensure_ascii=False),
            datetime.now(timezone.utc),
        )
        for r in rows
    ]
    execute_values(
        cur,
        f"""
        insert into {ENTRY_SAFE_TABLE} (
            run_id, sample_id, proof_unit_type, horizon, window_label, pool_id, token_pair, sample_start_time,
            classifier_bucket_start, classifier_bucket_end, classifier_feature_cutoff_time, feature_lag_seconds,
            regime_primary, regime_secondary, regime_confidence, rule_hits, used_features, diagnostic_only_features,
            stale_data_flag, data_quality_score, exit_depth_score, volatility_score, volume_score, tvl_score,
            fee_proxy_score, risk_score, lookahead_safe, leakage_risk, missing_features, created_at
        ) values %s
        """,
        values,
        page_size=1000,
    )


def materialize_entry_safe_counterfactual(cur, rows: list[dict[str, Any]]):
    cur.execute(
        f"""
        create table if not exists {ENTRY_SAFE_COUNTERFACTUAL_TABLE} (
            run_id text not null,
            variant_name text not null,
            sample_id text not null,
            proof_unit_type text not null,
            horizon text not null,
            window_label text not null,
            pool_id text not null,
            token_pair text not null,
            regime_primary text not null,
            risk_score double precision,
            entry_allowed boolean not null,
            quarantine_reason text not null,
            hold_to_horizon_pnl_pct double precision,
            regime_filtered_pnl_pct double precision,
            opportunity_retained boolean not null,
            false_quarantine_flag boolean not null,
            missed_profit double precision,
            loss_avoided double precision,
            leakage_risk text not null,
            data_quality_status text not null,
            created_at timestamptz default now()
        )
        """
    )
    cur.execute(f"delete from {ENTRY_SAFE_COUNTERFACTUAL_TABLE} where run_id = %s", (RUN_ID,))
    values = [
        (
            RUN_ID,
            r["variant_name"],
            r["sample_id"],
            r["proof_unit_type"],
            r["horizon"],
            r["window_label"],
            r["pool_id"],
            r["token_pair"],
            r["regime_primary"],
            r["risk_score"],
            r["entry_allowed"],
            r["quarantine_reason"],
            r["hold_to_horizon_pnl_pct"],
            r["regime_filtered_pnl_pct"],
            r["opportunity_retained"],
            r["false_quarantine_flag"],
            r["missed_profit"],
            r["loss_avoided"],
            r["leakage_risk"],
            r["data_quality_status"],
            datetime.now(timezone.utc),
        )
        for r in rows
    ]
    execute_values(
        cur,
        f"""
        insert into {ENTRY_SAFE_COUNTERFACTUAL_TABLE} (
            run_id, variant_name, sample_id, proof_unit_type, horizon, window_label, pool_id, token_pair,
            regime_primary, risk_score, entry_allowed, quarantine_reason, hold_to_horizon_pnl_pct,
            regime_filtered_pnl_pct, opportunity_retained, false_quarantine_flag, missed_profit,
            loss_avoided, leakage_risk, data_quality_status, created_at
        ) values %s
        """,
        values,
        page_size=1000,
    )


def apply_variant(sample: dict[str, Any], variant_name: str):
    hold = sample["hold_pnl"]
    valid = sample["data_quality_status"] == "ok" and hold is not None
    if not valid:
        return False, "invalid_sample", 0.0, False, 0.0, 0.0, False

    regime_primary = sample["regime_primary"]
    risk_score = sample["risk_score"]
    first_signal = (sample["first_risk_signal"] or "").strip()
    signal_block = first_signal in RISK_QUARANTINE_SIGNALS
    fee_proxy = sample["fee_proxy_f"]
    exit_cost = sample["exit_cost_proxy_f"]

    allowed = True
    quarantine_reason = ""
    if variant_name == "baseline_hold_all":
        allowed = True
    elif variant_name == "entry_safe_regime_score_threshold_loose":
        allowed = risk_score is not None and risk_score <= 35.0
        if not allowed:
            quarantine_reason = "risk_score_gt_35"
    elif variant_name == "entry_safe_exclude_DATA_STALE_OR_INCOMPLETE":
        allowed = regime_primary != "DATA_STALE_OR_INCOMPLETE"
        if not allowed:
            quarantine_reason = "DATA_STALE_OR_INCOMPLETE"
    elif variant_name == "entry_safe_enter_only_HEALTHY_SHORT_HOLD":
        allowed = regime_primary == "HEALTHY_SHORT_HOLD"
        if not allowed:
            quarantine_reason = regime_primary
    elif variant_name == "entry_safe_enter_HEALTHY_or_STABLE_FEE":
        allowed = regime_primary in {"HEALTHY_SHORT_HOLD", "STABLE_FEE"}
        if not allowed:
            quarantine_reason = regime_primary
    elif variant_name == "entry_safe_exclude_bad_all":
        allowed = regime_primary not in BAD_REGIMES
        if not allowed:
            quarantine_reason = regime_primary
    elif variant_name == "entry_safe_hybrid_regime_plus_signal":
        allowed = regime_primary not in BAD_REGIMES and not signal_block
        if not allowed:
            quarantine_reason = regime_primary if regime_primary in BAD_REGIMES else f"risk_signal:{first_signal}"
    elif variant_name == "entry_safe_hybrid_regime_plus_signal_plus_fee":
        allowed = regime_primary not in BAD_REGIMES and not signal_block and fee_proxy is not None and exit_cost is not None and fee_proxy > exit_cost
        if not allowed:
            if regime_primary in BAD_REGIMES:
                quarantine_reason = regime_primary
            elif signal_block:
                quarantine_reason = f"risk_signal:{first_signal}"
            else:
                quarantine_reason = "fee_proxy_vs_exit_cost_low"
    else:
        raise KeyError(variant_name)

    filtered_pnl = hold if allowed else 0.0
    opportunity_retained = bool(allowed and hold > 0)
    loss_avoided = abs(hold) if (not allowed and hold < 0) else 0.0
    missed_profit = hold if (not allowed and hold > 0) else 0.0
    false_quarantine = bool((not allowed) and hold > 0)
    return allowed, quarantine_reason, filtered_pnl, opportunity_retained, loss_avoided, missed_profit, false_quarantine


def compute_group_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid_rows = [r for r in rows if r["data_quality_status"] == "ok" and r["hold_to_horizon_pnl_pct"] is not None]
    hold_vals = [r["hold_to_horizon_pnl_pct"] for r in valid_rows]
    kept = [r for r in valid_rows if r["entry_allowed"]]
    kept_vals = [r["regime_filtered_pnl_pct"] for r in kept]
    pos = [r for r in valid_rows if r["hold_to_horizon_pnl_pct"] > 0]
    neg = [r for r in valid_rows if r["hold_to_horizon_pnl_pct"] < 0]
    worst_pool = Counter()
    for r in kept:
        if r["hold_to_horizon_pnl_pct"] < 0:
            worst_pool[r["pool_id"]] += abs(r["hold_to_horizon_pnl_pct"])
    worst_pool_contribution = (max(worst_pool.values()) / sum(worst_pool.values())) if worst_pool else None
    return {
        "sample_count": len(valid_rows),
        "retained_sample_count": len(kept),
        "baseline_p10": percentile(hold_vals, 0.10),
        "baseline_p5": percentile(hold_vals, 0.05),
        "baseline_p1": percentile(hold_vals, 0.01),
        "filtered_p10": percentile(kept_vals, 0.10),
        "filtered_p5": percentile(kept_vals, 0.05),
        "filtered_p1": percentile(kept_vals, 0.01),
        "tail_improvement_p10": (percentile(kept_vals, 0.10) - percentile(hold_vals, 0.10)) if kept_vals and hold_vals else None,
        "tail_improvement_p5": (percentile(kept_vals, 0.05) - percentile(hold_vals, 0.05)) if kept_vals and hold_vals else None,
        "tail_improvement_p1": (percentile(kept_vals, 0.01) - percentile(hold_vals, 0.01)) if kept_vals and hold_vals else None,
        "opportunity_retention_rate": (sum(1 for r in pos if r["entry_allowed"]) / len(pos)) if pos else None,
        "false_quarantine_rate": (sum(1 for r in valid_rows if r["false_quarantine_flag"]) / len(valid_rows)) if valid_rows else None,
        "missed_profit_rate": (sum(r["missed_profit"] for r in valid_rows) / len(pos)) if pos else None,
        "worst_pool_contribution": worst_pool_contribution,
        "data_quality_status": "sufficient" if len(valid_rows) >= 300 else "preliminary" if len(valid_rows) >= 100 else "insufficient",
        "loss_avoidance_rate": (sum(1 for r in valid_rows if (not r["entry_allowed"]) and r["hold_to_horizon_pnl_pct"] < 0) / len(neg)) if neg else None,
        "leakage_risk": "LOW" if all(r["leakage_risk"] == "LOW" for r in valid_rows) else "MEDIUM" if any(r["leakage_risk"] == "MEDIUM" for r in valid_rows) else "HIGH",
    }


def row_verdict(metrics: dict[str, Any]) -> str:
    if metrics["retained_sample_count"] < 30:
        return "INSUFFICIENT"
    if all((metrics[k] is not None and metrics[k] > 0) for k in ["tail_improvement_p10", "tail_improvement_p5", "tail_improvement_p1"]):
        return "PROMISING"
    if (metrics["tail_improvement_p10"] or -1) > -0.01 and (metrics["tail_improvement_p5"] or -1) > -0.02:
        return "WEAK"
    return "BAD"


def main():
    ensure_dir(REPORT_DIR)
    inputs = load_inputs()
    input_exists = {k: v.exists() for k, v in inputs.items()}
    review_final = load_json(inputs["review_final"])
    input_audit = {
        **input_exists,
        "prior_stage_ok": review_final.get("stage") == INPUT_REVIEW_RUN_STAGE,
        "prior_leakage_found_yes": review_final.get("leakage_found") is True,
        "prior_lookahead_risk_high": review_final.get("lookahead_risk") == "HIGH",
        "prior_next_stage_rule_fix": review_final.get("recommended_next_stage") == "POOL_REGIME_RULE_FIX",
        "enough_for_rule_fix": all(input_exists.values()) and review_final.get("stage") == INPUT_REVIEW_RUN_STAGE,
        "edge_proven": "no",
    }
    write_text(
        REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md",
        "# Input Artifact Audit\n\n"
        + "\n".join(f"- {k}: {'yes' if v else 'no'}" for k, v in input_exists.items())
        + "\n\n"
        + f"- prior_stage_ok: {fmt(input_audit['prior_stage_ok'])}\n"
        + f"- prior_leakage_found_yes: {fmt(input_audit['prior_leakage_found_yes'])}\n"
        + f"- prior_lookahead_risk_high: {fmt(input_audit['prior_lookahead_risk_high'])}\n"
        + f"- prior_next_stage_rule_fix: {fmt(input_audit['prior_next_stage_rule_fix'])}\n"
        + f"- enough_for_rule_fix: {fmt(input_audit['enough_for_rule_fix'])}\n"
        + "- edge_proven: no\n",
    )
    write_json(REPORT_DIR / "input_artifact_audit.json", input_audit)
    if review_final.get("stage") != INPUT_REVIEW_RUN_STAGE:
        write_text(
            REPORT_DIR / "WRONG_STAGE_BLOCKER_CN.md",
            f"# Wrong Stage Blocker\n\n- expected_stage: {INPUT_REVIEW_RUN_STAGE}\n- actual_stage: {review_final.get('stage')}\n",
        )
        return

    bootstrap_env()
    conn = connect_db(readonly=False)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("select current_database(), current_user")
        db_name, db_user = cur.fetchone().values()
        pools, meta = load_pool_metadata(cur)
        samples = load_sample_rows(cur)
        pool_ids = sorted({s["pool_id"] for s in samples})
        marks = load_marks(cur, pool_ids)
        original_lookup = load_original_classifier(cur)

        entry_safe_rows = []
        compare_regimes = []
        for sample in samples:
            pool_marks = marks.get(sample["pool_id"], [])
            token_pair = sample["token_pair"] or build_token_pair(sample["pool_id"], pools, meta)
            row = feature_for_previous_closed_bucket(sample, pool_marks, pools.get(sample["pool_id"], {}), token_pair)
            row["sample_id"] = sample["sample_id"]
            entry_safe_rows.append(row)
            same_bucket_key = (sample["pool_id"], bucket_floor(sample["start_ts"]), sample["sample_window"])
            orig = original_lookup.get(same_bucket_key)
            compare_regimes.append(
                {
                    "sample_id": sample["sample_id"],
                    "window": sample["sample_window"],
                    "horizon": sample["horizon"],
                    "original_regime_primary": orig["regime_primary"] if orig else "MISSING",
                    "entry_safe_regime_primary": row["regime_primary"],
                }
            )

        materialize_entry_safe(cur, entry_safe_rows)

        counterfactual_rows = []
        grouped_rows: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
        safe_lookup = {r["sample_id"]: r for r in entry_safe_rows}
        for sample in samples:
            safe = safe_lookup[sample["sample_id"]]
            for variant in VARIANTS:
                allowed, quarantine_reason, filtered_pnl, opportunity_retained, loss_avoided, missed_profit, false_quarantine = apply_variant(
                    {**sample, **safe},
                    variant,
                )
                row = {
                    "variant_name": variant,
                    "sample_id": sample["sample_id"],
                    "proof_unit_type": sample["proof_unit_type"],
                    "window_label": sample["sample_window"],
                    "horizon": sample["horizon"],
                    "pool_id": sample["pool_id"],
                    "token_pair": sample["token_pair"],
                    "regime_primary": safe["regime_primary"],
                    "risk_score": safe["risk_score"],
                    "entry_allowed": allowed,
                    "quarantine_reason": quarantine_reason,
                    "hold_to_horizon_pnl_pct": sample["hold_pnl"],
                    "regime_filtered_pnl_pct": filtered_pnl,
                    "opportunity_retained": opportunity_retained,
                    "false_quarantine_flag": false_quarantine,
                    "missed_profit": missed_profit,
                    "loss_avoided": loss_avoided,
                    "leakage_risk": safe["leakage_risk"],
                    "data_quality_status": sample["data_quality_status"],
                    "first_risk_signal": sample["first_risk_signal"],
                    "fee_proxy_f": sample["fee_proxy_f"],
                    "exit_cost_proxy_f": sample["exit_cost_proxy_f"],
                }
                counterfactual_rows.append(row)
                grouped_rows[(variant, sample["sample_window"], sample["horizon"], sample["proof_unit_type"])].append(row)

        materialize_entry_safe_counterfactual(cur, counterfactual_rows)
    conn.close()

    write_text(
        REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md",
        f"# VPS DB Quick Check\n\n- DSN_PRESENT: yes\n- DB_CONNECT: ok\n- DB_NAME: {db_name}\n- DB_USER: {db_user}\n",
    )

    policy = {
        "sample_start_time": "counterfactual entry timestamp from risk_aware_short_hold_counterfactual_v1.start_time",
        "classifier_feature_cutoff_time": "previous fully closed 15m bucket_end, always <= sample_start_time",
        "previous_closed_bucket_rule": "for each sample_start use bucket_end = floor(sample_start/15m); features are computed from bucket [bucket_end-15m, bucket_end], never same bucket as sample_start",
        "allowed_features_for_entry_safe_classifier": [
            "previous bucket price_move_5m/15m/30m/1h",
            "previous bucket volume_change_15m/30m/1h",
            "previous bucket tvl_change_1h",
            "previous bucket exit_depth and slippage approximations",
            "previous bucket stale_data_flag",
            "previous bucket data_quality_score",
            "previous bucket fee_proxy",
        ],
        "banned_features": [
            "same bucket price / volume / tvl / stale data computed at bucket_end after sample_start",
            "target horizon outcome",
            "future mark after sample_start",
            "any feature requiring data after sample_start",
        ],
        "diagnostic_only_features": [
            "security_score_latest",
            "concentration_proxy_latest",
            "same_bucket features until timestamp safe",
        ],
    }
    write_json(REPORT_DIR / "entry_safe_regime_feature_policy.json", policy)
    write_text(
        REPORT_DIR / "ENTRY_SAFE_REGIME_FEATURE_POLICY_CN.md",
        "# Entry Safe Regime Feature Policy\n\n"
        f"- sample_start_time: {policy['sample_start_time']}\n"
        f"- classifier_feature_cutoff_time: {policy['classifier_feature_cutoff_time']}\n"
        f"- previous_closed_bucket_rule: {policy['previous_closed_bucket_rule']}\n"
        f"- allowed_features_for_entry_safe_classifier: {', '.join(policy['allowed_features_for_entry_safe_classifier'])}\n"
        f"- banned_features: {', '.join(policy['banned_features'])}\n"
        f"- diagnostic_only_features: {', '.join(policy['diagnostic_only_features'])}\n",
    )

    write_json(
        REPORT_DIR / "entry_safe_regime_schema.json",
        {
            "table_name": ENTRY_SAFE_TABLE,
            "fields": [
                "run_id", "sample_id", "proof_unit_type", "horizon", "window_label", "pool_id", "token_pair",
                "sample_start_time", "classifier_bucket_start", "classifier_bucket_end", "classifier_feature_cutoff_time",
                "feature_lag_seconds", "regime_primary", "regime_secondary", "regime_confidence", "rule_hits",
                "used_features", "diagnostic_only_features", "stale_data_flag", "data_quality_score",
                "exit_depth_score", "volatility_score", "volume_score", "tvl_score", "fee_proxy_score",
                "risk_score", "lookahead_safe", "leakage_risk", "missing_features", "created_at",
            ],
        },
    )
    write_text(
        REPORT_DIR / "ENTRY_SAFE_REGIME_SCHEMA_CN.md",
        "# Entry Safe Regime Schema\n\n"
        f"- table_name: {ENTRY_SAFE_TABLE}\n"
        "- includes sample_start_time, previous bucket classifier timestamps, safe rule fields, and leakage flags.\n",
    )

    by_window = Counter(r["sample_window"] for r in entry_safe_rows)
    by_bucket = Counter(r["horizon"] for r in entry_safe_rows)
    by_regime = Counter(r["regime_primary"] for r in entry_safe_rows)
    leakage_dist = Counter(r["leakage_risk"] for r in entry_safe_rows)
    original_regime = Counter(r["original_regime_primary"] for r in compare_regimes)
    entry_safe_regime = Counter(r["entry_safe_regime_primary"] for r in compare_regimes)
    materialization_rows = []
    for window, count in sorted(by_window.items()):
        materialization_rows.append({"dimension": "window", "key": window, "count": count})
    for bucket, count in sorted(by_bucket.items()):
        materialization_rows.append({"dimension": "bucket", "key": bucket, "count": count})
    for regime, count in sorted(by_regime.items()):
        materialization_rows.append({"dimension": "regime", "key": regime, "count": count})
    for risk, count in sorted(leakage_dist.items()):
        materialization_rows.append({"dimension": "leakage_risk", "key": risk, "count": count})
    write_csv(REPORT_DIR / "entry_safe_regime_materialization_counts.csv", materialization_rows, ["dimension", "key", "count"])
    write_text(
        REPORT_DIR / "ENTRY_SAFE_REGIME_MATERIALIZATION_CN.md",
        "# Entry Safe Regime Materialization\n\n"
        + "\n".join(f"- window {k}: {v}" for k, v in sorted(by_window.items()))
        + "\n"
        + "\n".join(f"- bucket {k}: {v}" for k, v in sorted(by_bucket.items()))
        + "\n"
        + "\n".join(f"- regime {k}: {v}" for k, v in sorted(by_regime.items()))
        + "\n"
        + f"- lookahead_safe_count: {sum(1 for r in entry_safe_rows if r['lookahead_safe'])}\n"
        + f"- leakage_risk_distribution: {json.dumps(dict(leakage_dist), ensure_ascii=False)}\n"
        + f"- diagnostic_only_feature_count: {sum(len(r['diagnostic_only_features']) for r in entry_safe_rows)}\n"
        + f"- missing_feature_distribution: {json.dumps(dict(Counter(len(r['missing_features']) for r in entry_safe_rows)), ensure_ascii=False)}\n"
        + f"- original_regime_distribution: {json.dumps(dict(original_regime), ensure_ascii=False)}\n"
        + f"- entry_safe_regime_distribution: {json.dumps(dict(entry_safe_regime), ensure_ascii=False)}\n",
    )

    report_rows = []
    best_candidates = []
    for key, rows in sorted(grouped_rows.items()):
        variant, window, horizon, proof_unit = key
        metrics = compute_group_metrics(rows)
        verdict = row_verdict(metrics)
        report_row = {
            "variant_name": variant,
            "window": window,
            "horizon": horizon,
            "proof_unit_type": proof_unit,
            "sample_count": metrics["sample_count"],
            "retained_sample_count": metrics["retained_sample_count"],
            "baseline_p10": metrics["baseline_p10"],
            "baseline_p5": metrics["baseline_p5"],
            "baseline_p1": metrics["baseline_p1"],
            "filtered_p10": metrics["filtered_p10"],
            "filtered_p5": metrics["filtered_p5"],
            "filtered_p1": metrics["filtered_p1"],
            "tail_improvement_p10": metrics["tail_improvement_p10"],
            "tail_improvement_p5": metrics["tail_improvement_p5"],
            "tail_improvement_p1": metrics["tail_improvement_p1"],
            "opportunity_retention_rate": metrics["opportunity_retention_rate"],
            "false_quarantine_rate": metrics["false_quarantine_rate"],
            "missed_profit_rate": metrics["missed_profit_rate"],
            "worst_pool_contribution": metrics["worst_pool_contribution"],
            "data_quality_status": metrics["data_quality_status"],
            "leakage_risk": metrics["leakage_risk"],
            "verdict": verdict,
        }
        report_rows.append(report_row)
        if variant != "baseline_hold_all" and verdict in {"PROMISING", "WEAK"}:
            best_candidates.append(report_row)
    write_csv(
        REPORT_DIR / "entry_safe_regime_aware_counterfactual.csv",
        report_rows,
        [
            "variant_name", "window", "horizon", "proof_unit_type", "sample_count", "retained_sample_count",
            "baseline_p10", "baseline_p5", "baseline_p1", "filtered_p10", "filtered_p5", "filtered_p1",
            "tail_improvement_p10", "tail_improvement_p5", "tail_improvement_p1", "opportunity_retention_rate",
            "false_quarantine_rate", "missed_profit_rate", "worst_pool_contribution", "data_quality_status",
            "leakage_risk", "verdict",
        ],
    )
    write_text(
        REPORT_DIR / "ENTRY_SAFE_REGIME_AWARE_COUNTERFACTUAL_CN.md",
        "# Entry Safe Regime Aware Counterfactual\n\n"
        + "\n".join(
            f"- {r['variant_name']} / {r['window']} / {r['horizon']} / {r['proof_unit_type']}: retained={r['retained_sample_count']}, "
            f"tail={fmt(r['tail_improvement_p10'])}/{fmt(r['tail_improvement_p5'])}/{fmt(r['tail_improvement_p1'])}, "
            f"opp={fmt(r['opportunity_retention_rate'])}, false_q={fmt(r['false_quarantine_rate'])}, "
            f"missed={fmt(r['missed_profit_rate'])}, leakage={r['leakage_risk']}, verdict={r['verdict']}"
            for r in report_rows
        )
        + "\n",
    )

    best_candidates.sort(
        key=lambda r: (
            r["tail_improvement_p10"] or -999.0,
            r["tail_improvement_p5"] or -999.0,
            r["tail_improvement_p1"] or -999.0,
            r["opportunity_retention_rate"] or 0.0,
            -(r["false_quarantine_rate"] or 1.0),
        ),
        reverse=True,
    )
    entry_safe_best = best_candidates[0] if best_candidates else None

    leaky_final = load_json(inputs["leaky_final"])
    comparison_rows = []
    if entry_safe_best:
        comparison_rows.append(
            {
                "mode": "leaky_best",
                "best_variant_name": leaky_final["best_variant_name"],
                "best_window": leaky_final["best_window"],
                "best_horizon": leaky_final["best_horizon"],
                "best_proof_unit": leaky_final["best_proof_unit"],
                "retained_sample_count": leaky_final["retained_sample_count"],
                "tail_improvement_p10": leaky_final["tail_improvement_p10"],
                "tail_improvement_p5": leaky_final["tail_improvement_p5"],
                "tail_improvement_p1": leaky_final["tail_improvement_p1"],
                "opportunity_retention_rate": leaky_final["opportunity_retention_rate"],
                "false_quarantine_rate": leaky_final["false_quarantine_rate"],
                "missed_profit_rate": leaky_final["missed_profit_rate"],
                "lookahead_risk": "HIGH",
                "leakage_found": "yes",
                "review_ready": "yes",
            }
        )
        comparison_rows.append(
            {
                "mode": "entry_safe_best",
                "best_variant_name": entry_safe_best["variant_name"],
                "best_window": entry_safe_best["window"],
                "best_horizon": entry_safe_best["horizon"],
                "best_proof_unit": entry_safe_best["proof_unit_type"],
                "retained_sample_count": entry_safe_best["retained_sample_count"],
                "tail_improvement_p10": entry_safe_best["tail_improvement_p10"],
                "tail_improvement_p5": entry_safe_best["tail_improvement_p5"],
                "tail_improvement_p1": entry_safe_best["tail_improvement_p1"],
                "opportunity_retention_rate": entry_safe_best["opportunity_retention_rate"],
                "false_quarantine_rate": entry_safe_best["false_quarantine_rate"],
                "missed_profit_rate": entry_safe_best["missed_profit_rate"],
                "lookahead_risk": entry_safe_best["leakage_risk"],
                "leakage_found": "no" if entry_safe_best["leakage_risk"] in {"LOW", "MEDIUM"} else "yes",
                "review_ready": "yes" if entry_safe_best["verdict"] == "PROMISING" else "no",
            }
        )
    write_csv(REPORT_DIR / "leaky_vs_entry_safe_comparison.csv", comparison_rows, [
        "mode", "best_variant_name", "best_window", "best_horizon", "best_proof_unit", "retained_sample_count",
        "tail_improvement_p10", "tail_improvement_p5", "tail_improvement_p1", "opportunity_retention_rate",
        "false_quarantine_rate", "missed_profit_rate", "lookahead_risk", "leakage_found", "review_ready",
    ])
    if entry_safe_best:
        leaky_vs_safe_md = (
            f"- leaky_tail_improvement_p10/p5/p1: {fmt(leaky_final['tail_improvement_p10'])}/{fmt(leaky_final['tail_improvement_p5'])}/{fmt(leaky_final['tail_improvement_p1'])}\n"
            f"- entry_safe_tail_improvement_p10/p5/p1: {fmt(entry_safe_best['tail_improvement_p10'])}/{fmt(entry_safe_best['tail_improvement_p5'])}/{fmt(entry_safe_best['tail_improvement_p1'])}\n"
            f"- tail_improvement_mainly_from_leakage: {'yes' if (entry_safe_best['tail_improvement_p10'] or -1) < (leaky_final['tail_improvement_p10'] or -1) and (entry_safe_best['tail_improvement_p5'] or -1) < (leaky_final['tail_improvement_p5'] or -1) else 'no'}\n"
            f"- entry_safe_tail_improvement_still_exists: {'yes' if all((entry_safe_best[k] or 0) > 0 for k in ['tail_improvement_p10','tail_improvement_p5','tail_improvement_p1']) else 'no'}\n"
            f"- should_stop_regime_aware_if_no_tail_after_fix: {'yes' if not all((entry_safe_best[k] or 0) > 0 for k in ['tail_improvement_p10','tail_improvement_p5','tail_improvement_p1']) else 'no'}\n"
        )
    else:
        leaky_vs_safe_md = "- no entry-safe candidate passed minimum filters.\n"
    write_text(REPORT_DIR / "LEAKY_VS_ENTRY_SAFE_COMPARISON_CN.md", "# Leaky vs Entry Safe Comparison\n\n" + leaky_vs_safe_md)

    if entry_safe_best:
        best_variant_rows = [r for r in report_rows if r["variant_name"] == entry_safe_best["variant_name"]]
        positive_windows = sum(1 for r in best_variant_rows if r["window"] in WINDOWS and (r["tail_improvement_p10"] or 0) > 0 and (r["tail_improvement_p5"] or 0) > 0 and (r["tail_improvement_p1"] or 0) > 0)
        positive_horizons = sum(1 for r in best_variant_rows if r["window"] == entry_safe_best["window"] and (r["tail_improvement_p10"] or 0) > 0 and (r["tail_improvement_p5"] or 0) > 0 and (r["tail_improvement_p1"] or 0) > 0)
        only_data_stale = entry_safe_best["variant_name"] == "entry_safe_exclude_DATA_STALE_OR_INCOMPLETE"
        if entry_safe_best["leakage_risk"] == "LOW" and positive_windows >= 3 and positive_horizons >= 2 and (entry_safe_best["worst_pool_contribution"] or 1) <= 0.5 and (entry_safe_best["opportunity_retention_rate"] or 0) >= 0.7 and (entry_safe_best["false_quarantine_rate"] or 1) <= 0.2 and (entry_safe_best["missed_profit_rate"] or 1) <= 0.2 and not only_data_stale:
            robustness_status = "PASS"
            overfit_risk = "LOW"
        elif entry_safe_best["leakage_risk"] in {"LOW", "MEDIUM"} and positive_windows >= 2 and positive_horizons >= 2:
            robustness_status = "WARN"
            overfit_risk = "MEDIUM" if not only_data_stale else "HIGH"
        else:
            robustness_status = "FAIL"
            overfit_risk = "HIGH"
    else:
        robustness_status = "FAIL"
        overfit_risk = "HIGH"

    robustness_rows = []
    if entry_safe_best:
        for r in best_variant_rows:
            robustness_rows.append(
                {
                    "variant_name": r["variant_name"],
                    "window": r["window"],
                    "horizon": r["horizon"],
                    "proof_unit_type": r["proof_unit_type"],
                    "tail_improvement_p10": r["tail_improvement_p10"],
                    "tail_improvement_p5": r["tail_improvement_p5"],
                    "tail_improvement_p1": r["tail_improvement_p1"],
                    "retained_sample_count": r["retained_sample_count"],
                    "opportunity_retention_rate": r["opportunity_retention_rate"],
                    "false_quarantine_rate": r["false_quarantine_rate"],
                    "missed_profit_rate": r["missed_profit_rate"],
                    "worst_pool_contribution": r["worst_pool_contribution"],
                    "leakage_risk": r["leakage_risk"],
                }
            )
    write_csv(REPORT_DIR / "entry_safe_robustness_audit.csv", robustness_rows, [
        "variant_name", "window", "horizon", "proof_unit_type", "tail_improvement_p10", "tail_improvement_p5",
        "tail_improvement_p1", "retained_sample_count", "opportunity_retention_rate", "false_quarantine_rate",
        "missed_profit_rate", "worst_pool_contribution", "leakage_risk",
    ])
    write_text(
        REPORT_DIR / "ENTRY_SAFE_ROBUSTNESS_AUDIT_CN.md",
        "# Entry Safe Robustness Audit\n\n"
        f"- robustness_status: {robustness_status}\n"
        f"- overfit_risk: {overfit_risk}\n"
        f"- best_variant_name: {entry_safe_best['variant_name'] if entry_safe_best else ''}\n"
        f"- best_window: {entry_safe_best['window'] if entry_safe_best else ''}\n"
        f"- best_horizon: {entry_safe_best['horizon'] if entry_safe_best else ''}\n"
        f"- leakage_risk: {entry_safe_best['leakage_risk'] if entry_safe_best else ''}\n",
    )

    if entry_safe_best and all((entry_safe_best[k] or 0) > 0 for k in ["tail_improvement_p10", "tail_improvement_p5", "tail_improvement_p1"]) and entry_safe_best["leakage_risk"] in {"LOW", "MEDIUM"} and robustness_status in {"PASS", "WARN"} and (entry_safe_best["missed_profit_rate"] or 1) <= 0.25 and (entry_safe_best["false_quarantine_rate"] or 1) <= 0.2:
        recommended_next_stage = "POOL_REGIME_AWARE_SHORT_HOLD_REVIEW_V3"
        status = "PASS" if robustness_status == "PASS" else "WARN"
    elif entry_safe_best and entry_safe_best["variant_name"] in {"entry_safe_enter_HEALTHY_or_STABLE_FEE", "entry_safe_hybrid_regime_plus_signal_plus_fee"}:
        recommended_next_stage = "FEE_VELOCITY_EXIT_DEPTH_COUNTERFACTUAL_V1"
        status = "WARN"
    elif any(r["regime_primary"] == "DATA_STALE_OR_INCOMPLETE" for r in entry_safe_rows):
        recommended_next_stage = "POOL_REGIME_DATA_FIX" if not entry_safe_best or entry_safe_best["leakage_risk"] != "LOW" else "POOL_REGIME_AWARE_SHORT_HOLD_REVIEW_V3"
        status = "FAIL" if not entry_safe_best else "WARN"
    else:
        recommended_next_stage = "STOP_RESEARCH"
        status = "FAIL"

    decision = {
        "recommended_next_stage": recommended_next_stage,
        "entry_safe_best_variant": entry_safe_best["variant_name"] if entry_safe_best else "",
        "entry_safe_tail_improved": bool(entry_safe_best and all((entry_safe_best[k] or 0) > 0 for k in ["tail_improvement_p10", "tail_improvement_p5", "tail_improvement_p1"])),
        "lookahead_risk_after_fix": entry_safe_best["leakage_risk"] if entry_safe_best else "HIGH",
        "leakage_found_after_fix": False if entry_safe_best and entry_safe_best["leakage_risk"] in {"LOW", "MEDIUM"} else True,
    }
    write_json(REPORT_DIR / "pool_regime_rule_fix_decision.json", decision)
    write_text(
        REPORT_DIR / "POOL_REGIME_RULE_FIX_DECISION_CN.md",
        "# Pool Regime Rule Fix Decision\n\n"
        f"- recommended_next_stage: {recommended_next_stage}\n"
        f"- entry_safe_best_variant: {decision['entry_safe_best_variant']}\n"
        f"- entry_safe_tail_improved: {fmt(decision['entry_safe_tail_improved'])}\n"
        f"- leakage_found_after_fix: {fmt(decision['leakage_found_after_fix'])}\n"
        f"- lookahead_risk_after_fix: {decision['lookahead_risk_after_fix']}\n",
    )

    final_verdict = {
        "status": status,
        "stage": "POOL_REGIME_RULE_FIX_V1",
        "data_source": "vps_postgres",
        "db_ready": True,
        "entry_safe_classifier_built": True,
        "same_bucket_features_banned": True,
        "previous_closed_bucket_rule_applied": True,
        "leakage_found_after_fix": decision["leakage_found_after_fix"],
        "lookahead_risk_after_fix": decision["lookahead_risk_after_fix"],
        "entry_safe_best_variant": entry_safe_best["variant_name"] if entry_safe_best else "",
        "entry_safe_best_window": entry_safe_best["window"] if entry_safe_best else "",
        "entry_safe_best_horizon": entry_safe_best["horizon"] if entry_safe_best else "",
        "entry_safe_tail_improved": bool(entry_safe_best and all((entry_safe_best[k] or 0) > 0 for k in ["tail_improvement_p10", "tail_improvement_p5", "tail_improvement_p1"])),
        "entry_safe_tail_improvement_p10": entry_safe_best["tail_improvement_p10"] if entry_safe_best else None,
        "entry_safe_tail_improvement_p5": entry_safe_best["tail_improvement_p5"] if entry_safe_best else None,
        "entry_safe_tail_improvement_p1": entry_safe_best["tail_improvement_p1"] if entry_safe_best else None,
        "opportunity_retention_rate": entry_safe_best["opportunity_retention_rate"] if entry_safe_best else None,
        "false_quarantine_rate": entry_safe_best["false_quarantine_rate"] if entry_safe_best else None,
        "missed_profit_rate": entry_safe_best["missed_profit_rate"] if entry_safe_best else None,
        "robustness_status": robustness_status,
        "overfit_risk": overfit_risk,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": recommended_next_stage,
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final_verdict)
    write_text(
        REPORT_DIR / "ONEPAGE_CN.md",
        "# Pool Regime Rule Fix V1\n\n"
        f"- status: {status}\n"
        f"- entry_safe_classifier_built: yes\n"
        f"- same_bucket_features_banned: yes\n"
        f"- previous_closed_bucket_rule_applied: yes\n"
        f"- leakage_found_after_fix: {fmt(decision['leakage_found_after_fix'])}\n"
        f"- lookahead_risk_after_fix: {decision['lookahead_risk_after_fix']}\n"
        f"- entry_safe_best_variant: {entry_safe_best['variant_name'] if entry_safe_best else ''}\n"
        f"- entry_safe_best_window: {entry_safe_best['window'] if entry_safe_best else ''}\n"
        f"- entry_safe_best_horizon: {entry_safe_best['horizon'] if entry_safe_best else ''}\n"
        f"- entry_safe_tail_improved: {fmt(final_verdict['entry_safe_tail_improved'])}\n"
        f"- tail_improvement_p10/p5/p1: {fmt(final_verdict['entry_safe_tail_improvement_p10'])}/{fmt(final_verdict['entry_safe_tail_improvement_p5'])}/{fmt(final_verdict['entry_safe_tail_improvement_p1'])}\n"
        f"- opportunity_retention_rate: {fmt(final_verdict['opportunity_retention_rate'])}\n"
        f"- false_quarantine_rate: {fmt(final_verdict['false_quarantine_rate'])}\n"
        f"- missed_profit_rate: {fmt(final_verdict['missed_profit_rate'])}\n"
        f"- robustness_status: {robustness_status}\n"
        f"- overfit_risk: {overfit_risk}\n"
        f"- recommended_next_stage: {recommended_next_stage}\n"
        "- tiny_canary_allowed: no\n",
    )

    artifact_files = [
        "INPUT_ARTIFACT_AUDIT_CN.md",
        "input_artifact_audit.json",
        "VPS_DB_QUICK_CHECK_CN.md",
        "ENTRY_SAFE_REGIME_FEATURE_POLICY_CN.md",
        "entry_safe_regime_feature_policy.json",
        "ENTRY_SAFE_REGIME_SCHEMA_CN.md",
        "entry_safe_regime_schema.json",
        "ENTRY_SAFE_REGIME_MATERIALIZATION_CN.md",
        "entry_safe_regime_materialization_counts.csv",
        "ENTRY_SAFE_REGIME_AWARE_COUNTERFACTUAL_CN.md",
        "entry_safe_regime_aware_counterfactual.csv",
        "LEAKY_VS_ENTRY_SAFE_COMPARISON_CN.md",
        "leaky_vs_entry_safe_comparison.csv",
        "ENTRY_SAFE_ROBUSTNESS_AUDIT_CN.md",
        "entry_safe_robustness_audit.csv",
        "POOL_REGIME_RULE_FIX_DECISION_CN.md",
        "pool_regime_rule_fix_decision.json",
        "FINAL_VERDICT.json",
        "ONEPAGE_CN.md",
        "ARTIFACT_INDEX.md",
        "pool_regime_rule_fix_v1_readonly.py",
    ]
    write_text(REPORT_DIR / "ARTIFACT_INDEX.md", "# Artifact Index\n\n" + "\n".join(f"- {x}" for x in artifact_files) + "\n")


if __name__ == "__main__":
    main()
