import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal

from scripts.lp_rh_shadow_runner_v1_readonly import (
    compute_conjuncts, load_samples_from_db)
from scripts.lp_rh_store_v1_readonly import migrate
from scripts.lp_rh_registry_v1_readonly import RH_CHAIN_ID
from scripts.lp_rh_market_session_v1_readonly import evaluate_health

# RTH: 2026-09-09 (Wed) 15:00 UTC = 11:00 EDT, inside 09:30-16:00.
RTH_NOW = "2026-09-09T15:00:00Z"
# OVERNIGHT: 2026-09-08 (Tue) 02:00 UTC = Mon 22:00 EDT, >= 20:00.
OVERNIGHT_NOW = "2026-09-08T02:00:00Z"
# WEEKEND: 2026-09-05 (Sat) 15:00 UTC.
WEEKEND_NOW = "2026-09-05T15:00:00Z"


def _dt(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fresh(now_iso, secs=3):
    return _iso(_dt(now_iso) - timedelta(seconds=secs))


def make_sample(now_iso=RTH_NOW, *, source_event_time=None,
                reference_age_secs=60, reference_mid=Decimal("3000.5"),
                **extra):
    base = {
        "asset_address": "0xPOOL", "sample_time": now_iso,
        "chain_id": RH_CHAIN_ID, "reference_mid": reference_mid,
        "multiplier_human": "1.0", "session": "RTH",
        "health_flags_json": "[]", "reference_age_secs": reference_age_secs,
        "oracle_paused": 0, "source_payload_hash": "0xhash",
        "source_event_time": source_event_time,
        "reference_bid": "3000.0", "reference_ask": "3001.0",
    }
    base.update(extra)
    return base


def gate(sample, now_iso=RTH_NOW):
    bits, _ = compute_conjuncts(sample, {}, pool_meta=None,
                                capital_usd=Decimal("10000"),
                                position_usd=Decimal("1000"), now=now_iso)
    return bits


def gate_flags(sample, now_iso):
    # Mirror the gate's evaluate_health call exactly (CORE bucket wiring).
    return evaluate_health(
        oracle_paused=bool(sample.get("oracle_paused")),
        oracle_updated_at=sample.get("source_event_time"),
        api_generated_at=sample.get("source_event_time"),
        now=_dt(now_iso),
        halt=bool(sample.get("halt")),
        corp_action_pending=bool(sample.get("corp_action_pending")),
        sources_disagree=bool(sample.get("sources_disagree")),
        chain_degraded=bool(sample.get("chain_degraded")),
        oracle_heartbeat_secs=sample.get("oracle_heartbeat_secs") or 3600,
        api_stale_secs=sample.get("reference_age_secs"))


def make_db():
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    return conn


def insert_state(conn, *, asset="0xPOOL", sample_time=RTH_NOW,
                  chain_id=RH_CHAIN_ID, reference_mid="3000.5",
                  multiplier_human="1.0", session="RTH",
                  health_flags_json="[]", reference_age_secs=60,
                  oracle_paused=0, source_payload_hash="0xhash",
                  reference_bid="3000.0", reference_ask="3001.0",
                  source_event_time="2026-09-09T14:59:57Z"):
    conn.execute(
        "INSERT INTO rh_market_states (asset_address, sample_time, chain_id, "
        "reference_mid, multiplier_human, session, health_flags_json, "
        "reference_age_secs, oracle_paused, source_payload_hash, "
        "reference_bid, reference_ask, source_event_time) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (asset, sample_time, chain_id, reference_mid, multiplier_human,
         session, health_flags_json, reference_age_secs, oracle_paused,
         source_payload_hash, reference_bid, reference_ask,
         source_event_time))
    conn.commit()


# --- Gate: market_and_chain_risk_pass (CORE bucket, block timestamp) --------

def test_fresh_sample_rth_gate_passes():
    s = make_sample(source_event_time=_fresh(RTH_NOW, 3))
    assert gate(s, RTH_NOW)["market_and_chain_risk_pass"] is True
    flags = gate_flags(s, RTH_NOW)
    assert "API_STALE" not in flags
    assert "ORACLE_UNAVAILABLE" not in flags


def test_none_source_event_time_fails_closed():
    s = make_sample(source_event_time=None)
    assert gate(s, RTH_NOW)["market_and_chain_risk_pass"] is False
    flags = gate_flags(s, RTH_NOW)
    assert "ORACLE_UNAVAILABLE" in flags
    assert "API_STALE" in flags


def test_stale_source_event_time_fails():
    s = make_sample(source_event_time=_fresh(RTH_NOW, 600))
    assert gate(s, RTH_NOW)["market_and_chain_risk_pass"] is False
    flags = gate_flags(s, RTH_NOW)
    assert "ORACLE_STALE" in flags or "API_STALE" in flags


def test_overnight_fresh_still_false():
    s = make_sample(now_iso=OVERNIGHT_NOW,
                    source_event_time=_fresh(OVERNIGHT_NOW, 3))
    assert gate(s, OVERNIGHT_NOW)["market_and_chain_risk_pass"] is False


def test_weekend_fresh_still_false():
    s = make_sample(now_iso=WEEKEND_NOW,
                    source_event_time=_fresh(WEEKEND_NOW, 3))
    assert gate(s, WEEKEND_NOW)["market_and_chain_risk_pass"] is False


def test_halt_fresh_rth_still_false():
    s = make_sample(source_event_time=_fresh(RTH_NOW, 3), halt=True)
    assert gate(s, RTH_NOW)["market_and_chain_risk_pass"] is False


def test_oracle_paused_fresh_rth_still_false():
    s = make_sample(source_event_time=_fresh(RTH_NOW, 3), oracle_paused=1)
    assert gate(s, RTH_NOW)["market_and_chain_risk_pass"] is False


def test_sources_disagree_still_false():
    s = make_sample(source_event_time=_fresh(RTH_NOW, 3),
                    sources_disagree=True)
    assert gate(s, RTH_NOW)["market_and_chain_risk_pass"] is False


# --- load_samples_from_db: source_event_time wiring -------------------------

def test_load_sample_has_source_event_time_key():
    conn = make_db()
    insert_state(conn, source_event_time="2026-09-09T14:59:57Z")
    samples, skipped = load_samples_from_db(conn, pool="0xPOOL", limit=10)
    assert skipped == 0 and len(samples) == 1
    assert samples[0]["source_event_time"] == "2026-09-09T14:59:57Z"


def test_old_row_null_source_event_time_reads_none():
    conn = make_db()
    insert_state(conn, source_event_time=None)
    samples, skipped = load_samples_from_db(conn, pool="0xPOOL", limit=10)
    assert skipped == 0
    assert samples[0]["source_event_time"] is None


def test_null_reference_mid_skipped_and_counted():
    conn = make_db()
    insert_state(conn, reference_mid=None)
    insert_state(conn, sample_time="2026-09-09T15:01:00Z")
    samples, skipped = load_samples_from_db(conn, pool="0xPOOL", limit=10)
    assert skipped == 1 and len(samples) == 1


def test_reference_mid_is_decimal():
    conn = make_db()
    insert_state(conn, reference_mid="3000.5")
    samples, _ = load_samples_from_db(conn, pool="0xPOOL", limit=10)
    assert isinstance(samples[0]["reference_mid"], Decimal)
    assert samples[0]["reference_mid"] == Decimal("3000.5")


def test_session_key_present_unchanged():
    conn = make_db()
    insert_state(conn, session="RTH")
    samples, _ = load_samples_from_db(conn, pool="0xPOOL", limit=10)
    assert samples[0]["session"] == "RTH"


def test_reference_age_secs_key_present_unchanged():
    conn = make_db()
    insert_state(conn, reference_age_secs=42)
    samples, _ = load_samples_from_db(conn, pool="0xPOOL", limit=10)
    assert samples[0]["reference_age_secs"] == 42


def test_oracle_paused_key_present_unchanged():
    conn = make_db()
    insert_state(conn, oracle_paused=1)
    samples, _ = load_samples_from_db(conn, pool="0xPOOL", limit=10)
    assert samples[0]["oracle_paused"] == 1


def test_source_payload_hash_key_present_unchanged():
    conn = make_db()
    insert_state(conn, source_payload_hash="0xdeadbeef")
    samples, _ = load_samples_from_db(conn, pool="0xPOOL", limit=10)
    assert samples[0]["source_payload_hash"] == "0xdeadbeef"


# --- data_complete_and_fresh regression -------------------------------------

def test_data_complete_fails_when_mid_none():
    s = make_sample(reference_mid=None)
    assert gate(s, RTH_NOW)["data_complete_and_fresh"] is False


def test_data_complete_fails_when_age_over_limit():
    s = make_sample(reference_age_secs=300)  # > REFERENCE_MAX_AGE_SECS (120)
    assert gate(s, RTH_NOW)["data_complete_and_fresh"] is False
