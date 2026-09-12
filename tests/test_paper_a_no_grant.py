import json
import pytest
import sqlite3
from decimal import Decimal
from pathlib import Path

from scripts.lp_rh_shadow_daemon_v1_readonly import _run_episode_persisted
from scripts.lp_rh_store_v1_readonly import open_store, migrate
from scripts.lp_rh_tx_intents_writer_v1 import TxIntentWriter, DryRunViolation

NOW = "2026-09-08T18:00:00Z"
POOL = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"


def _rejected_sample(idx: int, sample_time: str) -> dict:
    return {
        "candidate_key": f"{POOL}-{idx}",
        "sample_time": sample_time,
        "chain_id": 8453,
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
        "position_open": False,
        "legacy_required_conjunction": False,
        "identity_verified": True,
        "protocol_capabilities_sufficient": True,
        "data_complete_and_fresh": True,
        "profile_policy_pass": False,
        "market_and_chain_risk_pass": False,
        "absolute_profit_pass": False,
        "position_and_exit_depth_pass": False,
        "capital_policy_pass": False,
        "reference_mid": Decimal("2000"),
        "fee_growth_global_0": 1000000000000 + idx * 1000000000000,
        "fee_growth_global_1": 2000000000000 + idx * 2000000000000,
        "reference_age_secs": 5,
        "source_event_time": "2026-09-08T17:59:55Z",
        "source_payload_hash": f"hash-paper-a-{idx}",
    }


def test_paper_a_no_grant_dry_run_invariants(tmp_path):
    ledger = open_store(tmp_path / "ledger.db")
    migrate(ledger)
    ep_id = "ep-paper-a-no-grant"

    pool_meta = {
        "pool_address": POOL,
        "token0": "0xtoken0",
        "token1": "0xtoken1",
        "dec0": 18,
        "dec1": 6,
        "range_pct": Decimal("5.0"),
        "as_of": NOW,
        "attestation_status": "ATTESTED_SAME_BLOCK",
        "quote_usd_per_token1": {
            "value": "1.0",
            "source": "coingecko:test",
            "observed_at": NOW,
            "ttl_secs": 86400,
        },
    }

    cfg = {
        "live_db": str(tmp_path / "live.db"),
        "pool": POOL,
        "samples": 3,
        "position_usd": Decimal("1000"),
        "capital_usd": Decimal("10000"),
        "horizon_hours": 24,
        "target_mode": "SHADOW_SCENARIO",
        "pool_meta": pool_meta,
        "pool_meta_hash": "h",
        "ledger_db": str(tmp_path / "ledger.db"),
    }

    sample_list = [
        _rejected_sample(0, "2026-09-08T18:00:00Z"),
        _rejected_sample(1, "2026-09-08T18:01:00Z"),
        _rejected_sample(2, "2026-09-08T18:02:00Z"),
    ]

    steps, dups, stats = _run_episode_persisted(
        ledger,
        cfg=cfg,
        episode_id=ep_id,
        sample_list=sample_list,
        now_fn=lambda: NOW,
    )

    # 1. rh_tx_intents has zero rows for this episode (no grant -> no intent to propose)
    intents_count = ledger.execute(
        "SELECT COUNT(*) FROM rh_tx_intents WHERE position_id LIKE ?",
        (f"%{ep_id}%",),
    ).fetchone()[0]
    assert intents_count == 0, f"Expected 0 rh_tx_intents rows, found {intents_count}"

    total_intents = ledger.execute("SELECT COUNT(*) FROM rh_tx_intents").fetchone()[0]
    assert total_intents == 0

    # 2. rh_position_marks has no virtual LP row (cash valuation, position not open)
    marks = ledger.execute(
        "SELECT accrued_fee, reference_nav, liquidation_nav, unvalued_risk_json FROM rh_position_marks WHERE position_id = ?",
        (f"rh-shadow-{ep_id}",),
    ).fetchall()
    assert len(marks) == 3
    for accrued_fee, ref_nav, liq_nav, risk_json in marks:
        assert Decimal(str(accrued_fee)) == Decimal("0")
        assert Decimal(str(ref_nav)) == Decimal("10000")
        assert Decimal(str(liq_nav)) == Decimal("10000")
        risk = json.loads(risk_json)
        assert risk.get("position_open") is False
        assert risk.get("liquidation_nav_reason") == "POSITION_NOT_OPEN:CASH_VALUATION"

    virtual_positions = ledger.execute(
        "SELECT COUNT(*) FROM rh_shadow_positions WHERE strategy_episode = ?",
        (ep_id,),
    ).fetchone()[0]
    assert virtual_positions == 0

    # 3. rh_journal has no fee-event row
    journal_ep_count = ledger.execute(
        "SELECT COUNT(*) FROM rh_journal WHERE ref_json LIKE ?",
        (f"%{ep_id}%",),
    ).fetchone()[0]
    assert journal_ep_count == 0

    # 4. rh_bucket_reservations count for this episode == 0 (no leak)
    resv_count = ledger.execute(
        "SELECT COUNT(*) FROM rh_bucket_reservations WHERE intent_id LIKE ?",
        (f"%{ep_id}%",),
    ).fetchone()[0]
    assert resv_count == 0

    # 5. rh_journal total count == 0
    assert ledger.execute("SELECT COUNT(*) FROM rh_journal").fetchone()[0] == 0

    # 6. TxIntentWriter(ledger, dry_run=True) refuses SUBMITTED state
    writer = TxIntentWriter(ledger, dry_run=True)
    with pytest.raises(DryRunViolation):
        writer.update_state("nonexistent_id", "SUBMITTED")

    ledger.close()
