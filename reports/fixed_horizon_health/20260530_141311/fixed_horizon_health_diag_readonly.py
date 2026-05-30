#!/usr/bin/env python3
import csv
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

RUN_ID = "20260530_141311"
OUT_DIR = Path("/tmp/fixed_horizon_health_20260530_141311")
OUT_DIR.mkdir(parents=True, exist_ok=True)
WINDOWS = [2, 6, 12, 24, 48]


def utc_now():
    return datetime.now(timezone.utc)


def parse_ts(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, (int, float)):
        if v > 10_000_000_000:
            v = v / 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc)
    s = str(v)
    if s.isdigit():
        return parse_ts(int(s))
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def q(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


def q1(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchone()


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_md(path, text):
    Path(path).write_text(text)


dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
if not dsn:
    raise SystemExit("missing dsn")

conn = psycopg2.connect(dsn)
cur = conn.cursor(cursor_factory=RealDictCursor)
now = utc_now()

# DB freshness
fresh_tables = [
    ("shadow_decision_trace", "tick_time"),
    ("shadow_position_marks", "mark_time"),
    ("positions", "opened_at"),
    ("shadow_exit_decisions", "created_at"),
    ("shadow_exit_actions", "created_at"),
    ("shadow_outcome_labels", "created_at"),
    ("shadow_position_lifecycle_proof_v2", "created_at"),
]
fr = []
for table, col in fresh_tables:
    total = q1(cur, f"select count(*) as c from {table}")["c"]
    latest = parse_ts(q1(cur, f"select max({col}) as ts from {table}")["ts"])
    row = {"table_name": table, "total_rows": total, "latest_timestamp": latest.isoformat() if latest else ""}
    status = "UNKNOWN"
    if total == 0:
        status = "EMPTY"
    elif latest is None:
        status = "UNKNOWN"
    else:
        age = (now - latest).total_seconds() / 3600.0
        status = "HEALTHY" if age <= 6 else "STALE"
    for h in WINDOWS:
        c = q1(cur, f"select count(*) as c from {table} where {col} >= %s", (now - timedelta(hours=h),))["c"]
        row[f"rows_last_{h}h"] = c
    row["freshness_status"] = status
    fr.append(row)
write_csv(OUT_DIR / "db_write_freshness.csv", fr, list(fr[0].keys()))

# Decision trace funnel and reasons
funnel = []
reason_rows = []
for h in WINDOWS:
    cutoff = now - timedelta(hours=h)
    base = q1(
        cur,
        """
        select count(*) as trace_count,
               count(*) filter (where pipeline_stage='candidate_filtered') as candidate_filtered_count,
               count(*) filter (where selected) as selected_count,
               count(*) filter (where intent_open) as intent_open_count,
               count(*) filter (where final_action in ('open','open_or_reuse','reuse','opened')) as open_or_reuse_count,
               count(distinct pool_id) as unique_pool_count,
               avg(score_total) as avg_score,
               max(score_total) as max_score
        from shadow_decision_trace
        where to_timestamp(case when tick_time > 1000000000000 then tick_time/1000.0 else tick_time::double precision end) >= %s
        """,
        (cutoff,),
    )
    funnel.append(
        {
            "window": f"recent_{h}h",
            "trace_count": base["trace_count"],
            "candidate_filtered_count": base["candidate_filtered_count"],
            "selected_count": base["selected_count"],
            "intent_open_count": base["intent_open_count"],
            "open_or_reuse_count": base["open_or_reuse_count"],
            "unique_pool_count": base["unique_pool_count"],
            "avg_score": float(base["avg_score"]) if base["avg_score"] is not None else None,
            "max_score": float(base["max_score"]) if base["max_score"] is not None else None,
        }
    )
    top_reasons = q(
        cur,
        """
        select coalesce(selection_reason, intent_reason, pipeline_reason, final_action, 'unknown') as latest_reason,
               count(*) as reason_count
        from shadow_decision_trace
        where to_timestamp(case when tick_time > 1000000000000 then tick_time/1000.0 else tick_time::double precision end) >= %s
        group by 1 order by 2 desc limit 20
        """,
        (cutoff,),
    )
    for r in top_reasons:
        reason_rows.append({"window": f"recent_{h}h", "latest_reason": r["latest_reason"], "reason_count": r["reason_count"]})
write_csv(OUT_DIR / "decision_trace_selection_funnel.csv", funnel, list(funnel[0].keys()))
write_csv(
    OUT_DIR / "decision_trace_latest_reason_top.csv",
    reason_rows,
    list(reason_rows[0].keys()) if reason_rows else ["window", "latest_reason", "reason_count"],
)

# Position lifecycle freshness from positions + marks + proof v2 current latest run
pos_rows = q(cur, "select id::text as position_id, opened_at, closed_at, pool_id::text as pool_id from positions")
mark_rows = q(cur, "select position_id::text as position_id, mark_time from shadow_position_marks order by position_id, mark_time")
latest_run = q1(cur, "select run_id from shadow_position_lifecycle_proof_v2 order by created_at desc limit 1")
active_run_id = latest_run["run_id"] if latest_run else ""
proof_rows = q(
    cur,
    """
    select run_id, position_id::text as position_id, horizon, entry_time, target_time,
           future_position_mark_exists, invalid_reason, mark_distance_seconds, created_at
    from shadow_position_lifecycle_proof_v2
    where run_id=%s
    """,
    (active_run_id,),
)
marks_by_pos = defaultdict(list)
for r in mark_rows:
    mt = parse_ts(r["mark_time"])
    if mt:
        marks_by_pos[r["position_id"]].append(mt)
proof_by_pos_h = {(r["position_id"], r["horizon"]): r for r in proof_rows}
plf = []
invalid_counter = Counter()
for h in WINDOWS:
    cutoff = now - timedelta(hours=h)
    new_positions = [p for p in pos_rows if parse_ts(p["opened_at"]) and parse_ts(p["opened_at"]) >= cutoff]
    pos_ids = {p["position_id"] for p in new_positions}
    open_count = sum(1 for p in new_positions if parse_ts(p["closed_at"]) is None)
    closed_count = sum(1 for p in new_positions if parse_ts(p["closed_at"]) is not None)
    with_marks = {pid for pid in pos_ids if marks_by_pos.get(pid)}
    fut6 = fut12 = fut24 = no_future = 0
    mark_dist = []
    for pid in pos_ids:
        any_future = False
        for hz in ("6h", "12h", "24h"):
            pr = proof_by_pos_h.get((pid, hz))
            if pr and pr.get("future_position_mark_exists"):
                any_future = True
                if hz == "6h":
                    fut6 += 1
                elif hz == "12h":
                    fut12 += 1
                else:
                    fut24 += 1
            if pr and pr.get("mark_distance_seconds") is not None:
                mark_dist.append(int(pr["mark_distance_seconds"]))
            if pr and pr.get("invalid_reason"):
                invalid_counter[(f"recent_{h}h", pr["invalid_reason"])] += 1
        if not any_future:
            no_future += 1
    mark_dist.sort()
    def pct(vals, p):
        if not vals:
            return None
        idx = max(0, min(len(vals) - 1, int((len(vals) - 1) * p)))
        return vals[idx]
    plf.append(
        {
            "window": f"recent_{h}h",
            "new_position_count": len(pos_ids),
            "open_position_count": open_count,
            "closed_position_count": closed_count,
            "position_with_marks_count": len(with_marks),
            "position_with_future_6h_mark_count": fut6,
            "position_with_future_12h_mark_count": fut12,
            "position_with_future_24h_mark_count": fut24,
            "position_without_future_mark_count": no_future,
            "mark_distance_p50_seconds": pct(mark_dist, 0.5),
            "mark_distance_p90_seconds": pct(mark_dist, 0.9),
            "mark_distance_p99_seconds": pct(mark_dist, 0.99),
        }
    )
invalid_rows = [{"window": w, "invalid_reason": reason, "count": count} for (w, reason), count in invalid_counter.items()]
write_csv(OUT_DIR / "position_lifecycle_freshness.csv", plf, list(plf[0].keys()) if plf else ["window"])
write_csv(
    OUT_DIR / "position_lifecycle_invalid_reasons.csv",
    invalid_rows,
    list(invalid_rows[0].keys()) if invalid_rows else ["window", "invalid_reason", "count"],
)

# Materializer audit
mat = []
run_rows = q(
    cur,
    """
    select run_id, horizon, count(*) as row_count, min(created_at) as min_created_at, max(created_at) as max_created_at,
           sum(case when length(coalesce(invalid_reason,''))=0 then 1 else 0 end) as completed_count
    from shadow_position_lifecycle_proof_v2
    group by run_id, horizon
    order by run_id desc, horizon
    """,
)
for r in run_rows:
    dup = q1(
        cur,
        """
        select count(*) as c from (
          select position_id, horizon, count(*) as n
          from shadow_position_lifecycle_proof_v2
          where run_id=%s
          group by position_id, horizon
          having count(*) > 1
        ) t
        """,
        (r["run_id"],),
    )["c"]
    mat.append(
        {
            "run_id": r["run_id"],
            "horizon": r["horizon"],
            "row_count": r["row_count"],
            "completed_count": int(r["completed_count"] or 0),
            "min_created_at": str(r["min_created_at"]),
            "max_created_at": str(r["max_created_at"]),
            "duplicate_position_horizon_count": dup,
        }
    )
write_csv(OUT_DIR / "materializer_health_audit.csv", mat, list(mat[0].keys()) if mat else ["run_id", "horizon"])

# Root cause classification
root_causes = []
f24 = next((r for r in fr if r["table_name"] == "shadow_decision_trace"), None)
pm24 = next((r for r in fr if r["table_name"] == "shadow_position_marks"), None)
pos24 = next((r for r in fr if r["table_name"] == "positions"), None)
proof24 = next((r for r in fr if r["table_name"] == "shadow_position_lifecycle_proof_v2"), None)
fun24 = next((r for r in funnel if r["window"] == "recent_24h"), None)
pl24 = next((r for r in plf if r["window"] == "recent_24h"), None)
if (f24 and (f24["rows_last_24h"] or 0) == 0 and pos24 and (pos24["rows_last_24h"] or 0) == 0 and pm24 and (pm24["rows_last_24h"] or 0) == 0):
    root_causes.append({"root_cause": "SHADOW_DB_WRITES_STALE", "table": "shadow_decision_trace/positions/shadow_position_marks", "metric": "rows_last_24h", "time_window": "24h", "observed_value": "0/0/0"})
elif fun24 and (fun24["trace_count"] or 0) == 0:
    root_causes.append({"root_cause": "NO_NEW_MARKET_EVENTS", "table": "shadow_decision_trace", "metric": "trace_count", "time_window": "24h", "observed_value": fun24["trace_count"]})
if fun24 and (fun24["trace_count"] or 0) > 0 and (fun24["selected_count"] or 0) == 0:
    root_causes.append({"root_cause": "DECISION_TRACE_EXISTS_BUT_NO_SELECTED", "table": "shadow_decision_trace", "metric": "selected_count", "time_window": "24h", "observed_value": fun24["selected_count"]})
if fun24 and (fun24["selected_count"] or 0) > 0 and (fun24["intent_open_count"] or 0) == 0:
    root_causes.append({"root_cause": "SELECTED_EXISTS_BUT_NO_INTENT_OPEN", "table": "shadow_decision_trace", "metric": "intent_open_count", "time_window": "24h", "observed_value": fun24["intent_open_count"]})
if fun24 and (fun24["intent_open_count"] or 0) > 0 and pos24 and (pos24["rows_last_24h"] or 0) == 0:
    root_causes.append({"root_cause": "INTENT_OPEN_EXISTS_BUT_NO_POSITION", "table": "positions", "metric": "rows_last_24h", "time_window": "24h", "observed_value": pos24["rows_last_24h"]})
if pl24 and (pl24["new_position_count"] or 0) > 0 and (pl24["position_with_future_24h_mark_count"] or 0) == 0:
    root_causes.append({"root_cause": "POSITIONS_EXIST_BUT_NO_FUTURE_MARKS", "table": "shadow_position_lifecycle_proof_v2", "metric": "position_with_future_24h_mark_count", "time_window": "24h", "observed_value": pl24["position_with_future_24h_mark_count"]})
if pos24 and (pos24["rows_last_24h"] or 0) > 0 and proof24 and (proof24["rows_last_24h"] or 0) == 0:
    root_causes.append({"root_cause": "FUTURE_MARKS_EXIST_BUT_MATERIALIZER_MISSES", "table": "shadow_position_lifecycle_proof_v2", "metric": "rows_last_24h", "time_window": "24h", "observed_value": proof24["rows_last_24h"]})
if pl24 and (pl24["new_position_count"] or 0) > 0 and (pl24["position_with_future_24h_mark_count"] or 0) < (pl24["new_position_count"] or 0):
    root_causes.append({"root_cause": "HORIZONS_NOT_MATURE_YET", "table": "shadow_position_lifecycle_proof_v2", "metric": "future_24h_coverage", "time_window": "24h", "observed_value": f"{pl24['position_with_future_24h_mark_count']}/{pl24['new_position_count']}"})
if not root_causes:
    root_causes.append({"root_cause": "UNKNOWN", "table": "n/a", "metric": "n/a", "time_window": "24h", "observed_value": "n/a"})

write_md(OUT_DIR / "DB_WRITE_FRESHNESS_CN.md", "# DB Write Freshness\n\n" + "\n".join([f"- `{r['table_name']}` total={r['total_rows']} latest={r['latest_timestamp']} 2h={r['rows_last_2h']} 6h={r['rows_last_6h']} 12h={r['rows_last_12h']} 24h={r['rows_last_24h']} 48h={r['rows_last_48h']} status={r['freshness_status']}" for r in fr]) + "\n")
write_md(OUT_DIR / "DECISION_TRACE_SELECTION_FUNNEL_CN.md", "# Decision Trace Selection Funnel\n\n" + "\n".join([f"- `{r['window']}` trace={r['trace_count']} filtered={r['candidate_filtered_count']} selected={r['selected_count']} intent_open={r['intent_open_count']} open_or_reuse={r['open_or_reuse_count']} pools={r['unique_pool_count']} avg_score={r['avg_score']} max_score={r['max_score']}" for r in funnel]) + "\n")
write_md(OUT_DIR / "POSITION_LIFECYCLE_FRESHNESS_CN.md", "# Position Lifecycle Freshness\n\n" + "\n".join([f"- `{r['window']}` new_positions={r['new_position_count']} with_marks={r['position_with_marks_count']} future_6h={r['position_with_future_6h_mark_count']} future_12h={r['position_with_future_12h_mark_count']} future_24h={r['position_with_future_24h_mark_count']} no_future={r['position_without_future_mark_count']}" for r in plf]) + "\n")
write_md(OUT_DIR / "MATERIALIZER_HEALTH_AUDIT_CN.md", "# Materializer Health Audit\n\n" + "\n".join([f"- run_id=`{r['run_id']}` horizon=`{r['horizon']}` row_count={r['row_count']} completed={r['completed_count']} dup={r['duplicate_position_horizon_count']} created_at=[{r['min_created_at']} .. {r['max_created_at']}]" for r in mat[:12]]) + "\n")
write_md(OUT_DIR / "OOS_FLAT_ROOT_CAUSE_CN.md", "# OOS Flat Root Cause\n\n" + "\n".join([f"- `{r['root_cause']}` table={r['table']} metric={r['metric']} window={r['time_window']} observed={r['observed_value']}" for r in root_causes]) + "\n")

recommended = "CONTINUE_OOS_ACCUMULATION"
if any(r["root_cause"] == "SHADOW_DB_WRITES_STALE" for r in root_causes):
    recommended = "SHADOW_DAEMON_RECOVERY_REQUIRED"
elif any(r["root_cause"] == "DECISION_TRACE_EXISTS_BUT_NO_SELECTED" for r in root_causes) or any(r["root_cause"] == "SELECTED_EXISTS_BUT_NO_INTENT_OPEN" for r in root_causes):
    recommended = "SHADOW_SELECTOR_GATE_REVIEW"
elif any(r["root_cause"] == "POSITIONS_EXIST_BUT_NO_FUTURE_MARKS" for r in root_causes):
    recommended = "SHADOW_MARK_COVERAGE_FIX"
elif any(r["root_cause"] == "FUTURE_MARKS_EXIST_BUT_MATERIALIZER_MISSES" for r in root_causes):
    recommended = "MATERIALIZER_FIX"
elif any(r["root_cause"] == "HORIZONS_NOT_MATURE_YET" for r in root_causes):
    recommended = "EXTEND_SHADOW_RUNTIME"

next_json = {"recommended_next_stage": recommended, "root_cause": [r["root_cause"] for r in root_causes]}
(OUT_DIR / "next_action_decision.json").write_text(json.dumps(next_json, indent=2))
write_md(OUT_DIR / "NEXT_ACTION_DECISION_CN.md", "# Next Action Decision\n\n- recommended_next_stage: `" + recommended + "`\n- basis:\n" + "\n".join([f"  - `{r['root_cause']}`" for r in root_causes]) + "\n")

final = {
    "status": "PASS",
    "stage": "FIXED_HORIZON_OOS_ACCUMULATION_HEALTH_DIAGNOSIS_V1",
    "data_source": "vps_postgres",
    "db_ready": True,
    "shadow_daemon_running": False,
    "db_writes_fresh": any(r["freshness_status"] == "HEALTHY" and r["table_name"] == "shadow_decision_trace" for r in fr),
    "decision_trace_rows_last_24h": next((r["rows_last_24h"] for r in fr if r["table_name"] == "shadow_decision_trace"), 0),
    "selected_rows_last_24h": next((r["selected_count"] for r in funnel if r["window"] == "recent_24h"), 0),
    "intent_open_rows_last_24h": next((r["intent_open_count"] for r in funnel if r["window"] == "recent_24h"), 0),
    "new_positions_last_24h": next((r["new_position_count"] for r in plf if r["window"] == "recent_24h"), 0),
    "future_marks_coverage_status": "LOW_24H" if next((r["position_with_future_24h_mark_count"] for r in plf if r["window"] == "recent_24h"), 0) < next((r["new_position_count"] for r in plf if r["window"] == "recent_24h"), 0) else "OK",
    "materializer_status": "HEALTHY" if proof24 and (proof24["rows_last_24h"] or 0) > 0 else "STALE",
    "root_cause": [r["root_cause"] for r in root_causes],
    "edge_proven": "no",
    "tiny_canary_candidate": "no",
    "tiny_canary_allowed": "no",
    "recommended_next_stage": recommended,
}
(OUT_DIR / "oos_flat_root_cause.json").write_text(json.dumps({"root_cause": root_causes}, indent=2))
(OUT_DIR / "FINAL_VERDICT.json").write_text(json.dumps(final, indent=2))
write_md(
    OUT_DIR / "ONEPAGE_CN.md",
    "# One Page\n\n"
    + f"- data_source = vps_postgres\n"
    + f"- db_ready = yes\n"
    + f"- shadow_daemon_running = see process audit\n"
    + f"- db_writes_fresh = {str(final['db_writes_fresh']).lower()}\n"
    + f"- decision_trace_rows_last_24h = {final['decision_trace_rows_last_24h']}\n"
    + f"- selected_rows_last_24h = {final['selected_rows_last_24h']}\n"
    + f"- intent_open_rows_last_24h = {final['intent_open_rows_last_24h']}\n"
    + f"- new_positions_last_24h = {final['new_positions_last_24h']}\n"
    + f"- future_marks_coverage_status = {final['future_marks_coverage_status']}\n"
    + f"- materializer_status = {final['materializer_status']}\n"
    + f"- root_cause = {', '.join(final['root_cause'])}\n"
    + f"- recommended_next_stage = {recommended}\n"
    + f"- tiny_canary_allowed = no\n"
)
write_md(
    OUT_DIR / "ARTIFACT_INDEX.md",
    "# Artifact Index\n\n"
    "- SHADOW_PROCESS_HEALTH_CN.md\n"
    "- DB_WRITE_FRESHNESS_CN.md\n"
    "- db_write_freshness.csv\n"
    "- DECISION_TRACE_SELECTION_FUNNEL_CN.md\n"
    "- decision_trace_selection_funnel.csv\n"
    "- decision_trace_latest_reason_top.csv\n"
    "- POSITION_LIFECYCLE_FRESHNESS_CN.md\n"
    "- position_lifecycle_freshness.csv\n"
    "- position_lifecycle_invalid_reasons.csv\n"
    "- MATERIALIZER_HEALTH_AUDIT_CN.md\n"
    "- materializer_health_audit.csv\n"
    "- OOS_FLAT_ROOT_CAUSE_CN.md\n"
    "- oos_flat_root_cause.json\n"
    "- NEXT_ACTION_DECISION_CN.md\n"
    "- next_action_decision.json\n"
    "- FINAL_VERDICT.json\n"
    "- ONEPAGE_CN.md\n"
)

cur.close()
conn.close()
