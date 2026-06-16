import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.lp_v3_position_value import (
    lp_hodl_value_usd,
    lp_impermanent_loss_usd,
    lp_mtm_usd,
    lp_position_value_usd,
)


def test_value_at_entry_equals_size():
    v = lp_position_value_usd(1000, 1675.6, 2, 1675.6)
    assert abs(v - 1000) < 1e-6


def test_mtm_at_entry_is_zero():
    m = lp_mtm_usd(1000, 1675.6, 2, 1675.6)
    assert abs(m) < 1e-6


def test_il_at_entry_is_zero():
    il = lp_impermanent_loss_usd(1000, 1675.6, 2, 1675.6)
    assert abs(il) < 1e-6


def test_monotonic_in_price():
    v1 = lp_position_value_usd(1000, 1675.6, 2, 1500)
    v2 = lp_position_value_usd(1000, 1675.6, 2, 1675.6)
    v3 = lp_position_value_usd(1000, 1675.6, 2, 1850)
    assert v1 < v2 < v3


def test_above_range_plateau():
    v1 = lp_position_value_usd(1000, 1675.6, 2, 1709.2)
    v2 = lp_position_value_usd(1000, 1675.6, 2, 5000)
    assert abs(v1 - v2) < 1e-6


def test_il_non_positive_in_range():
    il = lp_impermanent_loss_usd(1000, 1675.6, 2, 1750)
    assert il <= 1e-9


def test_hedge_offset_sanity():
    m = lp_mtm_usd(1000, 1675.6, 2, 1778.9)
    assert m > 0
    assert m < 20


def test_guard_negative_entry_price():
    assert lp_position_value_usd(1000, -1, 2, 1700) == 0.0
    assert lp_hodl_value_usd(1000, -1, 1700) == 0.0
    assert lp_mtm_usd(1000, -1, 2, 1700) == 0.0 - 1000


def test_guard_zero_size():
    assert lp_position_value_usd(0, 1675.6, 2, 1700) == 0.0
    assert lp_hodl_value_usd(0, 1675.6, 1700) == 0.0
