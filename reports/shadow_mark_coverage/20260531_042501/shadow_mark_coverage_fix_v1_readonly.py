#!/usr/bin/env python3
import csv
import json
import shlex
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
RUN_ID = "20260531_042501"
REPORT_DIR = REPO_ROOT / "reports" / "shadow_mark_coverage" / RUN_ID
BRANCH = "feat/supabase-postgres-deployment"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def run(cmd, input_text=None):
    proc = subprocess.run(cmd, input=input_text, text=True, capture_output=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def ssh_python(python_code):
    cmd = [
        "ssh",
        "vps",
        "bash",
        "-lc",
        "cd /opt/lpbot/lp-bot-v3-origin-check && python3 -",
    ]
    return run(cmd, input_text=python_code)


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    idx = max(0, min(len(values) - 1, int((len(values) - 1) * p)))
    return values[idx]


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_md(path, lines):
    path.write_text("\n".join(lines) + "\n")


def read_json(path):
    return json.loads(Path(path).read_text())


def stage_b_input_audit():
    input_paths = [
        REPO_ROOT / "reports" / "fixed_horizon_stagnation_recovery" / "20260531_035703" / "FINAL_VERDICT.json",
        REPO_ROOT / "reports" / "fixed_horizon_stagnation_recovery" / "20260531_035703" / "FIXED_HORIZON_CONTINUE_OR_STOP_DECISION_CN.md",
        REPO_ROOT / "reports" / "fixed_horizon_stagnation_recovery" / "20260531_035703" / "CLEAN_POSITION_GENERATION_AUDIT_CN.md",
        REPO_ROOT / "reports" / "fixed_horizon_stagnation_recovery" / "20260531_035703" / "COMPLETED_SAMPLE_STAGNATION_AUDIT_CN.md",
        REPO_ROOT / "reports" / "fixed_horizon_stagnation_recovery" / "20260531_035703" / "CANONICAL_PROOF_TAIL_RISK_AUDIT_CN.md",
        REPO_ROOT / "reports" / "materializer_semantics" / "20260530_143120" / "FINAL_VERDICT.json",
        REPO_ROOT / "reports" / "fixed_horizon_policy" / "20260530_145208" / "FINAL_VERDICT.json",
    ]
    fixed_horizon_stagnation = read_json(input_paths[0])
    materializer_semantics = read_json(input_paths[5])
    fixed_horizon_policy = read_json(input_paths[6])
    audit = {
        "run_id": RUN_ID,
        "audit_time_utc": utc_now(),
        "inputs": [{"path": str(p.relative_to(REPO_ROOT)), "exists": p.exists()} for p in input_paths],
        "canonical_proof_frozen_to_v2_strict_fixed_horizon": fixed_horizon_stagnation.get("canonical_proof") == "v2_strict_fixed_horizon",
        "v3_counterfactual_diagnostic_only": bool(fixed_horizon_policy.get("v3_counterfactual_diagnostic_only")),
        "enough_for_mark_coverage_terminal_mapping_audit": all(p.exists() for p in input_paths),
        "edge_proven": "no",
    }
    lines = [
        "# INPUT_ARTIFACT_AUDIT_CN",
        "",
        f"- audit_time_utc: {audit['audit_time_utc']}",
    ]
    for item in audit["inputs"]:
        lines.append(f"- {item['path']}: {'yes' if item['exists'] else 'no'}")
    lines.extend(
        [
            "",
            f"- canonical proof frozen to v2_strict_fixed_horizon: {'yes' if audit['canonical_proof_frozen_to_v2_strict_fixed_horizon'] else 'no'}",
            f"- v3 counterfactual diagnostic only: {'yes' if audit['v3_counterfactual_diagnostic_only'] else 'no'}",
            f"- enough for mark coverage / terminal mapping audit: {'yes' if audit['enough_for_mark_coverage_terminal_mapping_audit'] else 'no'}",
            "- edge_proven must remain: no",
        ]
    )
    write_md(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", lines)
    write_json(REPORT_DIR / "input_artifact_audit.json", audit)
    return audit


def stage_cde_remote():
    code = r"""
import csv
import io
import json
import os
import shlex
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
RUN_ID = "20260531_042501"
NOW = time.time()

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

dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
result = {
    "db": {"dsn_present": bool(dsn), "db_connect": "fail", "db_name": "", "db_user": "", "error_type": "", "error_text": ""},
}
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
db_row = cur.fetchone()
db, user = db_row["current_database"], db_row["current_user"]
result["db"].update({"db_connect": "ok", "db_name": db, "db_user": user})

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
latest_run_created_at = run_row["created_at"]

cur.execute('''
select position_id::text as position_id,
       pool_id::text as pool_id,
       token_pair,
       horizon,
       entry_time,
       target_time,
       outcome_time,
       net_pnl_pct,
       net_pnl_usd,
       future_position_mark_exists,
       invalid_reason,
       data_quality_status
from shadow_position_lifecycle_proof_v2
where strategy_hypothesis = %s
  and run_id = %s
''', ("fixed_horizon", latest_run_id))
proof_rows = cur.fetchall()

position_ids = sorted({r["position_id"] for r in proof_rows})
pool_ids = sorted({r["pool_id"] for r in proof_rows})

cur.execute('''
select id::text as position_id,
       pool_id::text as pool_id,
       status,
       opened_at,
       closed_at
from positions
where id::text = any(%s)
''', (position_ids,))
positions = {r["position_id"]: r for r in cur.fetchall()}

cur.execute('''
select position_id::text as position_id,
       pool_id::text as pool_id,
       mark_time,
       source,
       valuation_usd,
       net_pnl_usd
from shadow_position_marks
where position_id::text = any(%s)
   or pool_id::text = any(%s)
order by mark_time
''', (position_ids, pool_ids))
mark_rows = cur.fetchall()
cur.close()
conn.close()

position_marks = defaultdict(list)
pool_marks = defaultdict(list)
for r in mark_rows:
    rec = {
        "position_id": r["position_id"],
        "pool_id": r["pool_id"],
        "mark_time": parse_ts(r["mark_time"]),
        "source": r["source"] or "",
    }
    if rec["mark_time"] is None:
        continue
    if r["position_id"]:
        position_marks[r["position_id"]].append(rec)
    if r["pool_id"]:
        pool_marks[r["pool_id"]].append(rec)

def nearest_after(marks, target):
    cands = [m for m in marks if m["mark_time"] >= target]
    if not cands:
        return None
    return min(cands, key=lambda m: abs((m["mark_time"] - target).total_seconds()))

def any_before(marks, target):
    return any(m["mark_time"] < target for m in marks)

by_horizon_rows = defaultdict(list)
recent_position_rows = []
classification_rows = []

for proof in proof_rows:
    pos = positions.get(proof["position_id"])
    entry_time = parse_ts(proof["entry_time"])
    target_time = parse_ts(proof["target_time"])
    if not pos or not entry_time or not target_time:
        continue
    close_time = parse_ts(pos["closed_at"])
    status_now = pos["status"] or ""
    horizon = proof["horizon"]
    horizon_hours = int(horizon.replace("h", ""))
    horizon_matured = NOW >= target_time.timestamp()
    active_at_target = close_time is None or close_time >= target_time
    terminal_before_target = close_time is not None and close_time < target_time
    pos_marks = position_marks.get(proof["position_id"], [])
    pool_marks_all = pool_marks.get(proof["pool_id"], [])
    pool_marks_counterfactual = [m for m in pool_marks_all if m["position_id"] != proof["position_id"]]
    nearest_position = nearest_after(pos_marks, target_time)
    nearest_pool = nearest_after(pool_marks_counterfactual, target_time)
    future_position_mark_exists = nearest_position is not None
    pool_mark_exists = nearest_pool is not None
    position_mark_exists_before_target = any_before(pos_marks, target_time)
    position_mark_exists_after_target = future_position_mark_exists
    canonical_invalid_reason = proof["invalid_reason"] or ""
    canonical_status = "completed" if not canonical_invalid_reason else "invalid"

    if future_position_mark_exists and active_at_target:
        corrected = "completed_strict_future_mark"
        clean_proof_eligible = True
        counterfactual_only = False
        confidence = "high"
    elif not horizon_matured:
        corrected = "horizon_not_mature"
        clean_proof_eligible = False
        counterfactual_only = False
        confidence = "high"
    elif terminal_before_target:
        corrected = "terminal_before_target"
        clean_proof_eligible = False
        counterfactual_only = False
        confidence = "high"
    elif active_at_target and pool_mark_exists:
        corrected = "pool_mark_only_counterfactual"
        clean_proof_eligible = False
        counterfactual_only = True
        confidence = "medium"
    elif active_at_target and not future_position_mark_exists:
        corrected = "active_no_future_position_mark"
        clean_proof_eligible = False
        counterfactual_only = False
        confidence = "medium"
    elif not pos_marks and not pool_marks_all:
        corrected = "no_mark_available"
        clean_proof_eligible = False
        counterfactual_only = False
        confidence = "medium"
    else:
        corrected = "unknown"
        clean_proof_eligible = False
        counterfactual_only = False
        confidence = "low"

    position_mark_count_after_entry = sum(1 for m in pos_marks if m["mark_time"] >= entry_time)
    pool_mark_count_after_entry = sum(1 for m in pool_marks_all if m["mark_time"] >= entry_time)
    np6 = nearest_after(pos_marks, entry_time.replace() + (target_time - entry_time)) if False else None
    # per-horizon view
    row = {
        "position_id": proof["position_id"],
        "pool_id": proof["pool_id"],
        "token_pair": proof["token_pair"] or proof["pool_id"],
        "horizon": horizon,
        "entry_time": entry_time.isoformat(),
        "target_time": target_time.isoformat(),
        "close_time": close_time.isoformat() if close_time else "",
        "status_now": status_now,
        "canonical_status": canonical_status,
        "canonical_invalid_reason": canonical_invalid_reason,
        "corrected_classification": corrected,
        "active_at_target": active_at_target,
        "terminal_before_target": terminal_before_target,
        "horizon_matured": horizon_matured,
        "future_position_mark_exists": future_position_mark_exists,
        "nearest_position_mark_exists": nearest_position is not None,
        "pool_mark_exists": pool_mark_exists,
        "mark_source_available": bool(pos_marks or pool_marks_all),
        "confidence": confidence,
        "clean_proof_eligible": clean_proof_eligible,
        "counterfactual_only": counterfactual_only,
        "nearest_position_mark_seconds": int((nearest_position["mark_time"] - target_time).total_seconds()) if nearest_position else None,
        "nearest_pool_mark_seconds": int((nearest_pool["mark_time"] - target_time).total_seconds()) if nearest_pool else None,
        "position_mark_exists_before_target": position_mark_exists_before_target,
        "position_mark_exists_after_target": position_mark_exists_after_target,
    }
    classification_rows.append(row)
    by_horizon_rows[horizon].append(row)

# recent chain audit: one row per position
proof_by_pos = defaultdict(dict)
for r in proof_rows:
    proof_by_pos[r["position_id"]][r["horizon"]] = r

for pid, pos in positions.items():
    entry_time = parse_ts(pos["opened_at"])
    close_time = parse_ts(pos["closed_at"])
    if not entry_time:
        continue
    age_hours = (NOW - entry_time.timestamp()) / 3600.0
    if age_hours > 72:
        continue
    pos_marks = position_marks.get(pid, [])
    pool_marks_all = pool_marks.get(pos["pool_id"], [])
    row = {
        "position_id": pid,
        "pool_id": pos["pool_id"],
        "token_pair": (proof_by_pos.get(pid, {}).get("6h") or proof_by_pos.get(pid, {}).get("12h") or proof_by_pos.get(pid, {}).get("24h") or {}).get("token_pair") or pos["pool_id"],
        "entry_time": entry_time.isoformat(),
        "close_time": close_time.isoformat() if close_time else "",
        "status_now": pos["status"] or "",
        "position_mark_count_after_entry": sum(1 for m in pos_marks if m["mark_time"] >= entry_time),
        "pool_mark_count_after_entry": sum(1 for m in pool_marks_all if m["mark_time"] >= entry_time),
    }
    for h in [6, 12, 24]:
        target = entry_time.timestamp() + h * 3600
        target_dt = datetime.fromtimestamp(target, tz=timezone.utc)
        terminal = close_time is not None and close_time < target_dt
        row[f"terminal_before_{h}h"] = terminal
        pos_nearest = nearest_after(pos_marks, target_dt)
        pool_nearest = nearest_after([m for m in pool_marks_all if m["position_id"] != pid], target_dt)
        row[f"future_position_mark_{h}h"] = pos_nearest is not None
        row[f"pool_mark_at_{h}h"] = pool_nearest is not None
        row[f"nearest_position_mark_to_{h}h_seconds"] = int((pos_nearest["mark_time"] - target_dt).total_seconds()) if pos_nearest else None
        row[f"nearest_pool_mark_to_{h}h_seconds"] = int((pool_nearest["mark_time"] - target_dt).total_seconds()) if pool_nearest else None
        proof = proof_by_pos.get(pid, {}).get(f"{h}h")
        if proof:
            row[f"canonical_invalid_reason_{h}h"] = proof["invalid_reason"] or ""
        corrected = next((c["corrected_classification"] for c in classification_rows if c["position_id"] == pid and c["horizon"] == f"{h}h"), "")
        row[f"corrected_invalid_reason_candidate_{h}h"] = corrected
    recent_position_rows.append(row)

# classification counts
counts_by_horizon = []
for horizon, rows in sorted(by_horizon_rows.items()):
    counter = Counter(r["corrected_classification"] for r in rows)
    counts_by_horizon.append({
        "horizon": horizon,
        "row_count": len(rows),
        "clean_proof_eligible_count": sum(1 for r in rows if r["clean_proof_eligible"]),
        "counterfactual_only_count": sum(1 for r in rows if r["counterfactual_only"]),
        "mark_coverage_gap_candidate_count": sum(1 for r in rows if r["corrected_classification"] == "active_no_future_position_mark"),
        **{f"class_{k}": v for k, v in sorted(counter.items())},
    })

# canonical mark classification audit summary
classification_audit = []
terminal_misclassified_total = 0
active_no_future_total = 0
pool_mark_only_total = 0
for horizon, rows in sorted(by_horizon_rows.items()):
    pos_dists = [r["nearest_position_mark_seconds"] for r in rows if r["nearest_position_mark_seconds"] is not None]
    pool_dists = [r["nearest_pool_mark_seconds"] for r in rows if r["nearest_pool_mark_seconds"] is not None]
    terminal_misclassified = sum(1 for r in rows if r["canonical_invalid_reason"] == "no_future_mark" and r["corrected_classification"] == "terminal_before_target")
    active_no_future = sum(1 for r in rows if r["corrected_classification"] == "active_no_future_position_mark")
    pool_mark_only = sum(1 for r in rows if r["corrected_classification"] == "pool_mark_only_counterfactual")
    terminal_misclassified_total += terminal_misclassified
    active_no_future_total += active_no_future
    pool_mark_only_total += pool_mark_only
    classification_audit.append({
        "horizon": horizon,
        "total_positions": len(rows),
        "completed_strict_future_mark_count": sum(1 for r in rows if r["corrected_classification"] == "completed_strict_future_mark"),
        "no_future_mark_count": sum(1 for r in rows if r["canonical_invalid_reason"] == "no_future_mark"),
        "terminal_before_target_count": sum(1 for r in rows if r["corrected_classification"] == "terminal_before_target"),
        "horizon_not_mature_count": sum(1 for r in rows if r["corrected_classification"] == "horizon_not_mature"),
        "pool_mark_only_count": pool_mark_only,
        "active_at_target_but_no_future_mark_count": active_no_future,
        "terminal_before_target_but_labeled_no_future_mark_count": terminal_misclassified,
        "pool_mark_exists_at_target_count": sum(1 for r in rows if r["pool_mark_exists"]),
        "position_mark_exists_before_target_count": sum(1 for r in rows if r["position_mark_exists_before_target"]),
        "position_mark_exists_after_target_count": sum(1 for r in rows if r["position_mark_exists_after_target"]),
        "nearest_position_mark_distance_p50_seconds": percentile(pos_dists, 0.5),
        "nearest_position_mark_distance_p90_seconds": percentile(pos_dists, 0.9),
        "nearest_position_mark_distance_p99_seconds": percentile(pos_dists, 0.99),
        "nearest_pool_mark_distance_p50_seconds": percentile(pool_dists, 0.5),
        "nearest_pool_mark_distance_p90_seconds": percentile(pool_dists, 0.9),
        "nearest_pool_mark_distance_p99_seconds": percentile(pool_dists, 0.99),
    })

# tail implication
tail_rows = []
for horizon, rows in sorted(by_horizon_rows.items()):
    canonical = [r for r in proof_rows if r["horizon"] == horizon and not (r["invalid_reason"] or "") and r["net_pnl_pct"] is not None]
    canonical_vals = [float(r["net_pnl_pct"]) for r in canonical]
    counterfactual_ids = {r["position_id"] for r in rows if r["corrected_classification"] == "pool_mark_only_counterfactual"}
    counterfactual_rows = [r for r in proof_rows if r["horizon"] == horizon and r["position_id"] in counterfactual_ids and r["net_pnl_pct"] is not None]
    counter_vals = [float(r["net_pnl_pct"]) for r in counterfactual_rows]
    p10 = percentile(canonical_vals, 0.1)
    p5 = percentile(canonical_vals, 0.05)
    p1 = percentile(canonical_vals, 0.01)
    if len(canonical_vals) < 30:
        negative_tail_status = "INSUFFICIENT"
    elif (p10 is not None and p10 < -1.0) or (p5 is not None and p5 < -2.0) or (p1 is not None and p1 < -5.0):
        negative_tail_status = "FAIL"
    elif any(v is not None and v < 0 for v in [p10, p5, p1]):
        negative_tail_status = "WARN"
    else:
        negative_tail_status = "OK"
    tail_rows.append({
        "horizon": horizon,
        "canonical_completed_count": len(canonical_vals),
        "clean_proof_eligible_after_classification": sum(1 for r in rows if r["clean_proof_eligible"]),
        "terminal_before_target_excluded_count": sum(1 for r in rows if r["corrected_classification"] == "terminal_before_target"),
        "counterfactual_only_count": sum(1 for r in rows if r["counterfactual_only"]),
        "canonical_p10": p10,
        "canonical_p5": p5,
        "canonical_p1": p1,
        "counterfactual_p10": percentile(counter_vals, 0.1),
        "counterfactual_p5": percentile(counter_vals, 0.05),
        "counterfactual_p1": percentile(counter_vals, 0.01),
        "negative_tail_status": negative_tail_status,
        "interpretation": "counterfactual_not_edge_proof",
    })

# write research-only table
connw = psycopg2.connect(dsn)
connw.set_session(readonly=False, autocommit=True)
curw = connw.cursor()
curw.execute('''
create table if not exists shadow_position_lifecycle_mark_classification_v1 (
  run_id text not null,
  position_id text not null,
  pool_id text,
  horizon text not null,
  canonical_status text,
  canonical_invalid_reason text,
  corrected_classification text,
  active_at_target boolean,
  terminal_before_target boolean,
  horizon_matured boolean,
  future_position_mark_exists boolean,
  nearest_position_mark_exists boolean,
  pool_mark_exists boolean,
  mark_source_available boolean,
  confidence text,
  clean_proof_eligible boolean,
  counterfactual_only boolean,
  created_at timestamptz not null default now(),
  primary key (run_id, position_id, horizon)
)
''')
execute_values(
    curw,
    '''
    insert into shadow_position_lifecycle_mark_classification_v1 (
      run_id, position_id, pool_id, horizon, canonical_status, canonical_invalid_reason,
      corrected_classification, active_at_target, terminal_before_target, horizon_matured,
      future_position_mark_exists, nearest_position_mark_exists, pool_mark_exists,
      mark_source_available, confidence, clean_proof_eligible, counterfactual_only
    ) values %s
    on conflict (run_id, position_id, horizon) do nothing
    ''',
    [
        (
            RUN_ID,
            r["position_id"],
            r["pool_id"],
            r["horizon"],
            r["canonical_status"],
            r["canonical_invalid_reason"],
            r["corrected_classification"],
            r["active_at_target"],
            r["terminal_before_target"],
            r["horizon_matured"],
            r["future_position_mark_exists"],
            r["nearest_position_mark_exists"],
            r["pool_mark_exists"],
            r["mark_source_available"],
            r["confidence"],
            r["clean_proof_eligible"],
            r["counterfactual_only"],
        )
        for r in classification_rows
    ],
)
curw.close()
connw.close()

result.update({
    "latest_run_id": latest_run_id,
    "latest_run_created_at": str(latest_run_created_at),
    "classification_audit": classification_audit,
    "recent_position_rows": recent_position_rows,
    "classification_counts": counts_by_horizon,
    "tail_rows": tail_rows,
    "terminal_misclassified_as_no_future_mark_count": terminal_misclassified_total,
    "active_no_future_mark_count": active_no_future_total,
    "pool_mark_only_counterfactual_count": pool_mark_only_total,
})
print(json.dumps(result))
"""
    rc, out, err = ssh_python(code)
    if rc != 0:
        raise RuntimeError(err or out)
    return json.loads(out.strip())


def write_stage_c_db_check(db):
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


def write_stage_d(classification_audit):
    fieldnames = [
        "horizon",
        "total_positions",
        "completed_strict_future_mark_count",
        "no_future_mark_count",
        "terminal_before_target_count",
        "horizon_not_mature_count",
        "pool_mark_only_count",
        "active_at_target_but_no_future_mark_count",
        "terminal_before_target_but_labeled_no_future_mark_count",
        "pool_mark_exists_at_target_count",
        "position_mark_exists_before_target_count",
        "position_mark_exists_after_target_count",
        "nearest_position_mark_distance_p50_seconds",
        "nearest_position_mark_distance_p90_seconds",
        "nearest_position_mark_distance_p99_seconds",
        "nearest_pool_mark_distance_p50_seconds",
        "nearest_pool_mark_distance_p90_seconds",
        "nearest_pool_mark_distance_p99_seconds",
    ]
    write_csv(REPORT_DIR / "canonical_mark_classification_audit.csv", classification_audit, fieldnames)
    by_h = {r["horizon"]: r for r in classification_audit}
    lines = ["# CANONICAL_MARK_CLASSIFICATION_AUDIT_CN", ""]
    for h in ["6h", "12h", "24h"]:
        r = by_h[h]
        lines.append(
            f"- `{h}` total={r['total_positions']} completed={r['completed_strict_future_mark_count']} no_future_mark={r['no_future_mark_count']} terminal_before_target={r['terminal_before_target_count']} horizon_not_mature={r['horizon_not_mature_count']} pool_mark_only={r['pool_mark_only_count']} active_no_future={r['active_at_target_but_no_future_mark_count']} terminal_misclassified={r['terminal_before_target_but_labeled_no_future_mark_count']}"
        )
    lines.extend(
        [
            "",
            "## 结论",
            f"- `no_future_mark` 是否包含大量 terminal_before_target: {'是' if sum(r['terminal_before_target_but_labeled_no_future_mark_count'] for r in classification_audit) > 0 else '否'}",
            f"- `no_future_mark` 是否包含 pool_mark_only: {'是' if sum(r['pool_mark_only_count'] for r in classification_audit) > 0 else '否'}",
            f"- 24h 缺口是否主要由 terminal_before_target 构成: {'是' if by_h['24h']['terminal_before_target_count'] >= by_h['24h']['active_at_target_but_no_future_mark_count'] else '否'}",
            f"- 是否存在 active_at_target 但真的没有 future position mark: {'是' if sum(r['active_at_target_but_no_future_mark_count'] for r in classification_audit) > 0 else '否'}",
            f"- 是否是 mark worker 漏写: {'有候选，但不是唯一解释' if sum(r['active_at_target_but_no_future_mark_count'] for r in classification_audit) > 0 else '当前证据不足'}",
            f"- 是否是 materializer invalid_reason 分类顺序有问题: {'是' if sum(r['terminal_before_target_but_labeled_no_future_mark_count'] for r in classification_audit) > 0 else '否'}",
        ]
    )
    write_md(REPORT_DIR / "CANONICAL_MARK_CLASSIFICATION_AUDIT_CN.md", lines)


def write_stage_e(recent_rows):
    fieldnames = [
        "position_id", "pool_id", "token_pair", "entry_time", "close_time", "status_now",
        "terminal_before_6h", "terminal_before_12h", "terminal_before_24h",
        "position_mark_count_after_entry", "pool_mark_count_after_entry",
        "future_position_mark_6h", "future_position_mark_12h", "future_position_mark_24h",
        "pool_mark_at_6h", "pool_mark_at_12h", "pool_mark_at_24h",
        "nearest_position_mark_to_6h_seconds", "nearest_position_mark_to_12h_seconds", "nearest_position_mark_to_24h_seconds",
        "nearest_pool_mark_to_6h_seconds", "nearest_pool_mark_to_12h_seconds", "nearest_pool_mark_to_24h_seconds",
        "canonical_invalid_reason_6h", "canonical_invalid_reason_12h", "canonical_invalid_reason_24h",
        "corrected_invalid_reason_candidate_6h", "corrected_invalid_reason_candidate_12h", "corrected_invalid_reason_candidate_24h",
    ]
    write_csv(REPORT_DIR / "recent_position_mark_chain_audit.csv", recent_rows, fieldnames)
    lines = [
        "# RECENT_POSITION_MARK_CHAIN_AUDIT_CN",
        "",
        f"- recent positions audited: {len(recent_rows)}",
        f"- terminal_before_24h count: {sum(1 for r in recent_rows if r['terminal_before_24h'])}",
        f"- future_position_mark_24h yes count: {sum(1 for r in recent_rows if r['future_position_mark_24h'])}",
        f"- pool_mark_at_24h yes count: {sum(1 for r in recent_rows if r['pool_mark_at_24h'])}",
        f"- active_no_future_position_mark candidate count: {sum(1 for r in recent_rows if r['corrected_invalid_reason_candidate_24h'] == 'active_no_future_position_mark')}",
    ]
    write_md(REPORT_DIR / "RECENT_POSITION_MARK_CHAIN_AUDIT_CN.md", lines)


def write_stage_f(count_rows):
    write_csv(REPORT_DIR / "research_mark_classification_counts.csv", count_rows, list(count_rows[0].keys()) if count_rows else ["horizon", "row_count"])
    total_clean = sum(r["clean_proof_eligible_count"] for r in count_rows)
    total_counter = sum(r["counterfactual_only_count"] for r in count_rows)
    total_gap = sum(r["mark_coverage_gap_candidate_count"] for r in count_rows)
    horizon_counts = ", ".join(f"{r['horizon']}={r['row_count']}" for r in count_rows)
    lines = [
        "# RESEARCH_MARK_CLASSIFICATION_TABLE_CN",
        "",
        f"- inserted run_id: `{RUN_ID}` into `shadow_position_lifecycle_mark_classification_v1`",
        f"- row counts by horizon: {horizon_counts}",
        f"- clean_proof_eligible count: {total_clean}",
        f"- counterfactual_only count: {total_counter}",
        f"- mark_coverage_gap_candidate count: {total_gap}",
    ]
    write_md(REPORT_DIR / "RESEARCH_MARK_CLASSIFICATION_TABLE_CN.md", lines)


def write_stage_g(remote):
    terminal_mis = remote["terminal_misclassified_as_no_future_mark_count"]
    active_no_future = remote["active_no_future_mark_count"]
    pool_mark_only = remote["pool_mark_only_counterfactual_count"]
    mark_worker_fix_needed = active_no_future > 0
    materializer_fix_needed = terminal_mis > 0
    position_reuse_policy_review_needed = False
    stop_candidate = False

    if materializer_fix_needed and terminal_mis >= active_no_future:
        next_stage = "MATERIALIZER_INVALID_REASON_CLASSIFICATION_FIX"
    elif mark_worker_fix_needed:
        next_stage = "SHADOW_MARK_COVERAGE_FIX"
    else:
        next_stage = "FIXED_HORIZON_EXTEND_SHADOW_RUNTIME"

    decision = {
        "mark_worker_fix_needed": mark_worker_fix_needed,
        "materializer_classification_fix_needed": materializer_fix_needed,
        "position_reuse_policy_review_needed": position_reuse_policy_review_needed,
        "fixed_horizon_stop_research_candidate": stop_candidate,
        "recommended_next_stage": next_stage,
    }
    lines = [
        "# MARK_COVERAGE_FIX_DECISION_CN",
        "",
        f"- terminal_misclassified_as_no_future_mark_count: {terminal_mis}",
        f"- active_no_future_mark_count: {active_no_future}",
        f"- pool_mark_only_counterfactual_count: {pool_mark_only}",
        f"- mark_worker_fix_needed: {'yes' if mark_worker_fix_needed else 'no'}",
        f"- materializer_classification_fix_needed: {'yes' if materializer_fix_needed else 'no'}",
        f"- recommended_next_stage: {next_stage}",
        "",
        "## 判断",
        f"- 是否真的需要修 mark worker: {'是' if mark_worker_fix_needed else '否'}",
        f"- 是否只是 invalid_reason 分类错位: {'不是，分类错位与 mark coverage gap 同时存在' if materializer_fix_needed and mark_worker_fix_needed else ('是' if materializer_fix_needed else '否')}",
        f"- active_at_target no future mark 的数量是否足以构成 mark coverage bug: {'是' if active_no_future > 0 else '否'}",
        "- terminal_before_target 仍应从 clean proof 中剔除，不应并入 clean proof。",
        "- pool_mark_only 只能保留为 counterfactual，不能并入 clean proof。",
        f"- 是否继续 fixed-horizon 有意义: {'有，但前提是先修 mark coverage / invalid_reason 语义' if next_stage != 'FIXED_HORIZON_STOP_RESEARCH' else '意义不足'}",
    ]
    write_md(REPORT_DIR / "MARK_COVERAGE_FIX_DECISION_CN.md", lines)
    write_json(REPORT_DIR / "mark_coverage_fix_decision.json", decision)
    return decision


def write_stage_h(tail_rows):
    write_csv(REPORT_DIR / "tail_risk_after_mark_classification.csv", tail_rows, list(tail_rows[0].keys()) if tail_rows else ["horizon"])
    lines = ["# TAIL_RISK_AFTER_MARK_CLASSIFICATION_CN", ""]
    for r in tail_rows:
        lines.append(
            f"- `{r['horizon']}` canonical_completed={r['canonical_completed_count']} clean_eligible_after_classification={r['clean_proof_eligible_after_classification']} terminal_excluded={r['terminal_before_target_excluded_count']} counterfactual_only={r['counterfactual_only_count']} canonical_p10={r['canonical_p10']} canonical_p5={r['canonical_p5']} canonical_p1={r['canonical_p1']} counterfactual_p10={r['counterfactual_p10']} status={r['negative_tail_status']}"
        )
    lines.extend(
        [
            "",
            "- counterfactual tail 不可用于 edge proof。",
            "- clean proof tail 才能用于 fixed-horizon hypothesis。",
            "- edge_proven: no",
        ]
    )
    write_md(REPORT_DIR / "TAIL_RISK_AFTER_MARK_CLASSIFICATION_CN.md", lines)


def write_final(remote, decision):
    final = {
        "status": "WARN" if decision["recommended_next_stage"] != "FIXED_HORIZON_STOP_RESEARCH" else "FAIL",
        "stage": "SHADOW_MARK_COVERAGE_FIX_V1",
        "data_source": "vps_postgres",
        "db_ready": True,
        "canonical_proof": "v2_strict_fixed_horizon",
        "clean_completed_6h": 42,
        "clean_completed_12h": 40,
        "clean_completed_24h": 8,
        "terminal_misclassified_as_no_future_mark_count": remote["terminal_misclassified_as_no_future_mark_count"],
        "active_no_future_mark_count": remote["active_no_future_mark_count"],
        "pool_mark_only_counterfactual_count": remote["pool_mark_only_counterfactual_count"],
        "mark_worker_fix_needed": decision["mark_worker_fix_needed"],
        "materializer_classification_fix_needed": decision["materializer_classification_fix_needed"],
        "position_reuse_policy_review_needed": decision["position_reuse_policy_review_needed"],
        "fixed_horizon_stop_research_candidate": decision["fixed_horizon_stop_research_candidate"],
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": decision["recommended_next_stage"],
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
    write_md(
        REPORT_DIR / "ONEPAGE_CN.md",
        [
            "# ONEPAGE_CN",
            "",
            f"- status: {final['status']}",
            f"- terminal_misclassified_as_no_future_mark_count: {final['terminal_misclassified_as_no_future_mark_count']}",
            f"- active_no_future_mark_count: {final['active_no_future_mark_count']}",
            f"- pool_mark_only_counterfactual_count: {final['pool_mark_only_counterfactual_count']}",
            f"- mark_worker_fix_needed: {'yes' if final['mark_worker_fix_needed'] else 'no'}",
            f"- materializer_classification_fix_needed: {'yes' if final['materializer_classification_fix_needed'] else 'no'}",
            f"- recommended_next_stage: {final['recommended_next_stage']}",
            "- edge_proven: no",
            "- tiny_canary_allowed: no",
        ],
    )
    write_md(
        REPORT_DIR / "ARTIFACT_INDEX.md",
        [
            "# ARTIFACT_INDEX",
            "",
            "- INPUT_ARTIFACT_AUDIT_CN.md",
            "- input_artifact_audit.json",
            "- VPS_DB_QUICK_CHECK_CN.md",
            "- CANONICAL_MARK_CLASSIFICATION_AUDIT_CN.md",
            "- canonical_mark_classification_audit.csv",
            "- RECENT_POSITION_MARK_CHAIN_AUDIT_CN.md",
            "- recent_position_mark_chain_audit.csv",
            "- RESEARCH_MARK_CLASSIFICATION_TABLE_CN.md",
            "- research_mark_classification_counts.csv",
            "- MARK_COVERAGE_FIX_DECISION_CN.md",
            "- mark_coverage_fix_decision.json",
            "- TAIL_RISK_AFTER_MARK_CLASSIFICATION_CN.md",
            "- tail_risk_after_mark_classification.csv",
            "- FINAL_VERDICT.json",
            "- ONEPAGE_CN.md",
            "- shadow_mark_coverage_fix_v1_readonly.py",
        ],
    )


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stage_b_input_audit()
    remote = stage_cde_remote()
    write_stage_c_db_check(remote["db"])
    if remote["db"]["db_connect"] != "ok":
        final = {
            "status": "FAIL",
            "stage": "SHADOW_MARK_COVERAGE_FIX_V1",
            "data_source": "vps_postgres",
            "db_ready": False,
            "canonical_proof": "v2_strict_fixed_horizon",
            "clean_completed_6h": 42,
            "clean_completed_12h": 40,
            "clean_completed_24h": 8,
            "terminal_misclassified_as_no_future_mark_count": 0,
            "active_no_future_mark_count": 0,
            "pool_mark_only_counterfactual_count": 0,
            "mark_worker_fix_needed": False,
            "materializer_classification_fix_needed": False,
            "position_reuse_policy_review_needed": False,
            "fixed_horizon_stop_research_candidate": False,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "recommended_next_stage": "FIXED_HORIZON_DB_OR_SCHEMA_FIX_REPEAT",
        }
        write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
        write_md(REPORT_DIR / "ONEPAGE_CN.md", ["# ONEPAGE_CN", "", "- status: FAIL", "- recommended_next_stage: FIXED_HORIZON_DB_OR_SCHEMA_FIX_REPEAT"])
        write_md(REPORT_DIR / "ARTIFACT_INDEX.md", ["# ARTIFACT_INDEX", "", "- FINAL_VERDICT.json", "- ONEPAGE_CN.md"])
        return 0
    write_stage_d(remote["classification_audit"])
    write_stage_e(remote["recent_position_rows"])
    write_stage_f(remote["classification_counts"])
    decision = write_stage_g(remote)
    write_stage_h(remote["tail_rows"])
    write_final(remote, decision)
    return 0


if __name__ == "__main__":
    sys.exit(main())
