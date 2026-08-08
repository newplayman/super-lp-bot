from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.lp_report_digest_v1_readonly import (
    build_digest_markdown,
    main,
    summarize_heartbeat,
    summarize_scanner_db,
)
from scripts.lp_scanner_daemon_v1_readonly import ScannerStore


ROOT = Path(__file__).parents[1]
HISTORICAL_HEARTBEAT = (
    ROOT
    / "reports/lp_portfolio_paper_runner/launch_20260624_115413_freerpc/heartbeat.jsonl"
)


def _write_jsonl(path: Path, records):
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n{bad json\n")


def test_heartbeat_summary_counts_valid_ticks_drawdown_breaches_and_last_state(tmp_path):
    heartbeat = tmp_path / "heartbeat.jsonl"
    _write_jsonl(
        heartbeat,
        [
            {
                "tick": 0,
                "ts_utc": "2026-08-08T00:00:00+00:00",
                "portfolio_net_usd": 100.0,
                "by_pool": [{"new_breach": False, "exited": False}],
            },
            {
                "tick": 1,
                "ts_utc": "2026-08-08T00:01:00+00:00",
                "portfolio_net_usd": 80.0,
                "by_pool": [
                    {"new_breach": True, "exited": True},
                    {"new_breach": True, "exited": False},
                ],
            },
            {
                "tick": 2,
                "ts_utc": "2026-08-09T00:00:00+00:00",
                "portfolio_net_usd": 90.0,
                "by_pool": [{"new_breach": False, "exited": False}],
            },
        ],
    )

    summary = summarize_heartbeat(heartbeat, day="2026-08-08")

    assert summary["ticks"] == 2
    assert summary["malformed_lines"] == 1
    assert summary["start_portfolio_net_usd"] == 100.0
    assert summary["end_portfolio_net_usd"] == 80.0
    assert summary["max_drawdown_usd"] == 20.0
    assert summary["breach_events"] == 2
    assert summary["last_pool_count"] == 2
    assert summary["last_exited_count"] == 1


def test_real_historical_heartbeat_summary_reads_every_valid_tick_without_mutation():
    assert HISTORICAL_HEARTBEAT.exists()
    before = HISTORICAL_HEARTBEAT.stat()
    expected = 0
    with HISTORICAL_HEARTBEAT.open() as handle:
        for line in handle:
            try:
                json.loads(line)
            except json.JSONDecodeError:
                continue
            expected += 1

    summary = summarize_heartbeat(HISTORICAL_HEARTBEAT)

    after = HISTORICAL_HEARTBEAT.stat()
    assert expected >= 2_150
    assert summary["ticks"] == expected
    assert summary["last_tick"] >= 2_149
    assert (after.st_size, after.st_ino) == (before.st_size, before.st_ino)


def test_scanner_db_summary_uses_latest_cycle_and_session_counts(tmp_path):
    db = tmp_path / "scanner.db"
    store = ScannerStore(db)
    store.initialize_schema()
    store.write_cycle(
        "2026-08-08T12:00:00+00:00",
        pool_snapshots=[{"pool": "0x1", "source": "test", "tvl_usd": 100.0}],
        opportunity_scores=[
            {"pool": "0x1", "source": "test", "accepted": True, "expected_net_yield_usd": 2.0},
            {
                "pool": "0x2",
                "source": "test",
                "accepted": False,
                "rejection_reason": "unstable",
            },
        ],
        market_sessions=[
            {
                "instrument_id": "AAPLX-USD",
                "pool": "0x1",
                "market_session": "PRIMARY_CLOSED",
                "source": "test",
            }
        ],
    )

    summary = summarize_scanner_db(db)

    assert summary["latest_as_of"] == "2026-08-08T12:00:00+00:00"
    assert summary["snapshot_count"] == 1
    assert summary["opportunity_count"] == 2
    assert summary["accepted_count"] == 1
    assert summary["rejection_reasons"] == {"unstable": 1}
    assert summary["market_sessions"] == {"PRIMARY_CLOSED": 1}


def test_digest_markdown_and_cli_write_human_readable_daily_report(tmp_path):
    heartbeat = tmp_path / "heartbeat.jsonl"
    _write_jsonl(
        heartbeat,
        [
            {
                "tick": 0,
                "ts_utc": "2026-08-08T00:00:00+00:00",
                "portfolio_net_usd": 1.0,
                "by_pool": [],
            }
        ],
    )
    db = tmp_path / "scanner.db"
    ScannerStore(db).initialize_schema()
    out = tmp_path / "digest.md"

    rc = main(
        [
            "--heartbeat",
            str(heartbeat),
            "--scanner-db",
            str(db),
            "--date",
            "2026-08-08",
            "--out",
            str(out),
        ]
    )

    assert rc == 0
    text = out.read_text()
    assert "# LP Shadow Daily Digest — 2026-08-08" in text
    assert "Runner heartbeat" in text
    assert "Scanner" in text
    assert "1" in text


def test_digest_handles_missing_scanner_db_without_creating_it(tmp_path):
    missing = tmp_path / "missing.db"

    summary = summarize_scanner_db(missing)
    markdown = build_digest_markdown(
        {"period": "all", "ticks": 0, "malformed_lines": 0}, summary, generated_at="2026-08-08"
    )

    assert summary["available"] is False
    assert not missing.exists()
    assert "unavailable" in markdown.lower()
