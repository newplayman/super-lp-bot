#!/usr/bin/env python3
import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


HORIZONS = [6, 12, 24]


def utc_now():
    return datetime.now(timezone.utc)


def parse_ts(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            value = value / 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            if value.isdigit():
                return parse_ts(int(value))
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    idx = max(0, min(len(values) - 1, int((len(values) - 1) * p)))
    return values[idx]


def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return (a - b) / b * 100.0


def q(cur, sql_text, params=None):
    cur.execute(sql_text, params or ())
    return cur.fetchall()


def write_csv(path: Path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def load_positions(cur):
    rows = q(
        cur,
        """
        select id::text as position_id,
               coalesce(pool_id::text, '') as pool_id,
               opened_at,
               closed_at,
               amount_usd
        from positions
        """
    )
    token_pairs = {}
    try:
        seed_rows = q(cur, "select distinct position_id::text as position_id, token_pair from shadow_position_lifecycle_proof_v1")
        token_pairs = {r["position_id"]: r.get("token_pair") or "" for r in seed_rows}
    except Exception:
        token_pairs = {}
    out = {}
    for r in rows:
        position_id = r["position_id"]
        out[position_id] = {
            "position_id": position_id,
            "pool_id": r["pool_id"],
            "entry_time": parse_ts(r["opened_at"]),
            "closed_at": parse_ts(r["closed_at"]),
            "entry_value_usd": float(r["amount_usd"] or 0.0),
            "token_pair": token_pairs.get(position_id) or r["pool_id"],
        }
    return out


def load_marks(cur):
    rows = q(
        cur,
        """
        select position_id::text as position_id,
               mark_time,
               valuation_usd,
               fee_usd,
               il_usd,
               net_pnl_usd,
               source
        from shadow_position_marks
        order by position_id, mark_time
        """
    )
    by_position = defaultdict(list)
    for r in rows:
        by_position[r["position_id"]].append(
            {
                "mark_time": parse_ts(r["mark_time"]),
                "value_usd": float(r["valuation_usd"]) if r.get("valuation_usd") is not None else None,
                "fee_usd": float(r["fee_usd"]) if r.get("fee_usd") is not None else None,
                "il_usd": float(r["il_usd"]) if r.get("il_usd") is not None else None,
                "net_pnl_usd": float(r["net_pnl_usd"]) if r.get("net_pnl_usd") is not None else None,
                "source": r.get("source") or "",
            }
        )
    return by_position


def load_scores(cur):
    rows = q(
        cur,
        """
        select coalesce(position_id::text, '') as position_id,
               tick_time,
               score_total,
               selected,
               intent_open
        from shadow_decision_trace
        where coalesce(position_id::text, '') <> ''
        order by position_id, tick_time
        """
    )
    by_position = defaultdict(list)
    for r in rows:
        by_position[r["position_id"]].append(
            {
                "decision_time": parse_ts(r["tick_time"]),
                "score_total": float(r["score_total"] or 0.0),
                "selected": bool(r["selected"]),
                "intent_open": bool(r["intent_open"]),
            }
        )
    return by_position


def nearest_future_mark(marks, target_time):
    best = None
    for m in marks:
        mt = m["mark_time"]
        if mt is None or mt < target_time:
            continue
        dist = int((mt - target_time).total_seconds())
        if best is None or dist < best["dist"]:
            best = {"mark": m, "dist": dist}
    return best


def score_summary(score_rows, entry_time):
    before = [r for r in score_rows if r["decision_time"] and r["decision_time"] <= entry_time]
    if not before:
        return {
            "score_open_decision": None,
            "score_first_selected": None,
            "score_max_before_open": None,
            "score_median_before_open": None,
        }
    vals = [r["score_total"] for r in before]
    vals_sorted = sorted(vals)
    mid = len(vals_sorted) // 2
    median = vals_sorted[mid] if len(vals_sorted) % 2 == 1 else (vals_sorted[mid - 1] + vals_sorted[mid]) / 2.0
    selected_rows = [r for r in before if r["selected"] and r["intent_open"]]
    return {
        "score_open_decision": before[-1]["score_total"],
        "score_first_selected": selected_rows[0]["score_total"] if selected_rows else None,
        "score_max_before_open": max(vals) if vals else None,
        "score_median_before_open": median if vals else None,
    }


def build_snapshot(cur):
    positions = load_positions(cur)
    marks_by_position = load_marks(cur)
    scores_by_position = load_scores(cur)
    rows = []
    for position_id, p in positions.items():
        if not p["entry_time"] or not p["entry_value_usd"]:
            continue
        score_meta = score_summary(scores_by_position.get(position_id, []), p["entry_time"])
        for horizon_h in HORIZONS:
            target_time = p["entry_time"] + timedelta(hours=horizon_h)
            nearest = nearest_future_mark(marks_by_position.get(position_id, []), target_time)
            invalid_reason = ""
            quality = "ok"
            target_value = None
            outcome_time = None
            future_exists = False
            mark_distance = None
            if nearest is None:
                invalid_reason = "no_future_mark"
                quality = "invalid"
            else:
                future_exists = True
                target_value = nearest["mark"]["value_usd"]
                outcome_time = nearest["mark"]["mark_time"]
                mark_distance = nearest["dist"]
                if target_value is None:
                    invalid_reason = "target_value_missing"
                    quality = "invalid"
            if not invalid_reason and p["closed_at"] and p["closed_at"] < target_time:
                invalid_reason = "terminal_before_target"
                quality = "terminal_before_target"
            elif not invalid_reason and mark_distance is not None and mark_distance > 3600:
                quality = "stale_mark"
            fee_estimate = nearest["mark"]["fee_usd"] if nearest else None
            price_loss = nearest["mark"]["il_usd"] if nearest else None
            net_pnl_usd = nearest["mark"]["net_pnl_usd"] if nearest else None
            if net_pnl_usd is None and target_value is not None:
                net_pnl_usd = target_value - p["entry_value_usd"]
            rows.append(
                {
                    "position_id": position_id,
                    "pool_id": p["pool_id"],
                    "token_pair": p["token_pair"],
                    "horizon": f"{horizon_h}h",
                    "entry_time": p["entry_time"],
                    "target_time": target_time,
                    "outcome_time": outcome_time,
                    "entry_value_usd": p["entry_value_usd"],
                    "target_value_usd": target_value,
                    "fee_estimate_usd": fee_estimate,
                    "price_loss_or_il_usd": price_loss,
                    "net_pnl_usd": net_pnl_usd,
                    "net_pnl_pct": pct(target_value, p["entry_value_usd"]) if target_value is not None else None,
                    "score_open_decision": score_meta["score_open_decision"],
                    "score_first_selected": score_meta["score_first_selected"],
                    "score_max_before_open": score_meta["score_max_before_open"],
                    "score_median_before_open": score_meta["score_median_before_open"],
                    "entry_trusted": True,
                    "future_position_mark_exists": future_exists,
                    "mark_distance_seconds": mark_distance,
                    "data_quality_status": quality,
                    "invalid_reason": invalid_reason,
                }
            )
    return rows


def summarize_by_horizon(rows):
    out = []
    for horizon in [f"{h}h" for h in HORIZONS]:
        horizon_rows = [r for r in rows if r["horizon"] == horizon]
        valid = [r for r in horizon_rows if not r["invalid_reason"] and r["net_pnl_pct"] is not None]
        invalid = [r for r in horizon_rows if r["invalid_reason"]]
        ordered = sorted(valid, key=lambda r: (r["score_open_decision"] is None, -(r["score_open_decision"] or -10**9)))
        n = len(ordered)
        topn = max(1, int(n * 0.2)) if n else 0
        top = ordered[:topn]
        bottom = ordered[-topn:] if topn else []
        vals = [r["net_pnl_pct"] for r in valid]
        top_vals = [r["net_pnl_pct"] for r in top]
        bottom_vals = [r["net_pnl_pct"] for r in bottom]
        signal = "insufficient"
        if top_vals and bottom_vals:
            top_med = percentile(top_vals, 0.5)
            bottom_med = percentile(bottom_vals, 0.5)
            if top_med > bottom_med:
                signal = "better"
            elif top_med < bottom_med:
                signal = "worse"
            else:
                signal = "flat"
        worst_position_contribution = None
        worst_pool_contribution = None
        losses = [abs(min(r["net_pnl_usd"] or 0.0, 0.0)) for r in valid]
        total_loss = sum(losses)
        if total_loss > 0:
            worst_position_contribution = max(losses) / total_loss
            pool_losses = defaultdict(float)
            for r in valid:
                pool_losses[r["pool_id"]] += abs(min(r["net_pnl_usd"] or 0.0, 0.0))
            worst_pool_contribution = max(pool_losses.values()) / total_loss if pool_losses else None
        completed = len(valid)
        sample_sufficiency = "INSUFFICIENT"
        if completed >= 300:
            sample_sufficiency = "USABLE"
        elif completed >= 100:
            sample_sufficiency = "PRELIMINARY"
        elif completed >= 30:
            sample_sufficiency = "EARLY"
        out.append(
            {
                "horizon": horizon,
                "completed_count": completed,
                "position_count": len(horizon_rows),
                "invalid_count": len(invalid),
                "future_position_mark_coverage": (sum(1 for r in horizon_rows if r["future_position_mark_exists"]) / len(horizon_rows)) if horizon_rows else None,
                "p10_net_pnl_pct": percentile(vals, 0.1),
                "p5_net_pnl_pct": percentile(vals, 0.05),
                "p1_net_pnl_pct": percentile(vals, 0.01),
                "top20_vs_bottom20_signal": signal,
                "worst_position_contribution": worst_position_contribution,
                "worst_pool_contribution": worst_pool_contribution,
                "sample_sufficiency": sample_sufficiency,
            }
        )
    return out


def summarize_windows(rows):
    now = utc_now()
    out = {}
    for hours in [6, 12, 24]:
        cutoff = now - timedelta(hours=hours)
        position_ids = {r["position_id"] for r in rows if r["entry_time"] and r["entry_time"] >= cutoff}
        out[f"new_positions_last_{hours}h"] = len(position_ids)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("missing dsn")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows = build_snapshot(cur)
    finally:
        conn.close()

    by_horizon = summarize_by_horizon(rows)
    windows = summarize_windows(rows)
    now = utc_now().isoformat()
    top = {
        "checkpoint": args.checkpoint,
        "timestamp": now,
        **windows,
        "sample_sufficiency": max((r["sample_sufficiency"] for r in by_horizon), key=lambda x: {"INSUFFICIENT": 0, "EARLY": 1, "PRELIMINARY": 2, "USABLE": 3}[x]),
        "rows": by_horizon,
    }

    write_csv(out_dir / "fixed_horizon_snapshot.csv", by_horizon, list(by_horizon[0].keys()) if by_horizon else [
        "horizon","completed_count","position_count","invalid_count","future_position_mark_coverage","p10_net_pnl_pct","p5_net_pnl_pct","p1_net_pnl_pct","top20_vs_bottom20_signal","worst_position_contribution","worst_pool_contribution","sample_sufficiency"
    ])
    (out_dir / "fixed_horizon_snapshot.json").write_text(json.dumps(top, indent=2))
    md = [
        "# Fixed Horizon Snapshot",
        "",
        f"- checkpoint: `{args.checkpoint}`",
        f"- timestamp: `{now}`",
        f"- new_positions_last_6h = {windows['new_positions_last_6h']}",
        f"- new_positions_last_12h = {windows['new_positions_last_12h']}",
        f"- new_positions_last_24h = {windows['new_positions_last_24h']}",
        "",
    ]
    for row in by_horizon:
        md.append(
            f"- `{row['horizon']}` completed={row['completed_count']} position_count={row['position_count']} invalid={row['invalid_count']} future_position_mark_coverage={row['future_position_mark_coverage']} p10={row['p10_net_pnl_pct']} p5={row['p5_net_pnl_pct']} p1={row['p1_net_pnl_pct']} signal={row['top20_vs_bottom20_signal']} sample_sufficiency={row['sample_sufficiency']}"
        )
    (out_dir / "FIXED_HORIZON_SNAPSHOT_CN.md").write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
