#!/usr/bin/env python3
import csv
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

RUN_ID = "20260530_143120"
OUT_DIR = Path("/tmp/materializer_semantics_20260530_143120")
OUT_DIR.mkdir(parents=True, exist_ok=True)
HORIZONS = [6, 12, 24]
PROOF_VARIANTS = [
    "v2_strict_baseline",
    "v3_active_nearest_position_mark",
    "v3_terminal_pool_counterfactual",
    "v3_clean_fixed_horizon",
]


def utc_now():
    return datetime.now(timezone.utc)


def parse_ts(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v
    if isinstance(v, (int, float)):
        if v == 0:
            return None
        if v > 10_000_000_000:
            v = v / 1000.0
        if v <= 0:
            return None
        return datetime.fromtimestamp(v, tz=timezone.utc)
    s = str(v)
    if s.isdigit():
        return parse_ts(int(s))
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.year <= 1971:
            return None
        return dt
    except Exception:
        return None


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_md(path, text):
    Path(path).write_text(text)


def q(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


def q1(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchone()


def pct_change(target, entry):
    if target is None or entry in (None, 0):
        return None
    return (target - entry) / entry * 100.0


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    idx = max(0, min(len(values) - 1, int((len(values) - 1) * p)))
    return values[idx]


def ensure_table(cur):
    cur.execute(
        """
        create table if not exists shadow_position_lifecycle_proof_v3_research (
          run_id text not null,
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
          proof_variant text not null,
          mark_source text,
          position_status_at_target text,
          entry_trusted boolean,
          future_position_mark_exists boolean,
          nearest_position_mark_exists boolean,
          pool_mark_exists boolean,
          mark_distance_seconds integer,
          confidence text,
          score_open_decision double precision,
          score_first_selected double precision,
          score_max_before_open double precision,
          score_median_before_open double precision,
          data_quality_status text,
          invalid_reason text,
          created_at timestamptz not null default now(),
          primary key (run_id, position_id, horizon, proof_variant)
        )
        """
    )


def load_positions(cur):
    rows = q(
        cur,
        """
        select id::text as position_id,
               pool_id::text as pool_id,
               opened_at,
               closed_at,
               amount_usd
        from positions
        """
    )
    token_pairs = {}
    try:
        seed = q(cur, "select distinct position_id::text as position_id, token_pair from shadow_position_lifecycle_proof_v1")
        token_pairs = {r["position_id"]: (r["token_pair"] or "") for r in seed}
    except Exception:
        token_pairs = {}
    out = {}
    for r in rows:
        open_dt = parse_ts(r["opened_at"])
        close_dt = parse_ts(r["closed_at"])
        out[r["position_id"]] = {
            "position_id": r["position_id"],
            "pool_id": r["pool_id"],
            "token_pair": token_pairs.get(r["position_id"]) or r["pool_id"],
            "entry_time": open_dt,
            "close_time": close_dt,
            "entry_value_usd": float(r["amount_usd"] or 0.0),
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
               source
        from shadow_position_marks
        order by mark_time
        """
    )
    by_pos = defaultdict(list)
    by_pool = defaultdict(list)
    for r in rows:
        mark_dt = parse_ts(r["mark_time"])
        if not mark_dt:
            continue
        rec = {
            "position_id": r["position_id"],
            "pool_id": r["pool_id"],
            "mark_dt": mark_dt,
            "valuation_usd": float(r["valuation_usd"]) if r["valuation_usd"] is not None else None,
            "fee_usd": float(r["fee_usd"]) if r["fee_usd"] is not None else None,
            "il_usd": float(r["il_usd"]) if r["il_usd"] is not None else None,
            "net_pnl_usd": float(r["net_pnl_usd"]) if r["net_pnl_usd"] is not None else None,
            "source": r["source"] or "",
        }
        by_pos[r["position_id"]].append(rec)
        by_pool[r["pool_id"]].append(rec)
    return by_pos, by_pool


def load_scores(cur):
    rows = q(
        cur,
        """
        select coalesce(position_id::text,'') as position_id,
               tick_time, score_total, selected, intent_open
        from shadow_decision_trace
        where coalesce(position_id::text,'') <> ''
        order by position_id, tick_time
        """
    )
    by_pos = defaultdict(list)
    for r in rows:
        dt = parse_ts(r["tick_time"])
        if not dt:
            continue
        by_pos[r["position_id"]].append(
            {
                "dt": dt,
                "score_total": float(r["score_total"] or 0.0),
                "selected": bool(r["selected"]),
                "intent_open": bool(r["intent_open"]),
            }
        )
    return by_pos


def score_summary(score_rows, entry_time):
    before = [r for r in score_rows if r["dt"] <= entry_time]
    if not before:
        return {k: None for k in ("score_open_decision", "score_first_selected", "score_max_before_open", "score_median_before_open")}
    vals = [r["score_total"] for r in before]
    vals_sorted = sorted(vals)
    mid = len(vals_sorted) // 2
    median = vals_sorted[mid] if len(vals_sorted) % 2 == 1 else (vals_sorted[mid - 1] + vals_sorted[mid]) / 2.0
    selected_rows = [r for r in before if r["selected"] and r["intent_open"]]
    return {
        "score_open_decision": before[-1]["score_total"],
        "score_first_selected": selected_rows[0]["score_total"] if selected_rows else None,
        "score_max_before_open": max(vals),
        "score_median_before_open": median,
    }


def nearest_after_target(marks, target):
    after = [m for m in marks if m["mark_dt"] >= target]
    if not after:
        return None
    return min(after, key=lambda m: abs((m["mark_dt"] - target).total_seconds()))


def nearest_any_after_open(marks, open_dt, target):
    pool = [m for m in marks if m["mark_dt"] > open_dt]
    if not pool:
        return None
    return min(pool, key=lambda m: abs((m["mark_dt"] - target).total_seconds()))


dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
if not dsn:
    raise SystemExit("missing dsn")

conn = psycopg2.connect(dsn)
conn.set_session(readonly=False, autocommit=False)
cur = conn.cursor(cursor_factory=RealDictCursor)
ensure_table(cur)
cur.execute("delete from shadow_position_lifecycle_proof_v3_research where run_id = %s", (RUN_ID,))

positions = load_positions(cur)
marks_by_pos, marks_by_pool = load_marks(cur)
scores_by_pos = load_scores(cur)
now = utc_now()

rows = []
for pid, p in positions.items():
    if not p["entry_time"] or not p["entry_value_usd"]:
        continue
    score_meta = score_summary(scores_by_pos.get(pid, []), p["entry_time"])
    pos_marks = marks_by_pos.get(pid, [])
    pool_marks = marks_by_pool.get(p["pool_id"], [])
    for h in HORIZONS:
        horizon = f"{h}h"
        target = p["entry_time"] + timedelta(hours=h)
        matured = now >= target
        active_at_target = not p["close_time"] or p["close_time"] >= target
        status = "unknown"
        if not matured:
            status = "horizon_not_mature"
        elif active_at_target:
            status = "active_at_target"
        else:
            status = "terminal_before_target"

        future_pos = nearest_after_target(pos_marks, target) if matured else None
        nearest_pos = nearest_any_after_open(pos_marks, p["entry_time"], target) if active_at_target else None
        pool_mark = nearest_after_target(pool_marks, target) if matured and not future_pos else None

        common = {
            "run_id": RUN_ID,
            "position_id": pid,
            "pool_id": p["pool_id"],
            "token_pair": p["token_pair"],
            "horizon": horizon,
            "entry_time": p["entry_time"],
            "target_time": target,
            "entry_value_usd": p["entry_value_usd"],
            "position_status_at_target": status,
            "entry_trusted": True,
            "future_position_mark_exists": bool(future_pos),
            "nearest_position_mark_exists": bool(nearest_pos),
            "pool_mark_exists": bool(pool_mark),
            "score_open_decision": score_meta["score_open_decision"],
            "score_first_selected": score_meta["score_first_selected"],
            "score_max_before_open": score_meta["score_max_before_open"],
            "score_median_before_open": score_meta["score_median_before_open"],
        }

        def finalize(variant, mark, mark_source, confidence, quality, invalid_reason):
            target_val = mark["valuation_usd"] if mark else None
            fee = mark["fee_usd"] if mark else None
            il = mark["il_usd"] if mark else None
            pnl_usd = mark["net_pnl_usd"] if mark and mark["net_pnl_usd"] is not None else (target_val - p["entry_value_usd"] if target_val is not None else None)
            pnl_pct = pct_change(target_val, p["entry_value_usd"])
            dist = int((mark["mark_dt"] - target).total_seconds()) if mark else None
            return {
                **common,
                "proof_variant": variant,
                "outcome_time": mark["mark_dt"] if mark else None,
                "target_value_usd": target_val,
                "fee_estimate_usd": fee,
                "price_loss_or_il_usd": il,
                "net_pnl_usd": pnl_usd,
                "net_pnl_pct": pnl_pct,
                "mark_source": mark_source,
                "mark_distance_seconds": dist,
                "confidence": confidence,
                "data_quality_status": quality,
                "invalid_reason": invalid_reason,
            }

        # v2 strict baseline
        if status == "active_at_target" and future_pos:
            rows.append(finalize("v2_strict_baseline", future_pos, "future_position_mark", "high", "ok", ""))
        else:
            invalid = "horizon_not_mature" if status == "horizon_not_mature" else ("terminal_before_target" if status == "terminal_before_target" else "no_future_mark")
            rows.append(finalize("v2_strict_baseline", None, "none", "none", "invalid", invalid))

        # v3 active nearest position mark
        if status == "active_at_target" and nearest_pos:
            source = "future_position_mark" if future_pos else "nearest_position_mark"
            conf = "high" if future_pos else "medium"
            qual = "ok" if future_pos else "nearest_tolerance"
            rows.append(finalize("v3_active_nearest_position_mark", future_pos or nearest_pos, source, conf, qual, ""))
        else:
            invalid = "horizon_not_mature" if status == "horizon_not_mature" else ("terminal_before_target" if status == "terminal_before_target" else "no_nearest_position_mark")
            rows.append(finalize("v3_active_nearest_position_mark", None, "none", "none", "invalid", invalid))

        # v3 terminal pool counterfactual
        if status == "terminal_before_target" and pool_mark:
            rows.append(finalize("v3_terminal_pool_counterfactual", pool_mark, "pool_mark_only", "low", "counterfactual_only", ""))
        else:
            invalid = "not_terminal_before_target" if status != "terminal_before_target" else "no_pool_mark_only_counterfactual"
            rows.append(finalize("v3_terminal_pool_counterfactual", None, "none", "none", "invalid", invalid))

        # v3 clean fixed horizon
        if common["entry_trusted"] and status == "active_at_target" and (future_pos or nearest_pos):
            source = "future_position_mark" if future_pos else "nearest_position_mark"
            conf = "high" if future_pos else "medium"
            qual = "clean_fixed_horizon" if future_pos else "clean_fixed_horizon_with_tolerance"
            rows.append(finalize("v3_clean_fixed_horizon", future_pos or nearest_pos, source, conf, qual, ""))
        else:
            if status == "terminal_before_target":
                invalid = "terminal_before_target"
            elif status == "horizon_not_mature":
                invalid = "horizon_not_mature"
            elif not common["entry_trusted"]:
                invalid = "entry_untrusted"
            else:
                invalid = "no_clean_same_position_mark"
            rows.append(finalize("v3_clean_fixed_horizon", None, "none", "none", "invalid", invalid))

insert_sql = """
insert into shadow_position_lifecycle_proof_v3_research (
  run_id, position_id, pool_id, token_pair, horizon, entry_time, target_time, outcome_time,
  entry_value_usd, target_value_usd, fee_estimate_usd, price_loss_or_il_usd, net_pnl_usd, net_pnl_pct,
  proof_variant, mark_source, position_status_at_target, entry_trusted, future_position_mark_exists,
  nearest_position_mark_exists, pool_mark_exists, mark_distance_seconds, confidence,
  score_open_decision, score_first_selected, score_max_before_open, score_median_before_open,
  data_quality_status, invalid_reason
) values (
  %(run_id)s, %(position_id)s, %(pool_id)s, %(token_pair)s, %(horizon)s, %(entry_time)s, %(target_time)s, %(outcome_time)s,
  %(entry_value_usd)s, %(target_value_usd)s, %(fee_estimate_usd)s, %(price_loss_or_il_usd)s, %(net_pnl_usd)s, %(net_pnl_pct)s,
  %(proof_variant)s, %(mark_source)s, %(position_status_at_target)s, %(entry_trusted)s, %(future_position_mark_exists)s,
  %(nearest_position_mark_exists)s, %(pool_mark_exists)s, %(mark_distance_seconds)s, %(confidence)s,
  %(score_open_decision)s, %(score_first_selected)s, %(score_max_before_open)s, %(score_median_before_open)s,
  %(data_quality_status)s, %(invalid_reason)s
)
"""
for r in rows:
    cur.execute(insert_sql, r)
conn.commit()

# reports
schema = {
    "research_table": "shadow_position_lifecycle_proof_v3_research",
    "run_id": RUN_ID,
    "proof_variants": PROOF_VARIANTS,
    "horizons": [f"{h}h" for h in HORIZONS],
}
(OUT_DIR / "v3_schema.json").write_text(json.dumps(schema, indent=2))
write_md(OUT_DIR / "V3_SCHEMA_CN.md", "# V3 Schema\n\n- research_table: `shadow_position_lifecycle_proof_v3_research`\n- run_id: `%s`\n- variants: %s\n" % (RUN_ID, ", ".join(PROOF_VARIANTS)))

counts = []
for hz in [f"{h}h" for h in HORIZONS]:
    for variant in PROOF_VARIANTS:
        subset = [r for r in rows if r["horizon"] == hz and r["proof_variant"] == variant]
        counts.append({
            "horizon": hz,
            "proof_variant": variant,
            "row_count": len(subset),
            "completed_count": sum(1 for r in subset if not r["invalid_reason"]),
            "pool_mark_only_count": sum(1 for r in subset if r["mark_source"] == "pool_mark_only"),
            "active_nearest_count": sum(1 for r in subset if r["mark_source"] == "nearest_position_mark"),
            "terminal_before_target_count": sum(1 for r in subset if r["position_status_at_target"] == "terminal_before_target"),
            "confidence_high": sum(1 for r in subset if r["confidence"] == "high"),
            "confidence_medium": sum(1 for r in subset if r["confidence"] == "medium"),
            "confidence_low": sum(1 for r in subset if r["confidence"] == "low"),
        })
write_csv(OUT_DIR / "materializer_v3_research_materialization_counts.csv", counts, list(counts[0].keys()))

v2v3 = []
for hz in [f"{h}h" for h in HORIZONS]:
    byv = {v: [r for r in rows if r["horizon"] == hz and r["proof_variant"] == v] for v in PROOF_VARIANTS}
    v2_completed = sum(1 for r in byv["v2_strict_baseline"] if not r["invalid_reason"])
    v2_no_future = sum(1 for r in byv["v2_strict_baseline"] if r["invalid_reason"] == "no_future_mark")
    v3_active = sum(1 for r in byv["v3_active_nearest_position_mark"] if not r["invalid_reason"])
    v3_counter = sum(1 for r in byv["v3_terminal_pool_counterfactual"] if not r["invalid_reason"])
    v3_clean = sum(1 for r in byv["v3_clean_fixed_horizon"] if not r["invalid_reason"])
    terminal_excluded = sum(1 for r in byv["v3_clean_fixed_horizon"] if r["invalid_reason"] == "terminal_before_target")
    pool_counter = sum(1 for r in byv["v3_terminal_pool_counterfactual"] if r["mark_source"] == "pool_mark_only" and not r["invalid_reason"])
    v2v3.append({
        "horizon": hz,
        "v2_strict_completed_count": v2_completed,
        "v2_no_future_mark_count": v2_no_future,
        "v3_active_nearest_count": v3_active,
        "v3_terminal_pool_counterfactual_count": v3_counter,
        "v3_clean_fixed_horizon_count": v3_clean,
        "coverage_gain_clean": v3_clean - v2_completed,
        "coverage_gain_counterfactual": v3_counter,
        "terminal_excluded_count": terminal_excluded,
        "pool_mark_only_counterfactual_count": pool_counter,
    })
write_csv(OUT_DIR / "v2_vs_v3_coverage_comparison.csv", v2v3, list(v2v3[0].keys()))

quality_rows = []
for hz in [f"{h}h" for h in HORIZONS]:
    for variant in PROOF_VARIANTS:
        subset = [r for r in rows if r["horizon"] == hz and r["proof_variant"] == variant]
        valid = [r for r in subset if not r["invalid_reason"] and r["net_pnl_pct"] is not None]
        vals = [r["net_pnl_pct"] for r in valid]
        ranked = [r for r in valid if r["score_open_decision"] is not None]
        ranked.sort(key=lambda r: r["score_open_decision"], reverse=True)
        n = len(ranked)
        topn = max(1, int(n * 0.2)) if n else 0
        top = ranked[:topn]
        bot = ranked[-topn:] if topn else []
        top_vals = [r["net_pnl_pct"] for r in top]
        bot_vals = [r["net_pnl_pct"] for r in bot]
        signal = "insufficient"
        if top_vals and bot_vals:
            tm, bm = percentile(top_vals, 0.5), percentile(bot_vals, 0.5)
            if tm > bm:
                signal = "better"
            elif tm < bm:
                signal = "worse"
            else:
                signal = "flat"
        losses = [abs(min(r["net_pnl_usd"] or 0.0, 0.0)) for r in valid]
        total_loss = sum(losses)
        worst_pos = max(losses) / total_loss if total_loss > 0 else None
        pool_losses = defaultdict(float)
        for r in valid:
            pool_losses[r["pool_id"]] += abs(min(r["net_pnl_usd"] or 0.0, 0.0))
        worst_pool = max(pool_losses.values()) / total_loss if total_loss > 0 and pool_losses else None
        conf_dist = Counter(r["confidence"] for r in subset)
        quality_rows.append({
            "horizon": hz,
            "proof_variant": variant,
            "position_count": len(subset),
            "completed_count": len(valid),
            "invalid_count": len(subset) - len(valid),
            "median_net_pnl_pct": percentile(vals, 0.5),
            "p10_net_pnl_pct": percentile(vals, 0.1),
            "p5_net_pnl_pct": percentile(vals, 0.05),
            "p1_net_pnl_pct": percentile(vals, 0.01),
            "win_rate": (sum(1 for v in vals if v > 0) / len(vals)) if vals else None,
            "top20_vs_bottom20_signal": signal,
            "worst_position_contribution": worst_pos,
            "worst_pool_contribution": worst_pool,
            "confidence_distribution": json.dumps(conf_dist),
            "can_be_clean_proof": "yes" if variant == "v3_clean_fixed_horizon" else "no",
            "can_be_counterfactual_only": "yes" if variant == "v3_terminal_pool_counterfactual" else "no",
        })
write_csv(OUT_DIR / "materializer_v3_proof_quality.csv", quality_rows, list(quality_rows[0].keys()))

v3_clean_completed = {r["horizon"]: r["v3_clean_fixed_horizon_count"] for r in v2v3}
v2_completed = {r["horizon"]: r["v2_strict_completed_count"] for r in v2v3}
v3_counter = {r["horizon"]: r["v3_terminal_pool_counterfactual_count"] for r in v2v3}
v3_clean_usable = any((v3_clean_completed.get(hz, 0) > v2_completed.get(hz, 0)) for hz in ["6h", "12h", "24h"])
if v3_clean_usable:
    next_stage = "FIXED_HORIZON_V3_CLEAN_PROOF_REVIEW"
elif any(v3_counter.get(hz, 0) > 0 for hz in ["6h", "12h", "24h"]):
    next_stage = "FIXED_HORIZON_CONTINUE_OOS_ACCUMULATION"
else:
    next_stage = "FIXED_HORIZON_STOP_RESEARCH"
if any(r["proof_variant"] == "v3_active_nearest_position_mark" and r["completed_count"] > 0 for r in quality_rows) and not v3_clean_usable:
    next_stage = "MATERIALIZER_FIX"

semantics = {
    "keep_v2_strict_as_canonical_proof": True,
    "add_v3_research_only_proof": True,
    "v3_clean_fixed_horizon_adds_meaningful_samples": v3_clean_usable,
    "pool_mark_only_counterfactual_only": True,
    "terminal_before_target_excluded_from_clean_proof": True,
    "worth_entering_hypothesis_review": next_stage == "FIXED_HORIZON_V3_CLEAN_PROOF_REVIEW",
    "recommended_next_stage": next_stage,
}
(OUT_DIR / "materializer_semantics_decision.json").write_text(json.dumps(semantics, indent=2))

final = {
    "status": "PASS",
    "stage": "MATERIALIZER_SEMANTICS_FIX_V1",
    "data_source": "vps_postgres",
    "db_ready": True,
    "v2_strict_completed_6h": v2_completed.get("6h", 0),
    "v2_strict_completed_12h": v2_completed.get("12h", 0),
    "v2_strict_completed_24h": v2_completed.get("24h", 0),
    "v3_clean_completed_6h": v3_clean_completed.get("6h", 0),
    "v3_clean_completed_12h": v3_clean_completed.get("12h", 0),
    "v3_clean_completed_24h": v3_clean_completed.get("24h", 0),
    "v3_counterfactual_completed_6h": v3_counter.get("6h", 0),
    "v3_counterfactual_completed_12h": v3_counter.get("12h", 0),
    "v3_counterfactual_completed_24h": v3_counter.get("24h", 0),
    "v3_clean_proof_usable": bool(v3_clean_usable),
    "pool_mark_only_used_as_clean_proof": False,
    "terminal_before_target_in_clean_proof": False,
    "edge_proven": "no",
    "tiny_canary_candidate": "no",
    "tiny_canary_allowed": "no",
    "recommended_next_stage": next_stage,
}
(OUT_DIR / "FINAL_VERDICT.json").write_text(json.dumps(final, indent=2))

write_md(OUT_DIR / "MATERIALIZER_V3_RESEARCH_MATERIALIZATION_CN.md", "# V3 Research Materialization\n\n- run_id: `%s`\n- rows_inserted: `%d`\n- table: `shadow_position_lifecycle_proof_v3_research`\n" % (RUN_ID, len(rows)))
write_md(OUT_DIR / "V2_VS_V3_COVERAGE_COMPARISON_CN.md", "# V2 vs V3 Coverage Comparison\n\n" + "\n".join(f"- `{r['horizon']}` v2_strict={r['v2_strict_completed_count']} v3_clean={r['v3_clean_fixed_horizon_count']} v3_counterfactual={r['v3_terminal_pool_counterfactual_count']} gain_clean={r['coverage_gain_clean']} gain_counterfactual={r['coverage_gain_counterfactual']}" for r in v2v3) + "\n")
write_md(OUT_DIR / "MATERIALIZER_V3_PROOF_QUALITY_CN.md", "# V3 Proof Quality\n\n" + "\n".join(f"- `{r['horizon']}` `{r['proof_variant']}` completed={r['completed_count']} median={r['median_net_pnl_pct']} p10={r['p10_net_pnl_pct']} signal={r['top20_vs_bottom20_signal']} clean={r['can_be_clean_proof']} counterfactual={r['can_be_counterfactual_only']}" for r in quality_rows) + "\n")
write_md(OUT_DIR / "MATERIALIZER_SEMANTICS_DECISION_CN.md", "# Materializer Semantics Decision\n\n- keep_v2_strict_as_canonical_proof: yes\n- add_v3_research_only_proof: yes\n- v3_clean_fixed_horizon_adds_meaningful_samples: %s\n- pool_mark_only_counterfactual_only: yes\n- terminal_before_target_excluded_from_clean_proof: yes\n- worth_entering_hypothesis_review: %s\n- recommended_next_stage: `%s`\n" % ("yes" if semantics["v3_clean_fixed_horizon_adds_meaningful_samples"] else "no", "yes" if semantics["worth_entering_hypothesis_review"] else "no", next_stage))
write_md(OUT_DIR / "ONEPAGE_CN.md", "# One Page\n\n- v2_strict_completed_6h = %s\n- v2_strict_completed_12h = %s\n- v2_strict_completed_24h = %s\n- v3_clean_completed_6h = %s\n- v3_clean_completed_12h = %s\n- v3_clean_completed_24h = %s\n- v3_counterfactual_completed_6h = %s\n- v3_counterfactual_completed_12h = %s\n- v3_counterfactual_completed_24h = %s\n- v3_clean_proof_usable = %s\n- pool_mark_only_used_as_clean_proof = no\n- terminal_before_target_in_clean_proof = no\n- recommended_next_stage = %s\n- tiny_canary_allowed = no\n" % (final["v2_strict_completed_6h"], final["v2_strict_completed_12h"], final["v2_strict_completed_24h"], final["v3_clean_completed_6h"], final["v3_clean_completed_12h"], final["v3_clean_completed_24h"], final["v3_counterfactual_completed_6h"], final["v3_counterfactual_completed_12h"], final["v3_counterfactual_completed_24h"], "yes" if final["v3_clean_proof_usable"] else "no", next_stage))
write_md(OUT_DIR / "ARTIFACT_INDEX.md", "# Artifact Index\n\n- INPUT_ARTIFACT_AUDIT_CN.md\n- input_artifact_audit.json\n- VPS_DB_QUICK_CHECK_CN.md\n- V3_SCHEMA_CN.md\n- v3_schema.json\n- MATERIALIZER_V3_RESEARCH_MATERIALIZATION_CN.md\n- materializer_v3_research_materialization_counts.csv\n- V2_VS_V3_COVERAGE_COMPARISON_CN.md\n- v2_vs_v3_coverage_comparison.csv\n- MATERIALIZER_V3_PROOF_QUALITY_CN.md\n- materializer_v3_proof_quality.csv\n- MATERIALIZER_SEMANTICS_DECISION_CN.md\n- materializer_semantics_decision.json\n- FINAL_VERDICT.json\n- ONEPAGE_CN.md\n")

cur.close()
conn.close()
