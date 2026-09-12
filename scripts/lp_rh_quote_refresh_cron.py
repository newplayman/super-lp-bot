#!/usr/bin/env python3
"""Single-shot cron wrapper for lp_rh_quote_refresh_v1 with PID lock, timeout, and structured JSONL logging."""
from __future__ import annotations

import atexit, json, logging, os, signal, sys, time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_quote_refresh_v1 import COINGECKO_URL, _default_fetch, apply_to_pool_meta, build_quote_refresh

DEFAULT_PIDFILE = Path("/var/run/lpbot-quote-refresh.pid")
DEFAULT_POOL_META = REPO_ROOT / "reports/lp_rh/pool_meta.json"
DEFAULT_SUCCESS_LOG = REPO_ROOT / "reports/quote_refresh/cron_success.jsonl"
DEFAULT_FAILURE_LOG = REPO_ROOT / "reports/quote_refresh/cron_failures.jsonl"
DEFAULT_TIMEOUT_SECS = 120
DEFAULT_HOLD_SECS = 2.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stderr)


def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True


def _acquire_pid_lock(pidfile: Path) -> bool:
    if pidfile.exists():
        try:
            old_pid = int(pidfile.read_text().strip())
            if _is_pid_alive(old_pid):
                logging.error("PID lock held: pid %s is alive in %s", old_pid, pidfile)
                return False
        except (ValueError, OSError):
            pass
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    tmp = pidfile.with_name(f"{pidfile.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(f"{os.getpid()}\n")
        os.replace(tmp, pidfile)
    except Exception as exc:
        logging.error("Failed to acquire PID lock file %s: %s", pidfile, exc)
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        return False
    return True


def _release_pid_lock(pidfile: Path) -> None:
    try:
        if pidfile.exists() and int(pidfile.read_text().strip()) == os.getpid():
            pidfile.unlink()
    except Exception:
        pass


def _append_jsonl(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
    except Exception as exc:
        logging.error("Failed to append to %s: %s", path, exc)


class CronTimeoutError(Exception):
    """Raised when quote refresh exceeds allotted timeout."""


def _alarm_handler(signum, frame):
    raise CronTimeoutError("Quote refresh operation timed out")


def main() -> int:
    pidfile_path = Path(os.environ.get("LPBOT_QUOTE_REFRESH_PIDFILE", str(DEFAULT_PIDFILE)))
    if not _acquire_pid_lock(pidfile_path):
        return 2
    atexit.register(_release_pid_lock, pidfile_path)

    pool_meta_path = Path(os.environ.get("LPBOT_POOL_META_PATH", str(DEFAULT_POOL_META)))
    success_log_path = Path(os.environ.get("LPBOT_QUOTE_REFRESH_SUCCESS_LOG", str(DEFAULT_SUCCESS_LOG)))
    failure_log_path = Path(os.environ.get("LPBOT_QUOTE_REFRESH_FAILURE_LOG", str(DEFAULT_FAILURE_LOG)))
    timeout_secs = int(os.environ.get("LPBOT_QUOTE_REFRESH_TIMEOUT_SECS", str(DEFAULT_TIMEOUT_SECS)))
    hold_secs = float(os.environ.get("LPBOT_QUOTE_REFRESH_HOLD_SECS", str(DEFAULT_HOLD_SECS)))

    t0 = time.monotonic()
    prev_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(timeout_secs)
    try:
        mock_payload = os.environ.get("LPBOT_QUOTE_REFRESH_MOCK_PAYLOAD")
        raw_payload = json.loads(mock_payload) if mock_payload is not None else _default_fetch(COINGECKO_URL, timeout=float(timeout_secs))
        refresh = build_quote_refresh(raw_payload)
        if refresh.get("status") != "OK":
            raise RuntimeError(f"build_quote_refresh status: {refresh.get('status')}")
        result = apply_to_pool_meta(pool_meta_path, refresh)
        if not result.get("written"):
            raise RuntimeError(f"apply_to_pool_meta failed: {result.get('reason')}")
        duration_ms = int((time.monotonic() - t0) * 1000)
        _append_jsonl(success_log_path, {
            "ts": _utc_now_rfc3339(), "success": True, "applied_to": str(pool_meta_path), "duration_ms": duration_ms,
        })
        if hold_secs > 0:
            time.sleep(hold_secs)
        return 0
    except CronTimeoutError as exc:
        logging.error("Execution timed out: %s", exc)
        _append_jsonl(failure_log_path, {"ts": _utc_now_rfc3339(), "success": False, "error": repr(exc), "exit_code": 124})
        return 124
    except Exception as exc:
        logging.error("Execution failed: %s", exc)
        _append_jsonl(failure_log_path, {"ts": _utc_now_rfc3339(), "success": False, "error": repr(exc), "exit_code": 1})
        return 1
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prev_handler)
        _release_pid_lock(pidfile_path)


if __name__ == "__main__":
    raise SystemExit(main())
