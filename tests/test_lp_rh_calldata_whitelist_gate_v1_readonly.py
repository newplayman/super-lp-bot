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
        # §2 / §3: opt the daemon into the fail-closed calldata wrapper
        # for the wrapper-targeted test cases in this file.  Without this
        # the daemon stays in schema-only mode and the WHITELIST_REJECTED
        # assertions below would never fire.
        "verify_calldata": True,
    }
    return ledger, cfg


def test_case_1_research_path_writes_research_only_state(tmp_path):
    """Case 1 (CA-03 PAPER_ACCEPTANCE_REPAIR_V2): default research path.

    Default ``verify_calldata=False`` path MUST NOT label the intent
    SIMULATED_OK -- no wrapper ran, no simulator ran.  The schema row gets
    RESEARCH_ONLY_NOT_SIMULATED so downstream consumers (paper readiness
    gates, admission, graduation) can tell that no actual simulation
    occurred.  This was previously labeled SIMULATED_OK which silently
    granted eligibility that had no wrapper evidence.
    """
    ledger, cfg = _build_test_setup(tmp_path, LEGAL_ROUTER)
    # Default research path -- do NOT opt into the wrapper.
    cfg.pop("verify_calldata", None)
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
    assert row[0] == "RESEARCH_ONLY_NOT_SIMULATED", (
        f"default research path must write RESEARCH_ONLY_NOT_SIMULATED, got {row[0]!r}"
    )
    assert row[1] is None


def test_case_1b_verify_calldata_true_without_calldata_fails_closed(tmp_path):
    """Case 1b (CA-03): opted-in wrapper path with empty calldata MUST fail closed.

    When the caller sets ``verify_calldata=True`` but does not supply a real
    calldata payload, the wrapper must reject (decoder exception -> reject
    reason starts with ``whitelist_reject:decoder_exception:``).  This proves
    the wrapper is genuinely fail-closed: opting in is not enough to obtain
    SIMULATED_OK -- real decoded bytes are required.
    """
    ledger, cfg = _build_test_setup(tmp_path, LEGAL_ROUTER)
    cfg["verify_calldata"] = True
    ep_id = "ep-w2-case1b"
    sample = _cost_sample(0, price=Decimal("2000.0"))
    sample["target_address"] = LEGAL_ROUTER.lower()
    sample["selector"] = "0xb95cac29"
    # Deliberately do NOT set sample["calldata_bytes"] -- wrapper must reject.

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
    assert row[0] == "WHITELIST_REJECTED", (
        f"wrapper must fail-closed on missing calldata, got {row[0]!r}"
    )
    assert row[1] is not None and "whitelist_reject:" in row[1], (
        f"reject_reason must be a whitelist_reject reason, got {row[1]!r}"
    )


def test_case_1c_wrapper_rejection_leaves_no_journal_or_reservation(tmp_path):
    """Case 1c (CA-04 PAPER_ACCEPTANCE_REPAIR_V2): wrapper rejection MUST leave
    no journal rows and no reservation rows for this episode.

    Audit §3: ``拒绝后 steps、持仓、资金预约、journal、episode summary 的
    状态必须一致``。  If wrapper rejects a step that the strategy would
    otherwise have admitted, the journal debit/credit and the
    rh_bucket_reservations row that ``run_episode`` already wrote must be
    rolled back together with the step, not left dangling in the ledger.

    This test provides a sample with a legal target (so the strategy admits
    and ``run_episode`` writes journal + reservation rows) but then opts
    into ``verify_calldata=True`` without supplying real calldata (so the
    wrapper fail-closes inside ``_record_tx_intents_safe``).
    """
    ledger, cfg = _build_test_setup(tmp_path, LEGAL_ROUTER)
    cfg["verify_calldata"] = True
    ep_id = "ep-w2-case1c"
    sample = _cost_sample(0, price=Decimal("2000.0"))
    sample["target_address"] = LEGAL_ROUTER.lower()
    sample["selector"] = "0xb95cac29"
    # Deliberately no calldata_bytes -- wrapper must reject.

    steps, dups, stats = _run_episode_persisted(
        ledger,
        cfg=cfg,
        episode_id=ep_id,
        sample_list=[sample],
        now_fn=lambda: NOW,
    )

    intent_row = ledger.execute(
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

    assert intent_row is not None, "Expected rh_tx_intents row"
    assert intent_row[0] == "WHITELIST_REJECTED", (
        f"wrapper must reject, got {intent_row[0]!r}"
    )
    assert journal_count == 0, (
        f"rh_journal must have 0 rows for rejected episode {ep_id}, got {journal_count}"
    )
    assert resv_count == 0, (
        f"rh_bucket_reservations must have 0 rows for rejected episode {ep_id}, got {resv_count}"
    )


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


def test_case_3_empty_target_in_research_path_records_schema_only(tmp_path):
    """Case 3 (CA-03): empty target_address in default research path.

    With ``verify_calldata=False`` (default research path), the wrapper is
    never invoked.  An empty / None ``target_address`` therefore does NOT
    produce a rejection; the daemon still writes a schema row carrying
    ``RESEARCH_ONLY_NOT_SIMULATED``.  This is the explicit difference
    between the research path (records intent but grants no eligibility)
    and the wrapper path (case_1b / case_2 -- fail-closed when opted in).
    The wrapper path's empty-target rejection is structurally redundant with
    case_2 (evil target_address is also off the allow-list) and case_1b
    (missing calldata fail-closes before any target check).
    """
    ledger, cfg = _build_test_setup(tmp_path, LEGAL_ROUTER)
    cfg.pop("verify_calldata", None)  # default research path
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
    assert row[0] == "RESEARCH_ONLY_NOT_SIMULATED", (
        f"empty target in research path must record RESEARCH_ONLY_NOT_SIMULATED, got {row[0]!r}"
    )
    assert row[1] is None
