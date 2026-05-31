#!/usr/bin/env python3
import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

HORIZONS = [6, 12, 24]
WINDOWS = [2, 4, 8, 12, 24, 48]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: Any) -> Optional[datetime]:
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


def q(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


def write_csv(path: Path, rows, fieldnames):
    if not rows:
        rows = []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def load_latest_rows(cur):
    run_row = q(
        cur,
        """
        select run_id, created_at
        from shadow_position_lifecycle_proof_v2
        where strategy_hypothesis = 'fixed_horizon'
        order by created_at desc, run_id desc
        limit 1
        """,
    )
    if not run_row:
        raise RuntimeError("no fixed_horizon rows in shadow_position_lifecycle_proof_v2")

    run_id = run_row[0]["run_id"]
    rows = q(
        cur,
        """
        select position_id::text as position_id,
               coalesce(pool_id::text, '') as pool_id,
               coalesce(token_pair::text, '') as token_pair,
               horizon,
               entry_time,
               target_time,
               outcome_time,
               entry_value_usd,
               target_value_usd,
               fee_estimate_usd,
               price_loss_or_il_usd,
               net_pnl_usd,
               net_pnl_pct,
               score_open_decision,
               score_first_selected,
               score_max_before_open,
               score_median_before_open,
               top20_by_score_open,
               top20_by_score_max,
               entry_trusted,
               future_position_mark_exists,
               mark_distance_seconds,
               data_quality_status,
               invalid_reason
        from shadow_position_lifecycle_proof_v2
        where strategy_hypothesis = 'fixed_horizon'
          and run_id = %s
          and horizon in ('6h', '12h', '24h')
        order by position_id, horizon
        """,
        (run_id,),
    )
    out = []
    for r in rows:
        entry = parse_ts(r["entry_time"])
        out.append(
            {
                "position_id": r["position_id"],
                "pool_id": r["pool_id"],
                "token_pair": r["token_pair"],
                "horizon": r["horizon"],
                "entry_time": entry,
                "target_time": parse_ts(r["target_time"]),
                "outcome_time": parse_ts(r["outcome_time"]),
                "entry_value_usd": float(r["entry_value_usd"]) if r.get("entry_value_usd") is not None else None,
                "target_value_usd": float(r["target_value_usd"]) if r.get("target_value_usd") is not None else None,
                "fee_estimate_usd": float(r["fee_estimate_usd"]) if r.get("fee_estimate_usd") is not None else None,
                "price_loss_or_il_usd": float(r["price_loss_or_il_usd"]) if r.get("price_loss_or_il_usd") is not None else None,
                "net_pnl_usd": float(r["net_pnl_usd"]) if r.get("net_pnl_usd") is not None else None,
                "net_pnl_pct": float(r["net_pnl_pct"]) if r.get("net_pnl_pct") is not None else None,
                "score_open_decision": float(r["score_open_decision"]) if r.get("score_open_decision") is not None else None,
                "score_first_selected": float(r["score_first_selected"]) if r.get("score_first_selected") is not None else None,
                "score_max_before_open": float(r["score_max_before_open"]) if r.get("score_max_before_open") is not None else None,
                "score_median_before_open": float(r["score_median_before_open"]) if r.get("score_median_before_open") is not None else None,
                "top20_by_score_open": bool(r["top20_by_score_open"]),
                "top20_by_score_max": bool(r["top20_by_score_max"]),
                "entry_trusted": bool(r["entry_trusted"]),
                "future_position_mark_exists": bool(r["future_position_mark_exists"]),
                "mark_distance_seconds": int(r["mark_distance_seconds"]) if r.get("mark_distance_seconds") is not None else None,
                "data_quality_status": r["data_quality_status"] or "ok",
                "invalid_reason": r["invalid_reason"] or "",
                "run_id": run_id,
            }
        )
    return run_id, out


def summarize_horizons(rows):
    out = []
    for h in [f"{x}h" for x in HORIZONS]:
        horizon_rows = [r for r in rows if r["horizon"] == h]
        if not horizon_rows:
            out.append(
                {
                    "horizon": h,
                    "completed_count": 0,
                    "position_count": 0,
                    "invalid_count": 0,
                    "future_position_mark_coverage": None,
                    "p10_net_pnl_pct": None,
                    "p5_net_pnl_pct": None,
                    "p1_net_pnl_pct": None,
                    "top20_vs_bottom20_signal": "insufficient",
                    "worst_position_contribution": None,
                    "worst_pool_contribution": None,
                    "sample_sufficiency": "INSUFFICIENT",
                    "top20_position_count": 0,
                    "bottom20_position_count": 0,
                    "top20_median_net_pnl_pct": None,
                    "bottom20_median_net_pnl_pct": None,
                    "top20_p10_net_pnl_pct": None,
                    "bottom20_p10_net_pnl_pct": None,
                    "win_rate": None,
                }
            )
            continue

        valid = [r for r in horizon_rows if not r["invalid_reason"] and r["net_pnl_pct"] is not None]
        invalid = [r for r in horizon_rows if r["invalid_reason"]]
        valid_sorted = sorted(valid, key=lambda r: (r["score_open_decision"] is None, -(r["score_open_decision"] or 0.0)))
        n = len(valid_sorted)
        topn = max(1, int(n * 0.2)) if n else 0
        top = valid_sorted[:topn]
        bottom = valid_sorted[-topn:] if topn else []
        vals = [r["net_pnl_pct"] for r in valid]
        top_vals = [r["net_pnl_pct"] for r in top]
        bottom_vals = [r["net_pnl_pct"] for r in bottom]

        signal = "insufficient"
        if top_vals and bottom_vals:
            top_med = percentile(top_vals, 0.5)
            bot_med = percentile(bottom_vals, 0.5)
            if top_med > bot_med:
                signal = "better"
            elif top_med < bot_med:
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
            if pool_losses:
                worst_pool_contribution = max(pool_losses.values()) / total_loss

        sample_suff = "INSUFFICIENT"
        if len(valid) >= 300:
            sample_suff = "USABLE"
        elif len(valid) >= 100:
            sample_suff = "PRELIMINARY"
        elif len(valid) >= 30:
            sample_suff = "EARLY"

        future_ratio = (sum(1 for r in horizon_rows if r["future_position_mark_exists"]) / len(horizon_rows)) if horizon_rows else None
        out.append(
            {
                "horizon": h,
                "completed_count": len(valid),
                "position_count": len(horizon_rows),
                "invalid_count": len(invalid),
                "future_position_mark_coverage": future_ratio,
                "p10_net_pnl_pct": percentile(vals, 0.1),
                "p5_net_pnl_pct": percentile(vals, 0.05),
                "p1_net_pnl_pct": percentile(vals, 0.01),
                "top20_vs_bottom20_signal": signal,
                "worst_position_contribution": worst_position_contribution,
                "worst_pool_contribution": worst_pool_contribution,
                "sample_sufficiency": sample_suff,
                "top20_position_count": len(top),
                "bottom20_position_count": len(bottom),
                "top20_median_net_pnl_pct": percentile(top_vals, 0.5),
                "bottom20_median_net_pnl_pct": percentile(bottom_vals, 0.5),
                "top20_p10_net_pnl_pct": percentile(top_vals, 0.1),
                "bottom20_p10_net_pnl_pct": percentile(bottom_vals, 0.1),
                "win_rate": (sum(1 for v in vals if v > 0) / len(vals)) if vals else None,
            }
        )
    return out


def summarize_windows(rows, now):
    by_position = defaultdict(lambda: {"entry_trusted": False, "future_mark": False, "completed_6h": False, "completed_12h": False, "completed_24h": False})
    for h in [2, 4, 8, 12, 24, 48]:
        cutoff = now - timedelta(hours=h)
        window_rows = [r for r in rows if r["entry_time"] and r["entry_time"] >= cutoff]
        by_pos = {}
        for r in window_rows:
            p = by_pos.setdefault(
                r["position_id"],
                {"entry_trusted": False, "future_mark": False, "completed_6h": False, "completed_12h": False, "completed_24h": False},
            )
            p["entry_trusted"] = p["entry_trusted"] or bool(r["entry_trusted"])
            p["future_mark"] = p["future_mark"] or bool(r["future_position_mark_exists"])
            if r["horizon"] == "6h" and not r["invalid_reason"]:
                p["completed_6h"] = True
            if r["horizon"] == "12h" and not r["invalid_reason"]:
                p["completed_12h"] = True
            if r["horizon"] == "24h" and not r["invalid_reason"]:
                p["completed_24h"] = True
        count = len(by_pos)
        suff = "INSUFFICIENT"
        if count >= 300:
            suff = "USABLE"
        elif count >= 100:
            suff = "PRELIMINARY"
        elif count >= 30:
            suff = "EARLY"
        by_window = {
            "window": f"recent_{h}h",
            "new_position_count": count,
            "completed_6h_count": sum(1 for v in by_pos.values() if v["completed_6h"]),
            "completed_12h_count": sum(1 for v in by_pos.values() if v["completed_12h"]),
            "completed_24h_count": sum(1 for v in by_pos.values() if v["completed_24h"]),
            "entry_trusted_rate": (sum(1 for v in by_pos.values() if v["entry_trusted"]) / count) if count else None,
            "future_position_mark_coverage": (sum(1 for v in by_pos.values() if v["future_mark"]) / count) if count else None,
            "sample_sufficiency": suff,
            "sample_note": "SAMPLE_INSUFFICIENT" if suff == "INSUFFICIENT" else "",
        }
        by_position[h] = by_window
    return [by_position[h] for h in (2, 4, 8, 12, 24, 48)]


def parse_checkpoint_json(path):
    if not Path(path).exists():
        return None
    with open(path, "r") as fh:
        return json.load(fh)


def add_deltas(current_rows, previous_summary):
    if not previous_summary:
        return current_rows
    prev_rows = {r["horizon"]: r for r in previous_summary.get("rows", [])}
    for row in current_rows:
        prev = prev_rows.get(row["horizon"], {})
        row.update(
            {
                "completed_count_delta_from_previous": row["completed_count"] - prev.get("completed_count", 0),
                "position_count_delta_from_previous": row["position_count"] - prev.get("position_count", 0),
                "invalid_count_delta_from_previous": row["invalid_count"] - prev.get("invalid_count", 0),
            }
        )
        if row.get("future_position_mark_coverage") is not None and prev.get("future_position_mark_coverage") is not None:
            row["future_mark_coverage_delta"] = row["future_position_mark_coverage"] - prev["future_position_mark_coverage"]
        else:
            row["future_mark_coverage_delta"] = None
    return current_rows


def write_checkpoint(out_dir: Path, checkpoint: str, run_id: str, rows, window_rows, previous):
    now = utc_now().isoformat()
    current = {
        "checkpoint": checkpoint,
        "timestamp": now,
        "proof_run_id": run_id,
        "new_positions_last_6h": window_rows[0]["new_position_count"],
        "new_positions_last_12h": next((r for r in window_rows if r["window"] == "recent_12h"), {}).get("new_position_count", 0),
        "new_positions_last_24h": next((r for r in window_rows if r["window"] == "recent_24h"), {}).get("new_position_count", 0),
        "new_positions_last_48h": next((r for r in window_rows if r["window"] == "recent_48h"), {}).get("new_position_count", 0),
        "rows": rows,
        "windows": window_rows,
    }

    if previous and previous.get("sample_sufficiency"):
        current["previous_checkpoint"] = previous.get("checkpoint")
        current["previous_timestamp"] = previous.get("timestamp")
    if previous and previous.get("rows"):
        for row in current["rows"]:
            prev_map = {r["horizon"]: r for r in previous.get("rows", [])}
            pr = prev_map.get(row["horizon"], {})
            row["completed_count_delta"] = row["completed_count"] - pr.get("completed_count", 0)
            row["position_count_delta"] = row["position_count"] - pr.get("position_count", 0)
            row["invalid_count_delta"] = row["invalid_count"] - pr.get("invalid_count", 0)
            if row.get("future_position_mark_coverage") is not None and pr.get("future_position_mark_coverage") is not None:
                row["future_position_mark_coverage_delta"] = row["future_position_mark_coverage"] - pr["future_position_mark_coverage"]
            else:
                row["future_position_mark_coverage_delta"] = None
    current["sample_sufficiency"] = max((r["sample_sufficiency"] for r in rows), key=lambda x: {"INSUFFICIENT": 0, "EARLY": 1, "PRELIMINARY": 2, "USABLE": 3}[x]) if rows else "INSUFFICIENT"

    out_dir = out_dir / checkpoint
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "fixed_horizon_snapshot.csv", rows, list(rows[0].keys()) if rows else [
        "horizon",
        "completed_count",
        "position_count",
        "invalid_count",
        "future_position_mark_coverage",
        "p10_net_pnl_pct",
        "p5_net_pnl_pct",
        "p1_net_pnl_pct",
        "top20_vs_bottom20_signal",
        "worst_position_contribution",
        "worst_pool_contribution",
        "sample_sufficiency",
        "top20_position_count",
        "bottom20_position_count",
        "top20_median_net_pnl_pct",
        "bottom20_median_net_pnl_pct",
        "top20_p10_net_pnl_pct",
        "bottom20_p10_net_pnl_pct",
        "win_rate",
    ])
    (out_dir / "fixed_horizon_snapshot.json").write_text(json.dumps(current, indent=2, default=str))

    md = [
        "# Fixed Horizon Snapshot",
        "",
        f"- checkpoint: `{checkpoint}`",
        f"- timestamp: `{now}`",
        f"- proof_run_id: `{run_id}`",
        f"- new_positions_last_6h: {current['new_positions_last_6h']}",
        f"- new_positions_last_12h: {current['new_positions_last_12h']}",
        f"- new_positions_last_24h: {current['new_positions_last_24h']}",
        f"- new_positions_last_48h: {current['new_positions_last_48h']}",
    ]
    for row in rows:
        md.append(
            "- `{h}` completed={c} position_count={pc} invalid={iv} future_mark_coverage={fm:.6g} p10={p10} p5={p5} p1={p1} signal={sig} sample={s} top20_vs_bottom20_top={tp} bottom={bp}".format(
                h=row["horizon"],
                c=row["completed_count"],
                pc=row["position_count"],
                iv=row["invalid_count"],
                fm=row["future_position_mark_coverage"] if row["future_position_mark_coverage"] is not None else 0,
                p10=row["p10_net_pnl_pct"],
                p5=row["p5_net_pnl_pct"],
                p1=row["p1_net_pnl_pct"],
                sig=row["top20_vs_bottom20_signal"],
                s=row["sample_sufficiency"],
                tp=row["top20_position_count"],
                bp=row["bottom20_position_count"],
            )
        )
    (out_dir / "FIXED_HORIZON_SNAPSHOT_CN.md").write_text("\n".join(md) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True, choices=["checkpoint_0h", "checkpoint_12h", "checkpoint_24h"])
    ap.add_argument("--report-dir", required=True)
    ap.add_argument("--previous-json", required=False, default="")
    args = ap.parse_args()

    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("missing dsn")

    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            proof_run_id, rows = load_latest_rows(cur)
    finally:
        conn.close()

    now = utc_now()
    row_summary = summarize_horizons(rows)
    previous_summary = parse_checkpoint_json(args.previous_json) if args.previous_json else None
    if previous_summary:
        row_summary = add_deltas(row_summary, previous_summary)
    windows = summarize_windows(rows, now)

    report_dir = Path(args.report_dir)
    write_checkpoint(report_dir, args.checkpoint, proof_run_id, row_summary, windows, previous_summary)


if __name__ == "__main__":
    main()
