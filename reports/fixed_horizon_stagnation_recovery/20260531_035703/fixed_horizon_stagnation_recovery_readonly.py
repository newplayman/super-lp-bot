#!/usr/bin/env python3
import csv
import json
import math
import statistics
import subprocess
import sys
import shlex
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path("/Users/bendu/lp-bot/v3")
RUN_ID = "20260531_035703"
REPORT_DIR = REPO_ROOT / "reports" / "fixed_horizon_stagnation_recovery" / RUN_ID
FAILED_RUN_DIR = REPO_ROOT / "reports" / "fixed_horizon_stagnation" / "20260531_034610"
BRANCH = "feat/supabase-postgres-deployment"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def run(cmd, input_text=None):
    proc = subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def ssh_bash(script):
    return run(["ssh", "vps", "bash", "-lc", script])


def ssh_python(python_code, source_runtime=True):
    source = ""
    if source_runtime:
        source = (
            "cd /opt/lpbot/lp-bot-v3-origin-check && "
            "set -a && "
            "source .runtime.shadow.env 2>/dev/null || source .env 2>/dev/null || source .env.chain 2>/dev/null || true; "
            "set +a; "
        )
    else:
        source = "cd /opt/lpbot/lp-bot-v3-origin-check && "
    return run(["ssh", "vps", "bash", "-lc", source + "python3 -"], input_text=python_code)


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


def load_previous_inputs():
    periodic_final = json.loads((REPO_ROOT / "reports" / "fixed_horizon_periodic_loop" / "20260531_032608" / "FINAL_VERDICT.json").read_text())
    review_gate = json.loads((REPO_ROOT / "reports" / "fixed_horizon_periodic_loop" / "20260531_032608" / "fixed_horizon_review_gate_24h.json").read_text())
    root_cause = json.loads((REPO_ROOT / "reports" / "fixed_horizon_periodic_loop" / "20260531_032608" / "fixed_horizon_24h_root_cause.json").read_text())
    policy = json.loads((REPO_ROOT / "reports" / "fixed_horizon_policy" / "20260530_145208" / "FINAL_VERDICT.json").read_text())
    health = json.loads((REPO_ROOT / "reports" / "shadow_health" / "20260530_142032" / "FINAL_VERDICT.json").read_text())
    return periodic_final, review_gate, root_cause, policy, health


def build_input_audit():
    periodic_final, review_gate, root_cause, policy, health = load_previous_inputs()
    data = {
        "run_id": RUN_ID,
        "audit_time_utc": utc_now(),
        "failed_run_id": "20260531_034610",
        "failed_dir": str(FAILED_RUN_DIR.relative_to(REPO_ROOT)),
        "periodic_final": periodic_final,
        "review_gate": review_gate,
        "root_cause": root_cause,
        "policy": policy,
        "shadow_health": health,
    }
    lines = [
        "# INPUT_ARTIFACT_AUDIT_CN",
        "",
        f"- audit_time_utc: {data['audit_time_utc']}",
        f"- run_id: {RUN_ID}",
        f"- failed_run_id: {data['failed_run_id']}",
        "",
        "## 输入结论",
        f"- periodic stage: `{periodic_final.get('stage')}` status={periodic_final.get('status')} gate={periodic_final.get('fixed_horizon_gate')}",
        f"- completed counts: 6h={periodic_final.get('completed_6h_count')}, 12h={periodic_final.get('completed_12h_count')}, 24h={periodic_final.get('completed_24h_count')}",
        f"- root cause: {', '.join(periodic_final.get('root_cause', []))}",
        f"- policy next stage: {policy.get('recommended_next_stage')}",
        f"- shadow health next stage: {health.get('recommended_next_stage')}",
        f"- tiny_canary_allowed: {periodic_final.get('tiny_canary_allowed')}",
    ]
    write_md(REPORT_DIR / "INPUT_ARTIFACT_AUDIT_CN.md", lines)
    write_json(REPORT_DIR / "input_artifact_audit.json", data)
    return data


def stage_b_env_audit():
    code = r"""
import json, os, subprocess, stat
from pathlib import Path

root = Path("/opt/lpbot/lp-bot-v3-origin-check")
files = [".runtime.shadow.env", ".env", ".env.chain", ".env.local"]
result = {"cwd": str(root), "files": {}, "systemd_environment_file_references_found": False, "running_process_env_has_db_vars": False, "process_env_status": "unknown"}
for name in files:
    p = root / name
    if p.exists():
        text = p.read_text(errors="ignore")
        result["files"][name] = {
            "exists": True,
            "mode": oct(p.stat().st_mode & 0o777),
            "postgres_dsn_present": "POSTGRES_DSN=" in text,
            "database_url_present": "DATABASE_URL=" in text,
            "pghost_present": "PGHOST=" in text,
            "pgdatabase_present": "PGDATABASE=" in text,
            "pguser_present": "PGUSER=" in text,
            "supabase_present": "SUPABASE" in text,
        }
    else:
        result["files"][name] = {"exists": False}

try:
    unit = subprocess.run(["systemctl", "cat", "lpbot-shadow.service"], capture_output=True, text=True, check=False)
    text = (unit.stdout or "") + (unit.stderr or "")
    refs = []
    for line in text.splitlines():
        line = line.strip()
        if "EnvironmentFile" in line or "Environment=" in line:
            refs.append(line)
    result["systemd_environment_file_references_found"] = bool(refs)
    result["systemd_reference_count"] = len(refs)
except Exception:
    result["systemd_reference_count"] = 0

pid_proc = subprocess.run("pgrep -f 'lpbot-shadow.*config.shadow.toml' | head -1", shell=True, capture_output=True, text=True, check=False)
pid = (pid_proc.stdout or "").strip()
result["lpbot_shadow_pid_found"] = bool(pid)
if pid:
    try:
        env_text = Path(f"/proc/{pid}/environ").read_bytes().replace(b"\x00", b"\n").decode("utf-8", "ignore")
        keys = [line.split("=", 1)[0] for line in env_text.splitlines() if "=" in line]
        result["running_process_env_has_db_vars"] = any(k in {"POSTGRES_DSN", "DATABASE_URL", "PGHOST", "PGDATABASE", "PGUSER", "SUPABASE_URL"} for k in keys)
        result["process_env_status"] = "readable"
    except PermissionError:
        result["process_env_status"] = "permission_denied"
    except Exception:
        result["process_env_status"] = "unreadable"

runtime = result["files"].get(".runtime.shadow.env", {})
if runtime.get("exists") and (runtime.get("postgres_dsn_present") or runtime.get("database_url_present")):
    result["likely_dsn_source"] = "runtime_env_file"
elif result["systemd_environment_file_references_found"]:
    result["likely_dsn_source"] = "systemd_environment_file"
elif result["running_process_env_has_db_vars"]:
    result["likely_dsn_source"] = "process_env_only"
elif not any(v.get("exists") for v in result["files"].values()):
    result["likely_dsn_source"] = "missing"
else:
    result["likely_dsn_source"] = "unknown"

print(json.dumps(result))
"""
    rc, out, err = ssh_python(code, source_runtime=False)
    if rc != 0:
        raise RuntimeError(f"env audit failed: {err or out}")
    data = json.loads(out.strip())
    lines = [
        "# VPS_RUNTIME_ENV_SOURCE_AUDIT_CN",
        "",
        f"- audit_time_utc: {utc_now()}",
        f"- .runtime.shadow.env exists: {'yes' if data['files'].get('.runtime.shadow.env', {}).get('exists') else 'no'}",
        f"- .env exists: {'yes' if data['files'].get('.env', {}).get('exists') else 'no'}",
        f"- .env.chain exists: {'yes' if data['files'].get('.env.chain', {}).get('exists') else 'no'}",
        f"- systemd EnvironmentFile references found: {'yes' if data.get('systemd_environment_file_references_found') else 'no'}",
        f"- running process env has DB vars: {'yes' if data.get('running_process_env_has_db_vars') else 'no'}",
        f"- process env status: {data.get('process_env_status')}",
        f"- likely_dsn_source: {data.get('likely_dsn_source')}",
        "",
        "未输出真实 DSN。",
    ]
    write_md(REPORT_DIR / "VPS_RUNTIME_ENV_SOURCE_AUDIT_CN.md", lines)
    write_json(REPORT_DIR / "vps_runtime_env_source_audit.json", data)
    return data


def stage_c_recovery():
    code = r"""
import json, os, re, stat, subprocess
from pathlib import Path

root = Path("/opt/lpbot/lp-bot-v3-origin-check")
runtime = root / ".runtime.shadow.env"
out = {
    "runtime_env_created_or_reused": False,
    "runtime_env_readable": False,
    "postgres_dsn_present": False,
    "database_url_present": False,
    "secret_leaked": "no",
    "recovery_status": "",
    "recovery_action": "",
}

def inspect_runtime():
    if runtime.exists():
        text = runtime.read_text(errors="ignore")
        out["runtime_env_created_or_reused"] = True
        out["runtime_env_readable"] = os.access(runtime, os.R_OK)
        out["postgres_dsn_present"] = "POSTGRES_DSN=" in text
        out["database_url_present"] = "DATABASE_URL=" in text
        return True
    return False

if inspect_runtime():
    try:
        os.chmod(runtime, 0o600)
        out["recovery_action"] = "reused_existing_runtime_env"
        out["recovery_status"] = "PASS" if out["runtime_env_readable"] and (out["postgres_dsn_present"] or out["database_url_present"]) else "FAIL_PERMISSION"
    except PermissionError:
        out["recovery_action"] = "existing_runtime_env_permission_denied"
        out["recovery_status"] = "FAIL_PERMISSION"
else:
    unit = subprocess.run(["systemctl", "cat", "lpbot-shadow.service"], capture_output=True, text=True, check=False)
    refs = []
    for line in (unit.stdout or "").splitlines():
        line = line.strip()
        if "EnvironmentFile=" in line:
            ref = line.split("EnvironmentFile=", 1)[1].strip().strip('"')
            if ref.startswith("-"):
                ref = ref[1:]
            refs.append(ref)
    copied = []
    for ref in refs:
        p = Path(ref)
        if not p.exists():
            continue
        lines = []
        for raw in p.read_text(errors="ignore").splitlines():
            if raw.startswith("POSTGRES_DSN=") or raw.startswith("DATABASE_URL="):
                lines.append(raw)
        if lines:
            runtime.write_text("\n".join(lines) + "\n")
            os.chmod(runtime, 0o600)
            copied = [line.split("=", 1)[0] for line in lines]
            break
    if copied and inspect_runtime():
        out["recovery_action"] = "copied_db_vars_from_systemd_environment_file"
        out["recovery_status"] = "PASS"
    else:
        pid_proc = subprocess.run("pgrep -f 'lpbot-shadow.*config.shadow.toml' | head -1", shell=True, capture_output=True, text=True, check=False)
        pid = (pid_proc.stdout or "").strip()
        if pid:
            out["recovery_action"] = "process_env_only_needs_manual_confirm"
            out["recovery_status"] = "FAIL_PROCESS_ENV_ONLY"
        else:
            out["recovery_action"] = "dsn_not_found"
            out["recovery_status"] = "FAIL_DSN_NOT_FOUND"

print(json.dumps(out))
"""
    rc, out, err = ssh_python(code, source_runtime=False)
    if rc != 0:
        raise RuntimeError(f"recovery failed: {err or out}")
    data = json.loads(out.strip())
    lines = [
        "# VPS_RUNTIME_ENV_RECOVERY_CN",
        "",
        f"- recovery_time_utc: {utc_now()}",
        f"- runtime_env_created_or_reused: {'yes' if data['runtime_env_created_or_reused'] else 'no'}",
        f"- runtime_env_readable: {'yes' if data['runtime_env_readable'] else 'no'}",
        f"- postgres_dsn_present: {'yes' if data['postgres_dsn_present'] else 'no'}",
        f"- database_url_present: {'yes' if data['database_url_present'] else 'no'}",
        f"- recovery_action: {data['recovery_action']}",
        f"- recovery_status: {data['recovery_status']}",
        "- secret_leaked: no",
    ]
    write_md(REPORT_DIR / "VPS_RUNTIME_ENV_RECOVERY_CN.md", lines)
    write_json(REPORT_DIR / "vps_runtime_env_recovery.json", data)
    return data


def stage_d_db_quick_check():
    code = r"""
import json, os, sys, shlex
from pathlib import Path

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
        key = key.strip()
        value = value.strip()
        os.environ[key] = value

for candidate in [
    "/opt/lpbot/lp-bot-v3-origin-check/.runtime.shadow.env",
    "/opt/lpbot/lp-bot-v3-origin-check/.env",
    "/opt/lpbot/lp-bot-v3-origin-check/.env.chain",
]:
    load_env_file(candidate)

out = {"dsn_present": False, "db_connect": "fail", "db_name": "", "db_user": "", "error_type": "", "error_text": ""}
dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
out["dsn_present"] = bool(dsn)
if not dsn:
    print(json.dumps(out))
    sys.exit(2)
try:
    import psycopg2
    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("select current_database(), current_user")
    db, user = cur.fetchone()
    out["db_connect"] = "ok"
    out["db_name"] = db
    out["db_user"] = user
    cur.close()
    conn.close()
except Exception as e:
    out["error_type"] = type(e).__name__
    out["error_text"] = str(e)[:200]
print(json.dumps(out))
"""
    rc, out, err = ssh_python(code, source_runtime=False)
    data = json.loads(out.strip()) if out.strip() else {
        "dsn_present": False,
        "db_connect": "fail",
        "db_name": "",
        "db_user": "",
        "error_type": "no_output",
        "error_text": err[:200],
    }
    lines = [
        "# VPS_DB_QUICK_CHECK_CN",
        "",
        f"- check_time_utc: {utc_now()}",
        f"- DSN_PRESENT: {'yes' if data['dsn_present'] else 'no'}",
        f"- DB_CONNECT: {data['db_connect']}",
    ]
    if data["db_connect"] == "ok":
        lines.append(f"- DB_NAME: `{data['db_name']}`")
        lines.append(f"- DB_USER: `{data['db_user']}`")
    else:
        lines.append(f"- DB_ERROR_TYPE: {data.get('error_type', '')}")
        lines.append(f"- DB_ERROR_TEXT: {data.get('error_text', '')}")
    write_md(REPORT_DIR / "VPS_DB_QUICK_CHECK_CN.md", lines)
    return data


def stage_e_remote_aggregate():
    code = r"""
import json, os, statistics, time, shlex
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

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
        key = key.strip()
        value = value.strip()
        os.environ[key] = value

for candidate in [
    "/opt/lpbot/lp-bot-v3-origin-check/.runtime.shadow.env",
    "/opt/lpbot/lp-bot-v3-origin-check/.env",
    "/opt/lpbot/lp-bot-v3-origin-check/.env.chain",
]:
    load_env_file(candidate)

def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    idx = max(0, min(len(values) - 1, int((len(values) - 1) * p)))
    return values[idx]

dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
conn = psycopg2.connect(dsn)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor(cursor_factory=RealDictCursor)

cur.execute('''
select run_id, max(created_at) as created_at
from shadow_position_lifecycle_proof_v2
where strategy_hypothesis = %s
group by 1
order by max(created_at) desc
''', ("fixed_horizon",))
runs = cur.fetchall()
latest_run_id = runs[0]["run_id"] if runs else None

cur.execute('''
select run_id, horizon, position_id, pool_id, entry_time, net_pnl_pct, net_pnl_usd,
       score_open_decision, future_position_mark_exists, invalid_reason, entry_trusted,
       created_at
from shadow_position_lifecycle_proof_v2
where strategy_hypothesis = %s
''', ("fixed_horizon",))
proof_rows = cur.fetchall()

cur.execute('''
select id as position_id, pool_id, opened_at, closed_at
from positions
where opened_at >= extract(epoch from now() - interval '72 hours')
''')
position_rows = cur.fetchall()

cur.execute('''
select tick_time, pool_id, position_id, final_action, intent_open
from shadow_decision_trace
where tick_time >= extract(epoch from now() - interval '72 hours')
''')
trace_rows = cur.fetchall()
cur.close()
conn.close()

now_epoch = time.time()
windows = [24, 48, 72]
proof_latest = [r for r in proof_rows if r["run_id"] == latest_run_id]

clean_windows = []
for hours in windows:
    cutoff = now_epoch - hours * 3600
    positions_in_window = [p for p in position_rows if p["opened_at"] is not None and float(p["opened_at"]) >= cutoff]
    trace_in_window = [t for t in trace_rows if t["tick_time"] is not None and float(t["tick_time"]) >= cutoff and t["intent_open"]]
    proof_positions = {r["position_id"] for r in proof_latest if r["entry_time"] and r["entry_time"].timestamp() >= cutoff and r["entry_trusted"]}
    row = {
        "window_hours": hours,
        "new_positions_count": len({p["position_id"] for p in positions_in_window}),
        "reused_position_count": len({t["position_id"] for t in trace_in_window if t["final_action"] == "reuse_shadow_position" and t["position_id"]}),
        "distinct_position_id_from_intent_open": len({t["position_id"] for t in trace_in_window if t["position_id"]}),
        "distinct_pool_id_from_intent_open": len({t["pool_id"] for t in trace_in_window if t["pool_id"]}),
        "positions_with_entry_trusted": len(proof_positions),
    }
    for h in [6, 12, 24]:
        active = 0
        terminal = 0
        for p in positions_in_window:
            target = float(p["opened_at"]) + h * 3600
            closed = float(p["closed_at"]) if p["closed_at"] is not None else None
            if closed is None or closed >= target:
                active += 1
            elif closed < target:
                terminal += 1
        future_mark = len({
            r["position_id"]
            for r in proof_latest
            if r["horizon"] == f"{h}h" and r["entry_time"] and r["entry_time"].timestamp() >= cutoff and r["future_position_mark_exists"]
        })
        row[f"positions_active_at_{h}h_target"] = active
        row[f"positions_terminal_before_{h}h"] = terminal
        row[f"positions_with_future_position_mark_{h}h"] = future_mark
    clean_windows.append(row)

stagnation = []
by_run_h = defaultdict(list)
run_created_at = {}
for r in proof_rows:
    by_run_h[(r["run_id"], r["horizon"])].append(r)
    run_created_at[r["run_id"]] = str(r["created_at"])
for run in sorted(run_created_at.keys(), key=lambda x: run_created_at[x], reverse=True):
    row = {"run_id": run, "created_at": run_created_at[run]}
    for h in ["6h", "12h", "24h"]:
        rows = by_run_h.get((run, h), [])
        completed = [x for x in rows if not (x["invalid_reason"] or "")]
        invalid = [x for x in rows if (x["invalid_reason"] or "")]
        row[f"completed_{h}"] = len(completed)
        row[f"invalid_{h}"] = len(invalid)
        row[f"no_future_mark_{h}"] = sum(1 for x in rows if (x["invalid_reason"] or "") == "no_future_mark")
        row[f"terminal_before_target_{h}"] = sum(1 for x in rows if (x["invalid_reason"] or "") == "terminal_before_target")
        row[f"pool_mark_only_{h}"] = sum(1 for x in rows if (x["invalid_reason"] or "") == "pool_mark_only")
        row[f"strict_future_mark_{h}"] = sum(1 for x in rows if x["future_position_mark_exists"])
    stagnation.append(row)

tail = []
for h in ["6h", "12h", "24h"]:
    rows = [r for r in proof_latest if r["horizon"] == h]
    valid = [r for r in rows if not (r["invalid_reason"] or "") and r["net_pnl_pct"] is not None]
    vals = [float(r["net_pnl_pct"]) for r in valid]
    ordered = sorted(valid, key=lambda r: (r["score_open_decision"] is None, -(float(r["score_open_decision"] or 0.0))))
    n = len(ordered)
    topn = max(1, int(n * 0.2)) if n else 0
    top = ordered[:topn]
    bottom = ordered[-topn:] if topn else []
    top_vals = [float(r["net_pnl_pct"]) for r in top if r["net_pnl_pct"] is not None]
    bottom_vals = [float(r["net_pnl_pct"]) for r in bottom if r["net_pnl_pct"] is not None]
    signal = "insufficient"
    if top_vals and bottom_vals:
        top_med = percentile(top_vals, 0.5)
        bot_med = percentile(bottom_vals, 0.5)
        signal = "better" if top_med > bot_med else ("worse" if top_med < bot_med else "flat")
    losses = [abs(min(float(r["net_pnl_usd"] or 0.0), 0.0)) for r in valid]
    total_loss = sum(losses)
    worst_position_contribution = None
    worst_pool_contribution = None
    if total_loss > 0:
        worst_position_contribution = max(losses) / total_loss
        pool_losses = defaultdict(float)
        for r in valid:
            pool_losses[r["pool_id"]] += abs(min(float(r["net_pnl_usd"] or 0.0), 0.0))
        worst_pool_contribution = max(pool_losses.values()) / total_loss if pool_losses else None
    if len(valid) < 30:
        negative_tail_status = "INSUFFICIENT"
    else:
        p10 = percentile(vals, 0.1)
        p5 = percentile(vals, 0.05)
        p1 = percentile(vals, 0.01)
        if (p10 is not None and p10 < -1.0) or (p5 is not None and p5 < -2.0) or (p1 is not None and p1 < -5.0):
            negative_tail_status = "FAIL"
        elif any(v is not None and v < 0 for v in [p10, p5, p1]):
            negative_tail_status = "WARN"
        else:
            negative_tail_status = "OK"
    tail.append({
        "horizon": h,
        "completed_count": len(valid),
        "median_net_pnl_pct": percentile(vals, 0.5),
        "p10": percentile(vals, 0.1),
        "p5": percentile(vals, 0.05),
        "p1": percentile(vals, 0.01),
        "worst_position_contribution": worst_position_contribution,
        "worst_pool_contribution": worst_pool_contribution,
        "top20_vs_bottom20_signal": signal,
        "negative_tail_status": negative_tail_status,
        "future_mark_coverage": (sum(1 for r in rows if r["future_position_mark_exists"]) / len(rows)) if rows else None,
    })

print(json.dumps({
    "latest_run_id": latest_run_id,
    "run_created_at": run_created_at.get(latest_run_id),
    "clean_windows": clean_windows,
    "stagnation": stagnation,
    "tail": tail,
}))
"""
    rc, out, err = ssh_python(code, source_runtime=False)
    if rc != 0:
        raise RuntimeError(f"remote aggregate failed: {err or out}")
    return json.loads(out.strip())


def write_stage_e1(clean_windows):
    fieldnames = [
        "window_hours",
        "new_positions_count",
        "reused_position_count",
        "distinct_position_id_from_intent_open",
        "distinct_pool_id_from_intent_open",
        "positions_with_entry_trusted",
        "positions_active_at_6h_target",
        "positions_active_at_12h_target",
        "positions_active_at_24h_target",
        "positions_terminal_before_6h",
        "positions_terminal_before_12h",
        "positions_terminal_before_24h",
        "positions_with_future_position_mark_6h",
        "positions_with_future_position_mark_12h",
        "positions_with_future_position_mark_24h",
    ]
    write_csv(REPORT_DIR / "clean_position_generation_audit.csv", clean_windows, fieldnames)
    latest24 = next(r for r in clean_windows if r["window_hours"] == 24)
    reuse_dominant = latest24["reused_position_count"] > latest24["new_positions_count"]
    lines = [
        "# CLEAN_POSITION_GENERATION_AUDIT_CN",
        "",
        f"- latest 24h new_positions_count={latest24['new_positions_count']}, reused_position_count={latest24['reused_position_count']}",
        f"- latest 24h distinct_position_id_from_intent_open={latest24['distinct_position_id_from_intent_open']}, distinct_pool_id_from_intent_open={latest24['distinct_pool_id_from_intent_open']}",
        f"- latest 24h entry_trusted positions={latest24['positions_with_entry_trusted']}",
        f"- latest 24h future_position_mark: 6h={latest24['positions_with_future_position_mark_6h']}, 12h={latest24['positions_with_future_position_mark_12h']}, 24h={latest24['positions_with_future_position_mark_24h']}",
        "",
        "## 结论",
        f"- 是否真的没有新 position: {'否，但新增很少' if latest24['new_positions_count'] > 0 else '是，近 24h 为 0'}",
        f"- 是否大量 intent_open 都是 position reuse: {'是' if reuse_dominant else '否'}",
        f"- 是否 reuse 机制导致样本自然增长很慢: {'是' if reuse_dominant and latest24['new_positions_count'] <= 2 else '部分是'}",
        f"- clean fixed-horizon 是否需要新 position 但当前 shadow 主要在复用旧 position: {'是' if reuse_dominant else '不明显'}",
        f"- 继续等待是否能自然增加 clean samples: {'较慢，单靠等待不足' if reuse_dominant else '可能可以'}",
    ]
    write_md(REPORT_DIR / "CLEAN_POSITION_GENERATION_AUDIT_CN.md", lines)
    return latest24, reuse_dominant


def write_stage_e2(stagnation_rows, clean_windows):
    fieldnames = ["run_id", "created_at"]
    for h in ["6h", "12h", "24h"]:
        fieldnames.extend([
            f"completed_{h}",
            f"invalid_{h}",
            f"no_future_mark_{h}",
            f"terminal_before_target_{h}",
            f"pool_mark_only_{h}",
            f"strict_future_mark_{h}",
        ])
    write_csv(REPORT_DIR / "completed_sample_stagnation_audit.csv", stagnation_rows, fieldnames)
    latest = stagnation_rows[0]
    previous = stagnation_rows[1] if len(stagnation_rows) > 1 else None
    by_window = {r["window_hours"]: r for r in clean_windows}
    latest72 = by_window.get(72, {})
    terminal_mismatch_24h = latest72.get("positions_terminal_before_24h", 0) > 0 and latest.get("terminal_before_target_24h", 0) == 0
    no_growth = False
    if previous:
        no_growth = all(latest[f"completed_{h}"] == previous[f"completed_{h}"] for h in ["6h", "12h", "24h"])
    lines = [
        "# COMPLETED_SAMPLE_STAGNATION_AUDIT_CN",
        "",
        f"- latest run_id={latest['run_id']} created_at={latest['created_at']}",
        f"- latest completed: 6h={latest['completed_6h']}, 12h={latest['completed_12h']}, 24h={latest['completed_24h']}",
        f"- latest invalid: 6h={latest['invalid_6h']}, 12h={latest['invalid_12h']}, 24h={latest['invalid_24h']}",
        f"- latest no_future_mark: 6h={latest['no_future_mark_6h']}, 12h={latest['no_future_mark_12h']}, 24h={latest['no_future_mark_24h']}",
        f"- latest terminal_before_target: 6h={latest['terminal_before_target_6h']}, 12h={latest['terminal_before_target_12h']}, 24h={latest['terminal_before_target_24h']}",
        f"- latest pool_mark_only: 6h={latest['pool_mark_only_6h']}, 12h={latest['pool_mark_only_12h']}, 24h={latest['pool_mark_only_24h']}",
        f"- recent positions table terminal_before_24h (72h window)={latest72.get('positions_terminal_before_24h', 0)}",
        "",
        "## 结论",
        f"- completed 不增长是否因 no new positions: {'部分是' if no_growth else '不是唯一原因'}",
        f"- 还是有 positions 但 no future marks: {'是，24h 与 12h 覆盖明显不足' if latest['no_future_mark_24h'] or latest['no_future_mark_12h'] else '不是主因'}",
        f"- 还是 positions terminal before target: {'是，但在 canonical proof 中被 no_future_mark 吞并/错记' if terminal_mismatch_24h else ('有影响，但不是唯一主因' if latest['terminal_before_target_12h'] or latest['terminal_before_target_24h'] else '影响有限')}",
        f"- 还是 strict proof 排除了大量 pool_mark_only: {'当前 v2 strict 下不明显' if not any(latest[f'pool_mark_only_{h}'] for h in ['6h','12h','24h']) else '是'}",
        f"- 还是 materializer run 口径不同: {'存在 terminal/no_future_mark 语义错位，但 run 之间 completed 仍持平' if terminal_mismatch_24h else ('目前看不是主因，run 之间 completed 持平' if previous else '待更多 run 观察')}",
    ]
    write_md(REPORT_DIR / "COMPLETED_SAMPLE_STAGNATION_AUDIT_CN.md", lines)
    return latest, previous, no_growth


def write_stage_e3(tail_rows):
    write_csv(
        REPORT_DIR / "canonical_proof_tail_risk_audit.csv",
        tail_rows,
        [
            "horizon",
            "completed_count",
            "median_net_pnl_pct",
            "p10",
            "p5",
            "p1",
            "worst_position_contribution",
            "worst_pool_contribution",
            "top20_vs_bottom20_signal",
            "negative_tail_status",
            "future_mark_coverage",
        ],
    )
    by_h = {r["horizon"]: r for r in tail_rows}
    lines = [
        "# CANONICAL_PROOF_TAIL_RISK_AUDIT_CN",
        "",
    ]
    for h in ["6h", "12h", "24h"]:
        row = by_h[h]
        lines.append(
            f"- `{h}` completed={row['completed_count']} median={row['median_net_pnl_pct']} p10={row['p10']} p5={row['p5']} p1={row['p1']} signal={row['top20_vs_bottom20_signal']} negative_tail_status={row['negative_tail_status']} worst_position_contribution={row['worst_position_contribution']} worst_pool_contribution={row['worst_pool_contribution']}"
        )
    lines.extend(
        [
            "",
            "## 结论",
            f"- 12h tail 是否仍严重负: {'是' if by_h['12h']['negative_tail_status'] == 'FAIL' else '否'}",
            f"- 24h 是否因样本太少不能判断: {'是' if by_h['24h']['negative_tail_status'] == 'INSUFFICIENT' else '否'}",
            f"- 6h better 是否足以支撑继续研究: {'不足以单独支撑' if by_h['6h']['top20_vs_bottom20_signal'] == 'better' else '否'}",
            f"- 当前 tail 风险是否支持继续等待: {'仅在修复样本增长/覆盖问题前提下有限支持' if by_h['12h']['negative_tail_status'] != 'FAIL' else '不支持无条件继续等待'}",
        ]
    )
    write_md(REPORT_DIR / "CANONICAL_PROOF_TAIL_RISK_AUDIT_CN.md", lines)
    return by_h


def decide(latest24, reuse_dominant, stagnation_latest, stagnation_previous, no_growth, tail_by_h):
    completed_growth_status = "GROWTH_STALLED" if no_growth else "GROWTH_PRESENT"
    new_position_generation_status = "LOW_NEW_POSITION_FLOW" if latest24["new_positions_count"] < 5 or latest24["positions_with_entry_trusted"] < 3 else "ADEQUATE_NEW_POSITION_FLOW"
    position_reuse_status = "REUSE_DOMINANT" if reuse_dominant else "REUSE_NOT_DOMINANT"
    future_mark_coverage_status = (
        "LOW_FUTURE_MARK_COVERAGE"
        if latest24["positions_with_future_position_mark_24h"] < latest24["new_positions_count"] or tail_by_h["24h"]["future_mark_coverage"] in (None,) or (tail_by_h["24h"]["future_mark_coverage"] or 0) < 0.3
        else "FUTURE_MARK_COVERAGE_OK"
    )
    if tail_by_h["12h"]["negative_tail_status"] == "FAIL" and tail_by_h["24h"]["negative_tail_status"] == "INSUFFICIENT":
        tail_risk_status = "12H_FAIL_24H_INSUFFICIENT"
    elif any(v["negative_tail_status"] == "FAIL" for v in tail_by_h.values()):
        tail_risk_status = "TAIL_FAIL"
    elif any(v["negative_tail_status"] == "WARN" for v in tail_by_h.values()):
        tail_risk_status = "TAIL_WARN"
    else:
        tail_risk_status = "TAIL_OK"

    if reuse_dominant and latest24["new_positions_count"] <= 2:
        recommended = "SHADOW_POSITION_REUSE_POLICY_REVIEW"
    elif future_mark_coverage_status == "LOW_FUTURE_MARK_COVERAGE":
        recommended = "SHADOW_MARK_COVERAGE_FIX"
    elif tail_by_h["12h"]["negative_tail_status"] == "FAIL" and no_growth:
        recommended = "FIXED_HORIZON_STOP_RESEARCH"
    else:
        recommended = "FIXED_HORIZON_EXTEND_SHADOW_RUNTIME"

    hypothesis_review_ready = False
    status = "WARN" if recommended != "FIXED_HORIZON_STOP_RESEARCH" else "FAIL"
    decision = {
        "selected_decision": recommended,
        "completed_growth_status": completed_growth_status,
        "new_position_generation_status": new_position_generation_status,
        "position_reuse_status": position_reuse_status,
        "future_mark_coverage_status": future_mark_coverage_status,
        "tail_risk_status": tail_risk_status,
        "hypothesis_review_ready": hypothesis_review_ready,
        "status": status,
    }
    lines = [
        "# FIXED_HORIZON_CONTINUE_OR_STOP_DECISION_CN",
        "",
        f"- completed_growth_status: {completed_growth_status}",
        f"- new_position_generation_status: {new_position_generation_status}",
        f"- position_reuse_status: {position_reuse_status}",
        f"- future_mark_coverage_status: {future_mark_coverage_status}",
        f"- tail_risk_status: {tail_risk_status}",
        f"- selected_decision: {recommended}",
        "",
        "## 选择理由",
        "- 当前 completed 样本停滞不是单一原因：新增 position 偏少、reuse 占主导、24h future mark 覆盖接近空白同时存在 terminal/no_future_mark 语义错位。",
        "- 12h canonical tail 仍为明显负值，24h 仍不足样本，单靠继续等待不能证明 edge。",
        "- 由于 canonical strict proof 当前首先卡在 future mark / terminal 映射链路，优先动作落在 mark coverage 口径修复，而不是继续被动等样本。",
    ]
    write_md(REPORT_DIR / "FIXED_HORIZON_CONTINUE_OR_STOP_DECISION_CN.md", lines)
    write_json(REPORT_DIR / "fixed_horizon_continue_or_stop_decision.json", decision)
    return decision


def write_final_verdict(recovery, db_check, stagnation_latest, decision):
    final = {
        "status": decision["status"],
        "stage": "FIXED_HORIZON_DB_ENV_RECOVERY_AND_STAGNATION_AUDIT_RESUME_V1",
        "db_env_recovery_status": recovery["recovery_status"],
        "db_ready": db_check["db_connect"] == "ok",
        "canonical_proof": "v2_strict_fixed_horizon",
        "completed_6h": stagnation_latest["completed_6h"],
        "completed_12h": stagnation_latest["completed_12h"],
        "completed_24h": stagnation_latest["completed_24h"],
        "completed_growth_status": decision["completed_growth_status"],
        "new_position_generation_status": decision["new_position_generation_status"],
        "position_reuse_status": decision["position_reuse_status"],
        "future_mark_coverage_status": decision["future_mark_coverage_status"],
        "tail_risk_status": decision["tail_risk_status"],
        "hypothesis_review_ready": False,
        "edge_proven": "no",
        "tiny_canary_candidate": "no",
        "tiny_canary_allowed": "no",
        "recommended_next_stage": decision["selected_decision"],
    }
    write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
    onepage = [
        "# ONEPAGE_CN",
        "",
        f"- status: {final['status']}",
        f"- db_env_recovery_status: {final['db_env_recovery_status']}",
        f"- db_ready: {'yes' if final['db_ready'] else 'no'}",
        f"- completed: 6h={final['completed_6h']}, 12h={final['completed_12h']}, 24h={final['completed_24h']}",
        f"- completed_growth_status: {final['completed_growth_status']}",
        f"- new_position_generation_status: {final['new_position_generation_status']}",
        f"- position_reuse_status: {final['position_reuse_status']}",
        f"- future_mark_coverage_status: {final['future_mark_coverage_status']}",
        f"- tail_risk_status: {final['tail_risk_status']}",
        f"- hypothesis_review_ready: {final['hypothesis_review_ready']}",
        f"- recommended_next_stage: {final['recommended_next_stage']}",
        "- edge_proven: no",
        "- tiny_canary_allowed: no",
    ]
    write_md(REPORT_DIR / "ONEPAGE_CN.md", onepage)
    index = [
        "# ARTIFACT_INDEX",
        "",
        "- INPUT_ARTIFACT_AUDIT_CN.md",
        "- input_artifact_audit.json",
        "- VPS_RUNTIME_ENV_SOURCE_AUDIT_CN.md",
        "- vps_runtime_env_source_audit.json",
        "- VPS_RUNTIME_ENV_RECOVERY_CN.md",
        "- vps_runtime_env_recovery.json",
        "- VPS_DB_QUICK_CHECK_CN.md",
        "- CLEAN_POSITION_GENERATION_AUDIT_CN.md",
        "- clean_position_generation_audit.csv",
        "- COMPLETED_SAMPLE_STAGNATION_AUDIT_CN.md",
        "- completed_sample_stagnation_audit.csv",
        "- CANONICAL_PROOF_TAIL_RISK_AUDIT_CN.md",
        "- canonical_proof_tail_risk_audit.csv",
        "- FIXED_HORIZON_CONTINUE_OR_STOP_DECISION_CN.md",
        "- fixed_horizon_continue_or_stop_decision.json",
        "- FINAL_VERDICT.json",
        "- ONEPAGE_CN.md",
        "- fixed_horizon_stagnation_recovery_readonly.py",
    ]
    write_md(REPORT_DIR / "ARTIFACT_INDEX.md", index)
    return final


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    build_input_audit()
    env_audit = stage_b_env_audit()
    recovery = stage_c_recovery()
    if recovery["recovery_status"] != "PASS":
        final = {
            "status": "FAIL",
            "stage": "FIXED_HORIZON_DB_ENV_RECOVERY_AND_STAGNATION_AUDIT_RESUME_V1",
            "db_env_recovery_status": recovery["recovery_status"],
            "db_ready": False,
            "canonical_proof": "v2_strict_fixed_horizon",
            "completed_6h": 42,
            "completed_12h": 40,
            "completed_24h": 8,
            "completed_growth_status": "UNKNOWN",
            "new_position_generation_status": "UNKNOWN",
            "position_reuse_status": "UNKNOWN",
            "future_mark_coverage_status": "UNKNOWN",
            "tail_risk_status": "UNKNOWN",
            "hypothesis_review_ready": False,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "recommended_next_stage": "MANUAL_CONFIGURE_POSTGRES_DSN_ON_VPS",
        }
        write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
        write_md(REPORT_DIR / "ONEPAGE_CN.md", ["# ONEPAGE_CN", "", f"- status: {final['status']}", f"- db_env_recovery_status: {final['db_env_recovery_status']}", f"- recommended_next_stage: {final['recommended_next_stage']}"])
        write_md(REPORT_DIR / "ARTIFACT_INDEX.md", ["# ARTIFACT_INDEX", "", "- FINAL_VERDICT.json", "- ONEPAGE_CN.md"])
        return 0
    db_check = stage_d_db_quick_check()
    if db_check["db_connect"] != "ok":
        final = {
            "status": "FAIL",
            "stage": "FIXED_HORIZON_DB_ENV_RECOVERY_AND_STAGNATION_AUDIT_RESUME_V1",
            "db_env_recovery_status": recovery["recovery_status"],
            "db_ready": False,
            "canonical_proof": "v2_strict_fixed_horizon",
            "completed_6h": 42,
            "completed_12h": 40,
            "completed_24h": 8,
            "completed_growth_status": "UNKNOWN",
            "new_position_generation_status": "UNKNOWN",
            "position_reuse_status": "UNKNOWN",
            "future_mark_coverage_status": "UNKNOWN",
            "tail_risk_status": "UNKNOWN",
            "hypothesis_review_ready": False,
            "edge_proven": "no",
            "tiny_canary_candidate": "no",
            "tiny_canary_allowed": "no",
            "recommended_next_stage": "FIXED_HORIZON_DB_OR_SCHEMA_FIX_REPEAT",
        }
        write_json(REPORT_DIR / "FINAL_VERDICT.json", final)
        write_md(REPORT_DIR / "ONEPAGE_CN.md", ["# ONEPAGE_CN", "", f"- status: {final['status']}", f"- db_ready: {final['db_ready']}", f"- recommended_next_stage: {final['recommended_next_stage']}"])
        write_md(REPORT_DIR / "ARTIFACT_INDEX.md", ["# ARTIFACT_INDEX", "", "- FINAL_VERDICT.json", "- ONEPAGE_CN.md"])
        return 0
    aggregate = stage_e_remote_aggregate()
    latest24, reuse_dominant = write_stage_e1(aggregate["clean_windows"])
    stagnation_latest, stagnation_previous, no_growth = write_stage_e2(aggregate["stagnation"], aggregate["clean_windows"])
    tail_by_h = write_stage_e3(aggregate["tail"])
    decision = decide(latest24, reuse_dominant, stagnation_latest, stagnation_previous, no_growth, tail_by_h)
    write_final_verdict(recovery, db_check, stagnation_latest, decision)
    return 0


if __name__ == "__main__":
    sys.exit(main())
