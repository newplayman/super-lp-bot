from decimal import Decimal, getcontext

import pytest

from scripts.lp_rh_v3_inventory_v1_readonly import inventory_for_position
from scripts.lp_v3_fee_share import position_liquidity_raw


def _relative_error(actual, expected):
    return abs(actual - expected) / abs(expected)


def _standard_position(range_pct=10):
    return inventory_for_position(
        position_usd=Decimal("1000"),
        entry_price=Decimal("2484"),
        range_pct=Decimal(str(range_pct)),
        dec0=18,
        dec1=6,
        quote_usd_per_token1=Decimal("1"),
    )


def test_inventory_reconstructs_position_usd_and_has_two_positive_legs():
    result = _standard_position()

    assert result.amount0_raw > 0
    assert result.amount1_raw > 0
    assert _relative_error(
        result.reconstructed_usd, Decimal("1000")
    ) < Decimal("1e-18")


def test_inventory_is_not_one_to_one_and_matches_independent_values():
    result = _standard_position()

    assert result.amount0_raw != result.amount1_raw
    assert Decimal("1e17") < result.amount0_raw < Decimal("1e18")
    assert Decimal("1e8") < result.amount1_raw < Decimal("1e9")

    assert _relative_error(
        result.liquidity_raw,
        Decimal(
            "205043081922807.99205984882428818144653845292934"
        ),
    ) < Decimal("1e-15")
    assert _relative_error(
        result.amount0_raw,
        Decimal(
            "191457128737724882.53936834449842371736793257181"
        ),
    ) < Decimal("1e-15")
    assert _relative_error(
        result.amount1_raw,
        Decimal(
            "524420492.21549139177220903226591548605805549163"
        ),
    ) < Decimal("1e-15")


def test_token0_usd_share_is_not_fifty_fifty():
    result = _standard_position()

    token0_usd = (
        result.amount0_raw / (Decimal(10) ** 18)
        * Decimal("2484")
    )
    token1_usd = result.amount1_raw / (Decimal(10) ** 6)
    token0_share = token0_usd / (token0_usd + token1_usd)

    assert _relative_error(
        token0_share, Decimal("0.4755795077845086")
    ) < Decimal("1e-15")


def test_liquidity_matches_existing_float_implementation():
    result = _standard_position()
    legacy = Decimal(
        str(position_liquidity_raw(1000.0, 2484.0, 10.0, 18, 6))
    )

    assert _relative_error(result.liquidity_raw, legacy) < Decimal("1e-9")


def test_wider_range_requires_less_liquidity():
    narrow = _standard_position(range_pct=5)
    wide = _standard_position(range_pct=20)

    assert narrow.liquidity_raw > wide.liquidity_raw


def test_decimal_context_is_not_modified():
    before = getcontext().prec
    assert before == 28

    _standard_position()

    assert getcontext().prec == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("position_usd", Decimal("0")),
        ("entry_price", Decimal("0")),
        ("range_pct", Decimal("0")),
    ],
)
def test_non_positive_required_parameters_fail_closed(field, value):
    kwargs = {
        "position_usd": Decimal("1000"),
        "entry_price": Decimal("2484"),
        "range_pct": Decimal("10"),
        "dec0": 18,
        "dec1": 6,
        "quote_usd_per_token1": Decimal("1"),
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=field):
        inventory_for_position(**kwargs)


def test_quote_must_be_explicit_and_positive():
    kwargs = {
        "position_usd": Decimal("1000"),
        "entry_price": Decimal("2484"),
        "range_pct": Decimal("10"),
        "dec0": 18,
        "dec1": 6,
    }

    with pytest.raises(ValueError, match="quote_usd_per_token1"):
        inventory_for_position(**kwargs)

    with pytest.raises(ValueError, match="quote_usd_per_token1"):
        inventory_for_position(
            **kwargs, quote_usd_per_token1=Decimal("0")
        )
