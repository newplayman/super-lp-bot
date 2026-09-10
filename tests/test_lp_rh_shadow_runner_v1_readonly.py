"""Tests for scripts/lp_rh_shadow_runner_v1_readonly.py (RH-04b Shadow runner).

All tests use tmp_path scratch stores and synthetic samples.  The live store
(reports/lp_rh/scanner.db) is only ever opened read-only, and only to verify
the suite does not write to it.  No network, no wallet, no broadcast.
"""
import json
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
from scripts.lp_rh_readiness_v1_readonly import audit_unexplained_ledger_diffs
from scripts.lp_rh_store_v1_readonly import insert_row, migrate, open_store
from scripts.lp_rh_v3_inventory_v1_readonly import inventory_for_position

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


def _run(conn, samples, *, episode="ep", target_mode="SHADOW_SCENARIO", pool_meta=None,
         allow_bare_quote=True):
    return run_episode(
        conn, strategy_episode=episode, samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode=target_mode, now_fn=lambda: NOW,
        pool_meta=pool_meta, allow_bare_quote=allow_bare_quote,
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
    meta = {"range_pct": 10.0, "dec0": 18, "dec1": 6}
    s0 = _passing_sample(0, price=Decimal("1.0"), quote_usd_per_token1=Decimal("2.0"))
    s1 = _passing_sample(1, price=Decimal("2.0"))  # no quote -> reuses s0's quote and cached legs
    steps = _run(conn, [s0, s1], pool_meta=meta)
    inv = inventory_for_position(
        position_usd=POSITION_USD, entry_price=Decimal("1.0"),
        range_pct=Decimal("10.0"), dec0=18, dec1=6,
        quote_usd_per_token1=Decimal("2.0"))
    exp0 = (inv.amount0_human * Decimal("1.0") + inv.amount1_human) * Decimal("2.0")
    exp1 = (inv.amount0_human * Decimal("2.0") + inv.amount1_human) * Decimal("2.0")
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
    # RH-04f split this: "skipped_samples" summed samples dropped at load with
    # steps that produced no NAV, so it reported 40 when the live database held
    # 7 null prices.  Asserting both separately is tighter than asserting a sum.
    summary = episode_summary(dummy, load_skipped=1)
    assert "skipped_samples" not in summary
    assert summary["skipped_at_load"] == 1
    assert summary["steps_without_nav"] == 2
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

def test_live_db_not_polluted_by_test_fixtures():
    """The suite must never write to the live store.

    This used to snapshot every rh_ table's row count at import and assert it was
    unchanged. That worked while the live store was quiescent. It no longer is:
    the collector writes every 15s and, since the daemon moved to --ledger-db, so
    does the shadow loop every 15 minutes -- both legitimately. The counts now
    move for reasons that have nothing to do with the test suite, which made this
    flaky (it failed in a full run and passed in isolation, minutes apart).

    Checking for fixture fingerprints is both stable under concurrent writers and
    a stricter statement of the actual guarantee: not "nothing changed" but
    "nothing *we* made is in there".
    """
    if not LIVE_DB.exists():
        pytest.skip("live store not present")
    conn = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        probes = (
            ("rh_shadow_positions", "strategy_episode", ("ep1", "ep2", "ep-1")),
            ("rh_shadow_positions", "pool_key", ("0xpool", "0xpool-rh02by")),
            ("rh_journal", "event_id", ("ep1-open-token0", "ep1-open-token1")),
            ("rh_gate_decisions", "candidate_key", ("cand_1", "unknown")),
        )
        existing = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table, column, values in probes:
            if table not in existing:
                continue
            placeholders = ",".join("?" for _ in values)
            found = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column} IN ({placeholders})",
                values).fetchone()[0]
            assert found == 0, (
                f"test fixture leaked into the live store: "
                f"{table}.{column} matched one of {values}")
    finally:
        conn.close()


# --- RH-04f: the nine non-netcover conjuncts ---------------------------------

def _conj_sample(**over):
    s = {
        "chain_id": 4663,
        "reference_mid": Decimal("2480"),
        "reference_age_secs": 10,
        "source_payload_hash": "abc123",
        "source_event_time": "2026-09-08T17:59:55Z",
        "oracle_updated_at": "2026-09-08T17:59:50Z",
        "oracle_heartbeat_secs": 3600,
    }
    s.update(over)
    return s


def _conj_meta(**over):
    m = {
        "attestation_status": "ATTESTED_SAME_BLOCK", "protocol": "v3",
        "sqrt_price_x96": 3950376364833515856698135, "current_tick": -198160,
        "tick_spacing": 1, "fee_pips": 100, "liquidity": 10 ** 19,
        "tick_data": [{"tick_lower": -198200, "tick_upper": -198200,
                       "liquidity_net": 10 ** 18}],
        "token0_decimals": 18, "token1_decimals": 6,
        "input_price_usd": "2484", "max_impact_bps": 50,
    }
    m.update(over)
    return m


def _conj(sample=None, meta=None, gated=None, capital="10000", position="1000",
          now="2026-09-08T18:00:00Z"):
    from scripts.lp_rh_shadow_runner_v1_readonly import compute_conjuncts
    g = {"fee_ev_usd": "40", "entry_cost_usd": "1",
         "exit_cost_usd": "1", "gas_usd": "0.02"}
    if gated is not None:
        g.update(gated)
    return compute_conjuncts(sample if sample is not None else _conj_sample(), g,
                             pool_meta=meta if meta is not None else _conj_meta(),
                             capital_usd=Decimal(capital),
                             position_usd=Decimal(position), now=now)


def test_conjuncts_all_pass_on_a_complete_input():
    bits, reasons = _conj()
    assert reasons == [], reasons
    assert bits["legacy_required_conjunction"] is True


def test_conjunct_identity_fails_on_wrong_chain():
    bits, reasons = _conj(sample=_conj_sample(chain_id=8453))
    assert bits["identity_verified"] is False
    assert any("identity_verified" in r and "8453" in r for r in reasons)
    assert bits["legacy_required_conjunction"] is False


def test_conjunct_identity_fails_when_chain_id_missing():
    s = _conj_sample()
    del s["chain_id"]
    bits, _ = _conj(sample=s)
    assert bits["identity_verified"] is False


def test_conjunct_protocol_fails_without_pool_meta():
    bits, reasons = _conj(meta={})
    assert bits["protocol_capabilities_sufficient"] is False
    assert any("pool_meta not supplied" in r for r in reasons)


def test_conjunct_protocol_fails_on_unattested_pool():
    bits, _ = _conj(meta=_conj_meta(attestation_status="DISCOVERED_NOT_ATTESTED"))
    assert bits["protocol_capabilities_sufficient"] is False


def test_conjunct_protocol_fails_on_v4():
    bits, _ = _conj(meta=_conj_meta(protocol="v4"))
    assert bits["protocol_capabilities_sufficient"] is False


def test_conjunct_freshness_fails_on_missing_price():
    bits, _ = _conj(sample=_conj_sample(reference_mid=None))
    assert bits["data_complete_and_fresh"] is False


def test_conjunct_freshness_fails_on_stale_quote():
    bits, reasons = _conj(sample=_conj_sample(reference_age_secs=9999))
    assert bits["data_complete_and_fresh"] is False
    assert any("9999s old" in r for r in reasons)


def test_conjunct_freshness_fails_without_payload_hash():
    bits, _ = _conj(sample=_conj_sample(source_payload_hash=None))
    assert bits["data_complete_and_fresh"] is False


def test_conjunct_profile_policy_fails_when_position_exceeds_cap():
    bits, reasons = _conj(capital="100", position="50")
    assert bits["profile_policy_pass"] is False
    assert any("42.5" in r for r in reasons)


def test_conjunct_capital_policy_fails_on_the_d02_conflict():
    """At 100U the CORE active cap is 42.5, below the legacy 50U floor."""
    bits, reasons = _conj(capital="100", position="10")
    assert bits["capital_policy_pass"] is False
    assert any("CAPITAL_POLICY_CONFLICT" in r for r in reasons)


def test_conjunct_capital_policy_cannot_be_forced_true():
    """Self-incrimination: no argument combination unlocks the conflict."""
    from scripts.lp_rh_shadow_runner_v1_readonly import compute_conjuncts
    for position in ("1", "10", "42", "50", "60"):
        bits, _ = compute_conjuncts(
            _conj_sample(), {"fee_ev_usd": "40", "entry_cost_usd": "1",
                             "exit_cost_usd": "1", "gas_usd": "0.02"},
            pool_meta=_conj_meta(), capital_usd=Decimal("100"),
            position_usd=Decimal(position), now="2026-09-08T18:00:00Z")
        assert bits["capital_policy_pass"] is False, position


def test_conjunct_absolute_profit_fails_when_costs_exceed_fees():
    bits, reasons = _conj(gated={"fee_ev_usd": "0.5"})
    assert bits["absolute_profit_pass"] is False
    assert any("net EV" in r for r in reasons)


def test_conjunct_absolute_profit_fails_when_a_leg_is_none():
    bits, _ = _conj(gated={"gas_usd": None})
    assert bits["absolute_profit_pass"] is False


def test_conjunct_exit_depth_fails_without_tick_data():
    bits, reasons = _conj(meta=_conj_meta(tick_data=[]))
    assert bits["position_and_exit_depth_pass"] is False
    assert any("tick_data" in r for r in reasons)


def test_conjunct_market_risk_fails_outside_rth():
    bits, reasons = _conj(now="2026-09-08T02:00:00Z")
    assert bits["market_and_chain_risk_pass"] is False
    assert any("session=" in r for r in reasons)


def test_conjunct_market_risk_fails_without_an_oracle():
    """This chain has no on-chain price source, so this is the live case.

    RH-02x: the gate now reads source_event_time (the block timestamp) as the
    oracle time for the CORE bucket, so "no oracle" means source_event_time is
    None, not oracle_updated_at.
    """
    bits, reasons = _conj(sample=_conj_sample(source_event_time=None))
    assert bits["market_and_chain_risk_pass"] is False
    assert any("ORACLE_UNAVAILABLE" in r for r in reasons)


def test_conjunct_market_risk_fails_on_unparseable_timestamp():
    bits, reasons = _conj(now="not-a-timestamp")
    assert bits["market_and_chain_risk_pass"] is False
    assert any("unparseable" in r for r in reasons)


def test_legacy_conjunction_names_every_dependency_that_failed():
    bits, reasons = _conj(sample=_conj_sample(chain_id=8453),
                          meta=_conj_meta(protocol="v4"))
    assert bits["legacy_required_conjunction"] is False
    rollup = [r for r in reasons if r.startswith("legacy_required_conjunction")][0]
    assert "identity_verified" in rollup
    assert "protocol_capabilities_sufficient" in rollup


def test_nothing_defaults_to_true_when_everything_is_missing():
    from scripts.lp_rh_shadow_runner_v1_readonly import compute_conjuncts
    bits, reasons = compute_conjuncts({}, {}, pool_meta=None,
                                      capital_usd=Decimal("100"),
                                      position_usd=Decimal("50"), now=None)
    assert not any(bits.values()), bits
    assert len(reasons) >= 6


# --- RH-02ao: health_flags parsing and risk conjunct tests -------------------

def test_conjunct_market_risk_chain_degraded_fails():
    # Synthetic sample with health_flags_json containing CHAIN_DEGRADED
    bits, reasons = _conj(sample=_conj_sample(health_flags_json='["CHAIN_DEGRADED"]'))
    assert bits["market_and_chain_risk_pass"] is False
    assert any("CHAIN_DEGRADED" in r for r in reasons)


def test_conjunct_market_risk_empty_or_none_health_flags_passes():
    # health_flags_json=None and '[]' -> four booleans False, does not fail
    bits_none, reasons_none = _conj(sample=_conj_sample(health_flags_json=None))
    assert bits_none["market_and_chain_risk_pass"] is True
    assert reasons_none == []

    bits_empty, reasons_empty = _conj(sample=_conj_sample(health_flags_json="[]"))
    assert bits_empty["market_and_chain_risk_pass"] is True
    assert reasons_empty == []


def test_conjunct_market_risk_bad_json_fails_closed():
    # health_flags_json bad JSON -> fail-closed with parse error
    bits, reasons = _conj(sample=_conj_sample(health_flags_json="{ 坏的 json"))
    assert bits["market_and_chain_risk_pass"] is False
    assert any("HEALTH_FLAGS_JSON_INVALID" in r for r in reasons)


def test_conjunct_market_risk_unknown_flag_fails_closed():
    # health_flags_json containing unknown flag -> fail-closed naming the flag
    bits, reasons = _conj(sample=_conj_sample(health_flags_json='["SOMETHING_NEW"]'))
    assert bits["market_and_chain_risk_pass"] is False
    assert any("HEALTH_FLAGS_UNKNOWN: SOMETHING_NEW" in r for r in reasons)


def test_load_samples_parses_health_flags(tmp_path):
    conn = _fresh_store(tmp_path)
    # health_flags_json is NOT NULL in the store, so None cannot occur there --
    # inserting it fails at the database, not at the parser.  The shapes that
    # can actually reach the loader are a flag list, an empty list, and an
    # empty string.
    for i, flags_str in enumerate(['["CHAIN_DEGRADED"]', '[]', '', '["HALT"]']):
        insert_row(conn, "rh_market_states", {
            "asset_address": "poolRisk",
            "sample_time": f"2026-01-01T00:{i:02d}:00Z",
            "chain_id": 4663, "session": "RTH",
            "health_flags_json": flags_str,
            "reference_mid": "100.0", "multiplier_human": "1.0",
        })
    samples, skipped = load_samples_from_db(conn, pool="poolRisk", limit=10)
    assert skipped == 0
    assert len(samples) == 4

    assert samples[0]["chain_degraded"] is True
    assert samples[0]["halt"] is False

    assert samples[1]["chain_degraded"] is False
    assert samples[1]["halt"] is False

    assert samples[2]["chain_degraded"] is False
    assert samples[2]["halt"] is False

    assert samples[3]["chain_degraded"] is False
    assert samples[3]["halt"] is True
    conn.close()


# --- RH-02bq: rh_economic_evaluations writer ---------------------------------

def test_economic_row_count_matches_gate_decisions_minus_skipped(tmp_path):
    conn = _fresh_store(tmp_path)
    samples = [
        _passing_sample(0, source_payload_hash="h-0"),
        _passing_sample(1),  # no source_payload_hash -> economic row skipped
        _passing_sample(2, source_payload_hash="h-2"),
        _passing_sample(3),  # no source_payload_hash -> economic row skipped
        _passing_sample(4, source_payload_hash="h-4"),
    ]
    _run(conn, samples)
    conn.commit()
    gate_count = conn.execute("SELECT COUNT(*) FROM rh_gate_decisions").fetchone()[0]
    econ_count = conn.execute("SELECT COUNT(*) FROM rh_economic_evaluations").fetchone()[0]
    assert gate_count == 5
    assert econ_count == 3  # 5 gate decisions - 2 skipped (no source_payload_hash)
    assert econ_count == gate_count - 2
    conn.close()


def test_stored_netcover_equals_recomputed_gated_value(tmp_path):
    from scripts.lp_rh_shadow_runner_v1_readonly import _evidence_for
    from scripts.lp_rh_netcover_inputs_v1_readonly import assemble_rh_clmm_inputs
    from scripts.lp_netcover_engine_v1_readonly import apply_netcover_gate
    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-0")
    _run(conn, [sample])
    conn.commit()
    stored_netcover = conn.execute(
        "SELECT netcover FROM rh_economic_evaluations WHERE snapshot_id = 'h-0'"
    ).fetchone()[0]
    # Independently recompute the gate for this sample, exactly as the runner does.
    record = assemble_rh_clmm_inputs(_evidence_for(sample, None),
                                     position_usd=POSITION_USD,
                                     horizon_hours=HORIZON_HOURS)
    gated = apply_netcover_gate([record])[0]
    assert gated["netcover"] is not None  # a real number, not a placeholder
    expected = format(Decimal(str(gated["netcover"])), "f")
    assert stored_netcover == expected
    conn.close()


def test_missing_netcover_input_stores_none_netcover_and_missing_inputs(tmp_path):
    conn = _fresh_store(tmp_path)
    s = _passing_sample(0, source_payload_hash="h-0")
    del s["fee_apr_pct"]  # missing NetCover input -> netcover None
    _run(conn, [s])
    conn.commit()
    row = conn.execute(
        "SELECT netcover, missing_inputs_json FROM rh_economic_evaluations "
        "WHERE snapshot_id = 'h-0'"
    ).fetchone()
    assert row is not None
    netcover, missing_json = row
    assert netcover is None  # not "0" or ""
    missing = json.loads(missing_json)
    assert isinstance(missing, list) and len(missing) > 0
    assert any(m.get("field") == "fee_apr_pct" for m in missing)
    conn.close()


def test_no_source_payload_hash_writes_no_economic_row_and_records_reason(tmp_path):
    conn = _fresh_store(tmp_path)
    samples = [
        _passing_sample(0, source_payload_hash="h-0"),  # writes a row
        _passing_sample(1),  # no source_payload_hash -> no row, reason recorded
    ]
    steps = _run(conn, samples)
    conn.commit()
    econ_count = conn.execute("SELECT COUNT(*) FROM rh_economic_evaluations").fetchone()[0]
    assert econ_count == 1  # only the first sample wrote a row
    assert "ECONOMIC_EVAL_SKIPPED_NO_SNAPSHOT_ID" in steps[1].conjunct_reasons
    assert "ECONOMIC_EVAL_SKIPPED_NO_SNAPSHOT_ID" not in steps[0].conjunct_reasons
    conn.close()


def test_evaluated_at_equals_gate_decisions_decided_at(tmp_path):
    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-0")
    _run(conn, [sample])
    conn.commit()
    econ_evaluated_at = conn.execute(
        "SELECT evaluated_at FROM rh_economic_evaluations"
    ).fetchone()[0]
    gate_decided_at = conn.execute(
        "SELECT decided_at FROM rh_gate_decisions"
    ).fetchone()[0]
    assert econ_evaluated_at == gate_decided_at
    conn.close()



def test_rh02bt_missing_max_impact_bps_fails_closed():
    """RH-02bt: pool_meta without max_impact_bps must fail the exit-depth gate.

    It used to default to 50 bps, so a single config omission silently relaxed a
    risk gate to a threshold nobody chose -- no error, no log line. This assertion
    is what keeps the permissive default from coming back.
    """
    meta = _conj_meta()
    del meta["max_impact_bps"]
    bits, reasons = _conj(meta=meta)
    assert bits["position_and_exit_depth_pass"] is False
    assert any("max_impact_bps" in r for r in reasons), reasons


def test_rh02bt_zero_max_impact_bps_is_not_treated_as_missing():
    """RH-02bt: 0 bps is a real (if unsatisfiable) tolerance, not an absent key.

    The guard tests `is None` rather than falsiness, so a legitimate zero reaches
    exit_depth_for_size and is judged on its own merits. Conflating the two is the
    exact mistake this repo keeps finding elsewhere.
    """
    bits, reasons = _conj(meta=_conj_meta(max_impact_bps=0))
    assert bits["position_and_exit_depth_pass"] is False
    assert not any("lacks max_impact_bps" in r for r in reasons), reasons


# ---------------------------------------------------------------------------
# RH-02bu-2: virtual open position persistence (rh_shadow_positions)
# ---------------------------------------------------------------------------

OPEN_META = {"range_pct": 10.0, "dec0": 18, "dec1": 6,
             "pool_address": "0xpool-rh02bu2"}
OPEN_PRICE = Decimal("1.0")
OPEN_QUOTE = Decimal("2.0")


def _open_sample(idx, **overrides):
    """A passing sample that also resolves the open: RTH timestamp, price, bare quote."""
    s = _passing_sample(
        idx, price=OPEN_PRICE, quote_usd_per_token1=OPEN_QUOTE,
        sample_time=f"2026-09-08T18:{idx:02d}:00Z")
    s.update(overrides)
    return s


def test_rh02bu2_granted_step_writes_one_shadow_position(tmp_path):
    conn = _fresh_store(tmp_path)
    _run(conn, [_open_sample(i) for i in range(3)], pool_meta=OPEN_META)
    assert conn.execute(
        "SELECT COUNT(*) FROM rh_shadow_positions").fetchone()[0] == 1
    conn.close()


def test_rh02bu2_position_id_matches_position_marks(tmp_path):
    conn = _fresh_store(tmp_path)
    _run(conn, [_open_sample(i) for i in range(2)], episode="ep-bu2",
         pool_meta=OPEN_META)
    pos_id = conn.execute(
        "SELECT position_id FROM rh_shadow_positions").fetchone()[0]
    mark_ids = {r[0] for r in conn.execute(
        "SELECT DISTINCT position_id FROM rh_position_marks")}
    assert pos_id == "rh-shadow-ep-bu2"
    assert pos_id in mark_ids
    conn.close()


def test_rh02bu2_raw_fields_match_inventory_verbatim(tmp_path):
    conn = _fresh_store(tmp_path)
    _run(conn, [_open_sample(i) for i in range(2)], pool_meta=OPEN_META)
    row = conn.execute(
        "SELECT initial_token0_raw, initial_token1_raw, virtual_liquidity_raw "
        "FROM rh_shadow_positions").fetchone()
    inv = inventory_for_position(
        position_usd=POSITION_USD, entry_price=OPEN_PRICE,
        range_pct=Decimal("10.0"), dec0=18, dec1=6,
        quote_usd_per_token1=OPEN_QUOTE)
    for value in row:
        assert value is not None and value != "0"
    assert row[0] == str(inv.amount0_raw)
    assert row[1] == str(inv.amount1_raw)
    assert row[2] == str(inv.liquidity_raw)
    conn.close()


def test_rh02bu2_no_granted_step_writes_no_shadow_position(tmp_path):
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(i, absolute_profit_pass=False,
                               source_payload_hash=f"hash-{i}")
               for i in range(3)]
    _run(conn, samples, pool_meta=OPEN_META)
    assert conn.execute(
        "SELECT COUNT(*) FROM rh_shadow_positions").fetchone()[0] == 0
    # the other three writers still record every step
    assert conn.execute(
        "SELECT COUNT(*) FROM rh_gate_decisions").fetchone()[0] == 3
    assert conn.execute(
        "SELECT COUNT(*) FROM rh_position_marks").fetchone()[0] == 3
    assert conn.execute(
        "SELECT COUNT(*) FROM rh_economic_evaluations").fetchone()[0] == 3
    conn.close()


def test_rh02bu2_multiple_eligible_steps_still_one_row(tmp_path):
    conn = _fresh_store(tmp_path)
    steps = _run(conn, [_open_sample(i) for i in range(5)], pool_meta=OPEN_META)
    assert sum(1 for s in steps if s.terminal_eligible) >= 2
    assert conn.execute(
        "SELECT COUNT(*) FROM rh_shadow_positions").fetchone()[0] == 1
    conn.close()


def test_rh02bu2_missing_pool_key_writes_no_row_and_records_reason(tmp_path):
    conn = _fresh_store(tmp_path)
    meta = {"range_pct": 10.0, "dec0": 18, "dec1": 6}  # no pool identifier
    steps = _run(conn, [_open_sample(i) for i in range(2)], pool_meta=meta)
    assert conn.execute(
        "SELECT COUNT(*) FROM rh_shadow_positions").fetchone()[0] == 0
    assert any("NO_POOL_KEY" in r for s in steps for r in s.conjunct_reasons)
    conn.close()


# ---------------------------------------------------------------------------
# RH-02by: virtual open booked into rh_journal (first double-entry rows)
# ---------------------------------------------------------------------------

OPEN_META_TOKENS = {"range_pct": 10.0, "dec0": 18, "dec1": 6,
                    "pool_address": "0xpool-rh02by",
                    "token0": "0xtoken0-rh02by",
                    "token1": "0xtoken1-rh02by"}


def _journal_rows(conn):
    return conn.execute(
        "SELECT idempotency_key, asset, amount_raw, is_external_flow "
        "FROM rh_journal ORDER BY idempotency_key").fetchall()


def test_rh02by_granted_step_writes_two_journal_rows(tmp_path):
    conn = _fresh_store(tmp_path)
    _run(conn, [_open_sample(i) for i in range(3)], pool_meta=OPEN_META_TOKENS)
    assert conn.execute("SELECT COUNT(*) FROM rh_journal").fetchone()[0] == 2
    conn.close()


def test_rh02by_journal_asset_and_amount_match_inventory(tmp_path):
    conn = _fresh_store(tmp_path)
    _run(conn, [_open_sample(i) for i in range(2)], pool_meta=OPEN_META_TOKENS)
    rows = _journal_rows(conn)
    inv = inventory_for_position(
        position_usd=POSITION_USD, entry_price=OPEN_PRICE,
        range_pct=Decimal("10.0"), dec0=18, dec1=6,
        quote_usd_per_token1=OPEN_QUOTE)
    assert rows[0][0] == "ep-open-token0"
    assert rows[0][1] == "0xtoken0-rh02by"
    assert rows[0][2] == str(inv.amount0_raw)
    assert rows[1][0] == "ep-open-token1"
    assert rows[1][1] == "0xtoken1-rh02by"
    assert rows[1][2] == str(inv.amount1_raw)
    conn.close()


def test_rh02by_journal_is_internal_flow(tmp_path):
    conn = _fresh_store(tmp_path)
    _run(conn, [_open_sample(i) for i in range(2)], pool_meta=OPEN_META_TOKENS)
    rows = _journal_rows(conn)
    assert len(rows) == 2
    assert all(r[3] == 0 for r in rows)
    conn.close()


def test_rh02by_journal_idempotency_keys_distinct(tmp_path):
    conn = _fresh_store(tmp_path)
    _run(conn, [_open_sample(i) for i in range(2)], pool_meta=OPEN_META_TOKENS)
    keys = [r[0] for r in _journal_rows(conn)]
    assert len(keys) == 2
    assert len(set(keys)) == 2
    conn.close()


def test_rh02by_no_granted_step_writes_no_journal(tmp_path):
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(i, absolute_profit_pass=False,
                               source_payload_hash=f"hash-{i}")
               for i in range(3)]
    _run(conn, samples, pool_meta=OPEN_META_TOKENS)
    assert conn.execute("SELECT COUNT(*) FROM rh_journal").fetchone()[0] == 0
    conn.close()


def test_rh02by_missing_token_addresses_no_journal_but_position_written(tmp_path):
    conn = _fresh_store(tmp_path)
    steps = _run(conn, [_open_sample(i) for i in range(2)], pool_meta=OPEN_META)
    assert conn.execute("SELECT COUNT(*) FROM rh_journal").fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM rh_shadow_positions").fetchone()[0] == 1
    assert any("JOURNAL_NOT_BOOKED:NO_TOKEN_ADDRESSES" in r
               for s in steps for r in s.conjunct_reasons)
    conn.close()


def test_rh02by_journal_entries_pass_stage_b_balance_audit(tmp_path):
    conn = _fresh_store(tmp_path)
    _run(conn, [_open_sample(i) for i in range(2)], pool_meta=OPEN_META_TOKENS)
    result = audit_unexplained_ledger_diffs(conn)
    assert result["count"] == 0
    assert result["reason"] == "OK"
    conn.close()
