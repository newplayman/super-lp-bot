"""Tests for RH-02ae: load_samples_from_db must SELECT and return the
fee_growth_global_0/1 columns so run_episode's NAV path gets its inputs.

All tests use tmp_path scratch stores and synthetic rows.  No network, no
wallet, no broadcast.  Pairs with scripts/lp_rh_shadow_runner_v1_readonly.py.
"""
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from decimal import Decimal

from scripts.lp_rh_shadow_runner_v1_readonly import (
    episode_summary,
    load_samples_from_db,
    run_episode,
)
from scripts.lp_rh_store_v1_readonly import insert_row, migrate, open_store

POSITION_USD = Decimal("1000")
CAPITAL_USD = Decimal("10000")
HORIZON_HOURS = 8760
BIG = "45276536446647926570249392638825938606714"


def _ts(idx):
    return f"2026-01-01T{idx // 3600:02d}:{(idx // 60) % 60:02d}:{idx % 60:02d}Z"


def _fresh_store(tmp_path, name="s.db"):
    conn = open_store(tmp_path / name)
    migrate(conn)
    return conn


def _insert_state(conn, idx, *, mid="1.5", fg0=None, fg1=None,
                  session="sess-1", age=10, paused=0, payload="hash-1",
                  source_event_time=None):
    st = _ts(idx)
    insert_row(conn, "rh_market_states", {
        "asset_address": "poolX", "sample_time": st, "chain_id": 4663,
        "session": session, "health_flags_json": "{}",
        "reference_mid": mid, "multiplier_human": "1.0",
        "reference_age_secs": age, "oracle_paused": paused,
        "source_payload_hash": payload,
        "source_event_time": source_event_time if source_event_time is not None else st,
        "fee_growth_global_0": fg0, "fee_growth_global_1": fg1,
    })


def _passing_sample(idx, *, sample_time, **overrides):
    s = {
        "candidate_key": f"pool-{idx}", "sample_time": sample_time,
        "chain_id": 4663, "attestation_status": "ATTESTED_SAME_BLOCK",
        "protocol": "v3", "fee_apr_pct": 100.0, "sigma_daily": 0.0,
        "liquidity_raw": 1e20,
        "sqrt_price_x96": 4_340_000_000_000_000_000_000_000_000_000,
        "fee": 500, "dec0": 18, "dec1": 6, "gas_usd_estimate": 0.01,
        "legacy_required_conjunction": True, "identity_verified": True,
        "protocol_capabilities_sufficient": True, "data_complete_and_fresh": True,
        "profile_policy_pass": True, "absolute_profit_pass": True,
        "position_and_exit_depth_pass": True, "capital_policy_pass": True,
        "source_event_time": "2026-01-01T00:00:05Z",
        "oracle_heartbeat_secs": 3600, "reference_age_secs": 10,
        "source_payload_hash": "abc123",
    }
    s.update(overrides)
    return s


def _run(conn, samples, *, episode="ep"):
    # RH-02ai: pool_meta is now required for a NAV -- the fee formula scales
    # feeGrowth by the position's liquidity, derived from price/range/decimals.
    # Without it the step fails closed rather than computing a wrong number.
    return run_episode(
        conn, strategy_episode=episode, samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode="SHADOW_SCENARIO",
        now_fn=lambda: "2026-01-01T01:00:00Z",
        pool_meta={"input_price_usd": 2484.0, "range_pct": 10.0,
                   "dec0": 18, "dec1": 6},
    )


def test_loaded_sample_has_fee_growth_keys_with_written_values(tmp_path):
    conn = _fresh_store(tmp_path)
    _insert_state(conn, 0, fg0=BIG, fg1="12345678901234567890123456789012345678901")
    samples, skipped = load_samples_from_db(conn, pool="poolX", limit=10)
    assert skipped == 0 and len(samples) == 1
    s = samples[0]
    assert "fee_growth_global_0" in s and "fee_growth_global_1" in s
    assert s["fee_growth_global_0"] == BIG
    assert s["fee_growth_global_1"] == "12345678901234567890123456789012345678901"
    conn.close()


def test_null_fee_growth_is_none_not_zero(tmp_path):
    conn = _fresh_store(tmp_path)
    _insert_state(conn, 0, fg0=None, fg1=None)
    samples, _ = load_samples_from_db(conn, pool="poolX", limit=10)
    s = samples[0]
    assert "fee_growth_global_0" in s and "fee_growth_global_1" in s  # present
    assert s["fee_growth_global_0"] is None  # None, not 0, not absent
    assert s["fee_growth_global_1"] is None
    conn.close()


def test_big_uint256_roundtrip_char_equal_str(tmp_path):
    conn = _fresh_store(tmp_path)
    _insert_state(conn, 0, fg0=BIG, fg1=BIG)
    samples, _ = load_samples_from_db(conn, pool="poolX", limit=10)
    s = samples[0]
    assert s["fee_growth_global_0"] == BIG
    assert s["fee_growth_global_1"] == BIG
    assert isinstance(s["fee_growth_global_0"], str)
    assert isinstance(s["fee_growth_global_1"], str)
    conn.close()


def test_end_to_end_two_fg_samples_nav_computed(tmp_path):
    base = [
        _passing_sample(0, sample_time="2026-01-01T00:00:00Z"),
        _passing_sample(1, sample_time="2026-01-01T00:01:00Z"),
    ]
    conn_no = _fresh_store(tmp_path, "no.db")
    steps_no = _run(conn_no, base, episode="ep-nofg")
    assert episode_summary(steps_no)["steps_without_nav"] == 2
    conn_no.close()
    with_fg = []
    for i, s in enumerate(base):
        s2 = dict(s)
        s2["fee_growth_global_0"] = str(1000 + i)
        s2["fee_growth_global_1"] = str(2000 + i)
        # RH-02ai: each leg is converted to USD at the step's own price before
        # the two are summed, so a step without reference_mid fails closed.
        # The old formula multiplied a USD notional straight into feeGrowth and
        # so never needed a price -- that was the dimensional error.
        s2["reference_mid"] = "2484"
        with_fg.append(s2)
    conn_yes = _fresh_store(tmp_path, "yes.db")
    steps_yes = _run(conn_yes, with_fg, episode="ep-withfg")
    assert episode_summary(steps_yes)["steps_without_nav"] < 2
    assert all(s.nav is not None for s in steps_yes)
    conn_yes.close()


def test_single_fg_sample_step_still_without_nav(tmp_path):
    s0 = _passing_sample(0, sample_time="2026-01-01T00:00:00Z")  # no fg
    s1 = _passing_sample(1, sample_time="2026-01-01T00:01:00Z")
    s1["fee_growth_global_0"] = "1000"
    s1["fee_growth_global_1"] = "2000"
    conn = _fresh_store(tmp_path)
    steps = _run(conn, [s0, s1], episode="ep-onefg")
    assert steps[0].nav is None  # the step without fg still has no NAV
    assert episode_summary(steps)["steps_without_nav"] == 1
    conn.close()


def test_window_is_most_recent_n(tmp_path):
    conn = _fresh_store(tmp_path)
    for i in range(300):
        _insert_state(conn, i)
    samples, skipped = load_samples_from_db(conn, pool="poolX", limit=200)
    assert skipped == 0 and len(samples) == 200
    assert samples[0]["sample_time"] == _ts(100)  # most recent 200 of 300
    assert samples[-1]["sample_time"] == _ts(299)
    conn.close()


def test_return_order_ascending_time(tmp_path):
    conn = _fresh_store(tmp_path)
    _insert_state(conn, 2)
    _insert_state(conn, 0)
    _insert_state(conn, 1)
    samples, _ = load_samples_from_db(conn, pool="poolX", limit=10)
    assert [s["sample_time"] for s in samples] == [_ts(0), _ts(1), _ts(2)]
    conn.close()


def test_source_event_time_key_present_and_correct(tmp_path):
    conn = _fresh_store(tmp_path)
    _insert_state(conn, 0, source_event_time="2026-01-01T00:00:07Z")
    samples, _ = load_samples_from_db(conn, pool="poolX", limit=10)
    s = samples[0]
    assert "source_event_time" in s
    assert s["source_event_time"] == "2026-01-01T00:00:07Z"
    conn.close()


def test_session_key_unchanged(tmp_path):
    conn = _fresh_store(tmp_path)
    _insert_state(conn, 0, session="sess-42")
    samples, _ = load_samples_from_db(conn, pool="poolX", limit=10)
    assert samples[0]["session"] == "sess-42"
    conn.close()


def test_reference_age_secs_key_unchanged(tmp_path):
    conn = _fresh_store(tmp_path)
    _insert_state(conn, 0, age=123)
    samples, _ = load_samples_from_db(conn, pool="poolX", limit=10)
    assert samples[0]["reference_age_secs"] == 123
    conn.close()


def test_oracle_paused_key_unchanged(tmp_path):
    conn = _fresh_store(tmp_path)
    _insert_state(conn, 0, paused=1)
    samples, _ = load_samples_from_db(conn, pool="poolX", limit=10)
    assert samples[0]["oracle_paused"] == 1
    conn.close()


def test_source_payload_hash_key_unchanged(tmp_path):
    conn = _fresh_store(tmp_path)
    _insert_state(conn, 0, payload="deadbeef")
    samples, _ = load_samples_from_db(conn, pool="poolX", limit=10)
    assert samples[0]["source_payload_hash"] == "deadbeef"
    conn.close()


def test_null_mid_still_skipped_and_counted(tmp_path):
    conn = _fresh_store(tmp_path)
    _insert_state(conn, 0, mid="1.5")
    _insert_state(conn, 1, mid=None)
    _insert_state(conn, 2, mid="2.5")
    samples, skipped = load_samples_from_db(conn, pool="poolX", limit=10)
    assert skipped == 1
    assert [s["reference_mid"] for s in samples] == [Decimal("1.5"), Decimal("2.5")]
    conn.close()
