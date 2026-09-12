import os
import pytest
import sqlite3
from scripts.lp_rh_store_v1_readonly import open_store, migrate
from scripts.lp_rh_tx_intents_writer_v1 import (
    TxIntentWriter,
    DryRunViolation,
    STATE_PROPOSED,
    STATE_SIMULATED_OK,
    STATE_WHITELIST_REJECTED,
    STATE_SUBMITTED,
    STATE_CONFIRMED,
)

SAMPLE_POLICY_HASH = "0x1111111111111111111111111111111111111111111111111111111111111111"
SAMPLE_CALLDATA_HASH = "0x2222222222222222222222222222222222222222222222222222222222222222"
SAMPLE_EXPIRES = "2026-09-15T00:00:00Z"


@pytest.fixture
def store(tmp_path):
    conn = open_store(tmp_path / "test.db")
    migrate(conn)
    yield conn
    conn.close()


def _write_sample_intent(writer, req_id="req-1", idemp_key="idemp-1", **kwargs):
    params = {
        "request_id": req_id,
        "idempotency_key": idemp_key,
        "chain_id": 8453,
        "wallet_id": "0xWalleT1",
        "position_id": "pos-1",
        "intent_type": "MINT_POSITION",
        "target_address": "0xPooL1",
        "recipient_address": "0xRecipienT1",
        "selector": "0x12345678",
        "calldata_hash": SAMPLE_CALLDATA_HASH,
        "policy_hash": SAMPLE_POLICY_HASH,
        "expires_at": SAMPLE_EXPIRES,
    }
    params.update(kwargs)
    return writer.write_intent(**params)


def test_dry_run_default_blocks_submitted_state(store, monkeypatch):
    monkeypatch.delenv("LPBOT_TX_DRY_RUN", raising=False)
    writer = TxIntentWriter(store, dry_run=True)
    _write_sample_intent(writer, req_id="req-sub")
    with pytest.raises(DryRunViolation):
        writer.update_state("req-sub", STATE_SUBMITTED)


def test_dry_run_default_blocks_confirmed_state(store, monkeypatch):
    monkeypatch.delenv("LPBOT_TX_DRY_RUN", raising=False)
    writer = TxIntentWriter(store, dry_run=True)
    _write_sample_intent(writer, req_id="req-conf")
    with pytest.raises(DryRunViolation):
        writer.update_state("req-conf", STATE_CONFIRMED)


def test_dry_run_env_false_allows_submitted(store, monkeypatch):
    monkeypatch.setenv("LPBOT_TX_DRY_RUN", "false")
    writer = TxIntentWriter(store, dry_run=False)
    _write_sample_intent(writer, req_id="req-live")
    writer.update_state("req-live", STATE_SUBMITTED, tx_hash="0xabc123")
    intent = writer.get_intent("req-live")
    assert intent is not None
    assert intent["state"] == STATE_SUBMITTED
    assert intent["tx_hash"] == "0xabc123"


def test_idempotent_write_returns_existing(store):
    writer = TxIntentWriter(store)
    r1 = _write_sample_intent(writer, req_id="req-idemp-1", idemp_key="same-key")
    assert r1["idempotent_hit"] is False
    assert r1["request_id"] == "req-idemp-1"

    r2 = _write_sample_intent(writer, req_id="req-idemp-2", idemp_key="same-key")
    assert r2["idempotent_hit"] is True
    assert r2["request_id"] == "req-idemp-1"

    cur = store.execute("SELECT COUNT(*) FROM rh_tx_intents WHERE idempotency_key = 'same-key'")
    assert cur.fetchone()[0] == 1


def test_state_machine_proposed_to_simulated_ok(store):
    writer = TxIntentWriter(store)
    r = _write_sample_intent(writer, req_id="req-sm")
    assert r["state"] == STATE_PROPOSED

    writer.update_state("req-sm", STATE_SIMULATED_OK, simulated_at="2026-09-12T17:00:00Z")
    intent = writer.get_intent("req-sm")
    assert intent is not None
    assert intent["state"] == STATE_SIMULATED_OK
    assert intent["simulated_at"] == "2026-09-12T17:00:00Z"


def test_state_machine_to_whitelist_rejected(store):
    writer = TxIntentWriter(store)
    _write_sample_intent(writer, req_id="req-wl")
    reason = "target 0xdeadbeef not in whitelist"
    writer.update_state("req-wl", STATE_WHITELIST_REJECTED, reject_reason=reason)

    intent = writer.get_intent("req-wl")
    assert intent is not None
    assert intent["state"] == STATE_WHITELIST_REJECTED
    assert intent["reject_reason"] == reason


def test_dry_run_does_not_set_tx_hash_columns(store, monkeypatch):
    monkeypatch.delenv("LPBOT_TX_DRY_RUN", raising=False)
    writer = TxIntentWriter(store, dry_run=True)
    _write_sample_intent(writer, req_id="req-dry")
    writer.update_state("req-dry", STATE_SIMULATED_OK)

    intent = writer.get_intent("req-dry")
    assert intent is not None
    assert intent["tx_hash"] is None
    assert intent["submitted_at"] is None
    assert intent["confirmed_at"] is None
    assert intent["broadcaster_signature"] is None


def test_schema_columns_present(store):
    cols = {r[1] for r in store.execute("PRAGMA table_info(rh_tx_intents)").fetchall()}
    expected_new = [
        "intent_type",
        "target_address",
        "recipient_address",
        "selector",
        "value_wei",
        "reject_reason",
        "tx_hash",
        "submitted_at",
        "confirmed_at",
        "broadcaster_signature",
        "simulated_at",
        "live_block_number",
    ]
    for col in expected_new:
        assert col in cols, f"Missing column: {col}"


def test_value_wei_default_zero(store):
    writer = TxIntentWriter(store)
    _write_sample_intent(writer, req_id="req-val")
    intent = writer.get_intent("req-val")
    assert intent is not None
    assert intent["value_wei"] == "0"
