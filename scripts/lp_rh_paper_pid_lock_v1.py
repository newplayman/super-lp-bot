"""
PID lock utility for paper daemon singleton enforcement.

acquire  — atomically write our PID; fails if file already exists
release  — read PID; if it matches us, unlink; returns True if released
is_alive — read PID; check process still running (kill 0); stale file → False
read_pid — read integer PID or None if missing/corrupt
"""

from __future__ import annotations

import os
from typing import Optional


def acquire(path: str) -> bool:
    """Atomically acquire a PID lock file.

    Uses O_EXCL | os.O_CREAT | os.WRONLY to ensure atomic creation.
    Writes the current process PID as ASCII decimal.

    Returns True on success (lock held by this process).
    Returns False only when the file already exists (another process holds it).
    Other OSErrors propagate to the caller.
    """
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False

    try:
        pid_str = str(os.getpid()).encode("ascii")
        os.write(fd, pid_str)
    finally:
        os.close(fd)
    return True


def release(path: str) -> bool:
    """Release a PID lock if and only if the file is owned by the current process.

    Returns True if the lock was released (or the file never existed).
    Returns False if the lock is held by a different process.
    Permission denied on unlink propagates to the caller.
    """
    pid = read_pid(path)
    if pid is None:
        return True  # no lock file = nothing to release
    if pid != os.getpid():
        return False
    os.unlink(path)
    return True


def is_alive(path: str) -> bool:
    """Check whether the process recorded in the PID lock file is still running.

    Returns True if the PID exists and the process is alive.
    Returns False if the PID file is missing, stale (process dead), or corrupt.
    Permission denied on kill(0) propagates to the caller.
    """
    pid = read_pid(path)
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def read_pid(path: str) -> Optional[int]:
    """Read the PID stored in a lock file, or None if absent / not an integer."""
    try:
        with open(path, "r") as fh:
            content = fh.read().strip()
    except FileNotFoundError:
        return None
    if not content:
        return None
    try:
        return int(content)
    except ValueError:
        return None
