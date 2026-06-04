"""Retry / backoff / timeout / 429 helpers.

These helpers are used by the source adapters to wrap any I/O call that may:
- time out (network / RPC)
- return 429 (rate limited)
- return 5xx (server error)

They do NOT catch wallet / signer / tx / mutation related errors. Those should
fail loud because they violate the read-only contract.
"""
from __future__ import annotations

import signal
import time as _time_mod
from time import sleep
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class TimeoutError_(Exception):  # noqa: N801 - intentionally distinct name
    """Raised when a callable exceeds its timeout budget."""


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_retries: int = 3,
    base_delay_s: float = 1.0,
    backoff_factor: float = 2.0,
    is_retryable: Callable[[Exception], bool] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> T:
    """Run ``fn`` with exponential backoff retry on retryable exceptions.

    - ``max_retries`` is the number of retries AFTER the first attempt. Total
      attempts = 1 + max_retries.
    - Delay between attempt n and n+1 is ``base_delay_s * backoff_factor ** n``.
    - ``is_retryable(exc)`` decides whether to retry. Default: retry on any
      exception (callers should narrow this in production).
    - ``sleep_fn`` defaults to this module's ``sleep`` (looked up at call
      time so tests can monkeypatch ``lp_long_horizon.utils.retry.sleep``).
    - On final failure, the original exception is re-raised.
    """
    if sleep_fn is None:
        sleep_fn = sleep  # late-bound: picks up any monkeypatched sleep
    retry_decider = is_retryable or (lambda e: True)
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - intentional, re-raised below
            last_exc = exc
            if attempt >= max_retries or not retry_decider(exc):
                raise
            delay = base_delay_s * (backoff_factor ** attempt)
            sleep_fn(delay)
    # unreachable
    assert last_exc is not None
    raise last_exc


def classify_429(exc: Exception) -> bool:
    """Return True if ``exc`` represents HTTP 429 / Solana rate-limit.

    We check a few common surfaces:
    - ``exc.status_code == 429``
    - ``exc.code == 429``
    - ``"429" in str(exc)``
    - ``"Too Many Requests" in str(exc)``
    - ``"rate limit" in str(exc).lower()``
    """
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429:
        return True
    msg = str(exc).lower()
    if "too many requests" in msg:
        return True
    if "rate limit" in msg:
        return True
    if "rate-limited" in msg:
        return True
    if "rate_limit_exceeded" in msg:
        return True
    return False


def with_timeout(fn: Callable[[], T], *, timeout_s: float) -> T:
    """Run ``fn`` synchronously with a wall-clock timeout.

    Uses SIGALRM on POSIX. Not safe to nest with other SIGALRM users. If
    ``fn`` finishes after the timeout, ``TimeoutError_`` is raised.
    """
    def _handler(_signum, _frame):
        raise TimeoutError_(f"call exceeded {timeout_s}s timeout")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, float(timeout_s))
    try:
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, old)


def safe_sleep(s: float) -> None:
    """Test-friendly sleep; replaceable via monkeypatch in unit tests."""
    sleep(max(0.0, s))
