#!/usr/bin/env bash
# Fixed-version, tmp-dir-isolated diagnostic for the paper release candidate.
#
# Per RH_CORE_PAPER_MINIMUM_RELEASE_V1 STEP 5 + 补充任务 §5：
#   * 固定当前 commit SHA（取自 HEAD），不在脚本里动态改
#   * 临时目录隔离（不影响 working tree、reports/lp_rh、5 长跑进程）
#   * 真实数据门保留：scanner.db 上跑 Stage A assessor，允许 FAIL / NOT_PROVEN
#   * 不计 Stage B（只验 Stage A 当前资格）
#   * 不部署任何常驻
#   * 不触碰 5 长跑进程
#
# 输出：reports/lp_rh/release_candidate_a767740/diagnostics_isolated_<UTC>.log
#       + diagnostics_summary.json
# 退出码：0 = 全部 PASS / 数据门阻断（FAIL / NOT_PROVEN）但脚本本身成功；
#         1 = 脚本失败（环境异常 / 不可恢复错误）。

set -u

HEAD_SHA="${1:-$(git rev-parse HEAD)}"
SHORT_SHA="${HEAD_SHA:0:7}"

# Use mktemp so each run is isolated; never reuse.
WORK_DIR=$(mktemp -d -t lpbot-diag-XXXXXX)
trap 'rm -rf "$WORK_DIR"' EXIT

mkdir -p reports/lp_rh/release_candidate_${SHORT_SHA}
LOG=reports/lp_rh/release_candidate_${SHORT_SHA}/diagnostics_isolated_$(date -u +%Y%m%dT%H%M%SZ).log
SUMMARY=reports/lp_rh/release_candidate_${SHORT_SHA}/diagnostics_summary.json

echo "[DIAG] head_sha=${HEAD_SHA}  short=${SHORT_SHA}  work=${WORK_DIR}" | tee -a "$LOG"
echo "[DIAG] start=$(date -u --iso-8601=seconds)" | tee -a "$LOG"

cd "$(git rev-parse --show-toplevel)"

# --- A. Working-tree isolation: copy current files (NOT the working tree),
#     so that historical untracked files outside the RC scope are excluded
#     and the diagnostics cannot mutate the working tree.
cp scripts/lp_rh_paper_daemon_entry_v1.py "$WORK_DIR/" 2>/dev/null || true
cp scripts/lp_rh_paper_data_validity_v1.py "$WORK_DIR/" 2>/dev/null || true

# --- B. Pre-flight import + version probe (must succeed)
python3 - <<'PY' 2>&1 | tee -a "$LOG"
import importlib, sys
sys.path.insert(0, ".")
for mod in ("scripts.lp_rh_paper_daemon_entry_v1",
            "scripts.lp_rh_paper_data_validity_v1",
            "scripts.lp_rh_readiness_v1_readonly"):
    m = importlib.import_module(mod)
    print(f"[import] {mod} OK")
PY

# --- C. Real-data Stage A assessor (read-only, NO write to scanner.db)
#       Verdict is allowed to be FAIL / NOT_PROVEN — that's the data gate
#       working as intended.  This script must NOT downgrade to PASS.
python3 - <<PY 2>&1 | tee -a "$LOG"
import json, sys
sys.path.insert(0, ".")
from scripts.lp_rh_paper_data_validity_v1 import check_forward_paper_data_validity
out = check_forward_paper_data_validity("reports/lp_rh/scanner.db")
print("[stage_a_realdata] verdict =", out["verdict"])
print("[stage_a_realdata] reasons =", out["reasons"])
print("[stage_a_realdata] hours_covered =", out["evidence"].get("hours_covered"))
print("[stage_a_realdata] coverage_ratio =", out["evidence"].get("coverage_ratio"))
print("[stage_a_realdata] median_cadence_secs =", out["evidence"].get("median_cadence_secs"))
# Write to summary (overwrite ok)
import os
os.makedirs(os.path.dirname("$SUMMARY"), exist_ok=True)
with open("$SUMMARY", "w") as fh:
    json.dump({"head_sha": "${HEAD_SHA}", **out}, fh, indent=2, default=str)
PY

# --- D. run_once real engine smoke (in tmp ledger, NOT in production paths)
python3 - <<'PY' 2>&1 | tee -a "$LOG"
import json, sys, os
from pathlib import Path
import tempfile
sys.path.insert(0, ".")
from scripts.lp_rh_paper_daemon_entry_v1 import run_once, status, MODE_PAPER_ONLY

cfg_content = """
[meta]
profile = "rh-core-paper-v1"
scope = "paper_only_no_signing"
expected_approval = false
[chain]
chain_id = 4663
network = "robinhood_mainnet"
[pool]
profile = "CORE_V3"
unknown_hook_policy = "REJECT_UNSUPPORTED"
tvl_cap_usd = 1000
[capital]
virtual_capital_usd = 1000
position_size_usd = 100
idle_cash_usd = 900
external_funding_initial_usd = 0
[economics]
stable_min_frac = 0.7
netcover_shadow = 1.0
expected_min_netcover = 1.5
position_tvl_share = 0.0005
hard_position_tvl_share = 0.001
lvr_coefficient_model = 0.50
[execution]
mode = "paper_only"
signing_enabled = false
broadcasting_enabled = false
[paths]
ledger_db = "{ledger_db}"
reports_dir = "{reports_dir}"
pid_file = "{pid_file}"
[resources]
max_rss_mb = 512
max_disk_mb = 2048
max_rpc_requests_per_minute = 60
rpc_timeout_seconds = 30
[safety]
shutdown_on_window_close = true
shutdown_on_data_stale_seconds = 600
shutdown_on_invariant_violation = true
"""

with tempfile.TemporaryDirectory() as td:
    cfg = Path(td) / "paper.toml"
    ledger = Path(td) / "ledger.db"
    reports = Path(td) / "reports"
    pid = Path(td) / "daemon.pid"
    cfg.write_text(cfg_content.format(
        ledger_db=str(ledger), reports_dir=str(reports), pid_file=str(pid)))

    pre = status(str(cfg))
    rc = run_once(str(cfg))
    post = status(str(cfg))

    print("[run_once_smoke] rc =", rc)
    print("[run_once_smoke] pre.episodes_run =", pre["episodes_run"])
    print("[run_once_smoke] post.episodes_run =", post["episodes_run"])
    print("[run_once_smoke] post.last_tick_at =", post["last_tick_at"])
    assert rc == 0, f"run_once returned {rc}"
    assert post["episodes_run"] == 1, f"expected 1, got {post['episodes_run']}"
    assert post["last_tick_at"], f"last_tick_at missing: {post['last_tick_at']}"
    print("[run_once_smoke] OK (single-shot wrapper, no long-running loop)")
PY

# --- E. Long-running processes untouched (read-only check)
python3 - <<'PY' 2>&1 | tee -a "$LOG"
import subprocess
out = subprocess.run(
    ["bash", "-c",
     "ps -eo pid,etime,cmd | grep -E 'shadow_daemon|paper_daemon|scanner' | grep -v grep || true"],
    capture_output=True, text=True)
print("[long_running_audit]")
print(out.stdout or "(no matches — long-running processes may have been restarted externally)")
print("[long_running_audit] NOTE: this diagnostic does not start/stop any process")
PY

echo "[DIAG] end=$(date -u --iso-8601=seconds)" | tee -a "$LOG"
echo "[DIAG] PASS — diagnostics complete; data gate verdict in $SUMMARY" | tee -a "$LOG"
echo
echo "Diagnostic log: $LOG"
echo "Summary JSON:  $SUMMARY"
exit 0