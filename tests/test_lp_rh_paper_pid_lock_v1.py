"""Tests for lp_rh_paper_pid_lock_v1.py — all use tmp_path, no /var/run."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.lp_rh_paper_pid_lock_v1 import (
    acquire,
    is_alive,
    read_pid,
    release,
)


class TestAcquire:
    def test_acquire_succeeds_when_no_existing_lock(self, tmp_path: Path) -> None:
        lock = tmp_path / "daemon.pid"
        assert acquire(str(lock)) is True
        # Lock file must contain our PID
        assert read_pid(str(lock)) == os.getpid()

    def test_acquire_fails_when_lock_held(self, tmp_path: Path) -> None:
        lock = tmp_path / "daemon.pid"
        assert acquire(str(lock)) is True
        # Second acquire from same process should fail (O_EXCL)
        assert acquire(str(lock)) is False


class TestRelease:
    def test_release_removes_lock(self, tmp_path: Path) -> None:
        lock = tmp_path / "daemon.pid"
        assert acquire(str(lock)) is True
        assert release(str(lock)) is True
        assert not lock.exists()

    def test_release_returns_false_when_owned_by_other(self, tmp_path: Path) -> None:
        lock = tmp_path / "daemon.pid"
        # Simulate another process holding the lock
        lock.write_text(str(999999))
        assert release(str(lock)) is False
        assert lock.exists()  # not removed

    def test_release_returns_true_when_lock_missing(self, tmp_path: Path) -> None:
        lock = tmp_path / "nonexistent.pid"
        assert release(str(lock)) is True  # no-op


class TestIsAlive:
    def test_is_alive_returns_true_for_current_pid(self, tmp_path: Path) -> None:
        lock = tmp_path / "daemon.pid"
        acquire(str(lock))
        assert is_alive(str(lock)) is True

    def test_is_alive_returns_false_for_stale_lock(self, tmp_path: Path) -> None:
        lock = tmp_path / "daemon.pid"
        # PID 2^31-1 is never allocated on any real Unix system
        lock.write_text("2147483647")
        assert is_alive(str(lock)) is False

    def test_is_alive_returns_false_when_missing(self, tmp_path: Path) -> None:
        lock = tmp_path / "nonexistent.pid"
        assert is_alive(str(lock)) is False


class TestReadPid:
    def test_read_pid_returns_int_when_present(self, tmp_path: Path) -> None:
        lock = tmp_path / "daemon.pid"
        acquire(str(lock))
        assert read_pid(str(lock)) == os.getpid()

    def test_read_pid_returns_none_when_missing(self, tmp_path: Path) -> None:
        lock = tmp_path / "nonexistent.pid"
        assert read_pid(str(lock)) is None

    def test_read_pid_returns_none_when_corrupt(self, tmp_path: Path) -> None:
        lock = tmp_path / "corrupt.pid"
        lock.write_text("not-a-number")
        assert read_pid(str(lock)) is None

    def test_read_pid_returns_none_when_empty(self, tmp_path: Path) -> None:
        lock = tmp_path / "empty.pid"
        lock.write_text("")
        assert read_pid(str(lock)) is None
