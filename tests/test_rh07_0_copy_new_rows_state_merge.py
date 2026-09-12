# RH-07-0 defect 2 test: _copy_new_rows state merge for rh_bucket_reservations.
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
        # R3 / Package C conjunct fields
        "reference_age_secs": 5,
        "source_event_time": "2026-09-08T17:59:55Z",
        "source_payload_hash": f"hash-rh07-0-merge-{idx}",
    }


def test_rh07_0_copy_new_rows_merges_released_reservation(tmp_path):
    """RH-07-0 Defect 2: _copy_new_rows must merge status on rh_bucket_reservations.

    When an episode is re-run via scratch (e.g. following an IntegrityError),
    scratch produces a RELEASED reservation row with released_at stamped.
    If _copy_new_rows merely skips existing primary keys, a pre-existing PENDING
    row in ledger_conn is never updated, leaving room permanently occupied and
    exhausting the bucket active cap.

    With state merge, _copy_new_rows updates PENDING to RELEASED and carries
    over released_at.
    """
    ledger = open_store(tmp_path / "ledger.db")
    migrate(ledger)
    ep_id = "ep-merge-test"
    intent_id = f"rh-shadow-{ep_id}-0"

    # Pre-existing PENDING reservation in ledger (the leaked reservation)
    insert_row(ledger, "rh_bucket_reservations", {
        "intent_id": intent_id,
        "policy_version": POLICY_ID,
        "bucket": "CORE",
        "amount_usd": "1000",
        "status": "PENDING",
        "created_at": NOW,
        "released_at": None,
    })
    ledger.commit()

    pool_meta = {
        "pool_address": POOL,
        "token0": "0xtoken0",
        "token1": "0xtoken1",
        "dec0": 18,
        "dec1": 6,
        "range_pct": Decimal("5.0"),
        # R3 / Package D: pool_meta must carry as_of for the conjunct
        # gate to allow the sample.
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

    # Run persisted episode via daemon entry point:
    # First attempt on ledger hits IntegrityError because intent_id already exists in ledger.
    # Rollback path replays on scratch (excluding intent_id from scratch sync),
    # where intent_id is granted and then released.
    # _copy_new_rows copies scratch results back to ledger.
    steps, dups, stats = _run_episode_persisted(
        ledger, cfg=cfg, episode_id=ep_id, sample_list=[s0, s1], now_fn=lambda: NOW,
    )

    # Directly verify against SQLite database:
    row = ledger.execute(
        "SELECT status, released_at FROM rh_bucket_reservations WHERE intent_id = ?",
        (intent_id,),
    ).fetchone()
    ledger.close()

    assert row is not None
    assert row[0] == "RELEASED", f"Expected RELEASED status, got {row[0]}"
    assert row[1] is not None, "Expected non-null released_at timestamp"
    assert stats["rh_bucket_reservations"]["copied"] >= 1
