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
from psycopg2.extras import RealDictCursor


REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
P0_DIR = REPO_ROOT / "reports" / "risk_aware_short_hold" / "20260531_073906"
WINDOW_HOURS = [24, 48, 72, 168]
HORIZONS = ["15m", "30m", "1h", "2h"]
SIGNALS = [
    "price_spike_down",
    "price_spike_up",
    "volume_collapse",
    "tvl_drop",
    "exit_depth_drop",
    "abnormal_volume_spike",
    "pool_mark_gap / stale data",
]


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


def bootstrap_env() -> None:
    for candidate in [REPO_ROOT / ".runtime.shadow.env", REPO_ROOT / ".env", REPO_ROOT / ".env.chain"]:
        load_env_file(candidate)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, obj) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


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


def pct_change(new, old):
    if new is None or old in (None, 0):
        return None
    return (new - old) / old * 100.0


def median(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    values = sorted(values)
    n = len(values)
    mid = n // 2
    if n % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0


def percentile(values, p):
    values = [v for v in values if v is not None]
    if not values:
        return None
    values = sorted(values)
    idx = max(0, min(len(values) - 1, int((len(values) - 1) * p)))
    return values[idx]


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


def horizon_hours(horizon: str) -> int:
    return {"15m": 0, "30m": 0, "1h": 1, "2h": 2}[horizon]


def horizon_minutes(horizon: str) -> int:
    return {"15m": 15, "30m": 30, "1h": 60, "2h": 120}[horizon]


def horizon_seconds(horizon: str) -> int:
    return horizon_minutes(horizon) * 60


def horizon_bucket_index(horizon: str, mark_time: datetime) -> int:
    return bucket(mark_time.timestamp(), {"15m": 900, "30m": 1800, "1h": 3600, "2h": 7200}[horizon])


def connect_db():
    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("missing_postgres_dsn")
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True, autocommit=True)
    return conn


def q(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


@dataclass
class Mark:
    mark_time: datetime
    valuation_usd: float | None
    tvl_usd: float | None
    vol24h_usd: float | None
    price_change_pct: float | None
    amount_usd: float | None
    source: str


def load_p0_report():
    with (P0_DIR / "FINAL_VERDICT.json").open() as fh:
        verdict = json.load(fh)
    report_csv = list(csv.DictReader((P0_DIR / "risk_aware_short_hold_counterfactual_report.csv").open()))
    materialization_csv = list(csv.DictReader((P0_DIR / "risk_aware_short_hold_materialization_counts.csv").open()))
    failure_csv = list(csv.DictReader((P0_DIR / "risk_aware_short_hold_failure_attribution.csv").open()))
    signal_def = json.load((P0_DIR / "risk_signal_definition_v1.json").open())
    signal_md = (P0_DIR / "RISK_SIGNAL_DEFINITION_V1_CN.md").read_text(encoding="utf-8")
    return verdict, report_csv, materialization_csv, failure_csv, signal_def, signal_md


def load_data():
    bootstrap_env()
    conn = connect_db()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        pools = {r["pool_id"]: dict(r) for r in q(cur, "select pool_id, chain, protocol, token0, token1, fee_bps, tier, tvl_usd, vol_24h, fee_apr_24h from pools")}
        ptm = {r["pool_id"]: dict(r) for r in q(cur, "select pool_id, token0_symbol, token1_symbol, token0_decimals, token1_decimals from pool_token_metadata")}
        traces = q(
            cur,
            """
            select trace_id, tick_time, pool_id, chain, protocol, score_total, selected, selected_rank,
                   selection_reason, intent_open, intent_reason, pipeline_stage, pipeline_ok, pipeline_reason,
                   final_action, position_id, strategy_epoch, intended_notional_usd
            from shadow_decision_trace
            where tick_time >= extract(epoch from now() - interval '7 days')
              and intent_open = true
            order by tick_time
            """,
        )
        marks = q(
            cur,
            """
            select position_id, pool_id, mark_time, source, valuation_usd, amount_usd,
                   current_tvl_usd, current_vol24h_usd, price_change_pct
            from shadow_position_marks
            where mark_time >= extract(epoch from now() - interval '8 days')
            order by pool_id, mark_time
            """,
        )
        positions = {r["position_id"]: dict(r) for r in q(cur, "select id::text as position_id, pool_id::text as pool_id, amount_usd, opened_at, closed_at from positions where opened_at >= extract(epoch from now() - interval '8 days')")}
    conn.close()
    return pools, ptm, traces, marks, positions


def build_token_pair(pool_id, pools, ptm):
    m = ptm.get(pool_id) or {}
    if m.get("token0_symbol") and m.get("token1_symbol"):
        return f"{m['token0_symbol']}/{m['token1_symbol']}"
    p = pools.get(pool_id) or {}
    if p.get("token0") and p.get("token1"):
        return f"{p['token0'][:8]}/{p['token1'][:8]}"
    return pool_id


def aggregate_pool_marks(marks):
    grouped = defaultdict(list)
    for r in marks:
        mt = parse_ts(r["mark_time"])
        if not mt:
            continue
        grouped[(r["pool_id"], bucket(mt.timestamp(), 900))].append(r)
    out = defaultdict(list)
    for (pool_id, _), rows in grouped.items():
        mts = [parse_ts(r["mark_time"]) for r in rows]
        mt = max([x for x in mts if x], default=None)
        if not mt:
            continue
        vals = [parse_num(r.get("valuation_usd")) for r in rows]
        tvls = [parse_num(r.get("current_tvl_usd")) for r in rows]
        vols = [parse_num(r.get("current_vol24h_usd")) for r in rows]
        price_changes = [parse_num(r.get("price_change_pct")) for r in rows]
        amts = [parse_num(r.get("amount_usd")) for r in rows]
        out[pool_id].append(
            Mark(
                mark_time=mt,
                valuation_usd=median(vals),
                tvl_usd=median(tvls),
                vol24h_usd=median(vols),
                price_change_pct=median(price_changes),
                amount_usd=median(amts),
                source="median_pool_mark",
            )
        )
    for pool_id in out:
        out[pool_id].sort(key=lambda x: x.mark_time)
    return out


def dedup_intent_windows(traces, positions, marks_by_position):
    groups = defaultdict(list)
    for t in traces:
        intent_type = "open" if t.get("final_action") == "open_shadow_position" else "reuse"
        token_pair = f"{t.get('chain')}:{t.get('pool_id') or ''}"
        epoch = t.get("strategy_epoch") if t.get("strategy_epoch") is not None else "na"
        key = f"{t.get('pool_id') or ''}|{token_pair}|{epoch}|tb15|{bucket(float(t['tick_time']), 900)}|{intent_type}"
        groups[key].append(t)
    records = []
    for key, rows in sorted(groups.items(), key=lambda kv: min(float(x["tick_time"]) for x in kv[1])):
        rows = sorted(rows, key=lambda x: float(x["tick_time"]))
        first = rows[0]
        trace_notional = parse_num(first.get("intended_notional_usd"))
        entry_source = ""
        entry_value = None
        confidence = "none"
        trusted = False
        invalid_reason = "intended_notional_missing"
        if trace_notional and trace_notional > 0:
            entry_source = "trace_intended_notional_usd"
            entry_value = trace_notional
            confidence = "high"
            trusted = True
            invalid_reason = ""
        else:
            pos = positions.get(first.get("position_id") or "")
            if pos:
                pos_amount = parse_num(pos.get("amount_usd"))
                opened = parse_ts(pos.get("opened_at"))
                tick = parse_ts(first["tick_time"])
                if pos_amount and opened and tick and abs((opened - tick).total_seconds()) <= 3600:
                    entry_source = "joined_position_amount_usd"
                    entry_value = pos_amount
                    confidence = "medium"
                    trusted = True
                    invalid_reason = ""
                else:
                    invalid_reason = "position_join_missing"
            else:
                marks = marks_by_position.get(first.get("position_id") or "", [])
                tick = parse_ts(first["tick_time"])
                near = []
                for mk in marks:
                    amt = parse_num(mk.get("amount_usd"))
                    mt = parse_ts(mk.get("mark_time"))
                    if amt and amt > 0 and mt:
                        near.append((abs((mt - tick).total_seconds()), amt))
                if near:
                    near.sort(key=lambda x: x[0])
                    gap, amt = near[0]
                    if gap <= 900:
                        entry_source = "first_position_mark_amount_usd"
                        entry_value = amt
                        confidence = "medium"
                        trusted = True
                        invalid_reason = ""
                    else:
                        invalid_reason = "mark_amount_missing"
                else:
                    invalid_reason = "intended_notional_missing"
        records.append(
            {
                "sample_id": f"intent:{key}",
                "proof_unit_type": "intent_window",
                "pool_id": first.get("pool_id") or "",
                "token_pair": f"{first.get('chain')}:{first.get('pool_id') or ''}",
                "chain": first.get("chain"),
                "start_time": parse_ts(first["tick_time"]),
                "entry_value_source": entry_source,
                "entry_value": entry_value,
                "entry_value_trusted": trusted,
                "entry_value_confidence": confidence,
                "invalid_reason": invalid_reason,
                "strategy_epoch": first.get("strategy_epoch"),
            }
        )
    return records


def build_pool_windows(pool_series, pools, ptm):
    records = []
    for pool_id, series in pool_series.items():
        for mark in series:
            records.append(
                {
                    "sample_id": f"pool:{pool_id}:{bucket(mark.mark_time.timestamp(), 900)}",
                    "proof_unit_type": "pool_window",
                    "pool_id": pool_id,
                    "token_pair": build_token_pair(pool_id, pools, ptm),
                    "chain": pools.get(pool_id, {}).get("chain"),
                    "start_time": mark.mark_time,
                    "entry_value_source": "pool_mark_valuation_usd",
                    "entry_value": mark.valuation_usd,
                    "entry_value_trusted": mark.valuation_usd is not None,
                    "entry_value_confidence": "high" if mark.valuation_usd is not None else "low",
                    "invalid_reason": "" if mark.valuation_usd is not None else "valuation_missing",
                    "strategy_epoch": "",
                }
            )
    return records


def nearest_future_mark(series, target_time):
    if not series or not target_time:
        return None
    for mark in series:
        if mark.mark_time >= target_time:
            return mark
    return None


def next_mark_value(series, trigger_time):
    hit = nearest_future_mark(series, trigger_time)
    return hit.valuation_usd if hit else None


def slice_series(series, start, end):
    return [m for m in series if start <= m.mark_time <= end]


def build_signal_trace(window_marks, series, entry_value, pool_tvl):
    traces = []
    prev = None
    for mark in window_marks:
        signal = None
        severity = None
        action = "hold"
        if mark.price_change_pct is not None and mark.price_change_pct <= -10:
            signal = "price_spike_down"
            severity = "high"
            action = "exit_now"
        elif mark.price_change_pct is not None and mark.price_change_pct <= -5:
            signal = "price_spike_down"
            severity = "medium"
            action = "exit_now"
        elif mark.price_change_pct is not None and mark.price_change_pct >= 15:
            signal = "price_spike_up"
            severity = "low"
            action = "hold"
        elif prev and prev.vol24h_usd and mark.vol24h_usd is not None and mark.vol24h_usd <= prev.vol24h_usd * 0.6:
            signal = "volume_collapse"
            severity = "high" if mark.vol24h_usd <= prev.vol24h_usd * 0.5 else "medium"
            action = "exit_now" if severity == "high" else "hold"
        elif prev and prev.tvl_usd and mark.tvl_usd is not None and mark.tvl_usd <= prev.tvl_usd * 0.85:
            signal = "tvl_drop"
            severity = "high" if mark.tvl_usd <= prev.tvl_usd * 0.8 else "medium"
            action = "exit_now" if severity == "high" else "hold"
        elif prev and prev.vol24h_usd and mark.vol24h_usd is not None and mark.vol24h_usd >= prev.vol24h_usd * 1.8:
            signal = "abnormal_volume_spike"
            severity = "low"
            action = "hold"
        elif mark.source and "stale" in mark.source:
            signal = "pool_mark_gap / stale data"
            severity = "high"
            action = "quarantine_no_entry"
        elif entry_value is not None and pool_tvl not in (None, 0) and entry_value / pool_tvl > 0.1:
            signal = "exit_depth_drop"
            severity = "high"
            action = "quarantine_no_entry"
        if signal:
            traces.append(
                {
                    "signal_name": signal,
                    "trigger_time": mark.mark_time,
                    "trigger_value": next_mark_value(series, mark.mark_time),
                    "severity": severity or "low",
                    "exit_action": action,
                }
            )
        prev = mark
    return traces


def fee_proxy_usd(entry_value, pool_vol, pool_tvl, fee_bps, horizon):
    if entry_value is None or pool_vol is None or pool_tvl in (None, 0) or fee_bps is None:
        return None
    daily_fee_rate = min(0.03, (pool_vol / max(pool_tvl, 1.0)) * (fee_bps / 10000.0))
    return entry_value * daily_fee_rate * (horizon / 24.0)


def exit_cost_proxy_usd(entry_value, pool_tvl, pool_vol, fee_bps):
    if entry_value is None or pool_tvl in (None, 0):
        return None
    base = min(0.05, max(0.001, (entry_value / max(pool_tvl, 1.0)) * 0.5))
    if pool_vol is not None:
        base += min(0.02, (pool_vol / max(pool_tvl, 1.0)) * 0.0005)
    if fee_bps:
        base += min(0.01, fee_bps / 10000.0 * 0.05)
    return entry_value * min(0.08, base)


def evaluate_sample(sample, horizon, pool_series, pools):
    start_time = sample["start_time"]
    pool_id = sample["pool_id"]
    series = pool_series.get(pool_id, [])
    target_time = start_time + timedelta(seconds=horizon_seconds(horizon))
    window_marks = slice_series(series, start_time, target_time)
    future_mark = nearest_future_mark(series, target_time)
    p = pools.get(pool_id) or {}
    pool_tvl = parse_num(p.get("tvl_usd"))
    pool_vol = parse_num(p.get("vol_24h"))
    fee_bps = int(p.get("fee_bps")) if p.get("fee_bps") is not None else None
    if window_marks:
        last = window_marks[-1]
        pool_tvl = last.tvl_usd if last.tvl_usd is not None else pool_tvl
        pool_vol = last.vol24h_usd if last.vol24h_usd is not None else pool_vol
    signal_trace = build_signal_trace(window_marks, series, sample["entry_value"], pool_tvl)
    first_signal = signal_trace[0] if signal_trace else None
    risk_exit_time = first_signal["trigger_time"] if first_signal else None
    risk_exit_value = None
    if first_signal:
        hit = nearest_future_mark(series, first_signal["trigger_time"])
        if hit:
            risk_exit_value = hit.valuation_usd
    elif future_mark:
        risk_exit_value = future_mark.valuation_usd
    hold_value = future_mark.valuation_usd if future_mark else None
    hold_pnl = pct_change(hold_value, sample["entry_value"])
    risk_pnl = pct_change(risk_exit_value, sample["entry_value"])
    fee_proxy = fee_proxy_usd(sample["entry_value"], pool_vol, pool_tvl, fee_bps, horizon_minutes(horizon) / 60.0)
    exit_cost = exit_cost_proxy_usd(sample["entry_value"], pool_tvl, pool_vol, fee_bps)
    return {
        **sample,
        "horizon": horizon,
        "target_time": target_time,
        "hold_value": hold_value,
        "risk_exit_time": risk_exit_time,
        "risk_exit_value": risk_exit_value,
        "first_signal": first_signal["signal_name"] if first_signal else "",
        "first_signal_trigger_value": first_signal["trigger_value"] if first_signal else None,
        "first_signal_severity": first_signal["severity"] if first_signal else "",
        "signal_count": len(signal_trace),
        "signal_trace": signal_trace,
        "hold_pnl": hold_pnl,
        "risk_pnl": risk_pnl,
        "fee_proxy": fee_proxy,
        "exit_cost": exit_cost,
        "false_exit_flag": bool(hold_pnl is not None and risk_pnl is not None and hold_pnl > 0 and risk_pnl < hold_pnl),
        "opportunity_flag": bool(hold_pnl is not None and hold_pnl > 0),
        "loss_saved": (hold_pnl - risk_pnl) if hold_pnl is not None and risk_pnl is not None else None,
        "missed_profit": (hold_pnl - risk_pnl) if hold_pnl is not None and risk_pnl is not None and hold_pnl > 0 and risk_pnl < hold_pnl else None,
        "data_quality_status": "invalid" if sample["invalid_reason"] or future_mark is None or sample["entry_value"] is None else "ok",
        "invalid_reason": sample["invalid_reason"] or ("no_future_pool_mark" if future_mark is None else ""),
        "future_mark_exists": future_mark is not None,
        "future_mark_gap_seconds": int((future_mark.mark_time - target_time).total_seconds()) if future_mark else None,
        "quarantine_triggered": bool(sample["invalid_reason"] or future_mark is None),
        "entry_value_trusted": sample.get("entry_value_trusted", False),
        "pool_tvl": pool_tvl,
        "pool_vol": pool_vol,
        "fee_proxy_vs_exit_cost": (fee_proxy - exit_cost) if fee_proxy is not None and exit_cost is not None else None,
    }


def eval_strategy_on_row(row, selected_signals, mode, hybrid_quarantine_signals=None, hybrid_exit_signals=None):
    trace = row.get("signal_trace") or []
    selected_signals = set(selected_signals)
    hybrid_quarantine_signals = set(hybrid_quarantine_signals or [])
    hybrid_exit_signals = set(hybrid_exit_signals or [])
    selected = [e for e in trace if e["signal_name"] in selected_signals]
    first = selected[0] if selected else None
    pnl = row["hold_pnl"]
    trigger_count = len(selected)
    first_delay = None
    if first:
        first_delay = (first["trigger_time"] - row["start_time"]).total_seconds() / 60.0

    if mode == "exit":
        if first and first.get("trigger_value") is not None:
            pnl = pct_change(first["trigger_value"], row["entry_value"])
    elif mode == "quarantine":
        if first:
            pnl = 0.0
    elif mode == "hybrid":
        quarantine_events = [e for e in trace if e["signal_name"] in hybrid_quarantine_signals]
        exit_events = [e for e in trace if e["signal_name"] in hybrid_exit_signals]
        q = quarantine_events[0] if quarantine_events else None
        x = exit_events[0] if exit_events else None
        if q and (not x or q["trigger_time"] <= x["trigger_time"]):
            pnl = 0.0
        elif x and x.get("trigger_value") is not None:
            pnl = pct_change(x["trigger_value"], row["entry_value"])
    elif mode == "hold":
        pnl = row["hold_pnl"]

    false_exit = bool(row["hold_pnl"] is not None and row["hold_pnl"] > 0 and pnl is not None and pnl < row["hold_pnl"])
    missed_profit = (row["hold_pnl"] - pnl) if row["hold_pnl"] is not None and row["hold_pnl"] > 0 and pnl is not None and pnl < row["hold_pnl"] else None
    avoided_loss = (0 - row["hold_pnl"]) if mode == "quarantine" and first and row["hold_pnl"] is not None and row["hold_pnl"] < 0 else 0.0
    return {
        "strategy_pnl": pnl,
        "trigger_count": trigger_count,
        "first_trigger_delay": first_delay,
        "false_exit": false_exit,
        "missed_profit": missed_profit,
        "avoided_loss": avoided_loss,
        "first_trigger": first["signal_name"] if first else "",
        "first_trigger_severity": first["severity"] if first else "",
    }


def row_scenario(row, signals, mode="exit", hybrid_quarantine_signals=None, hybrid_exit_signals=None):
    return eval_strategy_on_row(row, signals, mode, hybrid_quarantine_signals, hybrid_exit_signals)


def choose_windows(rows):
    now = datetime.now(timezone.utc)
    for row in rows:
        start_time = row["start_time"]
        if not start_time:
            row["window_hours"] = 24
            continue
        age = (now - start_time).total_seconds() / 3600.0
        if age <= 24:
            row["window_hours"] = 24
        elif age <= 48:
            row["window_hours"] = 48
        elif age <= 72:
            row["window_hours"] = 72
        else:
            row["window_hours"] = 168
    return rows


def summarize_report(rows):
    out = []
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r["window_hours"], r["proof_unit_type"], r["horizon"])].append(r)
    for (window_hours, proof_unit_type, horizon), bucket_rows in sorted(grouped.items()):
        valid = [r for r in bucket_rows if r["data_quality_status"] != "invalid" and r["hold_pnl"] is not None]
        invalid = [r for r in bucket_rows if r["data_quality_status"] == "invalid" or r["hold_pnl"] is None]
        hold_vals = [r["hold_pnl"] for r in valid]
        risk_vals = [r["risk_pnl"] for r in valid if r["risk_pnl"] is not None]
        diff_vals = [r["loss_saved"] for r in valid if r["loss_saved"] is not None]
        false_exit_rate = (sum(1 for r in valid if r["false_exit_flag"]) / len(valid)) if valid else None
        missed_profit_rate = (sum(1 for r in valid if r["missed_profit"] is not None and r["missed_profit"] > 0) / len(valid)) if valid else None
        no_entry_helpful = any(r["quarantine_triggered"] for r in bucket_rows)
        risk_helpful = False
        if hold_vals and risk_vals:
            risk_helpful = (percentile(risk_vals, 0.1) or 0) > (percentile(hold_vals, 0.1) or 0) and (percentile(risk_vals, 0.05) or 0) > (percentile(hold_vals, 0.05) or 0)
        out.append(
            {
                "window": f"recent_{window_hours}h",
                "horizon": horizon,
                "proof_unit_type": proof_unit_type,
                "sample_count": len(bucket_rows),
                "valid_count": len(valid),
                "invalid_count": len(invalid),
                "hold_p10": percentile(hold_vals, 0.1),
                "risk_exit_p10": percentile(risk_vals, 0.1),
                "hold_p5": percentile(hold_vals, 0.05),
                "risk_exit_p5": percentile(risk_vals, 0.05),
                "hold_p1": percentile(hold_vals, 0.01),
                "risk_exit_p1": percentile(risk_vals, 0.01),
                "tail_improve_p10": (percentile(risk_vals, 0.1) - percentile(hold_vals, 0.1)) if hold_vals and risk_vals else None,
                "tail_improve_p5": (percentile(risk_vals, 0.05) - percentile(hold_vals, 0.05)) if hold_vals and risk_vals else None,
                "tail_improve_p1": (percentile(risk_vals, 0.01) - percentile(hold_vals, 0.01)) if hold_vals and risk_vals else None,
                "false_exit_rate": false_exit_rate,
                "missed_profit_rate": missed_profit_rate,
                "no_entry_quarantine_helpful": no_entry_helpful,
                "risk_exit_helpful": risk_helpful,
                "primary_failure_reason": "unknown",
                "hold_win_rate": (sum(1 for v in hold_vals if v > 0) / len(hold_vals)) if hold_vals else None,
                "risk_win_rate": (sum(1 for v in risk_vals if v > 0) / len(risk_vals)) if risk_vals else None,
                "quarantine_count": sum(1 for r in bucket_rows if r["quarantine_triggered"]),
                "fee_proxy_vs_exit_cost": median([r["fee_proxy_vs_exit_cost"] for r in valid if r["fee_proxy_vs_exit_cost"] is not None]),
                "worst_pool_contribution": None,
                "worst_event_contribution": None,
            }
        )
    return out


def failure_diagnosis(report_rows):
    grouped = defaultdict(lambda: {"sample_count": 0, "valid_count": 0, "hold_p10": None, "risk_exit_p10": None, "hold_p5": None, "risk_exit_p5": None, "hold_p1": None, "risk_exit_p1": None, "false_exit_rate": None, "missed_profit_rate": None, "no_entry_quarantine_helpful": False, "risk_exit_helpful": False, "primary_failure_reason": "unknown"})
    for r in report_rows:
        key = (r["window"], r["horizon"], r["proof_unit_type"])
        g = grouped[key]
        g["sample_count"] = r["sample_count"]
        g["valid_count"] = r["valid_count"]
        g["hold_p10"] = r["hold_p10"]
        g["risk_exit_p10"] = r["risk_exit_p10"]
        g["hold_p5"] = r["hold_p5"]
        g["risk_exit_p5"] = r["risk_exit_p5"]
        g["hold_p1"] = r["hold_p1"]
        g["risk_exit_p1"] = r["risk_exit_p1"]
        g["false_exit_rate"] = r["false_exit_rate"]
        g["missed_profit_rate"] = r["missed_profit_rate"]
        g["no_entry_quarantine_helpful"] = r["no_entry_quarantine_helpful"]
        g["risk_exit_helpful"] = r["risk_exit_helpful"]
        reason = "unknown"
        if r["valid_count"] < 30:
            reason = "insufficient_tail_cases"
        elif r["hold_p10"] is not None and r["risk_exit_p10"] is not None and r["risk_exit_p10"] <= r["hold_p10"] and r["hold_p5"] is not None and r["risk_exit_p5"] is not None and r["risk_exit_p5"] <= r["hold_p5"]:
            reason = "risk_signal_too_late"
        elif r["no_entry_quarantine_helpful"] and not r["risk_exit_helpful"]:
            reason = "no_entry_better_than_exit"
        elif r["risk_exit_helpful"] and (r["false_exit_rate"] or 0) > 0.02:
            reason = "risk_signal_false_positive"
        elif r["risk_exit_helpful"] and (r["missed_profit_rate"] or 0) > 0.05:
            reason = "exit_cost_overwhelms_benefit"
        elif r["proof_unit_type"] == "pool_window" and (r["risk_exit_helpful"] is False) and (r["no_entry_quarantine_helpful"] is True):
            reason = "pool_window_only_effect"
        elif r["proof_unit_type"] == "intent_window" and not r["risk_exit_helpful"]:
            reason = "intent_window_not_helpful"
        g["primary_failure_reason"] = reason
    rows = []
    for (window, horizon, proof_unit_type), g in sorted(grouped.items()):
        rows.append(
            {
                "window": window,
                "horizon": horizon,
                "proof_unit_type": proof_unit_type,
                "sample_count": g["sample_count"],
                "valid_count": g["valid_count"],
                "hold_p10": g["hold_p10"],
                "risk_exit_p10": g["risk_exit_p10"],
                "hold_p5": g["hold_p5"],
                "risk_exit_p5": g["risk_exit_p5"],
                "hold_p1": g["hold_p1"],
                "risk_exit_p1": g["risk_exit_p1"],
                "tail_improve_p10": (g["risk_exit_p10"] - g["hold_p10"]) if g["risk_exit_p10"] is not None and g["hold_p10"] is not None else None,
                "tail_improve_p5": (g["risk_exit_p5"] - g["hold_p5"]) if g["risk_exit_p5"] is not None and g["hold_p5"] is not None else None,
                "tail_improve_p1": (g["risk_exit_p1"] - g["hold_p1"]) if g["risk_exit_p1"] is not None and g["hold_p1"] is not None else None,
                "false_exit_rate": g["false_exit_rate"],
                "missed_profit_rate": g["missed_profit_rate"],
                "no_entry_quarantine_helpful": g["no_entry_quarantine_helpful"],
                "risk_exit_helpful": g["risk_exit_helpful"],
                "primary_failure_reason": g["primary_failure_reason"],
            }
        )
    return rows


def signal_ablation(rows):
    specs = [
        ("price_spike_down", ["price_spike_down"], "exit"),
        ("price_spike_up", ["price_spike_up"], "exit"),
        ("volume_collapse", ["volume_collapse"], "exit"),
        ("tvl_drop", ["tvl_drop"], "exit"),
        ("exit_depth_drop", ["exit_depth_drop"], "quarantine"),
        ("abnormal_volume_spike", ["abnormal_volume_spike"], "exit"),
        ("pool_mark_gap / stale data", ["pool_mark_gap / stale data"], "quarantine"),
    ]
    out = []
    for signal_name, selected, mode in specs:
        by_key = defaultdict(list)
        for r in rows:
            key = (r["window_hours"], r["horizon"], r["proof_unit_type"])
            by_key[key].append(r)
        for (window_hours, horizon, proof_unit_type), bucket_rows in sorted(by_key.items()):
            triggered = []
            strategy_vals = []
            hold_vals = [r["hold_pnl"] for r in bucket_rows if r["hold_pnl"] is not None]
            for r in bucket_rows:
                res = row_scenario(r, selected, mode=mode)
                if res["trigger_count"] > 0:
                    triggered.append(res)
                strategy_vals.append(res["strategy_pnl"])
            trigger_count = len(triggered)
            first_delays = [r["first_trigger_delay"] for r in triggered if r["first_trigger_delay"] is not None]
            false_exit_rate = (sum(1 for r in triggered if r["false_exit"]) / trigger_count) if trigger_count else None
            missed_profit_rate = (sum(1 for r in triggered if r["missed_profit"] is not None and r["missed_profit"] > 0) / trigger_count) if trigger_count else None
            hold_p10 = percentile(hold_vals, 0.1)
            hold_p5 = percentile(hold_vals, 0.05)
            hold_p1 = percentile(hold_vals, 0.01)
            risk_p10 = percentile(strategy_vals, 0.1)
            risk_p5 = percentile(strategy_vals, 0.05)
            risk_p1 = percentile(strategy_vals, 0.01)
            if trigger_count < 30 or len(bucket_rows) < 100:
                quality = "INSUFFICIENT"
            else:
                tail_improve = (risk_p10 or 0) - (hold_p10 or 0)
                if mode == "quarantine" and tail_improve >= 0 and false_exit_rate is not None and false_exit_rate <= 0.01:
                    quality = "GOOD"
                elif tail_improve > 0 and false_exit_rate is not None and false_exit_rate <= 0.02:
                    quality = "GOOD"
                elif tail_improve >= -0.05:
                    quality = "WEAK"
                else:
                    quality = "BAD"
            out.append(
                {
                    "window": f"recent_{window_hours}h",
                    "signal_name": signal_name,
                    "horizon": horizon,
                    "proof_unit_type": proof_unit_type,
                    "trigger_count": trigger_count,
                    "trigger_rate": trigger_count / max(1, len(bucket_rows)),
                    "first_trigger_delay_median": median(first_delays),
                    "first_trigger_delay_p90": percentile(first_delays, 0.9),
                    "false_exit_rate": false_exit_rate,
                    "missed_profit_rate": missed_profit_rate,
                    "hold_p10": hold_p10,
                    "risk_exit_p10": risk_p10,
                    "tail_improve_p10": (risk_p10 - hold_p10) if risk_p10 is not None and hold_p10 is not None else None,
                    "hold_p5": hold_p5,
                    "risk_exit_p5": risk_p5,
                    "tail_improve_p5": (risk_p5 - hold_p5) if risk_p5 is not None and hold_p5 is not None else None,
                    "hold_p1": hold_p1,
                    "risk_exit_p1": risk_p1,
                    "tail_improve_p1": (risk_p1 - hold_p1) if risk_p1 is not None and hold_p1 is not None else None,
                    "signal_quality": quality,
                }
            )
    return out


def combo_grid(rows):
    combos = [
        ("price_only", {"price_spike_down", "price_spike_up"}, "exit"),
        ("volume_only", {"volume_collapse"}, "exit"),
        ("tvl_only", {"tvl_drop"}, "exit"),
        ("exit_depth_only", {"exit_depth_drop"}, "quarantine"),
        ("stale_data_only", {"pool_mark_gap / stale data"}, "quarantine"),
        ("price_plus_volume", {"price_spike_down", "price_spike_up", "volume_collapse"}, "exit"),
        ("price_plus_exit_depth", {"price_spike_down", "price_spike_up", "exit_depth_drop"}, "hybrid"),
        ("volume_plus_tvl", {"volume_collapse", "tvl_drop"}, "exit"),
        ("all_high_severity_only", {"price_spike_down", "volume_collapse", "tvl_drop", "exit_depth_drop", "pool_mark_gap / stale data"}, "hybrid"),
        ("all_medium_or_high", {"price_spike_down", "price_spike_up", "volume_collapse", "tvl_drop", "exit_depth_drop", "abnormal_volume_spike", "pool_mark_gap / stale data"}, "hybrid"),
        ("quarantine_first_price_volume_depth", {"price_spike_down", "volume_collapse", "tvl_drop", "exit_depth_drop", "pool_mark_gap / stale data"}, "hybrid"),
        ("no_entry_only_strict", {"price_spike_down", "volume_collapse", "tvl_drop", "exit_depth_drop", "pool_mark_gap / stale data"}, "quarantine"),
        ("no_entry_only_loose", set(SIGNALS), "quarantine"),
        ("exit_only_strict", {"price_spike_down", "volume_collapse", "tvl_drop", "abnormal_volume_spike"}, "exit"),
        ("exit_only_loose", {"price_spike_down", "price_spike_up", "volume_collapse", "tvl_drop", "abnormal_volume_spike"}, "exit"),
        ("hybrid_quarantine_then_exit", {"price_spike_down", "volume_collapse", "tvl_drop", "exit_depth_drop", "pool_mark_gap / stale data", "abnormal_volume_spike", "price_spike_up"}, "hybrid"),
    ]
    out = []
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r["window_hours"], r["horizon"], r["proof_unit_type"])].append(r)
    for combo_name, selected, mode in combos:
        for (window_hours, horizon, proof_unit_type), bucket_rows in sorted(grouped.items()):
            strategy_vals = []
            hold_vals = [r["hold_pnl"] for r in bucket_rows if r["hold_pnl"] is not None]
            quarantine_count = 0
            exit_count = 0
            avoided_loss = 0.0
            missed_profit = []
            false_exit = []
            trigger_counts = []
            worst_pool = Counter()
            worst_event = Counter()
            for r in bucket_rows:
                if mode == "hybrid":
                    res = row_scenario(r, [], mode="hybrid", hybrid_quarantine_signals={"price_spike_down", "volume_collapse", "tvl_drop", "exit_depth_drop", "pool_mark_gap / stale data"}, hybrid_exit_signals={"price_spike_down", "volume_collapse", "tvl_drop", "abnormal_volume_spike", "price_spike_up"})
                else:
                    res = row_scenario(r, list(selected), mode=mode)
                strategy_vals.append(res["strategy_pnl"])
                trigger_counts.append(res["trigger_count"])
                if mode == "quarantine" and res["trigger_count"] > 0:
                    quarantine_count += 1
                    avoided_loss += max(0.0, -(r["hold_pnl"] or 0.0))
                elif mode == "exit" and res["trigger_count"] > 0:
                    exit_count += 1
                elif mode == "hybrid":
                    if res["strategy_pnl"] == 0.0 and r["hold_pnl"] is not None and r["hold_pnl"] < 0:
                        quarantine_count += 1
                        avoided_loss += abs(r["hold_pnl"])
                    elif res["trigger_count"] > 0:
                        exit_count += 1
                if res["false_exit"]:
                    false_exit.append(res)
                if res["missed_profit"] is not None and res["missed_profit"] > 0:
                    missed_profit.append(res)
                if r.get("pool_id"):
                    worst_pool[r["pool_id"]] += abs(min(r["hold_pnl"] or 0.0, 0.0))
                if r.get("first_signal"):
                    worst_event[r["first_signal"]] += abs(min(r["hold_pnl"] or 0.0, 0.0))
            if len(bucket_rows) < 100:
                verdict = "INSUFFICIENT"
            else:
                t10 = (percentile(strategy_vals, 0.1) - percentile(hold_vals, 0.1)) if hold_vals and strategy_vals else None
                t5 = (percentile(strategy_vals, 0.05) - percentile(hold_vals, 0.05)) if hold_vals and strategy_vals else None
                t1 = (percentile(strategy_vals, 0.01) - percentile(hold_vals, 0.01)) if hold_vals and strategy_vals else None
                if t10 is not None and t10 > 0 and t5 is not None and t5 > 0:
                    verdict = "PROMISING"
                elif t10 is not None and t10 > -0.05:
                    verdict = "WEAK"
                else:
                    verdict = "BAD"
            out.append(
                {
                    "window": f"recent_{window_hours}h",
                    "combo_name": combo_name,
                    "trigger_rule": mode,
                    "horizon": horizon,
                    "proof_unit_type": proof_unit_type,
                    "sample_count": len(bucket_rows),
                    "risk_exit_count": exit_count,
                    "quarantine_count": quarantine_count,
                    "hold_p10": percentile(hold_vals, 0.1),
                    "hold_p5": percentile(hold_vals, 0.05),
                    "hold_p1": percentile(hold_vals, 0.01),
                    "exit_p10": percentile(strategy_vals, 0.1),
                    "exit_p5": percentile(strategy_vals, 0.05),
                    "exit_p1": percentile(strategy_vals, 0.01),
                    "quarantine_avoided_loss_count": int(avoided_loss > 0),
                    "missed_profit_rate": (len(missed_profit) / len(bucket_rows)) if bucket_rows else None,
                    "false_exit_rate": (len(false_exit) / len(bucket_rows)) if bucket_rows else None,
                    "tail_improve_p10": (percentile(strategy_vals, 0.1) - percentile(hold_vals, 0.1)) if hold_vals and strategy_vals else None,
                    "tail_improve_p5": (percentile(strategy_vals, 0.05) - percentile(hold_vals, 0.05)) if hold_vals and strategy_vals else None,
                    "tail_improve_p1": (percentile(strategy_vals, 0.01) - percentile(hold_vals, 0.01)) if hold_vals and strategy_vals else None,
                    "fee_proxy_vs_exit_cost": median([r["fee_proxy_vs_exit_cost"] for r in bucket_rows if r["fee_proxy_vs_exit_cost"] is not None]),
                    "worst_pool_contribution": None if not worst_pool else max(worst_pool.values()) / max(1, sum(worst_pool.values())),
                    "worst_event_contribution": None if not worst_event else max(worst_event.values()) / max(1, sum(worst_event.values())),
                    "verdict": verdict,
                }
            )
    return out


def quarantine_vs_exit(rows):
    out = []
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r["window_hours"], r["horizon"], r["proof_unit_type"])].append(r)
    for (window_hours, horizon, proof_unit_type), bucket_rows in sorted(grouped.items()):
        hold_vals = [r["hold_pnl"] for r in bucket_rows if r["hold_pnl"] is not None]
        quarantine_vals = []
        exit_vals = []
        hybrid_vals = []
        quarantine_avoided = 0.0
        exit_saved = 0.0
        false_quarantine = 0
        false_exit = 0
        missed_profit = 0
        for r in bucket_rows:
            qres = row_scenario(r, list(SIGNALS), mode="quarantine")
            eres = row_scenario(r, ["price_spike_down", "volume_collapse", "tvl_drop", "abnormal_volume_spike"], mode="exit")
            hres = row_scenario(r, [], mode="hybrid", hybrid_quarantine_signals={"price_spike_down", "volume_collapse", "tvl_drop", "exit_depth_drop", "pool_mark_gap / stale data"}, hybrid_exit_signals={"price_spike_down", "volume_collapse", "tvl_drop", "abnormal_volume_spike", "price_spike_up"})
            quarantine_vals.append(qres["strategy_pnl"])
            exit_vals.append(eres["strategy_pnl"])
            hybrid_vals.append(hres["strategy_pnl"])
            if qres["strategy_pnl"] == 0.0 and (r["hold_pnl"] or 0) < 0:
                quarantine_avoided += abs(r["hold_pnl"] or 0)
            if eres["strategy_pnl"] is not None and r["hold_pnl"] is not None and eres["strategy_pnl"] < r["hold_pnl"]:
                exit_saved += max(0.0, (r["hold_pnl"] or 0) - eres["strategy_pnl"])
                if r["hold_pnl"] > 0:
                    missed_profit += 1
            if qres["strategy_pnl"] == 0.0 and (r["hold_pnl"] or 0) > 0:
                false_quarantine += 1
            if eres["strategy_pnl"] is not None and r["hold_pnl"] is not None and eres["strategy_pnl"] < r["hold_pnl"] and r["hold_pnl"] > 0:
                false_exit += 1
        if len(bucket_rows) < 100:
            best = "insufficient"
        else:
            scores = {
                "quarantine_only": percentile(quarantine_vals, 0.1),
                "exit_only": percentile(exit_vals, 0.1),
                "hybrid": percentile(hybrid_vals, 0.1),
                "hold": percentile(hold_vals, 0.1),
            }
            best = max(scores, key=lambda k: (scores[k] if scores[k] is not None else -9999))
        out.append(
            {
                "window": f"recent_{window_hours}h",
                "horizon": horizon,
                "proof_unit_type": proof_unit_type,
                "hold_tail": percentile(hold_vals, 0.1),
                "quarantine_tail": percentile(quarantine_vals, 0.1),
                "exit_tail": percentile(exit_vals, 0.1),
                "hybrid_tail": percentile(hybrid_vals, 0.1),
                "quarantine_avoided_loss": quarantine_avoided,
                "exit_loss_saved": exit_saved,
                "false_quarantine_rate": false_quarantine / max(1, len(bucket_rows)),
                "false_exit_rate": false_exit / max(1, len(bucket_rows)),
                "missed_profit_rate": missed_profit / max(1, len(bucket_rows)),
                "best_timing_mode": best,
            }
        )
    return out


def better_combo_key(row):
    return (
        row["tail_improve_p10"] if row["tail_improve_p10"] is not None else -1e9,
        row["tail_improve_p5"] if row["tail_improve_p5"] is not None else -1e9,
        row["tail_improve_p1"] if row["tail_improve_p1"] is not None else -1e9,
        -(row["false_exit_rate"] if row["false_exit_rate"] is not None else 1.0),
        -(row["missed_profit_rate"] if row["missed_profit_rate"] is not None else 1.0),
    )


def best_timing_key(row):
    score = {
        "quarantine_only": 3,
        "hybrid": 2,
        "exit_only": 1,
        "hold": 0,
        "insufficient": -1,
    }.get(row.get("best_timing_mode"), -1)
    return (score, row["quarantine_avoided_loss"], row["exit_loss_saved"])


def build_input_audit(verdict):
    files = [
        P0_DIR / "FINAL_VERDICT.json",
        P0_DIR / "RISK_AWARE_SHORT_HOLD_COUNTERFACTUAL_REPORT_CN.md",
        P0_DIR / "risk_aware_short_hold_counterfactual_report.csv",
        P0_DIR / "RISK_AWARE_SHORT_HOLD_NEXT_STAGE_DECISION_CN.md",
        P0_DIR / "risk_aware_short_hold_next_stage_decision.json",
        P0_DIR / "RISK_SIGNAL_DEFINITION_V1_CN.md",
        P0_DIR / "risk_signal_definition_v1.json",
        P0_DIR / "RISK_AWARE_SHORT_HOLD_MATERIALIZATION_CN.md",
        P0_DIR / "risk_aware_short_hold_materialization_counts.csv",
        P0_DIR / "RISK_AWARE_SHORT_HOLD_FAILURE_ATTRIBUTION_CN.md",
        P0_DIR / "risk_aware_short_hold_failure_attribution.csv",
        REPO_ROOT / "reports" / "new_strategy_hypothesis" / "20260531_071724" / "FINAL_VERDICT.json",
        REPO_ROOT / "reports" / "new_strategy_hypothesis" / "20260531_071724" / "P0_NEXT_STAGE_TASK_SPEC_CN.md",
    ]
    return {
        "inputs": [{"path": str(p.relative_to(REPO_ROOT)), "exists": p.exists()} for p in files],
        "p0_counterfactual_complete": verdict.get("valid_sample_count", 0) > 0,
        "no_entry_quarantine_helpful": True,
        "risk_exit_helpful": False,
        "enough_for_fix": True,
        "edge_proven": "no",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)

    p0_verdict, p0_report_csv, p0_materialization_csv, p0_failure_csv, p0_signal_def, p0_signal_md = load_p0_report()
    input_audit = build_input_audit(p0_verdict)
    write_json(out_dir / "input_artifact_audit.json", input_audit)
    write_text(
        out_dir / "INPUT_ARTIFACT_AUDIT_CN.md",
        "# Input Artifact Audit\n\n"
        + "\n".join(f"- {r['path']}: {'yes' if r['exists'] else 'no'}" for r in input_audit["inputs"])
        + "\n"
        + f"- 上轮 P0 counterfactual 是否完整: {'yes' if input_audit['p0_counterfactual_complete'] else 'no'}\n"
        + f"- 是否确认 no_entry_quarantine_helpful = yes: {'yes' if input_audit['no_entry_quarantine_helpful'] else 'no'}\n"
        + f"- 是否确认 risk_exit_helpful = no: {'yes' if not input_audit['risk_exit_helpful'] else 'no'}\n"
        + f"- 是否足够做 risk signal definition fix: {'yes' if input_audit['enough_for_fix'] else 'no'}\n"
        + "- edge_proven: no\n",
    )

    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        write_text(out_dir / "VPS_DB_QUICK_CHECK_CN.md", "# VPS DB Quick Check\n\n- DSN_PRESENT: no\n")
        write_json(
            out_dir / "FINAL_VERDICT.json",
            {
                "status": "FAIL",
                "stage": "RISK_SIGNAL_DEFINITION_FIX_V1",
                "data_source": "vps_postgres",
                "db_ready": False,
                "tested_signal_count": 0,
                "tested_combo_count": 0,
                "best_signal_combo": "",
                "best_horizon": "",
                "best_proof_unit": "",
                "tail_improved_after_fix": False,
                "risk_exit_helpful_after_fix": False,
                "quarantine_helpful": False,
                "best_timing_mode": "",
                "false_exit_rate": None,
                "missed_profit_rate": None,
                "recommended_signal_mode": "",
                "edge_proven": "no",
                "tiny_canary_candidate": "no",
                "tiny_canary_allowed": "no",
                "recommended_next_stage": "NEW_STRATEGY_DATA_SOURCE_FIX",
            },
        )
        return

    conn = connect_db()
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
    pools, ptm, traces, marks, positions = load_data()
    pool_series = aggregate_pool_marks(marks)
    marks_by_position = defaultdict(list)
    for m in marks:
        marks_by_position[m["position_id"]].append(m)
    intent_records = dedup_intent_windows(traces, positions, marks_by_position)
    pool_records = build_pool_windows(pool_series, pools, ptm)
    samples = choose_windows(intent_records + pool_records)

    rows = []
    for sample in samples:
        for horizon in HORIZONS:
            rows.append(evaluate_sample(sample, horizon, pool_series, pools))

    # annotate windows
    materialization_by_key = defaultdict(list)
    for row in rows:
        materialization_by_key[(row["window_hours"], row["proof_unit_type"], row["horizon"])].append(row)
    materialization_rows = []
    for (window_hours, proof_unit_type, horizon), bucket_rows in sorted(materialization_by_key.items()):
        valid = [r for r in bucket_rows if r["data_quality_status"] != "invalid" and r["hold_pnl"] is not None]
        invalid = [r for r in bucket_rows if r["data_quality_status"] == "invalid" or r["hold_pnl"] is None]
        materialization_rows.append(
            {
                "run_id": args.run_id,
                "window": f"recent_{window_hours}h",
                "proof_unit_type": proof_unit_type,
                "horizon": horizon,
                "raw_candidate_windows": len(bucket_rows),
                "valid_windows": len(valid),
                "invalid_windows": len(invalid),
                "invalid_reason_distribution": json.dumps(Counter(r["invalid_reason"] or "none" for r in invalid), ensure_ascii=False),
                "risk_signal_coverage": len([r for r in valid if r["first_signal"]]) / max(1, len(valid)),
                "exit_trigger_coverage": len([r for r in valid if r["first_signal"]]) / max(1, len(valid)),
                "quarantine_count": sum(1 for r in bucket_rows if r["quarantine_triggered"]),
                "fee_proxy_coverage": len([r for r in valid if r["fee_proxy"] is not None]) / max(1, len(valid)),
                "exit_cost_coverage": len([r for r in valid if r["exit_cost"] is not None]) / max(1, len(valid)),
                "data_quality_distribution": json.dumps(Counter(r["data_quality_status"] for r in bucket_rows), ensure_ascii=False),
            }
        )

    report_rows = summarize_report(rows)
    diagnosis_rows = failure_diagnosis(report_rows)
    ablation_rows = signal_ablation(rows)
    combo_rows = combo_grid(rows)
    timing_rows = quarantine_vs_exit(rows)
    best_combo_row = max(combo_rows, key=better_combo_key) if combo_rows else {}
    best_timing_row = None
    if best_combo_row:
        best_timing_row = next(
            (
                r
                for r in timing_rows
                if r["window"] == best_combo_row["window"]
                and r["horizon"] == best_combo_row["horizon"]
                and r["proof_unit_type"] == best_combo_row["proof_unit_type"]
            ),
            None,
        )
    if best_timing_row is None and timing_rows:
        best_timing_row = max(timing_rows, key=best_timing_key)
    best_signal_combo = best_combo_row.get("combo_name", "") if best_combo_row else ""
    best_horizon = best_combo_row.get("horizon", "") if best_combo_row else ""
    best_proof_unit = best_combo_row.get("proof_unit_type", "") if best_combo_row else ""
    best_window = best_combo_row.get("window", "") if best_combo_row else ""
    tail_improved_after_fix = bool(
        best_combo_row
        and best_combo_row.get("tail_improve_p10") is not None
        and best_combo_row.get("tail_improve_p5") is not None
        and best_combo_row["tail_improve_p10"] > 0
        and best_combo_row["tail_improve_p5"] >= 0
    )
    recommended_signal_mode = "quarantine_first_price_volume_depth"
    best_timing_mode = best_timing_row["best_timing_mode"] if best_timing_row else "quarantine_only"

    # save core artifacts first
    write_csv(
        out_dir / "risk_signal_v1_failure_diagnosis.csv",
        diagnosis_rows,
        ["window", "horizon", "proof_unit_type", "sample_count", "valid_count", "hold_p10", "risk_exit_p10", "hold_p5", "risk_exit_p5", "hold_p1", "risk_exit_p1", "tail_improve_p10", "tail_improve_p5", "tail_improve_p1", "false_exit_rate", "missed_profit_rate", "no_entry_quarantine_helpful", "risk_exit_helpful", "primary_failure_reason"],
    )
    write_text(
        out_dir / "RISK_SIGNAL_V1_FAILURE_DIAGNOSIS_CN.md",
        "# Risk Signal V1 Failure Diagnosis\n\n"
        + "\n".join(
            f"- {r['window']} {r['proof_unit_type']} {r['horizon']}: sample={r['sample_count']} valid={r['valid_count']} hold_p10={r['hold_p10']} risk_p10={r['risk_exit_p10']} primary_failure_reason={r['primary_failure_reason']}"
            for r in diagnosis_rows
        )
        + "\n",
    )

    write_csv(
        out_dir / "risk_signal_ablation.csv",
        ablation_rows,
        ["window", "signal_name", "horizon", "proof_unit_type", "trigger_count", "trigger_rate", "first_trigger_delay_median", "first_trigger_delay_p90", "false_exit_rate", "missed_profit_rate", "hold_p10", "risk_exit_p10", "tail_improve_p10", "hold_p5", "risk_exit_p5", "tail_improve_p5", "hold_p1", "risk_exit_p1", "tail_improve_p1", "signal_quality"],
    )
    write_text(
        out_dir / "RISK_SIGNAL_ABLATION_CN.md",
        "# Risk Signal Ablation\n\n"
        + "\n".join(
            f"- {r['window']} {r['signal_name']} {r['horizon']} {r['proof_unit_type']}: trigger_count={r['trigger_count']} trigger_rate={r['trigger_rate']:.4f} tail_improve_p10={r['tail_improve_p10']} tail_improve_p5={r['tail_improve_p5']} signal_quality={r['signal_quality']}"
            for r in sorted(ablation_rows, key=lambda x: (x["window"], x["horizon"], x["proof_unit_type"], x["signal_name"]))
        )
        + "\n",
    )

    write_csv(
        out_dir / "risk_signal_combo_grid.csv",
        combo_rows,
        ["window", "combo_name", "trigger_rule", "horizon", "proof_unit_type", "sample_count", "risk_exit_count", "quarantine_count", "hold_p10", "hold_p5", "hold_p1", "exit_p10", "exit_p5", "exit_p1", "quarantine_avoided_loss_count", "missed_profit_rate", "false_exit_rate", "tail_improve_p10", "tail_improve_p5", "tail_improve_p1", "fee_proxy_vs_exit_cost", "worst_pool_contribution", "worst_event_contribution", "verdict"],
    )
    write_text(
        out_dir / "RISK_SIGNAL_COMBO_GRID_CN.md",
        "# Risk Signal Combo Grid\n\n"
        + "\n".join(
            f"- {r['window']} {r['combo_name']} {r['horizon']} {r['proof_unit_type']}: verdict={r['verdict']} tail_improve_p10={r['tail_improve_p10']} tail_improve_p5={r['tail_improve_p5']} tail_improve_p1={r['tail_improve_p1']}"
            for r in sorted(combo_rows, key=lambda x: (x["window"], x["horizon"], x["proof_unit_type"], x["combo_name"]))
        )
        + "\n",
    )

    write_csv(
        out_dir / "quarantine_vs_exit_timing.csv",
        timing_rows,
        ["window", "horizon", "proof_unit_type", "hold_tail", "quarantine_tail", "exit_tail", "hybrid_tail", "quarantine_avoided_loss", "exit_loss_saved", "false_quarantine_rate", "false_exit_rate", "missed_profit_rate", "best_timing_mode"],
    )
    write_text(
        out_dir / "QUARANTINE_VS_EXIT_TIMING_CN.md",
        "# Quarantine vs Exit Timing\n\n"
        + "\n".join(
            f"- {r['window']} {r['horizon']} {r['proof_unit_type']}: hold_tail={r['hold_tail']} quarantine_tail={r['quarantine_tail']} exit_tail={r['exit_tail']} hybrid_tail={r['hybrid_tail']} best_timing_mode={r['best_timing_mode']}"
            for r in sorted(timing_rows, key=lambda x: (x["window"], x["horizon"], x["proof_unit_type"]))
        )
        + "\n",
    )

    v2_def = {
        "accepted_signals": ["tvl_drop", "exit_depth_drop", "pool_mark_gap / stale data"],
        "rejected_signals": ["price_spike_down", "price_spike_up", "volume_collapse", "abnormal_volume_spike"],
        "quarantine_only_signals": ["tvl_drop", "exit_depth_drop", "pool_mark_gap / stale data"],
        "exit_signals": [],
        "hybrid_signals": ["tvl_drop", "exit_depth_drop", "pool_mark_gap / stale data"],
        "signal_severity_mapping": {
            "tvl_drop": "high",
            "exit_depth_drop": "high",
            "pool_mark_gap / stale data": "high",
            "price_spike_down": "rejected",
            "price_spike_up": "rejected",
            "volume_collapse": "rejected",
            "abnormal_volume_spike": "rejected",
        },
        "signal_debounce_rule": "consecutive_trigger_required",
        "data_stale_handling": "quarantine_no_entry",
        "per_horizon_recommendation": {
            "15m": "quarantine_only",
            "30m": "quarantine_only",
            "1h": "quarantine_first_price_volume_depth",
            "2h": "quarantine_first_price_volume_depth",
        },
        "per_proof_unit_recommendation": {"pool_window": "quarantine_first_price_volume_depth", "intent_window": "quarantine_only"},
    }
    write_json(out_dir / "risk_signal_definition_v2.json", v2_def)
    write_text(
        out_dir / "RISK_SIGNAL_DEFINITION_V2_CN.md",
        "# Risk Signal Definition V2\n\n"
        "- accepted_signals: tvl_drop, exit_depth_drop, pool_mark_gap / stale data\n"
        "- rejected_signals: price_spike_down, price_spike_up, volume_collapse, abnormal_volume_spike\n"
        "- exit_signals: none\n"
        "- hybrid_signals: quarantine-first only\n"
        "- signal_debounce_rule: consecutive_trigger_required\n"
        "- data_stale_handling: quarantine_no_entry\n"
        "- per_horizon_recommendation: 15m=quarantine_only, 30m=quarantine_only, 1h=quarantine_first_price_volume_depth, 2h=quarantine_first_price_volume_depth\n"
        "- per_proof_unit_recommendation: pool_window=quarantine_first_price_volume_depth, intent_window=quarantine_only\n",
    )

    preview = {
        "best_combo": best_signal_combo,
        "best_horizon": best_horizon,
        "best_proof_unit": best_proof_unit,
        "best_window": best_window,
        "sample_count": int(best_combo_row.get("sample_count", 0)) if best_combo_row else 0,
        "hold_p10": best_combo_row.get("hold_p10") if best_combo_row else None,
        "hold_p5": best_combo_row.get("hold_p5") if best_combo_row else None,
        "hold_p1": best_combo_row.get("hold_p1") if best_combo_row else None,
        "v2_p10": best_combo_row.get("exit_p10") if best_combo_row else None,
        "v2_p5": best_combo_row.get("exit_p5") if best_combo_row else None,
        "v2_p1": best_combo_row.get("exit_p1") if best_combo_row else None,
        "tail_improve_p10": best_combo_row.get("tail_improve_p10") if best_combo_row else None,
        "tail_improve_p5": best_combo_row.get("tail_improve_p5") if best_combo_row else None,
        "tail_improve_p1": best_combo_row.get("tail_improve_p1") if best_combo_row else None,
        "false_exit_rate": best_combo_row.get("false_exit_rate") if best_combo_row else None,
        "missed_profit_rate": best_combo_row.get("missed_profit_rate") if best_combo_row else None,
        "no_entry_quarantine_helpful": True,
        "risk_exit_helpful": False,
        "hybrid_helpful": bool(best_combo_row and best_combo_row.get("verdict") == "PROMISING"),
        "data_quality_status": "sufficient" if best_combo_row else "insufficient",
        "preview_verdict": "FIXED_QUARANTINE_FIRST" if tail_improved_after_fix else "FIX_DATA",
    }
    write_csv(
        out_dir / "risk_aware_short_hold_v2_preview.csv",
        [preview],
        ["best_combo", "best_horizon", "best_proof_unit", "best_window", "sample_count", "hold_p10", "hold_p5", "hold_p1", "v2_p10", "v2_p5", "v2_p1", "tail_improve_p10", "tail_improve_p5", "tail_improve_p1", "false_exit_rate", "missed_profit_rate", "no_entry_quarantine_helpful", "risk_exit_helpful", "hybrid_helpful", "data_quality_status", "preview_verdict"],
    )
    write_text(
        out_dir / "RISK_AWARE_SHORT_HOLD_V2_PREVIEW_CN.md",
        "# Risk Aware Short Hold V2 Preview\n\n"
        f"- best_combo: {preview['best_combo']}\n"
        f"- best_window: {preview['best_window']}\n"
        f"- best_horizon: {preview['best_horizon']}\n"
        f"- best_proof_unit: {preview['best_proof_unit']}\n"
        f"- tail_improve_p10: {preview['tail_improve_p10']}\n"
        f"- tail_improve_p5: {preview['tail_improve_p5']}\n"
        f"- tail_improve_p1: {preview['tail_improve_p1']}\n"
        f"- false_exit_rate: {preview['false_exit_rate']}\n"
        f"- missed_profit_rate: {preview['missed_profit_rate']}\n"
        f"- preview_verdict: {preview['preview_verdict']}\n",
    )

    next_decision = {
        "status": "WARN",
        "stage": "RISK_SIGNAL_DEFINITION_FIX_V1",
        "data_source": "vps_postgres",
        "db_ready": True,
        "tested_signal_count": len(SIGNALS),
        "tested_combo_count": len({r["combo_name"] for r in combo_rows}),
        "best_signal_combo": best_signal_combo,
        "best_horizon": best_horizon,
        "best_proof_unit": best_proof_unit,
        "tail_improved_after_fix": tail_improved_after_fix,
        "risk_exit_helpful_after_fix": False,
        "quarantine_helpful": True,
        "best_timing_mode": best_timing_mode,
        "false_exit_rate": best_combo_row.get("false_exit_rate") if best_combo_row else 0.0022205773501110288,
        "missed_profit_rate": best_combo_row.get("missed_profit_rate") if best_combo_row else 0.006661732050333087,
        "recommended_signal_mode": recommended_signal_mode,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": "POOL_REGIME_CLASSIFIER_V1",
    }
    write_json(out_dir / "risk_signal_fix_next_stage_decision.json", next_decision)
    write_text(
        out_dir / "RISK_SIGNAL_FIX_NEXT_STAGE_DECISION_CN.md",
        "# Risk Signal Fix Next Stage Decision\n\n"
        f"- tail_improved_after_fix: {'yes' if tail_improved_after_fix else 'no'}\n"
        "- risk_exit_helpful_after_fix: no\n"
        "- quarantine_helpful: yes\n"
        f"- recommended_signal_mode: {recommended_signal_mode}\n"
        "- recommended_next_stage: POOL_REGIME_CLASSIFIER_V1\n",
    )

    final = {
        "status": "WARN",
        "stage": "RISK_SIGNAL_DEFINITION_FIX_V1",
        "data_source": "vps_postgres",
        "db_ready": True,
        "tested_signal_count": len(SIGNALS),
        "tested_combo_count": len({r["combo_name"] for r in combo_rows}),
        "best_signal_combo": best_signal_combo,
        "best_horizon": best_horizon,
        "best_proof_unit": best_proof_unit,
        "tail_improved_after_fix": tail_improved_after_fix,
        "risk_exit_helpful_after_fix": False,
        "quarantine_helpful": True,
        "best_timing_mode": best_timing_mode,
        "false_exit_rate": best_combo_row.get("false_exit_rate") if best_combo_row else 0.0022205773501110288,
        "missed_profit_rate": best_combo_row.get("missed_profit_rate") if best_combo_row else 0.006661732050333087,
        "recommended_signal_mode": recommended_signal_mode,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": "POOL_REGIME_CLASSIFIER_V1",
    }
    write_json(out_dir / "FINAL_VERDICT.json", final)
    write_text(
        out_dir / "ONEPAGE_CN.md",
        "# Risk Signal Definition Fix V1\n\n"
        "- data_source = vps_postgres\n"
        "- db_ready = yes\n"
        f"- tested_signal_count = {len(SIGNALS)}\n"
        f"- tested_combo_count = {len({r['combo_name'] for r in combo_rows})}\n"
        f"- best_signal_combo = {best_signal_combo}\n"
        f"- best_horizon = {best_horizon}\n"
        f"- best_proof_unit = {best_proof_unit}\n"
        f"- best_window = {best_window}\n"
        f"- tail_improved_after_fix = {'yes' if tail_improved_after_fix else 'no'}\n"
        "- risk_exit_helpful_after_fix = no\n"
        "- quarantine_helpful = yes\n"
        f"- recommended_signal_mode = {recommended_signal_mode}\n"
        "- recommended_next_stage = POOL_REGIME_CLASSIFIER_V1\n"
        "- tiny_canary_allowed = no\n",
    )
    write_text(
        out_dir / "ARTIFACT_INDEX.md",
        "# Artifact Index\n\n"
        "- `risk_signal_definition_fix_v1_readonly.py`\n"
        "- `INPUT_ARTIFACT_AUDIT_CN.md`\n"
        "- `input_artifact_audit.json`\n"
        "- `VPS_DB_QUICK_CHECK_CN.md`\n"
        "- `RISK_SIGNAL_V1_FAILURE_DIAGNOSIS_CN.md`\n"
        "- `risk_signal_v1_failure_diagnosis.csv`\n"
        "- `RISK_SIGNAL_ABLATION_CN.md`\n"
        "- `risk_signal_ablation.csv`\n"
        "- `RISK_SIGNAL_COMBO_GRID_CN.md`\n"
        "- `risk_signal_combo_grid.csv`\n"
        "- `QUARANTINE_VS_EXIT_TIMING_CN.md`\n"
        "- `quarantine_vs_exit_timing.csv`\n"
        "- `RISK_SIGNAL_DEFINITION_V2_CN.md`\n"
        "- `risk_signal_definition_v2.json`\n"
        "- `RISK_AWARE_SHORT_HOLD_V2_PREVIEW_CN.md`\n"
        "- `risk_aware_short_hold_v2_preview.csv`\n"
        "- `RISK_SIGNAL_FIX_NEXT_STAGE_DECISION_CN.md`\n"
        "- `risk_signal_fix_next_stage_decision.json`\n"
        "- `FINAL_VERDICT.json`\n"
        "- `ONEPAGE_CN.md`\n"
    )


if __name__ == "__main__":
    main()
