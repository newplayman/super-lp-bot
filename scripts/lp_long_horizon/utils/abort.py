"""Abort controller and error rate monitor.

The collector runner checks ``AbortController.check_abort()`` between units of
work. If any abort condition fires (5 consecutive 429, error rate >= 20%, write
failure, safety self-check fail, banned token detected), ``AbortError`` is
raised and the runner exits non-zero.

ErrorRateMonitor is a simple counter that returns ``should_abort()`` once the
error rate (over the last ``window`` calls) exceeds a threshold.
"""
from __future__ import annotations

from collections import deque
from typing import Deque


class AbortError(Exception):
    """Raised by AbortController when any abort condition fires."""


class ErrorRateMonitor:
    """Track ok/error counts in a sliding window. Returns should_abort on threshold."""

    def __init__(self, *, threshold_pct: float = 20.0, window: int = 50):
        if not 0.0 <= threshold_pct <= 100.0:
            raise ValueError(f"threshold_pct must be in [0, 100]; got {threshold_pct}")
        if window <= 0:
            raise ValueError(f"window must be > 0; got {window}")
        self.threshold_pct = threshold_pct
        self.window = window
        self._history: Deque[bool] = deque(maxlen=window)  # True = ok, False = error

    def record_ok(self) -> None:
        self._history.append(True)

    def record_error(self) -> None:
        self._history.append(False)

    @property
    def total(self) -> int:
        return len(self._history)

    @property
    def errors(self) -> int:
        return sum(1 for ok in self._history if not ok)

    @property
    def error_rate_pct(self) -> float:
        if not self._history:
            return 0.0
        return 100.0 * self.errors / len(self._history)

    def should_abort(self) -> bool:
        if not self._history:
            return False
        return self.error_rate_pct >= self.threshold_pct


class AbortController:
    """Centralized abort signaling.

    Abort conditions (any of these flips the controller to aborted):
    - 5 consecutive 429 from any single source
    - ErrorRateMonitor.should_abort() == True
    - write failure (record_write_failure)
    - safety self-check fail (record_safety_self_check_failure)
    - banned token detected at runtime (record_banned_token)
    """

    def __init__(self, *, error_rate_monitor: ErrorRateMonitor | None = None,
                 max_429_streak: int = 5):
        self.error_rate_monitor = error_rate_monitor or ErrorRateMonitor()
        self.max_429_streak = max_429_streak
        self._429_streak = 0
        self._aborted = False
        self._abort_reason: str | None = None
        self._write_failures = 0
        self._safety_self_check_failures = 0
        self._banned_token_detected = 0

    @property
    def is_aborted(self) -> bool:
        return self._aborted

    @property
    def abort_reason(self) -> str | None:
        return self._abort_reason

    def record_429(self) -> None:
        self._429_streak += 1
        if self._429_streak >= self.max_429_streak:
            self._abort("consecutive_429", f"5 consecutive 429 from single source")

    def record_429_cleared(self) -> None:
        self._429_streak = 0

    def record_ok(self) -> None:
        self.error_rate_monitor.record_ok()
        self.record_429_cleared()
        # Implicit abort check on each record (idempotent if not aborted)
        if not self._aborted:
            self._maybe_abort_error_rate()

    def record_error(self) -> None:
        self.error_rate_monitor.record_error()
        if not self._aborted:
            self._maybe_abort_error_rate()

    def _maybe_abort_error_rate(self) -> None:
        if self.error_rate_monitor.should_abort():
            self._abort(
                "error_rate",
                f"error_rate={self.error_rate_monitor.error_rate_pct:.1f}% "
                f">= threshold={self.error_rate_monitor.threshold_pct:.1f}%",
            )

    def record_write_failure(self, reason: str) -> None:
        self._write_failures += 1
        self._abort("write_failure", f"write failure: {reason}")

    def record_safety_self_check_failure(self, reason: str) -> None:
        self._safety_self_check_failures += 1
        self._abort("safety_self_check_failure", reason)

    def record_banned_token(self, token: str) -> None:
        self._banned_token_detected += 1
        self._abort("banned_token_detected", f"banned token detected at runtime: {token!r}")

    def check_abort(self) -> None:
        """Raise AbortError if any condition is met. Safe to call repeatedly."""
        if self._aborted:
            raise AbortError(f"aborted: {self._abort_reason}")
        if self.error_rate_monitor.should_abort():
            self._abort(
                "error_rate",
                f"error_rate={self.error_rate_monitor.error_rate_pct:.1f}% "
                f">= threshold={self.error_rate_monitor.threshold_pct:.1f}%",
            )
            raise AbortError(f"aborted: {self._abort_reason}")

    def _abort(self, kind: str, reason: str) -> None:
        if self._aborted:
            return
        self._aborted = True
        self._abort_reason = f"{kind}: {reason}"

    def summary(self) -> dict:
        return {
            "aborted": self._aborted,
            "abort_reason": self._abort_reason,
            "error_rate_pct": self.error_rate_monitor.error_rate_pct,
            "errors": self.error_rate_monitor.errors,
            "total": self.error_rate_monitor.total,
            "max_429_streak_hit": self._429_streak >= self.max_429_streak,
            "write_failures": self._write_failures,
            "safety_self_check_failures": self._safety_self_check_failures,
            "banned_token_detected": self._banned_token_detected,
        }
