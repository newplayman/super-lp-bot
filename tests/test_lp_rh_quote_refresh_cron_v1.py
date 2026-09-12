"""Unit tests for lp_rh_quote_refresh_cron.py (offline verification)."""
from __future__ import annotations

import json, os, subprocess, sys, time
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_quote_refresh_cron import main  # noqa: E402


def _make_dummy_pool_meta(p: Path) -> None:
    meta = {
        "attestation_status": "ATTESTED_SAME_BLOCK",
        "current_tick": -198144,
        "token0": "0x0bd7d308f8e1639fab988df18a8011f41eacad73",
        "token1": "0x5fc5360d0400a0fd4f2af552add042d716f1d168",
        "fee_apr_pct": 27.34,
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def test_pid_lock_blocks_concurrent_run(tmp_path):
    pidfile = tmp_path / "test.pid"
    pool_meta = tmp_path / "pool_meta.json"
    _make_dummy_pool_meta(pool_meta)

    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(REPO_ROOT), "LPBOT_QUOTE_REFRESH_PIDFILE": str(pidfile),
        "LPBOT_POOL_META_PATH": str(pool_meta), "LPBOT_QUOTE_REFRESH_SUCCESS_LOG": str(tmp_path / "success.jsonl"),
        "LPBOT_QUOTE_REFRESH_FAILURE_LOG": str(tmp_path / "failures.jsonl"), "LPBOT_QUOTE_REFRESH_HOLD_SECS": "3.0",
        "LPBOT_QUOTE_REFRESH_TIMEOUT_SECS": "10", "LPBOT_QUOTE_REFRESH_MOCK_PAYLOAD": json.dumps({"global-dollar": {"usd": 1.0}}),
    })
    script = str(REPO_ROOT / "scripts/lp_rh_quote_refresh_cron.py")
    p1 = subprocess.Popen([sys.executable, script], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        time.sleep(0.6)
        assert p1.poll() is None, "Process 1 exited prematurely"
        p2 = subprocess.run([sys.executable, script], env=env, capture_output=True, text=True)
        assert p2.returncode == 2
        assert "PID lock held" in p2.stderr
    finally:
        p1.communicate(timeout=5)
        assert p1.returncode == 0
        assert not pidfile.exists()


def test_timeout_exit_124(monkeypatch, tmp_path):
    pidfile = tmp_path / "timeout.pid"
    failures_log = tmp_path / "cron_failures.jsonl"
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_PIDFILE", str(pidfile))
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_FAILURE_LOG", str(failures_log))
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_TIMEOUT_SECS", "1")
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_HOLD_SECS", "0")
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_MOCK_PAYLOAD", json.dumps({"global-dollar": {"usd": 1.0}}))

    monkeypatch.setattr("scripts.lp_rh_quote_refresh_cron.build_quote_refresh", lambda *args, **kwargs: time.sleep(300))

    t0 = time.monotonic()
    rc = main()
    elapsed = time.monotonic() - t0

    assert rc == 124
    assert elapsed < 130
    assert failures_log.exists()
    rows = [json.loads(line) for line in failures_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1 and rows[0]["success"] is False and rows[0]["exit_code"] == 124
    assert not pidfile.exists()


def test_failure_writes_jsonl(monkeypatch, tmp_path):
    pidfile = tmp_path / "fail.pid"
    failures_log = tmp_path / "cron_failures.jsonl"
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_PIDFILE", str(pidfile))
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_FAILURE_LOG", str(failures_log))
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_HOLD_SECS", "0")
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_MOCK_PAYLOAD", json.dumps({"global-dollar": {"usd": 1.0}}))

    def _failing_build(*args, **kwargs):
        raise ValueError("Simulated refresh explosion")
    monkeypatch.setattr("scripts.lp_rh_quote_refresh_cron.build_quote_refresh", _failing_build)

    rc = main()
    assert rc != 0
    assert failures_log.exists()
    rows = [json.loads(line) for line in failures_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1 and rows[0]["success"] is False and "Simulated refresh explosion" in rows[0]["error"]
    assert rows[0]["exit_code"] == rc
    assert not pidfile.exists()


def test_success_writes_jsonl(monkeypatch, tmp_path):
    pidfile = tmp_path / "success.pid"
    pool_meta = tmp_path / "pool_meta.json"
    _make_dummy_pool_meta(pool_meta)
    success_log = tmp_path / "cron_success.jsonl"

    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_PIDFILE", str(pidfile))
    monkeypatch.setenv("LPBOT_POOL_META_PATH", str(pool_meta))
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_SUCCESS_LOG", str(success_log))
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_HOLD_SECS", "0")
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_MOCK_PAYLOAD", json.dumps({"global-dollar": {"usd": 1.0003}}))

    rc = main()
    assert rc == 0
    assert success_log.exists()
    rows = [json.loads(line) for line in success_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1 and rows[0]["success"] is True and rows[0]["applied_to"] == str(pool_meta)
    assert isinstance(rows[0]["duration_ms"], int)
    assert not pidfile.exists()


def test_pool_meta_json_written(monkeypatch, tmp_path):
    pidfile = tmp_path / "meta_write.pid"
    pool_meta = tmp_path / "pool_meta.json"
    _make_dummy_pool_meta(pool_meta)

    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_PIDFILE", str(pidfile))
    monkeypatch.setenv("LPBOT_POOL_META_PATH", str(pool_meta))
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_SUCCESS_LOG", str(tmp_path / "cron_success.jsonl"))
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_FAILURE_LOG", str(tmp_path / "cron_failures.jsonl"))
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_HOLD_SECS", "0")
    monkeypatch.setenv("LPBOT_QUOTE_REFRESH_MOCK_PAYLOAD", json.dumps({"global-dollar": {"usd": 0.9997}}))

    rc = main()
    assert rc == 0
    data = json.loads(pool_meta.read_text(encoding="utf-8"))
    assert data["attestation_status"] == "ATTESTED_SAME_BLOCK"
    assert data["quote_usd_per_token1"]["value"] == "0.9997"
    assert "-0.0300%" in data["quote_usd_per_token1"]["note"]
    assert not pidfile.exists()
