#!/usr/bin/env python3
"""Throttled Telegram alerts for the read-only LP shadow services.

Credentials are accepted only through ``LPBOT_TG_TOKEN`` and
``LPBOT_TG_CHAT`` by :meth:`TelegramAlerter.from_env`.  Missing credentials or
transport failures fall back to a credential-free stdout record; alerting must
never crash the runner or scanner.  This module has no wallet, signing,
transaction construction, or broadcast capability.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, TextIO


MIN_INTERVAL_SECS = 60.0
DEFAULT_TIMEOUT_SECS = 10.0
TELEGRAM_API_ROOT = "https://api.telegram.org"
MAX_MESSAGE_CHARS = 4000


class TelegramTransportError(RuntimeError):
    """A sanitized transport failure that never embeds credentials."""


@dataclass(frozen=True)
class AlertResult:
    """Observable delivery result for tests and service telemetry."""

    delivery: str
    event_type: str
    error: Optional[str] = None


def _default_transport(
    url: str, payload: Mapping[str, Any], timeout: float
) -> Mapping[str, Any]:
    body = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, Mapping):
        raise TelegramTransportError("invalid Telegram response")
    return parsed


class TelegramAlerter:
    """Best-effort Telegram delivery with a process-wide alert interval.

    ``transport`` and ``clock`` are injected so tests never need the network or
    wall clock.  Throttling is global to this instance: changing event type or
    throttle key cannot bypass the 60-second minimum.
    """

    def __init__(
        self,
        *,
        token: Optional[str],
        chat_id: Optional[str],
        transport: Optional[
            Callable[[str, Mapping[str, Any], float], Mapping[str, Any]]
        ] = None,
        clock: Callable[[], float] = time.monotonic,
        stdout: TextIO = sys.stdout,
        min_interval_secs: float = MIN_INTERVAL_SECS,
        timeout_secs: float = DEFAULT_TIMEOUT_SECS,
    ):
        if float(min_interval_secs) < MIN_INTERVAL_SECS:
            raise ValueError("Telegram min_interval_secs must be at least 60 seconds")
        if float(timeout_secs) <= 0:
            raise ValueError("Telegram timeout_secs must be positive")
        self._token = str(token).strip() if token else None
        self._chat_id = str(chat_id).strip() if chat_id else None
        self._transport = transport or _default_transport
        self._clock = clock
        self._stdout = stdout
        self._min_interval_secs = float(min_interval_secs)
        self._timeout_secs = float(timeout_secs)
        self._last_delivery_at: Optional[float] = None

    @classmethod
    def from_env(
        cls,
        *,
        env: Optional[Mapping[str, str]] = None,
        transport: Optional[
            Callable[[str, Mapping[str, Any], float], Mapping[str, Any]]
        ] = None,
        clock: Callable[[], float] = time.monotonic,
        stdout: TextIO = sys.stdout,
        min_interval_secs: float = MIN_INTERVAL_SECS,
        timeout_secs: float = DEFAULT_TIMEOUT_SECS,
    ) -> "TelegramAlerter":
        """Build from the two WP-07 environment names and no legacy aliases."""
        source = os.environ if env is None else env
        return cls(
            token=source.get("LPBOT_TG_TOKEN"),
            chat_id=source.get("LPBOT_TG_CHAT"),
            transport=transport,
            clock=clock,
            stdout=stdout,
            min_interval_secs=min_interval_secs,
            timeout_secs=timeout_secs,
        )

    @property
    def configured(self) -> bool:
        return bool(self._token and self._chat_id)

    def _stdout_fallback(
        self, event_type: str, text: str, *, error: Optional[str] = None
    ) -> AlertResult:
        suffix = f" transport_error={error}" if error else ""
        print(
            f"[tg-fallback] event={event_type}{suffix} text={text}",
            file=self._stdout,
            flush=True,
        )
        return AlertResult(delivery="STDOUT", event_type=event_type, error=error)

    def send_event(
        self,
        event_type: str,
        message: str,
        *,
        severity: str = "INFO",
        throttle_key: Optional[str] = None,
    ) -> AlertResult:
        """Send one event or safely report why no Telegram call was made.

        ``throttle_key`` is accepted for a stable hook interface, but the
        minimum interval intentionally remains global.  It cannot be used to
        evade the Telegram rate gate.
        """
        del throttle_key
        event = str(event_type).strip() or "unknown"
        level = str(severity).strip().upper() or "INFO"
        content = " ".join(str(message).split())
        text = f"[LPBOT][{level}][{event}] {content}"[:MAX_MESSAGE_CHARS]
        now = float(self._clock())
        if (
            self._last_delivery_at is not None
            and now - self._last_delivery_at < self._min_interval_secs
        ):
            return AlertResult(delivery="THROTTLED", event_type=event)

        # A stdout fallback is still an alert delivery and therefore advances
        # the same global throttle.  This prevents log storms during outages.
        self._last_delivery_at = now
        if not self.configured:
            return self._stdout_fallback(event, text)

        payload = {"chat_id": self._chat_id, "text": text}
        url = f"{TELEGRAM_API_ROOT}/bot{self._token}/sendMessage"
        try:
            response = self._transport(url, payload, self._timeout_secs)
            if not isinstance(response, Mapping) or response.get("ok") is not True:
                raise TelegramTransportError("Telegram API rejected request")
        except Exception as exc:  # noqa: BLE001 - alert failures are non-fatal by contract
            # Never print exception text: clients commonly include the URL,
            # which contains the bot credential, in transport exceptions.
            error = type(exc).__name__
            return self._stdout_fallback(event, text, error=error)
        return AlertResult(delivery="TELEGRAM", event_type=event)


def safe_send_event(
    alerter: Any,
    event_type: str,
    message: str,
    *,
    severity: str = "INFO",
    throttle_key: Optional[str] = None,
    stdout: TextIO = sys.stdout,
) -> Optional[AlertResult]:
    """Call an injected alerter without letting notification code escape.

    ``TelegramAlerter`` already satisfies this property internally.  This
    wrapper preserves it for arbitrary injected adapters and test doubles.
    Exception text is deliberately omitted because transports may embed a bot
    URL in it.
    """
    if alerter is None:
        return None
    try:
        return alerter.send_event(
            event_type,
            message,
            severity=severity,
            throttle_key=throttle_key,
        )
    except Exception as exc:  # noqa: BLE001 - hooks must be best-effort
        error = type(exc).__name__
        print(
            f"[tg-hook-fallback] event={event_type} alert_error={error}",
            file=stdout,
            flush=True,
        )
        return AlertResult(delivery="FAILED", event_type=event_type, error=error)


def _rpc_health_from_result(result: Any) -> Optional[str]:
    raw = result.get("rpc_health") if isinstance(result, Mapping) else getattr(
        result, "rpc_health", None
    )
    if raw is None:
        return None
    value = str(raw).upper()
    return value if value in {"NORMAL", "DEGRADED", "EXIT_ONLY", "KILLED"} else None


def _accepted_or_logged(result: Optional[AlertResult]) -> bool:
    """Whether a hook may advance its cursor after this delivery attempt."""
    return result is None or result.delivery != "THROTTLED"


class ScannerAlertBridge:
    """Translate scanner cycle state and UTC rollover into alert events."""

    def __init__(
        self,
        alerter: Any,
        *,
        digest_provider: Optional[Callable[[str], str]] = None,
        utc_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        stdout: TextIO = sys.stdout,
    ):
        self.alerter = alerter
        self.digest_provider = digest_provider
        self.utc_now = utc_now
        self.stdout = stdout
        self._rpc_health: Optional[str] = None
        self._digest_day = self._today()

    def _today(self):
        value = self.utc_now()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date()

    def _emit_health_transition(self, current: Optional[str]) -> None:
        previous = self._rpc_health
        if current is None or current == previous:
            return
        result: Optional[AlertResult] = None
        if current == "DEGRADED":
            result = safe_send_event(
                self.alerter,
                "rpc_degraded",
                f"scanner RPC health changed {previous or 'UNKNOWN'} -> DEGRADED; new entries blocked",
                severity="WARNING",
                throttle_key="scanner:rpc-health",
                stdout=self.stdout,
            )
        elif current == "EXIT_ONLY":
            result = safe_send_event(
                self.alerter,
                "rpc_exit_only",
                f"scanner RPC health changed {previous or 'UNKNOWN'} -> EXIT_ONLY; reduce-risk actions only",
                severity="CRITICAL",
                throttle_key="scanner:rpc-health",
                stdout=self.stdout,
            )
        elif current == "KILLED":
            result = safe_send_event(
                self.alerter,
                "rpc_killed",
                f"scanner RPC health changed {previous or 'UNKNOWN'} -> KILLED; all actions blocked",
                severity="CRITICAL",
                throttle_key="scanner:rpc-health",
                stdout=self.stdout,
            )
        elif current == "NORMAL" and previous not in (None, "NORMAL"):
            result = safe_send_event(
                self.alerter,
                "rpc_normal",
                f"scanner RPC health recovered {previous} -> NORMAL",
                severity="INFO",
                throttle_key="scanner:rpc-health",
                stdout=self.stdout,
            )
        if _accepted_or_logged(result):
            self._rpc_health = current

    def _emit_due_digest(self) -> None:
        today = self._today()
        if self.digest_provider is None or today <= self._digest_day:
            return
        report_day = self._digest_day.isoformat()
        try:
            message = self.digest_provider(report_day)
        except Exception as exc:  # noqa: BLE001 - digest failure cannot stop scanner
            print(
                f"[tg-hook-fallback] event=daily_digest provider_error={type(exc).__name__}",
                file=self.stdout,
                flush=True,
            )
            return
        result = safe_send_event(
            self.alerter,
            "daily_digest",
            message,
            severity="INFO",
            throttle_key=f"scanner:daily-digest:{report_day}",
            stdout=self.stdout,
        )
        # A globally throttled alert is retried on the next scanner cycle.
        if _accepted_or_logged(result):
            self._digest_day = today

    def after_cycle(self, result: Any) -> None:
        self._emit_health_transition(_rpc_health_from_result(result))
        self._emit_due_digest()


__all__ = [
    "AlertResult",
    "DEFAULT_TIMEOUT_SECS",
    "MAX_MESSAGE_CHARS",
    "MIN_INTERVAL_SECS",
    "ScannerAlertBridge",
    "TelegramAlerter",
    "TelegramTransportError",
    "safe_send_event",
]
