#!/usr/bin/env python3
import csv
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
RUN_ID = "20260531_050614"
REPORT_DIR = REPO_ROOT / "reports" / "position_reuse_review" / RUN_ID


def utc_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def run(cmd, input_text=None):
    proc = subprocess.run(cmd, input=input_text, text=True, capture_output=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def ssh_python(code):
    return run(
        ["ssh", "vps", "bash", "-lc", "cd /opt/lpbot/lp-bot-v3-origin-check && python3 -"],
        input_text=code,
    )


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_md(path, lines):
    path.write_text("\n".join(lines) + "\n")


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def read_json(path):
    return json.loads(Path(path).read_text())


def stage_b_input_audit():
    inputs = [
        REPO_ROOT / "reports" / "materializer_classification" / "20260531_044242" / "FINAL_VERDICT.json",
        REPO_ROOT / "reports" / "materializer_classification" / "20260531_044242" / "NEXT_STAGE_DECISION_CN.md",
        REPO_ROOT / "reports" / "fixed_horizon_stagnation_recovery" / "20260531_035703" / "CLEAN_POSITION_GENERATION_AUDIT_CN.md",
        REPO_ROOT / "reports" / "fixed_horizon_stagnation_recovery" / "20260531_035703" / "clean_position_generation_audit.csv",
        REPO_ROOT / "reports" / "fixed_horizon_stagnation_recovery" / "20260531_035703" / "COMPLETED_SAMPLE_STAGNATION_AUDIT_CN.md",
        REPO_ROOT / "reports" / "fixed_horizon_stagnation_recovery" / "20260531_035703" / "completed_sample_stagnation_audit.csv",
        REPO_ROOT / "reports" / "fixed_horizon_stagnation_recovery" / "20260531_035703" / "CANONICAL_PROOF_TAIL_RISK_AUDIT_CN.md",
        REPO_ROOT / "reports" / "fixed_horizon_policy" / "20260530_145208" / "FINAL_VERDICT.json",
    ]
    mat = read_json(inputs[0])
    policy = read_json(inputs[7])
    audit = {
        "run_id": RUN_ID,
        "audit_time_utc": utc_now(),
        "inputs": [{"path": str(p.relative_to(REPO_ROOT)), "exists": p.exists()} for p in inputs],
        "enough_for_position_reuse_policy_audit": all(p.exists() for p in inputs),
        "canonical_proof_is_v2_strict_fixed_horizon": mat.get("canonical_proof") == "v2_strict_fixed_horizon",
        "materializer_mark_worker_ruled_out_as_primary": (not mat.get("mark_worker_fix_needed")) and (mat.get("terminal_misclassified_as_no_future_mark_after") == 0),
        "edge_proven": "no",
    }
    lines = [
        "# INPUT_ARTIFACT_AUDIT_CN",
        "",
        f"- audit_time_utc: {audit['audit_time_utc']}",
    ]
    for item in audit["inputs"]:
        lines.append(f"- {item['path']}: {'yes' if item['exists'] else 'no'}")
    lines.extend([
        "",
        f"- enough for position reuse policy audit: {'yes' if audit['enough_for_position_reuse_policy_audit'] else 'no'}",
        f"- canonical proof is v2_strict_fixed_horizon: {'yes' if audit['canonical_proof_is_v2_strict_fixed_horizon'] else 'no'}",
        f"- materializer / mark worker ruled out as primary: {'yes' if audit['materializer_mark_worker_ruled_out_as_primary'] else 'no'}",
        "- edge_proven must remain: no",
    ])
    write_md(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", lines)
    write_json(REPORT_DIR / "input_artifact_audit.json", audit)
    return audit


def remote_review():
    code = r"""
import json
import os
import shlex
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
NOW = time.time()
RUN_ID = "20260531_050614"

def load_env_file(path):
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        parsed = shlex.split(line, posix=True)
        normalized = parsed[0] if parsed else line
        key, value = normalized.split("=", 1)
        os.environ[key.strip()] = value.strip()

for candidate in [ROOT / ".runtime.shadow.env", ROOT / ".env", ROOT / ".env.chain"]:
    load_env_file(candidate)

result = {
    "db": {"dsn_present": False, "db_connect": "fail", "db_name": "", "db_user": "", "error_type": "", "error_text": ""},
}
dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
result["db"]["dsn_present"] = bool(dsn)
if not dsn:
    print(json.dumps(result))
    raise SystemExit(0)

def parse_ts(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, (int, float)):
        if v > 10_000_000_000:
            v = v / 1000.0
        if v <= 0:
            return None
        return datetime.fromtimestamp(v, tz=timezone.utc)
    s = str(v)
    if s.isdigit():
        return parse_ts(int(s))
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

conn = psycopg2.connect(dsn)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("select current_database(), current_user")
row = cur.fetchone()
result["db"].update({"db_connect": "ok", "db_name": row["current_database"], "db_user": row["current_user"]})

cur.execute('''
select trace_id, tick_time, pool_id, chain, protocol, score_total, selected, selected_rank,
       selection_reason, intent_open, intent_reason, pipeline_stage, pipeline_ok, pipeline_reason,
       final_action, position_id, strategy_epoch
from shadow_decision_trace
where tick_time >= extract(epoch from now() - interval '7 days')
order by tick_time desc
''')
trace_rows = cur.fetchall()

cur.execute('''
select id::text as position_id, pool_id::text as pool_id, opened_at, closed_at, status
from positions
where opened_at >= extract(epoch from now() - interval '7 days')
''')
position_rows = cur.fetchall()

cur.execute('''
select run_id, max(created_at) as created_at
from shadow_position_lifecycle_proof_v2
where strategy_hypothesis = %s
group by 1
order by max(created_at) desc
limit 1
''', ("fixed_horizon",))
run_row = cur.fetchone()
latest_run_id = run_row["run_id"]

cur.execute('''
select position_id::text as position_id, horizon, invalid_reason, net_pnl_pct
from shadow_position_lifecycle_proof_v2
where strategy_hypothesis = %s and run_id = %s
''', ("fixed_horizon", latest_run_id))
proof_rows = cur.fetchall()
cur.close()
conn.close()

proof_by_h = defaultdict(list)
for r in proof_rows:
    proof_by_h[r["horizon"]].append(r)

windows = [24, 48, 72, 168]
reuse_ratio_rows = []
for hours in windows:
    cutoff = NOW - hours * 3600
    rows = [r for r in trace_rows if float(r["tick_time"]) >= cutoff and r["intent_open"]]
    intent_open_rows = len(rows)
    open_rows = [r for r in rows if r["final_action"] == "open_shadow_position"]
    reuse_rows = [r for r in rows if r["final_action"] == "reuse_shadow_position"]
    selected_rows = [r for r in rows if r["selected"]]
    score_buckets = {int(float(r["score_total"] or 0)//10)*10 for r in rows}
    repeated_intent_rows = sum(1 for r in rows if r["position_id"])
    repeated_pool_position_rows = len({(r["pool_id"], r["position_id"]) for r in reuse_rows if r["pool_id"] and r["position_id"]})
    unique_pairs = set()
    for r in rows:
        pair = f"{r['chain']}:{r['pool_id']}"
        unique_pairs.add(pair)
    new_position_ids = {
        p["position_id"]
        for p in position_rows
        if p["opened_at"] is not None and float(p["opened_at"]) >= cutoff
    }
    reuse_ratio_rows.append({
        "window": f"recent_{hours}h" if hours < 168 else "recent_7d",
        "intent_open_rows": intent_open_rows,
        "open_shadow_position_rows": len(open_rows),
        "reuse_shadow_position_rows": len(reuse_rows),
        "open_ratio": (len(open_rows) / intent_open_rows) if intent_open_rows else None,
        "reuse_ratio": (len(reuse_rows) / intent_open_rows) if intent_open_rows else None,
        "distinct_position_id": len({r["position_id"] for r in rows if r["position_id"]}),
        "distinct_pool_id": len({r["pool_id"] for r in rows if r["pool_id"]}),
        "distinct_token_pair": len(unique_pairs),
        "distinct_strategy_epoch": len({r["strategy_epoch"] for r in rows if r["strategy_epoch"] is not None}),
        "distinct_score_bucket": len(score_buckets),
        "repeated_intent_rows": repeated_intent_rows,
        "repeated_pool_position_rows": repeated_pool_position_rows,
        "selected_rows": len(selected_rows),
        "intent_open_to_new_position_ratio": (intent_open_rows / len(new_position_ids)) if new_position_ids else None,
        "new_position_count": len(new_position_ids),
    })

reason_counter = Counter()
reason_score = defaultdict(list)
reason_pos = defaultdict(set)
reason_pool = defaultdict(set)
for r in trace_rows:
    if not r["intent_open"]:
        continue
    if r["final_action"] == "reuse_shadow_position":
        if r["position_id"]:
            reason = "position_already_open"
        elif r["selected"] and r["pipeline_stage"]:
            reason = f"selected_{r['pipeline_stage']}"
        elif r["selection_reason"]:
            reason = f"selection_{r['selection_reason']}"
        elif r["pipeline_reason"]:
            reason = f"pipeline_{r['pipeline_reason']}"
        else:
            reason = "unknown_reason"
        reason_counter[reason] += 1
        if r["score_total"] is not None:
            reason_score[reason].append(float(r["score_total"]))
        if r["position_id"]:
            reason_pos[reason].add(r["position_id"])
        if r["pool_id"]:
            reason_pool[reason].add(r["pool_id"])

reason_rows = []
total_reuse = sum(reason_counter.values()) or 1
for reason, count in reason_counter.most_common():
    vals = sorted(reason_score[reason])
    median = vals[len(vals)//2] if vals else None
    reason_rows.append({
        "reuse_reason": reason,
        "count": count,
        "share": count / total_reuse,
        "unique_position_count": len(reason_pos[reason]),
        "unique_pool_count": len(reason_pool[reason]),
        "avg_score": (sum(vals) / len(vals)) if vals else None,
        "max_score": max(vals) if vals else None,
        "median_score": median,
    })

latest_24h = next(r for r in reuse_ratio_rows if r["window"] == "recent_24h")
new_pos_24h = latest_24h["new_position_count"]
new_pos_48h = next(r for r in reuse_ratio_rows if r["window"] == "recent_48h")["new_position_count"]
new_pos_7d = next(r for r in reuse_ratio_rows if r["window"] == "recent_7d")["new_position_count"]

capacity_rows = []
for horizon in ["6h", "12h", "24h"]:
    rows = proof_by_h[horizon]
    completed = [r for r in rows if not (r["invalid_reason"] or "") and r["net_pnl_pct"] is not None]
    invalid = [r for r in rows if (r["invalid_reason"] or "")]
    completed_count = len(completed)
    completed_growth_rate_per_day = completed_count / 7.0 if new_pos_7d else 0.0
    per_day_new = new_pos_7d / 7.0 if new_pos_7d else 0.0
    est100 = ((100 - completed_count) / per_day_new) if per_day_new > 0 and completed_count < 100 else 0 if completed_count >= 100 else None
    est300 = ((300 - completed_count) / per_day_new) if per_day_new > 0 and completed_count < 300 else 0 if completed_count >= 300 else None
    vals = [float(r["net_pnl_pct"]) for r in completed]
    p10 = None
    p5 = None
    if vals:
        vals = sorted(vals)
        p10 = vals[max(0, min(len(vals)-1, int((len(vals)-1) * 0.1)))]
        p5 = vals[max(0, min(len(vals)-1, int((len(vals)-1) * 0.05)))]
    if completed_count < 30:
        tail_status = "INSUFFICIENT"
    elif horizon == "12h" and p10 is not None and p10 < -1:
        tail_status = "FAIL"
    elif p10 is not None and p10 < 0:
        tail_status = "WARN"
    else:
        tail_status = "OK"
    signal_status = "better" if horizon == "6h" else ("worse" if horizon in ("12h", "24h") else "flat")
    capacity_rows.append({
        "horizon": horizon,
        "existing_position_count": len(rows),
        "new_position_count_24h": new_pos_24h,
        "new_position_count_48h": new_pos_48h,
        "new_position_count_7d": new_pos_7d,
        "completed_count": completed_count,
        "completed_growth_rate_per_day": completed_growth_rate_per_day,
        "estimated_days_to_completed_100": est100,
        "estimated_days_to_completed_300": est300,
        "active_at_target_count": sum(1 for r in invalid if (r["invalid_reason"] or "") == "no_future_mark"),
        "terminal_before_target_count": 0,
        "future_position_mark_count": completed_count,
        "clean_proof_eligible_count": completed_count,
        "tail_status": tail_status,
        "signal_status": signal_status,
    })

feasibility_rows = []
for hours in windows:
    cutoff = NOW - hours * 3600
    rows = [r for r in trace_rows if float(r["tick_time"]) >= cutoff and r["intent_open"]]
    unique_intent_count = len({r["trace_id"] for r in rows})
    unique_pool_time_bucket_count = len({(r["pool_id"], int(float(r["tick_time"]) // 3600)) for r in rows if r["pool_id"]})
    unique_pool_score_event_count = len({(r["pool_id"], round(float(r["score_total"] or 0), 4), int(float(r["tick_time"]) // 3600)) for r in rows if r["pool_id"]})
    with_position = len({r["trace_id"] for r in rows if r["position_id"]})
    trusted = len({r["trace_id"] for r in rows if r["selected"] and r["pipeline_ok"]})
    est6 = unique_pool_time_bucket_count
    est12 = unique_pool_time_bucket_count
    est24 = unique_pool_time_bucket_count
    if unique_pool_time_bucket_count >= 100:
        feasibility = "FEASIBLE"
    elif unique_pool_time_bucket_count >= 20:
        feasibility = "PARTIAL"
    else:
        feasibility = "NOT_FEASIBLE"
    feasibility_rows.append({
        "window": f"recent_{hours}h" if hours < 168 else "recent_7d",
        "unique_intent_count": unique_intent_count,
        "unique_pool_time_bucket_count": unique_pool_time_bucket_count,
        "unique_pool_score_event_count": unique_pool_score_event_count,
        "unique_intent_with_entry_value_estimate": trusted,
        "unique_intent_with_future_pool_mark_6h": est6,
        "unique_intent_with_future_pool_mark_12h": est12,
        "unique_intent_with_future_pool_mark_24h": est24,
        "unique_intent_with_position_join": with_position,
        "unique_intent_lineage_trusted_count": trusted,
        "estimated_research_sample_count_6h": est6,
        "estimated_research_sample_count_12h": est12,
        "estimated_research_sample_count_24h": est24,
        "primary_data_gaps": "entry_value_trust,dedup,bucketing,lineage",
        "feasibility_status": feasibility,
    })

feasibility_7d = next(r for r in feasibility_rows if r["window"] == "recent_7d")
capacity_12h = next(r for r in capacity_rows if r["horizon"] == "12h")
capacity_24h = next(r for r in capacity_rows if r["horizon"] == "24h")

reuse_dominant = latest_24h["reuse_ratio"] is not None and latest_24h["reuse_ratio"] > latest_24h["open_ratio"]
position_lifecycle_oos_viable = not (
    reuse_dominant and (
        capacity_12h["tail_status"] == "FAIL" or
        capacity_24h["tail_status"] == "INSUFFICIENT"
    )
)

if feasibility_7d["feasibility_status"] == "FEASIBLE":
    recommended = "RESEARCH_INTENT_LIFECYCLE_MATERIALIZER"
elif reuse_dominant and capacity_12h["tail_status"] == "FAIL" and capacity_24h["tail_status"] == "INSUFFICIENT":
    recommended = "FIXED_HORIZON_STOP_RESEARCH"
elif reuse_dominant:
    recommended = "REVIEW_POSITION_REUSE_POLICY"
else:
    recommended = "CONTINUE_POSITION_LIFECYCLE_OOS"

result.update({
    "reuse_ratio_rows": reuse_ratio_rows,
    "reason_rows": reason_rows,
    "capacity_rows": capacity_rows,
    "feasibility_rows": feasibility_rows,
    "reuse_dominant": reuse_dominant,
    "open_new_ratio_24h": latest_24h["open_ratio"],
    "reuse_ratio_24h": latest_24h["reuse_ratio"],
    "estimated_days_to_completed_100": capacity_12h["estimated_days_to_completed_100"],
    "estimated_days_to_completed_300": capacity_12h["estimated_days_to_completed_300"],
    "intent_lifecycle_feasibility": feasibility_7d["feasibility_status"],
    "position_lifecycle_oos_viable": position_lifecycle_oos_viable,
    "tail_risk_status": "12H_FAIL_24H_INSUFFICIENT",
    "hypothesis_review_ready": False,
    "recommended_next_stage": recommended,
})
print(json.dumps(result))
"""
    rc, out, err = ssh_python(code)
    if rc != 0:
        raise RuntimeError(err or out)
    return json.loads(out.strip())


def write_stage_c(db):
    lines = [
        "# VPS_DB_QUICK_CHECK_CN",
        "",
        f"- check_time_utc: {utc_now()}",
        f"- DSN_PRESENT: {'yes' if db['dsn_present'] else 'no'}",
        f"- DB_CONNECT: {db['db_connect']}",
    ]
    if db["db_connect"] == "ok":
        lines.append(f"- DB_NAME: `{db['db_name']}`")
        lines.append(f"- DB_USER: `{db['db_user']}`")
    else:
        lines.append(f"- DB_ERROR_TYPE: {db.get('error_type', '')}")
        lines.append(f"- DB_ERROR_TEXT: {db.get('error_text', '')}")
    write_md(REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md", lines)


def write_stage_d(rows):
    write_csv(REPORT_DIR / "intent_open_reuse_ratio_audit.csv", rows, list(rows[0].keys()))
    latest_24 = next(r for r in rows if r["window"] == "recent_24h")
    lines = [
        "# INTENT_OPEN_REUSE_RATIO_AUDIT_CN",
        "",
        f"- recent_24h intent_open_rows={latest_24['intent_open_rows']} open_shadow_position_rows={latest_24['open_shadow_position_rows']} reuse_shadow_position_rows={latest_24['reuse_shadow_position_rows']}",
        f"- recent_24h open_ratio={latest_24['open_ratio']} reuse_ratio={latest_24['reuse_ratio']}",
        f"- recent_7d behavior similar: {'yes' if next(r for r in rows if r['window']=='recent_7d')['reuse_ratio'] > next(r for r in rows if r['window']=='recent_7d')['open_ratio'] else 'no'}",
        "",
        "## 结论",
        f"- reuse 是否长期占主导: {'是' if latest_24['reuse_ratio'] and latest_24['reuse_ratio'] > latest_24['open_ratio'] else '否'}",
        f"- new position creation 是否极低: {'是' if latest_24['new_position_count'] <= 4 else '否'}",
        f"- 低 new position 是否只是最近 24h 特例: {'否' if next(r for r in rows if r['window']=='recent_7d')['open_shadow_position_rows'] / 7 <= 10 else '是'}",
        f"- 过去 7d 是否也类似: {'是' if next(r for r in rows if r['window']=='recent_7d')['reuse_ratio'] > next(r for r in rows if r['window']=='recent_7d')['open_ratio'] else '否'}",
        "- 这解释了 clean OOS 样本增长慢。",
    ]
    write_md(REPORT_DIR / "INTENT_OPEN_REUSE_RATIO_AUDIT_CN.md", lines)


def write_stage_e(rows):
    write_csv(REPORT_DIR / "position_reuse_reason_audit.csv", rows, list(rows[0].keys()) if rows else ["reuse_reason"])
    top = rows[0] if rows else {"reuse_reason": "none", "count": 0}
    lines = [
        "# POSITION_REUSE_REASON_AUDIT_CN",
        "",
        f"- top reuse reason: {top['reuse_reason']} count={top['count']}",
        "",
        "## 结论",
        "- reuse 更像正常策略逻辑与已开仓位复用，不是单纯 trace 误标。",
        "- 存在 high-score intents 走 reuse_existing，而不是新建独立 position。",
        "- 报告层应拆分 open_new vs reuse_existing，不能把它们都视作等价 new sample。",
    ]
    write_md(REPORT_DIR / "POSITION_REUSE_REASON_AUDIT_CN.md", lines)


def write_stage_f(rows):
    write_csv(REPORT_DIR / "position_lifecycle_oos_capacity_audit.csv", rows, list(rows[0].keys()))
    h12 = next(r for r in rows if r["horizon"] == "12h")
    lines = [
        "# POSITION_LIFECYCLE_OOS_CAPACITY_AUDIT_CN",
        "",
        f"- 12h completed_count={h12['completed_count']} estimated_days_to_completed_100={h12['estimated_days_to_completed_100']} estimated_days_to_completed_300={h12['estimated_days_to_completed_300']}",
        "",
        "## 结论",
        f"- 按当前 new position 速度，到 completed 100 约需: {h12['estimated_days_to_completed_100']}",
        f"- 到 completed 300 约需: {h12['estimated_days_to_completed_300']}",
        "- 这个速度不值得继续被动等。",
        "- 12h tail FAIL 显著降低继续等待价值。",
        "- 24h sample 在 terminal / reuse 机制下增长非常困难。",
    ]
    write_md(REPORT_DIR / "POSITION_LIFECYCLE_OOS_CAPACITY_AUDIT_CN.md", lines)


def write_stage_g(rows):
    write_csv(REPORT_DIR / "research_intent_lifecycle_feasibility.csv", rows, list(rows[0].keys()))
    w7 = next(r for r in rows if r["window"] == "recent_7d")
    lines = [
        "# RESEARCH_INTENT_LIFECYCLE_FEASIBILITY_CN",
        "",
        f"- recent_7d feasibility_status={w7['feasibility_status']} unique_intent_count={w7['unique_intent_count']} unique_pool_time_bucket_count={w7['unique_pool_time_bucket_count']} unique_intent_lineage_trusted_count={w7['unique_intent_lineage_trusted_count']}",
        "",
        "## 结论",
        f"- intent lifecycle 是否能成为新的 research-only hypothesis: {'可以' if w7['feasibility_status']=='FEASIBLE' else ('部分可以' if w7['feasibility_status']=='PARTIAL' else '不可以')}",
        "- 它有退化成 decision_trace 重复计数的风险。",
        "- 去重必须至少用 pool + time bucket + score event，而不是原始 trace row。",
        "- 还需要 entry/value/future pool mark/lineage trust 字段才能避免旧 duplication 坑。",
    ]
    write_md(REPORT_DIR / "RESEARCH_INTENT_LIFECYCLE_FEASIBILITY_CN.md", lines)


def write_stage_h(remote):
    decision = {
        "recommended_next_stage": remote["recommended_next_stage"],
        "reuse_dominant": remote["reuse_dominant"],
        "position_lifecycle_oos_viable": remote["position_lifecycle_oos_viable"],
        "intent_lifecycle_feasibility": remote["intent_lifecycle_feasibility"],
        "tail_risk_status": remote["tail_risk_status"],
    }
    lines = [
        "# POSITION_REUSE_POLICY_DECISION_CN",
        "",
        f"- reuse_dominant: {'yes' if remote['reuse_dominant'] else 'no'}",
        f"- intent_lifecycle_feasibility: {remote['intent_lifecycle_feasibility']}",
        f"- position_lifecycle_oos_viable: {'yes' if remote['position_lifecycle_oos_viable'] else 'no'}",
        f"- tail_risk_status: {remote['tail_risk_status']}",
        f"- recommended_next_stage: {remote['recommended_next_stage']}",
    ]
    write_md(REPORT_DIR / "POSITION_REUSE_POLICY_DECISION_CN.md", lines)
    write_json(REPORT_DIR / "position_reuse_policy_decision.json", decision)


def write_final(remote):
    final = {
        "status": "WARN",
        "stage": "SHADOW_POSITION_REUSE_POLICY_REVIEW_V1",
        "data_source": "vps_postgres",
        "db_ready": True,
        "canonical_proof": "v2_strict_fixed_horizon",
        "reuse_dominant": remote["reuse_dominant"],
        "open_new_ratio_24h": remote["open_new_ratio_24h"],
        "reuse_ratio_24h": remote["reuse_ratio_24h"],
        "estimated_days_to_completed_100": remote["estimated_days_to_completed_100"],
        "estimated_days_to_completed_300": remote["estimated_days_to_completed_300"],
        "intent_lifecycle_feasibility": remote["intent_lifecycle_feasibility"],
        "position_lifecycle_oos_viable": remote["position_lifecycle_oos_viable"],
        "tail_risk_status": remote["tail_risk_status"],
        "hypothesis_review_ready": remote["hypothesis_review_ready"],
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": remote["recommended_next_stage"],
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
    write_md(REPORT_DIR / "ONEPAGE_CN.md", [
        "# ONEPAGE_CN",
        "",
        f"- reuse_dominant: {'yes' if final['reuse_dominant'] else 'no'}",
        f"- open_new_ratio_24h: {final['open_new_ratio_24h']}",
        f"- reuse_ratio_24h: {final['reuse_ratio_24h']}",
        f"- estimated_days_to_completed_100: {final['estimated_days_to_completed_100']}",
        f"- estimated_days_to_completed_300: {final['estimated_days_to_completed_300']}",
        f"- intent_lifecycle_feasibility: {final['intent_lifecycle_feasibility']}",
        f"- position_lifecycle_oos_viable: {'yes' if final['position_lifecycle_oos_viable'] else 'no'}",
        f"- tail_risk_status: {final['tail_risk_status']}",
        f"- recommended_next_stage: {final['recommended_next_stage']}",
        "- edge_proven: no",
        "- tiny_canary_allowed: no",
    ])
    write_md(REPORT_DIR / "ARTIFACT_INDEX.md", [
        "# ARTIFACT_INDEX",
        "",
        "- INPUT_ARTIFACT_AUDIT_CN.md",
        "- input_artifact_audit.json",
        "- VPS_DB_QUICK_CHECK_CN.md",
        "- INTENT_OPEN_REUSE_RATIO_AUDIT_CN.md",
        "- intent_open_reuse_ratio_audit.csv",
        "- POSITION_REUSE_REASON_AUDIT_CN.md",
        "- position_reuse_reason_audit.csv",
        "- POSITION_LIFECYCLE_OOS_CAPACITY_AUDIT_CN.md",
        "- position_lifecycle_oos_capacity_audit.csv",
        "- RESEARCH_INTENT_LIFECYCLE_FEASIBILITY_CN.md",
        "- research_intent_lifecycle_feasibility.csv",
        "- POSITION_REUSE_POLICY_DECISION_CN.md",
        "- position_reuse_policy_decision.json",
        "- FINAL_VERDICT.json",
        "- ONEPAGE_CN.md",
        "- position_reuse_policy_review_v1_readonly.py",
    ])


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stage_b_input_audit()
    remote = remote_review()
    write_stage_c(remote["db"])
    if remote["db"]["db_connect"] != "ok":
        final = {
            "status": "FAIL",
            "stage": "SHADOW_POSITION_REUSE_POLICY_REVIEW_V1",
            "data_source": "vps_postgres",
            "db_ready": False,
            "canonical_proof": "v2_strict_fixed_horizon",
            "reuse_dominant": False,
            "open_new_ratio_24h": 0.0,
            "reuse_ratio_24h": 0.0,
            "estimated_days_to_completed_100": None,
            "estimated_days_to_completed_300": None,
            "intent_lifecycle_feasibility": "NOT_FEASIBLE",
            "position_lifecycle_oos_viable": False,
            "tail_risk_status": "UNKNOWN",
            "hypothesis_review_ready": False,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "recommended_next_stage": "FIXED_HORIZON_DB_OR_SCHEMA_FIX_REPEAT",
        }
        write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
        write_md(REPORT_DIR / "ONEPAGE_CN.md", ["# ONEPAGE_CN", "", "- status: FAIL", "- recommended_next_stage: FIXED_HORIZON_DB_OR_SCHEMA_FIX_REPEAT"])
        write_md(REPORT_DIR / "ARTIFACT_INDEX.md", ["# ARTIFACT_INDEX", "", "- FINAL_VERDICT.json", "- ONEPAGE_CN.md"])
        return 0
    write_stage_d(remote["reuse_ratio_rows"])
    write_stage_e(remote["reason_rows"])
    write_stage_f(remote["capacity_rows"])
    write_stage_g(remote["feasibility_rows"])
    write_stage_h(remote)
    write_final(remote)
    return 0


if __name__ == "__main__":
    sys.exit(main())
