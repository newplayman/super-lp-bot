# RH-07-0 defect 3 test: accrued_fee must guard on position_open.
# Entry point: _run_episode_persisted (daemon entry point).
# Direct assertion against SQLite database.
import json
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


def test_rh07_0_accrued_fee_zero_when_position_not_open(tmp_path):
    """RH-07-0 Defect 3: accrued_fee must require position_open to be True.

    When an episode cannot open a position (e.g. reservation denied due to bucket active cap exhaustion),
    the runner must not accrue fees even if step_in_range is True and fee growth increases.
    Marks written to rh_position_marks must record accrued_fee == 0 (not accumulating unearned fees),
    and unvalued_risk_json must include "accrued_accrual_basis": "position_open_v2".
    """
    ledger = open_store(tmp_path / "ledger.db")
    migrate(ledger)
    ep_id = "ep-fee-guard-test"

    # Fill the CORE active cap so try_reserve is denied and position_open stays False.
    # capital_usd = 10000 -> CORE cap = 10000 * 0.50 * 0.85 = 4250.
    insert_row(ledger, "rh_bucket_reservations", {
        "intent_id": "pre-existing-cap-fill",
        "policy_version": POLICY_ID,
        "bucket": "CORE",
        "amount_usd": "4250",
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
    marks = ledger.execute(
        "SELECT accrued_fee, unvalued_risk_json FROM rh_position_marks WHERE position_id = ? ORDER BY mark_time",
        (f"rh-shadow-{ep_id}",),
    ).fetchall()
    ledger.close()

    assert len(marks) == 2, f"Expected 2 marks, got {len(marks)}"
    for accrued_fee, risk_json in marks:
        # Without position_open guard, accrued_fee on step 2 would accumulate unearned fee (> 0).
        assert Decimal(str(accrued_fee)) == Decimal("0"), f"Expected accrued_fee == 0, got {accrued_fee}"
        risk = json.loads(risk_json)
        assert risk.get("accrued_accrual_basis") == "position_open_v2", (
            f"Expected accrued_accrual_basis 'position_open_v2', got {risk.get('accrued_accrual_basis')}"
        )
