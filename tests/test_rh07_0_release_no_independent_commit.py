# RH-07-0 defect 1 test: release() must not commit independently.
# Entry point: _run_episode_persisted (daemon entry point).
# Direct assertion against SQLite database.
import pytest
from decimal import Decimal
from pathlib import Path
from scripts.lp_rh_store_v1_readonly import open_store, migrate, insert_row
from scripts.lp_rh_bucket_ledger_v1_readonly import POLICY_ID
from scripts.lp_rh_shadow_daemon_v1_readonly import _run_episode_persisted

NOW = "2026-09-08T18:00:00Z"
POOL = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"


def _sample(idx, sample_time):
    return {
        "candidate_key": f"{POOL}-{idx}",
        "sample_time": sample_time,
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
        "reference_mid": Decimal("1.0"),
        "fee_growth_global_0": 1000000000000 + idx * 1000000000000,
        "fee_growth_global_1": 2000000000000 + idx * 2000000000000,
    }


def test_rh07_0_release_does_not_commit_caller_transaction(tmp_path):
    """RH-07-0 Defect 1: release() must not issue an independent conn.commit().

    If release() issues conn.commit(), uncommitted state from the caller's transaction
    is prematurely committed to disk. If run_episode then encounters an IntegrityError
    (e.g. duplicate fee journal event on line 1426), ledger_conn.rollback() fails
    to roll back the prematurely committed state.

    With no independent commit in release(), ledger_conn.rollback() cleanly rolls back
    uncommitted state from the initial execution attempt.
    """
    ledger = open_store(tmp_path / "ledger.db")
    migrate(ledger)
    ep_id = "ep-release-test"

    # Pre-insert a journal event that will trigger an IntegrityError at line 1426 of
    # run_episode (after release() at line 1383 has been called).
    insert_row(ledger, "rh_journal", {
        "event_id": f"{ep_id}-fees",
        "idempotency_key": f"{ep_id}-fees",
        "account_debit": "LP_FEES_RECEIVABLE",
        "account_credit": "LP_FEE_INCOME",
        "asset": "0xtoken1",
        "amount_raw": "100",
        "is_external_flow": 0,
        "booked_at": NOW,
    })
    ledger.commit()

    # Place an uncommitted marker row into the active transaction on ledger.
    # If release() prematurely commits, this row will be permanently committed to disk.
    # If release() does not commit, ledger_conn.rollback() will discard it.
    uncommitted_intent = f"marker-uncommitted-{ep_id}"
    ledger.execute(
        "INSERT INTO rh_bucket_reservations "
        "(intent_id, policy_version, bucket, amount_usd, status, created_at, released_at) "
        "VALUES (?, ?, ?, ?, 'PENDING', ?, NULL)",
        (uncommitted_intent, POLICY_ID, "CORE", "500", NOW),
    )
    assert ledger.in_transaction

    pool_meta = {
        "pool_address": POOL,
        "token0": "0xtoken0",
        "token1": "0xtoken1",
        "dec0": 18,
        "dec1": 6,
        "range_pct": Decimal("5.0"),
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
        "samples": 2,
        "position_usd": Decimal("1000"),
        "capital_usd": Decimal("10000"),
        "horizon_hours": 24,
        "target_mode": "SHADOW_SCENARIO",
        "pool_meta": pool_meta,
        "pool_meta_hash": "h",
        "ledger_db": str(tmp_path / "ledger.db"),
    }
    s0 = _sample(0, "2026-09-08T18:00:00Z")
    s1 = _sample(1, "2026-09-08T18:01:00Z")

    steps, dups, stats = _run_episode_persisted(
        ledger, cfg=cfg, episode_id=ep_id, sample_list=[s0, s1], now_fn=lambda: NOW,
    )

    # Directly verify against SQLite database:
    # If release() committed, uncommitted_intent survived rollback -> count is 1 (FAIL).
    # If release() did not commit, uncommitted_intent was rolled back -> count is 0 (PASS).
    cnt = ledger.execute(
        "SELECT COUNT(*) FROM rh_bucket_reservations WHERE intent_id = ?",
        (uncommitted_intent,),
    ).fetchone()[0]
    ledger.close()

    assert cnt == 0, "Uncommitted state must be rolled back; release() must not commit caller transaction"
