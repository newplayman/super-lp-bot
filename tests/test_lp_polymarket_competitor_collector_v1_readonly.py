"""Tests for the Polymarket competitor collector (read-only, no network).

These pin pure functions and the cycle driver against a fully injected HTTP
transport and clock. No real network calls. The collector writes to a temp
SQLite and a temp export dir per test.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import pytest

# Make the script importable as `scripts.lp_polymarket_competitor_collector_v1_readonly`
REPO = Path("/opt/lpbot/lp-bot-v3-origin-check")
sys.path.insert(0, str(REPO))

from scripts import lp_polymarket_competitor_collector_v1_readonly as m  # noqa: E402


# -----------------------------------------------------------------------------
# Address handling
# -----------------------------------------------------------------------------


def test_validate_address_lowercases_40hex():
    addr = "0x" + "A" * 40
    assert m.validate_address(addr) == "0x" + "a" * 40


def test_validate_address_rejects_short():
    with pytest.raises(ValueError):
        m.validate_address("0x1234")


def test_validate_address_rejects_non_hex():
    with pytest.raises(ValueError):
        m.validate_address("0x" + "Z" * 40)


def test_validate_address_rejects_empty():
    with pytest.raises(ValueError):
        m.validate_address("")


def test_parse_addresses_file_happy(tmp_path: Path):
    p = tmp_path / "addrs.json"
    p.write_text(json.dumps({"addresses": [
        "0x" + "a" * 40,
        "0x" + "B" * 40,  # mixed case must normalize
        "0x" + "a" * 40,  # duplicate
    ]}))
    addrs = m.parse_addresses_file(p)
    assert addrs == ["0x" + "a" * 40, "0x" + "b" * 40]


def test_parse_addresses_file_missing(tmp_path: Path):
    with pytest.raises(m.PolymarketAddressFileError):
        m.parse_addresses_file(tmp_path / "no_such.json")


def test_parse_addresses_file_bad_json(tmp_path: Path):
    p = tmp_path / "x.json"
    p.write_text("not json")
    with pytest.raises(m.PolymarketAddressFileError):
        m.parse_addresses_file(p)


def test_parse_addresses_file_one_bad(tmp_path: Path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"addresses": ["0x" + "a" * 40, "bad"]}))
    with pytest.raises(m.PolymarketAddressFileError):
        m.parse_addresses_file(p)


def test_parse_addresses_file_wrong_shape(tmp_path: Path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps([1, 2, 3]))
    with pytest.raises(m.PolymarketAddressFileError):
        m.parse_addresses_file(p)


# -----------------------------------------------------------------------------
# dedup key
# -----------------------------------------------------------------------------


def _sample_row() -> dict:
    return {
        "transactionHash": "0x" + "b" * 64,
        "timestamp": 1700000000,
        "type": "TRADE",
        "conditionId": "0x" + "c" * 64,
        "asset": "12345",
        "side": "BUY",
        "outcomeIndex": 0,
    }


def test_dedup_key_stable_across_runs():
    addr = "0x" + "a" * 40
    r = _sample_row()
    assert m.dedup_key(addr, r) == m.dedup_key(addr, dict(r))


def test_dedup_key_differs_on_txhash():
    addr = "0x" + "a" * 40
    r = _sample_row()
    r2 = dict(r, transactionHash="0x" + "f" * 64)
    assert m.dedup_key(addr, r) != m.dedup_key(addr, r2)


def test_dedup_key_differs_on_timestamp():
    addr = "0x" + "a" * 40
    r = _sample_row()
    r2 = dict(r, timestamp=1700000001)
    assert m.dedup_key(addr, r) != m.dedup_key(addr, r2)


def test_dedup_key_differs_on_outcome_index():
    addr = "0x" + "a" * 40
    r = _sample_row()
    r2 = dict(r, outcomeIndex=1)
    assert m.dedup_key(addr, r) != m.dedup_key(addr, r2)


def test_dedup_key_works_without_txhash():
    addr = "0x" + "a" * 40
    r = _sample_row()
    r.pop("transactionHash")
    k = m.dedup_key(addr, r)
    assert len(k) == 32
    # And the no-hash variant must still differ from the with-hash variant
    assert k != m.dedup_key(addr, _sample_row())


def test_dedup_key_case_insensitive_hash():
    addr = "0x" + "a" * 40
    r1 = _sample_row()
    r2 = _sample_row()
    r2["transactionHash"] = r1["transactionHash"].upper()
    assert m.dedup_key(addr, r1) == m.dedup_key(addr, r2)


def test_canonical_for_dedup_keys_sorted():
    addr = "0x" + "a" * 40
    r = _sample_row()
    c1 = m.canonical_for_dedup(addr, r)
    c2 = m.canonical_for_dedup(addr, r)
    # JSON keys are sorted by the implementation
    parsed = json.loads(c1)
    keys = list(parsed.keys())
    assert keys == sorted(keys)


# -----------------------------------------------------------------------------
# coerce_row
# -----------------------------------------------------------------------------


def test_coerce_row_typed_fields():
    r = _sample_row()
    r.update({"size": "10.5", "usdcSize": "5.0", "price": "0.5", "outcomeIndex": "1"})
    cr = m.coerce_row(r)
    assert cr["size"] == 10.5
    assert cr["usdcSize"] == 5.0
    assert cr["price"] == 0.5
    assert cr["outcomeIndex"] == 1
    assert cr["timestamp"] == 1700000000


def test_coerce_row_partial_trade_tolerated():
    # missing optional fields -> None
    cr = m.coerce_row({"timestamp": 1700000000, "type": "TRADE", "transactionHash": "0x" + "a" * 64})
    assert cr["side"] is None
    assert cr["asset"] is None
    assert cr["outcomeIndex"] is None


def test_coerce_row_empty_raises():
    with pytest.raises(m.PolymarketInvalidRow):
        m.coerce_row({})


# -----------------------------------------------------------------------------
# Overlap signal
# -----------------------------------------------------------------------------


def test_extract_overlap_signal_match_ts():
    assert m.extract_overlap_signal([{"timestamp": 5}, {"timestamp": 4}], 5, None) is True


def test_extract_overlap_signal_match_hash():
    rows = [{"transactionHash": "0xABC"}, {"timestamp": 99}]
    assert m.extract_overlap_signal(rows, 999, "0xabc") is True


def test_extract_overlap_signal_no_match():
    assert m.extract_overlap_signal([{"timestamp": 1}], 99, None) is False


def test_extract_overlap_signal_no_baseline():
    assert m.extract_overlap_signal([{"timestamp": 1}], None, None) is False


# -----------------------------------------------------------------------------
# backfill planning
# -----------------------------------------------------------------------------


def test_plan_backfill_offsets_no_baseline():
    assert m.plan_backfill_offsets(False) == []


def test_plan_backfill_offsets_with_baseline():
    assert m.plan_backfill_offsets(True) == [500, 1000, 1500, 2000, 2500, 3000]


def test_plan_backfill_offsets_respects_cap():
    assert m.plan_backfill_offsets(True, cap_pages=3) == [500, 1000, 1500]


def test_plan_backfill_offsets_caps_at_3000():
    assert m.plan_backfill_offsets(True, cap_pages=100) == [
        500, 1000, 1500, 2000, 2500, 3000,
    ]


# -----------------------------------------------------------------------------
# classification / retry
# -----------------------------------------------------------------------------


def test_classify_backfill_recovered():
    assert m.classify_backfill_outcome(True, False, False) == "recovered"


def test_classify_backfill_ran_past_end():
    assert m.classify_backfill_outcome(False, True, False) == "ran_past_end"


def test_classify_backfill_cap_exhausted():
    assert m.classify_backfill_outcome(False, False, True) == "cap_exhausted"


def test_should_retry_first_attempt_429():
    assert m.should_retry(429, 0) is True


def test_should_retry_first_attempt_500():
    assert m.should_retry(503, 0) is True


def test_should_retry_first_attempt_404():
    assert m.should_retry(404, 0) is False


def test_should_retry_second_attempt_429():
    assert m.should_retry(429, 1) is False


def test_parse_retry_after_seconds():
    assert m.parse_retry_after({"Retry-After": "30"}) == 30.0


def test_parse_retry_after_missing():
    assert m.parse_retry_after({}) is None


def test_parse_retry_after_http_date():
    # any future date string parses to a positive number
    assert m.parse_retry_after({"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}) > 0


# -----------------------------------------------------------------------------
# atomic IO
# -----------------------------------------------------------------------------


def test_atomic_write_json_no_tmp_left(tmp_path: Path):
    p = tmp_path / "a.json"
    m.atomic_write_json(p, {"x": 1})
    assert p.exists()
    siblings = list(tmp_path.iterdir())
    assert siblings == [p]


def test_atomic_write_json_overwrites_existing(tmp_path: Path):
    p = tmp_path / "a.json"
    p.write_text('{"old":true}')
    m.atomic_write_json(p, {"new": True})
    assert json.loads(p.read_text()) == {"new": True}


def test_atomic_write_json_creates_parent_dirs(tmp_path: Path):
    p = tmp_path / "deep" / "nested" / "a.json"
    m.atomic_write_json(p, {"x": 1})
    assert p.exists()


# -----------------------------------------------------------------------------
# totals / formatting
# -----------------------------------------------------------------------------


def test_compute_cycle_totals_sums_inserted():
    t = m.compute_cycle_totals([
        {"shallow_count": 10, "shallow_inserted": 3, "backfill_inserted": 0, "backfill_recovered": True},
        {"shallow_count": 20, "shallow_inserted": 1, "backfill_inserted": 5, "backfill_recovered": False},
    ])
    assert t["rows_last_cycle_inserted"] == 9
    assert t["rows_last_cycle_seen"] == 30
    assert t["addresses_with_gap"] == 1


def test_format_onepage_cn_contains_addresses():
    per = [{"address": "0x" + "a" * 40, "shallow_count": 1, "shallow_inserted": 0,
            "backfill_pages": 0, "backfill_inserted": 0, "backfill_status": "no_baseline"}]
    out = m.format_onepage_cn("20260629_120000", per, 1700000000, 1700000010)
    assert "0x" + "a" * 40 in out
    assert "20260629_120000" in out


def test_format_artifact_index_lists_files():
    out = m.format_artifact_index("rid", ["a.json", "b.md"])
    assert "a.json" in out and "b.md" in out
    assert "rid" in out


def test_summarize_page_for_log_includes_addr():
    s = m.summarize_page_for_log("0xabc", 0, [{}, {}], 0, True)
    assert s.startswith("addr=0xabc")
    assert "offset=0" in s


# -----------------------------------------------------------------------------
# Cycle driver with injected HTTP / clock (no network)
# -----------------------------------------------------------------------------


class FakeClock:
    def __init__(self, t0: float = 1_700_000_000.0):
        self.t = t0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def make_fake_http(pages: list[dict]):
    """Build a fake http_get_json. `pages[0]` is the shallow page (offset=0).
    `pages[1..]` are returned for backfill offsets 500, 1000, 1500, ... in order.
    Past the end of `pages`, an empty list is returned (hit_empty_page).
    """
    state = {"calls": [], "shallow_count": 0}

    def fn(url, params, timeout, user_agent):
        state["calls"].append((params.get("user"), params.get("offset"), params.get("limit")))
        offset = params.get("offset", 0)
        if offset == 0:
            state["shallow_count"] += 1
            return 200, json.dumps(pages[0]), {}
        # backfill: offset=500 -> pages[1], offset=1000 -> pages[2], ...
        idx = (offset // 500)  # 500->1, 1000->2, ...
        if 0 < idx < len(pages):
            return 200, json.dumps(pages[idx]), {}
        return 200, "[]", {}

    return fn, state


def test_run_cycle_with_fake_http_no_baseline(tmp_path: Path):
    addr = "0x" + "a" * 40
    pages = [[
        {"proxyWallet": addr, "transactionHash": "0x" + "h" * 64,
         "timestamp": 1700000000, "type": "TRADE", "conditionId": "0x" + "c" * 64,
         "asset": "1", "side": "BUY", "outcomeIndex": 0,
         "size": 10.0, "usdcSize": 5.0, "price": 0.5}
    ]]
    fake_http, _ = make_fake_http(pages)
    clock = FakeClock()
    db_p = tmp_path / "poly.db"
    exp_p = tmp_path / "export"
    st_p = tmp_path / "status.json"
    rep_p = tmp_path / "reports"
    r = m._run_cycle_core(
        addresses=[addr],
        db_path=db_p,
        export_dir=exp_p,
        status_path=st_p,
        reports_dir=rep_p,
        run_id="rid_test_1",
        write_db=True, write_export=True, write_reports=True, write_status=True,
        limit=500, backfill_cap_pages=2,
        http_get_json=fake_http, now_epoch=clock,
    )
    assert r.ok
    assert r.per_address[0]["shallow_inserted"] == 1
    assert r.per_address[0]["backfill_status"] == "no_baseline"
    # Status file
    st = json.loads(st_p.read_text())
    assert st["exit_status"] == "ok"
    assert st["last_unresolved_gap"] is None
    # No .tmp sibling
    assert not (tmp_path / "status.json.tmp").exists()
    # Reports written
    assert (rep_p / "rid_test_1" / "ONEPAGE_CN.md").exists()
    assert (rep_p / "rid_test_1" / "cycle_summary.json").exists()
    assert (rep_p / "rid_test_1" / "ARTIFACT_INDEX.md").exists()
    # DB row inserted
    conn = sqlite3.connect(str(db_p))
    cnt = conn.execute("SELECT COUNT(*) FROM activity WHERE address = ?", (addr,)).fetchone()[0]
    assert cnt == 1
    # Export file has 1 line
    lines = (exp_p / f"activity_{addr}.jsonl").read_text().splitlines()
    assert len(lines) == 1
    conn.close()


def test_run_cycle_gap_detected_and_recovered(tmp_path: Path):
    """Cycle 1 inserts a row at ts=100. Cycle 2's offset=0 returns a page with
    no overlap (all-newer rows). Backfill is triggered and finds a page with
    the overlap row -> recovered."""
    addr = "0x" + "a" * 40
    base_row = {
        "proxyWallet": addr, "transactionHash": "0x" + "h" * 64,
        "timestamp": 100, "type": "TRADE", "conditionId": "0x" + "c" * 64,
        "asset": "1", "side": "BUY", "outcomeIndex": 0,
        "size": 10.0, "usdcSize": 5.0, "price": 0.5,
    }
    # Cycle 1: shallow returns [base_row]
    pages1 = [[base_row]]
    fake1, _ = make_fake_http(pages1)
    clock = FakeClock()
    db_p = tmp_path / "poly.db"
    exp_p = tmp_path / "export"
    st_p = tmp_path / "status.json"
    rep_p = tmp_path / "reports"
    m._run_cycle_core(
        addresses=[addr], db_path=db_p, export_dir=exp_p, status_path=st_p,
        reports_dir=rep_p, run_id="rid_c1",
        http_get_json=fake1, now_epoch=clock,
    )

    # Cycle 2: shallow returns all-newer rows (no overlap with ts=100).
    # Backfill must recover at offset=500 (which is where we put the overlap).
    newer1 = {**base_row, "transactionHash": "0x" + "1" * 64, "timestamp": 200}
    newer2 = {**base_row, "transactionHash": "0x" + "2" * 64, "timestamp": 201}
    backfill_recovery = {**base_row, "transactionHash": "0x" + "3" * 64, "timestamp": 99}  # not used; we'll fake by ts=100
    recovery_row = {**base_row, "transactionHash": "0x" + "4" * 64, "timestamp": 100}  # overlap by ts
    pages2 = [[newer1, newer2], [recovery_row], []]  # offset 0, 500, 1000
    fake2, _ = make_fake_http(pages2)
    clock.advance(60)
    r = m._run_cycle_core(
        addresses=[addr], db_path=db_p, export_dir=exp_p, status_path=st_p,
        reports_dir=rep_p, run_id="rid_c2",
        http_get_json=fake2, now_epoch=clock,
    )
    assert r.ok
    pa = r.per_address[0]
    assert pa["shallow_count"] == 2
    assert pa["shallow_inserted"] == 2
    assert pa["backfill_pages"] >= 1
    assert pa["backfill_recovered"] is True
    assert pa["backfill_status"] == "recovered"
    # Total rows in DB = 1 base (cycle 1) + 2 newer (cycle 2 shallow) + 1 recovery (backfill) = 4
    conn = sqlite3.connect(str(db_p))
    cnt = conn.execute("SELECT COUNT(*) FROM activity WHERE address = ?", (addr,)).fetchone()[0]
    assert cnt == 4
    conn.close()


def test_run_cycle_gap_unrecovered(tmp_path: Path):
    """Cycle 1 inserts base row. Cycle 2: shallow has no overlap, backfill pages
    never contain overlap -> status=ran_past_end/cap_exhausted; last_unresolved_gap set."""
    addr = "0x" + "a" * 40
    base_row = {
        "proxyWallet": addr, "transactionHash": "0x" + "h" * 64,
        "timestamp": 100, "type": "TRADE", "conditionId": "0x" + "c" * 64,
        "asset": "1", "side": "BUY", "outcomeIndex": 0,
        "size": 10.0, "usdcSize": 5.0, "price": 0.5,
    }
    pages1 = [[base_row]]
    fake1, _ = make_fake_http(pages1)
    clock = FakeClock()
    db_p = tmp_path / "poly.db"
    exp_p = tmp_path / "export"
    st_p = tmp_path / "status.json"
    rep_p = tmp_path / "reports"
    m._run_cycle_core(
        addresses=[addr], db_path=db_p, export_dir=exp_p, status_path=st_p,
        reports_dir=rep_p, run_id="rid_c1",
        http_get_json=fake1, now_epoch=clock,
    )
    # Cycle 2: shallow returns new rows; backfill pages are all-newer (no ts=100)
    newer1 = {**base_row, "transactionHash": "0x" + "1" * 64, "timestamp": 200}
    newer2 = {**base_row, "transactionHash": "0x" + "2" * 64, "timestamp": 201}
    pages2 = [
        [newer1, newer2],  # offset=0
        [newer1],           # offset=500 (will not match ts=100)
        [newer2],           # offset=1000
        [newer1],           # offset=1500
        [],                 # offset=2000 -> hit_empty_page=True -> ran_past_end
    ]
    fake2, _ = make_fake_http(pages2)
    clock.advance(60)
    r = m._run_cycle_core(
        addresses=[addr], db_path=db_p, export_dir=exp_p, status_path=st_p,
        reports_dir=rep_p, run_id="rid_c2",
        http_get_json=fake2, now_epoch=clock,
        backfill_cap_pages=5,
    )
    assert r.ok  # cycle itself didn't crash
    pa = r.per_address[0]
    assert pa["backfill_recovered"] is False
    assert pa["backfill_status"] in ("ran_past_end", "cap_exhausted")
    st = json.loads(st_p.read_text())
    assert st["last_unresolved_gap"] is not None
    assert st["last_unresolved_gap"]["address"] == addr


def test_run_cycle_idempotent_under_duplicate_pages(tmp_path: Path):
    """If the API returns the same page twice in a row, dedup must prevent
    double-insert."""
    addr = "0x" + "a" * 40
    row = {
        "proxyWallet": addr, "transactionHash": "0x" + "h" * 64,
        "timestamp": 100, "type": "TRADE", "conditionId": "0x" + "c" * 64,
        "asset": "1", "side": "BUY", "outcomeIndex": 0,
        "size": 10.0, "usdcSize": 5.0, "price": 0.5,
    }
    # Two cycles, same page each time
    pages = [[row]]
    fake, _ = make_fake_http(pages)
    clock = FakeClock()
    db_p = tmp_path / "poly.db"
    exp_p = tmp_path / "export"
    st_p = tmp_path / "status.json"
    rep_p = tmp_path / "reports"
    m._run_cycle_core(
        addresses=[addr], db_path=db_p, export_dir=exp_p, status_path=st_p,
        reports_dir=rep_p, run_id="rid_a",
        http_get_json=fake, now_epoch=clock,
    )
    clock.advance(60)
    r2 = m._run_cycle_core(
        addresses=[addr], db_path=db_p, export_dir=exp_p, status_path=st_p,
        reports_dir=rep_p, run_id="rid_b",
        http_get_json=fake, now_epoch=clock,
    )
    # Second cycle: page matches by ts=100 -> no overlap=miss -> no backfill
    # But row already exists, so shallow_inserted=0.
    assert r2.per_address[0]["shallow_inserted"] == 0
    conn = sqlite3.connect(str(db_p))
    cnt = conn.execute("SELECT COUNT(*) FROM activity WHERE address = ?", (addr,)).fetchone()[0]
    assert cnt == 1
    # dedup_key uniqueness
    n_keys = conn.execute("SELECT COUNT(DISTINCT dedup_key) FROM activity WHERE address = ?", (addr,)).fetchone()[0]
    assert n_keys == cnt
    conn.close()


def test_run_cycle_empty_addresses_raises(tmp_path: Path):
    with pytest.raises(ValueError):
        m._run_cycle_core(
            addresses=[], db_path=tmp_path / "x.db", export_dir=tmp_path,
            status_path=tmp_path / "s.json", reports_dir=tmp_path,
            run_id="rid_empty",
            http_get_json=lambda *a, **k: (200, "[]", {}), now_epoch=lambda: 0,
        )


def test_run_cycle_429_then_success(tmp_path: Path):
    """First call returns 429, second returns 200. Cycle must succeed."""
    addr = "0x" + "a" * 40
    row = {
        "proxyWallet": addr, "transactionHash": "0x" + "h" * 64,
        "timestamp": 100, "type": "TRADE", "conditionId": "0x" + "c" * 64,
        "asset": "1", "side": "BUY", "outcomeIndex": 0,
        "size": 10.0, "usdcSize": 5.0, "price": 0.5,
    }
    calls = {"n": 0}

    def fake(url, params, timeout, user_agent):
        calls["n"] += 1
        if calls["n"] == 1:
            return 429, "rate limited", {"Retry-After": "0"}  # 0s wait
        return 200, json.dumps([row]), {}

    db_p = tmp_path / "poly.db"
    exp_p = tmp_path / "export"
    st_p = tmp_path / "status.json"
    rep_p = tmp_path / "reports"
    r = m._run_cycle_core(
        addresses=[addr], db_path=db_p, export_dir=exp_p, status_path=st_p,
        reports_dir=rep_p, run_id="rid_429",
        http_get_json=fake, now_epoch=FakeClock(),
    )
    assert r.ok
    assert calls["n"] == 2
    assert r.per_address[0]["shallow_inserted"] == 1


def test_run_cycle_429_persistent_is_fatal(tmp_path: Path):
    addr = "0x" + "a" * 40
    calls = {"n": 0}

    def fake(url, params, timeout, user_agent):
        calls["n"] += 1
        return 429, "rate limited", {"Retry-After": "0"}

    db_p = tmp_path / "poly.db"
    exp_p = tmp_path / "export"
    st_p = tmp_path / "status.json"
    rep_p = tmp_path / "reports"
    r = m._run_cycle_core(
        addresses=[addr], db_path=db_p, export_dir=exp_p, status_path=st_p,
        reports_dir=rep_p, run_id="rid_429b",
        http_get_json=fake, now_epoch=FakeClock(),
    )
    # The cycle captures the per-address error but does not fail overall
    assert r.per_address[0]["backfill_status"] == "error"
    st = json.loads(st_p.read_text())
    assert st["exit_status"] == "error"


def test_run_cycle_dryrun_does_not_write_db(tmp_path: Path):
    addr = "0x" + "a" * 40
    row = {
        "proxyWallet": addr, "transactionHash": "0x" + "h" * 64,
        "timestamp": 100, "type": "TRADE", "conditionId": "0x" + "c" * 64,
        "asset": "1", "side": "BUY", "outcomeIndex": 0,
    }
    fake, _ = make_fake_http([[row]])
    db_p = tmp_path / "poly.db"
    exp_p = tmp_path / "export"
    st_p = tmp_path / "status.json"
    rep_p = tmp_path / "reports"
    r = m._run_cycle_core(
        addresses=[addr], db_path=db_p, export_dir=exp_p, status_path=st_p,
        reports_dir=rep_p, run_id="rid_dry",
        write_db=False, write_export=False, write_reports=False, write_status=True,
        http_get_json=fake, now_epoch=FakeClock(),
        backfill_cap_pages=0,
    )
    assert r.ok
    # No DB file (we never opened it)
    assert not db_p.exists()
    # status.json written
    assert st_p.exists()


# -----------------------------------------------------------------------------
# Probe mode
# -----------------------------------------------------------------------------


def test_run_probe_writes_reports(tmp_path: Path):
    addr = "0x" + "a" * 40
    row = {
        "proxyWallet": addr, "transactionHash": "0x" + "h" * 64,
        "timestamp": 1700000000, "type": "TRADE", "conditionId": "0x" + "c" * 64,
        "asset": "1", "side": "BUY", "outcomeIndex": 0,
        "title": "T", "slug": "btc-updown-5m-1",
    }
    calls = {"n": 0}

    def fake(url, params, timeout, user_agent):
        calls["n"] += 1
        if calls["n"] == 1:
            return 200, json.dumps([row]), {}
        if calls["n"] == 2:
            # offset=5000 calibration
            return 200, "[]", {}
        return 200, "[]", {}

    out_dir = m.run_probe(
        [addr], reports_dir=tmp_path, run_id="rid_probe",
        http_get_json=fake,
    )
    assert (out_dir / "addresses_resolved.json").exists()
    ar = json.loads((out_dir / "addresses_resolved.json").read_text())
    assert ar["summary"]["total"] == 1
    assert ar["summary"]["with_activity"] == 1
    aps = json.loads((out_dir / "api_probe_summary.json").read_text())
    assert aps["observed_offset_ceiling"] == 3000
    assert "user" in aps["supported_query_params"]
    assert (out_dir / "ONEPAGE_CN.md").exists()
    assert (out_dir / "ARTIFACT_INDEX.md").exists()
