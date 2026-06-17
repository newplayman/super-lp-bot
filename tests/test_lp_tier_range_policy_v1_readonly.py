"""Pure tests for the Tier range-policy decision layer (no network)."""
from scripts.lp_tier_range_policy_v1_readonly import (
    efficiency_ratio,
    classify_regime,
    choose_h,
    build_policy,
    fee_cover_ratio,
    finalize_action,
    H_RANGE_BOUND,
    H_TRENDING,
)


def test_efficiency_ratio_trend_vs_chop():
    trend = [(i, 1.0 * (1.02 ** i)) for i in range(24)]
    chop = [(i, 1.0 + (0.05 if i % 2 else -0.05)) for i in range(24)]
    er_t = efficiency_ratio(trend)
    er_c = efficiency_ratio(chop)
    assert er_t > 0.95          # monotonic => efficient => trend
    assert er_c < 0.25          # whipsaw => inefficient => range-bound
    assert er_t > er_c


def test_efficiency_ratio_guards():
    assert efficiency_ratio([]) is None
    assert efficiency_ratio([(0, 1.0)]) is None
    assert efficiency_ratio([(0, 1.0), (1, 1.0)]) is None  # zero path


def test_classify_regime_bands():
    assert classify_regime(0.1) == "range-bound"
    assert classify_regime(0.35) == "neutral"
    assert classify_regime(0.8) == "trending"
    assert classify_regime(None) == "unknown"


def test_choose_h_monotonic():
    assert choose_h("range-bound") == H_RANGE_BOUND
    assert choose_h("trending") == H_TRENDING
    assert choose_h("range-bound") < choose_h("trending")


def test_build_policy_range_bound_allows_weekly():
    p = build_policy(0.03, 0.1)   # low ER => range-bound
    assert p["regime"] == "range-bound"
    assert p["weekly_tight_allowed"] is True
    assert p["H_days"] == H_RANGE_BOUND
    assert p["action"] == "ENTER"


def test_build_policy_high_vol_trend_avoids():
    p = build_policy(0.08, 0.9)   # high vol + strong trend
    assert p["regime"] == "trending"
    assert p["weekly_tight_allowed"] is False
    assert p["action"] == "AVOID"


def test_build_policy_low_vol_trend_wide_only():
    p = build_policy(0.02, 0.9)   # trend but low vol
    assert p["action"] == "ENTER_WIDE_ONLY"
    assert p["H_days"] == H_TRENDING
    assert p["weekly_tight_allowed"] is False


def test_trending_range_wider_than_range_bound():
    rb = build_policy(0.03, 0.1)["range_pct"]
    tr = build_policy(0.03, 0.9)["range_pct"]
    assert tr > rb   # trending uses larger H => wider range


def test_fee_cover_ratio():
    assert fee_cover_ratio(0.02, -0.01) == 2.0      # fees 2x the IL
    assert fee_cover_ratio(0.005, -0.01) == 0.5     # fees half the IL
    assert fee_cover_ratio(0.01, 0.0) == float("inf")  # no IL
    assert fee_cover_ratio(None, -0.01) is None


def test_finalize_action_fee_lt_il_avoids():
    pol = build_policy(0.03, 0.1)            # range-bound ENTER
    act, _ = finalize_action(pol, fee_cover=0.5, abs_move_pct=3.0)
    assert act == "AVOID_FEE<IL"             # fees don't cover IL -> AVOID


def test_finalize_action_enters_when_fees_cover():
    pol = build_policy(0.03, 0.1)
    act, _ = finalize_action(pol, fee_cover=2.0, abs_move_pct=3.0)
    assert act == "ENTER"


def test_finalize_action_directional_avoid_for_tier_a():
    pol = build_policy(0.03, 0.1)
    act, _ = finalize_action(pol, fee_cover=2.0, abs_move_pct=20.0, tier_hint="A")
    assert act == "AVOID_DIRECTIONAL"        # too directional for a Tier-A pair


def test_finalize_action_directional_ok_for_tier_b():
    pol = build_policy(0.03, 0.1)
    act, reason = finalize_action(pol, fee_cover=2.0, abs_move_pct=20.0, tier_hint="B")
    assert act == "ENTER"                     # B accepts the directional bet
    assert "directional" in reason.lower()


def test_finalize_preserves_high_vol_trend_avoid():
    pol = build_policy(0.08, 0.9)            # already AVOID (high-vol trend)
    act, _ = finalize_action(pol, fee_cover=5.0, abs_move_pct=2.0)
    assert act == "AVOID"
