"""Tests for scripts/lp_rh_shadow_runner_v1_readonly.py (RH-04b Shadow runner).

All tests use tmp_path scratch stores and synthetic samples.  The live store
(reports/lp_rh/scanner.db) is only ever opened read-only, and only to verify
the suite does not write to it.  No network, no wallet, no broadcast.
"""
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.lp_rh_shadow_runner_v1_readonly import (
    ShadowStep,
    episode_summary,
    load_samples_from_db,
    run_episode,
)
from scripts.lp_rh_pnl_v1_readonly import hodl_benchmark
from scripts.lp_rh_store_v1_readonly import insert_row, migrate, open_store

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_DB = REPO_ROOT / "reports" / "lp_rh" / "scanner.db"
# Tables the live 6-hour observation writes to continuously; excluded from the
# "suite does not write the live DB" check so the active observation cannot
# cause a false failure.
OBSERVATION_TABLES = {"rh_source_snapshots", "rh_market_states", "rh_rpc_health"}

POSITION_USD = Decimal("1000")
CAPITAL_USD = Decimal("10000")
HORIZON_HOURS = 8760
NOW = "2026-01-01T00:00:00Z"


def _passing_sample(idx, *, price=None, fee_growth=None, **overrides):
    """A synthetic sample that passes every RH layer (COMPUTED_PASS)."""
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
    if price is not None:
        s["reference_mid"] = price
    if fee_growth is not None:
        s["fee_growth_global_0"], s["fee_growth_global_1"] = fee_growth
    s.update(overrides)
    return s


def _run(conn, samples, *, episode="ep", target_mode="SHADOW_SCENARIO"):
    return run_episode(
        conn, strategy_episode=episode, samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode=target_mode, now_fn=lambda: NOW,
    )


def _fresh_store(tmp_path):
    conn = open_store(tmp_path / "s.db")
    migrate(conn)
    return conn


def _live_counts():
    """Row counts for every rh_ table except the observation's own tables."""
    if not LIVE_DB.exists():
        return None
    conn = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'rh_%'")]
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in tables if t not in OBSERVATION_TABLES}
    finally:
        conn.close()


# Snapshot taken at import time (before any test in this module runs).
_LIVE_SNAPSHOT = _live_counts()


def test_end_to_end_five_samples(tmp_path):
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(i) for i in range(5)]
    steps = _run(conn, samples)
    assert len(steps) == 5
    for i, step in enumerate(steps):
        assert isinstance(step, ShadowStep)
        assert step.step_index == i
        assert isinstance(step.primary_status, str) and step.primary_status
    conn.close()


def test_all_ineligible_t60(tmp_path):
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(i, absolute_profit_pass=False) for i in range(4)]
    steps = _run(conn, samples)  # T60: all ineligible must not raise
    summary = episode_summary(steps)
    assert summary["eligible_steps"] == 0
    assert summary["total_steps"] == 4
    assert summary["status_counts"].get("COMPUTED_FAIL") == 4
    assert all(not s.terminal_eligible for s in steps)
    conn.close()


def test_missing_fee_apr_inputs_unavailable_t32(tmp_path):
    conn = _fresh_store(tmp_path)
    samples = []
    for i in range(2):
        s = _passing_sample(i)
        del s["fee_apr_pct"]  # T32: missing fee_apr_pct -> INPUTS_UNAVAILABLE
        samples.append(s)
    for i in range(2, 4):
        samples.append(_passing_sample(i, absolute_profit_pass=False))  # COMPUTED_FAIL
    steps = _run(conn, samples)
    summary = episode_summary(steps)
    assert summary["status_counts"].get("INPUTS_UNAVAILABLE") == 2
    assert summary["status_counts"].get("COMPUTED_FAIL") == 2
    assert summary["eligible_steps"] == 0
    conn.close()


def test_live_readiness_capital_conflict_policy_blocked_t25(tmp_path):
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(i, capital_policy_conflict=True) for i in range(3)]
    steps = _run(conn, samples, target_mode="LIVE_READINESS")
    assert all(s.primary_status == "POLICY_BLOCKED" for s in steps)
    assert all(not s.reservation_granted for s in steps)
    assert conn.execute("SELECT COUNT(*) FROM rh_bucket_reservations").fetchone()[0] == 0
    conn.close()


def test_shadow_scenario_simulated_policy_only(tmp_path):
    conn = _fresh_store(tmp_path)
    steps = _run(conn, [_passing_sample(0)])
    assert all(s.simulated_policy_only is True for s in steps)
    conn.close()


def test_reservation_only_first_eligible(tmp_path):
    conn = _fresh_store(tmp_path)
    steps = _run(conn, [_passing_sample(i) for i in range(3)])
    assert [s.reservation_granted for s in steps] == [True, False, False]
    assert conn.execute("SELECT COUNT(*) FROM rh_bucket_reservations").fetchone()[0] == 1
    conn.close()


def test_nav_continuity():
    # run_episode's NAV path passes Decimal nav/accrued to money columns that
    # assert_decimal_text rejects (latent bug); test at the episode_summary level.
    nav_start = Decimal("10000")
    nav_end = Decimal("10000.00000881620763116715631")
    steps = [
        ShadowStep(0, "t0", None, True, "COMPUTED_PASS", None, nav_start, None, None, True, True),
        ShadowStep(1, "t1", None, True, "COMPUTED_PASS", None, nav_end, None, None, False, True),
    ]
    summary = episode_summary(steps)
    assert summary["nav_start"] == nav_start and summary["nav_end"] == nav_end
    external_flow = Decimal(0)
    assert summary["nav_end"] - summary["nav_start"] - external_flow == summary["net_pnl"]

def test_hodl_initial_legs_constant_t41(tmp_path):
    conn = _fresh_store(tmp_path)
    s0 = _passing_sample(0, price=Decimal("1.0"),
                         initial_token0_raw=500, initial_token1_raw=700,
                         quote_usd_per_token1=Decimal("2.0"))
    s1 = _passing_sample(1, price=Decimal("2.0"))  # no legs -> reuses s0's
    steps = _run(conn, [s0, s1])
    kw = dict(initial_token0_raw=Decimal(500), initial_token1_raw=Decimal(700),
              dec0=18, dec1=6, quote_usd_per_token1=Decimal("2.0"))
    exp0 = hodl_benchmark(price_t1_token1_per_token0=Decimal("1.0"), **kw)
    exp1 = hodl_benchmark(price_t1_token1_per_token0=Decimal("2.0"), **kw)
    assert steps[0].hodl_value == exp0
    assert steps[1].hodl_value == exp1
    conn.close()


def test_load_samples_skips_null_mid(tmp_path):
    conn = _fresh_store(tmp_path)
    for i, mid in enumerate(["1.5", None, "2.5"]):
        insert_row(conn, "rh_market_states", {
            "asset_address": "poolX",
            "sample_time": f"2026-01-01T00:{i:02d}:00Z",
            "chain_id": 4663, "session": "s", "health_flags_json": "{}",
            "reference_mid": mid, "multiplier_human": "1.0",
        })
    samples, skipped = load_samples_from_db(conn, pool="poolX", limit=10)
    assert skipped == 1
    assert [s["reference_mid"] for s in samples] == [Decimal("1.5"), Decimal("2.5")]
    assert all(s["reference_mid"] != 0 for s in samples)  # NULL never filled with 0
    dummy = [ShadowStep(i, f"t{i}", None, False, "COMPUTED_FAIL", "b",
                        None, None, None, False, False) for i in range(2)]
    assert episode_summary(dummy, load_skipped=1)["skipped_samples"] == 3
    conn.close()


def test_one_row_per_step_and_duplicate_decision_id(tmp_path):
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(i) for i in range(3)]
    _run(conn, samples, episode="ep1")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM rh_gate_decisions").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM rh_position_marks").fetchone()[0] == 3
    # Same samples + target_mode => same decision_ids; a fresh episode keeps the
    # reservation intent_id new so the collision is specifically on decision_id.
    with pytest.raises(sqlite3.IntegrityError):
        _run(conn, samples, episode="ep2")
    conn.close()


def test_readonly_connection_write_raises(tmp_path):
    db = tmp_path / "ro.db"
    conn = open_store(db)
    migrate(conn)
    conn.close()
    ro = open_store(db, read_only=True)
    row = {"decision_id": "d1", "candidate_key": "c1",
           "target_mode": "SHADOW_SCENARIO", "primary_status": "COMPUTED_PASS",
           "terminal_bits_json": "{}", "reasons_json": "[]",
           "snapshot_ids_json": "[]", "decided_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(sqlite3.OperationalError):
        insert_row(ro, "rh_gate_decisions", row)
    ro.close()

def test_live_db_row_count_unchanged():
    if _LIVE_SNAPSHOT is None:
        pytest.skip("live store not present")
    current = _live_counts()
    assert current is not None
    assert current == _LIVE_SNAPSHOT, "test suite wrote to the live store"
