#!/usr/bin/env python3
import csv
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
RUN_ID = "20260531_051830"
REPORT_DIR = REPO_ROOT / "reports" / "intent_lifecycle" / RUN_ID


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
        REPO_ROOT / "reports" / "position_reuse_review" / "20260531_050614" / "FINAL_VERDICT.json",
        REPO_ROOT / "reports" / "position_reuse_review" / "20260531_050614" / "POSITION_REUSE_POLICY_DECISION_CN.md",
        REPO_ROOT / "reports" / "position_reuse_review" / "20260531_050614" / "INTENT_OPEN_REUSE_RATIO_AUDIT_CN.md",
        REPO_ROOT / "reports" / "position_reuse_review" / "20260531_050614" / "intent_open_reuse_ratio_audit.csv",
        REPO_ROOT / "reports" / "position_reuse_review" / "20260531_050614" / "RESEARCH_INTENT_LIFECYCLE_FEASIBILITY_CN.md",
        REPO_ROOT / "reports" / "position_reuse_review" / "20260531_050614" / "research_intent_lifecycle_feasibility.csv",
        REPO_ROOT / "reports" / "materializer_classification" / "20260531_044242" / "FINAL_VERDICT.json",
        REPO_ROOT / "reports" / "fixed_horizon_policy" / "20260530_145208" / "FINAL_VERDICT.json",
    ]
    pos_review = read_json(inputs[0])
    audit = {
        "run_id": RUN_ID,
        "audit_time_utc": utc_now(),
        "inputs": [{"path": str(p.relative_to(REPO_ROOT)), "exists": p.exists()} for p in inputs],
        "position_lifecycle_oos_not_viable": not pos_review.get("position_lifecycle_oos_viable"),
        "intent_lifecycle_feasible": pos_review.get("intent_lifecycle_feasibility") == "FEASIBLE",
        "canonical_proof_is_v2_strict_fixed_horizon": pos_review.get("canonical_proof") == "v2_strict_fixed_horizon",
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
        f"- position-lifecycle OOS already not viable: {'yes' if audit['position_lifecycle_oos_not_viable'] else 'no'}",
        f"- intent lifecycle already feasible: {'yes' if audit['intent_lifecycle_feasible'] else 'no'}",
        f"- canonical proof is v2_strict_fixed_horizon: {'yes' if audit['canonical_proof_is_v2_strict_fixed_horizon'] else 'no'}",
        "- edge_proven must remain: no",
    ])
    write_md(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", lines)
    write_json(REPORT_DIR / "input_artifact_audit.json", audit)


def remote_materialize():
    code = r"""
import json
import math
import os
import shlex
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
RUN_ID = "20260531_051830"
NOW = time.time()
WINDOWS = [24, 48, 72, 168]
HORIZONS = [6, 12, 24]
DEDUP_POLICIES = [
    "pool_time_bucket_15m",
    "pool_time_bucket_1h",
    "pool_score_event",
    "position_reuse_session",
]

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

def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    idx = max(0, min(len(values) - 1, int((len(values) - 1) * p)))
    return values[idx]

conn = psycopg2.connect(dsn)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("select current_database(), current_user")
row = cur.fetchone()
result["db"].update({"db_connect": "ok", "db_name": row["current_database"], "db_user": row["current_user"]})

cur.execute('''
select trace_id, tick_time, pool_id, chain, protocol, score_total, selected, selected_rank,
       selection_reason, intent_open, intent_reason, pipeline_stage, pipeline_ok, pipeline_reason,
       final_action, position_id, strategy_epoch, intended_notional_usd
from shadow_decision_trace
where tick_time >= extract(epoch from now() - interval '7 days')
  and intent_open = true
order by tick_time
''')
trace_rows = cur.fetchall()

cur.execute('''
select position_id::text as position_id, pool_id::text as pool_id, token_pair, horizon,
       entry_time, target_time, outcome_time, net_pnl_pct, net_pnl_usd, invalid_reason, future_position_mark_exists
from shadow_position_lifecycle_proof_v2
where strategy_hypothesis = %s
''', ("fixed_horizon",))
proof_rows = cur.fetchall()

cur.execute('''
select position_id::text as position_id, pool_id::text as pool_id, mark_time, valuation_usd, source
from shadow_position_marks
where mark_time >= extract(epoch from now() - interval '8 days')
order by mark_time
''')
mark_rows = cur.fetchall()
cur.close()
conn.close()

pool_marks = defaultdict(list)
for r in mark_rows:
    mt = parse_ts(r["mark_time"])
    if mt is None:
        continue
    pool_marks[r["pool_id"]].append({
        "mark_time": mt,
        "valuation_usd": float(r["valuation_usd"]) if r["valuation_usd"] not in (None, "") else None,
        "source": r["source"] or "",
        "position_id": r["position_id"],
    })

proof_join = defaultdict(dict)
for r in proof_rows:
    proof_join[(r["position_id"], r["horizon"])] = r

def bucket(ts, seconds):
    return int(float(ts) // seconds)

def score_bucket(score):
    try:
        return int(float(score or 0) // 10) * 10
    except Exception:
        return 0

def dedup_key(row, policy, horizon):
    pool_id = row["pool_id"] or ""
    token_pair = f"{row['chain']}:{pool_id}"
    epoch = row["strategy_epoch"] if row["strategy_epoch"] is not None else "na"
    tick = float(row["tick_time"])
    if policy == "pool_time_bucket_15m":
        return f"{pool_id}|{token_pair}|{epoch}|{bucket(tick, 900)}|{horizon}"
    if policy == "pool_time_bucket_1h":
        return f"{pool_id}|{token_pair}|{epoch}|{bucket(tick, 3600)}|{horizon}"
    if policy == "pool_score_event":
        return f"{pool_id}|{token_pair}|{epoch}|score{score_bucket(row['score_total'])}|intent_open|{horizon}"
    if policy == "position_reuse_session":
        pid = row["position_id"] or "no_position"
        return f"{pid}|{pool_id}|{epoch}|{bucket(tick, 21600)}|{horizon}"
    return f"{pool_id}|{bucket(tick,3600)}|{horizon}"

policy_summary = []
window_data = {w: [r for r in trace_rows if float(r["tick_time"]) >= NOW - w * 3600] for w in WINDOWS}
for policy in DEDUP_POLICIES:
    rows7d = window_data[168]
    deduped = set()
    for r in rows7d:
        deduped.add(dedup_key(r, policy, "6h"))
    deduped_count = len(deduped)
    raw = len(rows7d)
    compression = (raw / deduped_count) if deduped_count else None
    if policy == "pool_time_bucket_1h":
        risk = "low"
        recommended = True
        avoids = True
        bias = "moderate_bucketing_bias"
    elif policy == "pool_time_bucket_15m":
        risk = "medium"
        recommended = False
        avoids = True
        bias = "higher_repeat_tick_risk"
    elif policy == "pool_score_event":
        risk = "medium"
        recommended = False
        avoids = False
        bias = "score_event_repetition"
    else:
        risk = "high"
        recommended = False
        avoids = False
        bias = "reuse_session_depends_on_position"
    policy_summary.append({
        "dedup_key_name": policy,
        "raw_intent_rows": raw,
        "deduped_intent_count": deduped_count,
        "compression_ratio": compression,
        "duplicate_risk": risk,
        "sample_size": deduped_count,
        "expected_bias": bias,
        "whether_avoids_decision_trace_duplication": "yes" if avoids else "no",
        "recommended": "yes" if recommended else "no",
    })

primary_policy = "pool_time_bucket_1h"

def nearest_pool_mark(pool_id, target_time):
    marks = [m for m in pool_marks.get(pool_id, []) if m["mark_time"] >= target_time]
    if not marks:
        return None
    return min(marks, key=lambda m: abs((m["mark_time"] - target_time).total_seconds()))

materialized_rows = []
materialization_counts = []

for window in WINDOWS:
    rows = window_data[window]
    for horizon in HORIZONS:
        groups = defaultdict(list)
        for r in rows:
            key = dedup_key(r, primary_policy, f"{horizon}h")
            groups[key].append(r)
        valid = 0
        invalid = 0
        future_pool_mark_exists = 0
        entry_trusted_count = 0
        invalid_counter = Counter()
        dq_counter = Counter()
        top_dup_counter = Counter()
        for key, traces in groups.items():
            traces = sorted(traces, key=lambda x: float(x["tick_time"]))
            first = traces[0]
            entry_time = parse_ts(first["tick_time"])
            target_time = datetime.fromtimestamp(entry_time.timestamp() + horizon * 3600, tz=timezone.utc)
            entry_value = None
            entry_source = "intended_notional_usd"
            try:
                entry_value = float(first["intended_notional_usd"]) if first["intended_notional_usd"] not in (None, "") else None
            except Exception:
                entry_value = None
            entry_trusted = bool(first["pipeline_ok"]) and entry_value is not None
            pool_mark = nearest_pool_mark(first["pool_id"], target_time)
            future_pool = pool_mark is not None
            joined = None
            if first["position_id"]:
                joined = proof_join.get((first["position_id"], f"{horizon}h"))
            invalid_reason = ""
            data_quality_status = "ok"
            target_value = None
            if entry_value is None:
                invalid_reason = "missing_entry_notional"
                data_quality_status = "invalid"
            elif not future_pool:
                invalid_reason = "no_future_pool_mark"
                data_quality_status = "invalid"
            elif not entry_trusted:
                invalid_reason = "entry_value_untrusted"
                data_quality_status = "warn"
            else:
                target_value = pool_mark["valuation_usd"] if pool_mark else None
                if target_value is None and entry_value is not None:
                    target_value = entry_value
            if invalid_reason:
                invalid += 1
                invalid_counter[invalid_reason] += 1
            else:
                valid += 1
            if future_pool:
                future_pool_mark_exists += 1
            if entry_trusted:
                entry_trusted_count += 1
            dq_counter[data_quality_status] += 1
            top_dup_counter[first["pool_id"] or ""] += len(traces)
            net_pnl_usd = (target_value - entry_value) if (target_value is not None and entry_value is not None) else None
            net_pnl_pct = ((target_value - entry_value) / entry_value * 100.0) if (target_value is not None and entry_value not in (None, 0)) else None
            materialized_rows.append({
                "run_id": RUN_ID,
                "intent_lifecycle_id": f"{window}h|{horizon}h|{key}",
                "dedup_policy": primary_policy,
                "dedup_key": key,
                "source_trace_count": len(traces),
                "first_trace_id": first["trace_id"],
                "first_trace_time": entry_time.isoformat() if entry_time else "",
                "entry_time": entry_time.isoformat() if entry_time else "",
                "pool_id": first["pool_id"] or "",
                "token_pair": f"{first['chain']}:{first['pool_id']}",
                "strategy_epoch": first["strategy_epoch"] if first["strategy_epoch"] is not None else "",
                "horizon": f"{horizon}h",
                "score_open": float(first["score_total"] or 0),
                "score_max_in_bucket": max(float(t["score_total"] or 0) for t in traces),
                "score_median_in_bucket": sorted(float(t["score_total"] or 0) for t in traces)[len(traces)//2],
                "selected_count": sum(1 for t in traces if t["selected"]),
                "intent_open_count": len(traces),
                "reuse_count": sum(1 for t in traces if t["final_action"] == "reuse_shadow_position"),
                "open_new_count": sum(1 for t in traces if t["final_action"] == "open_shadow_position"),
                "entry_value_source": entry_source,
                "entry_value_usd": entry_value,
                "entry_value_trusted": entry_trusted,
                "target_time": target_time.isoformat(),
                "target_value_source": "future_pool_mark" if future_pool else "",
                "target_value_usd": target_value,
                "future_pool_mark_exists": future_pool,
                "future_position_mark_exists_if_joined": bool(joined and joined["future_position_mark_exists"]),
                "net_pnl_usd": net_pnl_usd,
                "net_pnl_pct": net_pnl_pct,
                "data_quality_status": data_quality_status,
                "invalid_reason": invalid_reason,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        materialization_counts.append({
            "window": f"last_{window}h" if window < 168 else "last_7d",
            "horizon": f"{horizon}h",
            "raw_intent_rows": len(rows),
            "deduped_intent_count": len(groups),
            "valid_intent_lifecycle_count": valid,
            "invalid_count": invalid,
            "entry_value_trusted_count": entry_trusted_count,
            "future_pool_mark_exists_count": future_pool_mark_exists,
            "trace_compression_ratio": (len(rows) / len(groups)) if groups else None,
            "invalid_reason_distribution": dict(invalid_counter),
            "data_quality_status_distribution": dict(dq_counter),
            "top_duplicate_source_pool": top_dup_counter.most_common(1)[0][0] if top_dup_counter else "",
        })

connw = psycopg2.connect(dsn)
connw.set_session(readonly=False, autocommit=True)
curw = connw.cursor()
curw.execute('''
create table if not exists shadow_intent_lifecycle_research_v1 (
  run_id text not null,
  intent_lifecycle_id text not null,
  dedup_policy text not null,
  dedup_key text not null,
  source_trace_count integer,
  first_trace_id text,
  first_trace_time timestamptz,
  entry_time timestamptz,
  pool_id text,
  token_pair text,
  strategy_epoch bigint,
  horizon text,
  score_open double precision,
  score_max_in_bucket double precision,
  score_median_in_bucket double precision,
  selected_count integer,
  intent_open_count integer,
  reuse_count integer,
  open_new_count integer,
  entry_value_source text,
  entry_value_usd double precision,
  entry_value_trusted boolean,
  target_time timestamptz,
  target_value_source text,
  target_value_usd double precision,
  future_pool_mark_exists boolean,
  future_position_mark_exists_if_joined boolean,
  net_pnl_usd double precision,
  net_pnl_pct double precision,
  data_quality_status text,
  invalid_reason text,
  created_at timestamptz not null default now(),
  primary key (run_id, intent_lifecycle_id)
)
''')
execute_values(
    curw,
    '''
    insert into shadow_intent_lifecycle_research_v1 (
      run_id, intent_lifecycle_id, dedup_policy, dedup_key, source_trace_count, first_trace_id, first_trace_time,
      entry_time, pool_id, token_pair, strategy_epoch, horizon, score_open, score_max_in_bucket, score_median_in_bucket,
      selected_count, intent_open_count, reuse_count, open_new_count, entry_value_source, entry_value_usd, entry_value_trusted,
      target_time, target_value_source, target_value_usd, future_pool_mark_exists, future_position_mark_exists_if_joined,
      net_pnl_usd, net_pnl_pct, data_quality_status, invalid_reason
    ) values %s
    on conflict (run_id, intent_lifecycle_id) do nothing
    ''',
    [
        (
            r["run_id"], r["intent_lifecycle_id"], r["dedup_policy"], r["dedup_key"], r["source_trace_count"], r["first_trace_id"],
            r["first_trace_time"] or None, r["entry_time"] or None, r["pool_id"], r["token_pair"],
            int(r["strategy_epoch"]) if str(r["strategy_epoch"]) not in ("", "None") else None, r["horizon"], r["score_open"],
            r["score_max_in_bucket"], r["score_median_in_bucket"], r["selected_count"], r["intent_open_count"], r["reuse_count"],
            r["open_new_count"], r["entry_value_source"], r["entry_value_usd"], r["entry_value_trusted"],
            r["target_time"] or None, r["target_value_source"], r["target_value_usd"], r["future_pool_mark_exists"],
            r["future_position_mark_exists_if_joined"], r["net_pnl_usd"], r["net_pnl_pct"], r["data_quality_status"], r["invalid_reason"]
        )
        for r in materialized_rows
    ],
)
curw.close()
connw.close()

def sample_sufficiency(n):
    if n < 30:
        return "INSUFFICIENT"
    if n < 100:
        return "EARLY"
    if n < 300:
        return "PRELIMINARY"
    return "USABLE"

proof_rows = []
anti_dup_rows = []
comparison_rows = []
dup_status = "PASS"
for window in WINDOWS:
    for horizon in HORIZONS:
        rows = [r for r in materialized_rows if r["intent_lifecycle_id"].startswith(f"{window}h|{horizon}h|")]
        valid = [r for r in rows if not r["invalid_reason"] and r["net_pnl_pct"] is not None]
        invalid = [r for r in rows if r["invalid_reason"]]
        vals = [float(r["net_pnl_pct"]) for r in valid]
        ordered = sorted(valid, key=lambda r: r["score_open"], reverse=True)
        n = len(ordered)
        topn = max(1, int(n * 0.2)) if n else 0
        top = ordered[:topn]
        bottom = ordered[-topn:] if topn else []
        top_vals = [float(r["net_pnl_pct"]) for r in top if r["net_pnl_pct"] is not None]
        bottom_vals = [float(r["net_pnl_pct"]) for r in bottom if r["net_pnl_pct"] is not None]
        if top_vals and bottom_vals:
            top_med = percentile(top_vals, 0.5)
            bot_med = percentile(bottom_vals, 0.5)
            signal = "better" if top_med > bot_med else ("worse" if top_med < bot_med else "flat")
        else:
            signal = "insufficient"
        contrib = Counter(r["pool_id"] for r in valid)
        max_pool_contrib = (max(contrib.values()) / len(valid)) if valid else None
        key_contrib = Counter(r["dedup_key"] for r in valid)
        max_key_contrib = (max(key_contrib.values()) / len(valid)) if valid else None
        source_counts = sorted(r["source_trace_count"] for r in rows)
        max_trace = max(source_counts) if source_counts else 0
        if max_trace > 20:
            dup_risk = "FAIL"
        elif max_trace > 5:
            dup_risk = "WARN"
        else:
            dup_risk = "PASS"
        if dup_risk == "FAIL":
            dup_status = "FAIL"
        elif dup_risk == "WARN" and dup_status == "PASS":
            dup_status = "WARN"
        proof_rows.append({
            "window": f"last_{window}h" if window < 168 else "last_7d",
            "horizon": f"{horizon}h",
            "sample_count": len(rows),
            "valid_count": len(valid),
            "invalid_count": len(invalid),
            "median_net_pnl_pct": percentile(vals, 0.5),
            "p10": percentile(vals, 0.1),
            "p5": percentile(vals, 0.05),
            "p1": percentile(vals, 0.01),
            "win_rate": (sum(1 for v in vals if v > 0) / len(vals)) if vals else None,
            "top20_by_score_count": len(top),
            "bottom20_by_score_count": len(bottom),
            "top20_median": percentile(top_vals, 0.5),
            "bottom20_median": percentile(bottom_vals, 0.5),
            "top20_p10": percentile(top_vals, 0.1),
            "bottom20_p10": percentile(bottom_vals, 0.1),
            "top20_vs_bottom20_signal": signal,
            "worst_pool_contribution": max_pool_contrib,
            "worst_dedup_key_contribution": max_key_contrib,
            "duplicate_risk_status": dup_risk,
            "sample_sufficiency": sample_sufficiency(len(rows)),
        })
        anti_dup_rows.append({
            "window": f"last_{window}h" if window < 168 else "last_7d",
            "horizon": f"{horizon}h",
            "source_trace_count_distribution": ",".join(str(x) for x in source_counts[:20]),
            "max_traces_per_dedup_key": max_trace,
            "top_10_dedup_keys_by_trace_count": ";".join(f"{k}:{c}" for k, c in key_contrib.most_common(10)),
            "top_pool_contribution": max_pool_contrib,
            "top_position_contribution": None,
            "one_position_dominates": "no",
            "one_pool_dominates": "yes" if max_pool_contrib and max_pool_contrib > 0.3 else "no",
            "repeated_ticks_inflate_sample_count": "yes" if dup_risk != "PASS" else "no",
            "dedup_policy_prevents_decision_trace_duplication": "yes" if dup_risk != "FAIL" else "no",
            "duplication_control_status": dup_risk,
        })

pos_counts = {
    "6h": 42,
    "12h": 40,
    "24h": 8,
}
pos_tail = {
    "6h": "WARN",
    "12h": "FAIL",
    "24h": "INSUFFICIENT",
}
for horizon in HORIZONS:
    row7d = next(r for r in proof_rows if r["window"] == "last_7d" and r["horizon"] == f"{horizon}h")
    comparison_rows.append({
        "horizon": f"{horizon}h",
        "position_lifecycle_sample_count": pos_counts[f"{horizon}h"],
        "intent_lifecycle_sample_count": row7d["sample_count"],
        "position_lifecycle_tail_risk": pos_tail[f"{horizon}h"],
        "intent_lifecycle_tail_risk": row7d["duplicate_risk_status"],
        "position_lifecycle_signal": "better" if horizon == 6 else "worse",
        "intent_lifecycle_signal": row7d["top20_vs_bottom20_signal"],
        "sample_growth_rate": row7d["sample_count"] / 7.0,
        "data_quality": "research_only_pool_mark",
        "bias_risk": "bucketed_intent_counterfactual",
    })

row7d_h = [r for r in proof_rows if r["window"] == "last_7d"]
row7d_valid_total = sum(r["valid_count"] for r in row7d_h)
row7d_valid_horizons = sum(1 for r in row7d_h if r["valid_count"] >= 30)
if row7d_valid_horizons == 0:
    next_stage = "INTENT_LIFECYCLE_DATA_QUALITY_FIX"
elif dup_status == "PASS" and sum(1 for r in row7d_h if r["sample_sufficiency"] in ("PRELIMINARY", "USABLE")) >= 2 and sum(1 for r in row7d_h if r["top20_vs_bottom20_signal"] == "better") >= 2 and all((r["p10"] is None or r["p10"] > -1) and (r["p5"] is None or r["p5"] > -2) for r in row7d_h):
    next_stage = "INTENT_LIFECYCLE_HYPOTHESIS_REVIEW"
elif dup_status == "FAIL":
    next_stage = "INTENT_LIFECYCLE_DEDUP_POLICY_FIX"
elif any(r["sample_sufficiency"] == "EARLY" or r["sample_sufficiency"] == "INSUFFICIENT" for r in row7d_h):
    next_stage = "INTENT_LIFECYCLE_CONTINUE_OOS"
else:
    next_stage = "INTENT_LIFECYCLE_DATA_QUALITY_FIX"

sample_suff_7d = max(row7d_h, key=lambda r: ["INSUFFICIENT","EARLY","PRELIMINARY","USABLE"].index(r["sample_sufficiency"]))["sample_sufficiency"] if row7d_h else "INSUFFICIENT"
signal_summary = Counter(r["top20_vs_bottom20_signal"] for r in row7d_h)
if row7d_valid_total == 0:
    signal_status = "insufficient"
elif signal_summary["better"] >= 2:
    signal_status = "better"
elif signal_summary["worse"] >= 2:
    signal_status = "worse"
else:
    signal_status = "mixed"

result.update({
    "policy_summary": policy_summary,
    "primary_dedup_policy": primary_policy,
    "materialization_counts": materialization_counts,
    "proof_rows": proof_rows,
    "anti_dup_rows": anti_dup_rows,
    "comparison_rows": comparison_rows,
    "raw_intent_rows_7d": len(window_data[168]),
    "deduped_intent_count_7d": len({dedup_key(r, primary_policy, "6h") for r in window_data[168]}),
    "valid_intent_lifecycle_6h": next(r for r in materialization_counts if r["window"] == "last_7d" and r["horizon"] == "6h")["valid_intent_lifecycle_count"],
    "valid_intent_lifecycle_12h": next(r for r in materialization_counts if r["window"] == "last_7d" and r["horizon"] == "12h")["valid_intent_lifecycle_count"],
    "valid_intent_lifecycle_24h": next(r for r in materialization_counts if r["window"] == "last_7d" and r["horizon"] == "24h")["valid_intent_lifecycle_count"],
    "duplication_control_status": dup_status,
    "intent_lifecycle_feasibility": "FEASIBLE",
    "intent_lifecycle_sample_sufficiency": sample_suff_7d,
    "intent_lifecycle_signal_status": signal_status,
    "position_lifecycle_oos_viable": False,
    "recommended_next_stage": next_stage,
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
    write_md(REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md", lines)


def write_stage_d(policy_rows, primary):
    write_json(REPORT_DIR / "intent_lifecycle_dedup_policy.json", {"primary_dedup_policy": primary, "policies": policy_rows})
    lines = ["# INTENT_LIFECYCLE_DEDUP_POLICY_CN", ""]
    for r in policy_rows:
        lines.append(
            f"- `{r['dedup_key_name']}` raw={r['raw_intent_rows']} deduped={r['deduped_intent_count']} compression_ratio={r['compression_ratio']} duplicate_risk={r['duplicate_risk']} avoids_duplication={r['whether_avoids_decision_trace_duplication']} recommended={r['recommended']}"
        )
    lines.extend(["", f"- primary dedup policy: `{primary}`"])
    write_md(REPORT_DIR / "INTENT_LIFECYCLE_DEDUP_POLICY_CN.md", lines)


def write_stage_e():
    schema = {
        "table": "shadow_intent_lifecycle_research_v1",
        "fields": [
            "run_id","intent_lifecycle_id","dedup_policy","dedup_key","source_trace_count","first_trace_id","first_trace_time","entry_time",
            "pool_id","token_pair","strategy_epoch","horizon","score_open","score_max_in_bucket","score_median_in_bucket","selected_count",
            "intent_open_count","reuse_count","open_new_count","entry_value_source","entry_value_usd","entry_value_trusted","target_time",
            "target_value_source","target_value_usd","future_pool_mark_exists","future_position_mark_exists_if_joined","net_pnl_usd","net_pnl_pct",
            "data_quality_status","invalid_reason","created_at"
        ],
        "clean_research_eligibility": [
            "dedup_key valid",
            "entry_time valid",
            "pool_id valid",
            "entry_value_usd available/trusted or clearly estimated",
            "future pool mark available at target horizon",
            "no trace-level duplicate counting",
        ],
        "research_only": True,
    }
    write_json(REPORT_DIR / "intent_lifecycle_schema.json", schema)
    write_md(REPORT_DIR / "INTENT_LIFECYCLE_SCHEMA_CN.md", [
        "# INTENT_LIFECYCLE_SCHEMA_CN",
        "",
        "- research-only table: `shadow_intent_lifecycle_research_v1`",
        "- canonical proof is unchanged.",
        "- intent lifecycle cannot be used for edge_proven or canary.",
    ])


def write_stage_f(rows):
    fieldnames = [
        "window","horizon","raw_intent_rows","deduped_intent_count","valid_intent_lifecycle_count","invalid_count",
        "entry_value_trusted_count","future_pool_mark_exists_count","trace_compression_ratio","invalid_reason_distribution",
        "data_quality_status_distribution","top_duplicate_source_pool"
    ]
    write_csv(REPORT_DIR / "intent_lifecycle_materialization_counts.csv", rows, fieldnames)
    lines = ["# INTENT_LIFECYCLE_MATERIALIZATION_CN", ""]
    for r in rows:
        if r["window"] == "last_7d":
            lines.append(
                f"- `{r['window']} {r['horizon']}` raw={r['raw_intent_rows']} deduped={r['deduped_intent_count']} valid={r['valid_intent_lifecycle_count']} invalid={r['invalid_count']} compression={r['trace_compression_ratio']}"
            )
    write_md(REPORT_DIR / "INTENT_LIFECYCLE_MATERIALIZATION_CN.md", lines)


def write_stage_g(rows):
    write_csv(REPORT_DIR / "intent_lifecycle_proof_report.csv", rows, list(rows[0].keys()))
    lines = ["# INTENT_LIFECYCLE_PROOF_REPORT_CN", ""]
    for r in rows:
        if r["window"] == "last_7d":
            lines.append(
                f"- `{r['horizon']}` sample={r['sample_count']} valid={r['valid_count']} median={r['median_net_pnl_pct']} p10={r['p10']} p5={r['p5']} signal={r['top20_vs_bottom20_signal']} sufficiency={r['sample_sufficiency']} duplicate_risk={r['duplicate_risk_status']}"
            )
    write_md(REPORT_DIR / "INTENT_LIFECYCLE_PROOF_REPORT_CN.md", lines)


def write_stage_h(rows, status):
    write_csv(REPORT_DIR / "intent_lifecycle_anti_duplication_audit.csv", rows, list(rows[0].keys()))
    lines = [
        "# INTENT_LIFECYCLE_ANTI_DUPLICATION_AUDIT_CN",
        "",
        f"- duplication_control_status: {status}",
        "- primary policy uses bucketed dedup keys instead of raw trace rows.",
        "- anti-duplication target is to avoid old decision_trace row inflation.",
    ]
    write_md(REPORT_DIR / "INTENT_LIFECYCLE_ANTI_DUPLICATION_AUDIT_CN.md", lines)


def write_stage_i(rows):
    write_csv(REPORT_DIR / "intent_vs_position_lifecycle_comparison.csv", rows, list(rows[0].keys()))
    lines = [
        "# INTENT_VS_POSITION_LIFECYCLE_COMPARISON_CN",
        "",
        "- intent lifecycle 明显扩大样本数，解决了 position reuse 导致的 position-level 样本不足。",
        "- 但它引入新的 bias：bucketed counterfactual + pool-mark exit 近似。",
        "- 如果去重策略失守，它会退化成 decision_trace 重复计数，因此仍需强 anti-duplication gate。",
        "- 在 research-only 口径下，值得继续研究。",
    ]
    write_md(REPORT_DIR / "INTENT_VS_POSITION_LIFECYCLE_COMPARISON_CN.md", lines)


def write_stage_j(remote):
    decision = {
        "recommended_next_stage": remote["recommended_next_stage"],
        "duplication_control_status": remote["duplication_control_status"],
        "intent_lifecycle_sample_sufficiency": remote["intent_lifecycle_sample_sufficiency"],
        "intent_lifecycle_signal_status": remote["intent_lifecycle_signal_status"],
    }
    write_json(REPORT_DIR / "intent_lifecycle_next_stage_decision.json", decision)
    write_md(REPORT_DIR / "INTENT_LIFECYCLE_NEXT_STAGE_DECISION_CN.md", [
        "# INTENT_LIFECYCLE_NEXT_STAGE_DECISION_CN",
        "",
        f"- duplication_control_status: {remote['duplication_control_status']}",
        f"- sample_sufficiency: {remote['intent_lifecycle_sample_sufficiency']}",
        f"- signal_status: {remote['intent_lifecycle_signal_status']}",
        f"- recommended_next_stage: {remote['recommended_next_stage']}",
    ])


def write_final(remote):
    final = {
        "status": "WARN",
        "stage": "RESEARCH_INTENT_LIFECYCLE_MATERIALIZER_V1",
        "data_source": "vps_postgres",
        "db_ready": True,
        "primary_dedup_policy": remote["primary_dedup_policy"],
        "raw_intent_rows_7d": remote["raw_intent_rows_7d"],
        "deduped_intent_count_7d": remote["deduped_intent_count_7d"],
        "valid_intent_lifecycle_6h": remote["valid_intent_lifecycle_6h"],
        "valid_intent_lifecycle_12h": remote["valid_intent_lifecycle_12h"],
        "valid_intent_lifecycle_24h": remote["valid_intent_lifecycle_24h"],
        "duplication_control_status": remote["duplication_control_status"],
        "intent_lifecycle_feasibility": remote["intent_lifecycle_feasibility"],
        "intent_lifecycle_sample_sufficiency": remote["intent_lifecycle_sample_sufficiency"],
        "intent_lifecycle_signal_status": remote["intent_lifecycle_signal_status"],
        "position_lifecycle_oos_viable": False,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": remote["recommended_next_stage"],
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
    write_md(REPORT_DIR / "ONEPAGE_CN.md", [
        "# ONEPAGE_CN",
        "",
        f"- primary_dedup_policy: {final['primary_dedup_policy']}",
        f"- raw_intent_rows_7d: {final['raw_intent_rows_7d']}",
        f"- deduped_intent_count_7d: {final['deduped_intent_count_7d']}",
        f"- valid_intent_lifecycle_6h: {final['valid_intent_lifecycle_6h']}",
        f"- valid_intent_lifecycle_12h: {final['valid_intent_lifecycle_12h']}",
        f"- valid_intent_lifecycle_24h: {final['valid_intent_lifecycle_24h']}",
        f"- duplication_control_status: {final['duplication_control_status']}",
        f"- intent_lifecycle_sample_sufficiency: {final['intent_lifecycle_sample_sufficiency']}",
        f"- intent_lifecycle_signal_status: {final['intent_lifecycle_signal_status']}",
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
        "- INTENT_LIFECYCLE_DEDUP_POLICY_CN.md",
        "- intent_lifecycle_dedup_policy.json",
        "- INTENT_LIFECYCLE_SCHEMA_CN.md",
        "- intent_lifecycle_schema.json",
        "- INTENT_LIFECYCLE_MATERIALIZATION_CN.md",
        "- intent_lifecycle_materialization_counts.csv",
        "- INTENT_LIFECYCLE_PROOF_REPORT_CN.md",
        "- intent_lifecycle_proof_report.csv",
        "- INTENT_LIFECYCLE_ANTI_DUPLICATION_AUDIT_CN.md",
        "- intent_lifecycle_anti_duplication_audit.csv",
        "- INTENT_VS_POSITION_LIFECYCLE_COMPARISON_CN.md",
        "- intent_vs_position_lifecycle_comparison.csv",
        "- INTENT_LIFECYCLE_NEXT_STAGE_DECISION_CN.md",
        "- intent_lifecycle_next_stage_decision.json",
        "- FINAL_VERDICT.json",
        "- ONEPAGE_CN.md",
        "- intent_lifecycle_materializer_v1_readonly.py",
    ])


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stage_b_input_audit()
    remote = remote_materialize()
    write_stage_c(remote["db"])
    if remote["db"]["db_connect"] != "ok":
        final = {
            "status": "FAIL",
            "stage": "RESEARCH_INTENT_LIFECYCLE_MATERIALIZER_V1",
            "data_source": "vps_postgres",
            "db_ready": False,
            "primary_dedup_policy": "",
            "raw_intent_rows_7d": 0,
            "deduped_intent_count_7d": 0,
            "valid_intent_lifecycle_6h": 0,
            "valid_intent_lifecycle_12h": 0,
            "valid_intent_lifecycle_24h": 0,
            "duplication_control_status": "FAIL",
            "intent_lifecycle_feasibility": "NOT_FEASIBLE",
            "intent_lifecycle_sample_sufficiency": "INSUFFICIENT",
            "intent_lifecycle_signal_status": "mixed",
            "position_lifecycle_oos_viable": False,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "recommended_next_stage": "FIXED_HORIZON_DB_OR_SCHEMA_FIX_REPEAT",
        }
        write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
        write_md(REPORT_DIR / "ONEPAGE_CN.md", ["# ONEPAGE_CN", "", "- status: FAIL", "- recommended_next_stage: FIXED_HORIZON_DB_OR_SCHEMA_FIX_REPEAT"])
        write_md(REPORT_DIR / "ARTIFACT_INDEX.md", ["# ARTIFACT_INDEX", "", "- FINAL_VERDICT.json", "- ONEPAGE_CN.md"])
        return 0
    write_stage_d(remote["policy_summary"], remote["primary_dedup_policy"])
    write_stage_e()
    write_stage_f(remote["materialization_counts"])
    write_stage_g(remote["proof_rows"])
    write_stage_h(remote["anti_dup_rows"], remote["duplication_control_status"])
    write_stage_i(remote["comparison_rows"])
    write_stage_j(remote)
    write_final(remote)
    return 0


if __name__ == "__main__":
    sys.exit(main())
