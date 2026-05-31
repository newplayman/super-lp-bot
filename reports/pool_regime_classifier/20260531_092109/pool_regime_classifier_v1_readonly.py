#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import shlex
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values


REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
REPORT_DIR = REPO_ROOT / "reports" / "pool_regime_classifier" / "20260531_085529"
INPUT_RISK_DIR = REPO_ROOT / "reports" / "risk_signal_definition_fix" / "20260531_080614"
P0_DIR = REPO_ROOT / "reports" / "risk_aware_short_hold" / "20260531_073906"
REGIME_TABLE = "pool_regime_classifier_v1"
LOOKBACK_LABELS = [
    ("recent_24h", 24),
    ("recent_48h", 48),
    ("recent_72h", 72),
    ("recent_7d", 168),
]
HORIZONS = ["15m", "30m", "1h", "2h"]
BUCKET_SECONDS = 15 * 60
MAX_LOOKBACK_SECONDS = 7 * 24 * 3600


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
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


def build_token_pair(pool_id: str, pools: dict[str, dict[str, Any]], meta: dict[str, dict[str, Any]]) -> str:
    m = meta.get(pool_id) or {}
    if m.get("token0_symbol") and m.get("token1_symbol"):
        return f"{m['token0_symbol']}/{m['token1_symbol']}"
    if m.get("token0") and m.get("token1"):
        return f"{m['token0'][:8]}/{m['token1'][:8]}"
    p = pools.get(pool_id) or {}
    if p.get("token0") and p.get("token1"):
        return f"{p['token0'][:8]}/{p['token1'][:8]}"
    return pool_id


def parse_ts(v):
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


def fmt_num(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return ""
        return f"{v:.10f}".rstrip("0").rstrip(".")
    return str(v)


def parse_num(v):
    if v in (None, "", "null", "None"):
        return None
    try:
        return float(v)
    except Exception:
        return None


def median(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    vals = sorted(vals)
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def percentile(values, p):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    vals = sorted(vals)
    idx = max(0, min(len(vals) - 1, int(round((len(vals) - 1) * p))))
    return vals[idx]


def sample_sufficiency(n: int) -> str:
    if n < 30:
        return "INSUFFICIENT"
    if n < 100:
        return "EARLY"
    if n < 300:
        return "PRELIMINARY"
    return "USABLE"


def bucket_floor(ts: int, bucket_seconds: int = BUCKET_SECONDS) -> int:
    return ts - (ts % bucket_seconds)


def bucket_label(age_hours: float) -> str:
    if age_hours <= 24:
        return "recent_24h"
    if age_hours <= 48:
        return "recent_48h"
    if age_hours <= 72:
        return "recent_72h"
    return "recent_7d"


def pct_change(new, old):
    if new is None or old in (None, 0):
        return None
    return (new - old) / old * 100.0


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def safe_depth_from_slippage(notional: float, slippage: float | None, target: float) -> float | None:
    if slippage is None or slippage <= 0:
        return None
    return notional * target / slippage


def load_input_artifacts() -> dict[str, dict[str, Any]]:
    artifacts = {
        "risk_signal_definition_fix_final": INPUT_RISK_DIR / "FINAL_VERDICT.json",
        "risk_signal_fix_next_stage": INPUT_RISK_DIR / "RISK_SIGNAL_FIX_NEXT_STAGE_DECISION_CN.md",
        "risk_signal_ablation": INPUT_RISK_DIR / "RISK_SIGNAL_ABLATION_CN.md",
        "risk_signal_ablation_csv": INPUT_RISK_DIR / "risk_signal_ablation.csv",
        "risk_signal_combo_grid": INPUT_RISK_DIR / "RISK_SIGNAL_COMBO_GRID_CN.md",
        "risk_signal_combo_grid_csv": INPUT_RISK_DIR / "risk_signal_combo_grid.csv",
        "quarantine_vs_exit_timing": INPUT_RISK_DIR / "QUARANTINE_VS_EXIT_TIMING_CN.md",
        "quarantine_vs_exit_timing_csv": INPUT_RISK_DIR / "quarantine_vs_exit_timing.csv",
        "risk_signal_definition_v2": INPUT_RISK_DIR / "RISK_SIGNAL_DEFINITION_V2_CN.md",
        "risk_signal_definition_v2_json": INPUT_RISK_DIR / "risk_signal_definition_v2.json",
        "risk_aware_short_hold_preview": INPUT_RISK_DIR / "RISK_AWARE_SHORT_HOLD_V2_PREVIEW_CN.md",
        "risk_aware_short_hold_preview_csv": INPUT_RISK_DIR / "risk_aware_short_hold_v2_preview.csv",
    }
    return {name: {"path": str(path), "exists": path.exists()} for name, path in artifacts.items()}


def quick_check_db(cur) -> dict[str, Any]:
    cur.execute("select current_database(), current_user")
    db, user = cur.fetchone()
    return {"db_name": db, "db_user": user}


def load_pool_metadata(cur):
    pools = {r["pool_id"]: dict(r) for r in q(cur, "select pool_id, chain, protocol, token0, token1, fee_bps, tier, tvl_usd, vol_24h, fee_apr_24h from pools")}
    meta = {r["pool_id"]: dict(r) for r in q(cur, "select pool_id, token0, token1, token0_symbol, token1_symbol, token0_decimals, token1_decimals from pool_token_metadata")}
    return pools, meta


def load_latest_scores(cur):
    rows = q(
        cur,
        """
        select distinct on (pool_id) pool_id, block_time, score_json
        from pool_score_history
        order by pool_id, block_time desc
        """,
    )
    out = {}
    for r in rows:
        try:
            score = json.loads(r["score_json"] or "{}")
        except Exception:
            score = {}
        out[r["pool_id"]] = {
            "block_time": parse_ts(r["block_time"]),
            "FeeAPRScore": parse_num(score.get("FeeAPRScore")),
            "TvlScore": parse_num(score.get("TvlScore")),
            "VolScore": parse_num(score.get("VolScore")),
            "VolatilityScore": parse_num(score.get("VolatilityScore")),
            "SecurityScore": parse_num(score.get("SecurityScore")),
            "Total": parse_num(score.get("Total")),
        }
    return out


def load_marks(cur, pool_ids: list[str]):
    if not pool_ids:
        return {}
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
        pid = r["pool_id"]
        ts = int(r["mark_time"])
        grouped[pid][ts].append(r)
    series = {}
    for pid, by_ts in grouped.items():
        items = []
        for ts, rows2 in sorted(by_ts.items()):
            vals = [parse_num(x["valuation_usd"]) for x in rows2]
            tvls = [parse_num(x["current_tvl_usd"]) for x in rows2]
            vols = [parse_num(x["current_vol24h_usd"]) for x in rows2]
            prices = [parse_num(x["price_change_pct"]) for x in rows2]
            amts = [parse_num(x["amount_usd"]) for x in rows2]
            sources = [x.get("source") or "" for x in rows2 if x.get("source")]
            statuses = [x.get("status") or "" for x in rows2 if x.get("status")]
            items.append(
                {
                    "mark_time": ts,
                    "mark_dt": datetime.fromtimestamp(ts, tz=timezone.utc),
                    "valuation_usd": median(vals),
                    "current_tvl_usd": median(tvls),
                    "current_vol24h_usd": median(vols),
                    "price_change_pct": median(prices),
                    "amount_usd": median(amts),
                    "source": ",".join(sorted(set(sources))) if sources else "",
                    "status": ",".join(sorted(set(statuses))) if statuses else "",
                }
            )
        series[pid] = items
    return series


def series_values(series, field):
    return [s[field] for s in series if s.get(field) is not None]


def find_latest_index(ts_list, target_ts):
    return bisect_right(ts_list, target_ts) - 1


def feature_for_bucket(pool_id: str, bucket_end_ts: int, series: list[dict], pool: dict, score: dict, token_pair: str) -> dict[str, Any]:
    ts_list = [s["mark_time"] for s in series]
    idx = find_latest_index(ts_list, bucket_end_ts)
    current = series[idx] if idx >= 0 else None
    current_age = None
    if current:
        current_age = bucket_end_ts - current["mark_time"]

    def value_at(offset_seconds: int, field: str):
        target = bucket_end_ts - offset_seconds
        j = find_latest_index(ts_list, target)
        if j < 0:
            return None
        return series[j].get(field)

    val_now = current.get("valuation_usd") if current else None
    tvl_now = current.get("current_tvl_usd") if current else None
    vol_now = current.get("current_vol24h_usd") if current else None
    price_now = current.get("price_change_pct") if current else None

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

    slippage_10usd = None
    slippage_20usd = None
    slippage_50usd = None
    exit_depth_10usd = None
    exit_depth_20usd = None
    exit_depth_50usd = None
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

    security_score = parse_num(score.get("SecurityScore"))
    concentration_proxy = None
    if security_score is not None:
        concentration_proxy = clamp(100.0 - security_score, 0.0, 100.0)

    stale_data_flag = current is None or current_age is None or current_age > 5 * 60
    pool_mark_gap = current_age if current_age is not None else None
    missing_core = sum(v is None for v in [val_now, tvl_now, vol_now, price_now, price_move_5m, price_move_15m, price_move_30m, price_move_1h, volume_change_15m, volume_change_30m, volume_change_1h, tvl_change_1h, fee_proxy, fee_velocity_proxy, slippage_10usd, slippage_20usd, slippage_50usd, exit_depth_10usd, exit_depth_20usd, exit_depth_50usd])
    missing_count = missing_core + (1 if concentration_proxy is None else 0)
    data_quality_score = max(0.0, 100.0 - missing_count * 6.0 - (25.0 if stale_data_flag else 0.0))

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
    concentration_high = bool(concentration_proxy is not None and concentration_proxy >= 70.0)
    concentration_extreme = bool(concentration_proxy is not None and concentration_proxy >= 85.0)
    data_stale_or_incomplete = bool(stale_data_flag or data_quality_score < 70.0)

    exit_depth_score = 0.0
    if exit_depth_50usd is not None:
        exit_depth_score = clamp((exit_depth_50usd / 500.0) * 100.0, 0.0, 100.0)
    volatility_score = 100.0
    if price_move_1h is not None:
        volatility_score = clamp(100.0 - max(abs(price_move_5m or 0.0) / 2.0, abs(price_move_15m or 0.0) / 4.0, abs(price_move_30m or 0.0) / 6.0, abs(price_move_1h or 0.0) / 10.0) * 100.0, 0.0, 100.0)
    volume_score = 100.0
    if volume_change_1h is not None:
        vscore = 100.0
        if volume_collapse:
            vscore -= 50.0
        if abnormal_volume_spike:
            vscore -= 25.0
        if volume_change_1h > -10.0 and volume_change_1h < 50.0:
            vscore += 5.0
        volume_score = clamp(vscore, 0.0, 100.0)
    tvl_score = 100.0
    if tvl_change_1h is not None:
        tvl_score = clamp(100.0 - max(0.0, -tvl_change_1h) * 2.5, 0.0, 100.0)
    fee_proxy_score = 0.0
    if fee_velocity_proxy is not None:
        fee_proxy_score = clamp(fee_velocity_proxy * 4000.0, 0.0, 100.0)
    data_quality_score_score = clamp(data_quality_score, 0.0, 100.0)
    concentration_score = 100.0 - concentration_proxy if concentration_proxy is not None else 50.0

    risk_score = 100.0 - (
        0.30 * exit_depth_score
        + 0.22 * volatility_score
        + 0.18 * volume_score
        + 0.12 * tvl_score
        + 0.10 * data_quality_score_score
        + 0.05 * fee_proxy_score
        + 0.03 * concentration_score
    )
    risk_score = clamp(risk_score, 0.0, 100.0)

    hits = []
    if data_stale_or_incomplete:
        hits.append("DATA_STALE_OR_INCOMPLETE")
    if concentration_extreme:
        hits.append("WHALE_OR_HOLDER_CONCENTRATED")
    if exit_depth_thin:
        hits.append("EXIT_DEPTH_THIN")
    if tvl_drop:
        hits.append("TVL_DROP")
    if volume_collapse:
        hits.append("VOLUME_COLLAPSE")
    if abnormal_volume_spike and (price_spike_down or price_spike_up):
        hits.append("TOXIC_FLOW")
    if price_spike_volatile and not (tvl_drop or volume_collapse or exit_depth_thin or concentration_extreme):
        hits.append("PRICE_SPIKE_VOLATILE")
    if not hits and fee_velocity_proxy is not None and fee_velocity_proxy >= 0.01 and abs(price_move_15m or 0.0) <= 1.5 and abs(price_move_30m or 0.0) <= 2.0 and not volume_collapse and not tvl_drop:
        hits.append("STABLE_FEE")
    if not hits and exit_depth_50usd is not None and exit_depth_50usd >= 500.0 and abs(price_move_15m or 0.0) <= 1.5 and abs(price_move_30m or 0.0) <= 2.5 and not volume_collapse and not tvl_drop:
        hits.append("HEALTHY_SHORT_HOLD")
    if not hits:
        hits.append("UNKNOWN")

    primary = hits[0]
    secondary = hits[1] if len(hits) > 1 else ""
    should_enter = primary in {"HEALTHY_SHORT_HOLD", "STABLE_FEE"} and risk_score <= 35.0
    should_quarantine = primary in {
        "TOXIC_FLOW",
        "EXIT_DEPTH_THIN",
        "VOLUME_COLLAPSE",
        "TVL_DROP",
        "PRICE_SPIKE_VOLATILE",
        "WHALE_OR_HOLDER_CONCENTRATED",
        "DATA_STALE_OR_INCOMPLETE",
    }
    should_research_only = primary in {"VOLATILE_BUT_LIQUID", "UNKNOWN"} or (not should_enter and not should_quarantine)

    if primary == "UNKNOWN" and not data_stale_or_incomplete and not concentration_extreme and not exit_depth_thin:
        if fee_velocity_proxy is not None and fee_velocity_proxy >= 0.005 and abs(price_move_15m or 0.0) <= 2.0:
            primary = "VOLATILE_BUT_LIQUID"
            should_research_only = True
        elif abs(price_move_15m or 0.0) <= 1.0 and abs(price_move_30m or 0.0) <= 1.5:
            primary = "HEALTHY_SHORT_HOLD"
            should_enter = True
            should_research_only = False

    return {
        "pool_id": pool_id,
        "token_pair": token_pair,
        "bucket_start": bucket_floor(bucket_end_ts) - BUCKET_SECONDS,
        "bucket_end": bucket_floor(bucket_end_ts),
        "bucket_end_dt": datetime.fromtimestamp(bucket_end_ts, tz=timezone.utc),
        "window": bucket_label((datetime.now(timezone.utc) - datetime.fromtimestamp(bucket_end_ts, tz=timezone.utc)).total_seconds() / 3600.0),
        "price_move_5m": price_move_5m,
        "price_move_15m": price_move_15m,
        "price_move_30m": price_move_30m,
        "price_move_1h": price_move_1h,
        "volume_change_15m": volume_change_15m,
        "volume_change_30m": volume_change_30m,
        "volume_change_1h": volume_change_1h,
        "tvl_change_1h": tvl_change_1h,
        "fee_proxy": fee_proxy,
        "fee_velocity_proxy": fee_velocity_proxy,
        "exit_depth_10usd": exit_depth_10usd,
        "exit_depth_20usd": exit_depth_20usd,
        "exit_depth_50usd": exit_depth_50usd,
        "slippage_10usd": slippage_10usd,
        "slippage_20usd": slippage_20usd,
        "slippage_50usd": slippage_50usd,
        "trader_concentration": concentration_proxy,
        "holder_concentration": concentration_proxy,
        "stale_data_flag": stale_data_flag,
        "pool_mark_gap": pool_mark_gap,
        "abnormal_volume_spike": abnormal_volume_spike,
        "volume_collapse": volume_collapse,
        "price_spike_up": price_spike_up,
        "price_spike_down": price_spike_down,
        "regime_primary": primary,
        "regime_secondary": secondary,
        "regime_confidence": "high" if data_quality_score_score >= 80 and primary != "UNKNOWN" else "medium" if data_quality_score_score >= 60 else "low",
        "should_enter": should_enter,
        "should_quarantine": should_quarantine,
        "should_research_only": should_research_only,
        "risk_score": risk_score,
        "exit_depth_score": exit_depth_score,
        "volatility_score": volatility_score,
        "volume_score": volume_score,
        "tvl_score": tvl_score,
        "data_quality_score": data_quality_score_score,
        "fee_proxy_score": fee_proxy_score,
        "rule_hits": hits,
        "missing_features": [
            k
            for k, v in [
                ("price_move_5m", price_move_5m),
                ("price_move_15m", price_move_15m),
                ("price_move_30m", price_move_30m),
                ("price_move_1h", price_move_1h),
                ("volume_change_15m", volume_change_15m),
                ("volume_change_30m", volume_change_30m),
                ("volume_change_1h", volume_change_1h),
                ("tvl_change_1h", tvl_change_1h),
                ("fee_proxy", fee_proxy),
                ("fee_velocity_proxy", fee_velocity_proxy),
                ("exit_depth_10usd", exit_depth_10usd),
                ("exit_depth_20usd", exit_depth_20usd),
                ("exit_depth_50usd", exit_depth_50usd),
                ("slippage_10usd", slippage_10usd),
                ("slippage_20usd", slippage_20usd),
                ("slippage_50usd", slippage_50usd),
                ("trader_concentration", concentration_proxy),
                ("holder_concentration", concentration_proxy),
            ]
            if v is None
        ],
        "data_quality_status": "ok" if data_quality_score_score >= 70 and not stale_data_flag else "warn" if data_quality_score_score >= 50 else "bad",
        "current_security_score": security_score,
    }


def materialize_classifier(cur, rows: list[dict[str, Any]], run_id: str) -> None:
    cur.execute(f"drop table if exists {REGIME_TABLE}")
    cur.execute(
        f"""
        create table if not exists {REGIME_TABLE} (
            run_id text not null,
            pool_id text not null,
            token_pair text not null,
            bucket_start timestamptz not null,
            bucket_end timestamptz not null,
            window_label text not null,
            regime_primary text not null,
            regime_secondary text not null,
            regime_confidence text not null,
            should_enter boolean not null,
            should_quarantine boolean not null,
            should_research_only boolean not null,
            risk_score double precision,
            exit_depth_score double precision,
            volatility_score double precision,
            volume_score double precision,
            tvl_score double precision,
            data_quality_score double precision,
            fee_proxy_score double precision,
            rule_hits text,
            missing_features text,
            created_at timestamptz default now()
        )
        """
    )
    cur.execute(f"delete from {REGIME_TABLE} where run_id = %s", (run_id,))
    values = [
        (
            run_id,
            row["pool_id"],
            row["token_pair"],
            row["bucket_start_dt"],
            row["bucket_end_dt"],
            row["window"],
            row["regime_primary"],
            row["regime_secondary"],
            row["regime_confidence"],
            row["should_enter"],
            row["should_quarantine"],
            row["should_research_only"],
            row["risk_score"],
            row["exit_depth_score"],
            row["volatility_score"],
            row["volume_score"],
            row["tvl_score"],
            row["data_quality_score"],
            row["fee_proxy_score"],
            json.dumps(row["rule_hits"], ensure_ascii=False),
            json.dumps(row["missing_features"], ensure_ascii=False),
            datetime.now(timezone.utc),
        )
        for row in rows
    ]
    insert_sql = f"""
        insert into {REGIME_TABLE} (
            run_id, pool_id, token_pair, bucket_start, bucket_end, window_label,
            regime_primary, regime_secondary, regime_confidence,
            should_enter, should_quarantine, should_research_only,
            risk_score, exit_depth_score, volatility_score, volume_score, tvl_score,
            data_quality_score, fee_proxy_score, rule_hits, missing_features, created_at
        ) values %s
    """
    execute_values(
        cur,
        insert_sql,
        values,
        template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        page_size=1000,
    )


def bucketize_feature_rows(pools, meta, scores, series, run_id):
    now = datetime.now(timezone.utc)
    max_age = timedelta(seconds=MAX_LOOKBACK_SECONDS)
    rows = []
    for pool_id, marks in series.items():
        if not marks:
            continue
        token_pair = build_token_pair(pool_id, pools, meta)
        start_ts = max(marks[0]["mark_time"], int((now - max_age).timestamp()))
        end_ts = int(now.timestamp())
        # align to 15m buckets
        start_bucket = bucket_floor(start_ts)
        end_bucket = bucket_floor(end_ts)
        for bucket_end in range(start_bucket + BUCKET_SECONDS, end_bucket + 1, BUCKET_SECONDS):
            row = feature_for_bucket(pool_id, bucket_end, marks, pools.get(pool_id, {}), scores.get(pool_id, {}), token_pair)
            row["bucket_start_dt"] = datetime.fromtimestamp(row["bucket_start"], tz=timezone.utc)
            row["bucket_end_dt"] = datetime.fromtimestamp(row["bucket_end"], tz=timezone.utc)
            rows.append(row)
    return rows


def build_feature_coverage(rows: list[dict]) -> dict[str, Any]:
    feature_names = [
        "price_move_5m",
        "price_move_15m",
        "price_move_30m",
        "price_move_1h",
        "volume_change_15m",
        "volume_change_30m",
        "volume_change_1h",
        "tvl_change_1h",
        "fee_proxy",
        "fee_velocity_proxy",
        "exit_depth_10usd",
        "exit_depth_20usd",
        "exit_depth_50usd",
        "slippage_10usd",
        "slippage_20usd",
        "slippage_50usd",
        "trader_concentration",
        "holder_concentration",
    ]
    coverage = {}
    total = len(rows)
    for name in feature_names:
        coverage[name] = {
            "present": sum(1 for r in rows if r.get(name) is not None),
            "missing": sum(1 for r in rows if r.get(name) is None),
            "coverage_rate": (sum(1 for r in rows if r.get(name) is not None) / total) if total else 0,
        }
    return {
        "total_rows": total,
        "feature_coverage": coverage,
        "per_window_row_count": Counter(r["window"] for r in rows),
        "per_pool_row_count": Counter(r["pool_id"] for r in rows),
    }


def classify_samples_by_regime(samples: list[dict], regime_rows: list[dict]) -> list[dict]:
    regime_lookup = {(r["pool_id"], r["bucket_start"]): r for r in regime_rows}
    out = []
    for s in samples:
        if s.get("proof_unit_type") != "pool_window":
            continue
        start_ts = parse_ts(s["start_time"])
        if not start_ts:
            continue
        bucket = datetime.fromtimestamp(bucket_floor(int(start_ts.timestamp())), tz=timezone.utc)
        key = (s["pool_id"], int(bucket.timestamp()))
        regime = regime_lookup.get(key)
        if not regime:
            continue
        row = dict(s)
        row["sample_window"] = bucket_label((datetime.now(timezone.utc) - start_ts).total_seconds() / 3600.0)
        row["regime_primary"] = regime["regime_primary"]
        row["regime_secondary"] = regime["regime_secondary"]
        row["regime_confidence"] = regime["regime_confidence"]
        row["should_enter"] = regime["should_enter"]
        row["should_quarantine"] = regime["should_quarantine"]
        row["risk_score"] = regime["risk_score"]
        row["fee_proxy_score"] = regime["fee_proxy_score"]
        row["exit_depth_score"] = regime["exit_depth_score"]
        row["volatility_score"] = regime["volatility_score"]
        row["volume_score"] = regime["volume_score"]
        row["tvl_score"] = regime["tvl_score"]
        row["data_quality_score"] = regime["data_quality_score"]
        row["hold_pnl"] = parse_num(s["hold_to_horizon_pnl_pct"])
        row["risk_exit_pnl"] = parse_num(s["risk_aware_exit_pnl_pct"])
        row["no_entry_quarantine_pnl"] = parse_num(s["no_entry_quarantine_pnl_pct"])
        row["false_quarantine_flag"] = bool(regime["should_quarantine"] and row["hold_pnl"] is not None and row["hold_pnl"] > 0)
        row["missed_profit_flag"] = bool(regime["should_quarantine"] and row["hold_pnl"] is not None and row["hold_pnl"] > 0)
        row["quarantine_avoided_loss_flag"] = bool(regime["should_quarantine"] and row["hold_pnl"] is not None and row["hold_pnl"] < 0)
        row["is_valid"] = s["data_quality_status"] == "ok" and s["hold_to_horizon_pnl_pct"] is not None
        row["bucket_start"] = bucket
        out.append(row)
    return out


def summarize_regime_audit(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r["regime_primary"], r["sample_window"], r["horizon"])].append(r)
    out = []
    for (regime, window, horizon), bucket_rows in sorted(grouped.items()):
        hold_vals = [r["hold_pnl"] for r in bucket_rows if r["hold_pnl"] is not None]
        risk_vals = [r["risk_exit_pnl"] for r in bucket_rows if r["risk_exit_pnl"] is not None]
        valid = [r for r in bucket_rows if r["is_valid"]]
        q_rows = [r for r in bucket_rows if r["should_quarantine"]]
        q_avoided = sum(1 for r in q_rows if r["hold_pnl"] is not None and r["hold_pnl"] < 0)
        false_q = sum(1 for r in q_rows if r["hold_pnl"] is not None and r["hold_pnl"] > 0)
        opportunity_count = sum(1 for r in bucket_rows if r["hold_pnl"] is not None and r["hold_pnl"] > 0)
        missed_profit = sum(1 for r in q_rows if r["hold_pnl"] is not None and r["hold_pnl"] > 0)
        worst_pool = Counter()
        for r in bucket_rows:
            loss = -(r["hold_pnl"] or 0.0)
            if loss > 0:
                worst_pool[r["pool_id"]] += loss
        tail_status = "INSUFFICIENT"
        if len(valid) >= 30:
            p10 = percentile(hold_vals, 0.1)
            p5 = percentile(hold_vals, 0.05)
            p1 = percentile(hold_vals, 0.01)
            if p10 is not None and p5 is not None and p1 is not None:
                if p10 > -0.002 and p5 > -0.003 and p1 > -0.02:
                    tail_status = "OK"
                elif p10 > -0.01 and p5 > -0.015:
                    tail_status = "WARN"
                else:
                    tail_status = "FAIL"
        out.append(
            {
                "regime": regime,
                "window": window,
                "horizon": horizon,
                "sample_count": len(bucket_rows),
                "valid_count": len(valid),
                "hold_median": median(hold_vals),
                "hold_p10": percentile(hold_vals, 0.1),
                "hold_p5": percentile(hold_vals, 0.05),
                "hold_p1": percentile(hold_vals, 0.01),
                "risk_exit_p10": percentile(risk_vals, 0.1),
                "quarantine_avoided_loss_count": q_avoided,
                "false_quarantine_rate": (false_q / len(q_rows)) if q_rows else None,
                "missed_profit_rate": (missed_profit / opportunity_count) if opportunity_count else None,
                "worst_pool_contribution": (max(worst_pool.values()) / sum(worst_pool.values())) if worst_pool else None,
                "tail_status": tail_status,
            }
        )
    return out


def apply_filter(sample: dict, filter_name: str) -> bool:
    primary = sample["regime_primary"]
    risk_score = sample["risk_score"]
    if filter_name == "enter_only_HEALTHY_SHORT_HOLD":
        return primary == "HEALTHY_SHORT_HOLD"
    if filter_name == "enter_HEALTHY_or_STABLE_FEE":
        return primary in {"HEALTHY_SHORT_HOLD", "STABLE_FEE"}
    if filter_name == "exclude_TOXIC_FLOW":
        return primary != "TOXIC_FLOW"
    if filter_name == "exclude_EXIT_DEPTH_THIN":
        return primary != "EXIT_DEPTH_THIN"
    if filter_name == "exclude_PRICE_SPIKE_VOLATILE":
        return primary != "PRICE_SPIKE_VOLATILE"
    if filter_name == "exclude_DATA_STALE_OR_INCOMPLETE":
        return primary != "DATA_STALE_OR_INCOMPLETE"
    if filter_name == "exclude_all_bad_regimes":
        return primary in {"HEALTHY_SHORT_HOLD", "STABLE_FEE", "VOLATILE_BUT_LIQUID"}
    if filter_name == "quarantine_first_price_volume_depth_baseline":
        return primary not in {"PRICE_SPIKE_VOLATILE", "VOLUME_COLLAPSE", "TVL_DROP", "EXIT_DEPTH_THIN", "DATA_STALE_OR_INCOMPLETE", "TOXIC_FLOW"}
    if filter_name == "regime_score_threshold_loose":
        return risk_score <= 35.0
    if filter_name == "regime_score_threshold_strict":
        return risk_score <= 20.0
    raise KeyError(filter_name)


def filter_backtest(samples: list[dict]) -> list[dict]:
    filters = [
        "enter_only_HEALTHY_SHORT_HOLD",
        "enter_HEALTHY_or_STABLE_FEE",
        "exclude_TOXIC_FLOW",
        "exclude_EXIT_DEPTH_THIN",
        "exclude_PRICE_SPIKE_VOLATILE",
        "exclude_DATA_STALE_OR_INCOMPLETE",
        "exclude_all_bad_regimes",
        "quarantine_first_price_volume_depth_baseline",
        "regime_score_threshold_loose",
        "regime_score_threshold_strict",
    ]
    grouped = defaultdict(list)
    for r in samples:
        grouped[(r["sample_window"], r["horizon"])].append(r)
    out = []
    for filter_name in filters:
        for (window, horizon), bucket_rows in sorted(grouped.items()):
            kept = [r for r in bucket_rows if apply_filter(r, filter_name)]
            filtered = [r for r in bucket_rows if not apply_filter(r, filter_name)]
            before_hold = [r["hold_pnl"] for r in bucket_rows if r["hold_pnl"] is not None]
            after_hold = [r["hold_pnl"] for r in kept if r["hold_pnl"] is not None]
            opportunity_count = sum(1 for r in bucket_rows if r["hold_pnl"] is not None and r["hold_pnl"] > 0)
            retained_opportunity_count = sum(1 for r in kept if r["hold_pnl"] is not None and r["hold_pnl"] > 0)
            filtered_opportunity_count = sum(1 for r in filtered if r["hold_pnl"] is not None and r["hold_pnl"] > 0)
            loss_count = sum(1 for r in bucket_rows if r["hold_pnl"] is not None and r["hold_pnl"] < 0)
            filtered_loss_count = sum(1 for r in filtered if r["hold_pnl"] is not None and r["hold_pnl"] < 0)
            worst_pool = Counter()
            for r in kept:
                loss = -(r["hold_pnl"] or 0.0)
                if loss > 0:
                    worst_pool[r["pool_id"]] += loss
            if len(kept) >= 30:
                verdict = "PROMISING"
            elif len(kept) >= 10:
                verdict = "WEAK"
            else:
                verdict = "INSUFFICIENT"
            tail_improvement_p10 = (percentile(after_hold, 0.1) - percentile(before_hold, 0.1)) if after_hold and before_hold else None
            tail_improvement_p5 = (percentile(after_hold, 0.05) - percentile(before_hold, 0.05)) if after_hold and before_hold else None
            tail_improvement_p1 = (percentile(after_hold, 0.01) - percentile(before_hold, 0.01)) if after_hold and before_hold else None
            out.append(
                {
                    "filter_name": filter_name,
                    "window": window,
                    "horizon": horizon,
                    "before_sample_count": len(bucket_rows),
                    "after_sample_count": len(kept),
                    "filtered_out_count": len(filtered),
                    "hold_p10_before": percentile(before_hold, 0.1),
                    "hold_p10_after": percentile(after_hold, 0.1),
                    "hold_p5_before": percentile(before_hold, 0.05),
                    "hold_p5_after": percentile(after_hold, 0.05),
                    "hold_p1_before": percentile(before_hold, 0.01),
                    "hold_p1_after": percentile(after_hold, 0.01),
                    "median_before": median(before_hold),
                    "median_after": median(after_hold),
                    "false_quarantine_rate": (filtered_opportunity_count / len(filtered)) if filtered else None,
                    "missed_profit_rate": (filtered_opportunity_count / opportunity_count) if opportunity_count else None,
                    "opportunity_retention_rate": (retained_opportunity_count / opportunity_count) if opportunity_count else None,
                    "loss_avoidance_rate": (filtered_loss_count / loss_count) if loss_count else None,
                    "worst_pool_contribution_after": (max(worst_pool.values()) / sum(worst_pool.values())) if worst_pool else None,
                    "tail_improvement_p10": tail_improvement_p10,
                    "tail_improvement_p5": tail_improvement_p5,
                    "tail_improvement_p1": tail_improvement_p1,
                    "verdict": verdict,
                }
            )
    return out


def choose_best_filter(rows: list[dict]) -> dict[str, Any]:
    scored = []
    for r in rows:
        if r["after_sample_count"] < 100:
            continue
        if r["tail_improvement_p10"] is None or r["tail_improvement_p5"] is None or r["tail_improvement_p1"] is None:
            continue
        if r["tail_improvement_p10"] <= 0 or r["tail_improvement_p5"] <= 0 or r["tail_improvement_p1"] <= 0:
            continue
        if r["false_quarantine_rate"] is not None and r["false_quarantine_rate"] > 0.5:
            continue
        if r["missed_profit_rate"] is not None and r["missed_profit_rate"] > 0.5:
            continue
        if r["worst_pool_contribution_after"] is not None and r["worst_pool_contribution_after"] > 0.6:
            continue
        scored.append(r)
    if not scored:
        return {
            "best_filter_name": "",
            "best_window": "",
            "best_horizon": "",
            "sample_count_after": 0,
            "tail_improvement_p10": None,
            "tail_improvement_p5": None,
            "tail_improvement_p1": None,
            "false_quarantine_rate": None,
            "missed_profit_rate": None,
            "opportunity_retention_rate": None,
            "loss_avoidance_rate": None,
            "tail_status": "BAD",
            "data_quality_status": "insufficient",
            "review_ready": False,
        }
    scored.sort(
        key=lambda r: (
            r["tail_improvement_p10"],
            r["tail_improvement_p5"],
            r["tail_improvement_p1"],
            r["opportunity_retention_rate"] or 0.0,
            -(r["false_quarantine_rate"] or 1.0),
        ),
        reverse=True,
    )
    best = scored[0]
    review_ready = bool(
        best["after_sample_count"] >= 300
        and best["tail_improvement_p10"] > 0
        and best["tail_improvement_p5"] > 0
        and best["tail_improvement_p1"] > 0
        and (best["opportunity_retention_rate"] or 0) >= 0.7
        and (best["false_quarantine_rate"] or 1) <= 0.3
        and (best["missed_profit_rate"] or 1) <= 0.3
    )
    tail_status = "PASS" if best["tail_improvement_p10"] > 0 and best["tail_improvement_p5"] > 0 and best["tail_improvement_p1"] > 0 else "WARN"
    return {
        "best_filter_name": best["filter_name"],
        "best_window": best["window"],
        "best_horizon": best["horizon"],
        "sample_count_after": best["after_sample_count"],
        "tail_improvement_p10": best["tail_improvement_p10"],
        "tail_improvement_p5": best["tail_improvement_p5"],
        "tail_improvement_p1": best["tail_improvement_p1"],
        "false_quarantine_rate": best["false_quarantine_rate"],
        "missed_profit_rate": best["missed_profit_rate"],
        "opportunity_retention_rate": best["opportunity_retention_rate"],
        "loss_avoidance_rate": best["loss_avoidance_rate"],
        "tail_status": tail_status,
        "data_quality_status": "sufficient" if best["after_sample_count"] >= 300 else "preliminary" if best["after_sample_count"] >= 100 else "insufficient",
        "review_ready": review_ready,
    }


def build_taxonomy_json() -> dict[str, Any]:
    return {
        "regimes": [
            {
                "name": "HEALTHY_SHORT_HOLD",
                "rule": "exit depth is acceptable, price movement controlled, volume not collapsing, data fresh, and no extreme concentration proxy.",
                "required_data": ["valuation_usd", "current_tvl_usd", "current_vol24h_usd", "price_move_5m", "price_move_15m", "price_move_30m", "price_move_1h"],
                "confidence": "high",
                "should_enter": True,
                "should_quarantine": False,
                "should_research": True,
                "known_false_positive_risk": "Low-risk pools with muted price movement may still hide latent liquidity fragility.",
            },
            {
                "name": "STABLE_FEE",
                "rule": "fee proxy is attractive while price and TVL remain stable and exit depth is acceptable.",
                "required_data": ["current_tvl_usd", "current_vol24h_usd", "fee_proxy", "fee_velocity_proxy"],
                "confidence": "high",
                "should_enter": True,
                "should_quarantine": False,
                "should_research": True,
                "known_false_positive_risk": "Fee-rich periods can fade quickly and reverse into thin-liquidity regimes.",
            },
            {
                "name": "VOLATILE_BUT_LIQUID",
                "rule": "price movement is elevated but exit depth remains acceptable and data is fresh.",
                "required_data": ["price_move_15m", "price_move_30m", "exit_depth_50usd"],
                "confidence": "medium",
                "should_enter": False,
                "should_quarantine": False,
                "should_research": True,
                "known_false_positive_risk": "Liquidity can deteriorate right after the volatility spike is observed.",
            },
            {
                "name": "TOXIC_FLOW",
                "rule": "abnormal volume spike co-occurs with adverse price move and elevated concentration proxy.",
                "required_data": ["volume_change_15m", "volume_change_1h", "price_move_15m", "price_move_30m", "trader_concentration", "holder_concentration"],
                "confidence": "medium",
                "should_enter": False,
                "should_quarantine": True,
                "should_research": True,
                "known_false_positive_risk": "Organic flow bursts may look toxic before the price mean-reverts.",
            },
            {
                "name": "EXIT_DEPTH_THIN",
                "rule": "slippage at 10/20/50 USD is too high or safe exit depth is too small.",
                "required_data": ["exit_depth_10usd", "exit_depth_20usd", "exit_depth_50usd", "slippage_10usd", "slippage_20usd", "slippage_50usd"],
                "confidence": "high",
                "should_enter": False,
                "should_quarantine": True,
                "should_research": True,
                "known_false_positive_risk": "Depth can recover rapidly on a thin but active pool.",
            },
            {
                "name": "VOLUME_COLLAPSE",
                "rule": "volume decays hard over 15m/30m/1h and fee proxy becomes unreliable.",
                "required_data": ["volume_change_15m", "volume_change_30m", "volume_change_1h", "fee_proxy"],
                "confidence": "high",
                "should_enter": False,
                "should_quarantine": True,
                "should_research": True,
                "known_false_positive_risk": "Short-term lull can precede a new fee regime.",
            },
            {
                "name": "TVL_DROP",
                "rule": "TVL suddenly drops and liquidity pull risk rises.",
                "required_data": ["tvl_change_1h", "current_tvl_usd"],
                "confidence": "high",
                "should_enter": False,
                "should_quarantine": True,
                "should_research": True,
                "known_false_positive_risk": "Transient TVL dips from rebalancing can mimic a pull.",
            },
            {
                "name": "PRICE_SPIKE_VOLATILE",
                "rule": "price moves exceed thresholds and IL risk is elevated, even when exit depth may still be available.",
                "required_data": ["price_move_5m", "price_move_15m", "price_move_30m", "price_move_1h"],
                "confidence": "medium",
                "should_enter": False,
                "should_quarantine": True,
                "should_research": True,
                "known_false_positive_risk": "Fast momentum may briefly overshoot before mean reversion.",
            },
            {
                "name": "WHALE_OR_HOLDER_CONCENTRATED",
                "rule": "holder/trader concentration proxy is high and one actor dominates the pool.",
                "required_data": ["holder_concentration", "trader_concentration", "SecurityScore proxy"],
                "confidence": "medium",
                "should_enter": False,
                "should_quarantine": True,
                "should_research": True,
                "known_false_positive_risk": "Proxy concentration may overstate risk when direct holder data is unavailable.",
            },
            {
                "name": "DATA_STALE_OR_INCOMPLETE",
                "rule": "mark data is stale or core risk fields are missing.",
                "required_data": ["valuation_usd", "current_tvl_usd", "current_vol24h_usd"],
                "confidence": "high",
                "should_enter": False,
                "should_quarantine": True,
                "should_research": True,
                "known_false_positive_risk": "Temporary ingestion delays may create false stale signals.",
            },
            {
                "name": "UNKNOWN",
                "rule": "no regime can be assigned confidently from available evidence.",
                "required_data": ["any available pool window data"],
                "confidence": "low",
                "should_enter": False,
                "should_quarantine": False,
                "should_research": True,
                "known_false_positive_risk": "Unknown may conceal both good and bad pools; treat as research-only.",
            },
        ]
    }


def main() -> None:
    bootstrap_env()
    run_id = os.environ.get("RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_dir = REPO_ROOT / "reports" / "pool_regime_classifier" / run_id
    ensure_dir(report_dir)

    input_items = load_input_artifacts()
    input_verdict = json.loads((INPUT_RISK_DIR / "FINAL_VERDICT.json").read_text())
    decision_md = (INPUT_RISK_DIR / "RISK_SIGNAL_FIX_NEXT_STAGE_DECISION_CN.md").read_text(encoding="utf-8")

    conn = connect_db(readonly=True)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        db_check = quick_check_db(cur)
        pools, meta = load_pool_metadata(cur)
        scores = load_latest_scores(cur)
        pool_ids = list(pools.keys())
        marks = load_marks(cur, pool_ids)
        feature_rows = bucketize_feature_rows(pools, meta, scores, marks, run_id)
        feature_stats = build_feature_coverage(feature_rows)
        samples = q(
            cur,
            """
            select run_id, sample_id, proof_unit_type, pool_id, token_pair, start_time, horizon,
                   entry_value_source, entry_value, target_value_hold, risk_exit_time, risk_exit_value,
                   first_risk_signal, risk_signal_severity, fee_proxy, exit_cost_proxy,
                   hold_to_horizon_pnl_pct, risk_aware_exit_pnl_pct, no_entry_quarantine_pnl_pct,
                   loss_saved_vs_hold, missed_profit_vs_hold, false_exit_flag, opportunity_flag,
                   data_quality_status, invalid_reason, created_at
            from risk_aware_short_hold_counterfactual_v1
            where proof_unit_type = 'pool_window'
              and start_time >= now() - interval '8 days'
            order by start_time
            """,
        )
    conn.close()

    write_conn = connect_db(readonly=False)
    with write_conn.cursor(cursor_factory=RealDictCursor) as write_cur:
        materialize_classifier(write_cur, feature_rows, run_id)
        write_cur.execute(f"select count(*) from {REGIME_TABLE} where run_id = %s", (run_id,))
        materialized_count = write_cur.fetchone()["count"]
    write_conn.close()

    # Normalize pool_window sample rows
    sample_rows = []
    for s in samples:
        row = dict(s)
        row["hold_to_horizon_pnl_pct"] = parse_num(row["hold_to_horizon_pnl_pct"])
        row["risk_aware_exit_pnl_pct"] = parse_num(row["risk_aware_exit_pnl_pct"])
        row["no_entry_quarantine_pnl_pct"] = parse_num(row["no_entry_quarantine_pnl_pct"])
        row["hold_pnl"] = row["hold_to_horizon_pnl_pct"]
        row["risk_exit_pnl"] = row["risk_aware_exit_pnl_pct"]
        row["start_time_dt"] = parse_ts(row["start_time"])
        if row["start_time_dt"] is None:
            continue
        row["sample_window"] = bucket_label((datetime.now(timezone.utc) - row["start_time_dt"]).total_seconds() / 3600.0)
        sample_rows.append(row)

    regime_samples = classify_samples_by_regime(sample_rows, feature_rows)
    regime_audit_rows = summarize_regime_audit(regime_samples)
    backtest_rows = filter_backtest(regime_samples)
    best_filter = choose_best_filter(backtest_rows)

    regime_counts = Counter(r["regime_primary"] for r in feature_rows)
    window_counts = Counter(r["window"] for r in feature_rows)
    quality_counts = Counter(r["data_quality_status"] for r in feature_rows)
    enter_count = sum(1 for r in feature_rows if r["should_enter"])
    quarantine_count = sum(1 for r in feature_rows if r["should_quarantine"])
    research_count = sum(1 for r in feature_rows if r["should_research_only"])
    unknown_count = regime_counts.get("UNKNOWN", 0)
    healthy_short_hold_count = regime_counts.get("HEALTHY_SHORT_HOLD", 0)
    regime_count = len(build_taxonomy_json()["regimes"])

    tail_improved = bool(
        best_filter["tail_improvement_p10"] is not None
        and best_filter["tail_improvement_p5"] is not None
        and best_filter["tail_improvement_p1"] is not None
        and best_filter["tail_improvement_p10"] > 0
        and best_filter["tail_improvement_p5"] > 0
        and best_filter["tail_improvement_p1"] > 0
    )

    review_ready = bool(best_filter["review_ready"] and tail_improved and best_filter["sample_count_after"] >= 300)
    if review_ready:
        next_stage = "POOL_REGIME_AWARE_SHORT_HOLD_COUNTERFACTUAL_V1"
    elif feature_stats["feature_coverage"]["trader_concentration"]["coverage_rate"] < 0.3 or feature_stats["feature_coverage"]["holder_concentration"]["coverage_rate"] < 0.3:
        next_stage = "POOL_REGIME_CLASSIFIER_DATA_FIX"
    elif tail_improved is False and best_filter["best_filter_name"]:
        next_stage = "POOL_REGIME_RULE_FIX"
    elif tail_improved is False and not best_filter["best_filter_name"]:
        next_stage = "FEE_VELOCITY_EXIT_DEPTH_COUNTERFACTUAL_V1"
    else:
        next_stage = "STOP_RESEARCH"

    false_quarantine_rate = best_filter["false_quarantine_rate"]
    missed_profit_rate = best_filter["missed_profit_rate"]
    opportunity_retention_rate = best_filter["opportunity_retention_rate"]

    # Write input audit artifacts
    input_audit_md = ["# Input Artifact Audit", ""]
    for name, meta in input_items.items():
        input_audit_md.append(f"- {name}: {'yes' if meta['exists'] else 'no'}")
    input_audit_md.extend(
        [
            "",
            f"- risk_exit_helpful_confirmed: {'yes' if 'risk_exit_helpful: no' in decision_md else 'no'}",
            f"- quarantine_helpful_confirmed: {'yes' if 'quarantine_helpful: yes' in decision_md else 'no'}",
            f"- recommended_next_stage_confirmed: {'yes' if 'recommended_next_stage: POOL_REGIME_CLASSIFIER_V1' in decision_md else 'no'}",
            f"- sufficient_for_pool_regime_classifier: {'yes' if bool(feature_rows) and bool(sample_rows) else 'no'}",
            "- edge_proven: no",
        ]
    )
    write_text(report_dir / "INPUT_ARTIFACT_AUDIT_CN.md", "\n".join(input_audit_md) + "\n")
    write_json(
        report_dir / "input_artifact_audit.json",
        {
            **{k: v["exists"] for k, v in input_items.items()},
            "risk_exit_helpful_confirmed": "risk_exit_helpful: no" in decision_md,
            "quarantine_helpful_confirmed": "quarantine_helpful: yes" in decision_md,
            "recommended_next_stage_confirmed": "recommended_next_stage: POOL_REGIME_CLASSIFIER_V1" in decision_md,
            "sufficient_for_pool_regime_classifier": bool(feature_rows) and bool(sample_rows),
            "edge_proven": "no",
        },
    )

    # VPS quick check
    vps_quick_md = "\n".join(
        [
            "# VPS DB Quick Check",
            "",
            f"- DSN_PRESENT: yes",
            f"- DB_CONNECT: ok",
            f"- DB_NAME: {db_check['db_name']}",
            f"- DB_USER: {db_check['db_user']}",
            f"- report_ready: yes",
        ]
    )
    write_text(report_dir / "VPS_DB_QUICK_CHECK_CN.md", vps_quick_md + "\n")

    taxonomy = build_taxonomy_json()
    write_text(report_dir / "POOL_REGIME_TAXONOMY_V1_CN.md", "# Pool Regime Taxonomy V1\n\nThis classifier uses VPS Postgres pool-window history and mark-derived proxy signals to rank quarantine risk before entry.\n")
    write_json(report_dir / "pool_regime_taxonomy_v1.json", taxonomy)

    # Features report
    feature_rows_csv = []
    for r in feature_rows:
        feature_rows_csv.append(
            {
                "run_id": run_id,
                "pool_id": r["pool_id"],
                "token_pair": r["token_pair"],
                "bucket_start": r["bucket_start_dt"].isoformat(),
                "bucket_end": r["bucket_end_dt"].isoformat(),
                "window": r["window"],
                "price_move_5m": fmt_num(r["price_move_5m"]),
                "price_move_15m": fmt_num(r["price_move_15m"]),
                "price_move_30m": fmt_num(r["price_move_30m"]),
                "price_move_1h": fmt_num(r["price_move_1h"]),
                "volume_change_15m": fmt_num(r["volume_change_15m"]),
                "volume_change_30m": fmt_num(r["volume_change_30m"]),
                "volume_change_1h": fmt_num(r["volume_change_1h"]),
                "tvl_change_1h": fmt_num(r["tvl_change_1h"]),
                "fee_proxy": fmt_num(r["fee_proxy"]),
                "fee_velocity_proxy": fmt_num(r["fee_velocity_proxy"]),
                "exit_depth_10usd": fmt_num(r["exit_depth_10usd"]),
                "exit_depth_20usd": fmt_num(r["exit_depth_20usd"]),
                "exit_depth_50usd": fmt_num(r["exit_depth_50usd"]),
                "slippage_10usd": fmt_num(r["slippage_10usd"]),
                "slippage_20usd": fmt_num(r["slippage_20usd"]),
                "slippage_50usd": fmt_num(r["slippage_50usd"]),
                "trader_concentration": fmt_num(r["trader_concentration"]),
                "holder_concentration": fmt_num(r["holder_concentration"]),
                "stale_data_flag": fmt_num(r["stale_data_flag"]),
                "pool_mark_gap": fmt_num(r["pool_mark_gap"]),
                "abnormal_volume_spike": fmt_num(r["abnormal_volume_spike"]),
                "volume_collapse": fmt_num(r["volume_collapse"]),
                "price_spike_up": fmt_num(r["price_spike_up"]),
                "price_spike_down": fmt_num(r["price_spike_down"]),
                "regime_primary": r["regime_primary"],
                "regime_secondary": r["regime_secondary"],
                "regime_confidence": r["regime_confidence"],
                "should_enter": fmt_num(r["should_enter"]),
                "should_quarantine": fmt_num(r["should_quarantine"]),
                "should_research_only": fmt_num(r["should_research_only"]),
                "risk_score": fmt_num(r["risk_score"]),
                "exit_depth_score": fmt_num(r["exit_depth_score"]),
                "volatility_score": fmt_num(r["volatility_score"]),
                "volume_score": fmt_num(r["volume_score"]),
                "tvl_score": fmt_num(r["tvl_score"]),
                "data_quality_score": fmt_num(r["data_quality_score"]),
                "fee_proxy_score": fmt_num(r["fee_proxy_score"]),
                "rule_hits": json.dumps(r["rule_hits"], ensure_ascii=False),
                "missing_features": json.dumps(r["missing_features"], ensure_ascii=False),
            }
        )
    feature_fields = list(feature_rows_csv[0].keys()) if feature_rows_csv else []
    write_text(
        report_dir / "POOL_REGIME_FEATURES_CN.md",
        "\n".join(
            [
                "# Pool Regime Features",
                "",
                f"- total_rows: {feature_stats['total_rows']}",
                f"- feature_coverage: {json.dumps(feature_stats['feature_coverage'], ensure_ascii=False)}",
                f"- per_window_row_count: {json.dumps(dict(feature_stats['per_window_row_count']), ensure_ascii=False)}",
                f"- per_pool_row_count: {json.dumps(dict(feature_stats['per_pool_row_count']), ensure_ascii=False)}",
                f"- missing_field_count: {sum(v['missing'] for v in feature_stats['feature_coverage'].values())}",
            ]
        )
        + "\n",
    )
    write_csv(report_dir / "pool_regime_features.csv", feature_rows_csv, feature_fields)

    # Materialization report
    materialization_counts = Counter(r["regime_primary"] for r in feature_rows)
    materialization_rows = []
    for r in feature_rows:
        materialization_rows.append(
            {
                "run_id": run_id,
                "pool_id": r["pool_id"],
                "token_pair": r["token_pair"],
                "bucket_start": r["bucket_start_dt"].isoformat(),
                "bucket_end": r["bucket_end_dt"].isoformat(),
                "window": r["window"],
                "regime_primary": r["regime_primary"],
                "regime_secondary": r["regime_secondary"],
                "regime_confidence": r["regime_confidence"],
                "should_enter": fmt_num(r["should_enter"]),
                "should_quarantine": fmt_num(r["should_quarantine"]),
                "should_research_only": fmt_num(r["should_research_only"]),
                "risk_score": fmt_num(r["risk_score"]),
                "exit_depth_score": fmt_num(r["exit_depth_score"]),
                "volatility_score": fmt_num(r["volatility_score"]),
                "volume_score": fmt_num(r["volume_score"]),
                "tvl_score": fmt_num(r["tvl_score"]),
                "data_quality_score": fmt_num(r["data_quality_score"]),
                "fee_proxy_score": fmt_num(r["fee_proxy_score"]),
                "rule_hits": json.dumps(r["rule_hits"], ensure_ascii=False),
                "missing_features": json.dumps(r["missing_features"], ensure_ascii=False),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    write_text(
        report_dir / "POOL_REGIME_MATERIALIZATION_CN.md",
        "\n".join(
            [
                "# Pool Regime Materialization",
                "",
                f"- rows by window: {json.dumps(dict(window_counts), ensure_ascii=False)}",
                f"- rows by regime: {json.dumps(dict(materialization_counts), ensure_ascii=False)}",
                f"- quarantine count: {quarantine_count}",
                f"- should_enter count: {enter_count}",
                f"- should_research_only count: {research_count}",
                f"- unknown count: {unknown_count}",
                f"- data quality distribution: {json.dumps(dict(quality_counts), ensure_ascii=False)}",
            ]
        )
        + "\n",
    )
    write_csv(
        report_dir / "pool_regime_materialization_counts.csv",
        [
            {
                "metric": "rows_total",
                "value": len(feature_rows),
            },
            *[
                {"metric": f"rows_window_{k}", "value": v}
                for k, v in sorted(window_counts.items())
            ],
            *[
                {"metric": f"rows_regime_{k}", "value": v}
                for k, v in sorted(materialization_counts.items())
            ],
            {"metric": "quarantine_count", "value": quarantine_count},
            {"metric": "should_enter_count", "value": enter_count},
            {"metric": "should_research_only_count", "value": research_count},
            {"metric": "unknown_count", "value": unknown_count},
        ],
        ["metric", "value"],
    )

    # Tail outcome audit
    audit_fields = [
        "regime",
        "window",
        "horizon",
        "sample_count",
        "valid_count",
        "hold_median",
        "hold_p10",
        "hold_p5",
        "hold_p1",
        "risk_exit_p10",
        "quarantine_avoided_loss_count",
        "false_quarantine_rate",
        "missed_profit_rate",
        "worst_pool_contribution",
        "tail_status",
    ]
    write_text(
        report_dir / "POOL_REGIME_TAIL_OUTCOME_AUDIT_CN.md",
        "\n".join(
            [
                "# Pool Regime Tail Outcome Audit",
                "",
                "The audit aligns regime labels to pool_window counterfactual samples and tests which regime families carry negative tail.",
                f"- healthy_short_hold_count: {healthy_short_hold_count}",
                f"- quarantine_count: {quarantine_count}",
                f"- unknown_count: {unknown_count}",
                f"- classified_window_count: {len(feature_rows)}",
            ]
        )
        + "\n",
    )
    write_csv(report_dir / "pool_regime_tail_outcome_audit.csv", regime_audit_rows, audit_fields)

    # Backtest
    backtest_fields = [
        "filter_name",
        "window",
        "horizon",
        "before_sample_count",
        "after_sample_count",
        "filtered_out_count",
        "hold_p10_before",
        "hold_p10_after",
        "hold_p5_before",
        "hold_p5_after",
        "hold_p1_before",
        "hold_p1_after",
        "median_before",
        "median_after",
        "false_quarantine_rate",
        "missed_profit_rate",
        "opportunity_retention_rate",
        "loss_avoidance_rate",
        "worst_pool_contribution_after",
        "tail_improvement_p10",
        "tail_improvement_p5",
        "tail_improvement_p1",
        "verdict",
    ]
    write_text(
        report_dir / "POOL_REGIME_QUARANTINE_BACKTEST_CN.md",
        "\n".join(
            [
                "# Pool Regime Quarantine Backtest",
                "",
                "The backtest compares the hold-to-horizon baseline against several regime-driven entry filters.",
                f"- classified_window_count: {len(feature_rows)}",
                f"- healthy_short_hold_count: {healthy_short_hold_count}",
                f"- quarantine_count: {quarantine_count}",
                f"- unknown_count: {unknown_count}",
            ]
        )
        + "\n",
    )
    write_csv(report_dir / "pool_regime_quarantine_backtest.csv", backtest_rows, backtest_fields)

    best_filter_json = {
        **best_filter,
        "tail_improved": tail_improved,
    }
    write_text(
        report_dir / "POOL_REGIME_BEST_FILTER_SELECTION_CN.md",
        "\n".join(
            [
                "# Pool Regime Best Filter Selection",
                "",
                f"- best_filter_name: {best_filter['best_filter_name']}",
                f"- best_window: {best_filter['best_window']}",
                f"- best_horizon: {best_filter['best_horizon']}",
                f"- sample_count_after: {best_filter['sample_count_after']}",
                f"- tail_improvement_p10: {best_filter['tail_improvement_p10']}",
                f"- tail_improvement_p5: {best_filter['tail_improvement_p5']}",
                f"- tail_improvement_p1: {best_filter['tail_improvement_p1']}",
                f"- false_quarantine_rate: {best_filter['false_quarantine_rate']}",
                f"- missed_profit_rate: {best_filter['missed_profit_rate']}",
                f"- opportunity_retention_rate: {best_filter['opportunity_retention_rate']}",
                f"- loss_avoidance_rate: {best_filter['loss_avoidance_rate']}",
                f"- tail_status: {best_filter['tail_status']}",
                f"- data_quality_status: {best_filter['data_quality_status']}",
                f"- review_ready: {'yes' if best_filter['review_ready'] else 'no'}",
            ]
        )
        + "\n",
    )
    write_json(report_dir / "pool_regime_best_filter_selection.json", best_filter_json)

    # Next stage decision
    write_text(
        report_dir / "POOL_REGIME_NEXT_STAGE_DECISION_CN.md",
        "\n".join(
            [
                "# Pool Regime Next Stage Decision",
                "",
                f"- recommended_next_stage: {next_stage}",
                f"- review_ready: {'yes' if review_ready else 'no'}",
                f"- tail_improved: {'yes' if tail_improved else 'no'}",
                f"- best_filter_name: {best_filter['best_filter_name']}",
                f"- best_window: {best_filter['best_window']}",
                f"- best_horizon: {best_filter['best_horizon']}",
            ]
        )
        + "\n",
    )
    write_json(report_dir / "pool_regime_next_stage_decision.json", {"recommended_next_stage": next_stage, **best_filter_json})

    final_verdict = {
        "status": "PASS" if review_ready else "WARN" if tail_improved else "FAIL",
        "stage": "POOL_REGIME_CLASSIFIER_V1",
        "data_source": "vps_postgres",
        "db_ready": True,
        "regime_count": regime_count,
        "classified_window_count": len(feature_rows),
        "healthy_short_hold_count": healthy_short_hold_count,
        "quarantine_count": quarantine_count,
        "unknown_count": unknown_count,
        "best_filter_name": best_filter["best_filter_name"],
        "best_window": best_filter["best_window"],
        "best_horizon": best_filter["best_horizon"],
        "tail_improved": tail_improved,
        "false_quarantine_rate": false_quarantine_rate,
        "missed_profit_rate": missed_profit_rate,
        "opportunity_retention_rate": opportunity_retention_rate,
        "review_ready": review_ready,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage,
    }
    write_json(report_dir / "FINAL_VERDICT.json", final_verdict)

    onepage = "\n".join(
        [
            "# Pool Regime Classifier V1",
            "",
            f"- status: {final_verdict['status']}",
            f"- best_filter_name: {best_filter['best_filter_name']}",
            f"- best_window: {best_filter['best_window']}",
            f"- best_horizon: {best_filter['best_horizon']}",
            f"- tail_improved: {'yes' if tail_improved else 'no'}",
            f"- false_quarantine_rate: {fmt_num(false_quarantine_rate)}",
            f"- missed_profit_rate: {fmt_num(missed_profit_rate)}",
            f"- opportunity_retention_rate: {fmt_num(opportunity_retention_rate)}",
            f"- review_ready: {'yes' if review_ready else 'no'}",
            f"- recommended_next_stage: {next_stage}",
            f"- tiny_canary_allowed: no",
        ]
    )
    write_text(report_dir / "ONEPAGE_CN.md", onepage + "\n")

    artifact_index = "\n".join(
        [
            "# Artifact Index",
            "",
            "- INPUT_ARTIFACT_AUDIT_CN.md",
            "- VPS_DB_QUICK_CHECK_CN.md",
            "- POOL_REGIME_TAXONOMY_V1_CN.md",
            "- POOL_REGIME_FEATURES_CN.md",
            "- POOL_REGIME_MATERIALIZATION_CN.md",
            "- POOL_REGIME_TAIL_OUTCOME_AUDIT_CN.md",
            "- POOL_REGIME_QUARANTINE_BACKTEST_CN.md",
            "- POOL_REGIME_BEST_FILTER_SELECTION_CN.md",
            "- POOL_REGIME_NEXT_STAGE_DECISION_CN.md",
            "- FINAL_VERDICT.json",
            "- ONEPAGE_CN.md",
            "- pool_regime_taxonomy_v1.json",
            "- pool_regime_features.csv",
            "- pool_regime_materialization_counts.csv",
            "- pool_regime_tail_outcome_audit.csv",
            "- pool_regime_quarantine_backtest.csv",
            "- pool_regime_best_filter_selection.json",
            "- pool_regime_next_stage_decision.json",
            "- input_artifact_audit.json",
        ]
    )
    write_text(report_dir / "ARTIFACT_INDEX.md", artifact_index + "\n")

    # Write the sample / feature CSVs last so they exist for grep and review.
    if feature_rows_csv:
        write_csv(report_dir / "pool_regime_features.csv", feature_rows_csv, feature_fields)

    print(json.dumps({"report_dir": str(report_dir), "final_verdict": str(report_dir / "FINAL_VERDICT.json")}, indent=2))


if __name__ == "__main__":
    main()
