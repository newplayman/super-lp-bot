# Paper RH CORE Ops Runbook

**Profile**: `rh-core-paper-v1`
**Config**: `configs/paper_rh_core_v1.toml`
**Chain**: `robinhood_mainnet` (4663)
**Scope**: Paper only — no signing, no broadcasting, no real funds

> This runbook is operational documentation for the W5 paper deploy package.
> It does **not** authorize execution. Owner approval via
> `PAPER_APPROVAL_REQUEST_CN.md` must be obtained before any daemon start.

---

## Preflight Check

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from scripts.lp_rh_paper_daemon_entry_v1 import preflight
ok, errs = preflight('configs/paper_rh_core_v1.toml')
print('PASS' if ok else 'FAIL', errs)
"
```

Expected: `PASS []`

## Status Query

```bash
python3 -c "
import sys, json; sys.path.insert(0,'.')
from scripts.lp_rh_paper_daemon_entry_v1 import status
print(json.dumps(status('configs/paper_rh_core_v1.toml'), indent=2))
"
```

Expected fields: `mode=paper_only`, `episodes_run=0`, `last_tick_at=None`.

## Single Episode Run

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from scripts.lp_rh_paper_daemon_entry_v1 import run_once
rc = run_once('configs/paper_rh_core_v1.toml')
print('EXIT_CODE:', rc)
"
# 0 = NO_TRADE (stub), 1 = TECH_ERROR
```

## Daemon Start (requires Owner approval)

```bash
timeout 14400 python3 scripts/lp_rh_paper_daemon_entry_v1.py \
  --config configs/paper_rh_core_v1.toml --daemon
```

> `run_daemon` is a stub in W5. Real daemon requires W1+W2.

## PID Management

```bash
# Check if daemon is running
python3 -c "
import sys; sys.path.insert(0,'.')
from scripts.lp_rh_paper_pid_lock_v1 import is_alive, read_pid
pid_file = '/var/run/lpbot-paper-rh-core-v1.pid'
alive = is_alive(pid_file)
pid = read_pid(pid_file)
print(f'PID={pid} alive={alive}')
"

# Stale PID cleanup
sudo rm -f /var/run/lpbot-paper-rh-core-v1.pid
```

## Resource Health Checks

| Check | Command |
|-------|---------|
| RSS | `ps -o rss= -p $(cat /var/run/lpbot-paper-rh-core-v1.pid)` |
| Disk | `du -sm /var/lib/lpbot/` |
| DB size | `ls -lh /var/lib/lpbot/paper_rh_core_v1.db` |
| RPC rate | Log search or metrics counter |

## DB Integrity

```bash
sqlite3 /var/lib/lpbot/paper_rh_core_v1.db "PRAGMA integrity_check;"
```

## Hard Stops

```bash
# Normal: SIGTERM (daemon handles graceful shutdown + PID release)
sudo kill $(cat /var/run/lpbot-paper-rh-core-v1.pid)

# Emergency: SIGKILL (last resort — may leave stale lock)
sudo kill -9 $(cat /var/run/lpbot-paper-rh-core-v1.pid)
sudo rm -f /var/run/lpbot-paper-rh-core-v1.pid
```

## Explicitly Prohibited

- `signing_enabled = true` — never, hard-coded false
- `broadcasting_enabled = true` — never, hard-coded false
- Modifying six frozen constants
- Moving to main branch
- Creating keystores or private keys
- Starting live daemon without separate Tiny Live approval
