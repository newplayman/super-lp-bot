from decimal import Decimal, getcontext
from decimal import localcontext

import pytest

from scripts.lp_rh_v3_inventory_v1_readonly import inventory_for_position
from scripts.lp_rh_v3_inventory_v1_readonly import position_value_at
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


def _standard_liquidity_human():
    with localcontext() as ctx:
        ctx.prec = 80
        return _standard_position().liquidity_raw / (Decimal(10) ** 12)


def _standard_mark(price):
    return position_value_at(
        price=price,
        liquidity_human=_standard_liquidity_human(),
        entry_price=Decimal("2484"),
        range_pct=Decimal("10"),
        quote_usd_per_token1=Decimal("1"),
    )


def _assert_mark_close(actual, expected):
    if expected == 0:
        assert actual == expected
    else:
        assert _relative_error(actual, expected) < Decimal("1e-25")


@pytest.mark.parametrize(
    (
        "price",
        "expected_value_usd",
        "expected_amount0_human",
        "expected_amount1_human",
    ),
    [
        (
            Decimal("2484"),
            Decimal("1000"),
            Decimal(
                "0.19145712873772488253936834449842371736793257180588"
            ),
            Decimal(
                "524.42049221549139177220903226591548605805549163421"
            ),
        ),
        (
            Decimal("2474.055679"),
            Decimal(
                "998.05506101569517744962307444767141901132021256836"
            ),
            Decimal(
                "0.19971692330763781371243527892716317242894531930221"
            ),
            Decimal(
                "503.94427271402638035922849969797434490383182136826"
            ),
        ),
        (
            Decimal("2235.6"),
            Decimal(
                "925.53051912632391929181381822363713956594958075681"
            ),
            Decimal(
                "0.41399647482837892256746010834837946840487993413706"
            ),
            Decimal("0"),
        ),
        (
            Decimal("2732.4"),
            Decimal(
                "1023.2124879882894863806499472872990837981715472935"
            ),
            Decimal("0"),
            Decimal(
                "1023.2124879882894863806499472872990837981715472935"
            ),
        ),
        (
            Decimal("1000"),
            Decimal(
                "413.99647482837892256746010834837946840487993413706"
            ),
            Decimal(
                "0.41399647482837892256746010834837946840487993413706"
            ),
            Decimal("0"),
        ),
        (
            Decimal("5000"),
            Decimal(
                "1023.2124879882894863806499472872990837981715472935"
            ),
            Decimal("0"),
            Decimal(
                "1023.2124879882894863806499472872990837981715472935"
            ),
        ),
    ],
)
def test_position_value_matches_v3_anchors(
    price,
    expected_value_usd,
    expected_amount0_human,
    expected_amount1_human,
):
    result = _standard_mark(price)

    value_tolerance = (
        Decimal("1e-40")
        if price == Decimal("2484")
        else Decimal("1e-25")
    )
    assert _relative_error(
        result.value_usd, expected_value_usd
    ) < value_tolerance
    _assert_mark_close(result.amount0_human, expected_amount0_human)
    _assert_mark_close(result.amount1_human, expected_amount1_human)


def test_position_value_freezes_amounts_outside_range():
    at_lower = _standard_mark(Decimal("2235.6"))
    below_lower = _standard_mark(Decimal("1000"))
    at_upper = _standard_mark(Decimal("2732.4"))
    above_upper = _standard_mark(Decimal("5000"))

    assert below_lower.amount0_human == at_lower.amount0_human
    assert above_upper.amount1_human == at_upper.amount1_human


def test_position_value_has_negative_exposure_gap_vs_hodl():
    p0 = _standard_mark(Decimal("2484"))
    p1 = _standard_mark(Decimal("2474.055679"))

    lp_delta = p1.value_usd - p0.value_usd
    hodl_delta = (
        p0.amount0_human * Decimal("2474.055679")
        + p0.amount1_human
        - p0.amount0_human * Decimal("2484")
        - p0.amount1_human
    )

    assert lp_delta < hodl_delta
    assert lp_delta - hodl_delta < Decimal("-1e-15")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quote_usd_per_token1", None),
        ("price", Decimal("0")),
        ("liquidity_human", Decimal("0")),
        ("range_pct", Decimal("0")),
    ],
)
def test_position_value_rejects_invalid_inputs(field, value):
    kwargs = {
        "price": Decimal("2484"),
        "liquidity_human": _standard_liquidity_human(),
        "entry_price": Decimal("2484"),
        "range_pct": Decimal("10"),
        "quote_usd_per_token1": Decimal("1"),
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=field):
        position_value_at(**kwargs)


def test_position_value_does_not_modify_decimal_context():
    before = getcontext().prec
    assert before == 28

    _standard_mark(Decimal("2474.055679"))

    assert getcontext().prec == before
