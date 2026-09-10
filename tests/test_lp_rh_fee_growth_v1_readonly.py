"""Tests for RH-02ac: feeGrowthGlobal0/1X128 collected as uint256 decimal TEXT.

The collector now reads the two feeGrowth selectors per round and writes them
to rh_market_states as decimal TEXT (None when not asked, never 0).  run_episode
reads these columns to compute NAV; without them every step lacks NAV.  All
tests use tmp_path scratch stores and a fake rpc_fn; no network."""
import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

from scripts.lp_rh_store_v1_readonly import insert_row, migrate, open_store
from scripts.lp_rh_collector_v1_readonly import (
    SEL_BALANCE_OF, SEL_FEE_GROWTH_0, SEL_FEE_GROWTH_1, SEL_LIQUIDITY,
    SEL_SLOT0, collect_round,
)
from scripts.lp_rh_shadow_runner_v1_readonly import episode_summary, run_episode

MEASURED = "45250119888616697086558471479183978286028"
BLOCK_HASH = "0x" + "ab" * 32
BLOCK = {"number": "0x10", "hash": BLOCK_HASH,
         "timestamp": "0x64b00000", "baseFeePerGas": "0x3b9aca00"}
SLOT0 = "0x" + "0" * 39 + "1" + "0" * 24  # sqrtPriceX96 = 2**96
LIQ = "0x" + "01" * 32
BAL = "0x" + "02" * 32
POSITION_USD = Decimal("1000")
CAPITAL_USD = Decimal("10000")
HORIZON_HOURS = 8760


def make_rpc(fg0=("0x" + "01" * 32, None), fg1=("0x" + "02" * 32, None)):
    def rpc_fn(method, params=None, **kwargs):
        if method == "eth_getBlockByNumber":
            return dict(BLOCK), None, 5
        if method == "eth_call":
            data = params[0]["data"]
            if data == SEL_FEE_GROWTH_0:
                return fg0[0], fg0[1], 5
            if data == SEL_FEE_GROWTH_1:
                return fg1[0], fg1[1], 5
            if data == SEL_SLOT0:
                return SLOT0, None, 5
            if data == SEL_LIQUIDITY:
                return LIQ, None, 5
            if data.startswith(SEL_BALANCE_OF):
                return BAL, None, 5
            return "0x12", None, 5
        return None, {"unexpected": method}, 5
    return rpc_fn


def _run_round(tmp_path, rpc):
    conn = open_store(tmp_path / "c.db")
    migrate(conn)
    collect_round(conn, dec0=18, dec1=6, last_good_block=None, rpc_fn=rpc)
    row = conn.execute(
        "SELECT fee_growth_global_0, fee_growth_global_1, derived_block_hash,"
        " session, source_event_time, reference_mid FROM rh_market_states"
    ).fetchone()
    conn.close()
    return row


def _store_row(tmp_path, **cols):
    conn = open_store(tmp_path / "s.db")
    migrate(conn)
    base = {"asset_address": "0xpool", "sample_time": "2026-09-09T15:00:00Z",
            "chain_id": 4663, "session": "RTH", "health_flags_json": "[]"}
    base.update(cols)
    insert_row(conn, "rh_market_states", base)
    conn.commit()
    return conn


def test_write_read_uint256_char_equal_str(tmp_path):
    conn = _store_row(tmp_path, fee_growth_global_0=MEASURED)
    val = conn.execute("SELECT fee_growth_global_0 FROM rh_market_states").fetchone()[0]
    assert val == MEASURED
    assert isinstance(val, str)
    conn.close()


def test_decimal_roundtrip_exceeds_int64(tmp_path):
    conn = _store_row(tmp_path, fee_growth_global_0=MEASURED, fee_growth_global_1=MEASURED)
    v0 = conn.execute("SELECT fee_growth_global_0 FROM rh_market_states").fetchone()[0]
    v1 = conn.execute("SELECT fee_growth_global_1 FROM rh_market_states").fetchone()[0]
    assert Decimal(v0) == Decimal(MEASURED)
    assert Decimal(v1) == Decimal(MEASURED)
    assert int(MEASURED) > 2 ** 63
    conn.close()


def test_fee_growth0_error_is_none_not_zero(tmp_path):
    row = _run_round(tmp_path, make_rpc(fg0=(None, {"code": -32000, "message": "reverted"})))
    assert row[0] is None
    assert row[0] != "0"


def test_fee_growth_zero_value_written_as_zero(tmp_path):
    row = _run_round(tmp_path, make_rpc(fg0=("0x" + "0" * 64, None), fg1=("0x" + "0" * 64, None)))
    assert row[0] == "0"
    assert row[0] is not None
    assert row[1] == "0"
    assert row[1] is not None


def test_non_0x_prefix_is_none(tmp_path):
    row = _run_round(tmp_path, make_rpc(fg0=("deadbeef", None)))
    assert row[0] is None


def test_insufficient_length_is_none(tmp_path):
    row = _run_round(tmp_path, make_rpc(fg0=("0x", None)))
    assert row[0] is None


def test_one_success_one_failure_independent(tmp_path):
    row = _run_round(tmp_path, make_rpc(fg0=("0x" + "0" * 63 + "1", None),
                                        fg1=(None, {"code": -32000, "message": "reverted"})))
    assert row[0] == "1"
    assert row[1] is None


def test_migrate_adds_columns_preserves_rows(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE rh_market_states ("
        "asset_address TEXT NOT NULL, sample_time TEXT NOT NULL,"
        " chain_id INTEGER NOT NULL, source_payload_hash TEXT,"
        " session TEXT NOT NULL, health_flags_json TEXT NOT NULL,"
        " reference_bid TEXT, reference_ask TEXT, reference_mid TEXT,"
        " reference_age_secs INTEGER, multiplier_human TEXT,"
        " oracle_paused INTEGER, derived_block_hash TEXT,"
        " derived_block_number INTEGER, source_event_time TEXT,"
        " PRIMARY KEY (asset_address, sample_time))")
    for t in ("2026-09-01T00:00:00Z", "2026-09-01T00:01:00Z"):
        conn.execute("INSERT INTO rh_market_states"
                     " (asset_address, sample_time, chain_id, session, health_flags_json)"
                     " VALUES ('0xpool', ?, 4663, 'RTH', '[]')", (t,))
    conn.commit()
    conn.close()
    conn = open_store(db)
    migrate(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(rh_market_states)")}
    assert "fee_growth_global_0" in cols and "fee_growth_global_1" in cols
    rows = conn.execute("SELECT fee_growth_global_0, fee_growth_global_1"
                        " FROM rh_market_states ORDER BY sample_time").fetchall()
    assert len(rows) == 2
    assert all(r[0] is None and r[1] is None for r in rows)
    conn.close()


def test_migrate_idempotent(tmp_path):
    conn = open_store(tmp_path / "m.db")
    migrate(conn)
    migrate(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(rh_market_states)")}
    assert "fee_growth_global_0" in cols and "fee_growth_global_1" in cols
    conn.close()


def test_regression_derived_block_hash(tmp_path):
    assert _run_round(tmp_path, make_rpc())[2] == BLOCK_HASH


def test_regression_session(tmp_path):
    assert _run_round(tmp_path, make_rpc())[3] not in (None, "")


def test_regression_source_event_time(tmp_path):
    expected = datetime.fromtimestamp(int("0x64b00000", 16), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert _run_round(tmp_path, make_rpc())[4] == expected


def test_regression_reference_mid(tmp_path):
    assert _run_round(tmp_path, make_rpc())[5] is not None


def _replay_sample(idx, *, sample_time, source_event_time, **overrides):
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
        "source_event_time": source_event_time, "oracle_heartbeat_secs": 3600,
        "reference_age_secs": 10, "source_payload_hash": "abc123",
    }
    s.update(overrides)
    return s


def test_end_to_end_nav_computed(tmp_path):
    base = [_replay_sample(0, sample_time="2026-09-08T18:00:00Z",
                           source_event_time="2026-09-08T17:59:58Z"),
            _replay_sample(1, sample_time="2026-09-08T18:01:00Z",
                           source_event_time="2026-09-08T18:00:58Z")]
    # RH-02ai: the fee formula multiplies the position's liquidity, which is
    # derived from the pool's price/range/decimals, so a replay without
    # pool_meta can no longer produce a NAV.  The old formula only needed
    # position_usd, which is exactly the dimensional error that was fixed.
    kw = dict(position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
              capital_usd=CAPITAL_USD, target_mode="SHADOW_SCENARIO",
              now_fn=lambda: "2026-09-08T19:00:00Z",
              pool_meta={"input_price_usd": 2484.0, "range_pct": 10.0,
                         "quote_usd_per_token1": 1.0,
                         "dec0": 18, "dec1": 6},
              allow_bare_quote=True)
    # decision_id is keyed on candidate_key+target_mode, so the two runs need
    # separate stores (same samples would collide on rh_gate_decisions.decision_id).
    conn_no = open_store(tmp_path / "no.db")
    migrate(conn_no)
    steps_no = run_episode(conn_no, strategy_episode="ep-nofg", samples=base, **kw)
    assert episode_summary(steps_no)["steps_without_nav"] == 2
    conn_no.close()
    with_fg = []
    for i, s in enumerate(base):
        s2 = dict(s)
        s2["fee_growth_global_0"] = str(1000 + i)
        s2["fee_growth_global_1"] = str(2000 + i)
        # RH-02ai: each leg is converted to USD at the step's own price before
        # the two are summed, so a step without reference_mid fails closed.
        s2["reference_mid"] = "2484"
        with_fg.append(s2)
    conn_yes = open_store(tmp_path / "yes.db")
    migrate(conn_yes)
    steps_yes = run_episode(conn_yes, strategy_episode="ep-withfg", samples=with_fg, **kw)
    assert episode_summary(steps_yes)["steps_without_nav"] < 2
    assert all(s.nav is not None for s in steps_yes)
    conn_yes.close()
