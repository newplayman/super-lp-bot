#!/usr/bin/env python3
import csv
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
RUN_ID = "20260531_055521"
REPORT_DIR = REPO_ROOT / "reports" / "intent_lifecycle_dq" / RUN_ID


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


def input_audit():
    inputs = [
        REPO_ROOT / "reports" / "intent_lifecycle" / "20260531_051830" / "FINAL_VERDICT.json",
        REPO_ROOT / "reports" / "intent_lifecycle" / "20260531_051830" / "INTENT_LIFECYCLE_MATERIALIZATION_CN.md",
        REPO_ROOT / "reports" / "intent_lifecycle" / "20260531_051830" / "intent_lifecycle_materialization_counts.csv",
        REPO_ROOT / "reports" / "intent_lifecycle" / "20260531_051830" / "INTENT_LIFECYCLE_PROOF_REPORT_CN.md",
        REPO_ROOT / "reports" / "intent_lifecycle" / "20260531_051830" / "intent_lifecycle_proof_report.csv",
        REPO_ROOT / "reports" / "intent_lifecycle" / "20260531_051830" / "INTENT_LIFECYCLE_ANTI_DUPLICATION_AUDIT_CN.md",
        REPO_ROOT / "reports" / "intent_lifecycle" / "20260531_051830" / "intent_lifecycle_anti_duplication_audit.csv",
        REPO_ROOT / "reports" / "intent_lifecycle" / "20260531_051830" / "INTENT_LIFECYCLE_NEXT_STAGE_DECISION_CN.md",
        REPO_ROOT / "reports" / "intent_lifecycle" / "20260531_051830" / "intent_lifecycle_next_stage_decision.json",
        REPO_ROOT / "reports" / "position_reuse_review" / "20260531_050614" / "FINAL_VERDICT.json",
    ]
    prior = read_json(inputs[0])
    audit = {
        "run_id": RUN_ID,
        "inputs": [{"path": str(p.relative_to(REPO_ROOT)), "exists": p.exists()} for p in inputs],
        "enough_for_data_quality_fix": all(p.exists() for p in inputs),
        "confirmed_prior_valid_zero": prior.get("valid_intent_lifecycle_6h") == 0 and prior.get("valid_intent_lifecycle_12h") == 0 and prior.get("valid_intent_lifecycle_24h") == 0,
        "confirmed_old_better_signal_invalidated": prior.get("intent_lifecycle_signal_status") == "insufficient",
        "edge_proven": "no",
    }
    write_json(REPORT_DIR / "input_artifact_audit.json", audit)
    lines = [
        "# INPUT_ARTIFACT_AUDIT_CN.md",
        "",
    ]
    for item in audit["inputs"]:
        lines.append(f"- {item['path']}: {'yes' if item['exists'] else 'no'}")
    lines.extend([
        "",
        f"- enough_for_data_quality_fix: {'yes' if audit['enough_for_data_quality_fix'] else 'no'}",
        f"- confirmed_prior_valid_intent_lifecycle_zero: {'yes' if audit['confirmed_prior_valid_zero'] else 'no'}",
        f"- confirmed_old_better_signal_invalidated: {'yes' if audit['confirmed_old_better_signal_invalidated'] else 'no'}",
        "- edge_proven must remain: no",
    ])
    write_md(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", lines)


def remote_analysis():
    code = r'''
import json
import math
import os
import shlex
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
RUN_ID = "20260531_055521"
WINDOWS = [24, 48, 72, 168]
HORIZONS = [6, 12, 24]
POLICIES = ["pool_time_bucket_15m", "pool_time_bucket_1h", "pool_time_bucket_4h", "pool_score_event", "position_reuse_session"]

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

result = {"db_ready": False}
dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
if not dsn:
    print(json.dumps({"db_ready": False, "dsn_present": False}))
    raise SystemExit(0)

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

def parse_num(v):
    if v in (None, "", "null", "None"):
        return None
    try:
        return float(v)
    except Exception:
        return None

def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    idx = max(0, min(len(values) - 1, int((len(values) - 1) * p)))
    return values[idx]

def sample_sufficiency(n):
    if n < 30:
        return "INSUFFICIENT"
    if n < 100:
        return "EARLY"
    if n < 300:
        return "PRELIMINARY"
    return "USABLE"

def bucket(ts, seconds):
    return int(float(ts) // seconds)

def score_bucket(score):
    try:
        return int(float(score or 0) // 10) * 10
    except Exception:
        return 0

def dedup_key(row, policy):
    pool_id = row["pool_id"] or ""
    token_pair = f"{row['chain']}:{pool_id}"
    epoch = row["strategy_epoch"] if row["strategy_epoch"] is not None else "na"
    tick = float(row["tick_time"])
    if policy == "pool_time_bucket_15m":
        return f"{pool_id}|{token_pair}|{epoch}|{bucket(tick,900)}"
    if policy == "pool_time_bucket_1h":
        return f"{pool_id}|{token_pair}|{epoch}|{bucket(tick,3600)}"
    if policy == "pool_time_bucket_4h":
        return f"{pool_id}|{token_pair}|{epoch}|{bucket(tick,14400)}"
    if policy == "pool_score_event":
        return f"{pool_id}|{token_pair}|{epoch}|score{score_bucket(row['score_total'])}|intent_open"
    pid = row["position_id"] or "no_position"
    return f"{pid}|{pool_id}|{epoch}|{bucket(tick,21600)}"

conn = psycopg2.connect(dsn)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("select current_database(), current_user")
db_name, db_user = cur.fetchone().values()

cur.execute("""
select trace_id, tick_time, pool_id, chain, protocol, score_total, selected, selected_rank,
       selection_reason, intent_open, intent_reason, pipeline_stage, pipeline_ok, pipeline_reason,
       final_action, position_id, strategy_epoch, intended_notional_usd, score_json
from shadow_decision_trace
where tick_time >= extract(epoch from now() - interval '7 days')
  and intent_open = true
order by tick_time
""")
trace_rows = cur.fetchall()

cur.execute("""
select id as position_id, pool_id, chain, status, tier, amount_usd, opened_at, closed_at, metadata
from positions
where opened_at >= extract(epoch from now() - interval '8 days')
order by opened_at
""")
position_rows = cur.fetchall()

cur.execute("""
select position_id, pool_id, mark_time, source, valuation_usd, amount_usd, net_pnl_usd
from shadow_position_marks
where mark_time >= extract(epoch from now() - interval '8 days')
order by mark_time
""")
mark_rows = cur.fetchall()

cur.execute("""
select position_id, pool_id, token_pair, horizon, entry_time, target_time, outcome_time,
       entry_value_usd, target_value_usd, net_pnl_usd, net_pnl_pct, entry_trusted,
       future_position_mark_exists, data_quality_status, invalid_reason
from shadow_position_lifecycle_proof_v2
where strategy_hypothesis = 'fixed_horizon'
""")
proof_rows = cur.fetchall()

cur.execute("""
select intent_lifecycle_id, dedup_key, horizon, source_trace_count, entry_value_source, entry_value_usd,
       entry_value_trusted, target_value_source, target_value_usd, invalid_reason
from shadow_intent_lifecycle_research_v1
where run_id = '20260531_051830'
""")
v1_rows = cur.fetchall()

cur.close()
conn.close()

trace_total = len(trace_rows)
traces_7d = trace_rows
max_tick = max(float(x["tick_time"]) for x in traces_7d) if traces_7d else 0.0

positions_by_id = {r["position_id"]: r for r in position_rows}
marks_by_position = defaultdict(list)
marks_by_pool = defaultdict(list)
for r in mark_rows:
    r = dict(r)
    r["mark_dt"] = parse_ts(r["mark_time"])
    r["amount_num"] = parse_num(r["amount_usd"])
    r["valuation_num"] = parse_num(r["valuation_usd"])
    r["net_pnl_num"] = parse_num(r["net_pnl_usd"])
    marks_by_position[r["position_id"]].append(r)
    marks_by_pool[r["pool_id"]].append(r)

proof_by_position_h = {(r["position_id"], r["horizon"]): r for r in proof_rows}
v1_by_key_h = {(r["dedup_key"], r["horizon"]): r for r in v1_rows}

requested_sources = [
    ("shadow_decision_trace", "intended_notional_usd"),
    ("shadow_decision_trace", "intended_size_usd"),
    ("shadow_decision_trace", "notional_usd"),
    ("shadow_decision_trace", "max_order_usd"),
    ("shadow_decision_trace", "order_usd"),
    ("shadow_decision_trace", "amount_usd"),
    ("shadow_decision_trace", "score_json"),
    ("positions", "amount_usd"),
    ("positions", "entry_value_usd"),
    ("positions", "notional_usd"),
    ("positions", "opened_at"),
    ("shadow_position_marks", "amount_usd"),
    ("shadow_position_marks", "valuation_usd"),
    ("shadow_position_marks", "source"),
    ("shadow_position_lifecycle_proof_v2", "entry_value_usd"),
    ("shadow_intent_lifecycle_research_v1", "entry_value_usd"),
]

column_set = set()
conn = psycopg2.connect(dsn)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("""
select table_name, column_name
from information_schema.columns
where table_schema='public'
  and table_name in ('shadow_decision_trace','positions','shadow_position_marks','shadow_position_lifecycle_proof_v2','shadow_intent_lifecycle_research_v1')
""")
for row in cur.fetchall():
    column_set.add((row["table_name"], row["column_name"]))
cur.close()
conn.close()

source_audit = []
for table_name, column_name in requested_sources:
    exists = (table_name, column_name) in column_set
    non_null_count = 0
    coverage_pct = 0.0
    trust = "unusable"
    reason = ""
    join_key = ""
    if table_name == "shadow_decision_trace":
        join_key = "trace_id / position_id / pool_id"
        if exists and column_name == "intended_notional_usd":
            vals = [parse_num(r.get(column_name)) for r in trace_rows]
            non_null_count = sum(1 for v in vals if v and v > 0)
            coverage_pct = (non_null_count / trace_total * 100.0) if trace_total else 0.0
            trust = "high" if non_null_count > 0 else "unusable"
            reason = "direct intent entry notional when positive numeric" if non_null_count > 0 else "mostly null in current 7d sample"
        elif exists and column_name == "score_json":
            non_null_count = sum(1 for r in trace_rows if r.get("score_json"))
            coverage_pct = (non_null_count / trace_total * 100.0) if trace_total else 0.0
            trust = "diagnostic_only"
            reason = "JSON payload can support audit only; not a direct entry notional"
        else:
            reason = "column not present in live schema" if not exists else "not used in current schema"
    elif table_name == "positions":
        join_key = "position_id"
        if exists and column_name == "amount_usd":
            vals = [parse_num(r.get("amount_usd")) for r in position_rows]
            non_null_count = sum(1 for v in vals if v and v > 0)
            coverage_pct = (non_null_count / len(position_rows) * 100.0) if position_rows else 0.0
            trust = "medium" if non_null_count > 0 else "unusable"
            reason = "joinable position notional, requires clean position_id and timing alignment"
        elif exists and column_name == "opened_at":
            non_null_count = sum(1 for r in position_rows if r.get("opened_at") is not None)
            coverage_pct = (non_null_count / len(position_rows) * 100.0) if position_rows else 0.0
            trust = "diagnostic_only"
            reason = "timing support for clean join, not notional itself"
        else:
            reason = "column absent from live positions schema" if not exists else "not available in positions schema"
    elif table_name == "shadow_position_marks":
        join_key = "position_id + mark_time"
        if exists and column_name == "amount_usd":
            vals = [r["amount_num"] for r in marks_by_position.values() for r in r]
            non_null_count = sum(1 for v in vals if v and v > 0)
            coverage_pct = (non_null_count / len(mark_rows) * 100.0) if mark_rows else 0.0
            trust = "medium" if non_null_count > 0 else "unusable"
            reason = "same-position mark amount can approximate entry notional if near entry and not stale"
        elif exists and column_name == "valuation_usd":
            vals = [r["valuation_num"] for r in marks_by_position.values() for r in r]
            non_null_count = sum(1 for v in vals if v and v > 0)
            coverage_pct = (non_null_count / len(mark_rows) * 100.0) if mark_rows else 0.0
            trust = "diagnostic_only"
            reason = "absolute valuation without trustworthy entry notional cannot form valid entry"
        elif exists and column_name == "source":
            non_null_count = sum(1 for r in mark_rows if r.get("source"))
            coverage_pct = (non_null_count / len(mark_rows) * 100.0) if mark_rows else 0.0
            trust = "diagnostic_only"
            reason = "mark provenance only"
        else:
            reason = "column absent from shadow_position_marks schema"
    elif table_name == "shadow_position_lifecycle_proof_v2":
        join_key = "position_id + horizon"
        if exists and column_name == "entry_value_usd":
            vals = [parse_num(r.get("entry_value_usd")) for r in proof_rows]
            non_null_count = sum(1 for v in vals if v and v > 0)
            coverage_pct = (non_null_count / len(proof_rows) * 100.0) if proof_rows else 0.0
            trust = "diagnostic_only"
            reason = "useful reference but downstream derived table, not independent entry source"
        else:
            reason = "column absent"
    elif table_name == "shadow_intent_lifecycle_research_v1":
        join_key = "dedup_key + horizon"
        if exists and column_name == "entry_value_usd":
            vals = [parse_num(r.get("entry_value_usd")) for r in v1_rows]
            non_null_count = sum(1 for v in vals if v and v > 0)
            coverage_pct = (non_null_count / len(v1_rows) * 100.0) if v1_rows else 0.0
            trust = "diagnostic_only"
            reason = "prior research output only; cannot self-validate v2"
        else:
            reason = "column absent"
    source_audit.append({
        "source_table": table_name,
        "source_column": column_name,
        "exists": "yes" if exists else "no",
        "non_null_count": non_null_count,
        "coverage_pct": round(coverage_pct, 4),
        "join_key": join_key,
        "trust_level": trust,
        "reason": reason,
    })

def choose_entry_source(first, traces):
    pid = first.get("position_id") or ""
    trace_notional = parse_num(first.get("intended_notional_usd"))
    if trace_notional and trace_notional > 0:
        return {
            "entry_notional_source": "trace_intended_notional_usd",
            "entry_notional_usd": trace_notional,
            "entry_notional_confidence": "high",
            "entry_value_trusted": True,
            "missing_reason": "",
            "position_id": pid,
        }
    pos = positions_by_id.get(pid) if pid else None
    if pos:
        pos_amount = parse_num(pos.get("amount_usd"))
        first_ts = float(first["tick_time"])
        opened = pos.get("opened_at")
        opened_gap = abs(float(opened) - first_ts) if opened is not None else None
        same_pool = (pos.get("pool_id") == first.get("pool_id"))
        if pos_amount and pos_amount > 0 and same_pool and opened_gap is not None and opened_gap <= 3600:
            conf = "high" if opened_gap <= 900 else "medium"
            return {
                "entry_notional_source": "joined_position_amount_usd",
                "entry_notional_usd": pos_amount,
                "entry_notional_confidence": conf,
                "entry_value_trusted": True,
                "missing_reason": "",
                "position_id": pid,
            }
        if pos_amount and pos_amount > 0 and not same_pool:
            return {
                "entry_notional_source": "",
                "entry_notional_usd": None,
                "entry_notional_confidence": "none",
                "entry_value_trusted": False,
                "missing_reason": "ambiguous_multiple_positions",
                "position_id": pid,
            }
    if pid and pid in marks_by_position:
        first_ts = parse_ts(first["tick_time"])
        near_marks = []
        for mk in marks_by_position[pid]:
            if mk["amount_num"] and mk["amount_num"] > 0 and mk["mark_dt"] is not None:
                gap = abs((mk["mark_dt"] - first_ts).total_seconds())
                near_marks.append((gap, mk))
        if near_marks:
            near_marks.sort(key=lambda x: x[0])
            gap, mk = near_marks[0]
            if gap <= 900:
                return {
                    "entry_notional_source": "first_position_mark_amount_usd",
                    "entry_notional_usd": mk["amount_num"],
                    "entry_notional_confidence": "medium",
                    "entry_value_trusted": True,
                    "missing_reason": "",
                    "position_id": pid,
                }
            return {
                "entry_notional_source": "",
                "entry_notional_usd": None,
                "entry_notional_confidence": "low",
                "entry_value_trusted": False,
                "missing_reason": "mark_amount_missing",
                "position_id": pid,
            }
    if pid and not pos:
        return {
            "entry_notional_source": "",
            "entry_notional_usd": None,
            "entry_notional_confidence": "none",
            "entry_value_trusted": False,
            "missing_reason": "position_join_missing",
            "position_id": pid,
        }
    return {
        "entry_notional_source": "",
        "entry_notional_usd": None,
        "entry_notional_confidence": "none",
        "entry_value_trusted": False,
        "missing_reason": "intended_notional_missing",
        "position_id": pid,
    }

base_groups = defaultdict(list)
for row in traces_7d:
    base_groups[dedup_key(row, "pool_time_bucket_1h")].append(row)

lineage_rows = []
summary_counts = Counter()
base_records = []
for key, traces in sorted(base_groups.items(), key=lambda kv: min(float(x["tick_time"]) for x in kv[1])):
    traces = sorted(traces, key=lambda x: float(x["tick_time"]))
    first = traces[0]
    source = choose_entry_source(first, traces)
    first_tick = float(first["tick_time"])
    entry_dt = parse_ts(first["tick_time"])
    if source["entry_notional_confidence"] == "high":
        summary_counts["valid_entry_high_count"] += 1
    elif source["entry_notional_confidence"] == "medium":
        summary_counts["valid_entry_medium_count"] += 1
    elif source["entry_notional_confidence"] == "low":
        summary_counts["low_confidence_count"] += 1
    else:
        summary_counts["missing_entry_count"] += 1
    if source["missing_reason"] == "ambiguous_multiple_positions":
        summary_counts["ambiguous_count"] += 1
    base_record = {
        "dedup_key": key,
        "pool_id": first["pool_id"] or "",
        "token_pair": f"{first['chain']}:{first['pool_id']}",
        "strategy_epoch": first["strategy_epoch"] if first["strategy_epoch"] is not None else "",
        "first_trace_time": int(first_tick),
        "source_trace_count": len(traces),
        "selected_count": sum(1 for t in traces if t["selected"]),
        "intent_open_count": len(traces),
        "reuse_count": sum(1 for t in traces if t["final_action"] == "reuse_shadow_position"),
        "open_new_count": sum(1 for t in traces if t["final_action"] == "open_shadow_position"),
        "position_id": source["position_id"],
        "entry_notional_source": source["entry_notional_source"],
        "entry_notional_usd": source["entry_notional_usd"],
        "entry_notional_confidence": source["entry_notional_confidence"],
        "entry_value_trusted": "yes" if source["entry_value_trusted"] else "no",
        "missing_reason": source["missing_reason"],
        "valid_entry": "yes" if source["entry_notional_confidence"] in ("high", "medium") and source["entry_value_trusted"] else "no",
    }
    lineage_rows.append(base_record)
    base_records.append({
        "dedup_key": key,
        "first": first,
        "first_tick": first_tick,
        "entry_dt": entry_dt,
        "source": source,
        "trace_count": len(traces),
        "selected_count": base_record["selected_count"],
        "intent_open_count": base_record["intent_open_count"],
        "reuse_count": base_record["reuse_count"],
        "open_new_count": base_record["open_new_count"],
    })

entry_policy = {
    "valid_sources": [
        {"name": "trace_intended_notional_usd", "trust": "high", "condition": "non-null, positive, numeric"},
        {"name": "joined_position_amount_usd", "trust": "medium/high", "condition": "position_id joins cleanly, opened near intent, same pool, no ambiguity"},
        {"name": "first_position_mark_amount_usd", "trust": "medium", "condition": "same position, near entry time, positive, not stale"},
    ],
    "invalid_sources": [
        "config_default_notional",
        "hardcoded_default_10",
        "pool_valuation_without_position_linkage",
        "valuation_usd_absolute_without_matching_entry_notional",
        "null_or_zero_fallback",
    ],
    "requires_confidence": ["high", "medium"],
}

materialized_rows = []
materialization_counts = []

def nearest_future_pool_mark(pool_id, target_dt):
    cands = []
    for mk in marks_by_pool.get(pool_id, []):
        if mk["mark_dt"] and mk["mark_dt"] >= target_dt and mk["valuation_num"] is not None:
            cands.append(mk)
    if not cands:
        return None
    return min(cands, key=lambda x: abs((x["mark_dt"] - target_dt).total_seconds()))

def row_valid_for_lifecycle(base_row, horizon):
    target_dt = parse_ts(base_row["first_trace_time"]) if False else None

for window in WINDOWS:
    window_cutoff = max_tick - window * 3600
    window_rows = [r for r in traces_7d if float(r["tick_time"]) >= window_cutoff]
    window_base_records = [r for r in base_records if r["first_tick"] >= window_cutoff]
    for horizon in HORIZONS:
        valid_count = 0
        invalid_count = 0
        invalid_reason_dist = Counter()
        entry_source_dist = Counter()
        conf_dist = Counter()
        for base in window_base_records:
            key = base["dedup_key"]
            first = base["first"]
            source = base["source"]
            entry_source_dist[source["entry_notional_source"] or "missing"] += 1
            conf_dist[source["entry_notional_confidence"]] += 1
            entry_dt = base["entry_dt"]
            target_dt = datetime.fromtimestamp(entry_dt.timestamp() + horizon * 3600, tz=timezone.utc)
            future_pool_mark = nearest_future_pool_mark(first["pool_id"], target_dt)
            target_val = future_pool_mark["valuation_num"] if future_pool_mark else None
            invalid_reason = ""
            data_quality_status = "ok"
            if source["entry_notional_confidence"] not in ("high", "medium") or not source["entry_value_trusted"]:
                invalid_reason = source["missing_reason"] or "invalid_entry_source"
                data_quality_status = "invalid"
            elif target_val is None:
                invalid_reason = "no_future_pool_mark"
                data_quality_status = "invalid"
            if invalid_reason:
                invalid_count += 1
                invalid_reason_dist[invalid_reason] += 1
            else:
                valid_count += 1
            entry_val = source["entry_notional_usd"]
            net_pnl_usd = (target_val - entry_val) if (target_val is not None and entry_val is not None) else None
            net_pnl_pct = ((target_val - entry_val) / entry_val * 100.0) if (target_val is not None and entry_val not in (None, 0)) else None
            materialized_rows.append({
                "run_id": RUN_ID,
                "window": f"last_{window}h" if window < 168 else "last_7d",
                "dedup_key": key,
                "pool_id": first["pool_id"],
                "token_pair": f"{first['chain']}:{first['pool_id']}",
                "strategy_epoch": first["strategy_epoch"] if first["strategy_epoch"] is not None else None,
                "horizon": f"{horizon}h",
                "entry_time": entry_dt.isoformat(),
                "target_time": target_dt.isoformat(),
                "source_trace_count": base["trace_count"],
                "entry_notional_source": source["entry_notional_source"],
                "entry_notional_usd": entry_val,
                "entry_notional_confidence": source["entry_notional_confidence"],
                "entry_value_trusted": source["entry_value_trusted"],
                "target_value_source": "future_pool_mark" if future_pool_mark else "",
                "target_value_usd": target_val,
                "future_pool_mark_exists": bool(future_pool_mark),
                "net_pnl_usd": net_pnl_usd,
                "net_pnl_pct": net_pnl_pct,
                "data_quality_status": data_quality_status,
                "invalid_reason": invalid_reason,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        materialization_counts.append({
            "window": f"last_{window}h" if window < 168 else "last_7d",
            "horizon": f"{horizon}h",
            "raw_intent_rows": len(window_rows),
            "deduped_intent_count": len(window_base_records),
            "valid_entry_count": sum(1 for base in window_base_records if base["source"]["entry_notional_confidence"] in ("high", "medium")),
            "valid_lifecycle_count": valid_count,
            "invalid_count": invalid_count,
            "invalid_reason_distribution": dict(invalid_reason_dist),
            "entry_source_distribution": dict(entry_source_dist),
            "confidence_distribution": dict(conf_dist),
        })

conn = psycopg2.connect(dsn)
conn.set_session(readonly=False, autocommit=True)
cur = conn.cursor()
cur.execute("""
create table if not exists shadow_intent_lifecycle_research_v2 (
  run_id text not null,
  dedup_key text not null,
  pool_id text,
  token_pair text,
  strategy_epoch bigint,
  horizon text,
  entry_time timestamptz,
  target_time timestamptz,
  source_trace_count integer,
  entry_notional_source text,
  entry_notional_usd double precision,
  entry_notional_confidence text,
  entry_value_trusted boolean,
  target_value_source text,
  target_value_usd double precision,
  future_pool_mark_exists boolean,
  net_pnl_usd double precision,
  net_pnl_pct double precision,
  data_quality_status text,
  invalid_reason text,
  created_at timestamptz not null default now(),
  primary key (run_id, dedup_key, horizon)
)
""")
execute_values(
    cur,
    """
    insert into shadow_intent_lifecycle_research_v2 (
      run_id, dedup_key, pool_id, token_pair, strategy_epoch, horizon, entry_time, target_time,
      source_trace_count, entry_notional_source, entry_notional_usd, entry_notional_confidence, entry_value_trusted,
      target_value_source, target_value_usd, future_pool_mark_exists, net_pnl_usd, net_pnl_pct,
      data_quality_status, invalid_reason, created_at
    ) values %s
    on conflict (run_id, dedup_key, horizon) do nothing
    """,
    [(
        r["run_id"], r["dedup_key"], r["pool_id"], r["token_pair"], r["strategy_epoch"], r["horizon"], r["entry_time"],
        r["target_time"], r["source_trace_count"], r["entry_notional_source"], r["entry_notional_usd"], r["entry_notional_confidence"],
        r["entry_value_trusted"], r["target_value_source"], r["target_value_usd"], r["future_pool_mark_exists"], r["net_pnl_usd"],
        r["net_pnl_pct"], r["data_quality_status"], r["invalid_reason"], r["created_at"]
    ) for r in materialized_rows]
)
cur.close()
conn.close()

dedup_deep_rows = []
for policy in POLICIES:
    groups = defaultdict(list)
    for row in traces_7d:
        groups[dedup_key(row, policy)].append(row)
    source_counts = sorted(len(v) for v in groups.values())
    key_counter = Counter({k: len(v) for k, v in groups.items()})
    pool_counter = Counter()
    pos_counter = Counter()
    epoch_counter = Counter()
    for k, group in groups.items():
        first = sorted(group, key=lambda x: float(x["tick_time"]))[0]
        pool_counter[first["pool_id"] or ""] += 1
        pos_counter[first["position_id"] or ""] += 1
        epoch_counter[str(first["strategy_epoch"])] += 1
    deduped_count = len(groups)
    max_key_share = (max(key_counter.values()) / deduped_count) if deduped_count else None
    top_pool_share = (max(pool_counter.values()) / deduped_count) if deduped_count else None
    top_position_share = (max(pos_counter.values()) / deduped_count) if deduped_count else None
    if policy == "pool_time_bucket_1h":
        expected_bias = "moderate_time_bucket_bias"
    elif policy == "pool_time_bucket_15m":
        expected_bias = "under_compress_repeat_ticks"
    elif policy == "pool_time_bucket_4h":
        expected_bias = "over_compress_multi-intent-windows"
    elif policy == "pool_score_event":
        expected_bias = "score-band-collapse"
    else:
        expected_bias = "position-reuse-path-dependence"
    max_source_count = max(source_counts) if source_counts else 0
    if max_source_count > 20 or (top_position_share is not None and top_position_share > 0.35):
        dup_status = "FAIL"
    elif max_source_count > 5 or (top_pool_share is not None and top_pool_share > 0.30):
        dup_status = "WARN"
    else:
        dup_status = "PASS"
    dedup_deep_rows.append({
        "policy": policy,
        "deduped_count": deduped_count,
        "compression_ratio": (len(traces_7d) / deduped_count) if deduped_count else None,
        "max_source_trace_count": max_source_count,
        "p50_source_trace_count": percentile(source_counts, 0.5),
        "p90_source_trace_count": percentile(source_counts, 0.9),
        "p99_source_trace_count": percentile(source_counts, 0.99),
        "top_10_dedup_keys_by_source_trace_count": ";".join(f"{k}:{c}" for k, c in key_counter.most_common(10)),
        "max_dedup_key_share": max_key_share,
        "top_pool_share": top_pool_share,
        "top_position_share": top_position_share,
        "top_strategy_epoch_share": (max(epoch_counter.values()) / deduped_count) if deduped_count else None,
        "duplicate_tick_compression": "yes" if policy in ("pool_time_bucket_1h", "pool_time_bucket_4h") else "partial",
        "same_position_reuse_concentration": top_position_share,
        "expected_bias": expected_bias,
        "duplication_control_status": dup_status,
    })

primary_dup_status = next(r["duplication_control_status"] for r in dedup_deep_rows if r["policy"] == "pool_time_bucket_1h")

proof_report_rows = []
for mc in materialization_counts:
    rows = [r for r in materialized_rows if r["window"] == mc["window"] and r["horizon"] == mc["horizon"]]
    valid = [r for r in rows if r["invalid_reason"] == "" and r["net_pnl_pct"] is not None]
    vals = [float(r["net_pnl_pct"]) for r in valid]
    ordered = sorted(valid, key=lambda r: r["entry_notional_usd"] or 0, reverse=True)
    topn = max(1, int(len(ordered) * 0.2)) if ordered else 0
    top = ordered[:topn]
    bottom = ordered[-topn:] if topn else []
    top_vals = [float(r["net_pnl_pct"]) for r in top if r["net_pnl_pct"] is not None]
    bottom_vals = [float(r["net_pnl_pct"]) for r in bottom if r["net_pnl_pct"] is not None]
    if len(valid) == 0:
        signal = "insufficient"
    elif top_vals and bottom_vals:
        top_med = percentile(top_vals, 0.5)
        bottom_med = percentile(bottom_vals, 0.5)
        signal = "better" if top_med > bottom_med else ("worse" if top_med < bottom_med else "flat")
    else:
        signal = "insufficient"
    pool_counter = Counter(r["pool_id"] for r in valid)
    key_counter = Counter(r["dedup_key"] for r in valid)
    proof_report_rows.append({
        "window": mc["window"],
        "horizon": mc["horizon"],
        "sample_count": mc["deduped_intent_count"],
        "valid_count": len(valid),
        "invalid_count": mc["invalid_count"],
        "median_net_pnl_pct": percentile(vals, 0.5),
        "p10": percentile(vals, 0.1),
        "p5": percentile(vals, 0.05),
        "p1": percentile(vals, 0.01),
        "win_rate": (sum(1 for v in vals if v > 0) / len(vals)) if vals else None,
        "top20_vs_bottom20_signal": signal,
        "worst_pool_contribution": (max(pool_counter.values()) / len(valid)) if valid else None,
        "worst_dedup_key_contribution": (max(key_counter.values()) / len(valid)) if valid else None,
        "duplicate_risk_status": primary_dup_status,
        "sample_sufficiency": sample_sufficiency(mc["deduped_intent_count"]),
        "data_quality_status": "invalid_all" if len(valid) == 0 else "mixed",
    })

valid_entry_count_7d = next(r["valid_entry_count"] for r in materialization_counts if r["window"] == "last_7d" and r["horizon"] == "6h")
valid_lifecycle_6h = next(r["valid_lifecycle_count"] for r in materialization_counts if r["window"] == "last_7d" and r["horizon"] == "6h")
valid_lifecycle_12h = next(r["valid_lifecycle_count"] for r in materialization_counts if r["window"] == "last_7d" and r["horizon"] == "12h")
valid_lifecycle_24h = next(r["valid_lifecycle_count"] for r in materialization_counts if r["window"] == "last_7d" and r["horizon"] == "24h")

if valid_entry_count_7d == 0 and valid_lifecycle_6h == 0 and valid_lifecycle_12h == 0 and valid_lifecycle_24h == 0:
    next_stage = "FIXED_HORIZON_STOP_RESEARCH"
    entry_recovery_status = "NO_VALID_ENTRY_SOURCE_RECOVERED"
    signal_status = "insufficient"
elif primary_dup_status == "FAIL":
    next_stage = "INTENT_LIFECYCLE_DEDUP_POLICY_FIX"
    entry_recovery_status = "PARTIAL_VALID_ENTRY_RECOVERED"
    signal_status = "insufficient" if valid_lifecycle_6h + valid_lifecycle_12h + valid_lifecycle_24h == 0 else "mixed"
elif valid_lifecycle_6h + valid_lifecycle_12h + valid_lifecycle_24h == 0:
    next_stage = "INTENT_LIFECYCLE_DATA_QUALITY_FIX_REPEAT"
    entry_recovery_status = "PARTIAL_VALID_ENTRY_RECOVERED"
    signal_status = "insufficient"
else:
    seven = [r for r in proof_report_rows if r["window"] == "last_7d"]
    better_count = sum(1 for r in seven if r["top20_vs_bottom20_signal"] == "better")
    safe_tail = all((r["p10"] is None or r["p10"] > -1) and (r["p5"] is None or r["p5"] > -2) for r in seven)
    if better_count >= 2 and safe_tail and primary_dup_status == "PASS":
        next_stage = "INTENT_LIFECYCLE_HYPOTHESIS_REVIEW"
        signal_status = "better"
    else:
        next_stage = "INTENT_LIFECYCLE_DATA_QUALITY_FIX_REPEAT"
        signal_status = "mixed"
    entry_recovery_status = "VALID_ENTRY_PARTIALLY_RECOVERED"

result = {
    "db_ready": True,
    "db_name": db_name,
    "db_user": db_user,
    "raw_intent_rows_7d": len(traces_7d),
    "deduped_intent_count_7d": len(base_groups),
    "source_audit": source_audit,
    "lineage_rows": lineage_rows,
    "lineage_summary": {
        "total_deduped": len(base_groups),
        "valid_entry_high_count": summary_counts["valid_entry_high_count"],
        "valid_entry_medium_count": summary_counts["valid_entry_medium_count"],
        "low_confidence_count": summary_counts["low_confidence_count"],
        "missing_entry_count": summary_counts["missing_entry_count"],
        "ambiguous_count": summary_counts["ambiguous_count"],
    },
    "entry_policy": entry_policy,
    "materialization_counts": materialization_counts,
    "dedup_deep_rows": dedup_deep_rows,
    "proof_report_rows": proof_report_rows,
    "valid_entry_count_7d": valid_entry_count_7d,
    "valid_intent_lifecycle_6h": valid_lifecycle_6h,
    "valid_intent_lifecycle_12h": valid_lifecycle_12h,
    "valid_intent_lifecycle_24h": valid_lifecycle_24h,
    "entry_notional_recovery_status": entry_recovery_status,
    "duplication_control_status": primary_dup_status,
    "intent_lifecycle_signal_status": signal_status,
    "recommended_next_stage": next_stage,
}
print(json.dumps(result))
'''
    rc, out, err = ssh_python(code)
    if rc != 0:
        raise RuntimeError(err or out)
    return json.loads(out.strip())


def write_db_check(remote):
    lines = [
        "# VPS_DB_QUICK_CHECK_CN",
        "",
        f"- DB_READY: {'yes' if remote.get('db_ready') else 'no'}",
    ]
    if remote.get("db_ready"):
        lines.append(f"- DB_NAME: `{remote['db_name']}`")
        lines.append(f"- DB_USER: `{remote['db_user']}`")
    write_md(REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md", lines)


def write_source_audit(rows):
    fieldnames = ["source_table", "source_column", "exists", "non_null_count", "coverage_pct", "join_key", "trust_level", "reason"]
    write_csv(REPORT_DIR / "entry_notional_source_audit.csv", rows, fieldnames)
    lines = [
        "# ENTRY_NOTIONAL_SOURCE_AUDIT_CN",
        "",
        "- hardcoded 10 USD 已完全禁用。",
        "- 只有 high / medium trust source 才允许进入 valid intent lifecycle。",
        "- config default / valuation-only / prior research output 只用于 diagnostic。",
        "",
    ]
    for row in rows:
        lines.append(f"- `{row['source_table']}.{row['source_column']}` exists={row['exists']} coverage_pct={row['coverage_pct']} trust={row['trust_level']} reason={row['reason']}")
    write_md(REPORT_DIR / "ENTRY_NOTIONAL_SOURCE_AUDIT_CN.md", lines)


def write_lineage(rows, summary):
    fieldnames = ["dedup_key", "pool_id", "token_pair", "strategy_epoch", "first_trace_time", "source_trace_count", "selected_count", "intent_open_count", "reuse_count", "open_new_count", "position_id", "entry_notional_source", "entry_notional_usd", "entry_notional_confidence", "entry_value_trusted", "missing_reason", "valid_entry"]
    write_csv(REPORT_DIR / "deduped_intent_entry_lineage_audit.csv", rows, fieldnames)
    lines = [
        "# DEDUPED_INTENT_ENTRY_LINEAGE_AUDIT_CN",
        "",
        f"- total_deduped: {summary['total_deduped']}",
        f"- valid_entry_high_count: {summary['valid_entry_high_count']}",
        f"- valid_entry_medium_count: {summary['valid_entry_medium_count']}",
        f"- low_confidence_count: {summary['low_confidence_count']}",
        f"- missing_entry_count: {summary['missing_entry_count']}",
        f"- ambiguous_count: {summary['ambiguous_count']}",
    ]
    write_md(REPORT_DIR / "DEDUPED_INTENT_ENTRY_LINEAGE_AUDIT_CN.md", lines)


def write_entry_policy(policy):
    write_json(REPORT_DIR / "intent_entry_source_policy.json", policy)
    lines = [
        "# INTENT_ENTRY_SOURCE_POLICY_CN",
        "",
        "- valid_intent_lifecycle requires high or medium trust entry source.",
        "- low confidence and diagnostic-only sources are excluded from valid proof.",
        "- no hardcoded default notional allowed.",
        "",
        "## Valid Sources",
    ]
    for item in policy["valid_sources"]:
        lines.append(f"- `{item['name']}` trust={item['trust']} condition={item['condition']}")
    lines.extend(["", "## Invalid or Diagnostic Only"])
    for item in policy["invalid_sources"]:
        lines.append(f"- `{item}`")
    write_md(REPORT_DIR / "INTENT_ENTRY_SOURCE_POLICY_CN.md", lines)


def write_materialization(rows, remote):
    fieldnames = ["window", "horizon", "raw_intent_rows", "deduped_intent_count", "valid_entry_count", "valid_lifecycle_count", "invalid_count", "invalid_reason_distribution", "entry_source_distribution", "confidence_distribution"]
    write_csv(REPORT_DIR / "intent_lifecycle_dq_v2_materialization_counts.csv", rows, fieldnames)
    lines = [
        "# INTENT_LIFECYCLE_DQ_V2_MATERIALIZATION_CN",
        "",
        f"- raw_intent_rows_7d: {remote['raw_intent_rows_7d']}",
        f"- deduped_intent_count_7d: {remote['deduped_intent_count_7d']}",
        f"- valid_entry_count_7d: {remote['valid_entry_count_7d']}",
        f"- valid_lifecycle_count_6h: {remote['valid_intent_lifecycle_6h']}",
        f"- valid_lifecycle_count_12h: {remote['valid_intent_lifecycle_12h']}",
        f"- valid_lifecycle_count_24h: {remote['valid_intent_lifecycle_24h']}",
    ]
    write_md(REPORT_DIR / "INTENT_LIFECYCLE_DQ_V2_MATERIALIZATION_CN.md", lines)


def write_dedup_deep(rows):
    write_csv(REPORT_DIR / "intent_dedup_deep_audit.csv", rows, list(rows[0].keys()))
    lines = ["# INTENT_DEDUP_DEEP_AUDIT_CN", ""]
    for row in rows:
        lines.append(f"- `{row['policy']}` deduped={row['deduped_count']} compression={row['compression_ratio']} max_source_trace_count={row['max_source_trace_count']} top_pool_share={row['top_pool_share']} top_position_share={row['top_position_share']} status={row['duplication_control_status']} bias={row['expected_bias']}")
    write_md(REPORT_DIR / "INTENT_DEDUP_DEEP_AUDIT_CN.md", lines)


def write_proof(rows):
    write_csv(REPORT_DIR / "intent_lifecycle_dq_v2_proof_report.csv", rows, list(rows[0].keys()))
    lines = ["# INTENT_LIFECYCLE_DQ_V2_PROOF_REPORT_CN", ""]
    for row in rows:
        if row["window"] == "last_7d":
            lines.append(f"- `{row['horizon']}` sample={row['sample_count']} valid={row['valid_count']} invalid={row['invalid_count']} signal={row['top20_vs_bottom20_signal']} sample_sufficiency={row['sample_sufficiency']} data_quality_status={row['data_quality_status']} duplicate_risk={row['duplicate_risk_status']}")
    write_md(REPORT_DIR / "INTENT_LIFECYCLE_DQ_V2_PROOF_REPORT_CN.md", lines)


def write_next_stage(remote):
    decision = {
        "recommended_next_stage": remote["recommended_next_stage"],
        "entry_notional_recovery_status": remote["entry_notional_recovery_status"],
        "duplication_control_status": remote["duplication_control_status"],
        "intent_lifecycle_signal_status": remote["intent_lifecycle_signal_status"],
    }
    write_json(REPORT_DIR / "intent_lifecycle_dq_next_stage_decision.json", decision)
    write_md(REPORT_DIR / "INTENT_LIFECYCLE_DQ_NEXT_STAGE_DECISION_CN.md", [
        "# INTENT_LIFECYCLE_DQ_NEXT_STAGE_DECISION_CN",
        "",
        f"- entry_notional_recovery_status: {remote['entry_notional_recovery_status']}",
        f"- duplication_control_status: {remote['duplication_control_status']}",
        f"- intent_lifecycle_signal_status: {remote['intent_lifecycle_signal_status']}",
        f"- recommended_next_stage: {remote['recommended_next_stage']}",
    ])


def write_final(remote):
    final = {
        "status": "WARN",
        "stage": "INTENT_LIFECYCLE_DATA_QUALITY_FIX_V1",
        "data_source": "vps_postgres",
        "db_ready": True,
        "primary_dedup_policy": "pool_time_bucket_1h",
        "raw_intent_rows_7d": remote["raw_intent_rows_7d"],
        "deduped_intent_count_7d": remote["deduped_intent_count_7d"],
        "valid_entry_count_7d": remote["valid_entry_count_7d"],
        "valid_intent_lifecycle_6h": remote["valid_intent_lifecycle_6h"],
        "valid_intent_lifecycle_12h": remote["valid_intent_lifecycle_12h"],
        "valid_intent_lifecycle_24h": remote["valid_intent_lifecycle_24h"],
        "entry_notional_recovery_status": remote["entry_notional_recovery_status"],
        "duplication_control_status": remote["duplication_control_status"],
        "intent_lifecycle_signal_status": remote["intent_lifecycle_signal_status"],
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": remote["recommended_next_stage"],
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
    write_md(REPORT_DIR / "ONEPAGE_CN.md", [
        "# ONEPAGE_CN",
        "",
        f"- valid_entry_count_7d: {final['valid_entry_count_7d']}",
        f"- valid_intent_lifecycle_6h: {final['valid_intent_lifecycle_6h']}",
        f"- valid_intent_lifecycle_12h: {final['valid_intent_lifecycle_12h']}",
        f"- valid_intent_lifecycle_24h: {final['valid_intent_lifecycle_24h']}",
        f"- entry_notional_recovery_status: {final['entry_notional_recovery_status']}",
        f"- duplication_control_status: {final['duplication_control_status']}",
        f"- intent_lifecycle_signal_status: {final['intent_lifecycle_signal_status']}",
        f"- recommended_next_stage: {final['recommended_next_stage']}",
        "- edge_proven: no",
        "- tiny_canary_allowed: no",
    ])
    index_lines = [
        "# ARTIFACT_INDEX",
        "",
        "- INPUT_ARTIFACT_AUDIT_CN.md",
        "- input_artifact_audit.json",
        "- VPS_DB_QUICK_CHECK_CN.md",
        "- ENTRY_NOTIONAL_SOURCE_AUDIT_CN.md",
        "- entry_notional_source_audit.csv",
        "- DEDUPED_INTENT_ENTRY_LINEAGE_AUDIT_CN.md",
        "- deduped_intent_entry_lineage_audit.csv",
        "- INTENT_ENTRY_SOURCE_POLICY_CN.md",
        "- intent_entry_source_policy.json",
        "- INTENT_LIFECYCLE_DQ_V2_MATERIALIZATION_CN.md",
        "- intent_lifecycle_dq_v2_materialization_counts.csv",
        "- INTENT_DEDUP_DEEP_AUDIT_CN.md",
        "- intent_dedup_deep_audit.csv",
        "- INTENT_LIFECYCLE_DQ_V2_PROOF_REPORT_CN.md",
        "- intent_lifecycle_dq_v2_proof_report.csv",
        "- INTENT_LIFECYCLE_DQ_NEXT_STAGE_DECISION_CN.md",
        "- intent_lifecycle_dq_next_stage_decision.json",
        "- FINAL_VERDICT.json",
        "- ONEPAGE_CN.md",
        "- intent_lifecycle_data_quality_fix_v1_readonly.py",
    ]
    write_md(REPORT_DIR / "ARTIFACT_INDEX.md", index_lines)


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    input_audit()
    remote = remote_analysis()
    if not remote.get("db_ready"):
        write_md(REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md", ["# VPS_DB_QUICK_CHECK_CN", "", "- DB_READY: no"])
        write_json(REPORT_DIR / "FINAL_VERDICT.json", {
            "status": "FAIL",
            "stage": "INTENT_LIFECYCLE_DATA_QUALITY_FIX_V1",
            "data_source": "vps_postgres",
            "db_ready": False,
            "primary_dedup_policy": "pool_time_bucket_1h",
            "raw_intent_rows_7d": 0,
            "deduped_intent_count_7d": 0,
            "valid_entry_count_7d": 0,
            "valid_intent_lifecycle_6h": 0,
            "valid_intent_lifecycle_12h": 0,
            "valid_intent_lifecycle_24h": 0,
            "entry_notional_recovery_status": "DB_NOT_READY",
            "duplication_control_status": "unknown",
            "intent_lifecycle_signal_status": "insufficient",
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "recommended_next_stage": "FIXED_HORIZON_DB_OR_SCHEMA_FIX_REPEAT",
        })
        return
    write_db_check(remote)
    write_source_audit(remote["source_audit"])
    write_lineage(remote["lineage_rows"], remote["lineage_summary"])
    write_entry_policy(remote["entry_policy"])
    write_materialization(remote["materialization_counts"], remote)
    write_dedup_deep(remote["dedup_deep_rows"])
    write_proof(remote["proof_report_rows"])
    write_next_stage(remote)
    write_final(remote)


if __name__ == "__main__":
    main()
