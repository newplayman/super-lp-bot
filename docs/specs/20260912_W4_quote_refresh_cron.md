# W4 Spec: Quote refresh cron + offline verification

## GOAL
Generate a systemd timer + service definition for `scripts/lp_rh_quote_refresh_v1.py`, plus a wrapper cron script that adds PID locking, timeout, and structured failure logging. Provide install/uninstall/status shell scripts. All operations are **read-only in the local filesystem**; **actual enable** is BLOCKED_BY_OWNER_FREEZE — the systemd unit files are written but not enabled.

## CONTEXT
- Source script: `scripts/lp_rh_quote_refresh_v1.py` with `build_quote_refresh()` at `:46` and `apply_to_pool_meta()` at `:112`.
- Existing systemd precedent: `deploy/systemd/lpbot-shadow.service` and similar. Use these as a template.
- `flock` precedent at `scripts/capture_shadow_observation_snapshot.sh:1045,1077` — single-instance lock via file-based PID.
- 5-min cron precedent: `scripts/lp_rh_collector_watchdog.sh` is invoked every 5 minutes by external cron.
- `OnCalendar=*:*/5` is the established cadence in similar systems.

## TARGET FILES

### NEW: `scripts/lp_rh_quote_refresh_cron.py`
- Shebang: `#!/usr/bin/env python3`. Single-shot script (one invocation = one refresh cycle).
- PID lock via `/var/run/lpbot-quote-refresh.pid`:
  - If file exists and PID inside is alive (`os.kill(pid, 0)` returns no exception): log to stderr + exit 2.
  - If file exists but PID is dead: overwrite atomically.
  - On exit (success or failure), remove the PID file.
- Timeout: wrap `build_quote_refresh()` call in `signal.alarm(120)`; on timeout, exit 124 and write a failure row.
- Call sequence:
  1. `from scripts.lp_rh_quote_refresh_v1 import build_quote_refresh, apply_to_pool_meta`
  2. Build refresh object, apply to pool_meta JSON, write to `reports/lp_rh/pool_meta.json`.
  3. On success: append `{ts, "success": true, "applied_to": pool_meta_path, "duration_ms": ...}` to `reports/quote_refresh/cron_success.jsonl`.
  4. On failure: append `{ts, "success": false, "error": repr(exc), "exit_code": ...}` to `reports/quote_refresh/cron_failures.jsonl`. Then exit with non-zero code.
- Logger: use Python `logging` to stderr only; do NOT spam stdout.

### NEW: `deploy/systemd/lpbot-quote-refresh.service`
- Unit file. `Type=oneshot`. `ExecStart=/usr/bin/python3 /opt/lpbot/lp-bot-v3-origin-check/scripts/lp_rh_quote_refresh_cron.py`. `User=lpbot` (or `root` if no `lpbot` user exists; document the choice). `StandardOutput=append:/var/log/lpbot/quote-refresh.log`.

### NEW: `deploy/systemd/lpbot-quote-refresh.timer`
- `[Timer]` `OnCalendar=*:*/5`. `Persistent=true`. `AccuracySec=10s`.
- `[Install]` `WantedBy=timers.target`.

### NEW: `deploy/systemd/install-quote-refresh.sh`
- Bash script. Idempotent. Steps:
  1. Verify file presence of `.service` and `.timer`.
  2. `cp` them to `/etc/systemd/system/` (requires sudo).
  3. `systemctl daemon-reload` (skip if not root; print message instead).
  4. Print `[BLOCKED_BY_OWNER_FREEZE] NOT enabling timer. Run 'systemctl enable --now lpbot-quote-refresh.timer' manually after Owner approval.`
  5. Exit 0.

### NEW: `deploy/systemd/uninstall-quote-refresh.sh`
- Bash script. Idempotent. Steps:
  1. `systemctl disable --now lpbot-quote-refresh.timer` (skip if not root; print message).
  2. `rm` service + timer from `/etc/systemd/system/` (skip if not root).
  3. `systemctl daemon-reload` (skip if not root).
  4. Print `[OK] Quote refresh cron config removed.`

### NEW: `deploy/systemd/status-quote-refresh.sh`
- Bash script. Reports:
  - Whether systemd unit files are installed (`-f /etc/systemd/system/lpbot-quote-refresh.{service,timer}`).
  - Whether the timer is enabled (`systemctl is-enabled`).
  - Whether the last successful refresh is fresh (`stat -c %y reports/lp_rh/pool_meta.json` < 30 min old).
  - Whether the last failure log has entries (`wc -l reports/quote_refresh/cron_failures.jsonl`).
  - Print `[BLOCKED_BY_OWNER_FREEZE]` banner if the timer is NOT enabled.

### NEW: `tests/test_lp_rh_quote_refresh_cron_v1.py`
- `test_pid_lock_blocks_concurrent_run`: invoke script twice in subprocess; second one exits 2 with "PID lock held".
- `test_timeout_exit_124`: monkeypatch `build_quote_refresh` to `time.sleep(300)`; expect exit 124 within 130 seconds. (Use 5-second sleep + `signal.alarm` for testability; replace production 120 with 5 in a test-only override if needed via env var.)
- `test_failure_writes_jsonl`: monkeypatch to raise; expect exit non-zero + 1 line in cron_failures.jsonl.
- `test_success_writes_jsonl`: monkeypatch success path; expect exit 0 + 1 line in cron_success.jsonl.
- `test_pool_meta_json_written`: success path produces/updates `reports/lp_rh/pool_meta.json`.

## CWD
`/opt/lpbot/lp-bot-v3-origin-check`

## CONSTRAINTS
- READ-ONLY on existing files except `scripts/lp_rh_quote_refresh_v1.py` (READ-ONLY — do not modify).
- Do NOT modify any existing systemd units (`lpbot-shadow.service` etc.).
- Do NOT touch `internal/`, `configs/`, `internal/platform/`.
- The cron script is **standalone** — does NOT import daemon, broadcaster, signer.
- PID lock file path is configurable via `LPBOT_QUOTE_REFRESH_PIDFILE` env var; default `/var/run/lpbot-quote-refresh.pid`. Tests override to a tmp path.
- Timeout is configurable via `LPBOT_QUOTE_REFRESH_TIMEOUT_SECS`; default 120.
- Install/uninstall scripts MUST NOT actually enable the timer (BLOCKED_BY_OWNER_FREEZE). Print banner instead.
- Single Write/Edit ≤150 lines or 6000 characters.

## DELIVERABLES
- `scripts/lp_rh_quote_refresh_cron.py` (≤200 lines)
- `deploy/systemd/lpbot-quote-refresh.service` (≤25 lines)
- `deploy/systemd/lpbot-quote-refresh.timer` (≤15 lines)
- `deploy/systemd/install-quote-refresh.sh` (≤40 lines)
- `deploy/systemd/uninstall-quote-refresh.sh` (≤30 lines)
- `deploy/systemd/status-quote-refresh.sh` (≤60 lines)
- `tests/test_lp_rh_quote_refresh_cron_v1.py` (≤200 lines)
- `git status --short` and `git diff --stat` at end.

## VALIDATION
```bash
# 1. Unit tests pass
python3 -m pytest tests/test_lp_rh_quote_refresh_cron_v1.py -v

# 2. Dry-run via wrapper script
LPBOT_QUOTE_REFRESH_PIDFILE=/tmp/qr.pid LPBOT_QUOTE_REFRESH_TIMEOUT_SECS=10 \
  python3 scripts/lp_rh_quote_refresh_cron.py
echo "exit=$?"
ls -la reports/quote_refresh/

# 3. PID lock prevents concurrent run
LPBOT_QUOTE_REFRESH_PIDFILE=/tmp/qr.pid LPBOT_QUOTE_REFRESH_TIMEOUT_SECS=10 \
  python3 scripts/lp_rh_quote_refresh_cron.py &
sleep 1
LPBOT_QUOTE_REFRESH_PIDFILE=/tmp/qr.pid LPBOT_QUOTE_REFRESH_TIMEOUT_SECS=10 \
  python3 scripts/lp_rh_quote_refresh_cron.py 2>&1 | grep -i "lock"
echo "second_exit=$?"  # should be 2

# 4. systemd unit syntax check
systemd-analyze verify deploy/systemd/lpbot-quote-refresh.service 2>&1 | head -10 || echo "(systemd-analyze not present; skipping)"

# 5. install script is BLOCKED (does not actually enable)
sudo bash deploy/systemd/install-quote-refresh.sh 2>&1 | tail -5
echo "post-install systemctl is-enabled lpbot-quote-refresh.timer:"
systemctl is-enabled lpbot-quote-refresh.timer 2>&1 || echo "disabled"

# 6. Full pytest — no regression
python3 -m pytest tests/ -q --tb=line -p no:cacheprovider 2>&1 | tail -3
```

## UNRESOLVED (mark in report if hit)
- Test fails because `build_quote_refresh` cannot be monkeypatched via import path → mark BLOCKED, do not silently skip.
- systemd unit syntax error → return exact error.
- Need to modify `scripts/lp_rh_quote_refresh_v1.py` for any reason → mark BLOCKED.

## FAILURE HANDLING
If any validation step fails, return the original error + which test failed + last 30 lines of pytest output. Do NOT modify the spec. Do NOT skip tests. Do NOT silence errors with try/except.