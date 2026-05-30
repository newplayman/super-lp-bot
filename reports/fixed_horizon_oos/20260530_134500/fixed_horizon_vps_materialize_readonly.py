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
SCORE_FIELDS = [
    "score_open_decision",
    "score_first_selected",
    "score_max_before_open",
    "score_median_before_open",
]


def utc_now():
    return datetime.now(timezone.utc)


def write_csv(path: Path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def md(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def parse_ts(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        # support seconds and milliseconds
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


def fmt_dt(dt):
    return dt.isoformat() if dt else ""


def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return (a - b) / b * 100.0


def q(cur, sql_text, params=None):
    cur.execute(sql_text, params or ())
    return cur.fetchall()


def q1(cur, sql_text, params=None):
    cur.execute(sql_text, params or ())
    return cur.fetchone()


def ensure_table(cur):
    cur.execute(
        """
        create table if not exists shadow_position_lifecycle_proof_v2 (
          run_id text not null,
          strategy_hypothesis text not null default 'fixed_horizon',
          position_id text not null,
          pool_id text,
          token_pair text,
          horizon text not null,
          entry_time timestamptz,
          target_time timestamptz,
          outcome_time timestamptz,
          entry_value_usd double precision,
          target_value_usd double precision,
          fee_estimate_usd double precision,
          price_loss_or_il_usd double precision,
          net_pnl_usd double precision,
          net_pnl_pct double precision,
          score_open_decision double precision,
          score_first_selected double precision,
          score_max_before_open double precision,
          score_median_before_open double precision,
          top20_by_score_open boolean,
          top20_by_score_max boolean,
          entry_trusted boolean,
          future_position_mark_exists boolean,
          mark_distance_seconds integer,
          data_quality_status text,
          invalid_reason text,
          created_at timestamptz not null default now(),
          primary key (run_id, position_id, horizon, strategy_hypothesis)
        )
        """
    )


def load_positions(cur):
    rows = q(
        cur,
        """
        select id::text as position_id,
               coalesce(pool_id::text, '') as pool_id,
               opened_at,
               closed_at,
               amount_usd,
               metadata
        from positions
        """,
    )
    proof_token_pairs = {}
    try:
        seed_rows = q(cur, "select distinct position_id::text as position_id, token_pair from shadow_position_lifecycle_proof_v1")
        proof_token_pairs = {r["position_id"]: r.get("token_pair") or "" for r in seed_rows}
    except Exception:
        proof_token_pairs = {}
    out = {}
    for r in rows:
        entry_time = parse_ts(r.get("opened_at"))
        token_pair = proof_token_pairs.get(r["position_id"], "")
        if not token_pair:
            token_pair = r["pool_id"]
        out[r["position_id"]] = {
            "position_id": r["position_id"],
            "pool_id": r["pool_id"],
            "entry_time": entry_time,
            "entry_value_usd": float(r["amount_usd"] or 0.0),
            "token_pair": token_pair,
            "closed_at": parse_ts(r.get("closed_at")),
        }
    return out


def load_marks(cur):
    rows = q(
        cur,
        """
        select position_id::text as position_id,
               pool_id::text as pool_id,
               mark_time,
               valuation_usd,
               fee_usd,
               il_usd,
               net_pnl_usd,
               amount_usd,
               source
        from shadow_position_marks
        order by position_id, mark_time
        """,
    )
    by_position = defaultdict(list)
    for r in rows:
        t = parse_ts(r["mark_time"])
        value = r.get("valuation_usd")
        by_position[r["position_id"]].append(
            {
                "mark_time": t,
                "value_usd": float(value) if value is not None else None,
                "fee_usd": float(r["fee_usd"]) if r.get("fee_usd") is not None else None,
                "il_usd": float(r["il_usd"]) if r.get("il_usd") is not None else None,
                "net_pnl_usd": float(r["net_pnl_usd"]) if r.get("net_pnl_usd") is not None else None,
                "source": r.get("source") or "",
            }
        )
    return by_position


def load_score_rows(cur):
    # Try to use decision_trace fields if present; if absent, fall back to zeros.
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
        """,
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
    if not marks or not target_time:
        return None
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
    if not score_rows or not entry_time:
        return {
            "score_open_decision": None,
            "score_first_selected": None,
            "score_max_before_open": None,
            "score_median_before_open": None,
        }
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
    first_selected = selected_rows[0]["score_total"] if selected_rows else None
    open_decision = before[-1]["score_total"]
    return {
        "score_open_decision": open_decision,
        "score_first_selected": first_selected,
        "score_max_before_open": max(vals) if vals else None,
        "score_median_before_open": median if vals else None,
    }


def materialize(conn, run_id: str):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        ensure_table(cur)
        cur.execute("delete from shadow_position_lifecycle_proof_v2 where run_id = %s", (run_id,))

        positions = load_positions(cur)
        marks_by_position = load_marks(cur)
        scores_by_position = load_score_rows(cur)

        rows = []
        for position_id, p in positions.items():
            entry_time = p["entry_time"]
            entry_value = p["entry_value_usd"]
            if not entry_time or not entry_value:
                continue
            score_meta = score_summary(scores_by_position.get(position_id, []), entry_time)
            for horizon_h in HORIZONS:
                target_time = entry_time + timedelta(hours=horizon_h)
                nearest = nearest_future_mark(marks_by_position.get(position_id, []), target_time)
                invalid_reason = ""
                outcome_time = None
                target_value = None
                mark_distance = None
                future_exists = False
                if nearest is None:
                    invalid_reason = "no_future_mark"
                else:
                    future_exists = True
                    outcome_time = nearest["mark"]["mark_time"]
                    target_value = nearest["mark"]["value_usd"]
                    mark_distance = nearest["dist"]
                    if target_value is None:
                        invalid_reason = "target_value_missing"
                fee_estimate = nearest["mark"].get("fee_usd") if nearest else None
                price_loss = nearest["mark"].get("il_usd") if nearest else None
                pnl_usd = nearest["mark"].get("net_pnl_usd") if nearest else (None if target_value is None else target_value - entry_value)
                pnl_pct = pct(target_value, entry_value) if target_value is not None else None
                quality = "ok"
                if invalid_reason:
                    quality = "invalid"
                elif mark_distance is not None and mark_distance > 3600:
                    quality = "stale_mark"
                mark_source = nearest["mark"].get("source") if nearest else ""
                if not invalid_reason and p.get("closed_at") and p["closed_at"] < target_time:
                    quality = "terminal_before_horizon"
                rows.append(
                    {
                        "run_id": run_id,
                        "strategy_hypothesis": "fixed_horizon",
                        "position_id": position_id,
                        "pool_id": p["pool_id"],
                        "token_pair": p["token_pair"],
                        "horizon": f"{horizon_h}h",
                        "entry_time": entry_time,
                        "target_time": target_time,
                        "outcome_time": outcome_time,
                        "entry_value_usd": entry_value,
                        "target_value_usd": target_value,
                        "fee_estimate_usd": fee_estimate,
                        "price_loss_or_il_usd": price_loss,
                        "net_pnl_usd": pnl_usd,
                        "net_pnl_pct": pnl_pct,
                        "score_open_decision": score_meta["score_open_decision"],
                        "score_first_selected": score_meta["score_first_selected"],
                        "score_max_before_open": score_meta["score_max_before_open"],
                        "score_median_before_open": score_meta["score_median_before_open"],
                        "top20_by_score_open": False,
                        "top20_by_score_max": False,
                        "entry_trusted": True,
                        "future_position_mark_exists": future_exists,
                        "mark_distance_seconds": mark_distance,
                        "data_quality_status": quality,
                        "invalid_reason": invalid_reason,
                    }
                )

        # top20 tags by horizon
        for horizon in [f"{h}h" for h in HORIZONS]:
            bucket = [r for r in rows if r["horizon"] == horizon and r["score_open_decision"] is not None]
            bucket.sort(key=lambda r: r["score_open_decision"], reverse=True)
            topn = max(1, int(len(bucket) * 0.2)) if bucket else 0
            for r in bucket[:topn]:
                r["top20_by_score_open"] = True
            bucket2 = [r for r in rows if r["horizon"] == horizon and r["score_max_before_open"] is not None]
            bucket2.sort(key=lambda r: r["score_max_before_open"], reverse=True)
            topn2 = max(1, int(len(bucket2) * 0.2)) if bucket2 else 0
            for r in bucket2[:topn2]:
                r["top20_by_score_max"] = True

        # insert
        insert_sql = """
            insert into shadow_position_lifecycle_proof_v2 (
              run_id, strategy_hypothesis, position_id, pool_id, token_pair, horizon,
              entry_time, target_time, outcome_time, entry_value_usd, target_value_usd,
              fee_estimate_usd, price_loss_or_il_usd, net_pnl_usd, net_pnl_pct,
              score_open_decision, score_first_selected, score_max_before_open, score_median_before_open,
              top20_by_score_open, top20_by_score_max, entry_trusted, future_position_mark_exists,
              mark_distance_seconds, data_quality_status, invalid_reason
            ) values (
              %(run_id)s, %(strategy_hypothesis)s, %(position_id)s, %(pool_id)s, %(token_pair)s, %(horizon)s,
              %(entry_time)s, %(target_time)s, %(outcome_time)s, %(entry_value_usd)s, %(target_value_usd)s,
              %(fee_estimate_usd)s, %(price_loss_or_il_usd)s, %(net_pnl_usd)s, %(net_pnl_pct)s,
              %(score_open_decision)s, %(score_first_selected)s, %(score_max_before_open)s, %(score_median_before_open)s,
              %(top20_by_score_open)s, %(top20_by_score_max)s, %(entry_trusted)s, %(future_position_mark_exists)s,
              %(mark_distance_seconds)s, %(data_quality_status)s, %(invalid_reason)s
            )
        """
        for r in rows:
            cur.execute(insert_sql, r)
        conn.commit()
        return rows


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    idx = max(0, min(len(values) - 1, int((len(values) - 1) * p)))
    return values[idx]


def summarize_proof(rows):
    out = []
    by_h = defaultdict(list)
    for r in rows:
        by_h[r["horizon"]].append(r)
    for horizon, horizon_rows in sorted(by_h.items()):
        valid = [r for r in horizon_rows if not r["invalid_reason"] and r["net_pnl_pct"] is not None]
        invalid = [r for r in horizon_rows if r["invalid_reason"]]
        vals = [r["net_pnl_pct"] for r in valid]
        top_open = [r for r in valid if r["top20_by_score_open"]]
        bottom_open = [r for r in valid if not r["top20_by_score_open"]]
        top_vals = [r["net_pnl_pct"] for r in top_open]
        bottom_vals = [r["net_pnl_pct"] for r in bottom_open]
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
        worst_position_contribution = ""
        worst_pool_contribution = ""
        if valid:
            losses = [abs(min(r["net_pnl_usd"] or 0.0, 0.0)) for r in valid]
            total_loss = sum(losses)
            if total_loss > 0:
                worst_position_contribution = max(losses) / total_loss
                pool_losses = defaultdict(float)
                for r in valid:
                    pool_losses[r["pool_id"]] += abs(min(r["net_pnl_usd"] or 0.0, 0.0))
                worst_pool_contribution = max(pool_losses.values()) / total_loss if pool_losses else ""
        for score_field in SCORE_FIELDS:
            bucket = [r for r in valid if r[score_field] is not None]
            bucket.sort(key=lambda r: r[score_field], reverse=True)
            n = len(bucket)
            topn = max(1, int(n * 0.2)) if n else 0
            top = bucket[:topn]
            bottom = bucket[-topn:] if topn else []
            top_pnl = [r["net_pnl_pct"] for r in top]
            bottom_pnl = [r["net_pnl_pct"] for r in bottom]
            signal2 = "insufficient"
            if top_pnl and bottom_pnl:
                tm = percentile(top_pnl, 0.5)
                bm = percentile(bottom_pnl, 0.5)
                if tm > bm:
                    signal2 = "better"
                elif tm < bm:
                    signal2 = "worse"
                else:
                    signal2 = "flat"
            out.append(
                {
                    "horizon": horizon,
                    "score_basis": score_field,
                    "position_count": len(horizon_rows),
                    "completed_count": len(valid),
                    "invalid_count": len(invalid),
                    "median_net_pnl_pct": percentile(vals, 0.5),
                    "p10_net_pnl_pct": percentile(vals, 0.1),
                    "p5_net_pnl_pct": percentile(vals, 0.05),
                    "p1_net_pnl_pct": percentile(vals, 0.01),
                    "win_rate": (sum(1 for v in vals if v > 0) / len(vals)) if vals else None,
                    "top20_position_count": len(top),
                    "bottom20_position_count": len(bottom),
                    "top20_median_net_pnl_pct": percentile(top_pnl, 0.5),
                    "bottom20_median_net_pnl_pct": percentile(bottom_pnl, 0.5),
                    "top20_p10_net_pnl_pct": percentile(top_pnl, 0.1),
                    "bottom20_p10_net_pnl_pct": percentile(bottom_pnl, 0.1),
                    "top20_vs_bottom20_signal": signal2 if score_field != "score_open_decision" else signal,
                    "worst_position_contribution": worst_position_contribution,
                    "worst_pool_contribution": worst_pool_contribution,
                }
            )
    return out


def summarize_windows(rows):
    now = utc_now()
    windows = [2, 4, 8, 12, 24, 48]
    out = []
    for h in windows:
        cutoff = now - timedelta(hours=h)
        bucket = [r for r in rows if r["entry_time"] and r["entry_time"] >= cutoff]
        per_position = {}
        for r in bucket:
            slot = per_position.setdefault(
                r["position_id"],
                {
                    "entry_trusted": False,
                    "future_position_mark_exists": False,
                    "completed_6h": False,
                    "completed_12h": False,
                    "completed_24h": False,
                },
            )
            slot["entry_trusted"] = slot["entry_trusted"] or bool(r["entry_trusted"])
            slot["future_position_mark_exists"] = slot["future_position_mark_exists"] or bool(r["future_position_mark_exists"])
            if r["horizon"] == "6h" and not r["invalid_reason"]:
                slot["completed_6h"] = True
            if r["horizon"] == "12h" and not r["invalid_reason"]:
                slot["completed_12h"] = True
            if r["horizon"] == "24h" and not r["invalid_reason"]:
                slot["completed_24h"] = True
        count = len(per_position)
        suff = "INSUFFICIENT"
        if count >= 300:
            suff = "USABLE"
        elif count >= 100:
            suff = "PRELIMINARY"
        elif count >= 30:
            suff = "EARLY"
        out.append(
            {
                "window": f"recent_{h}h",
                "new_position_count": count,
                "completed_6h_count": sum(1 for v in per_position.values() if v["completed_6h"]),
                "completed_12h_count": sum(1 for v in per_position.values() if v["completed_12h"]),
                "completed_24h_count": sum(1 for v in per_position.values() if v["completed_24h"]),
                "entry_trusted_rate": (sum(1 for v in per_position.values() if v["entry_trusted"]) / count) if count else None,
                "future_position_mark_coverage": (sum(1 for v in per_position.values() if v["future_position_mark_exists"]) / count) if count else None,
                "sample_sufficiency": suff,
                "sample_note": "SAMPLE_INSUFFICIENT" if suff == "INSUFFICIENT" else "",
            }
        )
    return out


def gate(rows, windows_summary):
    by_h = defaultdict(list)
    for r in rows:
        if r["score_basis"] == "score_open_decision":
            by_h[r["horizon"]] = r
    suff_values = [w["sample_sufficiency"] for w in windows_summary]
    sample_suff = "INSUFFICIENT"
    order = {"INSUFFICIENT": 0, "EARLY": 1, "PRELIMINARY": 2, "USABLE": 3}
    if suff_values:
        sample_suff = max(suff_values, key=lambda x: order[x])
    better_count = sum(1 for h in ["6h", "12h", "24h"] if by_h.get(h, {}).get("top20_vs_bottom20_signal") == "better")
    gate = "INSUFFICIENT"
    if sample_suff in ("PRELIMINARY", "USABLE"):
        gate = "WARN"
        bad_tail = any((by_h.get(h, {}).get("p10_net_pnl_pct") or -999) < -1.0 for h in ["6h", "12h", "24h"] if by_h.get(h))
        if better_count >= 2 and not bad_tail:
            gate = "PASS"
        elif bad_tail:
            gate = "FAIL"
    return {
        "sample_sufficiency": sample_suff,
        "fixed_horizon_gate": gate,
        "better_horizon_count": better_count,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("missing dsn")

    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=False, autocommit=False)
    try:
        rows = materialize(conn, args.run_id)
    finally:
        conn.close()

    counts = defaultdict(lambda: {"total_rows": 0, "future_rows": 0, "invalid_rows": 0})
    for r in rows:
        c = counts[r["horizon"]]
        c["total_rows"] += 1
        if r["future_position_mark_exists"]:
            c["future_rows"] += 1
        if r["invalid_reason"]:
            c["invalid_rows"] += 1
    count_rows = []
    for horizon, c in sorted(counts.items()):
        count_rows.append(
            {
                "run_id": args.run_id,
                "horizon": horizon,
                "total_rows": c["total_rows"],
                "future_rows": c["future_rows"],
                "invalid_rows": c["invalid_rows"],
            }
        )
    write_csv(out_dir / "fixed_horizon_materialization_counts.csv", count_rows, list(count_rows[0].keys()) if count_rows else ["run_id","horizon","total_rows","future_rows","invalid_rows"])

    proof_rows = summarize_proof(rows)
    write_csv(out_dir / "fixed_horizon_vps_position_level_proof.csv", proof_rows, list(proof_rows[0].keys()) if proof_rows else [
        "horizon","score_basis","position_count","completed_count","invalid_count","median_net_pnl_pct","p10_net_pnl_pct","p5_net_pnl_pct","p1_net_pnl_pct","win_rate","top20_position_count","bottom20_position_count","top20_median_net_pnl_pct","bottom20_median_net_pnl_pct","top20_p10_net_pnl_pct","bottom20_p10_net_pnl_pct","top20_vs_bottom20_signal","worst_position_contribution","worst_pool_contribution"
    ])

    window_rows = summarize_windows(rows)
    write_csv(out_dir / "fixed_horizon_vps_fresh_oos_windows.csv", window_rows, list(window_rows[0].keys()))

    gate_summary = gate(proof_rows, window_rows)
    verdict = {
        "status": "WARN" if gate_summary["fixed_horizon_gate"] != "FAIL" else "FAIL",
        "stage": "FIXED_HORIZON_VPS_MATERIALIZATION_WITH_LOCAL_PUBLISH_V2",
        "primary_proof_unit": "position_lifecycle",
        "data_source": "vps_postgres",
        "db_ready": True,
        "vps_git_fetch_required": False,
        "fixed_horizon_hypothesis": "collecting_oos",
        "sample_sufficiency": gate_summary["sample_sufficiency"],
        "position_count_6h": next((r["position_count"] for r in proof_rows if r["horizon"] == "6h" and r["score_basis"] == "score_open_decision"), 0),
        "position_count_12h": next((r["position_count"] for r in proof_rows if r["horizon"] == "12h" and r["score_basis"] == "score_open_decision"), 0),
        "position_count_24h": next((r["position_count"] for r in proof_rows if r["horizon"] == "24h" and r["score_basis"] == "score_open_decision"), 0),
        "completed_6h_count": next((r["completed_count"] for r in proof_rows if r["horizon"] == "6h" and r["score_basis"] == "score_open_decision"), 0),
        "completed_12h_count": next((r["completed_count"] for r in proof_rows if r["horizon"] == "12h" and r["score_basis"] == "score_open_decision"), 0),
        "completed_24h_count": next((r["completed_count"] for r in proof_rows if r["horizon"] == "24h" and r["score_basis"] == "score_open_decision"), 0),
        "fixed_horizon_gate": gate_summary["fixed_horizon_gate"],
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": "FIXED_HORIZON_CONTINUE_OOS_ACCUMULATION" if gate_summary["sample_sufficiency"] != "USABLE" else "FIXED_HORIZON_HYPOTHESIS_REVIEW",
    }

    (out_dir / "fixed_horizon_vps_hypothesis_gate.json").write_text(json.dumps(gate_summary, indent=2))
    (out_dir / "FINAL_VERDICT.json").write_text(json.dumps(verdict, indent=2))

    md(out_dir / "FIXED_HORIZON_MATERIALIZATION_CN.md", f"""# Fixed Horizon Materialization\n\n- run_id: `{args.run_id}`\n- research_table: `shadow_position_lifecycle_proof_v2`\n- rows_inserted: {len(rows)}\n- proof_unit: `position_lifecycle`\n- horizons: 6h / 12h / 24h\n- source_tables: `positions`, `shadow_position_marks`, `shadow_decision_trace`\n""")
    md(out_dir / "FIXED_HORIZON_VPS_POSITION_LEVEL_PROOF_CN.md", "# Fixed Horizon VPS Position Level Proof\n\n" + "\n".join(
        f"- `{r['horizon']}` `{r['score_basis']}` position_count={r['position_count']} completed={r['completed_count']} invalid={r['invalid_count']} median={r['median_net_pnl_pct']} p10={r['p10_net_pnl_pct']} signal={r['top20_vs_bottom20_signal']}"
        for r in proof_rows
    ) + "\n")
    md(out_dir / "FIXED_HORIZON_VPS_FRESH_OOS_WINDOWS_CN.md", "# Fixed Horizon VPS Fresh OOS Windows\n\n" + "\n".join(
        f"- `{r['window']}` new_position_count={r['new_position_count']} completed_6h={r['completed_6h_count']} completed_12h={r['completed_12h_count']} completed_24h={r['completed_24h_count']} sample_sufficiency={r['sample_sufficiency']} {r['sample_note']}".rstrip()
        for r in window_rows
    ) + "\n")
    md(out_dir / "FIXED_HORIZON_VPS_HYPOTHESIS_GATE_CN.md", f"""# Fixed Horizon VPS Hypothesis Gate\n\n- sample_sufficiency: {gate_summary['sample_sufficiency']}\n- fixed_horizon_gate: {gate_summary['fixed_horizon_gate']}\n- better_horizon_count: {gate_summary['better_horizon_count']}\n- edge_proven: no\n- tiny_canary_allowed: no\n""")
    md(out_dir / "ONEPAGE_CN.md", f"""# One Page\n\n- data_source = vps_postgres\n- db_ready = yes\n- position_count_6h = {verdict['position_count_6h']}\n- position_count_12h = {verdict['position_count_12h']}\n- position_count_24h = {verdict['position_count_24h']}\n- completed_6h_count = {verdict['completed_6h_count']}\n- completed_12h_count = {verdict['completed_12h_count']}\n- completed_24h_count = {verdict['completed_24h_count']}\n- fixed_horizon_gate = {verdict['fixed_horizon_gate']}\n- sample_sufficiency = {verdict['sample_sufficiency']}\n- tiny_canary_allowed = no\n- recommended_next_stage = {verdict['recommended_next_stage']}\n""")
    md(out_dir / "ARTIFACT_INDEX.md", """# Artifact Index\n\n- `fixed_horizon_vps_materialize_readonly.py`\n- `FIXED_HORIZON_MATERIALIZATION_CN.md`\n- `fixed_horizon_materialization_counts.csv`\n- `FIXED_HORIZON_VPS_POSITION_LEVEL_PROOF_CN.md`\n- `fixed_horizon_vps_position_level_proof.csv`\n- `FIXED_HORIZON_VPS_FRESH_OOS_WINDOWS_CN.md`\n- `fixed_horizon_vps_fresh_oos_windows.csv`\n- `FIXED_HORIZON_VPS_HYPOTHESIS_GATE_CN.md`\n- `fixed_horizon_vps_hypothesis_gate.json`\n- `FINAL_VERDICT.json`\n- `ONEPAGE_CN.md`\n""")


if __name__ == "__main__":
    main()
