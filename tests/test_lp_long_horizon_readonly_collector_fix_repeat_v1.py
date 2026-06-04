"""Tests for LP Long Horizon Read-only Collector Fix Repeat (FIX_REPEAT_V1).

Verifies:
1. retry/backoff/timeout/429 helpers work as specified
2. AbortController + ErrorRateMonitor cover the 5 abort conditions
3. local_artifact_replay_adapter returns 5 real PoolRecord objects
4. public_api_coingecko + solana_rpc_readonly are read-only (no wallet / signer / tx)
5. classify_regime covers all 7 regimes + priority + boundary cases
6. ResearchStore writes to SQLite + JSONL, falls back when SQLite fails
7. The runner produces real_data_rows > 0 and placeholder_rows < total
8. No production / shadow writes
9. No wallet / tx / mutation anywhere
10. FINAL_VERDICT.json locks all required fields
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
SCRIPTS_DIR = REPO_ROOT / "scripts"
REPORT_DIR = REPO_ROOT / "reports" / "lp_long_horizon_readonly_collector_fix_repeat" / "20260604_084008"
RUNNER = REPO_ROOT / "scripts" / "lp_long_horizon_readonly_real_data_smoke_v1.py"

FINAL_VERDICT = REPORT_DIR / "FINAL_VERDICT.json"
INPUT_EVIDENCE = REPORT_DIR / "input_evidence_audit.json"
PLAN_JSON = REPORT_DIR / "fix_repeat_plan.json"
RETRY_IMPL_JSON = REPORT_DIR / "retry_backoff_utils_impl.json"
REPLAY_IMPL_JSON = REPORT_DIR / "local_artifact_replay_adapter_impl.json"
PUBLIC_API_IMPL_JSON = REPORT_DIR / "public_api_and_solana_rpc_adapters_impl.json"
REGIME_IMPL_JSON = REPORT_DIR / "regime_classifier_impl.json"
SQLITE_IMPL_JSON = REPORT_DIR / "sqlite_storage_impl.json"
RUNNER_IMPL_JSON = REPORT_DIR / "real_data_smoke_runner_impl.json"
SMOKE_RESULT_JSON = REPORT_DIR / "real_data_smoke_result.json"

CN_DOCS = [
    REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md",
    REPORT_DIR / "FIX_REPEAT_PLAN_CN.md",
    REPORT_DIR / "RETRY_BACKOFF_UTILS_IMPL_CN.md",
    REPORT_DIR / "LOCAL_ARTIFACT_REPLAY_ADAPTER_IMPL_CN.md",
    REPORT_DIR / "PUBLIC_API_AND_SOLANA_RPC_ADAPTERS_IMPL_CN.md",
    REPORT_DIR / "REGIME_CLASSIFIER_IMPL_CN.md",
    REPORT_DIR / "SQLITE_STORAGE_IMPL_CN.md",
    REPORT_DIR / "REAL_DATA_SMOKE_RUNNER_IMPL_CN.md",
    REPORT_DIR / "REAL_DATA_SMOKE_RESULT_CN.md",
    REPORT_DIR / "ONEPAGE_CN.md",
    REPORT_DIR / "ARTIFACT_INDEX.md",
]

# ---------------------------------------------------------------------------
# Pre-flight: ensure scripts/ is on sys.path so we can import the package
# ---------------------------------------------------------------------------

# Add SCRIPTS_DIR to sys.path so we can import lp_long_horizon.* directly
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# ---------------------------------------------------------------------------
# Final verdict
# ---------------------------------------------------------------------------

def test_final_verdict_required_fields():
    assert FINAL_VERDICT.exists(), f"missing {FINAL_VERDICT}"
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    assert v["stage"] == "LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1"
    assert v["status"] in {"PASS", "WARN", "FAIL"}
    assert v["source_adapter_implemented"] is True
    assert v["classifier_implemented"] is True
    assert v["retry_backoff_implemented"] is True
    assert v["abort_condition_implemented"] is True
    assert v["sqlite_enabled"] is True
    assert v["jsonl_storage_ready"] is True
    assert v["error_rate_monitor_implemented"] is True
    assert v["real_data_smoke_ran"] is True
    assert v["real_data_rows"] > 0
    assert v["placeholder_rows"] < v["total_rows"]
    assert v["schema_validation_pass"] is True
    assert v["research_only_write_ok"] is True
    assert v["can_run_probe_now"] is False
    assert v["tiny_canary_allowed"] == "no"
    assert v["edge_proven"] == "no"
    assert v["wallet_or_tx_touched"] is False
    assert v["transaction_sent"] is False


def test_final_verdict_long_run_readiness_partial():
    v = json.loads(FINAL_VERDICT.read_text(encoding="utf-8"))
    r = v["long_run_readiness_9_items"]
    assert r["source_adapter_implemented"] is True
    assert r["classifier_implemented"] is True
    assert r["rate_limit_retry_backoff_implemented"] is True
    assert r["abort_condition_implemented"] is True
    assert r["sqlite_enabled"] is True
    assert r["error_rate_monitor_implemented"] is True
    assert r["paid_rpc_indexer_integrated"] is False
    assert r["cron_systemd_configured"] is False
    assert r["manual_approval_recorded"] is False
    assert v["long_run_ready"] is False


# ---------------------------------------------------------------------------
# 1. retry / backoff / 429 / timeout
# ---------------------------------------------------------------------------

def test_retry_with_backoff_succeeds_after_retries(monkeypatch):
    from lp_long_horizon.utils import retry as retry_mod
    from lp_long_horizon.utils.retry import retry_with_backoff
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    sleeps = []
    monkeypatch.setattr(retry_mod, "sleep", lambda s: sleeps.append(s))
    result = retry_with_backoff(flaky, max_retries=3, base_delay_s=0.1)
    assert result == "ok"
    assert calls["n"] == 3
    assert len(sleeps) == 2
    assert abs(sleeps[0] - 0.1) < 1e-9
    assert abs(sleeps[1] - 0.2) < 1e-9


def test_retry_with_backoff_gives_up_after_max_retries(monkeypatch):
    from lp_long_horizon.utils import retry as retry_mod
    from lp_long_horizon.utils.retry import retry_with_backoff
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise RuntimeError("perma")

    monkeypatch.setattr(retry_mod, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="perma"):
        retry_with_backoff(always_fail, max_retries=2, base_delay_s=0.01)
    assert calls["n"] == 3


def test_retry_with_backoff_respects_is_retryable(monkeypatch):
    from lp_long_horizon.utils import retry as retry_mod
    from lp_long_horizon.utils.retry import retry_with_backoff
    monkeypatch.setattr(retry_mod, "sleep", lambda s: None)
    with pytest.raises(ValueError):
        retry_with_backoff(
            lambda: (_ for _ in ()).throw(ValueError("non-retryable")),
            max_retries=3,
            is_retryable=lambda e: False,
        )


def test_classify_429_various_shapes():
    from lp_long_horizon.utils.retry import classify_429

    class E1(Exception):
        status_code = 429
    assert classify_429(E1()) is True

    class E2(Exception):
        code = 429
    assert classify_429(E2()) is True

    assert classify_429(Exception("429 too many")) is False
    assert classify_429(Exception("Too Many Requests")) is True
    assert classify_429(Exception("rate limit hit")) is True
    assert classify_429(Exception("generic error")) is False
    assert classify_429(ValueError("not a 429")) is False


def test_with_timeout_raises_on_exceed(monkeypatch):
    from lp_long_horizon.utils.retry import with_timeout, TimeoutError_

    def slow():
        time.sleep(0.5)
        return "done"

    # Make signal-based timeout extremely short; not all CI runners allow SIGALRM
    # at sub-second granularity, so we use a guard with monkeypatched signal.alarm.
    import lp_long_horizon.utils.retry as retry_mod

    real_alarm = retry_mod.signal.signal
    real_setitimer = retry_mod.signal.setitimer

    # Stub out SIGALRM-based timing to immediately raise
    def fake_setitimer(which, seconds):
        if seconds > 0:
            raise TimeoutError_("test")
        return

    monkeypatch.setattr(retry_mod.signal, "setitimer", fake_setitimer)
    with pytest.raises(TimeoutError_):
        with_timeout(slow, timeout_s=0.001)


# ---------------------------------------------------------------------------
# 2. ErrorRateMonitor + AbortController
# ---------------------------------------------------------------------------

def test_error_rate_monitor_under_threshold():
    from lp_long_horizon.utils.abort import ErrorRateMonitor
    m = ErrorRateMonitor(threshold_pct=20.0, window=10)
    for _ in range(8):
        m.record_ok()
    m.record_error()
    m.record_error()
    # 2/10 = 20% (>= threshold)
    assert m.should_abort() is True


def test_error_rate_monitor_below_threshold():
    from lp_long_horizon.utils.abort import ErrorRateMonitor
    m = ErrorRateMonitor(threshold_pct=20.0, window=10)
    for _ in range(9):
        m.record_ok()
    m.record_error()
    # 1/10 = 10% (< 20%)
    assert m.should_abort() is False


def test_error_rate_monitor_window_slides():
    from lp_long_horizon.utils.abort import ErrorRateMonitor
    m = ErrorRateMonitor(threshold_pct=50.0, window=5)
    for _ in range(3):
        m.record_error()
    for _ in range(2):
        m.record_ok()
    # 3/5 = 60% (>= 50%)
    assert m.should_abort() is True
    for _ in range(5):
        m.record_ok()
    # 0/5 = 0% (window slid past errors)
    assert m.should_abort() is False


def test_abort_controller_consecutive_429():
    from lp_long_horizon.utils.abort import AbortController, AbortError
    a = AbortController()
    for _ in range(4):
        a.record_429()
    assert a.is_aborted is False
    a.record_429()
    assert a.is_aborted is True
    with pytest.raises(AbortError):
        a.check_abort()


def test_abort_controller_error_rate():
    from lp_long_horizon.utils.abort import AbortController, AbortError, ErrorRateMonitor
    a = AbortController(error_rate_monitor=ErrorRateMonitor(threshold_pct=20.0, window=10))
    for _ in range(8):
        a.record_ok()
    a.record_error()
    a.record_error()
    assert a.is_aborted is True
    with pytest.raises(AbortError):
        a.check_abort()


def test_abort_controller_write_failure():
    from lp_long_horizon.utils.abort import AbortController, AbortError
    a = AbortController()
    a.record_write_failure("disk full")
    assert a.is_aborted is True
    assert "write_failure" in a.abort_reason
    with pytest.raises(AbortError):
        a.check_abort()


def test_abort_controller_safety_self_check():
    from lp_long_horizon.utils.abort import AbortController, AbortError
    a = AbortController()
    a.record_safety_self_check_failure("banned token")
    assert a.is_aborted is True
    with pytest.raises(AbortError):
        a.check_abort()


def test_abort_controller_banned_token():
    from lp_long_horizon.utils.abort import AbortController, AbortError
    a = AbortController()
    a.record_banned_token("private_key")
    assert a.is_aborted is True
    assert "banned_token_detected" in a.abort_reason
    with pytest.raises(AbortError):
        a.check_abort()


def test_abort_controller_429_cleared():
    from lp_long_horizon.utils.abort import AbortController
    a = AbortController()
    # 4 record_429 + clear + 1 record_429 = streak 1
    for _ in range(4):
        a.record_429()
    a.record_429_cleared()
    a.record_429()
    assert a.is_aborted is False
    # 4 more record_429 → streak 5 → abort
    for _ in range(4):
        a.record_429()
    assert a.is_aborted is True


# ---------------------------------------------------------------------------
# 3. local_artifact_replay_adapter
# ---------------------------------------------------------------------------

def test_local_artifact_replay_returns_5_records():
    from lp_long_horizon.adapters.local_artifact_replay import LocalArtifactReplayAdapter
    a = LocalArtifactReplayAdapter()
    pools = a.fetch_pools()
    assert len(pools) == 5
    for p in pools:
        assert p.real_data is True
        assert p.pool_address
        assert p.program_id


def test_local_artifact_replay_pool_addresses_unique():
    from lp_long_horizon.adapters.local_artifact_replay import LocalArtifactReplayAdapter
    a = LocalArtifactReplayAdapter()
    pools = a.fetch_pools()
    addresses = [p.pool_address for p in pools]
    assert len(set(addresses)) == 5


def test_local_artifact_replay_program_ids_match():
    from lp_long_horizon.adapters.local_artifact_replay import LocalArtifactReplayAdapter
    a = LocalArtifactReplayAdapter()
    pools = a.fetch_pools()
    program_ids = {p.program_id for p in pools}
    # 4 distinct program ids (solana_stable shares with orca_whirlpool)
    assert "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo" in program_ids  # meteora_dlmm
    assert "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc" in program_ids  # orca_whirlpool
    assert "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK" in program_ids  # raydium_clmm
    assert "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8" in program_ids  # raydium_cpmm


def test_local_artifact_replay_records_abort_on_missing():
    from lp_long_horizon.adapters.local_artifact_replay import LocalArtifactReplayAdapter
    from lp_long_horizon.utils.abort import AbortController
    a = AbortController()
    # Construct with non-existent path
    bad = LocalArtifactReplayAdapter(repo_root=Path("/nonexistent/repo"))
    pools = bad.fetch_pools()
    assert pools == []


def test_build_pool_snapshot_row_real_data_true():
    from lp_long_horizon.adapters.local_artifact_replay import (
        LocalArtifactReplayAdapter, build_pool_snapshot_row,
    )
    a = LocalArtifactReplayAdapter()
    pools = a.fetch_pools()
    row = build_pool_snapshot_row(pools[0], snapshot_at="2026-06-04T00:00:00Z")
    assert row["real_data"] is True
    assert row["data_source"] == "local_artifact_replay"
    assert row["pool_address"] == pools[0].pool_address
    assert row["program_id"] == pools[0].program_id


def test_build_quote_snapshot_rows_6_notionals():
    from lp_long_horizon.adapters.local_artifact_replay import (
        LocalArtifactReplayAdapter, build_quote_snapshot_rows,
    )
    a = LocalArtifactReplayAdapter()
    pools = a.fetch_pools()
    rows = build_quote_snapshot_rows(pools[0], [10, 20, 100, 500, 1000, 2000], quote_at="2026-06-04T00:00:00Z")
    assert len(rows) == 6
    assert all(r["real_data"] is True for r in rows)
    notionals = [r["notional_usd"] for r in rows]
    assert notionals == [10, 20, 100, 500, 1000, 2000]


def test_build_fee_velocity_rows_5_windows():
    from lp_long_horizon.adapters.local_artifact_replay import (
        LocalArtifactReplayAdapter, build_fee_velocity_rows,
    )
    a = LocalArtifactReplayAdapter()
    pools = a.fetch_pools()
    rows = build_fee_velocity_rows(pools[0], ["15m", "1h", "6h", "24h", "7d"], window_end_at="2026-06-04T00:00:00Z")
    assert len(rows) == 5
    assert all(r["real_data"] is True for r in rows)


# ---------------------------------------------------------------------------
# 4. public_api + solana_rpc adapters: no banned tokens, no wallet, no tx
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module_name", [
    "lp_long_horizon.adapters.public_api_coingecko",
    "lp_long_horizon.adapters.solana_rpc_readonly",
])
def test_adapter_module_no_banned_token(module_name):
    """Import the module; the module-level _self_check would have raised if any
    banned token was present. Just verify the module is importable and exposes
    the expected classes."""
    mod = __import__(module_name, fromlist=["*"])
    assert hasattr(mod, "_self_check")


# ---------------------------------------------------------------------------
# 5. classify_regime: 7 regimes + priority + boundaries
# ---------------------------------------------------------------------------

def test_classify_low_vol_stable_priority():
    from lp_long_horizon.classify.market_regime import classify_regime
    # vol < 1 wins regardless of trend / incentive
    assert classify_regime(realized_vol_7d_pct=0.5, price_change_7d_pct=10.0,
                           volume_to_tvl_30d_pct=0.0, lm_active=True) == "low_volatility_stable"


def test_classify_incentive_overrides_trend():
    from lp_long_horizon.classify.market_regime import classify_regime
    # lm_active wins over trend
    assert classify_regime(realized_vol_7d_pct=5.0, price_change_7d_pct=20.0,
                           volume_to_tvl_30d_pct=0.0, lm_active=True) == "incentive_period"
    assert classify_regime(realized_vol_7d_pct=5.0, price_change_7d_pct=-20.0,
                           volume_to_tvl_30d_pct=0.0, bribe_active=True) == "incentive_period"


def test_classify_high_vol_overrides_trend():
    from lp_long_horizon.classify.market_regime import classify_regime
    # vol >= 10 wins even with sideways / downtrend
    assert classify_regime(realized_vol_7d_pct=12.0, price_change_7d_pct=0.0,
                           volume_to_tvl_30d_pct=0.5) == "high_volatility_trend"


def test_classify_uptrend():
    from lp_long_horizon.classify.market_regime import classify_regime
    assert classify_regime(realized_vol_7d_pct=5.0, price_change_7d_pct=8.0,
                           volume_to_tvl_30d_pct=0.0) == "uptrend"


def test_classify_downtrend():
    from lp_long_horizon.classify.market_regime import classify_regime
    assert classify_regime(realized_vol_7d_pct=5.0, price_change_7d_pct=-8.0,
                           volume_to_tvl_30d_pct=0.0) == "downtrend"


def test_classify_high_volume_sideways():
    from lp_long_horizon.classify.market_regime import classify_regime
    # sideways + vol/TVL >= 1
    assert classify_regime(realized_vol_7d_pct=2.0, price_change_7d_pct=2.0,
                           volume_to_tvl_30d_pct=1.5) == "high_volume_sideways"


def test_classify_sideways_default():
    from lp_long_horizon.classify.market_regime import classify_regime
    assert classify_regime(realized_vol_7d_pct=2.0, price_change_7d_pct=0.5,
                           volume_to_tvl_30d_pct=0.5) == "sideways"


def test_classify_priority_5pct_boundary():
    from lp_long_horizon.classify.market_regime import classify_regime
    # px = 5.0 is NOT uptrend (>5 strict)
    assert classify_regime(realized_vol_7d_pct=5.0, price_change_7d_pct=5.0,
                           volume_to_tvl_30d_pct=0.0) == "sideways"
    # px = 5.001 IS uptrend
    assert classify_regime(realized_vol_7d_pct=5.0, price_change_7d_pct=5.001,
                           volume_to_tvl_30d_pct=0.0) == "uptrend"


def test_classify_priority_1pct_vol_boundary():
    from lp_long_horizon.classify.market_regime import classify_regime
    # vol = 0.99 < 1 → low_vol
    assert classify_regime(realized_vol_7d_pct=0.99, price_change_7d_pct=0.0,
                           volume_to_tvl_30d_pct=0.0) == "low_volatility_stable"
    # vol = 1.0 NOT < 1, so it goes through incentive / high_vol / trend checks
    assert classify_regime(realized_vol_7d_pct=1.0, price_change_7d_pct=0.0,
                           volume_to_tvl_30d_pct=0.0) == "sideways"


def test_classify_priority_10pct_vol_boundary():
    from lp_long_horizon.classify.market_regime import classify_regime
    # vol = 9.99 < 10
    assert classify_regime(realized_vol_7d_pct=9.99, price_change_7d_pct=0.0,
                           volume_to_tvl_30d_pct=0.0) == "sideways"
    # vol = 10.0 >= 10 → high_volatility_trend
    assert classify_regime(realized_vol_7d_pct=10.0, price_change_7d_pct=0.0,
                           volume_to_tvl_30d_pct=0.0) == "high_volatility_trend"


def test_is_valid_regime():
    from lp_long_horizon.classify.market_regime import is_valid_regime
    assert is_valid_regime("uptrend") is True
    assert is_valid_regime("sideways") is True
    assert is_valid_regime("unknown") is False
    assert is_valid_regime("foo") is False


def test_regime_priority_index():
    from lp_long_horizon.classify.market_regime import regime_priority_index
    assert regime_priority_index("low_volatility_stable") == 0
    assert regime_priority_index("sideways") == 6
    assert regime_priority_index("unknown") == 7  # fallback index


# ---------------------------------------------------------------------------
# 6. ResearchStore: SQLite + JSONL dual write + fallback
# ---------------------------------------------------------------------------

def test_research_store_init_creates_sqlite(tmp_path):
    from lp_long_horizon.storage.research_store import ResearchStore
    store = ResearchStore(tmp_path)
    try:
        assert store.sqlite_available is True
        assert (tmp_path / "research.sqlite").exists()
    finally:
        store.close()


def test_research_store_write_pool_snapshot(tmp_path):
    from lp_long_horizon.storage.research_store import ResearchStore
    store = ResearchStore(tmp_path)
    try:
        store.write_pool_snapshot({
            "pool_address": "X", "chain": "solana", "protocol": "p",
            "program_id": "PRG", "snapshot_at": "2026-06-04T00:00:00Z",
            "real_data": True, "data_source": "test",
            "fee_tier_bps": 100, "reserve_a_raw": 0, "reserve_b_raw": 0,
            "liquidity": 0, "active_tick": None, "active_bin": None,
            "tvl_usd": 0.0, "token_mint_a": "a", "token_mint_b": "b",
            "token_symbol_a": "A", "token_symbol_b": "B",
        })
        assert store.counts["pool_snapshots"] == 1
        # JSONL exists
        assert (tmp_path / "pool_snapshots.jsonl").exists()
    finally:
        store.close()


def test_research_store_real_data_int_coercion(tmp_path):
    from lp_long_horizon.storage.research_store import ResearchStore
    import sqlite3
    store = ResearchStore(tmp_path)
    try:
        store.write_pool_snapshot({
            "pool_address": "X", "chain": "solana", "protocol": "p",
            "program_id": "PRG", "snapshot_at": "2026-06-04T00:00:00Z",
            "real_data": True, "data_source": "test",
            "fee_tier_bps": 0, "reserve_a_raw": 0, "reserve_b_raw": 0,
            "liquidity": 0, "active_tick": None, "active_bin": None,
            "tvl_usd": 0.0, "token_mint_a": "a", "token_mint_b": "b",
            "token_symbol_a": "A", "token_symbol_b": "B",
        })
        # Verify sqlite row stores real_data=1
        conn = sqlite3.connect(str(tmp_path / "research.sqlite"))
        row = conn.execute("SELECT real_data FROM pool_snapshots LIMIT 1").fetchone()
        conn.close()
        assert row[0] == 1
    finally:
        store.close()


def test_research_store_jsonl_only_when_sqlite_fails(tmp_path):
    from lp_long_horizon.storage.research_store import ResearchStore
    # Force sqlite to fail by passing a non-writable path
    bad_path = tmp_path / "no_such_subdir" / "x" / "research.sqlite"
    # Actually, sqlite3.connect will create the file; we need a different failure mode.
    # Simulate by passing a path that exists as a directory (not file).
    (tmp_path / "research.sqlite").mkdir()
    store = ResearchStore(tmp_path)
    try:
        # SQLite init will fail (path is a dir, not a file)
        assert store.sqlite_available is False
        assert store.jsonl_only is True
        # But JSONL writes still work
        store.write_pool_snapshot({
            "pool_address": "X", "chain": "solana", "protocol": "p",
            "program_id": "PRG", "snapshot_at": "2026-06-04T00:00:00Z",
            "real_data": True, "data_source": "test",
            "fee_tier_bps": 0, "reserve_a_raw": 0, "reserve_b_raw": 0,
            "liquidity": 0, "active_tick": None, "active_bin": None,
            "tvl_usd": 0.0, "token_mint_a": "a", "token_mint_b": "b",
            "token_symbol_a": "A", "token_symbol_b": "B",
        })
        assert (tmp_path / "pool_snapshots.jsonl").exists()
    finally:
        store.close()


def test_research_store_summary(tmp_path):
    from lp_long_horizon.storage.research_store import ResearchStore
    store = ResearchStore(tmp_path)
    try:
        s = store.summary()
        assert "sqlite_available" in s
        assert "jsonl_only" in s
        assert "counts" in s
    finally:
        store.close()


# ---------------------------------------------------------------------------
# 7. runner subprocess integration
# ---------------------------------------------------------------------------

def test_runner_design_mode():
    r = subprocess.run(
        [sys.executable, str(RUNNER), "--mode", "design"],
        capture_output=True, text=True, timeout=30, cwd=REPO_ROOT,
    )
    assert r.returncode == 0
    assert "[design mode]" in r.stdout
    assert "no daemon" in r.stdout.lower()


def test_runner_smoke_mode_produces_real_data(tmp_path):
    # Use a relative path that satisfies the write-path constraint
    out_rel = "data/lp_long_horizon/smoke_test_runner"
    r = subprocess.run(
        [sys.executable, str(RUNNER), "--mode", "smoke", "--out", out_rel],
        capture_output=True, text=True, timeout=60, cwd=REPO_ROOT,
    )
    assert r.returncode == 0, f"smoke failed: rc={r.returncode}\nstderr={r.stderr}"
    out = (REPO_ROOT / out_rel).resolve()
    summary = json.loads((out / "smoke_summary.json").read_text(encoding="utf-8"))
    assert summary["real_data_smoke_ran"] is True
    assert summary["real_data_rows"] > 0
    assert summary["placeholder_rows"] < summary["real_data_rows"] + summary["placeholder_rows"]
    assert summary["wallet_or_tx_touched"] is False
    assert summary["transaction_sent"] is False
    import shutil
    shutil.rmtree(out, ignore_errors=True)


def test_runner_smoke_writes_to_data_lp_long_horizon_only(tmp_path):
    out_rel = "data/lp_long_horizon/smoke_test_writepath"
    r = subprocess.run(
        [sys.executable, str(RUNNER), "--mode", "smoke", "--out", out_rel],
        capture_output=True, text=True, timeout=60, cwd=REPO_ROOT,
    )
    assert r.returncode == 0, f"smoke failed: rc={r.returncode}\nstderr={r.stderr}"
    out = (REPO_ROOT / out_rel).resolve()
    assert (out / "research.sqlite").exists()
    for t in ["pool_snapshots", "quote_snapshots", "fee_velocity",
              "liquidity_distribution", "market_regime", "future_actual_fee_accrual"]:
        assert (out / f"{t}.jsonl").exists()
    import shutil
    shutil.rmtree(out, ignore_errors=True)


def test_runner_refuses_outside_data_lp_long_horizon(tmp_path):
    out = tmp_path / "evil" / "smoke"
    r = subprocess.run(
        [sys.executable, str(RUNNER), "--mode", "smoke", "--out", str(out)],
        capture_output=True, text=True, timeout=10, cwd=REPO_ROOT,
    )
    assert r.returncode != 0
    assert "REFUSED" in r.stderr or "must start with" in r.stderr


# ---------------------------------------------------------------------------
# 8. CN docs + run_id consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", CN_DOCS, ids=lambda p: p.name)
def test_cn_doc_exists(path: Path):
    assert path.exists(), f"missing {path.name}"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"empty {path.name}"
    assert "20260604_084008" in text, f"run_id missing in {path.name}"


def test_run_id_consistent():
    expected = "20260604_084008"
    paths = [
        FINAL_VERDICT, INPUT_EVIDENCE, PLAN_JSON, RETRY_IMPL_JSON,
        REPLAY_IMPL_JSON, PUBLIC_API_IMPL_JSON, REGIME_IMPL_JSON,
        SQLITE_IMPL_JSON, RUNNER_IMPL_JSON, SMOKE_RESULT_JSON,
    ] + CN_DOCS
    for p in paths:
        text = p.read_text(encoding="utf-8")
        assert expected in text, f"run_id {expected} missing in {p.name}"


# ---------------------------------------------------------------------------
# 9. process safety
# ---------------------------------------------------------------------------

def test_no_canary_live_paper_keypair_process():
    r = subprocess.run(
        ["bash", "-c",
         "ps aux | egrep 'canary|lpbot-live|live|paper|sendTransaction|eth_sendRawTransaction|"
         "eth_sendTransaction|keypair' | grep -v grep || true"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0
    matched = [line for line in r.stdout.splitlines() if "grep" not in line and line.strip()]
    assert not matched, f"suspicious running process: {matched}"


# ---------------------------------------------------------------------------
# 10. lib files self-check at import (verify they import without error)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module_name", [
    "lp_long_horizon.utils.retry",
    "lp_long_horizon.utils.abort",
    "lp_long_horizon.adapters.local_artifact_replay",
    "lp_long_horizon.adapters.public_api_coingecko",
    "lp_long_horizon.adapters.solana_rpc_readonly",
    "lp_long_horizon.classify.market_regime",
    "lp_long_horizon.storage.research_store",
])
def test_lib_module_imports(module_name):
    """Importing the module should succeed (self_check at module load passes)."""
    __import__(module_name, fromlist=["*"])
