from __future__ import annotations

import io
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.lp_exit_policy_v1_readonly import QuoteResult
from scripts.lp_portfolio_paper_runner_v1_readonly import _tick, init_state
from scripts.lp_scanner_daemon_v1_readonly import ScannerDaemon
from scripts.lp_tg_alerter_v1_readonly import (
    MIN_INTERVAL_SECS,
    ScannerAlertBridge,
    TelegramAlerter,
)


class FakeClock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


class RecordingAlerter:
    def __init__(self):
        self.events = []

    def send_event(self, event_type, message, *, severity="INFO", throttle_key=None):
        self.events.append(
            {
                "event_type": event_type,
                "message": message,
                "severity": severity,
                "throttle_key": throttle_key,
            }
        )


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


def _book(state):
    return [
        {
            "symbol": "WETH-USDC",
            "project": "test",
            "tier": "A",
            "pool": "0xpool",
            "reward_apr": 0.0,
            "last_price": 1.0,
            "state": state,
        }
    ]


def _set_one_tick(monkeypatch, swap):
    import scripts.lp_portfolio_paper_runner_v1_readonly as runner

    monkeypatch.setattr(runner, "_latest_block", lambda: 1)
    monkeypatch.setattr(
        runner,
        "fetch_pool_swaps",
        lambda *args, **kwargs: [] if swap is None else [swap],
    )
    monkeypatch.setattr(
        runner,
        "_now_utc",
        lambda: datetime(2026, 8, 8, 12, 1, tzinfo=timezone.utc),
    )


def test_runner_tick_emits_one_breach_and_risk_off_complete_event(monkeypatch):
    state = init_state(
        capital=1000.0,
        anchor=1.0,
        range_pct=10.0,
        fee_tier=0.003,
        dec0=18,
        dec1=18,
        last_block=0,
        exit_on_breach=True,
    )
    _set_one_tick(
        monkeypatch,
        {"block": 1, "price": 1.5, "liquidity": 10**27, "amount1": 10**18},
    )
    alerter = RecordingAlerter()
    book = _book(state)

    _tick(
        book,
        last_ts=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
        alerter=alerter,
    )
    _tick(
        book,
        last_ts=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
        alerter=alerter,
    )

    assert [event["event_type"] for event in alerter.events] == [
        "breach",
        "risk_off_complete",
    ]


def test_runner_staged_remove_is_not_reported_as_risk_off_complete(monkeypatch):
    state = init_state(
        capital=1000.0,
        anchor=1.0,
        range_pct=10.0,
        fee_tier=0.003,
        dec0=18,
        dec1=18,
        last_block=0,
        exit_policy_enabled=True,
        risky_token_side="token0:WETH",
        stable_token_side="token1:USDC",
    )
    _set_one_tick(
        monkeypatch,
        {
            "block": 1,
            "price": 0.8,
            "liquidity": 10**27,
            "amount1": 10**18,
            "risk_signals": {"trend_continuation": True, "netcover_forward": 0.8},
            "exit_quote": QuoteResult.failed("unavailable"),
        },
    )
    alerter = RecordingAlerter()

    _tick(
        _book(state),
        last_ts=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
        alerter=alerter,
    )

    assert [event["event_type"] for event in alerter.events] == [
        "breach",
        "exit_staged",
    ]
    assert state["exit_policy_context"]["state"] == "EXITING"
    assert state["exited"]["risk_off_complete"] is False


def test_runner_emits_kill_once_and_alert_failure_does_not_interrupt_tick(monkeypatch):
    state = init_state(
        capital=1000.0,
        anchor=1.0,
        range_pct=10.0,
        fee_tier=0.003,
        dec0=18,
        dec1=18,
        last_block=0,
        rpc_health="KILLED",
    )
    _set_one_tick(monkeypatch, None)

    class FailingAlerter:
        calls = 0

        def send_event(self, *args, **kwargs):
            self.calls += 1
            raise RuntimeError("notification failed")

    alerter = FailingAlerter()
    book = _book(state)

    first, _ = _tick(
        book,
        last_ts=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
        alerter=alerter,
    )
    second, _ = _tick(
        book,
        last_ts=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
        alerter=alerter,
    )

    assert first["by_pool"][0]["risk_state"] == "HEALTHY"
    assert second["by_pool"][0]["risk_state"] == "HEALTHY"
    assert alerter.calls == 1


def test_scanner_bridge_alerts_rpc_transitions_and_previous_day_digest_once():
    alerter = RecordingAlerter()
    current = [datetime(2026, 8, 8, 23, 59, tzinfo=timezone.utc)]
    digest_days = []

    def digest_provider(day):
        digest_days.append(day)
        return f"digest for {day}"

    bridge = ScannerAlertBridge(
        alerter,
        digest_provider=digest_provider,
        utc_now=lambda: current[0],
    )

    bridge.after_cycle({"rpc_health": "NORMAL"})
    bridge.after_cycle({"rpc_health": "DEGRADED"})
    bridge.after_cycle({"rpc_health": "DEGRADED"})
    bridge.after_cycle({"rpc_health": "EXIT_ONLY"})
    bridge.after_cycle({"rpc_health": "NORMAL"})
    current[0] += timedelta(minutes=2)
    bridge.after_cycle({"rpc_health": "NORMAL"})
    bridge.after_cycle({"rpc_health": "NORMAL"})

    assert [event["event_type"] for event in alerter.events] == [
        "rpc_degraded",
        "rpc_exit_only",
        "rpc_normal",
        "daily_digest",
    ]
    assert digest_days == ["2026-08-08"]


def test_scanner_daemon_hook_failure_cannot_interrupt_completed_cycle():
    completed = []

    class FailingHook:
        def after_cycle(self, result):
            raise RuntimeError("notification failed")

    result = {"rpc_health": "DEGRADED"}
    daemon = ScannerDaemon(
        lambda refresh_coarse: completed.append(refresh_coarse) or result,
        event_hook=FailingHook(),
        coarse_interval_secs=900,
        top_interval_secs=60,
    )

    assert daemon.run(once=True) == 0
    assert completed == [True]
