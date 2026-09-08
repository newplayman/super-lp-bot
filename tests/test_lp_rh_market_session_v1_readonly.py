from __future__ import annotations

from datetime import datetime, timezone

from scripts import lp_rh_market_session_v1_readonly as ms

_NOW = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)


def _health(**overrides):
    kwargs = dict(oracle_paused=False, oracle_updated_at=_NOW,
                  api_generated_at=_NOW, now=_NOW, halt=False,
                  corp_action_pending=False, sources_disagree=False,
                  chain_degraded=False)
    kwargs.update(overrides)
    return ms.evaluate_health(**kwargs)


# --- T15: holiday beats RTH -------------------------------------------------
def test_t15_labor_day_holiday_not_rth():
    session, info = ms.classify_session(
        datetime(2026, 9, 7, 14, 30, tzinfo=timezone.utc))
    assert session == "HOLIDAY"
    assert info["calendar_version"] == "nyse-2026-v1"
    assert ms.allows_new_position(session, []) is False


# --- T16: DST-correct ET conversion (no hand-rolled offset) -----------------
def test_t16_dst_start_et_conversion():
    session, info = ms.classify_session(
        datetime(2026, 3, 8, 14, 35, tzinfo=timezone.utc))
    assert info["et_local"] == "2026-03-08T10:35:00-04:00"
    assert session == "WEEKEND"


def test_t16_dst_end_et_conversion():
    session, info = ms.classify_session(
        datetime(2026, 11, 1, 14, 35, tzinfo=timezone.utc))
    assert info["et_local"] == "2026-11-01T09:35:00-05:00"
    assert session == "WEEKEND"


def test_early_close_postmarket_not_rth():
    session, info = ms.classify_session(
        datetime(2026, 11, 27, 18, 30, tzinfo=timezone.utc))
    assert info["is_early_close"] is True
    assert session == "POSTMARKET"


def test_saturday_weekend():
    session, _ = ms.classify_session(
        datetime(2026, 9, 5, 14, 30, tzinfo=timezone.utc))
    assert session == "WEEKEND"


def test_weekday_session_boundaries():
    # 2026-09-08 is a Tuesday (normal trading day, EDT)
    assert ms.classify_session(datetime(2026, 9, 8, 14, 0, tzinfo=timezone.utc))[0] == "RTH"
    assert ms.classify_session(datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc))[0] == "PREMARKET"
    assert ms.classify_session(datetime(2026, 9, 8, 21, 0, tzinfo=timezone.utc))[0] == "POSTMARKET"
    # 2026-09-09 02:00 UTC == 2026-09-08 22:00 ET (Tuesday) -> OVERNIGHT
    assert ms.classify_session(datetime(2026, 9, 9, 2, 0, tzinfo=timezone.utc))[0] == "OVERNIGHT"


def test_classify_session_none_unknown():
    session, info = ms.classify_session(None)
    assert session == "UNKNOWN"
    assert info["et_local"] is None


# --- evaluate_health --------------------------------------------------------
def test_evaluate_health_oracle_paused():
    assert "ORACLE_PAUSED" in _health(oracle_paused=True)


def test_evaluate_health_oracle_unavailable_when_none():
    """RH-02e split absent from stale; this test used to assert ORACLE_STALE.

    An absent oracle and a stale one are different facts: absent is structural
    and needs a policy decision, stale is temporary.  This chain's stock tokens
    reference no on-chain price source at all, so collapsing them made the flag
    permanent and hid the reason.  The gate it protects is unchanged and is
    asserted here too, so this tightens the test rather than loosening it.
    """
    flags = _health(oracle_updated_at=None)
    assert "ORACLE_UNAVAILABLE" in flags
    assert "ORACLE_STALE" not in flags
    assert ms.allows_new_position("RTH", flags) is False


def test_evaluate_health_api_stale_when_none():
    assert "API_STALE" in _health(api_generated_at=None)


def test_evaluate_health_all_normal_empty():
    assert _health() == []


def test_evaluate_health_flags_sorted_and_whitelisted():
    flags = _health(halt=True, oracle_paused=True, chain_degraded=True)
    assert flags == sorted(flags)
    assert set(flags) <= set(ms.HEALTH_FLAGS)


# --- stale_reason -----------------------------------------------------------
def test_stale_reason_all_three_values():
    assert ms.stale_reason("RTH", 7200, 3600) == "STALE_WHILE_EXPECTED_LIVE"
    assert ms.stale_reason("PREMARKET", 7200, 3600) == "EXPECTED_SESSION_CLOSED"
    assert ms.stale_reason("RTH", 100, 3600) == "FRESH"


# --- allows_new_position ----------------------------------------------------
def test_allows_new_position_rth_with_flag_false():
    assert ms.allows_new_position("RTH", ["ORACLE_STALE"]) is False
    assert ms.allows_new_position("RTH", []) is True
    assert ms.allows_new_position("PREMARKET", []) is False


# --- session and flags are two independent values ---------------------------
def test_session_and_flags_are_independent():
    session, info = ms.classify_session(
        datetime(2026, 9, 8, 14, 0, tzinfo=timezone.utc))
    assert isinstance(session, str)
    assert session in ms.SESSIONS
    flags = _health()
    assert isinstance(flags, list)
    assert all(f in ms.HEALTH_FLAGS for f in flags)
    # a closed session can still carry health flags, and vice versa
    assert ms.allows_new_position("RTH", ["HALT"]) is False
    assert ms.allows_new_position("WEEKEND", []) is False


# --- evaluate_health: RFC3339 string + age-based stale path -----------------
def test_evaluate_health_oracle_stale_by_age_string():
    # 2026-09-09T15:00:00Z - 2026-09-09T13:00:00Z = 7200s > 3600s default
    flags = ms.evaluate_health(
        oracle_paused=False, oracle_updated_at="2026-09-09T13:00:00Z",
        api_generated_at="2026-09-09T15:00:00Z", now="2026-09-09T15:00:00Z",
        halt=False, corp_action_pending=False, sources_disagree=False,
        chain_degraded=False)
    assert "ORACLE_STALE" in flags
    # widen the heartbeat to 10800s -> 7200s is fresh, no ORACLE_STALE
    flags_wide = ms.evaluate_health(
        oracle_paused=False, oracle_updated_at="2026-09-09T13:00:00Z",
        api_generated_at="2026-09-09T15:00:00Z", now="2026-09-09T15:00:00Z",
        halt=False, corp_action_pending=False, sources_disagree=False,
        chain_degraded=False, oracle_heartbeat_secs=10800)
    assert "ORACLE_STALE" not in flags_wide


def test_evaluate_health_api_stale_by_age_string():
    # 2026-09-09T15:00:00Z - 2026-09-09T14:50:00Z = 600s > 300s default
    flags = ms.evaluate_health(
        oracle_paused=False, oracle_updated_at="2026-09-09T15:00:00Z",
        api_generated_at="2026-09-09T14:50:00Z", now="2026-09-09T15:00:00Z",
        halt=False, corp_action_pending=False, sources_disagree=False,
        chain_degraded=False)
    assert "API_STALE" in flags
    # widen the api threshold to 900s -> 600s is fresh, no API_STALE
    flags_wide = ms.evaluate_health(
        oracle_paused=False, oracle_updated_at="2026-09-09T15:00:00Z",
        api_generated_at="2026-09-09T14:50:00Z", now="2026-09-09T15:00:00Z",
        halt=False, corp_action_pending=False, sources_disagree=False,
        chain_degraded=False, api_stale_secs=900)
    assert "API_STALE" not in flags_wide


def test_evaluate_health_accepts_datetime_and_string_equivalently():
    oracle_instant = datetime(2026, 9, 9, 13, 0, tzinfo=timezone.utc)
    now_instant = datetime(2026, 9, 9, 15, 0, tzinfo=timezone.utc)
    via_dt = ms.evaluate_health(
        oracle_paused=False, oracle_updated_at=oracle_instant,
        api_generated_at=now_instant, now=now_instant, halt=False,
        corp_action_pending=False, sources_disagree=False,
        chain_degraded=False)
    via_str = ms.evaluate_health(
        oracle_paused=False, oracle_updated_at="2026-09-09T13:00:00Z",
        api_generated_at="2026-09-09T15:00:00Z", now="2026-09-09T15:00:00Z",
        halt=False, corp_action_pending=False, sources_disagree=False,
        chain_degraded=False)
    assert via_dt == via_str
    assert "ORACLE_STALE" in via_str


def test_evaluate_health_naive_datetime_rejected():
    naive = datetime(2026, 9, 9, 13, 0)  # no tzinfo
    try:
        ms.evaluate_health(
            oracle_paused=False, oracle_updated_at=naive,
            api_generated_at="2026-09-09T15:00:00Z",
            now="2026-09-09T15:00:00Z", halt=False,
            corp_action_pending=False, sources_disagree=False,
            chain_degraded=False)
    except ValueError as exc:
        assert "NAIVE_DATETIME" in str(exc)
    else:
        raise AssertionError("expected ValueError for naive datetime")


def test_evaluate_health_bad_timestamp_rejected():
    # no 'T' separator and no UTC offset -> not a valid RFC3339 timestamp
    try:
        ms.evaluate_health(
            oracle_paused=False, oracle_updated_at="2026-09-09 15:00:00",
            api_generated_at="2026-09-09T15:00:00Z",
            now="2026-09-09T15:00:00Z", halt=False,
            corp_action_pending=False, sources_disagree=False,
            chain_degraded=False)
    except ValueError as exc:
        assert "NON_UTC_TIMESTAMP" in str(exc)
    else:
        raise AssertionError("expected ValueError for bad timestamp")


# --- RH-02e: ORACLE_UNAVAILABLE vs ORACLE_STALE -----------------------------
def test_evaluate_health_oracle_unavailable_when_none():
    flags = _health(oracle_updated_at=None)
    assert "ORACLE_UNAVAILABLE" in flags
    assert "ORACLE_STALE" not in flags


def test_evaluate_health_oracle_stale_when_present_but_old():
    # oracle 2h old, default heartbeat 3600s -> stale, not unavailable
    old_oracle = datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)
    flags = _health(oracle_updated_at=old_oracle)
    assert "ORACLE_STALE" in flags
    assert "ORACLE_UNAVAILABLE" not in flags


def test_oracle_unavailable_and_stale_mutually_exclusive():
    old_oracle = datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)
    combos = [
        # (kwargs, expect_unavailable, expect_stale)
        (dict(oracle_updated_at=None), True, False),
        (dict(oracle_updated_at=_NOW), False, False),
        (dict(oracle_updated_at=old_oracle), False, True),
        (dict(oracle_updated_at=None, halt=True), True, False),
    ]
    for kwargs, exp_unavail, exp_stale in combos:
        flags = _health(**kwargs)
        assert ("ORACLE_UNAVAILABLE" in flags) is exp_unavail
        assert ("ORACLE_STALE" in flags) is exp_stale
        # the two oracle flags never appear together
        assert not ("ORACLE_UNAVAILABLE" in flags and "ORACLE_STALE" in flags)


def test_allows_new_position_rth_no_oracle_still_false():
    # regression guard: this package does NOT loosen the gate
    flags = _health(oracle_updated_at=None)
    assert ms.allows_new_position("RTH", flags) is False


def test_allows_new_position_rth_fresh_oracle_true():
    # prove the gate is not constantly False
    flags = _health()  # all fresh, no flags
    assert flags == []
    assert ms.allows_new_position("RTH", flags) is True


def test_stale_reason_rth_none_oracle_age_no_crash():
    assert ms.stale_reason("RTH", None, 3600) == "ORACLE_UNAVAILABLE"


def test_stale_reason_rth_none_heartbeat_no_crash():
    assert ms.stale_reason("RTH", 100, None) == "ORACLE_UNAVAILABLE"


def test_stale_reason_postmarket_none_oracle_age():
    # no oracle is independent of session
    assert ms.stale_reason("POSTMARKET", None, 3600) == "ORACLE_UNAVAILABLE"


def test_stale_reason_original_three_values_regression():
    assert ms.stale_reason("RTH", 7200, 3600) == "STALE_WHILE_EXPECTED_LIVE"
    assert ms.stale_reason("PREMARKET", 7200, 3600) == "EXPECTED_SESSION_CLOSED"
    assert ms.stale_reason("RTH", 100, 3600) == "FRESH"


def test_health_flags_contains_oracle_unavailable_and_whitelist():
    assert "ORACLE_UNAVAILABLE" in ms.HEALTH_FLAGS
    # every flag evaluate_health can return is a member of HEALTH_FLAGS
    for oracle_val in (None, _NOW,
                       datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)):
        flags = _health(oracle_updated_at=oracle_val, halt=True,
                        oracle_paused=True, chain_degraded=True,
                        sources_disagree=True, corp_action_pending=True,
                        api_generated_at=None)
        assert all(f in ms.HEALTH_FLAGS for f in flags)


def test_stock_reference_stale_classification_none_no_crash():
    from scripts import lp_rh_stock_reference_v1_readonly as sr
    # T23 call path: passing None must not raise
    assert sr.stale_classification(session="RTH", oracle_age_secs=None,
                                   heartbeat_secs=3600) == "ORACLE_UNAVAILABLE"
