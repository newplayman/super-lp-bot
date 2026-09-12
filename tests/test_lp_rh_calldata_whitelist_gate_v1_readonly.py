"""E2E tests for calldata whitelist gate wired into shadow daemon (W2)."""
from decimal import Decimal
from pathlib import Path
import pytest

from scripts.lp_rh_shadow_daemon_v1_readonly import _run_episode_persisted
from scripts.lp_rh_store_v1_readonly import open_store, migrate
from tests.test_rh07_fix_c_r2_01_full_cost_wired import _cost_sample
from tests.test_lp_rh_shadow_runner_v1_readonly import _conj_meta

NOW = "2026-09-08T18:00:00Z"
LEGAL_ROUTER = "0xF87912FeFD79b1dEe6561C3d38e9EB4F3F77D7e2"
EVIL_TARGET = "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"


def _build_test_setup(tmp_path, pool_address):
    ledger = open_store(tmp_path / "ledger.db")
    migrate(ledger)
    pm = _conj_meta(
        as_of="2026-09-08T17:59:55Z",
        range_pct="10.0",
        dec0=18,
        dec1=6,
        pool_address=pool_address,
        quote_usd_per_token1={
            "value": "1.0",
            "source": "COINGECKO_API",
            "observed_at": "2026-09-08T17:59:55Z",
            "ttl_secs": 86400,
        },
    )
    cfg = {
        "live_db": str(tmp_path / "live.db"),
        "pool": pool_address,
        "samples": 1,
        "position_usd": Decimal("1000"),
        "capital_usd": Decimal("10000"),
        "horizon_hours": 24,
        "target_mode": "SHADOW_SCENARIO",
        "pool_meta": pm,
        "pool_meta_hash": "h",
        "ledger_db": str(tmp_path / "ledger.db"),
    }
    return ledger, cfg


def test_case_1_legal_target_passes_gate(tmp_path):
    """Case 1: legal target_address in sample -> assert rh_tx_intents.state == 'SIMULATED_OK' after run."""
    ledger, cfg = _build_test_setup(tmp_path, LEGAL_ROUTER)
    ep_id = "ep-w2-case1"
    sample = _cost_sample(0, price=Decimal("2000.0"))
    sample["target_address"] = LEGAL_ROUTER.lower()
    sample["selector"] = "0xb95cac29"

    steps, dups, stats = _run_episode_persisted(
        ledger,
        cfg=cfg,
        episode_id=ep_id,
        sample_list=[sample],
        now_fn=lambda: NOW,
    )

    row = ledger.execute(
        "SELECT state, reject_reason FROM rh_tx_intents WHERE position_id = ?",
        (f"rh-shadow-{ep_id}-0",),
    ).fetchone()
    ledger.close()

    assert row is not None, "Expected rh_tx_intents row"
    assert row[0] == "SIMULATED_OK"
    assert row[1] is None


def test_case_2_evil_target_rejected_by_gate(tmp_path):
    """Case 2: evil target_address injected via sample -> assert rh_tx_intents.state == 'WHITELIST_REJECTED' + reject_reason non-empty + rh_journal count == 0 + rh_bucket_reservations count == 0."""
    ledger, cfg = _build_test_setup(tmp_path, LEGAL_ROUTER)
    ep_id = "ep-w2-case2"
    sample = _cost_sample(0, price=Decimal("2000.0"))
    sample["target_address"] = EVIL_TARGET
    sample["selector"] = "0xb95cac29"

    steps, dups, stats = _run_episode_persisted(
        ledger,
        cfg=cfg,
        episode_id=ep_id,
        sample_list=[sample],
        now_fn=lambda: NOW,
    )

    row = ledger.execute(
        "SELECT state, reject_reason FROM rh_tx_intents WHERE position_id = ?",
        (f"rh-shadow-{ep_id}-0",),
    ).fetchone()
    journal_count = ledger.execute(
        "SELECT COUNT(*) FROM rh_journal WHERE ref_json LIKE ?",
        (f"%{ep_id}%",),
    ).fetchone()[0]
    resv_count = ledger.execute(
        "SELECT COUNT(*) FROM rh_bucket_reservations WHERE intent_id LIKE ?",
        (f"%{ep_id}%",),
    ).fetchone()[0]
    ledger.close()

    assert row is not None, "Expected rh_tx_intents row"
    assert row[0] == "WHITELIST_REJECTED"
    assert row[1] is not None and len(row[1]) > 0
    assert journal_count == 0
    assert resv_count == 0


def test_case_3_empty_target_rejected_with_target_in_reason(tmp_path):
    """Case 3: empty target_address (None) -> must produce state='WHITELIST_REJECTED' with reason containing 'target'."""
    ledger, cfg = _build_test_setup(tmp_path, LEGAL_ROUTER)
    ep_id = "ep-w2-case3"
    sample = _cost_sample(0, price=Decimal("2000.0"))
    sample["target_address"] = None
    sample["selector"] = "0xb95cac29"

    steps, dups, stats = _run_episode_persisted(
        ledger,
        cfg=cfg,
        episode_id=ep_id,
        sample_list=[sample],
        now_fn=lambda: NOW,
    )

    row = ledger.execute(
        "SELECT state, reject_reason FROM rh_tx_intents WHERE position_id = ?",
        (f"rh-shadow-{ep_id}-0",),
    ).fetchone()
    ledger.close()

    assert row is not None, "Expected rh_tx_intents row"
    assert row[0] == "WHITELIST_REJECTED"
    assert row[1] is not None and "target" in row[1].lower()
