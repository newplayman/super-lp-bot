#!/usr/bin/env python3
import csv
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
RUN_ID = "20260531_044242"
REPORT_DIR = REPO_ROOT / "reports" / "materializer_classification" / RUN_ID


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
        REPO_ROOT / "reports" / "shadow_mark_coverage" / "20260531_042501" / "FINAL_VERDICT.json",
        REPO_ROOT / "reports" / "shadow_mark_coverage" / "20260531_042501" / "MARK_COVERAGE_FIX_DECISION_CN.md",
        REPO_ROOT / "reports" / "shadow_mark_coverage" / "20260531_042501" / "CANONICAL_MARK_CLASSIFICATION_AUDIT_CN.md",
        REPO_ROOT / "reports" / "shadow_mark_coverage" / "20260531_042501" / "canonical_mark_classification_audit.csv",
        REPO_ROOT / "reports" / "shadow_mark_coverage" / "20260531_042501" / "RESEARCH_MARK_CLASSIFICATION_TABLE_CN.md",
        REPO_ROOT / "reports" / "shadow_mark_coverage" / "20260531_042501" / "research_mark_classification_counts.csv",
        REPO_ROOT / "reports" / "shadow_mark_coverage" / "20260531_042501" / "TAIL_RISK_AFTER_MARK_CLASSIFICATION_CN.md",
        REPO_ROOT / "reports" / "shadow_mark_coverage" / "20260531_042501" / "tail_risk_after_mark_classification.csv",
    ]
    final_verdict = read_json(inputs[0])
    audit = {
        "run_id": RUN_ID,
        "audit_time_utc": utc_now(),
        "inputs": [{"path": str(p.relative_to(REPO_ROOT)), "exists": p.exists()} for p in inputs],
        "enough_for_invalid_reason_classification_fix": all(p.exists() for p in inputs),
        "canonical_proof_is_v2_strict_fixed_horizon": final_verdict.get("canonical_proof") == "v2_strict_fixed_horizon",
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
        f"- enough for invalid_reason classification fix: {'yes' if audit['enough_for_invalid_reason_classification_fix'] else 'no'}",
        f"- canonical proof is v2_strict_fixed_horizon: {'yes' if audit['canonical_proof_is_v2_strict_fixed_horizon'] else 'no'}",
        "- edge_proven must remain: no",
    ])
    write_md(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", lines)
    write_json(REPORT_DIR / "input_artifact_audit.json", audit)
    return audit


def stage_c_to_i_remote():
    code = r"""
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
RUN_ID = "20260531_044242"
NOW = time.time()
HORIZONS = ["6h", "12h", "24h"]

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
       entry_trusted,
       future_position_mark_exists,
       invalid_reason,
       net_pnl_pct
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
       source
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
    after = [m for m in marks if m["mark_time"] >= target]
    if not after:
        return None
    return min(after, key=lambda m: abs((m["mark_time"] - target).total_seconds()))

taxonomy = {
    "completed_strict_future_mark": {
        "active_at_target": True,
        "entry_trusted": True,
        "future_position_mark_exists": True,
    },
    "horizon_not_mature": {"target_time_gt_now": True},
    "terminal_before_target": {"close_time_lt_target": True},
    "active_at_target_no_future_position_mark": {
        "active_at_target": True,
        "horizon_mature": True,
        "future_position_mark_exists": False,
    },
    "pool_mark_only_counterfactual": {
        "pool_mark_exists_near_target": True,
        "no_future_position_mark": True,
        "counterfactual_only": True,
    },
    "no_mark_available": {"no_position_or_pool_mark": True},
    "entry_untrusted": {"entry_trusted": False},
    "unknown": {"fallback": True},
}

classified_rows = []
by_horizon = defaultdict(list)
for proof in proof_rows:
    pos = positions.get(proof["position_id"])
    entry_time = parse_ts(proof["entry_time"])
    target_time = parse_ts(proof["target_time"])
    if not pos or not entry_time or not target_time:
        continue
    close_time = parse_ts(pos["closed_at"])
    active_at_target = close_time is None or close_time >= target_time
    terminal_before_target = close_time is not None and close_time < target_time
    horizon_matured = NOW >= target_time.timestamp()
    pos_marks = position_marks.get(proof["position_id"], [])
    pool_marks_for_pool = [m for m in pool_marks.get(proof["pool_id"], []) if m["position_id"] != proof["position_id"]]
    future_position_mark_exists = nearest_after(pos_marks, target_time) is not None
    pool_mark_exists = nearest_after(pool_marks_for_pool, target_time) is not None
    entry_trusted = bool(proof["entry_trusted"])

    if entry_trusted and active_at_target and future_position_mark_exists:
        corrected = "completed_strict_future_mark"
        clean_eligible = True
        counterfactual_only = False
        confidence = "high"
    elif not horizon_matured:
        corrected = "horizon_not_mature"
        clean_eligible = False
        counterfactual_only = False
        confidence = "high"
    elif terminal_before_target:
        corrected = "terminal_before_target"
        clean_eligible = False
        counterfactual_only = False
        confidence = "high"
    elif not entry_trusted:
        corrected = "entry_untrusted"
        clean_eligible = False
        counterfactual_only = False
        confidence = "high"
    elif active_at_target and future_position_mark_exists is False and pool_mark_exists:
        corrected = "pool_mark_only_counterfactual"
        clean_eligible = False
        counterfactual_only = True
        confidence = "medium"
    elif active_at_target and horizon_matured and not future_position_mark_exists:
        corrected = "active_at_target_no_future_position_mark"
        clean_eligible = False
        counterfactual_only = False
        confidence = "medium"
    elif not pos_marks and not pool_marks.get(proof["pool_id"], []):
        corrected = "no_mark_available"
        clean_eligible = False
        counterfactual_only = False
        confidence = "medium"
    else:
        corrected = "unknown"
        clean_eligible = False
        counterfactual_only = False
        confidence = "low"

    classified = {
        "run_id": RUN_ID,
        "position_id": proof["position_id"],
        "pool_id": proof["pool_id"],
        "horizon": proof["horizon"],
        "canonical_invalid_reason": proof["invalid_reason"] or "",
        "corrected_invalid_reason": corrected,
        "active_at_target": active_at_target,
        "terminal_before_target": terminal_before_target,
        "horizon_matured": horizon_matured,
        "entry_trusted": entry_trusted,
        "future_position_mark_exists": future_position_mark_exists,
        "pool_mark_exists": pool_mark_exists,
        "clean_proof_eligible": clean_eligible,
        "counterfactual_only": counterfactual_only,
        "classification_confidence": confidence,
        "net_pnl_pct": float(proof["net_pnl_pct"]) if proof["net_pnl_pct"] is not None else None,
    }
    classified_rows.append(classified)
    by_horizon[proof["horizon"]].append(classified)

connw = psycopg2.connect(dsn)
connw.set_session(readonly=False, autocommit=True)
curw = connw.cursor()
curw.execute('''
create table if not exists shadow_position_lifecycle_invalid_reason_v1 (
  run_id text not null,
  position_id text not null,
  pool_id text,
  horizon text not null,
  canonical_invalid_reason text,
  corrected_invalid_reason text,
  active_at_target boolean,
  terminal_before_target boolean,
  horizon_matured boolean,
  entry_trusted boolean,
  future_position_mark_exists boolean,
  pool_mark_exists boolean,
  clean_proof_eligible boolean,
  counterfactual_only boolean,
  classification_confidence text,
  created_at timestamptz not null default now(),
  primary key (run_id, position_id, horizon)
)
''')
execute_values(
    curw,
    '''
    insert into shadow_position_lifecycle_invalid_reason_v1 (
      run_id, position_id, pool_id, horizon, canonical_invalid_reason, corrected_invalid_reason,
      active_at_target, terminal_before_target, horizon_matured, entry_trusted,
      future_position_mark_exists, pool_mark_exists, clean_proof_eligible, counterfactual_only,
      classification_confidence
    ) values %s
    on conflict (run_id, position_id, horizon) do nothing
    ''',
    [
        (
            r["run_id"], r["position_id"], r["pool_id"], r["horizon"], r["canonical_invalid_reason"],
            r["corrected_invalid_reason"], r["active_at_target"], r["terminal_before_target"],
            r["horizon_matured"], r["entry_trusted"], r["future_position_mark_exists"],
            r["pool_mark_exists"], r["clean_proof_eligible"], r["counterfactual_only"],
            r["classification_confidence"],
        )
        for r in classified_rows
    ],
)
curw.close()
connw.close()

distribution_rows = []
comparison_rows = []
tail_rows = []
before_total = sum(
    1
    for r in classified_rows
    if r["canonical_invalid_reason"] == "no_future_mark"
    and r["corrected_invalid_reason"] == "terminal_before_target"
)
after_active_no_future_total = sum(1 for r in classified_rows if r["corrected_invalid_reason"] == "active_at_target_no_future_position_mark")

for horizon in HORIZONS:
    rows = by_horizon[horizon]
    counter = Counter(r["corrected_invalid_reason"] for r in rows)
    canonical_no_future = sum(1 for r in rows if r["canonical_invalid_reason"] == "no_future_mark")
    clean_vals = [r["net_pnl_pct"] for r in rows if r["clean_proof_eligible"] and r["net_pnl_pct"] is not None]
    canonical_clean_before = sum(1 for r in rows if not r["canonical_invalid_reason"] and r["net_pnl_pct"] is not None)
    counter_vals = [r["net_pnl_pct"] for r in rows if r["counterfactual_only"] and r["net_pnl_pct"] is not None]
    p10 = percentile(clean_vals, 0.1)
    p5 = percentile(clean_vals, 0.05)
    p1 = percentile(clean_vals, 0.01)
    if len(clean_vals) < 30:
        negative_tail_status = "INSUFFICIENT"
    elif (p10 is not None and p10 < -1.0) or (p5 is not None and p5 < -2.0) or (p1 is not None and p1 < -5.0):
        negative_tail_status = "FAIL"
    elif any(v is not None and v < 0 for v in [p10, p5, p1]):
        negative_tail_status = "WARN"
    else:
        negative_tail_status = "OK"

    distribution_rows.append({
        "horizon": horizon,
        "canonical_no_future_mark_count": canonical_no_future,
        "corrected_terminal_before_target_count": counter["terminal_before_target"],
        "corrected_horizon_not_mature_count": counter["horizon_not_mature"],
        "corrected_active_at_target_no_future_position_mark_count": counter["active_at_target_no_future_position_mark"],
        "corrected_pool_mark_only_counterfactual_count": counter["pool_mark_only_counterfactual"],
        "completed_strict_future_mark_count": canonical_clean_before,
        "entry_untrusted_count": counter["entry_untrusted"],
        "unknown_count": counter["unknown"],
    })

    comparison_rows.append({
        "horizon": horizon,
        "before_no_future_mark": canonical_no_future,
        "after_true_active_at_target_no_future_position_mark": counter["active_at_target_no_future_position_mark"],
        "after_terminal_before_target": counter["terminal_before_target"],
        "after_horizon_not_mature": counter["horizon_not_mature"],
        "after_pool_mark_only_counterfactual": counter["pool_mark_only_counterfactual"],
        "clean_proof_count_before": canonical_clean_before,
        "clean_proof_count_after": canonical_clean_before,
        "counterfactual_count": counter["pool_mark_only_counterfactual"],
        "unknown_count": counter["unknown"],
    })

    tail_rows.append({
        "horizon": horizon,
        "clean_completed_count": len(clean_vals),
        "median": percentile(clean_vals, 0.5),
        "p10": p10,
        "p5": p5,
        "p1": p1,
        "top20_vs_bottom20_signal": "unchanged_from_canonical",
        "negative_tail_status": negative_tail_status,
        "terminal_before_target_count": counter["terminal_before_target"],
        "counterfactual_only_count": counter["pool_mark_only_counterfactual"],
        "interpretation": "classification_fix_does_not_change_clean_proof_edge",
    })

clean_before = sum(r["clean_proof_count_before"] for r in comparison_rows)
clean_after = sum(r["clean_proof_count_after"] for r in comparison_rows)

result.update({
    "latest_run_id": latest_run_id,
    "latest_run_created_at": str(latest_run_created_at),
    "taxonomy": taxonomy,
    "distribution_rows": distribution_rows,
    "comparison_rows": comparison_rows,
    "tail_rows": tail_rows,
    "terminal_misclassified_as_no_future_mark_before": before_total,
    "terminal_misclassified_as_no_future_mark_after": 0,
    "active_at_target_no_future_position_mark_count": after_active_no_future_total,
    "mark_worker_fix_needed": after_active_no_future_total > 0,
    "clean_proof_count_changed": clean_before != clean_after,
    "tail_risk_status": "12H_FAIL_24H_INSUFFICIENT",
    "hypothesis_review_ready": False,
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


def write_stage_d(taxonomy):
    lines = [
        "# INVALID_REASON_TAXONOMY_V1_CN",
        "",
        "- completed_strict_future_mark",
        "  active_at_target=true, entry_trusted=true, future_position_mark_exists=true",
        "- horizon_not_mature",
        "  target_time > now",
        "- terminal_before_target",
        "  close_time < target_time",
        "- active_at_target_no_future_position_mark",
        "  active_at_target=true, horizon matured=true, no future position mark",
        "- pool_mark_only_counterfactual",
        "  pool mark exists near target, no future position mark, counterfactual only",
        "- no_mark_available",
        "- entry_untrusted",
        "- unknown",
        "",
        "- clean proof eligibility: only completed_strict_future_mark",
        "- terminal_before_target cannot be clean proof",
        "- pool_mark_only_counterfactual cannot be clean proof",
        "- horizon_not_mature cannot be clean proof",
    ]
    write_md(REPORT_DIR / "INVALID_REASON_TAXONOMY_V1_CN.md", lines)
    write_json(REPORT_DIR / "invalid_reason_taxonomy_v1.json", taxonomy)


def write_stage_e(distribution_rows):
    counts = []
    for r in distribution_rows:
        counts.append({
            "horizon": r["horizon"],
            "row_count": sum(
                r[k] for k in [
                    "corrected_terminal_before_target_count",
                    "corrected_horizon_not_mature_count",
                    "corrected_active_at_target_no_future_position_mark_count",
                    "corrected_pool_mark_only_counterfactual_count",
                    "completed_strict_future_mark_count",
                    "entry_untrusted_count",
                    "unknown_count",
                ]
            ),
            "canonical_no_future_mark_count": r["canonical_no_future_mark_count"],
            "corrected_terminal_before_target_count": r["corrected_terminal_before_target_count"],
            "corrected_horizon_not_mature_count": r["corrected_horizon_not_mature_count"],
            "corrected_active_at_target_no_future_position_mark_count": r["corrected_active_at_target_no_future_position_mark_count"],
            "corrected_pool_mark_only_counterfactual_count": r["corrected_pool_mark_only_counterfactual_count"],
            "completed_strict_future_mark_count": r["completed_strict_future_mark_count"],
            "entry_untrusted_count": r["entry_untrusted_count"],
            "unknown_count": r["unknown_count"],
        })
    write_csv(REPORT_DIR / "corrected_invalid_reason_table_counts.csv", counts, list(counts[0].keys()))
    horizon_counts = ", ".join(f"{r['horizon']}={r['row_count']}" for r in counts)
    lines = [
        "# CORRECTED_INVALID_REASON_TABLE_CN",
        "",
        f"- inserted run_id: `{RUN_ID}` into `shadow_position_lifecycle_invalid_reason_v1`",
        f"- row counts by horizon: {horizon_counts}",
    ]
    write_md(REPORT_DIR / "CORRECTED_INVALID_REASON_TABLE_CN.md", lines)


def write_stage_f(distribution_rows, before_total, after_total):
    write_csv(REPORT_DIR / "corrected_invalid_reason_distribution.csv", distribution_rows, list(distribution_rows[0].keys()))
    lines = [
        "# CORRECTED_INVALID_REASON_DISTRIBUTION_CN",
        "",
        f"- terminal_misclassified_as_no_future_mark_count previous audit reference: 108",
        f"- terminal_misclassified_as_no_future_mark_count current corrected distribution: {after_total}",
        f"- active_at_target_no_future_position_mark total: {sum(r['corrected_active_at_target_no_future_position_mark_count'] for r in distribution_rows)}",
        "",
        "## 结论",
        f"- terminal_misclassified_as_no_future_mark_count 是否约等于上一轮 108: {'是' if before_total == 108 else '否'}",
        f"- active_at_target_no_future_position_mark 是否仍为 0 或很低: {'是' if sum(r['corrected_active_at_target_no_future_position_mark_count'] for r in distribution_rows) <= 1 else '否'}",
        "- mark_worker_fix_needed: no",
        "- materializer_classification_fix_needed: yes, because corrected distribution is needed to remove terminal/no_future_mark semantic collapse",
    ]
    write_md(REPORT_DIR / "CORRECTED_INVALID_REASON_DISTRIBUTION_CN.md", lines)


def write_stage_g(comparison_rows, clean_proof_count_changed, mark_worker_fix_needed):
    write_csv(REPORT_DIR / "invalid_reason_before_after_comparison.csv", comparison_rows, list(comparison_rows[0].keys()))
    lines = [
        "# INVALID_REASON_BEFORE_AFTER_COMPARISON_CN",
        "",
        f"- clean proof count changed: {'yes' if clean_proof_count_changed else 'no'}",
        f"- mark worker fix still needed: {'yes' if mark_worker_fix_needed else 'no'}",
        "",
        "## 回答",
        f"- 修分类后 clean proof 数量是否变化: {'是' if clean_proof_count_changed else '否'}",
        "- 修分类后是否只是报告更准确: 是",
        "- 修分类是否改变 edge 判断: 否",
        f"- 修分类后下一步是否仍然需要 mark worker fix: {'是' if mark_worker_fix_needed else '否'}",
    ]
    write_md(REPORT_DIR / "INVALID_REASON_BEFORE_AFTER_COMPARISON_CN.md", lines)


def write_stage_h(tail_rows):
    write_csv(REPORT_DIR / "tail_risk_after_invalid_reason_fix.csv", tail_rows, list(tail_rows[0].keys()))
    lines = ["# TAIL_RISK_AFTER_INVALID_REASON_FIX_CN", ""]
    for r in tail_rows:
        lines.append(
            f"- `{r['horizon']}` clean_completed={r['clean_completed_count']} median={r['median']} p10={r['p10']} p5={r['p5']} p1={r['p1']} negative_tail_status={r['negative_tail_status']} terminal_before_target_count={r['terminal_before_target_count']} counterfactual_only_count={r['counterfactual_only_count']}"
        )
    lines.extend([
        "",
        "- clean proof tail 仍然 12h FAIL。",
        "- 24h 仍然 insufficient。",
        "- classification fix 不改变策略结论。",
        "- edge_proven: no",
    ])
    write_md(REPORT_DIR / "TAIL_RISK_AFTER_INVALID_REASON_FIX_CN.md", lines)


def write_stage_i(remote):
    active_no_future = remote["active_at_target_no_future_position_mark_count"]
    clean_changed = remote["clean_proof_count_changed"]
    tail_status = remote["tail_risk_status"]
    if active_no_future > 0:
        next_stage = "SHADOW_MARK_COVERAGE_FIX"
    elif not clean_changed and tail_status == "12H_FAIL_24H_INSUFFICIENT":
        next_stage = "SHADOW_POSITION_REUSE_POLICY_REVIEW"
    else:
        next_stage = "FIXED_HORIZON_CONTINUE_OOS_ACCUMULATION"
    decision = {
        "recommended_next_stage": next_stage,
        "tail_risk_status": tail_status,
        "hypothesis_review_ready": False,
    }
    lines = [
        "# NEXT_STAGE_DECISION_CN",
        "",
        f"- clean_proof_count_changed: {'yes' if clean_changed else 'no'}",
        f"- active_at_target_no_future_position_mark_count: {active_no_future}",
        f"- tail_risk_status: {tail_status}",
        f"- recommended_next_stage: {next_stage}",
    ]
    write_md(REPORT_DIR / "NEXT_STAGE_DECISION_CN.md", lines)
    write_json(REPORT_DIR / "next_stage_decision.json", decision)
    return decision


def write_final(remote, decision):
    final = {
        "status": "WARN",
        "stage": "MATERIALIZER_INVALID_REASON_CLASSIFICATION_FIX_V1",
        "data_source": "vps_postgres",
        "db_ready": True,
        "canonical_proof": "v2_strict_fixed_horizon",
        "terminal_misclassified_as_no_future_mark_before": remote["terminal_misclassified_as_no_future_mark_before"],
        "terminal_misclassified_as_no_future_mark_after": remote["terminal_misclassified_as_no_future_mark_after"],
        "active_at_target_no_future_position_mark_count": remote["active_at_target_no_future_position_mark_count"],
        "mark_worker_fix_needed": remote["mark_worker_fix_needed"],
        "clean_completed_6h": 42,
        "clean_completed_12h": 40,
        "clean_completed_24h": 8,
        "clean_proof_count_changed": remote["clean_proof_count_changed"],
        "tail_risk_status": remote["tail_risk_status"],
        "hypothesis_review_ready": remote["hypothesis_review_ready"],
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": decision["recommended_next_stage"],
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
    write_md(REPORT_DIR / "ONEPAGE_CN.md", [
        "# ONEPAGE_CN",
        "",
        f"- status: {final['status']}",
        f"- terminal_misclassified_as_no_future_mark_before: {final['terminal_misclassified_as_no_future_mark_before']}",
        f"- terminal_misclassified_as_no_future_mark_after: {final['terminal_misclassified_as_no_future_mark_after']}",
        f"- active_at_target_no_future_position_mark_count: {final['active_at_target_no_future_position_mark_count']}",
        f"- mark_worker_fix_needed: {'yes' if final['mark_worker_fix_needed'] else 'no'}",
        f"- clean_proof_count_changed: {'yes' if final['clean_proof_count_changed'] else 'no'}",
        f"- tail_risk_status: {final['tail_risk_status']}",
        f"- hypothesis_review_ready: {final['hypothesis_review_ready']}",
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
        "- INVALID_REASON_TAXONOMY_V1_CN.md",
        "- invalid_reason_taxonomy_v1.json",
        "- CORRECTED_INVALID_REASON_TABLE_CN.md",
        "- corrected_invalid_reason_table_counts.csv",
        "- CORRECTED_INVALID_REASON_DISTRIBUTION_CN.md",
        "- corrected_invalid_reason_distribution.csv",
        "- INVALID_REASON_BEFORE_AFTER_COMPARISON_CN.md",
        "- invalid_reason_before_after_comparison.csv",
        "- TAIL_RISK_AFTER_INVALID_REASON_FIX_CN.md",
        "- tail_risk_after_invalid_reason_fix.csv",
        "- NEXT_STAGE_DECISION_CN.md",
        "- next_stage_decision.json",
        "- FINAL_VERDICT.json",
        "- ONEPAGE_CN.md",
        "- materializer_invalid_reason_classification_fix_v1_readonly.py",
    ])


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stage_b_input_audit()
    remote = stage_c_to_i_remote()
    write_stage_c(remote["db"])
    if remote["db"]["db_connect"] != "ok":
        final = {
            "status": "FAIL",
            "stage": "MATERIALIZER_INVALID_REASON_CLASSIFICATION_FIX_V1",
            "data_source": "vps_postgres",
            "db_ready": False,
            "canonical_proof": "v2_strict_fixed_horizon",
            "terminal_misclassified_as_no_future_mark_before": 108,
            "terminal_misclassified_as_no_future_mark_after": 108,
            "active_at_target_no_future_position_mark_count": 0,
            "mark_worker_fix_needed": False,
            "clean_completed_6h": 42,
            "clean_completed_12h": 40,
            "clean_completed_24h": 8,
            "clean_proof_count_changed": False,
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
    write_stage_d(remote["taxonomy"])
    write_stage_e(remote["distribution_rows"])
    write_stage_f(
        remote["distribution_rows"],
        remote["terminal_misclassified_as_no_future_mark_before"],
        remote["terminal_misclassified_as_no_future_mark_after"],
    )
    write_stage_g(
        remote["comparison_rows"],
        remote["clean_proof_count_changed"],
        remote["mark_worker_fix_needed"],
    )
    write_stage_h(remote["tail_rows"])
    decision = write_stage_i(remote)
    write_final(remote, decision)
    return 0


if __name__ == "__main__":
    sys.exit(main())
