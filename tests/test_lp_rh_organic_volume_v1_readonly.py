import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from decimal import Decimal

from scripts.lp_rh_organic_volume_v1_readonly import (
    apply_organic_haircut,
    organic_volume_estimate,
    participant_concentration,
    round_trip_volume,
    swap_direction,
)


def event(sender, block, amount1, direction="BUY0"):
    if direction == "BUY0":
        amount0 = -abs(Decimal(str(amount1)))
        token1 = abs(Decimal(str(amount1)))
    else:
        amount0 = abs(Decimal(str(amount1)))
        token1 = -abs(Decimal(str(amount1)))
    return {
        "block": block,
        "tx_hash": f"0x{block}",
        "log_index": 0,
        "sender": sender,
        "recipient": "0xpool",
        "amount0": amount0,
        "amount1": token1,
    }


def test_swap_direction_buy0():
    assert swap_direction(event("a", 1, 2, "BUY0")) == "BUY0"


def test_swap_direction_sell0():
    assert swap_direction(event("a", 1, 2, "SELL0")) == "SELL0"


def test_swap_direction_same_sign_is_none():
    assert swap_direction({"amount0": "1", "amount1": "2"}) is None


def test_swap_direction_missing_amount_is_none():
    assert swap_direction({"amount0": "-1", "amount1": None}) is None


def test_hundred_unique_senders_are_organic():
    events = [event(f"0x{i:040x}", i, 1, "BUY0" if i % 2 else "SELL0") for i in range(100)]
    result = organic_volume_estimate(events)
    concentration = participant_concentration(events)
    assert result["status"] == "COMPUTED"
    assert result["organic_fraction"] > Decimal("0.9")
    assert concentration["hhi"] < Decimal("0.02")
    assert Decimal("0") <= result["organic_fraction"] <= Decimal("1")


def test_single_sender_strict_alternation_is_wash_volume():
    events = [event("0xwash", i, 3, "BUY0" if i % 2 == 0 else "SELL0") for i in range(60)]
    result = organic_volume_estimate(events)
    pairs = round_trip_volume(events)
    assert pairs["pair_count"] == 30
    assert pairs["round_trip_share"] > Decimal("0.99")
    assert result["organic_fraction"] < Decimal("0.01")
    assert Decimal("0") <= result["organic_fraction"] <= Decimal("1")


def test_single_sender_eighty_percent_has_concentration_excess():
    events = [event("0xwhale", i, 2) for i in range(40)]
    events += [event(f"0xsmall{i}", 40 + i, 2) for i in range(10)]
    result = organic_volume_estimate(events)
    assert result["concentration_excess_volume"] > Decimal("0")
    assert result["organic_fraction"] < Decimal("0.5")
    assert Decimal("0") <= result["organic_fraction"] <= Decimal("1")


def test_round_trip_and_concentration_never_double_count():
    events = [event("0xlarge", i, 5, "BUY0" if i % 2 == 0 else "SELL0") for i in range(20)]
    events += [event("0xlarge", 20 + i, 1, "BUY0") for i in range(40)]
    result = organic_volume_estimate(events)
    assert result["round_trip_volume"] + result["concentration_excess_volume"] <= result["total_volume"]
    assert Decimal("0") <= result["organic_fraction"] <= Decimal("1")


def test_window_blocks_excludes_distant_pair():
    events = [event("0x1", 100, 4, "BUY0"), event("0x1", 151, 4, "SELL0")]
    result = round_trip_volume(events, window_blocks=50)
    assert result["pair_count"] == 0
    assert result["round_trip_volume"] == Decimal("0")


def test_addresses_are_case_insensitive():
    events = [event("0xAB", 1, 4, "BUY0"), event("0xab", 2, 4, "SELL0")]
    concentration = participant_concentration(events)
    pairs = round_trip_volume(events)
    assert concentration["n_unique_senders"] == 1
    assert pairs["pair_count"] == 1


def test_forty_nine_events_are_insufficient():
    events = [event(f"0x{i:040x}", i, 1) for i in range(49)]
    result = organic_volume_estimate(events)
    assert result["n_events"] == 49
    assert result["status"] == "INSUFFICIENT_SAMPLES"
    assert result["organic_fraction"] is None


def test_empty_participant_input_has_none_shares():
    result = participant_concentration([])
    assert result["status"] == "INPUTS_UNAVAILABLE"
    assert result["top1_share"] is None
    assert result["top5_share"] is None
    assert result["hhi"] is None


def test_empty_round_trip_input_has_none_volumes():
    result = round_trip_volume([])
    assert result["status"] == "INPUTS_UNAVAILABLE"
    assert result["round_trip_volume"] is None
    assert result["total_volume"] is None
    assert result["round_trip_share"] is None


def test_empty_organic_input_is_unavailable():
    result = organic_volume_estimate([])
    assert result["status"] == "INPUTS_UNAVAILABLE"
    assert result["organic_fraction"] is None
    assert result["total_volume"] is None


def test_haircut_does_not_passthrough_missing_fraction():
    assert apply_organic_haircut(Decimal("27.34"), None) is None


def test_haircut_multiplies_decimal_values():
    assert apply_organic_haircut(Decimal("27.34"), Decimal("0.2")) == Decimal("5.468")


def test_haircut_missing_fee_is_none():
    assert apply_organic_haircut(None, Decimal("0.2")) is None


def test_concentration_top_shares_and_hhi():
    events = [event("a", 1, 3), event("b", 2, 1), event("c", 3, 1)]
    result = participant_concentration(events)
    assert result["top1_share"] == Decimal("0.6")
    assert result["top5_share"] == Decimal("1")
    assert result["hhi"] == Decimal("0.44")


def test_round_trip_uses_smaller_leg_conservatively():
    events = [event("a", 1, 10, "BUY0"), event("a", 2, 4, "SELL0")]
    result = round_trip_volume(events)
    assert result["pair_count"] == 1
    assert result["round_trip_volume"] == Decimal("8")
    assert result["total_volume"] == Decimal("14")


def test_unmatched_direction_is_not_paired():
    events = [event("a", 1, 2, "BUY0"), event("a", 2, 2, "BUY0")]
    result = round_trip_volume(events)
    assert result["pair_count"] == 0
    assert result["round_trip_share"] == Decimal("0")


def test_each_event_is_used_at_most_once():
    events = [
        event("a", 1, 3, "BUY0"),
        event("a", 2, 2, "SELL0"),
        event("a", 3, 1, "SELL0"),
    ]
    result = round_trip_volume(events)
    assert result["pair_count"] == 1
    assert result["round_trip_volume"] == Decimal("4")


def test_organic_estimate_keeps_counts_for_insufficient_samples():
    events = [event("a", i, 1) for i in range(3)]
    result = organic_volume_estimate(events, min_events=4)
    assert result["n_events"] == 3
    assert result["n_unique_senders"] == 1
    assert result["status"] == "INSUFFICIENT_SAMPLES"
    assert result["organic_fraction"] is None


def test_no_concentration_excess_below_threshold():
    events = [event(f"0x{i}", i, 1) for i in range(4)]
    result = organic_volume_estimate(events, min_events=1)
    assert result["concentration_excess_volume"] == Decimal("0")
    assert result["organic_volume"] == result["total_volume"]


def test_decimal_like_string_amounts_are_supported():
    events = [
        {"sender": "A", "block": 1, "amount0": "-1.5", "amount1": "1.5"},
        {"sender": "B", "block": 2, "amount0": "1.5", "amount1": "-1.5"},
    ]
    result = participant_concentration(events)
    assert result["top1_share"] == Decimal("0.5")


def test_direction_zero_is_invalid():
    assert swap_direction({"amount0": "0", "amount1": "1"}) is None


def test_round_trip_share_is_bounded():
    events = [event("a", i, 1, "BUY0" if i % 2 == 0 else "SELL0") for i in range(52)]
    result = round_trip_volume(events)
    assert Decimal("0") <= result["round_trip_share"] <= Decimal("1")
