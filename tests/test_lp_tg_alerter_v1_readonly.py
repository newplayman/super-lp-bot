from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

from scripts.lp_tg_alerter_v1_readonly import (
    MIN_INTERVAL_SECS,
    TelegramAlerter,
)


class FakeClock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


def test_env_contract_uses_only_wp07_names_and_missing_values_fall_back_to_stdout():
    output = io.StringIO()
    called = []
    alerter = TelegramAlerter.from_env(
        env={
            "LPBOT_TELEGRAM_BOT_TOKEN": "legacy-name-must-not-be-read",
            "LPBOT_TELEGRAM_CHAT_ID": "legacy-chat-must-not-be-read",
        },
        transport=lambda *args, **kwargs: called.append((args, kwargs)),
        stdout=output,
        clock=FakeClock(),
    )

    result = alerter.send_event("breach", "WETH-USDC lower band")

    assert result.delivery == "STDOUT"
    assert called == []
    assert "event=breach" in output.getvalue()
    assert "WETH-USDC lower band" in output.getvalue()
    assert "legacy-name-must-not-be-read" not in output.getvalue()


def test_mock_transport_receives_json_payload_and_global_throttle_is_60_seconds():
    calls = []
    clock = FakeClock(100.0)

    def transport(url, payload, timeout):
        calls.append((url, payload, timeout))
        return {"ok": True}

    alerter = TelegramAlerter.from_env(
        env={"LPBOT_TG_TOKEN": "unit-test-token", "LPBOT_TG_CHAT": "test-chat"},
        transport=transport,
        clock=clock,
        stdout=io.StringIO(),
    )

    sent = alerter.send_event("breach", "first", throttle_key="pool-a:breach")
    clock.value += MIN_INTERVAL_SECS - 1
    throttled = alerter.send_event("breach", "duplicate", throttle_key="pool-a:breach")
    distinct = alerter.send_event("exit_complete", "done", throttle_key="pool-a:exit")
    clock.value += 1
    sent_again = alerter.send_event("breach", "after interval", throttle_key="pool-a:breach")

    assert sent.delivery == "TELEGRAM"
    assert throttled.delivery == "THROTTLED"
    assert distinct.delivery == "THROTTLED"
    assert sent_again.delivery == "TELEGRAM"
    assert len(calls) == 2
    assert calls[0][0].startswith("https://api.telegram.org/")
    assert calls[0][0].endswith("/sendMessage")
    assert calls[0][1] == {"chat_id": "test-chat", "text": "[LPBOT][INFO][breach] first"}
    assert "unit-test-token" not in str(calls[0][1])
    assert calls[0][2] > 0


def test_transport_failure_degrades_without_leaking_credentials_or_crashing():
    output = io.StringIO()

    def failing_transport(url, payload, timeout):
        del payload, timeout
        raise RuntimeError(f"request failed at {url}")

    alerter = TelegramAlerter.from_env(
        env={"LPBOT_TG_TOKEN": "unit-test-token", "LPBOT_TG_CHAT": "test-chat"},
        transport=failing_transport,
        clock=FakeClock(),
        stdout=output,
    )

    result = alerter.send_event("kill", "RPC killed", severity="CRITICAL")

    assert result.delivery == "STDOUT"
    assert result.error == "RuntimeError"
    assert "unit-test-token" not in output.getvalue()
    assert "test-chat" not in output.getvalue()
    assert "transport_error=RuntimeError" in output.getvalue()


def test_minimum_interval_cannot_be_configured_below_60_seconds():
    with pytest.raises(ValueError, match="at least 60"):
        TelegramAlerter(
            token=None,
            chat_id=None,
            min_interval_secs=MIN_INTERVAL_SECS - 1,
            stdout=io.StringIO(),
        )


def test_telegram_api_negative_response_degrades_without_raising():
    output = io.StringIO()
    alerter = TelegramAlerter.from_env(
        env={"LPBOT_TG_TOKEN": "unit-test-token", "LPBOT_TG_CHAT": "test-chat"},
        transport=lambda *args, **kwargs: {"ok": False},
        clock=FakeClock(),
        stdout=output,
    )

    result = alerter.send_event("breach", "transport rejected")

    assert result.delivery == "STDOUT"
    assert result.error == "TelegramTransportError"
    assert "transport_error=TelegramTransportError" in output.getvalue()


def test_wp07_python_sources_contain_no_bot_token_shaped_literal():
    root = Path(__file__).parents[1]
    token_shape = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")
    sources = [
        root / "scripts/lp_tg_alerter_v1_readonly.py",
        root / "tests/test_lp_tg_alerter_v1_readonly.py",
    ]

    assert all(token_shape.search(path.read_text()) is None for path in sources)
