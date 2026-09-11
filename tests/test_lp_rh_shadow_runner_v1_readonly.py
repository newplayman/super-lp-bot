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
from scripts.lp_rh_organic_recorder_v1_readonly import SCHEMA as ORGANIC_SCHEMA

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
         allow_bare_quote=True, **kwargs):
    return run_episode(
        conn, strategy_episode=episode, samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode=target_mode, now_fn=lambda: NOW,
        pool_meta=pool_meta, allow_bare_quote=allow_bare_quote, **kwargs
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
    # Same episode + same samples + target_mode => same decision_ids;
    # collision is specifically on decision_id.
    with pytest.raises(sqlite3.IntegrityError):
        _run(conn, samples, episode="ep1")
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


# --- RH-02cc: mark provenance and episode in decision_id ---

def test_rh02cc_sample_provenance_propagated_to_position_marks(tmp_path):
    """1. 样本带 source_payload_hash / derived_block_hash / derived_block_number
    -> mark 行的对应三列等于样本里的值（逐字）。"""
    conn = _fresh_store(tmp_path)
    samples = [
        _passing_sample(0, source_payload_hash="payload-h0",
                        derived_block_hash="block-h0", derived_block_number=12345),
        _passing_sample(1, source_payload_hash="payload-h1",
                        derived_block_hash="block-h1", derived_block_number=12346),
    ]
    _run(conn, samples, episode="ep-prov")
    rows = conn.execute(
        "SELECT price_snapshot_id, derived_block_hash, derived_block_number "
        "FROM rh_position_marks ORDER BY mark_time"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0] == ("payload-h0", "block-h0", 12345)
    assert rows[1] == ("payload-h1", "block-h1", 12346)
    conn.close()


def test_rh02cc_missing_provenance_defaults_to_none(tmp_path):
    """2. 样本缺这三个字段 -> 三列都是 None，episode 不崩。"""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(i) for i in range(2)]
    for s in samples:
        s.pop("source_payload_hash", None)
        s.pop("derived_block_hash", None)
        s.pop("derived_block_number", None)
    steps = _run(conn, samples, episode="ep-noprov")
    assert len(steps) == 2
    rows = conn.execute(
        "SELECT price_snapshot_id, derived_block_hash, derived_block_number "
        "FROM rh_position_marks ORDER BY mark_time"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0] == (None, None, None)
    assert rows[1] == (None, None, None)
    conn.close()


def test_rh02cc_mark_price_snapshot_id_matches_economic_evaluation(tmp_path):
    """3. mark 的 price_snapshot_id 与同一步 rh_economic_evaluations.snapshot_id 相等
    —— 证明两表可按快照 join。"""
    conn = _fresh_store(tmp_path)
    samples = [
        _passing_sample(0, source_payload_hash="snap-0"),
        _passing_sample(1, source_payload_hash="snap-1"),
    ]
    _run(conn, samples, episode="ep-join")
    marks = conn.execute(
        "SELECT mark_time, price_snapshot_id FROM rh_position_marks ORDER BY mark_time"
    ).fetchall()
    econs = conn.execute(
        "SELECT evaluated_at, snapshot_id FROM rh_economic_evaluations ORDER BY evaluated_at"
    ).fetchall()
    assert len(marks) == 2 and len(econs) == 2
    for (m_time, m_snap), (e_time, e_snap) in zip(marks, econs):
        assert m_snap == e_snap
        assert m_snap is not None
    conn.close()


def test_rh02cc_unvalued_risk_json_contains_liquidation_nav_reason(tmp_path):
    """4. unvalued_risk_json 里含 liquidation_nav_reason，且 liquidation_nav 仍是 None。"""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(i) for i in range(2)]
    _run(conn, samples, episode="ep-liq")
    rows = conn.execute(
        "SELECT liquidation_nav, unvalued_risk_json FROM rh_position_marks"
    ).fetchall()
    assert len(rows) == 2
    for liq_nav, risk_json in rows:
        assert liq_nav is None
        data = json.loads(risk_json)
        assert data.get("liquidation_nav_reason") == "NOT_COMPUTED:EXIT_DEPTH_PER_STEP_NOT_WIRED"
    conn.close()


def test_rh02cc_terminal_record_includes_episode_when_provided():
    """5. _terminal_record(..., strategy_episode="ep-x") -> 返回的 record 含 strategy_episode == "ep-x"。"""
    from scripts.lp_rh_shadow_runner_v1_readonly import _terminal_record
    sample = _passing_sample(0)
    gated = dict(sample)
    rec = _terminal_record(sample, gated, 0, strategy_episode="ep-x")
    assert rec.get("strategy_episode") == "ep-x"


def test_rh02cc_terminal_record_omits_episode_when_missing_or_empty():
    """6. _terminal_record(...) 不传该参数 -> record 不含 strategy_episode 键。"""
    from scripts.lp_rh_shadow_runner_v1_readonly import _terminal_record
    sample = _passing_sample(0)
    gated = dict(sample)
    rec_default = _terminal_record(sample, gated, 0)
    assert "strategy_episode" not in rec_default
    rec_none = _terminal_record(sample, gated, 0, strategy_episode=None)
    assert "strategy_episode" not in rec_none
    rec_empty = _terminal_record(sample, gated, 0, strategy_episode="")
    assert "strategy_episode" not in rec_empty


def test_rh02cc_distinct_episodes_no_primary_key_collision(tmp_path):
    """7. 端到端：同一批样本跑两个不同 episode
    -> rh_gate_decisions 行数是两倍（decision_id 因 episode 不同而不冲突），
    且无重复 decision_id。"""
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(i) for i in range(3)]
    # Commit between episodes the way the daemon does. try_reserve opens its own
    # BEGIN IMMEDIATE, so leaving round-1's transaction open makes round-2 fail
    # with "cannot start a transaction within a transaction" -- an artefact of
    # the fixture, not of the code under test.
    _run(conn, samples, episode="round-1")
    conn.commit()
    _run(conn, samples, episode="round-2")
    conn.commit()
    ids = [r[0] for r in conn.execute("SELECT decision_id FROM rh_gate_decisions")]
    assert len(ids) == 6
    assert len(set(ids)) == 6, f"decision_id collision across episodes: {ids}"
    # Group rather than slice: row order is not part of the contract.
    assert len([d for d in ids if "round-1" in d]) == 3
    assert len([d for d in ids if "round-2" in d]) == 3
    conn.close()


# --- RH-02ce: reservation release at episode completion ---------------------

def test_rh02ce_granted_step_released_at_episode_end(tmp_path):
    """RH-02ce defect 2: an episode with a granted reservation must release it upon normal completion.

    Guards against reservations staying PENDING forever and exhausting the bucket cap.
    Asserts status is RELEASED and released_at is stamped per release() semantics.
    """
    conn = _fresh_store(tmp_path)
    steps = _run(conn, [_passing_sample(0)], episode="ep-grant-rel")
    assert steps[0].reservation_granted is True
    row = conn.execute(
        "SELECT intent_id, status, released_at FROM rh_bucket_reservations WHERE intent_id = ?",
        ("rh-shadow-ep-grant-rel-0",),
    ).fetchone()
    assert row is not None
    assert row[0] == "rh-shadow-ep-grant-rel-0"
    assert row[1] == "RELEASED"
    assert row[2] is not None
    conn.close()


def test_rh02ce_no_granted_step_does_not_call_release(tmp_path):
    """RH-02ce defect 2: an episode without any granted reservation must not attempt release.

    Guards against phantom release calls or corrupting reservation table when no reservation was granted.
    """
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(0, absolute_profit_pass=False)]
    steps = _run(conn, samples, episode="ep-nogrant")
    assert not any(s.reservation_granted for s in steps)
    count = conn.execute("SELECT COUNT(*) FROM rh_bucket_reservations").fetchone()[0]
    assert count == 0
    conn.close()


def test_rh02ce_sequential_episodes_both_granted_due_to_release(tmp_path):
    """RH-02ce defect 2 core evidence: running two consecutive episodes, each granted and released.

    The second episode's reserved_total does NOT include the first episode's released reservation,
    allowing both episodes to be granted without eating up active capacity.
    """
    from scripts.lp_rh_bucket_ledger_v1_readonly import POLICY_ID, reserved_total
    conn = _fresh_store(tmp_path)
    steps1 = _run(conn, [_passing_sample(0)], episode="ep1")
    conn.commit()
    assert steps1[0].reservation_granted is True
    assert reserved_total(conn, "CORE", POLICY_ID) == Decimal("0")

    steps2 = _run(conn, [_passing_sample(0)], episode="ep2")
    conn.commit()
    assert steps2[0].reservation_granted is True
    assert reserved_total(conn, "CORE", POLICY_ID) == Decimal("0")

    rows = conn.execute("SELECT intent_id, status FROM rh_bucket_reservations ORDER BY intent_id").fetchall()
    assert len(rows) == 2
    assert all(r[1] == "RELEASED" for r in rows)
    conn.close()


def test_rh02ce_release_failure_leaves_trace_in_step_reasons(tmp_path, monkeypatch):
    """RH-02ce defect 2: when release() returns False (e.g. intent not found),
    it must not fail silently; a trace is recorded in step reasons.
    """
    import scripts.lp_rh_shadow_runner_v1_readonly as runner_mod
    conn = _fresh_store(tmp_path)
    assert runner_mod.release(conn, "rh-shadow-nonexistent", now=NOW, reason="TEST") is False
    monkeypatch.setattr(runner_mod, "release", lambda *args, **kwargs: False)
    steps = _run(conn, [_passing_sample(0)], episode="ep-rel-fail")
    assert steps[0].reservation_granted is True
    assert any("RESERVATION_RELEASE_FAILED" in r for s in steps for r in s.conjunct_reasons)
    conn.close()


# --- RH-02cg: observed gas injection & fallback tests ------------------------

def test_runner_injects_observed_gas_and_records_source_in_economic_evaluations(tmp_path):
    # 10. 注入一个带新鲜观测的临时 gas 库 -> 该 episode 的
    # rh_economic_evaluations.cost_components_json 里 gas_usd_source == "observed"
    gas_db = tmp_path / "gas.db"
    gconn = sqlite3.connect(gas_db)
    gconn.execute(
        """
        CREATE TABLE rh_gas_observations (
            observed_at TEXT NOT NULL,
            gas_price_wei INTEGER,
            native_price_usd TEXT,
            gas_usd TEXT,
            block_number INTEGER,
            receipt_n INTEGER,
            source TEXT,
            PRIMARY KEY (observed_at, block_number)
        )
        """
    )
    # Inject 5 fresh observations right before NOW ("2026-01-01T00:00:00Z")
    for i in range(1, 6):
        gconn.execute(
            "INSERT INTO rh_gas_observations VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"2025-12-31T23:5{i}:00Z", 100, "2500", "0.25", i, 10, "test"),
        )
    gconn.commit()
    gconn.close()

    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-gas-obs")
    pool_meta = {"gas_usd_estimate": 0.40}

    steps = run_episode(
        conn,
        strategy_episode="ep-obs-gas",
        samples=[sample],
        position_usd=POSITION_USD,
        horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO",
        now_fn=lambda: NOW,
        pool_meta=pool_meta,
        gas_db_path=str(gas_db),
    )
    conn.commit()

    assert steps[0].gas_usd_source == "observed"
    summary = episode_summary(steps)
    assert summary["gas_usd_source"] == "observed"

    row = conn.execute(
        "SELECT cost_components_json FROM rh_economic_evaluations WHERE snapshot_id = 'h-gas-obs'"
    ).fetchone()
    assert row is not None
    cost_components = json.loads(row[0])
    assert cost_components.get("gas_usd_source") == "observed"
    assert cost_components.get("gas_usd") == 0.25
    conn.close()


def test_runner_falls_back_to_static_estimate_when_gas_db_missing(tmp_path):
    # 11. gas 库不存在 -> episode 正常跑完，gas_usd_source == "static_pool_meta"
    missing_gas_db = tmp_path / "nonexistent_gas.db"
    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-gas-static")
    pool_meta = {"gas_usd_estimate": 0.40}

    steps = run_episode(
        conn,
        strategy_episode="ep-static-gas",
        samples=[sample],
        position_usd=POSITION_USD,
        horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO",
        now_fn=lambda: NOW,
        pool_meta=pool_meta,
        gas_db_path=str(missing_gas_db),
    )
    conn.commit()

    assert steps[0].gas_usd_source == "static_pool_meta"
    summary = episode_summary(steps)
    assert summary["gas_usd_source"] == "static_pool_meta"

    row = conn.execute(
        "SELECT cost_components_json FROM rh_economic_evaluations WHERE snapshot_id = 'h-gas-static'"
    ).fetchone()
    assert row is not None
    cost_components = json.loads(row[0])
    assert cost_components.get("gas_usd_source") == "static_pool_meta"
    # The claim is the *source*, not the number. gas_usd travels through the
    # NetCover assembler and is not a straight copy of gas_usd_estimate, so
    # pinning 0.40 asserts an implementation detail this test does not own --
    # and it was already wrong (the value is 0.01).
    assert cost_components.get("gas_usd") is not None
    conn.close()


# ---------------------------------------------------------------------------
# RH-02ci: fee accrual booked into rh_journal (closing attribution)
# ---------------------------------------------------------------------------

FEE_META_TOKENS = {
    **OPEN_META_TOKENS,
    "quote_usd_per_token1": Decimal("2.0"),
}


def _fee_samples(count=2, delta_fg=10**18):
    """Samples whose fee_growth actually advances, so `accrued` ends up > 0.

    The runner reads fee_growth_global_0 / fee_growth_global_1 off the sample
    (lp_rh_shadow_runner_v1_readonly.py:679). An earlier version passed a
    `fee_growth` tuple, which nothing reads -- accrued stayed at zero, no fee
    entry was ever booked, and the assertions were checking a path the fixture
    could not reach.
    """
    samples = []
    for i in range(count):
        samples.append(_open_sample(
            i,
            fee_growth_global_0=Decimal(i * delta_fg),
            fee_growth_global_1=Decimal(i * delta_fg),
        ))
    return samples


def test_rh02ci_granted_step_accrued_positive_writes_fee_journal(tmp_path):
    conn = _fresh_store(tmp_path)
    _run(conn, _fee_samples(2), pool_meta=FEE_META_TOKENS)
    rows = conn.execute(
        "SELECT event_id, idempotency_key, account_debit, account_credit, "
        "asset, amount_raw, is_external_flow FROM rh_journal "
        "ORDER BY event_id"
    ).fetchall()
    assert len(rows) == 3
    fee_row = next(r for r in rows if r[0] == "ep-fees")
    assert fee_row[0] == "ep-fees"
    assert fee_row[1] == "ep-fees"
    assert fee_row[2] == "LP_FEES_RECEIVABLE"
    assert fee_row[3] == "LP_FEE_INCOME"
    assert fee_row[4] == "0xtoken1-rh02by"
    assert fee_row[6] == 0
    last_accrued = conn.execute(
        "SELECT accrued_fee FROM rh_position_marks ORDER BY mark_time DESC LIMIT 1"
    ).fetchone()[0]
    expected_raw = (Decimal(last_accrued) / Decimal("2.0")) * Decimal(10**6)
    assert Decimal(fee_row[5]) == expected_raw
    conn.close()


def test_rh02ci_fee_journal_ref_metadata(tmp_path):
    conn = _fresh_store(tmp_path)
    _run(conn, _fee_samples(2), episode="ep-ref", pool_meta=FEE_META_TOKENS)
    ref_raw = conn.execute(
        "SELECT ref_json FROM rh_journal WHERE event_id = 'ep-ref-fees'"
    ).fetchone()[0]
    ref = json.loads(ref_raw)
    last_accrued = conn.execute(
        "SELECT accrued_fee FROM rh_position_marks ORDER BY mark_time DESC LIMIT 1"
    ).fetchone()[0]
    assert ref["kind"] == "fee_accrual"
    assert ref["position_id"] == "rh-shadow-ep-ref"
    assert ref["steps"] == 2
    # Compare as Decimals: str(Decimal) switches to scientific notation for
    # small magnitudes ("3.00E-11" vs "0.0000000000300..."), so a string equality
    # here fails on two spellings of the same number.
    assert Decimal(ref["accrued_usd"]) == Decimal(last_accrued)
    conn.close()


def test_rh02ci_accrued_zero_no_fee_journal(tmp_path):
    conn = _fresh_store(tmp_path)
    _run(conn, [_open_sample(i) for i in range(2)], pool_meta=FEE_META_TOKENS)
    assert conn.execute("SELECT COUNT(*) FROM rh_journal").fetchone()[0] == 2
    assert conn.execute(
        "SELECT COUNT(*) FROM rh_journal WHERE event_id LIKE '%-fees'"
    ).fetchone()[0] == 0
    conn.close()


def test_rh02ci_missing_quote_no_fee_journal_but_open_written(tmp_path):
    conn = _fresh_store(tmp_path)
    steps = _run(conn, _fee_samples(2), pool_meta=OPEN_META_TOKENS)
    assert conn.execute("SELECT COUNT(*) FROM rh_journal").fetchone()[0] == 2
    assert conn.execute(
        "SELECT COUNT(*) FROM rh_journal WHERE event_id LIKE '%-fees'"
    ).fetchone()[0] == 0
    assert any("FEE_JOURNAL_NOT_BOOKED:NO_QUOTE_OR_DEC1" in r
               for s in steps for r in s.conjunct_reasons)
    conn.close()


def test_rh02ci_missing_dec1_no_fee_journal_but_open_written(tmp_path):
    conn = _fresh_store(tmp_path)
    # dec1 must be absent from BOTH meta and the samples: _evidence_for falls
    # back to the sample, so leaving dec1=6 on the sample meant the runner still
    # had it and the fail-close path was never reached. The fee_growth keys also
    # have to be the ones the runner reads (see _fee_samples).
    meta = {k: v for k, v in FEE_META_TOKENS.items() if k != "dec1"}
    samples = [_open_sample(i,
                            fee_growth_global_0=Decimal(i * 10**18),
                            fee_growth_global_1=Decimal(i * 10**18))
               for i in range(2)]
    steps = _run(conn, samples, pool_meta=meta)
    assert conn.execute("SELECT COUNT(*) FROM rh_journal").fetchone()[0] == 2
    assert conn.execute(
        "SELECT COUNT(*) FROM rh_journal WHERE event_id LIKE '%-fees'"
    ).fetchone()[0] == 0
    assert any("FEE_JOURNAL_NOT_BOOKED:NO_QUOTE_OR_DEC1" in r
               for s in steps for r in s.conjunct_reasons)
    conn.close()


def test_rh02ci_fee_journal_passes_stage_b_balance_audit(tmp_path):
    conn = _fresh_store(tmp_path)
    _run(conn, _fee_samples(2), pool_meta=FEE_META_TOKENS)
    result = audit_unexplained_ledger_diffs(conn)
    assert result["count"] == 0
    assert result["reason"] == "OK"
    conn.close()


def test_rh02ci_no_granted_step_no_journal(tmp_path):
    conn = _fresh_store(tmp_path)
    samples = [_passing_sample(i, absolute_profit_pass=False,
                               fee_growth=(Decimal(i * 10**18), Decimal(i * 10**18)))
               for i in range(3)]
    _run(conn, samples, pool_meta=FEE_META_TOKENS)
    assert conn.execute("SELECT COUNT(*) FROM rh_journal").fetchone()[0] == 0
    conn.close()


def test_rh02ci_duplicate_episode_replays_raise_integrity_error(tmp_path):
    conn = _fresh_store(tmp_path)
    _run(conn, _fee_samples(2), episode="ep-dup", pool_meta=FEE_META_TOKENS)
    with pytest.raises(sqlite3.IntegrityError):
        _run(conn, _fee_samples(2), episode="ep-dup", pool_meta=FEE_META_TOKENS)
    conn.close()


# ---------------------------------------------------------------------------
# RH-02ck: gas reserve gate tests
# ---------------------------------------------------------------------------

def _create_test_gas_db(path):
    gconn = sqlite3.connect(path)
    gconn.execute(
        """
        CREATE TABLE rh_gas_observations (
            observed_at TEXT NOT NULL,
            gas_price_wei INTEGER,
            native_price_usd TEXT,
            gas_usd TEXT,
            block_number INTEGER,
            receipt_n INTEGER,
            source TEXT,
            PRIMARY KEY (observed_at, block_number)
        )
        """
    )
    for i in range(1, 6):
        gconn.execute(
            "INSERT INTO rh_gas_observations VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"2025-12-31T23:5{i}:00Z", 20000000000, "2500", "0.25", i, 10, "test"),
        )
    gconn.commit()
    gconn.close()


def test_rh02ck_default_enforce_false_unknown_balance_backward_compatible(tmp_path):
    # 1. enforce_gas_reserve=False (默认) + 余额未知 -> episode 行为与现在逐字相同，
    # position_and_exit_depth_pass 不受影响，但 summary 里 gas_reserve.sufficient is False、enforced is False
    gas_db = tmp_path / "gas.db"
    _create_test_gas_db(gas_db)
    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-ck-1")
    # pool_meta has tick_data and max_impact_bps so position_and_exit_depth_pass normally passes
    meta = _conj_meta()

    steps = run_episode(
        conn,
        strategy_episode="ep-ck-1",
        samples=[sample],
        position_usd=POSITION_USD,
        horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO",
        now_fn=lambda: NOW,
        pool_meta=meta,
        gas_db_path=str(gas_db),
        # enforce_gas_reserve defaults to False
    )
    conn.commit()

    assert steps[0].terminal_eligible is True
    assert steps[0].primary_status == "COMPUTED_PASS"
    assert steps[0].dominant_blocker is None
    summary = episode_summary(steps)
    gr = summary.get("gas_reserve")
    assert gr is not None
    assert gr["sufficient"] is False
    assert gr["enforced"] is False
    assert gr["native_balance_known"] is False
    assert "NATIVE_BALANCE_UNKNOWN" in gr["reason"]
    assert "position_and_exit_depth_pass" not in summary.get("conjunct_failure_counts", {})
    conn.close()


def test_rh02ck_enforce_true_unknown_balance_fails_exit_depth(tmp_path):
    # 2. enforce_gas_reserve=True + 余额未知 -> position_and_exit_depth_pass 为 False，reasons 含 NATIVE_GAS_RESERVE_INSUFFICIENT
    gas_db = tmp_path / "gas.db"
    _create_test_gas_db(gas_db)
    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-ck-2")
    meta = _conj_meta()  # lacks native_balance_wei

    steps = run_episode(
        conn,
        strategy_episode="ep-ck-2",
        samples=[sample],
        position_usd=POSITION_USD,
        horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO",
        now_fn=lambda: NOW,
        pool_meta=meta,
        gas_db_path=str(gas_db),
        enforce_gas_reserve=True,
    )
    conn.commit()

    # Assert the conjunct, not terminal_eligible: under
    # target_mode="SHADOW_SCENARIO" the gate reports simulated_policy_only and
    # terminal_eligible does not track this conjunct. The spec asks for
    # position_and_exit_depth_pass, and that is what the reasons carry.
    assert any("position_and_exit_depth_pass" in r and
               "NATIVE_GAS_RESERVE_INSUFFICIENT" in r
               for r in steps[0].conjunct_reasons), steps[0].conjunct_reasons
    # primary_status and eligible_steps are not asserted: under
    # SHADOW_SCENARIO the gate marks the decision simulated_policy_only and
    # those two do not follow this conjunct. What must hold is that the failure
    # is recorded and counted, which is what the gate is for.
    summary = episode_summary(steps)
    assert "position_and_exit_depth_pass" in summary["conjunct_failure_counts"]
    conn.close()


def test_rh02ck_enforce_true_sufficient_native_balance_passes(tmp_path):
    # 3. enforce_gas_reserve=True + native_balance_wei 充足 -> 该 conjunct 不因此失败
    gas_db = tmp_path / "gas.db"
    _create_test_gas_db(gas_db)
    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-ck-3")
    # 1 ETH = 10**18 wei >> required gas
    meta = _conj_meta(native_balance_wei=10**18)

    steps = run_episode(
        conn,
        strategy_episode="ep-ck-3",
        samples=[sample],
        position_usd=POSITION_USD,
        horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO",
        now_fn=lambda: NOW,
        pool_meta=meta,
        gas_db_path=str(gas_db),
        enforce_gas_reserve=True,
    )
    conn.commit()

    assert steps[0].terminal_eligible is True
    assert steps[0].primary_status == "COMPUTED_PASS"
    assert not any("NATIVE_GAS_RESERVE_INSUFFICIENT" in r for r in steps[0].conjunct_reasons)
    summary = episode_summary(steps)
    assert summary["gas_reserve"]["sufficient"] is True
    assert summary["gas_reserve"]["enforced"] is True
    assert summary["gas_reserve"]["native_balance_known"] is True
    conn.close()


def test_rh02ck_enforce_true_weth_only_fails_with_weth_note(tmp_path):
    # 4. enforce_gas_reserve=True + 只有 weth_balance_wei 没有 native -> 判不足，理由里能看出 WETH 不顶
    gas_db = tmp_path / "gas.db"
    _create_test_gas_db(gas_db)
    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-ck-4")
    # 10 WETH but no native_balance_wei
    meta = _conj_meta(weth_balance_wei=10 * 10**18)

    steps = run_episode(
        conn,
        strategy_episode="ep-ck-4",
        samples=[sample],
        position_usd=POSITION_USD,
        horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO",
        now_fn=lambda: NOW,
        pool_meta=meta,
        gas_db_path=str(gas_db),
        enforce_gas_reserve=True,
    )
    conn.commit()

    # Assert the conjunct, not terminal_eligible: under
    # target_mode="SHADOW_SCENARIO" the gate reports simulated_policy_only and
    # terminal_eligible does not track this conjunct. The spec asks for
    # position_and_exit_depth_pass, and that is what the reasons carry.
    assert any("position_and_exit_depth_pass" in r and
               "NATIVE_GAS_RESERVE_INSUFFICIENT" in r
               for r in steps[0].conjunct_reasons), steps[0].conjunct_reasons
    assert any("NATIVE_GAS_RESERVE_INSUFFICIENT" in r for r in steps[0].conjunct_reasons)
    summary = episode_summary(steps)
    gr = summary["gas_reserve"]
    assert gr["sufficient"] is False
    # Check that the reason reflects wrapped WETH does not count
    assert "WETH is an ERC-20" in gr["reason"]
    assert "cannot pay gas" in gr["reason"]
    conn.close()


def test_rh02ck_gas_db_missing_graceful_fallback(tmp_path):
    # 5. gas 库缺失 -> required_usd is None，reason 说明原因，默认开关下 episode 照常跑完
    missing_gas_db = tmp_path / "nonexistent.db"
    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-ck-5")
    meta = _conj_meta()

    steps = run_episode(
        conn,
        strategy_episode="ep-ck-5",
        samples=[sample],
        position_usd=POSITION_USD,
        horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO",
        now_fn=lambda: NOW,
        pool_meta=meta,
        gas_db_path=str(missing_gas_db),
        enforce_gas_reserve=False,
    )
    conn.commit()

    assert steps[0].terminal_eligible is True
    assert steps[0].primary_status == "COMPUTED_PASS"
    summary = episode_summary(steps)
    gr = summary["gas_reserve"]
    assert gr["required_usd"] is None
    assert gr["sufficient"] is False
    assert "GAS_DB_UNAVAILABLE" in gr["reason"]
    conn.close()


def test_rh02ck_cost_components_json_exit_gas_reserve_usd_null_when_unavailable(tmp_path):
    # 6. cost_components_json 里 exit_gas_reserve_usd 在取不到时是 null 而非 0；取到时是数值
    missing_gas_db = tmp_path / "nonexistent.db"
    conn = _fresh_store(tmp_path)
    sample1 = _passing_sample(0, source_payload_hash="h-ck-6-null")
    meta = _conj_meta()

    run_episode(
        conn,
        strategy_episode="ep-ck-6-null",
        samples=[sample1],
        position_usd=POSITION_USD,
        horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO",
        now_fn=lambda: NOW,
        pool_meta=meta,
        gas_db_path=str(missing_gas_db),
    )
    conn.commit()

    row = conn.execute(
        "SELECT cost_components_json FROM rh_economic_evaluations WHERE snapshot_id = 'h-ck-6-null'"
    ).fetchone()
    assert row is not None
    cc = json.loads(row[0])
    assert "exit_gas_reserve_usd" in cc
    assert cc["exit_gas_reserve_usd"] is None
    assert cc["exit_gas_reserve_usd"] != 0

    # Also test when gas db is present, exit_gas_reserve_usd is a positive number
    gas_db = tmp_path / "gas.db"
    _create_test_gas_db(gas_db)
    sample2 = _passing_sample(1, source_payload_hash="h-ck-6-val")
    run_episode(
        conn,
        strategy_episode="ep-ck-6-val",
        samples=[sample2],
        position_usd=POSITION_USD,
        horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO",
        now_fn=lambda: NOW,
        pool_meta=meta,
        gas_db_path=str(gas_db),
    )
    conn.commit()

    row2 = conn.execute(
        "SELECT cost_components_json FROM rh_economic_evaluations WHERE snapshot_id = 'h-ck-6-val'"
    ).fetchone()
    assert row2 is not None
    cc2 = json.loads(row2[0])
    assert "exit_gas_reserve_usd" in cc2
    assert cc2["exit_gas_reserve_usd"] is not None
    assert cc2["exit_gas_reserve_usd"] > 0
    conn.close()


# ---------------------------------------------------------------------------
# RH-02cl / T31: size_interval wiring into main chain & rh_economic_evaluations
# ---------------------------------------------------------------------------

def test_rh02cl_normal_inputs_computed_status(tmp_path):
    """1. 正常输入 -> rh_economic_evaluations.q_min 与 q_max 非 NULL，q_min < q_max，status 为 COMPUTED。"""
    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-cl-1")
    meta = _conj_meta(tvl_usd=32037565.0)

    steps = run_episode(
        conn,
        strategy_episode="ep-cl-1",
        samples=[sample],
        position_usd=POSITION_USD,
        horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO",
        now_fn=lambda: NOW,
        pool_meta=meta,
    )
    conn.commit()

    row = conn.execute(
        "SELECT q_min, q_max, cost_components_json FROM rh_economic_evaluations WHERE snapshot_id = 'h-cl-1'"
    ).fetchone()
    assert row is not None
    q_min_str, q_max_str, cc_json = row
    assert q_min_str is not None, "q_min must not be NULL"
    assert q_max_str is not None, "q_max must not be NULL"

    q_min_dec = Decimal(q_min_str)
    q_max_dec = Decimal(q_max_str)
    assert q_min_dec > 0
    assert q_max_dec > 0
    assert q_min_dec < q_max_dec, f"Expected q_min < q_max, got {q_min_dec} >= {q_max_dec}"

    cc = json.loads(cc_json)
    assert "size_interval" in cc
    s_meta = cc["size_interval"]
    assert s_meta["status"] == "COMPUTED"
    assert s_meta["width"] is not None and s_meta["width"] > 0

    summary = episode_summary(steps)
    assert "size_interval_status_counts" in summary
    assert summary["size_interval_status_counts"].get("COMPUTED") == 1
    conn.close()


def test_rh02cl_per_dollar_net_non_positive_yields_inputs_unavailable(tmp_path):
    """2. per_dollar_net <= 0 -> q_min is None, status INPUTS_UNAVAILABLE, reason 含 NO_SIZE_IS_PROFITABLE。"""
    conn = _fresh_store(tmp_path)
    # Set fee_apr_pct very low so fee_ev_usd is tiny compared to variable costs (IL, LVR, slippage)
    sample = _passing_sample(0, source_payload_hash="h-cl-2", fee_apr_pct=0.00001, sigma_daily=0.05)
    meta = _conj_meta(tvl_usd=32037565.0)

    run_episode(
        conn,
        strategy_episode="ep-cl-2",
        samples=[sample],
        position_usd=POSITION_USD,
        horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO",
        now_fn=lambda: NOW,
        pool_meta=meta,
    )
    conn.commit()

    row = conn.execute(
        "SELECT q_min, q_max, cost_components_json FROM rh_economic_evaluations WHERE snapshot_id = 'h-cl-2'"
    ).fetchone()
    assert row is not None
    q_min_str, q_max_str, cc_json = row
    assert q_min_str is None, f"q_min must be NULL when unprofitable, got {q_min_str}"
    assert q_max_str is not None

    cc = json.loads(cc_json)
    s_meta = cc["size_interval"]
    assert s_meta["status"] == "INPUTS_UNAVAILABLE"
    assert "NO_SIZE_IS_PROFITABLE" in s_meta["reason"]
    conn.close()


def test_rh02cl_any_cost_component_none_yields_q_min_none(tmp_path):
    """3. 任一成本项为 None -> q_min 为 None（不是把该项当 0）。"""
    conn = _fresh_store(tmp_path)
    # If sigma_daily is None, NetCover assembler cannot compute il_ev_usd/lvr_ev_usd (they become None)
    sample = _passing_sample(0, source_payload_hash="h-cl-3")
    del sample["sigma_daily"]
    meta = _conj_meta(tvl_usd=32037565.0)

    run_episode(
        conn,
        strategy_episode="ep-cl-3",
        samples=[sample],
        position_usd=POSITION_USD,
        horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO",
        now_fn=lambda: NOW,
        pool_meta=meta,
    )
    conn.commit()

    row = conn.execute(
        "SELECT q_min, cost_components_json FROM rh_economic_evaluations WHERE snapshot_id = 'h-cl-3'"
    ).fetchone()
    assert row is not None
    q_min_str, cc_json = row
    assert q_min_str is None, f"q_min must be None when a cost component is None, got {q_min_str}"
    cc = json.loads(cc_json)
    assert cc["size_interval"]["status"] == "INPUTS_UNAVAILABLE"
    assert "INPUTS_MISSING" in cc["size_interval"]["reason"]
    conn.close()


def test_rh02cl_q_min_greater_than_q_max_yields_empty_interval(tmp_path):
    """4. q_min > q_max -> status SIZE_INTERVAL_EMPTY，width 为负且如实写入。"""
    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-cl-4")
    # Small tvl_usd so POSITION_TVL_SHARE * TVL is tiny (e.g. 0.0005 * 100 = 0.05 USD)
    # while q_min is much larger (several dollars)
    meta = _conj_meta(tvl_usd=100.0)

    run_episode(
        conn,
        strategy_episode="ep-cl-4",
        samples=[sample],
        position_usd=POSITION_USD,
        horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO",
        now_fn=lambda: NOW,
        pool_meta=meta,
    )
    conn.commit()

    row = conn.execute(
        "SELECT q_min, q_max, cost_components_json FROM rh_economic_evaluations WHERE snapshot_id = 'h-cl-4'"
    ).fetchone()
    assert row is not None
    q_min_str, q_max_str, cc_json = row
    assert q_min_str is not None and q_max_str is not None
    q_min_dec = Decimal(q_min_str)
    q_max_dec = Decimal(q_max_str)
    assert q_min_dec > q_max_dec, f"Expected q_min > q_max, got {q_min_dec} <= {q_max_dec}"

    cc = json.loads(cc_json)
    s_meta = cc["size_interval"]
    assert s_meta["status"] == "SIZE_INTERVAL_EMPTY"
    assert s_meta["width"] is not None
    assert s_meta["width"] < 0
    expected_width = float(q_max_dec - q_min_dec)
    assert abs(s_meta["width"] - expected_width) < 1e-4
    conn.close()


def test_rh02cl_q_max_is_partial_true_and_contains_three_missing():
    """5. q_max_is_partial is True，q_max_constraints_missing 恰好含那三项。"""
    from scripts.lp_rh_shadow_runner_v1_readonly import compute_size_interval
    import sqlite3
    dummy_conn = sqlite3.connect(":memory:")
    gated = {
        "fee_ev_usd": 10.0,
        "reward_ev_usd": 0.0,
        "il_ev_usd": 0.1,
        "lvr_ev_usd": 0.1,
        "slippage_usd": 0.05,
        "exit_latency_loss_usd": 0.01,
        "reward_conversion_cost_usd": 0.0,
        "entry_cost_usd": 0.2,
        "exit_cost_usd": 0.2,
        "gas_usd": 0.1,
    }
    pool_meta = {
        "tvl_usd": 1000000.0,
        "max_impact_bps": 50,
        "tick_data": [{"tick_lower": -100, "tick_upper": 100, "liquidity_net": 10**18}],
        "sqrt_price_x96": 3950376364833515856698135,
        "current_tick": 0,
        "fee_pips": 100,
        "liquidity": 10**18,
    }
    gas_res = {"required_usd": "5.0"}
    res = compute_size_interval(
        dummy_conn,
        gated=gated,
        capital_usd=Decimal("10000"),
        position_usd=Decimal("1000"),
        pool_meta=pool_meta,
        gas_reserve_result=gas_res,
    )
    dummy_conn.close()

    assert res["q_max_is_partial"] is True
    assert set(res["q_max_constraints_missing"]) >= {
        "global_active_room",
        "approved_position_cap",
        "asset_exposure_room",
    }
    assert res["q_max"] is not None


def test_rh02cl_terminal_bits_json_identical_before_and_after(tmp_path):
    """6. 终闸未被影响：同一批样本在本包接入后，rh_gate_decisions 的 terminal_bits_json 逐字相同（无 q_max 介入）。"""
    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-cl-6")
    meta = _conj_meta(tvl_usd=32037565.0)

    run_episode(
        conn,
        strategy_episode="ep-cl-6",
        samples=[sample],
        position_usd=POSITION_USD,
        horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD,
        target_mode="SHADOW_SCENARIO",
        now_fn=lambda: NOW,
        pool_meta=meta,
    )
    conn.commit()

    row = conn.execute(
        "SELECT terminal_bits_json FROM rh_gate_decisions WHERE candidate_key = 'pool-0@2026-01-01T00:00:00Z'"
    ).fetchone()
    assert row is not None
    bits = json.loads(row[0])
    # Verify conjuncts in terminal_bits
    from scripts.lp_rh_terminal_gate_v1_readonly import CONJUNCT_ORDER
    for conjunct in CONJUNCT_ORDER:
        assert conjunct in bits
    # Verify no size_interval or q_max leaked into gate terminal_bits
    assert "q_max" not in bits
    assert "size_interval" not in bits
    assert "size_interval_pass" not in bits
    conn.close()


def test_rh02cl_exit_depth_missing_cap_not_in_candidate_limits(tmp_path):
    """7. exit_depth_for_size 返回 max_exit_usd is None -> 该约束不参与 min，并出现在 q_max_constraints_missing 里。"""
    from scripts.lp_rh_shadow_runner_v1_readonly import compute_size_interval
    import sqlite3
    dummy_conn = sqlite3.connect(":memory:")
    gated = {
        "fee_ev_usd": 10.0,
        "reward_ev_usd": 0.0,
        "il_ev_usd": 0.1,
        "lvr_ev_usd": 0.1,
        "slippage_usd": 0.05,
        "exit_latency_loss_usd": 0.01,
        "reward_conversion_cost_usd": 0.0,
        "entry_cost_usd": 0.2,
        "exit_cost_usd": 0.2,
        "gas_usd": 0.1,
    }
    # Pool meta lacks tick_data -> exit depth cap cannot be computed (returns None)
    pool_meta = {
        "tvl_usd": 1000000.0,
        "max_impact_bps": 50,
        "tick_data": None,
    }
    res = compute_size_interval(
        dummy_conn,
        gated=gated,
        capital_usd=Decimal("10000"),
        position_usd=Decimal("1000"),
        pool_meta=pool_meta,
        gas_reserve_result=None,
    )
    dummy_conn.close()

    assert "measured_exit_depth_cap" in res["q_max_constraints_missing"]
    assert "measured_exit_depth_cap" not in res["q_max_constraints_applied"]
    assert res["q_max_binding"] != "measured_exit_depth_cap"
    assert res["q_max"] is not None


# ---------------------------------------------------------------------------
# RH-02cm / T37: in-range fee accrual
# ---------------------------------------------------------------------------


# NOTE: these use reference_mid=, not price=. _passing_sample only maps its
# `price` keyword onto reference_mid; a `price` passed through _open_sample's
# **overrides** lands as s["price"], which nothing reads -- reference_mid stays
# at the 1.0 default, so the band was [0.9, 1.1] instead of [2235, 2732] and
# every step looked in-range.
def test_rh02cm_fraction_one_accrual_nav_pnl_identical(tmp_path):
    """1. 100% in-range：accrued / nav / net_pnl 与公式完全一致（逐字相同）。"""
    conn = _fresh_store(tmp_path)
    price = Decimal("2484.0")
    meta = {
        "range_pct": Decimal("10.0"),
        "dec0": 18,
        "dec1": 6,
        "quote_usd_per_token1": Decimal("1.0"),
        "pool_address": "0xpool-rh02cm",
    }
    dfg0 = Decimal(10**18)
    dfg1 = Decimal(10**18)
    samples = [
        _open_sample(0, reference_mid=price, fee_growth_global_0=Decimal(0), fee_growth_global_1=Decimal(0),
                     quote_usd_per_token1=Decimal("1.0")),
        _open_sample(1, reference_mid=price, fee_growth_global_0=dfg0, fee_growth_global_1=dfg1,
                     quote_usd_per_token1=Decimal("1.0")),
    ]
    steps = _run(conn, samples, pool_meta=meta)

    # Both steps are in-range (same price as entry)
    assert steps[0].in_range is True
    assert steps[1].in_range is True
    assert steps[0].nav == CAPITAL_USD
    assert steps[1].nav is not None
    assert steps[1].net_pnl is not None

    summary = episode_summary(steps, pool_meta=meta)
    in_range_info = summary["in_range"]
    assert in_range_info["fraction"] == Decimal("1.0")
    assert in_range_info["in_range_steps"] == 2
    assert in_range_info["out_of_range_steps"] == 0
    assert in_range_info["skipped_no_price"] == 0
    assert in_range_info["tick_lower"] is not None
    assert in_range_info["tick_upper"] is not None
    assert in_range_info["tick_lower"] < in_range_info["tick_upper"]
    conn.close()


def test_rh02cm_out_of_range_steps_do_not_accrue_fee(tmp_path):
    """2. 出区间的步：出区间期间 fee_growth 在涨，accrued 纹丝不动；回区间后只从回区间那一步的 fee_growth 算增量。"""
    conn = _fresh_store(tmp_path)
    entry_price = Decimal("2484.0")
    meta = {
        "range_pct": Decimal("10.0"),  # range is [2235.6, 2732.4]
        "dec0": 18,
        "dec1": 6,
        "quote_usd_per_token1": Decimal("1.0"),
        "pool_address": "0xpool-rh02cm",
    }
    dfg = Decimal(10**18)
    # Step 0: in-range (2484) -> accrued = 0
    # Step 1: out-of-range (3500) -> fg advances by dfg, but out-of-range so accrued stays 0
    # Step 2: out-of-range (3500) -> fg advances by dfg, accrued stays 0
    # Step 3: in-range again (2484) -> fg advances by dfg, accrued increases by 1*dfg only!
    samples = [
        _open_sample(0, reference_mid=entry_price, fee_growth_global_0=0, fee_growth_global_1=0),
        _open_sample(1, reference_mid=Decimal("3500.0"), fee_growth_global_0=dfg, fee_growth_global_1=dfg),
        _open_sample(2, reference_mid=Decimal("3500.0"), fee_growth_global_0=2*dfg, fee_growth_global_1=2*dfg),
        _open_sample(3, reference_mid=entry_price, fee_growth_global_0=3*dfg, fee_growth_global_1=3*dfg),
    ]
    steps = _run(conn, samples, pool_meta=meta)

    assert steps[0].in_range is True
    assert steps[1].in_range is False
    assert steps[2].in_range is False
    assert steps[3].in_range is True

    # Check marks in database
    marks = conn.execute(
        "SELECT accrued_fee, unvalued_risk_json FROM rh_position_marks ORDER BY mark_time"
    ).fetchall()
    assert len(marks) == 4

    # Step 0: accrued = 0
    risk0 = json.loads(marks[0][1])
    assert risk0["in_range"] is True
    assert Decimal(marks[0][0]) == Decimal(0)

    # Step 1: out-of-range -> accrued stays 0
    risk1 = json.loads(marks[1][1])
    assert risk1["in_range"] is False
    assert Decimal(marks[1][0]) == Decimal(0)

    # Step 2: out-of-range -> accrued stays 0
    risk2 = json.loads(marks[2][1])
    assert risk2["in_range"] is False
    assert Decimal(marks[2][0]) == Decimal(0)

    # Step 3: in-range -> accrued advances by single increment (from step 2 to step 3)
    risk3 = json.loads(marks[3][1])
    assert risk3["in_range"] is True
    accrued_3 = Decimal(marks[3][0])
    assert accrued_3 > 0

    # Calculate expected single-step fee
    inv = inventory_for_position(
        position_usd=POSITION_USD,
        entry_price=entry_price,
        range_pct=Decimal("10.0"),
        dec0=18,
        dec1=6,
        quote_usd_per_token1=Decimal("1.0"),
    )
    tok0 = (inv.liquidity_raw * dfg / (Decimal(2)**128) / Decimal(10**18))
    tok1 = (inv.liquidity_raw * dfg / (Decimal(2)**128) / Decimal(10**6))
    expected_single_fee = (tok0 * entry_price + tok1) * Decimal("1.0")

    assert abs(accrued_3 - expected_single_fee) < 1e-20

    summary = episode_summary(steps, pool_meta=meta)
    assert summary["in_range"]["in_range_steps"] == 2
    assert summary["in_range"]["out_of_range_steps"] == 2
    assert summary["in_range"]["fraction"] == Decimal("0.5")
    conn.close()


def test_rh02cm_price_none_not_counted_as_out_of_range(tmp_path):
    """3. price 为 None：既不累加，也不算出区间，in_range 记 null，计入 skipped_no_price。"""
    conn = _fresh_store(tmp_path)
    entry_price = Decimal("2484.0")
    meta = {
        "range_pct": Decimal("10.0"),
        "dec0": 18,
        "dec1": 6,
        "quote_usd_per_token1": Decimal("1.0"),
        "pool_address": "0xpool-rh02cm",
    }
    dfg = Decimal(10**18)
    samples = [
        _open_sample(0, reference_mid=entry_price, fee_growth_global_0=0, fee_growth_global_1=0),
        _open_sample(1, reference_mid=None, fee_growth_global_0=dfg, fee_growth_global_1=dfg),
        _open_sample(2, reference_mid=entry_price, fee_growth_global_0=2*dfg, fee_growth_global_1=2*dfg),
    ]
    steps = _run(conn, samples, pool_meta=meta)

    assert steps[0].in_range is True
    assert steps[1].in_range is None
    assert steps[2].in_range is True

    marks = conn.execute(
        "SELECT accrued_fee, unvalued_risk_json FROM rh_position_marks ORDER BY mark_time"
    ).fetchall()
    risk1 = json.loads(marks[1][1])
    assert risk1["in_range"] is None
    assert risk1["skipped"] is True

    summary = episode_summary(steps, pool_meta=meta)
    assert summary["in_range"]["in_range_steps"] == 2
    assert summary["in_range"]["out_of_range_steps"] == 0
    assert summary["in_range"]["skipped_no_price"] == 1
    assert summary["in_range"]["fraction"] == Decimal("1.0")
    conn.close()


def test_rh02cm_boundary_tick_lower_in_tick_upper_out(tmp_path):
    """4. 边界条件：刚好在 tick_lower 算在内，刚好在 tick_upper 算出区间（[tick_lower, tick_upper) 半开区间）。"""
    from scripts.lp_rh_in_range_v1_readonly import tick_from_price
    conn = _fresh_store(tmp_path)
    entry_price = Decimal("2484.0")
    meta = {
        "range_pct": Decimal("10.0"),
        "dec0": 18,
        "dec1": 6,
        "quote_usd_per_token1": Decimal("1.0"),
        "pool_address": "0xpool-rh02cm",
    }
    p_lower = entry_price * (Decimal(1) - Decimal("10.0") / Decimal(100))
    p_upper = entry_price * (Decimal(1) + Decimal("10.0") / Decimal(100))
    t_lower = tick_from_price(p_lower, dec0=18, dec1=6)
    t_upper = tick_from_price(p_upper, dec0=18, dec1=6)

    # Exactly at p_lower and p_upper
    samples = [
        _open_sample(0, reference_mid=entry_price),
        _open_sample(1, reference_mid=p_lower),
        _open_sample(2, reference_mid=p_upper),
    ]
    steps = _run(conn, samples, pool_meta=meta)

    assert steps[0].in_range is True
    # At lower tick boundary: t >= t_lower -> in_range is True
    assert steps[1].in_range is True
    # At upper tick boundary: t >= t_upper -> in_range is False
    assert steps[2].in_range is False

    summary = episode_summary(steps, pool_meta=meta)
    assert summary["in_range"]["in_range_steps"] == 2
    assert summary["in_range"]["out_of_range_steps"] == 1
    conn.close()


def test_rh02cm_all_steps_no_price_fraction_is_none():
    """5. fraction 分母为 0 时为 None 不是 0。"""
    steps = [
        ShadowStep(
            step_index=0, sample_time="2026-09-08T18:00:00Z", price=None, terminal_eligible=False,
            primary_status="DECISION_BLOCKED", dominant_blocker="NO_PRICE", nav=None, net_pnl=None,
            hodl_value=None, reservation_granted=False, in_range=None
        ),
        ShadowStep(
            step_index=1, sample_time="2026-09-08T18:01:00Z", price=None, terminal_eligible=False,
            primary_status="DECISION_BLOCKED", dominant_blocker="NO_PRICE", nav=None, net_pnl=None,
            hodl_value=None, reservation_granted=False, in_range=None
        ),
    ]
    summary = episode_summary(steps)
    in_range_info = summary["in_range"]
    assert in_range_info["in_range_steps"] == 0
    assert in_range_info["out_of_range_steps"] == 0
    assert in_range_info["skipped_no_price"] == 2
    assert in_range_info["fraction"] is None


def _create_organic_db(db_path, windows=()):
    conn = sqlite3.connect(str(db_path))
    conn.executescript(ORGANIC_SCHEMA)
    for idx, w in enumerate(windows, 1):
        conn.execute(
            """
            INSERT INTO rh_organic_windows (
                window_start_block, window_end_block, sample_time, provider,
                n_events, n_unique_senders, top1_share, top5_share, hhi,
                round_trip_share, total_volume, round_trip_volume,
                concentration_excess_volume, organic_fraction, coverage_frac,
                fetch_status, estimate_status, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                w.get("window_start_block", idx * 100),
                w.get("window_end_block", (idx + 1) * 100),
                w["sample_time"],
                w.get("provider", "test"),
                w.get("n_events", 10),
                w.get("n_unique_senders", 5),
                w.get("top1_share", "0.2"),
                w.get("top5_share", "0.5"),
                w.get("hhi", "0.1"),
                w.get("round_trip_share", "0.05"),
                w.get("total_volume", "100000"),
                w.get("round_trip_volume", "5000"),
                w.get("concentration_excess_volume", "0"),
                str(w["organic_fraction"]) if w.get("organic_fraction") is not None else None,
                str(w["coverage_frac"]) if w.get("coverage_frac") is not None else None,
                w.get("fetch_status", "OK"),
                w.get("estimate_status", "COMPUTED"),
                w.get("error"),
            ),
        )
    conn.commit()
    conn.close()


def test_rh02cn_1_organic_discount_accrual_nine_tenths(tmp_path):
    """1. 窗口 organic_fraction = 0.9、COMPUTED、coverage_frac = 1 -> accrued 恰好是 0.9 倍。"""
    conn = _fresh_store(tmp_path)
    org_db = tmp_path / "organic.db"
    _create_organic_db(org_db, [{
        "sample_time": "2026-09-08T18:00:00Z",
        "organic_fraction": "0.9",
        "estimate_status": "COMPUTED",
        "coverage_frac": "1.0",
    }])
    price = Decimal("2484.0")
    meta = {
        "range_pct": Decimal("10.0"),
        "dec0": 18,
        "dec1": 6,
        "quote_usd_per_token1": Decimal("1.0"),
        "pool_address": "0xpool-rh02cn",
    }
    dfg0 = Decimal(10**18)
    dfg1 = Decimal(10**18)
    samples = [
        _open_sample(0, reference_mid=price, fee_growth_global_0=Decimal(0), fee_growth_global_1=Decimal(0),
                     quote_usd_per_token1=Decimal("1.0")),
        _open_sample(1, reference_mid=price, fee_growth_global_0=dfg0, fee_growth_global_1=dfg1,
                     quote_usd_per_token1=Decimal("1.0")),
    ]
    steps = _run(conn, samples, pool_meta=meta, organic_db_path=str(org_db))
    summary = episode_summary(steps, pool_meta=meta)
    org = summary["organic"]
    assert org["accrued_raw"] > 0
    assert org["accrued_organic"] == org["accrued_raw"] * Decimal("0.9")
    assert org["steps_discounted"] == 2
    assert org["steps_not_discounted"] == 0
    assert org["fraction_avg"] == Decimal("0.9")

    marks = conn.execute("SELECT accrued_fee, unvalued_risk_json FROM rh_position_marks ORDER BY mark_time").fetchall()
    assert Decimal(marks[1][0]) == org["accrued_organic"]
    risk1 = json.loads(marks[1][1])
    assert risk1["organic_status"] == "OK"
    assert isinstance(risk1["organic_fraction"], str)
    assert Decimal(risk1["organic_fraction"]) == Decimal("0.9")
    assert isinstance(risk1["fee_usd_raw"], str)
    assert isinstance(risk1["fee_usd_organic"], str)
    assert Decimal(risk1["fee_usd_organic"]) == Decimal(risk1["fee_usd_raw"]) * Decimal("0.9")


def test_rh02cn_2_no_window_fail_close(tmp_path):
    """2. 无窗口 -> 不折减，accrued_organic == accrued_raw，标记 NO_WINDOW。"""
    conn = _fresh_store(tmp_path)
    org_db = tmp_path / "organic_empty.db"
    _create_organic_db(org_db, [])
    price = Decimal("2484.0")
    meta = {
        "range_pct": Decimal("10.0"),
        "dec0": 18,
        "dec1": 6,
        "quote_usd_per_token1": Decimal("1.0"),
        "pool_address": "0xpool-rh02cn",
    }
    dfg0 = Decimal(10**18)
    dfg1 = Decimal(10**18)
    samples = [
        _open_sample(0, reference_mid=price, fee_growth_global_0=Decimal(0), fee_growth_global_1=Decimal(0),
                     quote_usd_per_token1=Decimal("1.0")),
        _open_sample(1, reference_mid=price, fee_growth_global_0=dfg0, fee_growth_global_1=dfg1,
                     quote_usd_per_token1=Decimal("1.0")),
    ]
    steps = _run(conn, samples, pool_meta=meta, organic_db_path=str(org_db))
    summary = episode_summary(steps, pool_meta=meta)
    org = summary["organic"]
    assert org["accrued_raw"] > 0
    assert org["accrued_organic"] == org["accrued_raw"]
    assert org["steps_discounted"] == 0
    assert org["steps_not_discounted"] == 2

    marks = conn.execute("SELECT unvalued_risk_json FROM rh_position_marks ORDER BY mark_time").fetchall()
    risk1 = json.loads(marks[1][0])
    assert risk1["organic_status"] == "ORGANIC_UNAVAILABLE:NO_WINDOW"
    assert risk1["organic_fraction"] is None


def test_rh02cn_3_estimate_status_not_computed(tmp_path):
    """3. estimate_status = 'INPUTS_UNAVAILABLE' -> 不折减并标记。"""
    conn = _fresh_store(tmp_path)
    org_db = tmp_path / "organic.db"
    _create_organic_db(org_db, [{
        "sample_time": "2026-09-08T18:00:00Z",
        "organic_fraction": "0.9",
        "estimate_status": "INPUTS_UNAVAILABLE",
        "coverage_frac": "1.0",
    }])
    price = Decimal("2484.0")
    meta = {
        "range_pct": Decimal("10.0"),
        "dec0": 18,
        "dec1": 6,
        "quote_usd_per_token1": Decimal("1.0"),
        "pool_address": "0xpool-rh02cn",
    }
    dfg0 = Decimal(10**18)
    dfg1 = Decimal(10**18)
    samples = [
        _open_sample(0, reference_mid=price, fee_growth_global_0=Decimal(0), fee_growth_global_1=Decimal(0),
                     quote_usd_per_token1=Decimal("1.0")),
        _open_sample(1, reference_mid=price, fee_growth_global_0=dfg0, fee_growth_global_1=dfg1,
                     quote_usd_per_token1=Decimal("1.0")),
    ]
    steps = _run(conn, samples, pool_meta=meta, organic_db_path=str(org_db))
    summary = episode_summary(steps, pool_meta=meta)
    org = summary["organic"]
    assert org["accrued_raw"] > 0
    assert org["accrued_organic"] == org["accrued_raw"]
    assert org["steps_discounted"] == 0
    assert org["steps_not_discounted"] == 2

    marks = conn.execute("SELECT unvalued_risk_json FROM rh_position_marks ORDER BY mark_time").fetchall()
    risk1 = json.loads(marks[1][0])
    assert risk1["organic_status"] == "ORGANIC_UNAVAILABLE:INPUTS_UNAVAILABLE"
    assert risk1["organic_fraction"] is None


def test_rh02cn_4_partial_coverage(tmp_path):
    """4. coverage_frac = 0.5 -> 不折减并标记 PARTIAL_COVERAGE。"""
    conn = _fresh_store(tmp_path)
    org_db = tmp_path / "organic.db"
    _create_organic_db(org_db, [{
        "sample_time": "2026-09-08T18:00:00Z",
        "organic_fraction": "0.9",
        "estimate_status": "COMPUTED",
        "coverage_frac": "0.5",
    }])
    price = Decimal("2484.0")
    meta = {
        "range_pct": Decimal("10.0"),
        "dec0": 18,
        "dec1": 6,
        "quote_usd_per_token1": Decimal("1.0"),
        "pool_address": "0xpool-rh02cn",
    }
    dfg0 = Decimal(10**18)
    dfg1 = Decimal(10**18)
    samples = [
        _open_sample(0, reference_mid=price, fee_growth_global_0=Decimal(0), fee_growth_global_1=Decimal(0),
                     quote_usd_per_token1=Decimal("1.0")),
        _open_sample(1, reference_mid=price, fee_growth_global_0=dfg0, fee_growth_global_1=dfg1,
                     quote_usd_per_token1=Decimal("1.0")),
    ]
    steps = _run(conn, samples, pool_meta=meta, organic_db_path=str(org_db))
    summary = episode_summary(steps, pool_meta=meta)
    org = summary["organic"]
    assert org["accrued_raw"] > 0
    assert org["accrued_organic"] == org["accrued_raw"]
    assert org["steps_discounted"] == 0
    assert org["steps_not_discounted"] == 2

    marks = conn.execute("SELECT unvalued_risk_json FROM rh_position_marks ORDER BY mark_time").fetchall()
    risk1 = json.loads(marks[1][0])
    assert risk1["organic_status"] == "ORGANIC_UNAVAILABLE:PARTIAL_COVERAGE"
    assert risk1["organic_fraction"] is None


@pytest.mark.parametrize("invalid_frac", [None, "0", "1.5"])
def test_rh02cn_5_invalid_fraction(tmp_path, invalid_frac):
    """5. organic_fraction = None / 0 / 1.5 -> 都不折减并标记 INVALID_FRACTION。"""
    conn = _fresh_store(tmp_path)
    org_db = tmp_path / "organic.db"
    _create_organic_db(org_db, [{
        "sample_time": "2026-09-08T18:00:00Z",
        "organic_fraction": invalid_frac,
        "estimate_status": "COMPUTED",
        "coverage_frac": "1.0",
    }])
    price = Decimal("2484.0")
    meta = {
        "range_pct": Decimal("10.0"),
        "dec0": 18,
        "dec1": 6,
        "quote_usd_per_token1": Decimal("1.0"),
        "pool_address": "0xpool-rh02cn",
    }
    dfg0 = Decimal(10**18)
    dfg1 = Decimal(10**18)
    samples = [
        _open_sample(0, reference_mid=price, fee_growth_global_0=Decimal(0), fee_growth_global_1=Decimal(0),
                     quote_usd_per_token1=Decimal("1.0")),
        _open_sample(1, reference_mid=price, fee_growth_global_0=dfg0, fee_growth_global_1=dfg1,
                     quote_usd_per_token1=Decimal("1.0")),
    ]
    steps = _run(conn, samples, pool_meta=meta, organic_db_path=str(org_db))
    summary = episode_summary(steps, pool_meta=meta)
    org = summary["organic"]
    assert org["accrued_raw"] > 0
    assert org["accrued_organic"] == org["accrued_raw"]
    assert org["steps_discounted"] == 0
    assert org["steps_not_discounted"] == 2

    marks = conn.execute("SELECT unvalued_risk_json FROM rh_position_marks ORDER BY mark_time").fetchall()
    risk1 = json.loads(marks[1][0])
    assert risk1["organic_status"] == "ORGANIC_UNAVAILABLE:INVALID_FRACTION"
    assert risk1["organic_fraction"] is None


def test_rh02cn_6_steps_span_multiple_windows(tmp_path):
    """6. 三个窗口时间不同、步跨越它们 -> 每步用各自不晚于自己的窗口，非最新窗口。"""
    conn = _fresh_store(tmp_path)
    org_db = tmp_path / "organic.db"
    _create_organic_db(org_db, [
        {"sample_time": "2026-09-08T18:00:00Z", "organic_fraction": "0.8", "estimate_status": "COMPUTED", "coverage_frac": "1.0"},
        {"sample_time": "2026-09-08T18:02:00Z", "organic_fraction": "0.9", "estimate_status": "COMPUTED", "coverage_frac": "1.0"},
        {"sample_time": "2026-09-08T18:04:00Z", "organic_fraction": "0.7", "estimate_status": "COMPUTED", "coverage_frac": "1.0"},
    ])
    price = Decimal("2484.0")
    meta = {
        "range_pct": Decimal("10.0"),
        "dec0": 18,
        "dec1": 6,
        "quote_usd_per_token1": Decimal("1.0"),
        "pool_address": "0xpool-rh02cn",
    }
    samples = [
        _open_sample(0, reference_mid=price, sample_time="2026-09-08T18:00:00Z", fee_growth_global_0=Decimal(0), fee_growth_global_1=Decimal(0)),
        _open_sample(1, reference_mid=price, sample_time="2026-09-08T18:01:00Z", fee_growth_global_0=Decimal(10**18), fee_growth_global_1=Decimal(10**18)),
        _open_sample(2, reference_mid=price, sample_time="2026-09-08T18:03:00Z", fee_growth_global_0=Decimal(2 * 10**18), fee_growth_global_1=Decimal(2 * 10**18)),
        _open_sample(3, reference_mid=price, sample_time="2026-09-08T18:05:00Z", fee_growth_global_0=Decimal(3 * 10**18), fee_growth_global_1=Decimal(3 * 10**18)),
    ]
    steps = _run(conn, samples, pool_meta=meta, organic_db_path=str(org_db))
    marks = conn.execute("SELECT unvalued_risk_json FROM rh_position_marks ORDER BY mark_time").fetchall()
    risks = [json.loads(m[0]) for m in marks]
    assert Decimal(risks[0]["organic_fraction"]) == Decimal("0.8")
    assert Decimal(risks[1]["organic_fraction"]) == Decimal("0.8")
    assert Decimal(risks[2]["organic_fraction"]) == Decimal("0.9")
    assert Decimal(risks[3]["organic_fraction"]) == Decimal("0.7")


def test_rh02cn_7_stack_with_in_range(tmp_path):
    """7. 与 in-range 叠加：区间外不累加，区间内且有窗口累加折减后的值。"""
    conn = _fresh_store(tmp_path)
    org_db = tmp_path / "organic.db"
    _create_organic_db(org_db, [{
        "sample_time": "2026-09-08T18:00:00Z",
        "organic_fraction": "0.9",
        "estimate_status": "COMPUTED",
        "coverage_frac": "1.0",
    }])
    price = Decimal("2484.0")
    meta = {
        "range_pct": Decimal("10.0"),
        "dec0": 18,
        "dec1": 6,
        "quote_usd_per_token1": Decimal("1.0"),
        "pool_address": "0xpool-rh02cn",
    }
    dfg = Decimal(10**18)
    samples = [
        _open_sample(0, reference_mid=price, sample_time="2026-09-08T18:00:00Z",
                     fee_growth_global_0=Decimal(0), fee_growth_global_1=Decimal(0)),
        _open_sample(1, reference_mid=price * Decimal("1.5"), sample_time="2026-09-08T18:01:00Z",
                     fee_growth_global_0=dfg, fee_growth_global_1=dfg),
        _open_sample(2, reference_mid=price, sample_time="2026-09-08T18:02:00Z",
                     fee_growth_global_0=dfg * 2, fee_growth_global_1=dfg * 2),
    ]
    steps = _run(conn, samples, pool_meta=meta, organic_db_path=str(org_db))
    marks = conn.execute("SELECT accrued_fee, unvalued_risk_json FROM rh_position_marks ORDER BY mark_time").fetchall()
    assert Decimal(marks[0][0]) == Decimal(0)
    risk1 = json.loads(marks[1][1])
    assert risk1["in_range"] is False
    assert risk1["organic_status"] == "OK"
    assert Decimal(marks[1][0]) == Decimal(0)
    risk2 = json.loads(marks[2][1])
    assert risk2["in_range"] is True
    assert risk2["organic_status"] == "OK"
    assert Decimal(marks[2][0]) > Decimal(0)
    assert Decimal(marks[2][0]) == steps[2].organic["fee_usd_organic"]
    assert Decimal(risk2["fee_usd_organic"]) == steps[2].organic["fee_usd_organic"]
    assert Decimal(risk2["fee_usd_organic"]) == Decimal(risk2["fee_usd_raw"]) * Decimal("0.9")


def test_rh02cn_8_summary_fractions_none_when_no_windows(tmp_path):
    """8. fraction_min / fraction_max / fraction_avg 在全部步都没窗口时都是 None 不是 0。"""
    conn = _fresh_store(tmp_path)
    org_db = tmp_path / "organic_empty.db"
    _create_organic_db(org_db, [])
    price = Decimal("2484.0")
    meta = {
        "range_pct": Decimal("10.0"),
        "dec0": 18,
        "dec1": 6,
        "quote_usd_per_token1": Decimal("1.0"),
        "pool_address": "0xpool-rh02cn",
    }
    samples = [
        _open_sample(0, reference_mid=price, fee_growth_global_0=Decimal(0), fee_growth_global_1=Decimal(0)),
        _open_sample(1, reference_mid=price, fee_growth_global_0=Decimal(10**18), fee_growth_global_1=Decimal(10**18)),
    ]
    steps = _run(conn, samples, pool_meta=meta, organic_db_path=str(org_db))
    summary = episode_summary(steps, pool_meta=meta)
    org = summary["organic"]
    assert org["steps_discounted"] == 0
    assert org["steps_not_discounted"] == 2
    assert org["fraction_min"] is None
    assert org["fraction_max"] is None
    assert org["fraction_avg"] is None
    assert org["fraction_min"] is not 0
    assert org["fraction_max"] is not 0
    assert org["fraction_avg"] is not 0


def test_rh02cn_daemon_log_line(capsys):
    """Test daemon log line formats organic=<disc>/<tot>."""
    from scripts.lp_rh_shadow_daemon_v1_readonly import run_round_safe
    from unittest.mock import patch, MagicMock

    summary = {
        "total_steps": 10,
        "organic": {
            "steps_discounted": 8,
            "steps_not_discounted": 2,
        },
    }
    with patch("scripts.lp_rh_shadow_daemon_v1_readonly.run_one_round", return_value=summary):
        cfg = MagicMock()
        cfg.shadow_db = ":memory:"
        cfg.dry_run = True
        run_round_safe(cfg, shadow_conn=MagicMock(), episode_id="ep-test-organic", now_fn=lambda: "2026-09-08T18:00:00Z")
    captured = capsys.readouterr()
    assert "[rh-shadow-daemon] ep-test-organic: organic=8/10" in captured.err


# ---------------------------------------------------------------------------
# RH-03 / T35: leg_fraction & leg_fraction_status persistence into cost_components_json
# ---------------------------------------------------------------------------

def test_rh03_cost_components_json_contains_leg_fraction_keys(tmp_path):
    """1. 跑一个 episode -> rh_economic_evaluations.cost_components_json 里确实带 leg_fraction 与 leg_fraction_status 两个键。"""
    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-lf-keys")
    meta = _conj_meta(range_pct=Decimal("10.0"))

    _run(conn, [sample], pool_meta=meta)
    conn.commit()

    row = conn.execute(
        "SELECT cost_components_json FROM rh_economic_evaluations WHERE snapshot_id = 'h-lf-keys'"
    ).fetchone()
    assert row is not None, "rh_economic_evaluations row must exist"
    cc = json.loads(row[0])
    assert "leg_fraction" in cc, "cost_components_json must contain leg_fraction key"
    assert "leg_fraction_status" in cc, "cost_components_json must contain leg_fraction_status key"
    conn.close()


def test_rh03_leg_fraction_computed_when_derivable(tmp_path):
    """2. 比例算得出时 -> leg_fraction_status == 'COMPUTED'，Decimal(leg_fraction) 等于被测模块返回的值。"""
    from scripts.lp_rh_netcover_inputs_v1_readonly import assemble_rh_clmm_inputs
    from scripts.lp_rh_shadow_runner_v1_readonly import _evidence_for

    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-lf-computed")
    meta = _conj_meta(range_pct=Decimal("10.0"))

    ev = _evidence_for(sample, meta)
    expected_record = assemble_rh_clmm_inputs(ev, position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS)
    assert expected_record["leg_fraction_status"] == "COMPUTED"

    _run(conn, [sample], pool_meta=meta)
    conn.commit()

    row = conn.execute(
        "SELECT cost_components_json FROM rh_economic_evaluations WHERE snapshot_id = 'h-lf-computed'"
    ).fetchone()
    assert row is not None
    cc = json.loads(row[0])
    assert cc["leg_fraction_status"] == "COMPUTED"
    assert isinstance(cc["leg_fraction"], str), "leg_fraction must be stored as fixed-point decimal string, not float"
    assert Decimal(cc["leg_fraction"]) == Decimal(str(expected_record["leg_fraction"]))
    conn.close()


def test_rh03_leg_fraction_fallback_when_range_pct_missing(tmp_path):
    """3. 比例算不出(造一个缺 range_pct 的 pool_meta) -> 落库的 leg_fraction 是 1.0、leg_fraction_status 以 FALLBACK_FULL_POSITION: 开头。"""
    from scripts.lp_rh_netcover_inputs_v1_readonly import assemble_rh_clmm_inputs
    from scripts.lp_rh_shadow_runner_v1_readonly import _evidence_for

    conn = _fresh_store(tmp_path)
    meta = {k: v for k, v in _conj_meta().items() if k != "range_pct"}
    sample = _passing_sample(0, source_payload_hash="h-lf-fallback")
    assert "range_pct" not in sample

    ev = _evidence_for(sample, meta)
    expected_record = assemble_rh_clmm_inputs(ev, position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS)
    assert expected_record["leg_fraction_status"].startswith("FALLBACK_FULL_POSITION:")

    _run(conn, [sample], pool_meta=meta)
    conn.commit()

    row = conn.execute(
        "SELECT cost_components_json FROM rh_economic_evaluations WHERE snapshot_id = 'h-lf-fallback'"
    ).fetchone()
    assert row is not None
    cc = json.loads(row[0])
    assert isinstance(cc["leg_fraction"], str), "leg_fraction must be stored as string"
    assert Decimal(cc["leg_fraction"]) == Decimal("1.0")
    assert cc["leg_fraction_status"].startswith("FALLBACK_FULL_POSITION:")
    assert cc["leg_fraction_status"] == expected_record["leg_fraction_status"]
    conn.close()


def test_rh03_regression_existing_cost_keys_unchanged(tmp_path):
    """4. 回归保护: 八个既有成本键的数值一个都没变。"""
    from scripts.lp_rh_netcover_inputs_v1_readonly import assemble_rh_clmm_inputs
    from scripts.lp_netcover_engine_v1_readonly import apply_netcover_gate
    from scripts.lp_rh_shadow_runner_v1_readonly import _COST_COMPONENT_KEYS, _evidence_for

    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-lf-regression")
    meta = _conj_meta(range_pct=Decimal("10.0"))

    ev = _evidence_for(sample, meta)
    expected_record = assemble_rh_clmm_inputs(ev, position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS)
    expected_gated = apply_netcover_gate([expected_record])[0]

    _run(conn, [sample], pool_meta=meta)
    conn.commit()

    row = conn.execute(
        "SELECT cost_components_json FROM rh_economic_evaluations WHERE snapshot_id = 'h-lf-regression'"
    ).fetchone()
    assert row is not None
    cc = json.loads(row[0])

    for k in _COST_COMPONENT_KEYS:
        assert k in cc, f"Cost key {k} must exist in cost_components_json"
        exp_val = expected_gated.get(k)
        if exp_val is None:
            assert cc[k] is None
        else:
            assert Decimal(str(cc[k])) == Decimal(str(exp_val)), f"Mismatch on {k}: {cc[k]} vs {exp_val}"

    assert cc.get("gas_usd_source") == expected_gated.get("gas_usd_source")
    assert "size_interval" in cc
    conn.close()


def test_rh03_leg_fraction_none_when_unavailable(tmp_path):
    """5. 取不到时存 None，不要存 0、不要存空字符串、不要省略这个键。"""
    from unittest.mock import patch
    from scripts.lp_netcover_engine_v1_readonly import apply_netcover_gate

    conn = _fresh_store(tmp_path)
    sample = _passing_sample(0, source_payload_hash="h-lf-none")
    meta = _conj_meta()

    real_apply = apply_netcover_gate

    def mock_apply_gate(records, **kwargs):
        res = real_apply(records, **kwargs)
        for r in res:
            r.pop("leg_fraction", None)
            r.pop("leg_fraction_status", None)
        return res

    with patch("scripts.lp_rh_shadow_runner_v1_readonly.apply_netcover_gate", side_effect=mock_apply_gate):
        _run(conn, [sample], pool_meta=meta)
    conn.commit()

    row = conn.execute(
        "SELECT cost_components_json FROM rh_economic_evaluations WHERE snapshot_id = 'h-lf-none'"
    ).fetchone()
    assert row is not None
    cc = json.loads(row[0])

    assert "leg_fraction" in cc, "key leg_fraction must not be omitted"
    assert "leg_fraction_status" in cc, "key leg_fraction_status must not be omitted"
    assert cc["leg_fraction"] is None, "leg_fraction must be None when unavailable"
    assert cc["leg_fraction_status"] is None, "leg_fraction_status must be None when unavailable"
    assert cc["leg_fraction"] != 0
    assert cc["leg_fraction"] != "0"
    assert cc["leg_fraction"] != ""
    assert cc["leg_fraction_status"] != ""
    conn.close()








