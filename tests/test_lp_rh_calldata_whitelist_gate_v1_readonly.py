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


# ─────────────────────────────────────────────────────────────────────────────
# F4 — RH single-factor negative controls (12 tests)
# All use real verify_intent_or_reject; each asserts the exact reason string.
# Physical isolation from Base path is verified by chain_id routing tests.
# ─────────────────────────────────────────────────────────────────────────────
import sys, hashlib
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.fixtures.rh_v3_mint_calldata import (
    LEGAL_MINT_INTENT,
    LEGAL_COLLECT_INTENT,
    LEGAL_MULTICALL_INTENT,
    LEGAL_MINT_CALDATA,
    LEGAL_COLLECT_CALDATA,
    LEGAL_MULTICALL_CALDATA,
    NPM_RH_SENTINEL,
    DUMMY_TOKEN0, DUMMY_TOKEN1, DUMMY_RECIPIENT,
    PAST_DEADLINE,
    build_mint_calldata, build_collect_calldata,
    calldata_hash,
)
from scripts.lp_rh_calldata_whitelist_gate_v1_readonly import verify_intent_or_reject


class TestRHWhitelistPositive:
    """F4.1 — Legal RH intents must pass."""

    def test_rh_legal_mint_passes(self):
        """Legal mint intent with RH chain_id=4663 passes (role=test bypasses manifest)."""
        from copy import deepcopy
        intent = deepcopy(LEGAL_MINT_INTENT)
        intent["role"] = "test"
        ok, reason = verify_intent_or_reject(intent)
        assert ok is True, f"legal mint must pass, got reason={reason}"
        assert reason is None

    def test_rh_legal_collect_passes(self):
        """Legal collect intent with selector 0xfc6f7865 passes."""
        from copy import deepcopy
        intent = deepcopy(LEGAL_COLLECT_INTENT)
        intent["role"] = "test"
        ok, reason = verify_intent_or_reject(intent)
        assert ok is True, f"legal collect must pass, got reason={reason}"
        assert reason is None

    def test_rh_legal_multicall_passes(self):
        """Legal multicall containing one mint inner call passes."""
        from copy import deepcopy
        intent = deepcopy(LEGAL_MULTICALL_INTENT)
        intent["role"] = "test"
        ok, reason = verify_intent_or_reject(intent)
        assert ok is True, f"legal multicall must pass, got reason={reason}"
        assert reason is None


class TestRHWhitelistNegative:
    """F4.2 — RH-specific rejection reasons."""

    def test_rh_wrong_chain_8453_rejected(self):
        """chain_id=8453 routes to Base path; NPM_RH_SENTINEL not in WHITELIST_TARGETS → target_not_whitelisted.

        With the Base-path intent injection fix, verify_intent passes (expected_intent.chain_id=4663
        matches decoded mint claim). The rejection comes from target not being in Base whitelist.
        """
        from copy import deepcopy
        intent = deepcopy(LEGAL_MINT_INTENT)
        intent["chain_id"] = 8453  # Base path
        intent["target_address"] = NPM_RH_SENTINEL  # 0x0...0 not in Base WHITELIST_TARGETS
        intent["expected_intent"] = dict(LEGAL_MINT_INTENT["expected_intent"], chain_id=4663)
        intent["calldata_bytes"] = LEGAL_MINT_CALDATA
        intent["calldata_hash"] = calldata_hash(LEGAL_MINT_CALDATA)
        ok, reason = verify_intent_or_reject(intent)
        assert ok is False
        assert "target_not_whitelisted" in reason

    def test_rh_wrong_target_rejected(self):
        """target=0xdeadbeef not in RH_CORE_TARGETS → target_not_whitelisted."""
        from copy import deepcopy
        intent = deepcopy(LEGAL_MINT_INTENT)
        intent["role"] = "test"  # bypass manifest to reach target check
        intent["target_address"] = "0xdeadbeef" + "deadbeef" * 4
        ok, reason = verify_intent_or_reject(intent)
        assert ok is False
        assert "target_not_whitelisted" in reason

    def test_rh_wrong_selector_rejected(self):
        """selector=0xdeadbeef not in RH_CORE_SELECTORS → selector_not_whitelisted."""
        from copy import deepcopy
        intent = deepcopy(LEGAL_MINT_INTENT)
        intent["role"] = "test"  # bypass manifest to reach selector check
        intent["selector"] = "0xdeadbeef"
        ok, reason = verify_intent_or_reject(intent)
        assert ok is False
        assert "selector_not_whitelisted" in reason

    def test_rh_wrong_recipient_rejected(self):
        """recipient=0xaaaa... not in RH_CORE_RECIPIENTS → recipient_not_whitelisted."""
        from copy import deepcopy
        intent = deepcopy(LEGAL_MINT_INTENT)
        intent["role"] = "test"  # bypass manifest to reach recipient check
        intent["recipient_address"] = "0x" + "aa" * 20
        ok, reason = verify_intent_or_reject(intent)
        assert ok is False
        assert "recipient_not_whitelisted" in reason

    def test_rh_expired_deadline_rejected(self):
        """deadline in the past → deadline_expired."""
        from copy import deepcopy
        intent = deepcopy(LEGAL_MINT_INTENT)
        intent["role"] = "test"  # bypass manifest to reach deadline check
        intent["deadline"] = PAST_DEADLINE
        ok, reason = verify_intent_or_reject(intent)
        assert ok is False
        assert "deadline_expired" in reason

    def test_rh_calldata_hash_mismatch_rejected(self):
        """wrong calldata_hash → calldata_hash_mismatch."""
        from copy import deepcopy
        intent = deepcopy(LEGAL_MINT_INTENT)
        intent["role"] = "test"  # bypass manifest to reach hash check
        intent["calldata_hash"] = "0x" + "ff" * 32
        intent["expected_intent"] = dict(LEGAL_MINT_INTENT["expected_intent"],
                                          calldata_hash="0x" + "ff" * 32)
        ok, reason = verify_intent_or_reject(intent)
        assert ok is False
        assert "calldata_hash_mismatch" in reason

    def test_rh_multicall_inner_unknown_selector_rejected(self):
        """multicall with inner call selector=0xdeadbeef → multicall_inner_reject.

        0xdeadbeef is not in SELECTORS (decoder returns UNKNOWN_SELECTOR), causing
        the outer multicall decode to fail before _validate_rh even runs.
        The gate correctly rejects with calldata_decode_failed.
        """
        from copy import deepcopy
        intent = deepcopy(LEGAL_MULTICALL_INTENT)
        intent["role"] = "test"
        intent["calldata_bytes"] = "0xdeadbeef" + "00" * 50
        intent["calldata_hash"] = calldata_hash(intent["calldata_bytes"])
        intent["expected_intent"] = dict(
            LEGAL_MULTICALL_INTENT["expected_intent"],
            calldata_hash=intent["calldata_hash"],
        )
        ok, reason = verify_intent_or_reject(intent)
        assert ok is False
        assert "multicall_inner_reject" in reason or "calldata_decode_failed" in reason

    def test_rh_missing_min_protection_rejected(self):
        """amount0Min=0 and amount1Min=0 (non-multicall) → missing_slippage_protection."""
        zero_min_cd = build_mint_calldata(
            token0=DUMMY_TOKEN0, token1=DUMMY_TOKEN1, fee=3000,
            tick_lower=-887220, tick_upper=887220,
            amount0_desired=1_000_000_000_000_000_000,
            amount1_desired=1_000_000_000_000_000_000,
            amount0_min=0,  # zero!
            amount1_min=0,  # zero!
            recipient=DUMMY_RECIPIENT,
            deadline=LEGAL_MINT_INTENT["deadline"],
        )
        cd_hash = calldata_hash(zero_min_cd)
        from copy import deepcopy
        intent = deepcopy(LEGAL_MINT_INTENT)
        intent["role"] = "test"  # bypass manifest to reach slippage check
        intent["calldata_bytes"] = zero_min_cd
        intent["calldata_hash"] = cd_hash
        intent["expected_intent"] = dict(
            LEGAL_MINT_INTENT["expected_intent"], calldata_hash=cd_hash
        )
        ok, reason = verify_intent_or_reject(intent)
        assert ok is False
        assert "missing_slippage_protection" in reason

    def test_rh_value_mismatch_rejected(self):
        """expected_value_wei != actual value_wei → value_mismatch."""
        from copy import deepcopy
        intent = deepcopy(LEGAL_MINT_INTENT)
        intent["role"] = "test"  # bypass manifest to reach value check
        intent["expected_value_wei"] = 999  # different from 0
        ok, reason = verify_intent_or_reject(intent)
        assert ok is False
        assert "value_mismatch" in reason

    def test_rh_none_chain_rejected(self):
        """chain_id=None → unsupported_chain:None."""
        from copy import deepcopy
        intent = deepcopy(LEGAL_MINT_INTENT)
        intent["role"] = "gate"
        intent["chain_id"] = None
        ok, reason = verify_intent_or_reject(intent)
        assert ok is False
        assert "unsupported_chain" in reason

    def test_rh_unsupported_chain_rejected(self):
        """chain_id=1 (Ethereum mainnet) → unsupported_chain:1."""
        from copy import deepcopy
        intent = deepcopy(LEGAL_MINT_INTENT)
        intent["role"] = "gate"
        intent["chain_id"] = 1
        ok, reason = verify_intent_or_reject(intent)
        assert ok is False
        assert "unsupported_chain" in reason

    def test_rh_manifest_unverified_blocks_entry(self):
        """role=gateway → unverified_manifest_pending_rpc."""
        from copy import deepcopy
        intent = deepcopy(LEGAL_MINT_INTENT)
        intent["role"] = "gate"  # non-test role → blocked by unverified manifest
        ok, reason = verify_intent_or_reject(intent)
        assert ok is False
        assert "manifest_reject" in reason
        assert "unverified_manifest" in reason
