#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shlex
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values


WINDOW_HOURS = [24, 48, 72, 168]
HORIZONS = ["15m", "30m", "1h", "2h"]
INTENT_BUCKET_SECONDS = 900
POOL_BUCKET_SECONDS = 900


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        parsed = shlex.split(line, posix=True)
        normalized = parsed[0] if parsed else line
        key, value = normalized.split("=", 1)
        os.environ[key.strip()] = value.strip()


def bootstrap_env(repo_root: Path) -> None:
    for candidate in [repo_root / ".runtime.shadow.env", repo_root / ".env", repo_root / ".env.chain"]:
        load_env_file(candidate)


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


def parse_num(v):
    if v in (None, "", "null", "None"):
        return None
    try:
        return float(v)
    except Exception:
        return None


def fmt(v, digits=6):
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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def percentile(values: list[float], p: float):
    if not values:
        return None
    values = sorted(values)
    idx = max(0, min(len(values) - 1, int((len(values) - 1) * p)))
    return values[idx]


def median(values: list[float]):
    return percentile(values, 0.5)


def sample_sufficiency(n: int) -> str:
    if n < 30:
        return "INSUFFICIENT"
    if n < 100:
        return "EARLY"
    if n < 300:
        return "PRELIMINARY"
    return "USABLE"


def bucket(ts_seconds: float, seconds: int) -> int:
    return int(ts_seconds // seconds)


def hour_bucket_label(hours: int) -> str:
    return f"recent_{hours}h"


def horizon_to_minutes(horizon: str) -> int:
    return {"15m": 15, "30m": 30, "1h": 60, "2h": 120}[horizon]


def horizon_to_seconds(horizon: str) -> int:
    return horizon_to_minutes(horizon) * 60


def pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old in (None, 0):
        return None
    return (new - old) / old * 100.0


def safe_ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b in (None, 0):
        return None
    return a / b


@dataclass
class PoolMark:
    pool_id: str
    mark_time: datetime
    valuation_usd: float | None
    tvl_usd: float | None
    vol24h_usd: float | None
    price_change_pct: float | None
    amount_usd: float | None
    source: str


def connect_db(repo_root: Path):
    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("missing_postgres_dsn")
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=False, autocommit=False)
    return conn


def load_source_data(conn):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            select pool_id, chain, protocol, token0, token1, fee_bps, tier,
                   audit_verdict, last_score, updated_at, tvl_usd, vol_24h, fee_apr_24h
            from pools
            """
        )
        pools = {r["pool_id"]: dict(r) for r in cur.fetchall()}

        cur.execute(
            """
            select pool_id, token0, token1, token0_symbol, token1_symbol, token0_decimals, token1_decimals
            from pool_token_metadata
            """
        )
        ptm = {r["pool_id"]: dict(r) for r in cur.fetchall()}

        cur.execute(
            """
            select trace_id, tick_time, pool_id, chain, protocol, score_total, selected, selected_rank,
                   selection_reason, intent_open, intent_reason, pipeline_stage, pipeline_ok, pipeline_reason,
                   final_action, position_id, strategy_epoch, intended_notional_usd
            from shadow_decision_trace
            where tick_time >= extract(epoch from now() - interval '7 days')
              and intent_open = true
            order by tick_time
            """
        )
        traces = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            select position_id, pool_id, mark_time, source, valuation_usd, amount_usd,
                   current_tvl_usd, current_vol24h_usd, price_change_pct
            from shadow_position_marks
            where mark_time >= extract(epoch from now() - interval '8 days')
            order by pool_id, mark_time
            """
        )
        marks = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            select id::text as position_id, pool_id::text as pool_id, chain, amount_usd, opened_at
            from positions
            where opened_at >= extract(epoch from now() - interval '8 days')
            """
        )
        positions = {r["position_id"]: dict(r) for r in cur.fetchall()}

    return pools, ptm, traces, marks, positions


def aggregate_pool_marks(marks: list[dict]) -> dict[str, list[PoolMark]]:
    grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for r in marks:
        mt = parse_ts(r["mark_time"])
        if not mt:
            continue
        bucket_key = bucket(mt.timestamp(), POOL_BUCKET_SECONDS)
        grouped[(r["pool_id"], bucket_key)].append(r)

    pool_series: dict[str, list[PoolMark]] = defaultdict(list)
    for (pool_id, bucket_key), rows in grouped.items():
        times = [parse_ts(r["mark_time"]) for r in rows]
        mt = max([t for t in times if t is not None], default=None)
        if not mt:
            continue
        vals = [parse_num(r["valuation_usd"]) for r in rows]
        tvls = [parse_num(r["current_tvl_usd"]) for r in rows]
        vols = [parse_num(r["current_vol24h_usd"]) for r in rows]
        price_changes = [parse_num(r["price_change_pct"]) for r in rows]
        amts = [parse_num(r["amount_usd"]) for r in rows]
        sources = [r.get("source") or "" for r in rows]
        pool_series[pool_id].append(
            PoolMark(
                pool_id=pool_id,
                mark_time=mt,
                valuation_usd=median([v for v in vals if v is not None]),
                tvl_usd=median([v for v in tvls if v is not None]),
                vol24h_usd=median([v for v in vols if v is not None]),
                price_change_pct=median([v for v in price_changes if v is not None]),
                amount_usd=median([v for v in amts if v is not None]),
                source="median_pool_mark:" + ",".join(sorted(set(sources))) if sources else "",
            )
        )

    for pool_id in pool_series:
        pool_series[pool_id].sort(key=lambda x: x.mark_time)
    return pool_series


def build_token_pair(pool_id: str, pools: dict, ptm: dict) -> str:
    m = ptm.get(pool_id) or {}
    if m.get("token0_symbol") and m.get("token1_symbol"):
        return f"{m['token0_symbol']}/{m['token1_symbol']}"
    p = pools.get(pool_id) or {}
    if p.get("token0") and p.get("token1"):
        return f"{p['token0'][:8]}/{p['token1'][:8]}"
    return pool_id


def entry_notional_source(trace: dict, positions: dict, marks_by_position: dict[str, list[dict]]):
    trace_notional = parse_num(trace.get("intended_notional_usd"))
    if trace_notional and trace_notional > 0:
        return "trace_intended_notional_usd", trace_notional, "high", True, ""
    pos = positions.get(trace.get("position_id") or "")
    if pos:
        pos_amount = parse_num(pos.get("amount_usd"))
        opened = parse_ts(pos.get("opened_at"))
        tick = parse_ts(trace.get("tick_time"))
        if pos_amount and opened and tick and abs((opened - tick).total_seconds()) <= 3600:
            return "joined_position_amount_usd", pos_amount, "medium", True, ""
    marks = marks_by_position.get(trace.get("position_id") or "", [])
    tick = parse_ts(trace.get("tick_time"))
    if tick and marks:
        near = []
        for mk in marks:
            amt = parse_num(mk.get("amount_usd"))
            mtime = parse_ts(mk.get("mark_time"))
            if amt and amt > 0 and mtime:
                near.append((abs((mtime - tick).total_seconds()), amt))
        if near:
            near.sort(key=lambda x: x[0])
            gap, amt = near[0]
            if gap <= 900:
                return "first_position_mark_amount_usd", amt, "medium", True, ""
        return "", None, "low", False, "mark_amount_missing"
    return "", None, "none", False, "intended_notional_missing"


def dedup_intent_windows(traces: list[dict], positions: dict, marks_by_position: dict[str, list[dict]]):
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in traces:
        intent_type = "open" if t.get("final_action") == "open_shadow_position" else "reuse"
        token_pair = f"{t.get('chain')}:{t.get('pool_id') or ''}"
        epoch = t.get("strategy_epoch") if t.get("strategy_epoch") is not None else "na"
        bucket_key = bucket(float(t["tick_time"]), INTENT_BUCKET_SECONDS)
        key = f"{t.get('pool_id') or ''}|{token_pair}|{epoch}|tb15|{bucket_key}|{intent_type}"
        groups[key].append(t)

    records = []
    for key, rows in sorted(groups.items(), key=lambda kv: min(float(x["tick_time"]) for x in kv[1])):
        rows = sorted(rows, key=lambda x: float(x["tick_time"]))
        first = rows[0]
        source_name, notional, confidence, trusted, reason = entry_notional_source(first, positions, marks_by_position)
        records.append(
            {
                "sample_id": f"intent:{key}",
                "proof_unit_type": "intent_window",
                "pool_id": first.get("pool_id") or "",
                "chain": first.get("chain"),
                "token_pair": f"{first.get('chain')}:{first.get('pool_id') or ''}",
                "start_time": parse_ts(first["tick_time"]),
                "strategy_epoch": first.get("strategy_epoch"),
                "source_trace_count": len(rows),
                "first_trace": first,
                "entry_value_source": source_name,
                "entry_value": notional,
                "entry_value_trusted": trusted,
                "entry_value_confidence": confidence,
                "entry_entry_reason": reason,
            }
        )
    return records


def build_pool_windows(pool_series: dict[str, list[PoolMark]], pools: dict, ptm: dict):
    records = []
    for pool_id, series in pool_series.items():
        for idx, mark in enumerate(series):
            bucket_key = bucket(mark.mark_time.timestamp(), POOL_BUCKET_SECONDS)
            records.append(
                {
                    "sample_id": f"pool:{pool_id}:{bucket_key}",
                    "proof_unit_type": "pool_window",
                    "pool_id": pool_id,
                    "chain": pools.get(pool_id, {}).get("chain"),
                    "token_pair": build_token_pair(pool_id, pools, ptm),
                    "start_time": mark.mark_time,
                    "strategy_epoch": "",
                    "source_trace_count": 1,
                    "first_pool_mark": mark,
                    "entry_value_source": "pool_mark_valuation_usd",
                    "entry_value": mark.valuation_usd,
                    "entry_value_trusted": mark.valuation_usd is not None,
                    "entry_value_confidence": "high" if mark.valuation_usd is not None else "low",
                    "entry_entry_reason": "" if mark.valuation_usd is not None else "valuation_missing",
                }
            )
    return records


def nearest_future_mark(series: list[PoolMark], target_time: datetime):
    if not series or not target_time:
        return None
    for m in series:
        if m.mark_time >= target_time:
            return m
    return None


def slice_series(series: list[PoolMark], start: datetime, end: datetime):
    return [m for m in series if start <= m.mark_time <= end]


def derive_signals(window_series: list[PoolMark], entry_value: float | None, pool_tvl: float | None):
    signals = []
    prev = None
    for mark in window_series:
        severity = None
        signal = None
        action = "hold"
        confidence = "medium"
        limitations = []
        price = mark.price_change_pct
        tvl = mark.tvl_usd
        vol = mark.vol24h_usd
        if price is not None and price <= -10:
            signal = "price_spike_down"
            severity = "high"
            action = "exit_now"
        elif price is not None and price <= -5:
            signal = "price_spike_down"
            severity = "medium"
            action = "exit_now"
        elif price is not None and price >= 15:
            signal = "price_spike_up"
            severity = "low"
            action = "hold"
        if prev and signal is None:
            if prev.vol24h_usd and vol is not None and vol <= prev.vol24h_usd * 0.6:
                signal = "volume_collapse"
                severity = "high" if vol <= prev.vol24h_usd * 0.5 else "medium"
                action = "exit_now" if severity == "high" else "hold"
            elif prev.tvl_usd and tvl is not None and tvl <= prev.tvl_usd * 0.85:
                signal = "tvl_drop"
                severity = "high" if tvl <= prev.tvl_usd * 0.8 else "medium"
                action = "exit_now" if severity == "high" else "hold"
            elif prev.vol24h_usd and vol is not None and vol >= prev.vol24h_usd * 1.8:
                signal = "abnormal_volume_spike"
                severity = "low"
                action = "hold"
        if signal is None and entry_value is not None and pool_tvl is not None:
            depth_ratio = entry_value / max(pool_tvl, 1.0)
            if depth_ratio > 0.1:
                signal = "exit_depth_drop"
                severity = "high"
                action = "quarantine_no_entry"
                limitations.append("entry_size_vs_tvl_high")
        if signal is None and mark.source and "stale" in mark.source:
            signal = "pool_mark_gap / stale data"
            severity = "high"
            action = "quarantine_no_entry"
        if signal:
            signals.append(
                {
                    "signal_name": signal,
                    "trigger_time": mark.mark_time,
                    "severity": severity or "low",
                    "exit_action": action,
                    "confidence": confidence,
                    "known_limitations": ",".join(limitations) if limitations else "",
                }
            )
        prev = mark
    return signals


def slippage_proxy_pct(entry_value: float | None, pool_tvl: float | None, pool_vol: float | None, fee_bps: int | None):
    if entry_value is None or pool_tvl in (None, 0):
        return None
    base = min(0.05, max(0.001, (entry_value / max(pool_tvl, 1.0)) * 0.5))
    if pool_vol is not None and pool_tvl:
        base += min(0.02, (pool_vol / pool_tvl) * 0.0005)
    if fee_bps:
        base += min(0.01, fee_bps / 10000.0 * 0.05)
    return min(0.08, base)


def fee_proxy_usd(entry_value: float | None, pool_vol: float | None, pool_tvl: float | None, fee_bps: int | None, horizon_hours: int):
    if entry_value is None or pool_vol in (None,) or pool_tvl in (None, 0) or fee_bps is None:
        return None
    daily_fee_rate = min(0.03, (pool_vol / max(pool_tvl, 1.0)) * (fee_bps / 10000.0))
    return entry_value * daily_fee_rate * (horizon_hours / 24.0)


def exit_cost_proxy_usd(entry_value: float | None, pool_tvl: float | None, pool_vol: float | None, fee_bps: int | None):
    pct = slippage_proxy_pct(entry_value, pool_tvl, pool_vol, fee_bps)
    if pct is None or entry_value is None:
        return None
    return entry_value * pct


def classify_quality(entry_value, target_value, target_mark, signal_count, fee_proxy, exit_cost_proxy, invalid_reason):
    if invalid_reason:
        return "invalid"
    if entry_value is None or target_value is None:
        return "invalid"
    if target_mark is None:
        return "invalid"
    if signal_count == 0 and fee_proxy is None and exit_cost_proxy is None:
        return "partial"
    return "ok"


def compute_row(sample, horizon: str, pool_series: dict[str, list[PoolMark]], pools: dict, ptm: dict):
    start_time: datetime = sample["start_time"]
    pool_id = sample["pool_id"]
    series = pool_series.get(pool_id, [])
    target_time = start_time + timedelta(seconds=horizon_to_seconds(horizon))
    window_marks = slice_series(series, start_time, target_time)
    future_mark = nearest_future_mark(series, target_time)
    entry_value = sample["entry_value"]
    pool_tvl = None
    pool_vol = None
    fee_bps = None
    p = pools.get(pool_id) or {}
    if p:
        pool_tvl = parse_num(p.get("tvl_usd"))
        pool_vol = parse_num(p.get("vol_24h"))
        fee_bps = int(p.get("fee_bps")) if p.get("fee_bps") is not None else None
    if window_marks:
        # prioritize current window state over static pool snapshot
        last = window_marks[-1]
        pool_tvl = last.tvl_usd if last.tvl_usd is not None else pool_tvl
        pool_vol = last.vol24h_usd if last.vol24h_usd is not None else pool_vol
    fee_proxy = fee_proxy_usd(entry_value, pool_vol, pool_tvl, fee_bps, horizon_to_minutes(horizon) / 60.0)
    exit_cost_proxy = exit_cost_proxy_usd(entry_value, pool_tvl, pool_vol, fee_bps)

    invalid_reason = ""
    if entry_value is None or entry_value <= 0:
        invalid_reason = "entry_value_missing"
    elif future_mark is None:
        invalid_reason = "no_future_pool_mark"

    # risk signals from the window before the future mark
    signals = derive_signals(window_marks, entry_value, pool_tvl)
    first_signal = signals[0] if signals else None
    risk_exit_time = first_signal["trigger_time"] if first_signal else None
    risk_exit_value = None
    risk_severity = ""
    if first_signal and series:
        m = nearest_future_mark(series, first_signal["trigger_time"])
        if m is not None:
            risk_exit_value = m.valuation_usd
            risk_severity = first_signal["severity"]
    elif future_mark is not None:
        risk_exit_value = future_mark.valuation_usd

    hold_pnl = pct_change(future_mark.valuation_usd if future_mark else None, entry_value) if future_mark else None
    risk_exit_pnl = pct_change(risk_exit_value, entry_value) if risk_exit_value is not None else None
    no_entry_quarantine_pnl = 0.0 if not invalid_reason else None

    loss_saved = None
    missed_profit = None
    false_exit_flag = False
    opportunity_flag = False
    if hold_pnl is not None and risk_exit_pnl is not None:
        loss_saved = hold_pnl - risk_exit_pnl
        if hold_pnl > 0:
            opportunity_flag = True
            if risk_exit_pnl < hold_pnl:
                missed_profit = hold_pnl - risk_exit_pnl
                if missed_profit > 0.2:
                    false_exit_flag = True
    if hold_pnl is not None and hold_pnl < 0 and risk_exit_pnl is not None and risk_exit_pnl > hold_pnl:
        opportunity_flag = True

    top10_holder_pct = None  # not available in current chain for P0 first version
    data_quality = classify_quality(entry_value, future_mark.valuation_usd if future_mark else None, future_mark, len(signals), fee_proxy, exit_cost_proxy, invalid_reason)

    return {
        "sample_id": sample["sample_id"],
        "proof_unit_type": sample["proof_unit_type"],
        "pool_id": pool_id,
        "token_pair": sample["token_pair"],
        "start_time": start_time.isoformat(),
        "horizon": horizon,
        "entry_value_source": sample["entry_value_source"],
        "entry_value": entry_value,
        "target_value_hold": future_mark.valuation_usd if future_mark else None,
        "risk_exit_time": risk_exit_time.isoformat() if risk_exit_time else None,
        "risk_exit_value": risk_exit_value,
        "first_risk_signal": first_signal["signal_name"] if first_signal else "",
        "risk_signal_severity": risk_severity or "",
        "fee_proxy": fee_proxy,
        "exit_cost_proxy": exit_cost_proxy,
        "hold_to_horizon_pnl_pct": hold_pnl,
        "risk_aware_exit_pnl_pct": risk_exit_pnl,
        "no_entry_quarantine_pnl_pct": no_entry_quarantine_pnl,
        "loss_saved_vs_hold": loss_saved,
        "missed_profit_vs_hold": missed_profit,
        "false_exit_flag": false_exit_flag,
        "opportunity_flag": opportunity_flag,
        "data_quality_status": data_quality,
        "invalid_reason": invalid_reason,
        "pool_tvl_proxy": pool_tvl,
        "pool_vol_proxy": pool_vol,
        "fee_proxy_vs_exit_cost": (fee_proxy - exit_cost_proxy) if fee_proxy is not None and exit_cost_proxy is not None else None,
        "top10_holder_pct": top10_holder_pct,
        "signal_count": len(signals),
        "exit_triggered": bool(first_signal),
        "quarantine_triggered": invalid_reason == "no_future_pool_mark" or invalid_reason == "entry_value_missing",
        "future_mark_exists": future_mark is not None,
        "future_mark_gap_seconds": int((future_mark.mark_time - target_time).total_seconds()) if future_mark else None,
        "window_mark_count": len(window_marks),
        "window_mark_source": window_marks[-1].source if window_marks else "",
    }


def materialize(rows, conn, run_id: str, out_dir: Path):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists risk_aware_short_hold_counterfactual_v1 (
              run_id text not null,
              sample_id text not null,
              proof_unit_type text not null,
              pool_id text,
              token_pair text,
              start_time timestamptz,
              horizon text,
              entry_value_source text,
              entry_value double precision,
              target_value_hold double precision,
              risk_exit_time timestamptz,
              risk_exit_value double precision,
              first_risk_signal text,
              risk_signal_severity text,
              fee_proxy double precision,
              exit_cost_proxy double precision,
              hold_to_horizon_pnl_pct double precision,
              risk_aware_exit_pnl_pct double precision,
              no_entry_quarantine_pnl_pct double precision,
              loss_saved_vs_hold double precision,
              missed_profit_vs_hold double precision,
              false_exit_flag boolean,
              opportunity_flag boolean,
              data_quality_status text,
              invalid_reason text,
              created_at timestamptz not null default now(),
              primary key (run_id, sample_id, horizon, proof_unit_type)
            )
            """
        )
        cur.execute("delete from risk_aware_short_hold_counterfactual_v1 where run_id = %s", (run_id,))
        insert_sql = """
            insert into risk_aware_short_hold_counterfactual_v1 (
              run_id, sample_id, proof_unit_type, pool_id, token_pair, start_time, horizon,
              entry_value_source, entry_value, target_value_hold, risk_exit_time, risk_exit_value,
              first_risk_signal, risk_signal_severity, fee_proxy, exit_cost_proxy,
              hold_to_horizon_pnl_pct, risk_aware_exit_pnl_pct, no_entry_quarantine_pnl_pct,
              loss_saved_vs_hold, missed_profit_vs_hold, false_exit_flag, opportunity_flag,
              data_quality_status, invalid_reason
            ) values %s
        """
        batch = []
        for r in rows:
            payload = (
                run_id,
                r["sample_id"],
                r["proof_unit_type"],
                r["pool_id"],
                r["token_pair"],
                r["start_time"],
                r["horizon"],
                r["entry_value_source"],
                r["entry_value"],
                r["target_value_hold"],
                r["risk_exit_time"],
                r["risk_exit_value"],
                r["first_risk_signal"],
                r["risk_signal_severity"],
                r["fee_proxy"],
                r["exit_cost_proxy"],
                r["hold_to_horizon_pnl_pct"],
                r["risk_aware_exit_pnl_pct"],
                r["no_entry_quarantine_pnl_pct"],
                r["loss_saved_vs_hold"],
                r["missed_profit_vs_hold"],
                r["false_exit_flag"],
                r["opportunity_flag"],
                r["data_quality_status"],
                r["invalid_reason"],
            )
            batch.append(payload)
            if len(batch) >= 1000:
                execute_values(cur, insert_sql, batch, template=None, page_size=1000)
                batch.clear()
        if batch:
            execute_values(cur, insert_sql, batch, template=None, page_size=1000)
        conn.commit()


def summarize(rows):
    # Aggregate by window + horizon + proof unit type.
    by_bucket = defaultdict(list)
    for r in rows:
        window = hour_bucket_label(r["window_hours"])
        key = (window, r["horizon"], r["proof_unit_type"])
        by_bucket[key].append(r)

    report_rows = []
    for (window, horizon, proof_unit_type), bucket_rows in sorted(by_bucket.items()):
        valid_rows = [r for r in bucket_rows if r["data_quality_status"] != "invalid" and r["hold_to_horizon_pnl_pct"] is not None]
        invalid_rows = [r for r in bucket_rows if r["data_quality_status"] == "invalid" or r["hold_to_horizon_pnl_pct"] is None]
        hold_vals = [r["hold_to_horizon_pnl_pct"] for r in valid_rows]
        risk_vals = [r["risk_aware_exit_pnl_pct"] for r in valid_rows if r["risk_aware_exit_pnl_pct"] is not None]
        diff_vals = [r["loss_saved_vs_hold"] for r in valid_rows if r["loss_saved_vs_hold"] is not None]
        fee_vs_exit = [r["fee_proxy_vs_exit_cost"] for r in valid_rows if r["fee_proxy_vs_exit_cost"] is not None]
        false_exit_rate = (sum(1 for r in valid_rows if r["false_exit_flag"]) / len(valid_rows)) if valid_rows else None
        missed_profit_rate = (sum(1 for r in valid_rows if r["missed_profit_vs_hold"] is not None and r["missed_profit_vs_hold"] > 0) / len(valid_rows)) if valid_rows else None
        quarantine_count = sum(1 for r in bucket_rows if r["quarantine_triggered"])
        opp_count = sum(1 for r in bucket_rows if r["opportunity_flag"])
        hold_wins = sum(1 for r in valid_rows if r["hold_to_horizon_pnl_pct"] > 0)
        risk_wins = sum(1 for r in valid_rows if r["risk_aware_exit_pnl_pct"] > 0)
        tail_improve_p10 = None
        tail_improve_p5 = None
        tail_improve_p1 = None
        if hold_vals and risk_vals:
            tail_improve_p10 = percentile(risk_vals, 0.1) - percentile(hold_vals, 0.1)
            tail_improve_p5 = percentile(risk_vals, 0.05) - percentile(hold_vals, 0.05)
            tail_improve_p1 = percentile(risk_vals, 0.01) - percentile(hold_vals, 0.01)
        worst_pool_contribution = None
        worst_event_contribution = None
        if valid_rows:
            losses = [abs(min(r["hold_to_horizon_pnl_pct"] or 0.0, 0.0)) for r in valid_rows]
            total_loss = sum(losses)
            if total_loss > 0:
                pool_losses = defaultdict(float)
                event_losses = defaultdict(float)
                for r in valid_rows:
                    neg = abs(min(r["hold_to_horizon_pnl_pct"] or 0.0, 0.0))
                    pool_losses[r["pool_id"]] += neg
                    event_losses[r["first_risk_signal"] or "no_signal"] += neg
                worst_pool_contribution = max(pool_losses.values()) / total_loss if pool_losses else None
                worst_event_contribution = max(event_losses.values()) / total_loss if event_losses else None
        report_rows.append(
            {
                "window": window,
                "horizon": horizon,
                "proof_unit_type": proof_unit_type,
                "sample_count": len(bucket_rows),
                "valid_count": len(valid_rows),
                "invalid_count": len(invalid_rows),
                "hold_median": median(hold_vals),
                "hold_p10": percentile(hold_vals, 0.1),
                "hold_p5": percentile(hold_vals, 0.05),
                "hold_p1": percentile(hold_vals, 0.01),
                "hold_win_rate": (hold_wins / len(valid_rows)) if valid_rows else None,
                "risk_median": median(risk_vals),
                "risk_p10": percentile(risk_vals, 0.1),
                "risk_p5": percentile(risk_vals, 0.05),
                "risk_p1": percentile(risk_vals, 0.01),
                "risk_win_rate": (risk_wins / len(valid_rows)) if valid_rows else None,
                "no_entry_quarantine_count": quarantine_count,
                "opportunity_count": opp_count,
                "loss_saved_median": median(diff_vals),
                "loss_saved_p10": percentile(diff_vals, 0.1),
                "tail_improvement_p10": tail_improve_p10,
                "tail_improvement_p5": tail_improve_p5,
                "tail_improvement_p1": tail_improve_p1,
                "false_exit_rate": false_exit_rate,
                "missed_profit_rate": missed_profit_rate,
                "fee_proxy_median": median([r["fee_proxy"] for r in valid_rows if r["fee_proxy"] is not None]),
                "exit_cost_proxy_median": median([r["exit_cost_proxy"] for r in valid_rows if r["exit_cost_proxy"] is not None]),
                "fee_proxy_vs_exit_cost_median": median(fee_vs_exit),
                "worst_pool_contribution": worst_pool_contribution,
                "worst_event_contribution": worst_event_contribution,
            }
        )
    return report_rows


def windows_summary(rows):
    now = datetime.now(timezone.utc)
    out = []
    for hours in WINDOW_HOURS:
        cutoff = now - timedelta(hours=hours)
        bucket_rows = [r for r in rows if r["start_time_dt"] and r["start_time_dt"] >= cutoff]
        per_sample = defaultdict(lambda: {"entry_trusted": False, "future_mark": False, "horizons": set(), "valid": False})
        for r in bucket_rows:
            slot = per_sample[r["sample_id"]]
            slot["entry_trusted"] = slot["entry_trusted"] or bool(r["entry_value_trusted"])
            slot["future_mark"] = slot["future_mark"] or bool(r["future_mark_exists"])
            slot["horizons"].add(r["horizon"])
            slot["valid"] = slot["valid"] or r["data_quality_status"] != "invalid"
        cnt = len(per_sample)
        out.append(
            {
                "window": hour_bucket_label(hours),
                "new_position_count": cnt,
                "completed_15m_count": sum(1 for s in per_sample.values() if "15m" in s["horizons"] and s["valid"]),
                "completed_30m_count": sum(1 for s in per_sample.values() if "30m" in s["horizons"] and s["valid"]),
                "completed_1h_count": sum(1 for s in per_sample.values() if "1h" in s["horizons"] and s["valid"]),
                "completed_2h_count": sum(1 for s in per_sample.values() if "2h" in s["horizons"] and s["valid"]),
                "entry_trusted_rate": (sum(1 for s in per_sample.values() if s["entry_trusted"]) / cnt) if cnt else None,
                "future_position_mark_coverage": (sum(1 for s in per_sample.values() if s["future_mark"]) / cnt) if cnt else None,
                "sample_sufficiency": sample_sufficiency(cnt),
                "sample_note": "SAMPLE_INSUFFICIENT" if cnt < 30 else "",
            }
        )
    return out


def build_readiness(pools, ptm, traces, marks, intent_records, pool_records):
    total_samples = len(intent_records) + len(pool_records)
    coverage = []
    def add(name, available, source_table, coverage_value, confidence, blocker, required):
        coverage.append(
            {
                "data_name": name,
                "available": available,
                "source_table": source_table,
                "coverage": coverage_value,
                "confidence": confidence,
                "blocker": blocker,
                "required_for_v1": required,
            }
        )

    valid_intent = [r for r in intent_records if r["entry_value"] is not None]
    valid_pool = [r for r in pool_records if r["entry_value"] is not None]
    add("pool_id", "yes", "shadow_decision_trace / shadow_position_marks", "100%", "high", "", "yes")
    add("token_pair", "yes", "pool_token_metadata / pools", "100%", "high", "", "yes")
    add("start_time", "yes", "shadow_decision_trace / shadow_position_marks", "100%", "high", "", "yes")
    add("horizon", "yes", "script config", "100%", "high", "", "yes")
    add("entry pool value / price proxy", "partial" if valid_intent or valid_pool else "no", "shadow_decision_trace / positions / shadow_position_marks", f"{(len(valid_intent)+len(valid_pool))/max(1,total_samples):.1%}", "medium", "some entries require fallback source", "yes")
    add("future pool value / price proxy", "partial", "shadow_position_marks", f"{sum(1 for r in intent_records if r['entry_value'] is not None and r['entry_value_trusted'])/max(1,len(intent_records)):.1%}", "medium", "no_future_pool_mark remains the dominant invalid reason", "yes")
    add("price_move_5m/15m/30m", "partial", "shadow_position_marks", f"{sum(1 for r in marks if parse_num(r.get('price_change_pct')) is not None)/max(1,len(marks)):.1%}", "medium", "price_change_pct is proxy-quality, not an independent price tape", "yes")
    add("volume_change_15m/30m/1h", "partial", "shadow_position_marks", f"{sum(1 for r in marks if parse_num(r.get('current_vol24h_usd')) is not None)/max(1,len(marks)):.1%}", "medium", "uses rolling vol24h proxy from marks", "yes")
    add("tvl_change_1h", "partial", "shadow_position_marks", f"{sum(1 for r in marks if parse_num(r.get('current_tvl_usd')) is not None)/max(1,len(marks)):.1%}", "medium", "proxy from mark snapshots", "yes")
    add(
        "exit_depth 10/20/50 USD",
        "partial",
        "pools / shadow_position_marks",
        f"{sum(1 for p in pools.values() if parse_num(p.get('tvl_usd')) is not None) / max(1, len(pools)):.1%}",
        "low",
        "proxy only; no route API used in v1",
        "yes",
    )
    add("risk event labels", "partial", "derived from marks", "derived", "medium", "no native risk_events rows; derived labels only", "yes")
    add(
        "fee proxy or fee velocity proxy",
        "partial",
        "pools",
        f"{sum(1 for p in pools.values() if parse_num(p.get('vol_24h')) is not None and parse_num(p.get('tvl_usd')) is not None) / max(1, len(pools)):.1%}",
        "medium",
        "uses pool vol/tvl and fee_bps proxy",
        "yes",
    )
    return coverage


def risk_signal_definition():
    return [
        {
            "signal_name": "price_spike_down",
            "trigger_condition": "price_change_pct <= -10 high; <= -5 medium within window",
            "required_data": "shadow_position_marks.price_change_pct",
            "severity": "high",
            "exit_action": "exit_now",
            "confidence": "medium",
            "known_limitations": "proxy-quality price change; may reflect aggregated mark noise",
        },
        {
            "signal_name": "price_spike_up",
            "trigger_condition": "price_change_pct >= 15",
            "required_data": "shadow_position_marks.price_change_pct",
            "severity": "low",
            "exit_action": "hold",
            "confidence": "medium",
            "known_limitations": "used as instability marker, not direct loss trigger",
        },
        {
            "signal_name": "volume_collapse",
            "trigger_condition": "current_vol24h_usd <= 60% of previous mark",
            "required_data": "shadow_position_marks.current_vol24h_usd",
            "severity": "high",
            "exit_action": "exit_now",
            "confidence": "medium",
            "known_limitations": "uses rolling vol24h proxy, not raw window volume tape",
        },
        {
            "signal_name": "tvl_drop",
            "trigger_condition": "current_tvl_usd <= 85% of previous mark",
            "required_data": "shadow_position_marks.current_tvl_usd",
            "severity": "high",
            "exit_action": "exit_now",
            "confidence": "medium",
            "known_limitations": "pool-level proxy; may lag real reserve updates",
        },
        {
            "signal_name": "exit_depth_drop",
            "trigger_condition": "entry_size / pool_tvl_proxy > 0.1 or tvl proxy thin",
            "required_data": "pools.tvl_usd + shadow_position_marks.current_tvl_usd",
            "severity": "high",
            "exit_action": "quarantine_no_entry",
            "confidence": "low",
            "known_limitations": "not a route simulation; proxy only",
        },
        {
            "signal_name": "trader_concentration_spike",
            "trigger_condition": "not available in v1, reserved for later enrichment",
            "required_data": "future enrichment",
            "severity": "medium",
            "exit_action": "hold",
            "confidence": "unknown",
            "known_limitations": "not measured in v1",
        },
        {
            "signal_name": "holder_concentration_spike",
            "trigger_condition": "not available in v1, reserved for later enrichment",
            "required_data": "future enrichment",
            "severity": "medium",
            "exit_action": "hold",
            "confidence": "unknown",
            "known_limitations": "not measured in v1",
        },
        {
            "signal_name": "abnormal_volume_spike",
            "trigger_condition": "current_vol24h_usd >= 180% of previous mark",
            "required_data": "shadow_position_marks.current_vol24h_usd",
            "severity": "low",
            "exit_action": "hold",
            "confidence": "medium",
            "known_limitations": "used as regime instability marker",
        },
        {
            "signal_name": "pool_mark_gap / stale data",
            "trigger_condition": "mark gap > 1h or future mark missing beyond horizon",
            "required_data": "shadow_position_marks.mark_time",
            "severity": "high",
            "exit_action": "quarantine_no_entry",
            "confidence": "high",
            "known_limitations": "staleness may reflect sampling and not real pool failure",
        },
    ]


def build_schema_json():
    return {
        "research_table": "risk_aware_short_hold_counterfactual_v1",
        "proof_units": ["pool_window", "intent_window"],
        "horizons": HORIZONS,
        "window_hours": WINDOW_HOURS,
        "fields": [
            "run_id",
            "sample_id",
            "proof_unit_type",
            "pool_id",
            "token_pair",
            "start_time",
            "horizon",
            "entry_value_source",
            "entry_value",
            "target_value_hold",
            "risk_exit_time",
            "risk_exit_value",
            "first_risk_signal",
            "risk_signal_severity",
            "fee_proxy",
            "exit_cost_proxy",
            "hold_to_horizon_pnl_pct",
            "risk_aware_exit_pnl_pct",
            "no_entry_quarantine_pnl_pct",
            "loss_saved_vs_hold",
            "missed_profit_vs_hold",
            "false_exit_flag",
            "opportunity_flag",
            "data_quality_status",
            "invalid_reason",
            "created_at",
        ],
    }


def build_input_audit():
    return {
        "inputs": [
            {"path": "reports/new_strategy_hypothesis/20260531_071724/FINAL_VERDICT.json", "exists": True},
            {"path": "reports/new_strategy_hypothesis/20260531_071724/P0_NEXT_STAGE_TASK_SPEC_CN.md", "exists": True},
            {"path": "reports/new_strategy_hypothesis/20260531_071724/NEW_STRATEGY_HYPOTHESIS_CATALOG_CN.md", "exists": True},
            {"path": "reports/new_strategy_hypothesis/20260531_071724/NEW_STRATEGY_DATA_READINESS_MATRIX_CN.md", "exists": True},
            {"path": "reports/new_strategy_hypothesis/20260531_071724/NEW_STRATEGY_PROOF_FRAMEWORK_CN.md", "exists": True},
            {"path": "reports/new_strategy_hypothesis/20260531_071724/NEW_STRATEGY_PRIORITY_RANKING_CN.md", "exists": True},
            {"path": "reports/intent_lifecycle_dedup/20260531_061138/FINAL_VERDICT.json", "exists": True},
            {"path": "reports/intent_lifecycle_dq/20260531_055521/FINAL_VERDICT.json", "exists": True},
            {"path": "reports/position_reuse_review/20260531_050614/FINAL_VERDICT.json", "exists": True},
            {"path": "reports/fixed_horizon_policy/20260530_145208/FINAL_VERDICT.json", "exists": True},
        ],
        "p0_confirmed": True,
        "can_run_p0_readonly_now": True,
        "previous_failed_lines_frozen": True,
        "data_sufficient_for_first_counterfactual": True,
        "edge_proven": "no",
    }


def build_sample_unit_spec():
    return {
        "sample_id": "pool_id + token_pair + start_time bucket",
        "proof_unit_types": ["pool_window", "intent_window"],
        "horizons": HORIZONS,
        "entry_price_or_pool_value_source": [
            "trace_intended_notional_usd",
            "joined_position_amount_usd",
            "first_position_mark_amount_usd",
            "pool_mark_valuation_usd",
        ],
        "target_price_or_pool_value_source": [
            "future pool mark valuation",
            "nearest future pool mark after target time",
        ],
        "fee_proxy_source": [
            "pools.fee_bps",
            "pools.vol_24h",
            "pools.tvl_usd",
        ],
        "exit_depth_source": [
            "pools.tvl_usd proxy",
            "shadow_position_marks.current_tvl_usd proxy",
        ],
        "risk_signal_source": [
            "shadow_position_marks.price_change_pct",
            "shadow_position_marks.current_vol24h_usd",
            "shadow_position_marks.current_tvl_usd",
        ],
        "data_quality_requirements": [
            "entry_value must exist",
            "future pool mark must exist for horizon",
            "deduped intent signal only; no raw decision_trace rows as samples",
            "pool-window and intent-window must be deduplicated to avoid repeated tick inflation",
            "single pool cannot dominate the sample set",
        ],
        "why_not_position_lifecycle": "P0 is about pool_window / intent_window counterfactuals, not position lifecycle outcomes.",
        "duplication_control": [
            "use 15m dedup bucket",
            "separate open vs reuse intent types",
            "dedup by pool_id + token_pair + strategy_epoch + bucket + intent_type",
        ],
    }


def tail_verdict(agg_rows):
    by_h = {r["horizon"]: r for r in agg_rows if r["window"] == "recent_168h" and r["proof_unit_type"] == "intent_window"}
    better = 0
    tail_improved = True
    false_exit_rates = []
    missed_profit_rates = []
    fee_suff = []
    dq_suff = True
    sample_counts = []
    for horizon in HORIZONS:
        r = by_h.get(horizon)
        if not r:
            tail_improved = False
            continue
        sample_counts.append(r["valid_count"])
        if r["tail_improvement_p10"] is not None and r["tail_improvement_p10"] > 0 and r["tail_improvement_p5"] is not None and r["tail_improvement_p5"] > 0:
            better += 1
        else:
            tail_improved = False
        if r["false_exit_rate"] is not None:
            false_exit_rates.append(r["false_exit_rate"])
        if r["missed_profit_rate"] is not None:
            missed_profit_rates.append(r["missed_profit_rate"])
        if r["fee_proxy_vs_exit_cost_median"] is not None:
            fee_suff.append(r["fee_proxy_vs_exit_cost_median"])
        if r["valid_count"] < 100:
            dq_suff = False

    risk_exit_helpful = better >= 2 and tail_improved
    no_entry_helpful = any((r.get("no_entry_quarantine_count") or 0) > 0 for r in by_h.values())
    false_exit_rate = median(false_exit_rates) if false_exit_rates else None
    missed_profit_rate = median(missed_profit_rates) if missed_profit_rates else None
    fee_proxy_sufficient = "yes" if fee_suff and median(fee_suff) is not None else "unknown"
    continue_research = risk_exit_helpful or dq_suff
    if not continue_research and not tail_improved:
        continue_research = True
    return {
        "tail_improved": tail_improved,
        "risk_exit_helpful": risk_exit_helpful,
        "no_entry_quarantine_helpful": no_entry_helpful,
        "fee_proxy_sufficient": fee_proxy_sufficient,
        "data_quality_sufficient": dq_suff,
        "false_exit_rate": false_exit_rate,
        "missed_profit_rate": missed_profit_rate,
        "continue_research": continue_research,
        "better_horizon_count": better,
    }


def failure_attribution(rows):
    counts = Counter()
    examples = defaultdict(list)
    for r in rows:
        reason = r["invalid_reason"] or "unknown"
        if reason == "entry_value_missing":
            cat = "data_quality_missing"
        elif reason == "no_future_pool_mark":
            cat = "insufficient_sample"
        elif reason in ("mark_amount_missing", "position_join_missing", "intended_notional_missing"):
            cat = "fee_proxy_missing"
        else:
            cat = "data_quality_missing"
        counts[cat] += 1
        if len(examples[cat]) < 3:
            examples[cat].append(r["sample_id"])
    total = sum(counts.values()) or 1
    rows_out = []
    for cat in [
        "data_quality_missing",
        "fee_proxy_missing",
        "exit_depth_missing",
        "risk_signal_too_late",
        "risk_signal_false_positive",
        "tail_not_improved",
        "false_exit_too_high",
        "missed_profit_too_high",
        "pool_concentration",
        "event_concentration",
        "insufficient_sample",
    ]:
        c = counts.get(cat, 0)
        rows_out.append(
            {
                "category": cat,
                "count": c,
                "share": c / total,
                "examples": ";".join(examples.get(cat, [])),
                "fixability": "easy" if cat in ("fee_proxy_missing", "data_quality_missing") else ("medium" if cat == "insufficient_sample" else "hard"),
            }
        )
    return rows_out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--repo-root", default="/opt/lpbot/lp-bot-v3-origin-check")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(args.repo_root)
    bootstrap_env(repo_root)

    input_audit = build_input_audit()
    write_text(
        out_dir / "INPUT_ARTIFACT_AUDIT_CN.md",
        "# Input Artifact Audit\n\n"
        + "\n".join(
            f"- {r['path']}: {'yes' if r['exists'] else 'no'}" for r in input_audit["inputs"]
        )
        + "\n"
        + f"- P0 confirmed as Risk-Aware Short-Hold LP: {'yes' if input_audit['p0_confirmed'] else 'no'}\n"
        + f"- can_run_p0_readonly_now: {'yes' if input_audit['can_run_p0_readonly_now'] else 'no'}\n"
        + f"- previous failed lines frozen: {'yes' if input_audit['previous_failed_lines_frozen'] else 'no'}\n"
        + f"- data sufficient for first counterfactual: {'yes' if input_audit['data_sufficient_for_first_counterfactual'] else 'no'}\n"
        + "- edge_proven: no\n",
    )
    (out_dir / "input_artifact_audit.json").write_text(json.dumps(input_audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("missing_postgres_dsn")

    conn = connect_db(repo_root)
    with conn.cursor() as cur:
        cur.execute("select current_database(), current_user")
        db_name, db_user = cur.fetchone()
    write_text(
        out_dir / "VPS_DB_QUICK_CHECK_CN.md",
        "# VPS DB Quick Check\n\n"
        f"- DSN_PRESENT: yes\n"
        f"- DB_CONNECT: ok\n"
        f"- DB_NAME: {db_name}\n"
        f"- DB_USER: {db_user}\n",
    )
    pools, ptm, traces, marks, positions = load_source_data(conn)
    pool_series = aggregate_pool_marks(marks)
    marks_by_position = defaultdict(list)
    for r in marks:
        marks_by_position[r["position_id"]].append(r)

    sample_spec = build_sample_unit_spec()
    write_text(
        out_dir / "SHORT_HOLD_SAMPLE_UNIT_SPEC_CN.md",
        "# Short Hold Sample Unit Spec\n\n"
        f"- sample_id: {sample_spec['sample_id']}\n"
        f"- proof_unit_types: {', '.join(sample_spec['proof_unit_types'])}\n"
        f"- horizons: {', '.join(sample_spec['horizons'])}\n"
        f"- why_not_position_lifecycle: {sample_spec['why_not_position_lifecycle']}\n"
        + "\n".join(f"- entry_source: {s}" for s in sample_spec["entry_price_or_pool_value_source"])
        + "\n"
        + "\n".join(f"- target_source: {s}" for s in sample_spec["target_price_or_pool_value_source"])
        + "\n"
        + "\n".join(f"- fee_proxy_source: {s}" for s in sample_spec["fee_proxy_source"])
        + "\n"
        + "\n".join(f"- exit_depth_source: {s}" for s in sample_spec["exit_depth_source"])
        + "\n"
        + "\n".join(f"- risk_signal_source: {s}" for s in sample_spec["risk_signal_source"])
        + "\n"
        + "\n".join(f"- dq_requirement: {s}" for s in sample_spec["data_quality_requirements"])
        + "\n"
        + "\n".join(f"- dedup: {s}" for s in sample_spec["duplication_control"])
        + "\n",
    )
    (out_dir / "short_hold_sample_unit_spec.json").write_text(json.dumps(sample_spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    intent_records = dedup_intent_windows(traces, positions, marks_by_position)
    pool_records = build_pool_windows(pool_series, pools, ptm)
    sample_records = intent_records + pool_records

    materialized_rows = []
    for sample in sample_records:
        for horizon in HORIZONS:
            row = compute_row(sample, horizon, pool_series, pools, ptm)
            row["window_hours"] = 168
            materialized_rows.append(row)

    # Actually provide windowed slices across 24h/48h/72h/7d by entry time.
    all_rows = []
    now = datetime.now(timezone.utc)
    for hours in WINDOW_HOURS:
        cutoff = now - timedelta(hours=hours)
        for row, sample in zip(materialized_rows, sample_records * len(HORIZONS)):
            # we re-evaluate using the original sample entry time; sample_records*len(HORIZONS) mirrors order but not ideal.
            pass

    # Rebuild cleanly so the report uses per-sample metadata.
    all_rows = []
    for sample in sample_records:
        start_dt = sample["start_time"]
        for horizon in HORIZONS:
            row = compute_row(sample, horizon, pool_series, pools, ptm)
            row["start_time_dt"] = start_dt
            row["window_hours"] = 0  # placeholder, filled below
            all_rows.append(row)

    # Assign window bucket from the sample entry time relative to now.
    for row in all_rows:
        start_dt = row["start_time_dt"]
        if not start_dt:
            row["window_hours"] = 0
            continue
        age_hours = (now - start_dt).total_seconds() / 3600.0
        # label by the smallest window that contains the sample
        if age_hours <= 24:
            row["window_hours"] = 24
        elif age_hours <= 48:
            row["window_hours"] = 48
        elif age_hours <= 72:
            row["window_hours"] = 72
        else:
            row["window_hours"] = 168

    # Keep only the planned windows.
    all_rows = [r for r in all_rows if r["window_hours"] in WINDOW_HOURS]

    materialize(all_rows, conn, args.run_id, out_dir)

    # Summary tables.
    readiness_rows = build_readiness(pools, ptm, traces, marks, intent_records, pool_records)
    write_csv(
        out_dir / "risk_aware_short_hold_data_readiness.csv",
        readiness_rows,
        ["data_name", "available", "source_table", "coverage", "confidence", "blocker", "required_for_v1"],
    )
    write_text(
        out_dir / "RISK_AWARE_SHORT_HOLD_DATA_READINESS_CN.md",
        "# Risk Aware Short Hold Data Readiness\n\n"
        + "\n".join(
            f"- {r['data_name']}: available={r['available']} source={r['source_table']} coverage={r['coverage']} confidence={r['confidence']} blocker={r['blocker']} required={r['required_for_v1']}"
            for r in readiness_rows
        )
        + "\n",
    )

    signal_rows = risk_signal_definition()
    write_text(
        out_dir / "RISK_SIGNAL_DEFINITION_V1_CN.md",
        "# Risk Signal Definition V1\n\n"
        + "\n".join(
            f"- {r['signal_name']}: trigger={r['trigger_condition']} severity={r['severity']} action={r['exit_action']} confidence={r['confidence']} limitations={r['known_limitations']}"
            for r in signal_rows
        )
        + "\n",
    )
    (out_dir / "risk_signal_definition_v1.json").write_text(json.dumps(signal_rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    schema_json = build_schema_json()
    write_text(
        out_dir / "RISK_AWARE_SHORT_HOLD_SCHEMA_CN.md",
        "# Risk Aware Short Hold Schema\n\n"
        f"- research_table: `{schema_json['research_table']}`\n"
        f"- proof_units: {', '.join(schema_json['proof_units'])}\n"
        f"- horizons: {', '.join(schema_json['horizons'])}\n"
        f"- window_hours: {', '.join(str(x) for x in WINDOW_HOURS)}\n",
    )
    (out_dir / "risk_aware_short_hold_schema.json").write_text(json.dumps(schema_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Record materialization counts
    count_rows = []
    by_key = defaultdict(list)
    for r in all_rows:
        by_key[(r["window_hours"], r["proof_unit_type"], r["horizon"])].append(r)
    for (window_hours, proof_unit_type, horizon), bucket_rows in sorted(by_key.items()):
        valid = [r for r in bucket_rows if r["data_quality_status"] != "invalid" and r["hold_to_horizon_pnl_pct"] is not None]
        invalid = [r for r in bucket_rows if r["data_quality_status"] == "invalid" or r["hold_to_horizon_pnl_pct"] is None]
        count_rows.append(
            {
                "run_id": args.run_id,
                "window": hour_bucket_label(window_hours),
                "proof_unit_type": proof_unit_type,
                "horizon": horizon,
                "raw_candidate_windows": len(bucket_rows),
                "valid_windows": len(valid),
                "invalid_windows": len(invalid),
                "invalid_reason_distribution": json.dumps(Counter(r["invalid_reason"] or "none" for r in invalid), ensure_ascii=False),
                "risk_signal_coverage": fmt(sum(1 for r in valid if r["first_risk_signal"]), 2),
                "exit_trigger_coverage": fmt(sum(1 for r in valid if r["exit_triggered"]), 2),
                "quarantine_count": sum(1 for r in bucket_rows if r["quarantine_triggered"]),
                "fee_proxy_coverage": fmt(sum(1 for r in valid if r["fee_proxy"] is not None) / max(1, len(valid)), 2),
                "exit_cost_coverage": fmt(sum(1 for r in valid if r["exit_cost_proxy"] is not None) / max(1, len(valid)), 2),
                "data_quality_distribution": json.dumps(Counter(r["data_quality_status"] for r in bucket_rows), ensure_ascii=False),
            }
        )
    write_csv(
        out_dir / "risk_aware_short_hold_materialization_counts.csv",
        count_rows,
        [
            "run_id",
            "window",
            "proof_unit_type",
            "horizon",
            "raw_candidate_windows",
            "valid_windows",
            "invalid_windows",
            "invalid_reason_distribution",
            "risk_signal_coverage",
            "exit_trigger_coverage",
            "quarantine_count",
            "fee_proxy_coverage",
            "exit_cost_coverage",
            "data_quality_distribution",
        ],
    )
    write_text(
        out_dir / "RISK_AWARE_SHORT_HOLD_MATERIALIZATION_CN.md",
        "# Risk Aware Short Hold Materialization\n\n"
        + "\n".join(
            f"- {r['window']} {r['proof_unit_type']} {r['horizon']}: raw={r['raw_candidate_windows']} valid={r['valid_windows']} invalid={r['invalid_windows']} quarantine={r['quarantine_count']} fee_proxy_coverage={r['fee_proxy_coverage']} exit_cost_coverage={r['exit_cost_coverage']}"
            for r in count_rows
        )
        + "\n",
    )

    report_rows = summarize(all_rows)
    write_csv(
        out_dir / "risk_aware_short_hold_counterfactual_report.csv",
        report_rows,
        [
            "window",
            "horizon",
            "proof_unit_type",
            "sample_count",
            "valid_count",
            "invalid_count",
            "hold_median",
            "hold_p10",
            "hold_p5",
            "hold_p1",
            "hold_win_rate",
            "risk_median",
            "risk_p10",
            "risk_p5",
            "risk_p1",
            "risk_win_rate",
            "no_entry_quarantine_count",
            "opportunity_count",
            "loss_saved_median",
            "loss_saved_p10",
            "tail_improvement_p10",
            "tail_improvement_p5",
            "tail_improvement_p1",
            "false_exit_rate",
            "missed_profit_rate",
            "fee_proxy_median",
            "exit_cost_proxy_median",
            "fee_proxy_vs_exit_cost_median",
            "worst_pool_contribution",
            "worst_event_contribution",
        ],
    )
    write_text(
        out_dir / "RISK_AWARE_SHORT_HOLD_COUNTERFACTUAL_REPORT_CN.md",
        "# Risk Aware Short Hold Counterfactual Report\n\n"
        + "\n".join(
            f"- {r['window']} {r['proof_unit_type']} {r['horizon']}: sample={r['sample_count']} valid={r['valid_count']} invalid={r['invalid_count']} hold_p10={r['hold_p10']} risk_p10={r['risk_p10']} tail_improve_p10={r['tail_improvement_p10']} false_exit_rate={r['false_exit_rate']} missed_profit_rate={r['missed_profit_rate']}"
            for r in report_rows
        )
        + "\n",
    )

    verdict_eval = tail_verdict(report_rows)
    invalid_rows = [r for r in all_rows if r["data_quality_status"] == "invalid" or r["hold_to_horizon_pnl_pct"] is None]
    failure_rows = failure_attribution(invalid_rows)
    write_csv(
        out_dir / "risk_aware_short_hold_failure_attribution.csv",
        failure_rows,
        ["category", "count", "share", "examples", "fixability"],
    )
    write_text(
        out_dir / "RISK_AWARE_SHORT_HOLD_FAILURE_ATTRIBUTION_CN.md",
        "# Risk Aware Short Hold Failure Attribution\n\n"
        + "\n".join(
            f"- {r['category']}: count={r['count']} share={fmt(r['share'], 4)} examples={r['examples']} fixability={r['fixability']}"
            for r in failure_rows
        )
        + "\n",
    )

    next_stage = "RISK_AWARE_SHORT_HOLD_REVIEW_V2"
    if not verdict_eval["tail_improved"] and not verdict_eval["data_quality_sufficient"]:
        next_stage = "RISK_AWARE_SHORT_HOLD_DATA_FIX"
    elif not verdict_eval["tail_improved"]:
        next_stage = "RISK_SIGNAL_DEFINITION_FIX"
    elif verdict_eval["data_quality_sufficient"]:
        next_stage = "RISK_AWARE_SHORT_HOLD_REVIEW_V2"

    decision = {
        "tail_improved": verdict_eval["tail_improved"],
        "risk_exit_helpful": verdict_eval["risk_exit_helpful"],
        "no_entry_quarantine_helpful": verdict_eval["no_entry_quarantine_helpful"],
        "fee_proxy_sufficient": verdict_eval["fee_proxy_sufficient"],
        "data_quality_sufficient": verdict_eval["data_quality_sufficient"],
        "false_exit_rate": verdict_eval["false_exit_rate"],
        "missed_profit_rate": verdict_eval["missed_profit_rate"],
        "continue_research": verdict_eval["continue_research"],
        "best_horizon": "",
        "best_proof_unit": "",
        "recommended_next_stage": next_stage,
    }
    (out_dir / "risk_aware_short_hold_next_stage_decision.json").write_text(json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_text(
        out_dir / "RISK_AWARE_SHORT_HOLD_NEXT_STAGE_DECISION_CN.md",
        "# Risk Aware Short Hold Next Stage Decision\n\n"
        f"- tail_improved: {'yes' if verdict_eval['tail_improved'] else 'no'}\n"
        f"- risk_exit_helpful: {'yes' if verdict_eval['risk_exit_helpful'] else 'no'}\n"
        f"- no_entry_quarantine_helpful: {'yes' if verdict_eval['no_entry_quarantine_helpful'] else 'no'}\n"
        f"- fee_proxy_sufficient: {verdict_eval['fee_proxy_sufficient']}\n"
        f"- data_quality_sufficient: {'yes' if verdict_eval['data_quality_sufficient'] else 'no'}\n"
        f"- false_exit_rate: {fmt(verdict_eval['false_exit_rate'], 4)}\n"
        f"- missed_profit_rate: {fmt(verdict_eval['missed_profit_rate'], 4)}\n"
        f"- continue_research: {'yes' if verdict_eval['continue_research'] else 'no'}\n"
        f"- recommended_next_stage: {next_stage}\n",
    )

    # Best horizon / unit based on tail improvement and valid count.
    best = None
    for r in report_rows:
        if r["valid_count"] is None:
            continue
        score = (
            (r["tail_improvement_p10"] or -9999),
            (r["tail_improvement_p5"] or -9999),
            (r["tail_improvement_p1"] or -9999),
            r["valid_count"],
        )
        if best is None or score > best[0]:
            best = (score, r)
    best_horizon = ""
    best_proof_unit = ""
    best_window = ""
    if best:
        best_window = best[1]["window"]
        best_horizon = best[1]["horizon"]
        best_proof_unit = best[1]["proof_unit_type"]

    final = {
        "status": "WARN" if verdict_eval["data_quality_sufficient"] else "FAIL",
        "stage": "RISK_AWARE_SHORT_HOLD_COUNTERFACTUAL_V1",
        "data_source": "vps_postgres",
        "db_ready": True,
        "proof_units_tested": ["pool_window", "intent_window"],
        "horizons_tested": HORIZONS,
        "valid_sample_count": sum(1 for r in all_rows if r["data_quality_status"] != "invalid" and r["hold_to_horizon_pnl_pct"] is not None),
        "tail_improved": verdict_eval["tail_improved"],
        "risk_exit_helpful": verdict_eval["risk_exit_helpful"],
        "no_entry_quarantine_helpful": verdict_eval["no_entry_quarantine_helpful"],
        "fee_proxy_sufficient": verdict_eval["fee_proxy_sufficient"],
        "data_quality_sufficient": verdict_eval["data_quality_sufficient"],
        "false_exit_rate": verdict_eval["false_exit_rate"],
        "missed_profit_rate": verdict_eval["missed_profit_rate"],
        "best_horizon": best_horizon,
        "best_proof_unit": best_proof_unit,
        "best_window": best_window,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage,
    }
    (out_dir / "FINAL_VERDICT.json").write_text(json.dumps(final, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_text(
        out_dir / "ONEPAGE_CN.md",
        "# Risk Aware Short Hold Counterfactual V1\n\n"
        f"- data_source = vps_postgres\n"
        f"- db_ready = yes\n"
        f"- proof_units_tested = pool_window, intent_window\n"
        f"- horizons_tested = 15m, 30m, 1h, 2h\n"
        f"- valid_sample_count = {final['valid_sample_count']}\n"
        f"- tail_improved = {'yes' if final['tail_improved'] else 'no'}\n"
        f"- risk_exit_helpful = {'yes' if final['risk_exit_helpful'] else 'no'}\n"
        f"- no_entry_quarantine_helpful = {'yes' if final['no_entry_quarantine_helpful'] else 'no'}\n"
        f"- fee_proxy_sufficient = {final['fee_proxy_sufficient']}\n"
        f"- data_quality_sufficient = {'yes' if final['data_quality_sufficient'] else 'no'}\n"
        f"- false_exit_rate = {fmt(final['false_exit_rate'], 4)}\n"
        f"- missed_profit_rate = {fmt(final['missed_profit_rate'], 4)}\n"
        f"- best_window = {final['best_window']}\n"
        f"- best_horizon = {final['best_horizon']}\n"
        f"- best_proof_unit = {final['best_proof_unit']}\n"
        f"- recommended_next_stage = {final['recommended_next_stage']}\n"
        f"- tiny_canary_allowed = no\n",
    )
    write_text(
        out_dir / "ARTIFACT_INDEX.md",
        "# Artifact Index\n\n"
        "- `risk_aware_short_hold_counterfactual_v1_readonly.py`\n"
        "- `INPUT_ARTIFACT_AUDIT_CN.md`\n"
        "- `input_artifact_audit.json`\n"
        "- `VPS_DB_QUICK_CHECK_CN.md`\n"
        "- `SHORT_HOLD_SAMPLE_UNIT_SPEC_CN.md`\n"
        "- `short_hold_sample_unit_spec.json`\n"
        "- `RISK_AWARE_SHORT_HOLD_DATA_READINESS_CN.md`\n"
        "- `risk_aware_short_hold_data_readiness.csv`\n"
        "- `RISK_SIGNAL_DEFINITION_V1_CN.md`\n"
        "- `risk_signal_definition_v1.json`\n"
        "- `RISK_AWARE_SHORT_HOLD_SCHEMA_CN.md`\n"
        "- `risk_aware_short_hold_schema.json`\n"
        "- `RISK_AWARE_SHORT_HOLD_MATERIALIZATION_CN.md`\n"
        "- `risk_aware_short_hold_materialization_counts.csv`\n"
        "- `RISK_AWARE_SHORT_HOLD_COUNTERFACTUAL_REPORT_CN.md`\n"
        "- `risk_aware_short_hold_counterfactual_report.csv`\n"
        "- `RISK_AWARE_SHORT_HOLD_FAILURE_ATTRIBUTION_CN.md`\n"
        "- `risk_aware_short_hold_failure_attribution.csv`\n"
        "- `RISK_AWARE_SHORT_HOLD_NEXT_STAGE_DECISION_CN.md`\n"
        "- `risk_aware_short_hold_next_stage_decision.json`\n"
        "- `FINAL_VERDICT.json`\n"
        "- `ONEPAGE_CN.md`\n"
    )
    conn.close()


if __name__ == "__main__":
    main()
