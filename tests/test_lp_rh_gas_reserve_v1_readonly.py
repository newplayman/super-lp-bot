import sys; sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from decimal import Decimal

from scripts import lp_rh_gas_reserve_v1_readonly as mod
from scripts.lp_rh_gas_estimator_v1_readonly import GAS_UNITS, estimate_gas_usd

# Measured anchor inputs (T34/T29): gas price 228372000 wei, native $2484.
GP = 228372000
PRICE = 2484
BURN = GAS_UNITS["v3_burn_collect"]
# Exact wei equivalent of the 3x close-gas reserve: BURN * GP * 3.
REQUIRED_WEI = BURN * GP * 3


# --- T29 core scenario ------------------------------------------------------

def test_t29_weth_rich_native_zero_fails():
    # Plenty of WETH but zero native ETH: the close gas is unfundable.
    result = mod.native_reserve_gate(
        native_balance_wei=0, gas_price_wei=GP, native_price_usd=PRICE,
    )
    assert result["pass"] is False
    assert result["reason"] == "NATIVE_GAS_RESERVE_INSUFFICIENT"


def test_t29_wrapped_does_not_count():
    weth = 10 * 10 ** 18  # 10 ETH worth of WETH
    result = mod.wrapped_does_not_count(weth_balance_wei=weth, native_balance_wei=0)
    assert result["wrapped_usable"] is False


def test_wrapped_native_usable_true():
    result = mod.wrapped_does_not_count(weth_balance_wei=0, native_balance_wei=0)
    assert result["native_usable"] is True


# --- unknown inputs fail closed --------------------------------------------

def test_unknown_balance_fails():
    result = mod.native_reserve_gate(
        native_balance_wei=None, gas_price_wei=GP, native_price_usd=PRICE,
    )
    assert result["pass"] is False
    assert result["reason"] == "NATIVE_BALANCE_UNKNOWN"
    assert result["required_usd"] is None
    assert result["available_usd"] is None
    assert result["shortfall_usd"] is None


def test_unknown_gas_price_fails():
    result = mod.native_reserve_gate(
        native_balance_wei=REQUIRED_WEI, gas_price_wei=None, native_price_usd=PRICE,
    )
    assert result["pass"] is False
    assert result["reason"] == "GAS_ESTIMATE_UNAVAILABLE"


def test_unknown_native_price_fails():
    result = mod.native_reserve_gate(
        native_balance_wei=REQUIRED_WEI, gas_price_wei=GP, native_price_usd=None,
    )
    assert result["pass"] is False
    assert result["reason"] == "GAS_ESTIMATE_UNAVAILABLE"


# --- measured anchor --------------------------------------------------------

def test_measured_anchor_requirement():
    req = mod.exit_gas_requirement_usd(gas_price_wei=GP, native_price_usd=PRICE)
    assert req is not None
    assert Decimal("0.59") < req < Decimal("0.62")


def test_exit_requirement_none_gas_price():
    assert mod.exit_gas_requirement_usd(
        gas_price_wei=None, native_price_usd=PRICE,
    ) is None


def test_exit_requirement_none_native_price():
    assert mod.exit_gas_requirement_usd(
        gas_price_wei=GP, native_price_usd=None,
    ) is None


# --- boundary: exactly enough vs one wei short ------------------------------

def test_balance_equal_requirement_passes():
    result = mod.native_reserve_gate(
        native_balance_wei=REQUIRED_WEI, gas_price_wei=GP, native_price_usd=PRICE,
    )
    assert result["pass"] is True
    assert result["reason"] == "OK"
    assert result["shortfall_usd"] == Decimal(0)


def test_balance_one_wei_short_fails():
    result = mod.native_reserve_gate(
        native_balance_wei=REQUIRED_WEI - 1, gas_price_wei=GP, native_price_usd=PRICE,
    )
    assert result["pass"] is False
    assert result["reason"] == "NATIVE_GAS_RESERVE_INSUFFICIENT"
    assert result["shortfall_usd"] > 0


def test_insufficient_shortfall_is_difference():
    result = mod.native_reserve_gate(
        native_balance_wei=REQUIRED_WEI // 2, gas_price_wei=GP, native_price_usd=PRICE,
    )
    assert result["pass"] is False
    assert result["shortfall_usd"] == result["required_usd"] - result["available_usd"]


# --- multiplier override ----------------------------------------------------

def test_multiplier_override_one():
    single = estimate_gas_usd(gas_price_wei=GP, native_price_usd=PRICE, gas_units=BURN)
    req = mod.exit_gas_requirement_usd(
        gas_price_wei=GP, native_price_usd=PRICE, multiplier=Decimal("1"),
    )
    assert req == single


# --- types and regression ---------------------------------------------------

def test_all_amounts_are_decimal():
    result = mod.native_reserve_gate(
        native_balance_wei=REQUIRED_WEI * 2, gas_price_wei=GP, native_price_usd=PRICE,
    )
    for key in ("required_usd", "available_usd", "shortfall_usd"):
        assert isinstance(result[key], Decimal), key
        assert not isinstance(result[key], float), key


def test_reserve_multiplier_is_three():
    assert mod.RESERVE_MULTIPLIER == Decimal("3")


def test_sufficient_shortfall_is_zero_not_none():
    result = mod.native_reserve_gate(
        native_balance_wei=REQUIRED_WEI * 2, gas_price_wei=GP, native_price_usd=PRICE,
    )
    assert result["pass"] is True
    assert result["shortfall_usd"] is not None
    assert result["shortfall_usd"] == Decimal(0)


def test_available_usd_is_balance_times_price():
    balance = REQUIRED_WEI * 2
    result = mod.native_reserve_gate(
        native_balance_wei=balance, gas_price_wei=GP, native_price_usd=PRICE,
    )
    expected = Decimal(balance) / (Decimal(10) ** 18) * Decimal(str(PRICE))
    assert result["available_usd"] == expected


# --- finite and sign validation --------------------------------------------

def _assert_input_unavailable(result, parameter):
    assert result["pass"] is False
    assert result["reason"] == f"INPUTS_UNAVAILABLE: {parameter}"
    assert result["required_usd"] is None
    assert result["available_usd"] is None
    assert result["shortfall_usd"] is None


def test_infinite_balance_fails_closed():
    result = mod.native_reserve_gate(
        native_balance_wei=Decimal("Infinity"),
        gas_price_wei=GP,
        native_price_usd=PRICE,
    )
    _assert_input_unavailable(result, "native_balance_wei")


def test_nan_balance_fails_closed():
    result = mod.native_reserve_gate(
        native_balance_wei=Decimal("NaN"),
        gas_price_wei=GP,
        native_price_usd=PRICE,
    )
    _assert_input_unavailable(result, "native_balance_wei")


def test_negative_balance_fails_closed():
    result = mod.native_reserve_gate(
        native_balance_wei=Decimal("-1"),
        gas_price_wei=GP,
        native_price_usd=PRICE,
    )
    _assert_input_unavailable(result, "native_balance_wei")


def test_invalid_native_prices_fail_closed():
    for bad_price in (Decimal("Infinity"), Decimal("NaN"), Decimal("0"), Decimal("-1")):
        result = mod.native_reserve_gate(
            native_balance_wei=REQUIRED_WEI,
            gas_price_wei=GP,
            native_price_usd=bad_price,
        )
        _assert_input_unavailable(result, "native_price_usd")


def test_invalid_gas_prices_fail_closed():
    for bad_price in (Decimal("Infinity"), Decimal("NaN"), Decimal("0"), Decimal("-1")):
        result = mod.native_reserve_gate(
            native_balance_wei=REQUIRED_WEI,
            gas_price_wei=bad_price,
            native_price_usd=PRICE,
        )
        _assert_input_unavailable(result, "gas_price_wei")


def test_invalid_multiplier_fails_closed():
    for bad_multiplier in (Decimal("Infinity"), Decimal("NaN"), Decimal("0"), Decimal("-1")):
        result = mod.native_reserve_gate(
            native_balance_wei=REQUIRED_WEI,
            gas_price_wei=GP,
            native_price_usd=PRICE,
            multiplier=bad_multiplier,
        )
        _assert_input_unavailable(result, "multiplier")
        assert mod.exit_gas_requirement_usd(
            gas_price_wei=GP,
            native_price_usd=PRICE,
            multiplier=bad_multiplier,
        ) is None


def test_exit_requirement_rejects_nonfinite_inputs():
    assert mod.exit_gas_requirement_usd(
        gas_price_wei=Decimal("Infinity"),
        native_price_usd=PRICE,
    ) is None
    assert mod.exit_gas_requirement_usd(
        gas_price_wei=GP,
        native_price_usd=Decimal("NaN"),
    ) is None
    assert mod.exit_gas_requirement_usd(
        gas_price_wei=GP,
        native_price_usd=Decimal("0"),
    ) is None


def test_wrapped_validates_native_only():
    """The whole point of this function is that WETH does not count, so a
    WETH balance it refuses to look at cannot make it fail.  RH-02an
    validated both legs and broke that: weth_balance_wei=None started
    returning pass=False.  Only native_balance_wei is validated here.
    """
    baseline = mod.wrapped_does_not_count(weth_balance_wei=0, native_balance_wei=0)

    for junk in (Decimal("Infinity"), Decimal("-1"), None):
        result = mod.wrapped_does_not_count(
            weth_balance_wei=junk,
            native_balance_wei=0,
        )
        assert result == baseline, f"WETH {junk!r} changed a WETH-agnostic result"
        assert result["wrapped_usable"] is False

    # The schema is now the stable three keys, so an unusable native balance
    # shows up as native_usable=False rather than a pass/reason pair.  That
    # keeps the shape uniform but drops the reason: a caller can tell that
    # something was wrong, not what.  Distinguishability itself is what the
    # next two assertions pin down.
    invalid = mod.wrapped_does_not_count(
        weth_balance_wei=0,
        native_balance_wei=Decimal("NaN"),
    )
    assert invalid["native_usable"] is False
    assert set(invalid) == {"native_usable", "wrapped_usable", "note"}

    zero = mod.wrapped_does_not_count(weth_balance_wei=0, native_balance_wei=0)
    assert zero["native_usable"] is True
    assert invalid != zero, "a malformed balance must not look like a zero one"


# --- normal-input regression snapshots -------------------------------------

def test_normal_native_gate_result_is_unchanged():
    result = mod.native_reserve_gate(
        native_balance_wei=REQUIRED_WEI,
        gas_price_wei=GP,
        native_price_usd=PRICE,
    )
    assert result == {
        "pass": True,
        "required_usd": Decimal("0.5956398504"),
        "available_usd": Decimal("0.5956398504"),
        "shortfall_usd": Decimal("0"),
        "reason": "OK",
    }


def test_normal_exit_requirement_is_unchanged():
    assert mod.exit_gas_requirement_usd(
        gas_price_wei=GP,
        native_price_usd=PRICE,
    ) == Decimal("0.5956398504")


def test_normal_wrapped_result_is_unchanged():
    assert mod.wrapped_does_not_count(
        weth_balance_wei=10 * 10 ** 18,
        native_balance_wei=0,
    ) == {
        "native_usable": True,
        "wrapped_usable": False,
        "note": (
            "WETH is an ERC-20 and cannot pay gas; only native ETH counts "
            "toward the gas reserve (T29). weth_balance_wei is ignored on "
            "purpose."
        ),
    }


def test_wrapped_ignores_missing_or_nonfinite_weth_balance():
    expected = mod.wrapped_does_not_count(
        weth_balance_wei=0,
        native_balance_wei=0,
    )
    for weth_balance in (None, Decimal("Infinity"), Decimal("NaN"), "bad"):
        assert mod.wrapped_does_not_count(
            weth_balance_wei=weth_balance,
            native_balance_wei=0,
        ) == expected
    assert mod.wrapped_does_not_count(native_balance_wei=0) == expected


def test_wrapped_invalid_native_balance_keeps_stable_schema():
    result = mod.wrapped_does_not_count(
        weth_balance_wei=10 * 10 ** 18,
        native_balance_wei=Decimal("NaN"),
    )
    assert result == {
        "native_usable": False,
        "wrapped_usable": False,
        "note": (
            "WETH is an ERC-20 and cannot pay gas; only native ETH counts "
            "toward the gas reserve (T29). weth_balance_wei is ignored on "
            "purpose."
        ),
    }

