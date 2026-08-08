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


__all__ = [
    "AlertResult",
    "DEFAULT_TIMEOUT_SECS",
    "MAX_MESSAGE_CHARS",
    "MIN_INTERVAL_SECS",
    "TelegramAlerter",
    "TelegramTransportError",
]
