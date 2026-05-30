#!/usr/bin/env python3
import csv
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

RUN_ID = "20260530_142032"
OUT_DIR = Path("/tmp/shadow_health_20260530_142032")
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


dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
if not dsn:
    raise SystemExit("missing dsn")

conn = psycopg2.connect(dsn)
cur = conn.cursor(cursor_factory=RealDictCursor)
now = utc_now()

# Pull current source data
decision_rows = q(
    cur,
    """
    select id, tick_time, trace_id, pool_id::text as pool_id, pool_key,
           score_total, selected, selected_rank, selection_reason,
           intent_open, intent_reason, pipeline_stage, pipeline_reason,
           final_action, coalesce(position_id::text,'') as position_id,
           intended_notional_usd, strategy_epoch
    from shadow_decision_trace
    where to_timestamp(case when tick_time > 1000000000000 then tick_time/1000.0 else tick_time::double precision end) >= %s
    """,
    (now - timedelta(hours=48),),
)
for r in decision_rows:
    r["tick_dt"] = parse_ts(r["tick_time"])

positions = q(
    cur,
    """
    select id::text as position_id, pool_id::text as pool_id, opened_at, closed_at, amount_usd, metadata
    from positions
    where to_timestamp(case when opened_at > 1000000000000 then opened_at/1000.0 else opened_at::double precision end) >= %s
    """,
    (now - timedelta(hours=48),),
)
for p in positions:
    p["open_dt"] = parse_ts(p["opened_at"])
    p["close_dt"] = parse_ts(p["closed_at"])

marks = q(
    cur,
    """
    select position_id::text as position_id, pool_id::text as pool_id, mark_time, source
    from shadow_position_marks
    where to_timestamp(case when mark_time > 1000000000000 then mark_time/1000.0 else mark_time::double precision end) >= %s
    order by mark_time
    """,
    (now - timedelta(hours=72),),
)
for m in marks:
    m["mark_dt"] = parse_ts(m["mark_time"])

latest_run = q1(cur, "select run_id from shadow_position_lifecycle_proof_v2 order by created_at desc limit 1")
run_id = latest_run["run_id"] if latest_run else ""
proof_rows = q(
    cur,
    """
    select run_id, position_id::text as position_id, pool_id::text as pool_id, horizon,
           entry_time, target_time, outcome_time, future_position_mark_exists,
           mark_distance_seconds, data_quality_status, invalid_reason, created_at
    from shadow_position_lifecycle_proof_v2
    where run_id = %s
    """,
    (run_id,),
)
for r in proof_rows:
    r["entry_dt"] = parse_ts(r["entry_time"])
    r["target_dt"] = parse_ts(r["target_time"])
    r["outcome_dt"] = parse_ts(r["outcome_time"])

pos_by_id = {p["position_id"]: p for p in positions}
marks_by_position = defaultdict(list)
marks_by_pool = defaultdict(list)
for m in marks:
    marks_by_position[m["position_id"]].append(m)
    marks_by_pool[m["pool_id"]].append(m)
proof_by_key = {(r["position_id"], r["horizon"]): r for r in proof_rows}

# Stage D: intent_open -> position conversion
funnel_rows = []
reason_distribution = []
dedup_rows = []
intent_root = []

for h in WINDOWS:
    cutoff = now - timedelta(hours=h)
    bucket = [r for r in decision_rows if r["tick_dt"] and r["tick_dt"] >= cutoff]
    intent_rows = [r for r in bucket if r["intent_open"]]
    trace_count = len(bucket)
    selected_count = sum(1 for r in bucket if r["selected"])
    intent_open_count = len(intent_rows)
    open_or_reuse_rows = [r for r in bucket if (r.get("final_action") or "") in ("open", "open_or_reuse", "reuse", "opened")]
    repeated_same_pool_tick = sum(c - 1 for c in Counter((r["pool_id"], r["tick_dt"]) for r in intent_rows).values() if c > 1)
    score_bucket_count = len({int(float(r["score_total"] or 0) // 5) * 5 for r in intent_rows})
    distinct_pools = len({r["pool_id"] for r in intent_rows})
    distinct_pool_keys = len({r["pool_key"] for r in intent_rows if r.get("pool_key")})
    distinct_position_ids = len({r["position_id"] for r in intent_rows if r.get("position_id")})
    position_join_success = sum(1 for r in intent_rows if r.get("position_id") and r["position_id"] in pos_by_id)
    funnel_rows.append(
        {
            "window": f"recent_{h}h",
            "trace_count": trace_count,
            "selected_count": selected_count,
            "intent_open_count": intent_open_count,
            "open_or_reuse_count": len(open_or_reuse_rows),
            "unique_pool_count": len({r["pool_id"] for r in bucket}),
            "unique_position_id_count": distinct_position_ids,
            "unique_intent_key_count": len({(r["pool_id"], r["tick_dt"]) for r in intent_rows}),
            "unique_candidate_key_count": distinct_pool_keys,
            "distinct_intent_pool_count": distinct_pools,
            "repeated_same_pool_same_tick_count": repeated_same_pool_tick,
            "distinct_score_bucket_count": score_bucket_count,
            "position_id_present_count": sum(1 for r in intent_rows if r.get("position_id")),
            "positions_join_success_count": position_join_success,
        }
    )
    reason_counter = Counter()
    for r in intent_rows:
        reason = r.get("final_action") or r.get("intent_reason") or r.get("pipeline_reason") or r.get("selection_reason") or "unknown"
        reason_counter[reason] += 1
    for reason, count in reason_counter.most_common(20):
        reason_distribution.append({"window": f"recent_{h}h", "reason": reason, "count": count})
    dedup_rows.append(
        {
            "window": f"recent_{h}h",
            "intent_open_rows": intent_open_count,
            "distinct_pool_id": distinct_pools,
            "distinct_token_pair": distinct_pools,
            "distinct_score_bucket": score_bucket_count,
            "repeated_same_pool_same_tick_count": repeated_same_pool_tick,
            "repeated_same_intended_position_count": max(0, intent_open_count - distinct_position_ids) if distinct_position_ids else "",
        }
    )

f24 = next(r for r in funnel_rows if r["window"] == "recent_24h")
if f24["intent_open_count"] > 0 and f24["unique_intent_key_count"] < f24["intent_open_count"] * 0.1:
    intent_root.append("INTENT_OPEN_DUPLICATE_TRACE_NOISE")
if f24["positions_join_success_count"] > 0 and f24["positions_join_success_count"] <= 10:
    intent_root.append("POSITION_REUSE_EXPECTED")
if f24["intent_open_count"] > 1000 and f24["positions_join_success_count"] < f24["intent_open_count"] * 0.01:
    intent_root.append("INTENT_OPEN_SEMANTIC_MISLABELED")
if f24["position_id_present_count"] == 0 and f24["intent_open_count"] > 0:
    intent_root.append("POSITION_WRITER_NOT_TRIGGERED")
if not intent_root:
    intent_root.append("UNKNOWN")

write_csv(OUT_DIR / "intent_to_position_conversion_audit.csv", funnel_rows, list(funnel_rows[0].keys()))
write_csv(OUT_DIR / "intent_open_reason_distribution.csv", reason_distribution, list(reason_distribution[0].keys()) if reason_distribution else ["window", "reason", "count"])
write_csv(OUT_DIR / "intent_open_dedup_analysis.csv", dedup_rows, list(dedup_rows[0].keys()))

# Stage E: future mark coverage
coverage_rows = []
invalid_dist = Counter()
horizon_summary = {hz: Counter() for hz in ("6h", "12h", "24h")}

for p in positions:
    pid = p["position_id"]
    pool = p["pool_id"]
    open_dt = p["open_dt"]
    close_dt = p["close_dt"]
    pos_marks = marks_by_position.get(pid, [])
    pool_marks = marks_by_pool.get(pool, [])
    if not open_dt:
        continue
    latest_before = max((m["mark_dt"] for m in pos_marks if m["mark_dt"] and m["mark_dt"] < open_dt), default=None)
    first_after = min((m["mark_dt"] for m in pos_marks if m["mark_dt"] and m["mark_dt"] > open_dt), default=None)
    for hz, hh in (("6h", 6), ("12h", 12), ("24h", 24)):
        target = open_dt + timedelta(hours=hh)
        matured = now >= target
        pos_after_target = [m for m in pos_marks if m["mark_dt"] and m["mark_dt"] >= target]
        nearest_pos = min(pos_after_target, key=lambda m: abs((m["mark_dt"] - target).total_seconds())) if pos_after_target else None
        pool_after_target = [m for m in pool_marks if m["mark_dt"] and m["mark_dt"] >= target]
        nearest_pool = min(pool_after_target, key=lambda m: abs((m["mark_dt"] - target).total_seconds())) if pool_after_target else None
        pr = proof_by_key.get((pid, hz))
        invalid_reason = pr.get("invalid_reason") if pr else ""
        if invalid_reason:
            invalid_dist[(hz, invalid_reason)] += 1
        if matured:
            horizon_summary[hz]["matured_positions"] += 1
        if nearest_pos:
            horizon_summary[hz]["with_future_position_mark"] += 1
        elif nearest_pool:
            horizon_summary[hz]["with_pool_mark_only"] += 1
        elif close_dt and close_dt < target:
            horizon_summary[hz]["terminal_before_target"] += 1
        else:
            horizon_summary[hz]["no_mark"] += 1
        coverage_rows.append(
            {
                "position_id": pid,
                "pool_id": pool,
                "token_pair": pool,
                "open_time": open_dt.isoformat(),
                "close_time": close_dt.isoformat() if close_dt else "",
                "horizon": hz,
                "target_time": target.isoformat(),
                "horizon_matured": matured,
                "latest_mark_before_open": latest_before.isoformat() if latest_before else "",
                "first_mark_after_open": first_after.isoformat() if first_after else "",
                "mark_count_after_open": sum(1 for m in pos_marks if m["mark_dt"] and m["mark_dt"] > open_dt),
                "mark_count_before_target": sum(1 for m in pos_marks if m["mark_dt"] and open_dt < m["mark_dt"] < target),
                "mark_count_after_target": len(pos_after_target),
                "nearest_mark_to_target": nearest_pos["mark_dt"].isoformat() if nearest_pos else "",
                "nearest_pool_mark_to_target": nearest_pool["mark_dt"].isoformat() if nearest_pool else "",
                "mark_distance_seconds": int((nearest_pos["mark_dt"] - target).total_seconds()) if nearest_pos else "",
                "pool_mark_distance_seconds": int((nearest_pool["mark_dt"] - target).total_seconds()) if nearest_pool else "",
                "position_level_mark_exists": bool(nearest_pos),
                "pool_level_mark_exists": bool(nearest_pool),
                "terminal_before_target": bool(close_dt and close_dt < target),
                "materializer_invalid_reason": invalid_reason or "",
            }
        )

future_mark_root = []
for hz in ("6h", "12h", "24h"):
    s = horizon_summary[hz]
    if s["matured_positions"] and s["with_future_position_mark"] == 0 and s["with_pool_mark_only"] > 0:
        future_mark_root.append("POOL_MARK_ONLY")
    if s["matured_positions"] and s["with_future_position_mark"] == 0 and s["with_pool_mark_only"] == 0:
        future_mark_root.append("POSITION_MARK_WORKER_GAP")
if any(horizon_summary[hz]["matured_positions"] == 0 for hz in ("12h", "24h")):
    future_mark_root.append("HORIZON_NOT_MATURE")
if not future_mark_root:
    future_mark_root.append("UNKNOWN")

write_csv(OUT_DIR / "future_mark_coverage_audit.csv", coverage_rows, list(coverage_rows[0].keys()) if coverage_rows else ["position_id"])
fmr = [{"horizon": hz, "invalid_reason": reason, "count": count} for (hz, reason), count in invalid_dist.items()]
write_csv(OUT_DIR / "future_mark_invalid_reason_distribution.csv", fmr, list(fmr[0].keys()) if fmr else ["horizon", "invalid_reason", "count"])

# Stage F: materializer semantics
mat_rows = []
for hz in ("6h", "12h", "24h"):
    hz_rows = [r for r in proof_rows if r["horizon"] == hz]
    invalid = Counter((r.get("invalid_reason") or "") for r in hz_rows)
    nearest_fallback_possible = 0
    pool_mark_only_count = 0
    for r in hz_rows:
        if r.get("invalid_reason") == "no_future_mark":
            pid = r["position_id"]
            pool = r["pool_id"]
            target = r["target_dt"]
            if target:
                pos_after = [m for m in marks_by_position.get(pid, []) if m["mark_dt"] and m["mark_dt"] >= target]
                pool_after = [m for m in marks_by_pool.get(pool, []) if m["mark_dt"] and m["mark_dt"] >= target]
                if pos_after:
                    nearest_fallback_possible += 1
                elif pool_after:
                    pool_mark_only_count += 1
    mat_rows.append(
        {
            "horizon": hz,
            "row_count": len(hz_rows),
            "strict_future_mark_count": sum(1 for r in hz_rows if r.get("future_position_mark_exists")),
            "no_future_mark_count": invalid.get("no_future_mark", 0),
            "horizon_not_mature_count": invalid.get("horizon_not_mature", 0),
            "terminal_before_target_count": sum(1 for r in coverage_rows if r["horizon"] == hz and r["terminal_before_target"]),
            "pool_mark_only_count": pool_mark_only_count,
            "position_mark_outside_window_count": sum(1 for r in hz_rows if r.get("data_quality_status") == "stale_mark"),
            "nearest_mark_fallback_possible_count": nearest_fallback_possible,
            "terminal_excluded_count": sum(1 for r in hz_rows if r.get("data_quality_status") == "terminal_before_horizon"),
        }
    )

materializer_semantics_status = "STRICT_BUT_CONSISTENT"
if any(r["pool_mark_only_count"] > 0 or r["nearest_mark_fallback_possible_count"] > 0 for r in mat_rows):
    materializer_semantics_status = "OVER_STRICT_RESEARCH_FALLBACK_POSSIBLE"

write_csv(OUT_DIR / "materializer_semantics_audit.csv", mat_rows, list(mat_rows[0].keys()) if mat_rows else ["horizon"])

# Stage G repair options
options = [
    {
        "option": "Continue OOS accumulation only",
        "applicable": "yes" if "HORIZON_NOT_MATURE" in future_mark_root and len(intent_root) == 1 and intent_root[0] in ("POSITION_REUSE_EXPECTED", "UNKNOWN") else "no",
        "evidence": "recent positions exist but some horizons may not have matured",
        "risk": "may wait without fixing actual mark gap",
        "recommended": "no",
        "next_stage": "CONTINUE_OOS_ACCUMULATION",
    },
    {
        "option": "Shadow selector / position writer audit",
        "applicable": "yes" if any(x in intent_root for x in ("POSITION_WRITER_NOT_TRIGGERED", "INTENT_OPEN_SEMANTIC_MISLABELED")) else "no",
        "evidence": f"intent_open={f24['intent_open_count']} vs position join success={f24['positions_join_success_count']}",
        "risk": "may inspect writer semantics not mark path",
        "recommended": "yes" if any(x in intent_root for x in ("POSITION_WRITER_NOT_TRIGGERED", "INTENT_OPEN_SEMANTIC_MISLABELED")) else "no",
        "next_stage": "SHADOW_INTENT_POSITION_WRITER_AUDIT",
    },
    {
        "option": "Mark coverage fix",
        "applicable": "yes" if any(x in future_mark_root for x in ("POSITION_MARK_WORKER_GAP", "POOL_MARK_ONLY", "HORIZON_NOT_MATURE")) else "no",
        "evidence": f"recent_24h positions={next((r['new_position_count'] for r in coverage_rows if False), '')}",
        "risk": "may not address intent->position compression",
        "recommended": "yes" if any(x in future_mark_root for x in ("POSITION_MARK_WORKER_GAP", "POOL_MARK_ONLY")) else "no",
        "next_stage": "SHADOW_MARK_COVERAGE_FIX",
    },
    {
        "option": "Materializer semantics fix",
        "applicable": "yes" if materializer_semantics_status == "OVER_STRICT_RESEARCH_FALLBACK_POSSIBLE" else "no",
        "evidence": f"semantics_status={materializer_semantics_status}",
        "risk": "research semantics drift from strict proof",
        "recommended": "yes" if materializer_semantics_status == "OVER_STRICT_RESEARCH_FALLBACK_POSSIBLE" else "no",
        "next_stage": "MATERIALIZER_SEMANTICS_FIX",
    },
    {
        "option": "Add research-only synthetic lifecycle from unique intent",
        "applicable": "yes" if any(x in intent_root for x in ("INTENT_OPEN_SEMANTIC_MISLABELED", "POSITION_WRITER_NOT_TRIGGERED")) else "no",
        "evidence": "many intent_open rows but tiny position creation",
        "risk": "new research proof unit diverges from production positions",
        "recommended": "no",
        "next_stage": "RESEARCH_INTENT_LIFECYCLE_MATERIALIZER",
    },
]
(OUT_DIR / "shadow_sample_accumulation_repair_options.json").write_text(json.dumps(options, indent=2))

# Decide next stage
recommended_next = "CONTINUE_OOS_ACCUMULATION"
if any(x in intent_root for x in ("POSITION_WRITER_NOT_TRIGGERED", "INTENT_OPEN_SEMANTIC_MISLABELED")):
    recommended_next = "SHADOW_INTENT_POSITION_WRITER_AUDIT"
elif materializer_semantics_status == "OVER_STRICT_RESEARCH_FALLBACK_POSSIBLE":
    recommended_next = "MATERIALIZER_SEMANTICS_FIX"
elif any(x in future_mark_root for x in ("POSITION_MARK_WORKER_GAP", "POOL_MARK_ONLY")):
    recommended_next = "SHADOW_MARK_COVERAGE_FIX"
elif "HORIZON_NOT_MATURE" in future_mark_root:
    recommended_next = "CONTINUE_OOS_ACCUMULATION"

next_json = {
    "recommended_next_stage": recommended_next,
    "intent_to_position_root_cause": intent_root,
    "future_mark_root_cause": future_mark_root,
    "materializer_semantics_status": materializer_semantics_status,
}
(OUT_DIR / "next_action_decision.json").write_text(json.dumps(next_json, indent=2))

# markdowns
write_md(
    OUT_DIR / "INTENT_TO_POSITION_CONVERSION_AUDIT_CN.md",
    "# Intent To Position Conversion Audit\n\n"
    + "\n".join(
        f"- `{r['window']}` trace={r['trace_count']} selected={r['selected_count']} intent_open={r['intent_open_count']} open_or_reuse={r['open_or_reuse_count']} unique_intent_keys={r['unique_intent_key_count']} position_id_present={r['position_id_present_count']} positions_join_success={r['positions_join_success_count']}"
        for r in funnel_rows
    )
    + f"\n\n- intent_to_position_root_cause: {', '.join(intent_root)}\n"
)
hz_lines = []
for hz in ("6h", "12h", "24h"):
    s = horizon_summary[hz]
    hz_lines.append(
        f"- `{hz}` matured={s['matured_positions']} future_position_mark={s['with_future_position_mark']} pool_mark_only={s['with_pool_mark_only']} terminal_before_target={s['terminal_before_target']} no_mark={s['no_mark']}"
    )
write_md(
    OUT_DIR / "FUTURE_MARK_COVERAGE_AUDIT_CN.md",
    "# Future Mark Coverage Audit\n\n" + "\n".join(hz_lines) + f"\n\n- future_mark_root_cause: {', '.join(future_mark_root)}\n",
)
write_md(
    OUT_DIR / "MATERIALIZER_SEMANTICS_AUDIT_CN.md",
    "# Materializer Semantics Audit\n\n"
    + "\n".join(
        f"- `{r['horizon']}` strict_future_mark_count={r['strict_future_mark_count']} no_future_mark={r['no_future_mark_count']} pool_mark_only={r['pool_mark_only_count']} nearest_mark_fallback_possible={r['nearest_mark_fallback_possible_count']} terminal_excluded={r['terminal_excluded_count']}"
        for r in mat_rows
    )
    + f"\n\n- materializer_semantics_status: {materializer_semantics_status}\n- research-only nearest-position-mark tolerance possible: {'yes' if materializer_semantics_status == 'OVER_STRICT_RESEARCH_FALLBACK_POSSIBLE' else 'no'}\n",
)
write_md(
    OUT_DIR / "SHADOW_SAMPLE_ACCUMULATION_REPAIR_OPTIONS_CN.md",
    "# Shadow Sample Accumulation Repair Options\n\n"
    + "\n".join(
        f"- `{o['option']}` applicable={o['applicable']} recommended={o['recommended']} next_stage=`{o['next_stage']}` risk={o['risk']}"
        for o in options
    )
    + "\n",
)
write_md(
    OUT_DIR / "NEXT_ACTION_DECISION_CN.md",
    "# Next Action Decision\n\n"
    + f"- recommended_next_stage: `{recommended_next}`\n"
    + f"- intent_to_position_root_cause: {', '.join(intent_root)}\n"
    + f"- future_mark_root_cause: {', '.join(future_mark_root)}\n"
    + f"- materializer_semantics_status: {materializer_semantics_status}\n",
)

final = {
    "status": "PASS",
    "stage": "SHADOW_INTENT_POSITION_AND_MARK_COVERAGE_AUDIT_V1",
    "data_source": "vps_postgres",
    "db_ready": True,
    "intent_open_rows_last_24h": f24["intent_open_count"],
    "new_positions_last_24h": 0,
    "intent_to_position_root_cause": intent_root,
    "future_mark_root_cause": future_mark_root,
    "materializer_semantics_status": materializer_semantics_status,
    "recommended_next_stage": recommended_next,
    "edge_proven": "no",
    "tiny_canary_candidate": "no",
    "tiny_canary_allowed": "no",
}
pl24_unique = len({r["position_id"] for r in coverage_rows if r["horizon"] == "24h" and parse_ts(r["open_time"]) and parse_ts(r["open_time"]) >= now - timedelta(hours=24)})
final["new_positions_last_24h"] = pl24_unique

(OUT_DIR / "FINAL_VERDICT.json").write_text(json.dumps(final, indent=2))
write_md(
    OUT_DIR / "ONEPAGE_CN.md",
    "# One Page\n\n"
    + f"- intent_open_rows_last_24h = {final['intent_open_rows_last_24h']}\n"
    + f"- new_positions_last_24h = {final['new_positions_last_24h']}\n"
    + f"- intent_to_position_root_cause = {', '.join(intent_root)}\n"
    + f"- future_mark_root_cause = {', '.join(future_mark_root)}\n"
    + f"- materializer_semantics_status = {materializer_semantics_status}\n"
    + f"- recommended_next_stage = {recommended_next}\n"
    + "- tiny_canary_allowed = no\n",
)
write_md(
    OUT_DIR / "ARTIFACT_INDEX.md",
    "# Artifact Index\n\n"
    "- INPUT_ARTIFACT_AUDIT_CN.md\n"
    "- VPS_DB_QUICK_CHECK_CN.md\n"
    "- INTENT_TO_POSITION_CONVERSION_AUDIT_CN.md\n"
    "- intent_to_position_conversion_audit.csv\n"
    "- intent_open_reason_distribution.csv\n"
    "- intent_open_dedup_analysis.csv\n"
    "- FUTURE_MARK_COVERAGE_AUDIT_CN.md\n"
    "- future_mark_coverage_audit.csv\n"
    "- future_mark_invalid_reason_distribution.csv\n"
    "- MATERIALIZER_SEMANTICS_AUDIT_CN.md\n"
    "- materializer_semantics_audit.csv\n"
    "- SHADOW_SAMPLE_ACCUMULATION_REPAIR_OPTIONS_CN.md\n"
    "- shadow_sample_accumulation_repair_options.json\n"
    "- NEXT_ACTION_DECISION_CN.md\n"
    "- next_action_decision.json\n"
    "- FINAL_VERDICT.json\n"
    "- ONEPAGE_CN.md\n",
)

cur.close()
conn.close()
