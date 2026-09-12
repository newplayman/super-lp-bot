"""Tests for the RH-02ab replay-clock fix in lp_rh_shadow_runner_v1_readonly.

run_episode judged each sample's gate at the wall clock (now_fn()) instead of
the sample's own sample_time, so replaying ~200 samples spanning ~50 min made
the earliest samples stale and market_and_chain_risk_pass failed on all of
them.  Fix: the three gate-decision now values use sample_time (falling back to
now_fn() when missing/unparseable); mark_time and recording uses unchanged.
All tests use tmp_path scratch stores and synthetic samples; no network."""
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.lp_rh_shadow_runner_v1_readonly import (
    compute_conjuncts,
    run_episode,
)
from scripts.lp_rh_store_v1_readonly import migrate, open_store

POSITION_USD = Decimal("1000")
CAPITAL_USD = Decimal("10000")
HORIZON_HOURS = 8760


def _passing_sample(idx, **overrides):
    s = {
        "candidate_key": f"pool-{idx}",
        "sample_time": f"2026-01-01T00:{idx:02d}:00Z",
        "chain_id": 4663,
        "attestation_status": "ATTESTED_SAME_BLOCK",
        "protocol": "v3",
        "fee_apr_pct": 100.0,
        "sigma_daily": 0.0,
        "liquidity_raw": 1e20,
        "sqrt_price_x96": 4_340_000_000_000_000_000_000_000_000_000,
        "fee": 500,
        "dec0": 18,
        "dec1": 6,
        "gas_usd_estimate": 0.01,
        "legacy_required_conjunction": True,
        "identity_verified": True,
        "protocol_capabilities_sufficient": True,
        "data_complete_and_fresh": True,
        "profile_policy_pass": True,
        "market_and_chain_risk_pass": True,
        "absolute_profit_pass": True,
        "position_and_exit_depth_pass": True,
        "capital_policy_pass": True,
    }
    s.update(overrides)
    return s


def _replay_sample(idx, *, sample_time, source_event_time, **overrides):
    """Sample passing all conjuncts except market_and_chain_risk_pass (clock-computed)."""
    s = _passing_sample(idx, **overrides)
    del s["market_and_chain_risk_pass"]
    s["sample_time"] = sample_time
    s["source_event_time"] = source_event_time
    s["oracle_heartbeat_secs"] = 3600
    s["reference_age_secs"] = 10
    s["source_payload_hash"] = "abc123"
    return s


def _run(conn, samples, *, episode="ep", now="2026-09-08T19:00:00Z",
         pool_meta=None):
    return run_episode(
        conn, strategy_episode=episode, samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode="SHADOW_SCENARIO",
        now_fn=lambda: now,
        pool_meta=pool_meta if pool_meta is not None else _DEFAULT_POOL_META,
    )


def _fresh(tmp_path):
    conn = open_store(tmp_path / "s.db")
    migrate(conn)
    return conn


_GATED = {"fee_ev_usd": "40", "entry_cost_usd": "1",
          "exit_cost_usd": "1", "gas_usd": "0.02"}
# R3 / Package D: pool_meta must carry as_of and attestation; conjunct
# gate refuses samples with as-of-unknown evidence.
_META = {"attestation_status": "ATTESTED_SAME_BLOCK", "protocol": "v3",
         "as_of": "2026-09-08T18:00:00Z", "dec0": 18, "dec1": 6,
         "range_pct": 10.0, "pool_address": "0xpool-replay-clock"}
_DEFAULT_POOL_META = _META


# 1. RTH sample, source 2s before sample_time, wall clock 1h later: PASSES.
def test_rth_sample_judged_at_sample_time_passes(tmp_path):
    conn = _fresh(tmp_path)
    s = _replay_sample(0, sample_time="2026-09-08T18:00:00Z", source_event_time="2026-09-08T17:59:58Z")
    steps = _run(conn, [s], now="2026-09-08T19:00:00Z")
    assert len(steps) == 1 and steps[0].terminal_eligible is True
    conn.close()


# 2. Same sample: clean at sample_time, API_STALE+ORACLE_STALE at wall clock.
def test_same_sample_flags_clean_at_sample_time_stale_at_wall_clock():
    s = _replay_sample(0, sample_time="2026-09-08T18:00:00Z", source_event_time="2026-09-08T17:59:58Z")
    kw = dict(pool_meta=_META, capital_usd=CAPITAL_USD, position_usd=POSITION_USD)
    bits_at_sample, _ = compute_conjuncts(s, _GATED, now="2026-09-08T18:00:00Z", **kw)
    assert bits_at_sample["market_and_chain_risk_pass"] is True
    bits_at_wall, _ = compute_conjuncts(s, _GATED, now="2026-09-08T19:00:00Z", **kw)
    assert bits_at_wall["market_and_chain_risk_pass"] is False


# 3. source 1h before sample_time: sample itself stale -> must NOT pass.
def test_stale_source_event_time_fails_even_at_sample_time(tmp_path):
    conn = _fresh(tmp_path)
    s = _replay_sample(0, sample_time="2026-09-08T18:00:00Z", source_event_time="2026-09-08T16:59:58Z")
    steps = _run(conn, [s], now="2026-09-08T19:00:00Z")
    assert steps[0].terminal_eligible is False
    conn.close()


# 4. sample_time None: falls back to wall clock; old data -> step fails.
def test_none_sample_time_fails(tmp_path):
    conn = _fresh(tmp_path)
    s = _replay_sample(0, sample_time=None, source_event_time="2026-09-08T17:00:00Z")
    steps = _run(conn, [s], now="2026-09-08T19:00:00Z")
    assert steps[0].terminal_eligible is False
    conn.close()


# 5. sample_time unparseable: episode aborts fail-closed at the store layer
#    (pre-existing mark_time validation the fix does not touch) -> never passes.
def test_unparseable_sample_time_aborts_fail_closed(tmp_path):
    conn = _fresh(tmp_path)
    s = _replay_sample(0, sample_time="not-a-timestamp", source_event_time="2026-09-08T17:00:00Z")
    with pytest.raises(ValueError, match="NON_UTC_TIMESTAMP"):
        _run(conn, [s], now="2026-09-08T19:00:00Z")
    conn.close()


# 6. OVERNIGHT sample with fresh data: session restriction still blocks.
def test_overnight_sample_fails_even_with_fresh_data(tmp_path):
    conn = _fresh(tmp_path)
    s = _replay_sample(0, sample_time="2026-09-08T02:00:00Z", source_event_time="2026-09-08T01:59:58Z")
    steps = _run(conn, [s], now="2026-09-08T03:00:00Z")
    assert steps[0].terminal_eligible is False
    conn.close()


# 7. halt=True: HALT flag still blocks even in RTH with fresh data.
def test_halt_sample_fails(tmp_path):
    conn = _fresh(tmp_path)
    s = _replay_sample(0, sample_time="2026-09-08T18:00:00Z", source_event_time="2026-09-08T17:59:58Z", halt=True)
    steps = _run(conn, [s], now="2026-09-08T19:00:00Z")
    assert steps[0].terminal_eligible is False
    conn.close()


# 8. mark_time still equals sample_time (regression: unchanged by the fix).
def test_mark_time_equals_sample_time(tmp_path):
    conn = _fresh(tmp_path)
    s = _replay_sample(0, sample_time="2026-09-08T18:00:00Z", source_event_time="2026-09-08T17:59:58Z")
    _run(conn, [s], now="2026-09-08T19:00:00Z")
    conn.commit()
    row = conn.execute("SELECT mark_time FROM rh_position_marks "
                       "WHERE position_id = 'rh-shadow-ep'").fetchone()
    assert row is not None and row[0] == "2026-09-08T18:00:00Z"
    conn.close()


# 9. Per-sample progression: each decided_at equals its own sample_time
#    (no lookahead into later samples, T36).
def test_per_sample_decided_at_uses_own_sample_time(tmp_path):
    conn = _fresh(tmp_path)
    samples = [_replay_sample(i, sample_time=f"2026-09-08T18:{i:02d}:00Z",
                              source_event_time=f"2026-09-08T18:{i:02d}:00Z") for i in range(3)]
    _run(conn, samples, now="2026-09-08T19:00:00Z")
    conn.commit()
    rows = conn.execute("SELECT decided_at FROM rh_gate_decisions "
                        "ORDER BY candidate_key").fetchall()
    assert [r[0] for r in rows] == [f"2026-09-08T18:{i:02d}:00Z" for i in range(3)]
    conn.close()


# 10. 200 samples spanning ~1h, all fresh: every step passes (no decay from
#     the window span, which was the original bug).
def test_200_samples_spanning_one_hour_all_pass(tmp_path):
    conn = _fresh(tmp_path)
    start = datetime(2026, 9, 8, 17, 0, 0, tzinfo=timezone.utc)
    samples = []
    for i in range(200):
        t = (start + timedelta(seconds=i * 18)).isoformat().replace("+00:00", "Z")
        samples.append(_replay_sample(i, sample_time=t, source_event_time=t))
    # R3 / Package D: pool_meta.as_of must align with the sample window
    # (samples start at 17:00, so as_of must be ≤ 17:00 to avoid
    # POOL_STATE_AS_OF_IN_FUTURE).
    pm = dict(_DEFAULT_POOL_META, as_of="2026-09-08T17:00:00Z")
    steps = _run(conn, samples, now="2026-09-08T19:00:00Z", pool_meta=pm)
    assert len(steps) == 200 and all(s.terminal_eligible for s in steps)
    conn.close()


# 11. decided_at in rh_gate_decisions equals sample_time (the gate's clock).
def test_decided_at_equals_sample_time(tmp_path):
    conn = _fresh(tmp_path)
    s = _replay_sample(0, sample_time="2026-09-08T18:00:00Z", source_event_time="2026-09-08T17:59:58Z")
    _run(conn, [s], now="2026-09-08T19:00:00Z")
    conn.commit()
    row = conn.execute("SELECT decided_at FROM rh_gate_decisions "
                       "WHERE candidate_key = 'pool-0@2026-09-08T18:00:00Z'").fetchone()
    assert row is not None and row[0] == "2026-09-08T18:00:00Z"
    conn.close()


# 12. Reservation created_at equals sample_time (try_reserve uses decision_now).
def test_reservation_created_at_equals_sample_time(tmp_path):
    conn = _fresh(tmp_path)
    s = _replay_sample(0, sample_time="2026-09-08T18:00:00Z", source_event_time="2026-09-08T17:59:58Z")
    _run(conn, [s], now="2026-09-08T19:00:00Z")
    conn.commit()
    row = conn.execute("SELECT created_at FROM rh_bucket_reservations "
                       "WHERE intent_id = 'rh-shadow-ep-0'").fetchone()
    assert row is not None and row[0] == "2026-09-08T18:00:00Z"
    conn.close()


# 13. Three samples at different RTH times, all fresh: each judged at its
#     own time, all pass.
def test_multiple_samples_each_judged_at_own_time(tmp_path):
    conn = _fresh(tmp_path)
    samples = [
        _replay_sample(0, sample_time="2026-09-08T18:00:00Z", source_event_time="2026-09-08T17:59:58Z"),
        _replay_sample(1, sample_time="2026-09-08T18:30:00Z", source_event_time="2026-09-08T18:29:58Z"),
        _replay_sample(2, sample_time="2026-09-08T15:59:00Z", source_event_time="2026-09-08T15:58:58Z"),
    ]
    # R3 / Package D: as_of must pre-date the earliest sample (15:59).
    pm = dict(_DEFAULT_POOL_META, as_of="2026-09-08T15:00:00Z")
    steps = _run(conn, samples, now="2026-09-08T20:00:00Z", pool_meta=pm)
    assert len(steps) == 3 and all(s.terminal_eligible for s in steps)
    conn.close()


# 14. POSTMARKET sample (17:00 ET = 21:00 UTC) with fresh data: session
#     restriction still blocks.
def test_postmarket_sample_fails(tmp_path):
    conn = _fresh(tmp_path)
    s = _replay_sample(0, sample_time="2026-09-08T21:00:00Z", source_event_time="2026-09-08T20:59:58Z")
    steps = _run(conn, [s], now="2026-09-08T22:00:00Z")
    assert steps[0].terminal_eligible is False
    conn.close()
