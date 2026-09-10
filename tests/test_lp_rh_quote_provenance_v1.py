"""Tests for RH-02bg: Quote evidence provenance and TTL validation.

Verifies:
1. Structured evidence + unexpired -> computes NAV, bit-for-bit equal to bare quote.
2. Missing quote evidence -> no NAV, reason QUOTE_EVIDENCE_MISSING.
3. observed_at exceeds ttl_secs relative to sample_time -> no NAV, reason QUOTE_EVIDENCE_EXPIRED.
4. Boundary condition: exactly equal to ttl_secs (<=) -> unexpired, NAV computed.
5. Invalid values (value <= 0, non-finite), empty source, unparseable observed_at -> fail-close.
6. Real reports/lp_rh/pool_meta.json run: 200 steps all without NAV, reason QUOTE_EVIDENCE_MISSING.
7. Unprovenanced bare quotes: default rejected (QUOTE_EVIDENCE_UNPROVENANCED), allowed with allow_bare_quote=True.
"""
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.lp_rh_shadow_runner_v1_readonly import (
    DEFAULT_POOL,
    ShadowStep,
    episode_summary,
    load_samples_from_db,
    run_episode,
    validate_quote_evidence,
)
from scripts.lp_rh_store_v1_readonly import migrate, open_store

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_DB = REPO_ROOT / "reports" / "lp_rh" / "scanner.db"
REAL_POOL_META_PATH = REPO_ROOT / "reports" / "lp_rh" / "pool_meta.json"

POSITION_USD = Decimal("1000")
CAPITAL_USD = Decimal("10000")
HORIZON_HOURS = 8760.0
BASE_SAMPLE_TIME = "2026-01-01T00:00:00Z"
DFG0 = 9365277615024075401537929281665916457
DFG1 = 21451527583324632536589703137
X0 = 45000000000000000000000000000000000000000
X1 = X0 + 1
PRICE = Decimal("2484")


def _passing_sample(idx, *, price=PRICE, fee_growth=(X0, X1), sample_time=None, **overrides):
    # idx runs past 59 in the 200-step case, and f"00:{idx:02d}" then produces
    # "00:100:00" -- a string that looks like a timestamp and is not one.
    # Carry the overflow into hours instead.
    s_time = sample_time or (
        f"2026-01-01T{idx // 60:02d}:{idx % 60:02d}:00Z"
    )
    s = {
        "candidate_key": f"pool-{idx}",
        "sample_time": s_time,
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
    }
    if price is not None:
        s["reference_mid"] = price
    if fee_growth is not None:
        s["fee_growth_global_0"], s["fee_growth_global_1"] = fee_growth
    s.update(overrides)
    return s


def _base_meta(**overrides):
    m = {
        "input_price_usd": "2484.0",
        "range_pct": 10.0,
        "dec0": 18,
        "dec1": 6,
        "attestation_status": "ATTESTED_SAME_BLOCK",
        "protocol": "v3",
    }
    m.update(overrides)
    return m


def _fresh_store(tmp_path, name="s.db"):
    conn = open_store(tmp_path / name)
    migrate(conn)
    return conn


# ===========================================================================
# 1. validate_quote_evidence unit tests
# ===========================================================================

def test_unit_validate_quote_structured_valid():
    quote = {
        "value": "1.0005",
        "source": "coingecko:usdg-usd",
        "observed_at": "2026-01-01T00:00:00Z",
        "ttl_secs": 86400,
    }
    val, err = validate_quote_evidence(quote, sample_time="2026-01-01T12:00:00Z")
    assert err is None
    assert val == Decimal("1.0005")


def test_unit_validate_quote_missing():
    val, err = validate_quote_evidence(None, sample_time="2026-01-01T00:00:00Z")
    assert val is None and err == "QUOTE_EVIDENCE_MISSING"

    val, err = validate_quote_evidence({}, sample_time="2026-01-01T00:00:00Z")
    assert val is None and err == "QUOTE_EVIDENCE_MISSING"

    val, err = validate_quote_evidence({"value": None}, sample_time="2026-01-01T00:00:00Z")
    assert val is None and err == "QUOTE_EVIDENCE_MISSING"


def test_unit_validate_quote_expired():
    quote = {
        "value": "1.0",
        "source": "coingecko:usdg-usd",
        "observed_at": "2026-01-01T00:00:00Z",
        "ttl_secs": 3600,
    }
    # 3601s later -> expired
    val, err = validate_quote_evidence(quote, sample_time="2026-01-01T01:00:01Z")
    assert val is None and err == "QUOTE_EVIDENCE_EXPIRED"


def test_unit_validate_quote_boundary_exact_ttl():
    quote = {
        "value": "1.0",
        "source": "coingecko:usdg-usd",
        "observed_at": "2026-01-01T00:00:00Z",
        "ttl_secs": 3600,
    }
    # Exactly 3600s -> unexpired (<=)
    val, err = validate_quote_evidence(quote, sample_time="2026-01-01T01:00:00Z")
    assert err is None
    assert val == Decimal("1.0")


@pytest.mark.parametrize("bad_val", ["0", "-1.0", "nan", "inf", "-inf", "abc"])
def test_unit_validate_quote_invalid_value(bad_val):
    quote = {
        "value": bad_val,
        "source": "coingecko:usdg-usd",
        "observed_at": "2026-01-01T00:00:00Z",
        "ttl_secs": 86400,
    }
    val, err = validate_quote_evidence(quote, sample_time="2026-01-01T00:00:00Z")
    assert val is None and err == "QUOTE_EVIDENCE_INVALID_VALUE"


@pytest.mark.parametrize("bad_src", ["", "   ", None])
def test_unit_validate_quote_empty_source(bad_src):
    quote = {
        "value": "1.0",
        "source": bad_src,
        "observed_at": "2026-01-01T00:00:00Z",
        "ttl_secs": 86400,
    }
    val, err = validate_quote_evidence(quote, sample_time="2026-01-01T00:00:00Z")
    assert val is None and err == "QUOTE_EVIDENCE_SOURCE_EMPTY"


@pytest.mark.parametrize("bad_time", ["not-a-date", "", None])
def test_unit_validate_quote_unparseable_observed_at(bad_time):
    quote = {
        "value": "1.0",
        "source": "coingecko:usdg-usd",
        "observed_at": bad_time,
        "ttl_secs": 86400,
    }
    val, err = validate_quote_evidence(quote, sample_time="2026-01-01T00:00:00Z")
    assert val is None and err == "QUOTE_EVIDENCE_OBSERVED_AT_UNPARSEABLE"


def test_unit_validate_quote_bare_number_policy():
    # Default: allow_bare_quote=False -> rejected as unprovenanced
    val, err = validate_quote_evidence(1.0, sample_time="2026-01-01T00:00:00Z", allow_bare_quote=False)
    assert val is None and err == "QUOTE_EVIDENCE_UNPROVENANCED"

    val, err = validate_quote_evidence("1.0", sample_time="2026-01-01T00:00:00Z", allow_bare_quote=False)
    assert val is None and err == "QUOTE_EVIDENCE_UNPROVENANCED"

    # Explicit allow: allow_bare_quote=True -> passes
    val, err = validate_quote_evidence(1.0, sample_time="2026-01-01T00:00:00Z", allow_bare_quote=True)
    assert val == Decimal("1.0") and err is None


# ===========================================================================
# 2. Acceptance Criteria 1 to 7 via run_episode
# ===========================================================================

def test_ac1_structured_evidence_nav_identical_to_bare_quote(tmp_path):
    """AC 1: Structured quote + unexpired computes NAV identical to bare quote."""
    samples = [
        _passing_sample(0, sample_time="2026-01-01T00:00:00Z", fee_growth=(X0, X1)),
        _passing_sample(1, sample_time="2026-01-01T00:01:00Z", fee_growth=(X0 + DFG0, X1 + DFG1)),
    ]

    structured_quote = {
        "value": "1.002",
        "source": "coingecko:usdg-usd",
        "observed_at": "2026-01-01T00:00:00Z",
        "ttl_secs": 86400,
    }

    meta_struct = _base_meta(quote_usd_per_token1=structured_quote)
    meta_bare = _base_meta(quote_usd_per_token1="1.002")

    conn1 = _fresh_store(tmp_path, "struct.db")
    steps_struct = run_episode(
        conn1, strategy_episode="struct", samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode="SHADOW_SCENARIO",
        now_fn=lambda: BASE_SAMPLE_TIME, pool_meta=meta_struct,
        allow_bare_quote=False,
    )
    conn1.close()

    conn2 = _fresh_store(tmp_path, "bare.db")
    steps_bare = run_episode(
        conn2, strategy_episode="bare", samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode="SHADOW_SCENARIO",
        now_fn=lambda: BASE_SAMPLE_TIME, pool_meta=meta_bare,
        allow_bare_quote=True,
    )
    conn2.close()

    assert len(steps_struct) == 2 and len(steps_bare) == 2
    for s_st, s_ba in zip(steps_struct, steps_bare):
        assert s_st.nav is not None
        assert s_st.nav == s_ba.nav
        assert s_st.hodl_value is not None
        assert s_st.hodl_value == s_ba.hodl_value
        assert s_st.net_pnl == s_ba.net_pnl
        assert s_st.nav_reason is None


def test_ac2_missing_quote_fails_closed_with_reason(tmp_path):
    """AC 2: Missing quote -> no NAV, reason QUOTE_EVIDENCE_MISSING."""
    samples = [_passing_sample(i) for i in range(3)]
    meta_no_quote = _base_meta()
    assert "quote_usd_per_token1" not in meta_no_quote

    conn = _fresh_store(tmp_path, "missing.db")
    steps = run_episode(
        conn, strategy_episode="missing", samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode="SHADOW_SCENARIO",
        now_fn=lambda: BASE_SAMPLE_TIME, pool_meta=meta_no_quote,
    )
    summary = episode_summary(steps)

    assert all(s.nav is None for s in steps)
    assert all(s.hodl_value is None for s in steps)
    assert all(s.nav_reason == "QUOTE_EVIDENCE_MISSING" for s in steps)
    assert summary["steps_without_nav"] == 3
    assert summary["steps_without_nav_reasons"].get("QUOTE_EVIDENCE_MISSING") == 3

    # Verify rh_position_marks also records unvalued risk reason
    rows = conn.execute("SELECT unvalued_risk_json FROM rh_position_marks").fetchall()
    assert len(rows) == 3
    for (rj,) in rows:
        payload = json.loads(rj)
        assert payload["skipped"] is True
        assert payload["reason"] == "QUOTE_EVIDENCE_MISSING"
    conn.close()


def test_ac3_expired_quote_fails_closed_with_reason(tmp_path):
    """AC 3: observed_at exceeds ttl_secs relative to sample_time -> QUOTE_EVIDENCE_EXPIRED."""
    quote = {
        "value": "1.0",
        "source": "coingecko:usdg-usd",
        "observed_at": "2026-01-01T00:00:00Z",
        "ttl_secs": 3600,  # 1 hour
    }
    # Samples 2 hours later (7200s > 3600s)
    samples = [
        _passing_sample(0, sample_time="2026-01-01T02:00:00Z"),
        _passing_sample(1, sample_time="2026-01-01T02:01:00Z"),
    ]
    meta = _base_meta(quote_usd_per_token1=quote)

    conn = _fresh_store(tmp_path, "expired.db")
    steps = run_episode(
        conn, strategy_episode="expired", samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode="SHADOW_SCENARIO",
        now_fn=lambda: BASE_SAMPLE_TIME, pool_meta=meta,
    )
    summary = episode_summary(steps)

    assert all(s.nav is None for s in steps)
    assert all(s.hodl_value is None for s in steps)
    assert all(s.nav_reason == "QUOTE_EVIDENCE_EXPIRED" for s in steps)
    assert summary["steps_without_nav_reasons"].get("QUOTE_EVIDENCE_EXPIRED") == 2
    conn.close()


def test_ac3_per_step_freshness_check_expires_mid_episode(tmp_path):
    """AC 3: Freshness must be checked per step against sample_time; expires mid-run."""
    quote = {
        "value": "1.0",
        "source": "coingecko:usdg-usd",
        "observed_at": "2026-01-01T00:00:00Z",
        "ttl_secs": 120,  # 2 minutes TTL
    }
    samples = [
        _passing_sample(0, sample_time="2026-01-01T00:00:00Z", fee_growth=(X0, X1)),
        _passing_sample(1, sample_time="2026-01-01T00:01:00Z", fee_growth=(X0 + DFG0, X1 + DFG1)),
        # Step 2 is 5 minutes later: TTL expired!
        _passing_sample(2, sample_time="2026-01-01T00:05:00Z", fee_growth=(X0 + 2 * DFG0, X1 + 2 * DFG1)),
    ]
    meta = _base_meta(quote_usd_per_token1=quote)

    conn = _fresh_store(tmp_path, "mid_expire.db")
    steps = run_episode(
        conn, strategy_episode="mid_expire", samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode="SHADOW_SCENARIO",
        now_fn=lambda: BASE_SAMPLE_TIME, pool_meta=meta,
    )
    conn.close()

    assert steps[0].nav is not None and steps[0].nav_reason is None
    assert steps[1].nav is not None and steps[1].nav_reason is None
    assert steps[2].nav is None and steps[2].nav_reason == "QUOTE_EVIDENCE_EXPIRED"
    assert steps[2].hodl_value is None


def test_ac4_boundary_exactly_equal_ttl_secs(tmp_path):
    """AC 4: Exactly equal to ttl_secs is unexpired (<=); lock with a test."""
    quote = {
        "value": "1.0",
        "source": "coingecko:usdg-usd",
        "observed_at": "2026-01-01T00:00:00Z",
        "ttl_secs": 3600,
    }
    # Exactly 3600s after observed_at
    samples = [
        _passing_sample(0, sample_time="2026-01-01T01:00:00Z", fee_growth=(X0, X1)),
    ]
    meta = _base_meta(quote_usd_per_token1=quote)

    conn = _fresh_store(tmp_path, "boundary.db")
    steps = run_episode(
        conn, strategy_episode="boundary", samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode="SHADOW_SCENARIO",
        now_fn=lambda: BASE_SAMPLE_TIME, pool_meta=meta,
    )
    conn.close()

    assert steps[0].nav is not None
    assert steps[0].nav_reason is None


def test_ac5_invalid_values_fail_closed(tmp_path):
    """AC 5: value <= 0, non-finite, source empty, observed_at unparseable -> fail-close."""
    cases = [
        ({"value": "0", "source": "src", "observed_at": "2026-01-01T00:00:00Z", "ttl_secs": 3600},
         "QUOTE_EVIDENCE_INVALID_VALUE"),
        ({"value": "-1.5", "source": "src", "observed_at": "2026-01-01T00:00:00Z", "ttl_secs": 3600},
         "QUOTE_EVIDENCE_INVALID_VALUE"),
        ({"value": "nan", "source": "src", "observed_at": "2026-01-01T00:00:00Z", "ttl_secs": 3600},
         "QUOTE_EVIDENCE_INVALID_VALUE"),
        ({"value": "inf", "source": "src", "observed_at": "2026-01-01T00:00:00Z", "ttl_secs": 3600},
         "QUOTE_EVIDENCE_INVALID_VALUE"),
        ({"value": "1.0", "source": "", "observed_at": "2026-01-01T00:00:00Z", "ttl_secs": 3600},
         "QUOTE_EVIDENCE_SOURCE_EMPTY"),
        ({"value": "1.0", "source": "   ", "observed_at": "2026-01-01T00:00:00Z", "ttl_secs": 3600},
         "QUOTE_EVIDENCE_SOURCE_EMPTY"),
        ({"value": "1.0", "source": "src", "observed_at": "not-a-time", "ttl_secs": 3600},
         "QUOTE_EVIDENCE_OBSERVED_AT_UNPARSEABLE"),
    ]

    for idx, (quote_payload, expected_reason) in enumerate(cases):
        conn = _fresh_store(tmp_path, f"fail_{idx}.db")
        meta = _base_meta(quote_usd_per_token1=quote_payload)
        steps = run_episode(
            conn, strategy_episode=f"fail_{idx}",
            samples=[_passing_sample(0, sample_time="2026-01-01T00:00:00Z")],
            position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
            capital_usd=CAPITAL_USD, target_mode="SHADOW_SCENARIO",
            now_fn=lambda: BASE_SAMPLE_TIME, pool_meta=meta,
        )
        conn.close()
        assert steps[0].nav is None
        assert steps[0].nav_reason == expected_reason


def test_unprovenanced_bare_quote_default_rejected(tmp_path):
    """Unprovenanced bare quotes fail-close by default unless allow_bare_quote=True."""
    samples = [_passing_sample(0, sample_time="2026-01-01T00:00:00Z")]
    meta = _base_meta(quote_usd_per_token1="1.0")

    # Default allow_bare_quote=False -> fails closed with QUOTE_EVIDENCE_UNPROVENANCED
    conn = _fresh_store(tmp_path, "unprov.db")
    steps = run_episode(
        conn, strategy_episode="unprov", samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode="SHADOW_SCENARIO",
        now_fn=lambda: BASE_SAMPLE_TIME, pool_meta=meta,
    )
    conn.close()
    assert steps[0].nav is None
    assert steps[0].nav_reason == "QUOTE_EVIDENCE_UNPROVENANCED"


def test_ac6_real_pool_meta_200_steps_missing_quote(tmp_path):
    """AC 6: Real pool_meta.json has no quote key -> 200 steps all no NAV, reason QUOTE_EVIDENCE_MISSING."""
    if not REAL_POOL_META_PATH.exists():
        pytest.skip("real pool_meta.json not present")
    with open(REAL_POOL_META_PATH, "r", encoding="utf-8") as fh:
        real_meta = json.load(fh)

    assert "quote_usd_per_token1" not in real_meta, "real pool_meta.json must not yet have quote_usd_per_token1"

    # Try loading real samples from scanner.db, else synthetic samples
    samples = []
    if LIVE_DB.exists():
        src = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True)
        try:
            samples, _ = load_samples_from_db(src, pool=DEFAULT_POOL, limit=200)
        finally:
            src.close()

    if len(samples) < 200:
        samples = [_passing_sample(i) for i in range(200)]

    conn = _fresh_store(tmp_path, "real_run.db")
    steps = run_episode(
        conn, strategy_episode="real_run", samples=samples,
        position_usd=POSITION_USD, horizon_hours=HORIZON_HOURS,
        capital_usd=CAPITAL_USD, target_mode="SHADOW_SCENARIO",
        now_fn=lambda: BASE_SAMPLE_TIME, pool_meta=real_meta,
    )
    summary = episode_summary(steps)
    conn.close()

    assert len(steps) == 200
    assert all(s.nav is None for s in steps)
    assert all(s.hodl_value is None for s in steps)
    assert all(s.nav_reason == "QUOTE_EVIDENCE_MISSING" for s in steps)
    assert summary["steps_without_nav"] == 200
    assert summary["steps_without_nav_reasons"].get("QUOTE_EVIDENCE_MISSING") == 200
