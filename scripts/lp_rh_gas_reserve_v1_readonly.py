#!/usr/bin/env python3
"""RH native-ETH gas-reserve gate: keep a position closable (read-only, offline).

T29 forensics: no gate anywhere compares a native ETH balance against a gas
reserve requirement.  WETH is an ERC-20 and cannot pay gas; if opening a
position swaps all native ETH into WETH (and USDG) inside the pool, the gas
needed to close the position is unfundable -- the position can no longer be
closed and can only be watched drifting.  This is the only one of the four
audited gaps that traps capital.

The requirement is derived from the real cost estimator
(``scripts.lp_rh_gas_estimator_v1_readonly``), not a hard-coded constant:
reserve = one close (v3_burn_collect) gas cost x RESERVE_MULTIPLIER.  The
multiplier is a conservative starting point, not a measured calibration.

All money is ``Decimal``.  No I/O beyond the file named on the command line.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_gas_estimator_v1_readonly import (  # noqa: E402
    GAS_UNITS,
    estimate_gas_usd,
)

# Reserve = one close gas x this multiplier.  Closing can fail (slippage
# protection) and need a retry, and gas price moves; 3x is a conservative
# starting point, NOT a measured/calibrated value.
RESERVE_MULTIPLIER = Decimal("3")

_E18 = Decimal(10) ** 18

_WETH_GAS_NOTE = (
    "WETH is an ERC-20 and cannot pay gas; only native ETH counts "
    "toward the gas reserve (T29). weth_balance_wei is ignored on "
    "purpose."
)


def _input_unavailable_result(parameter: str) -> dict:
    """Return the standard fail-closed result for an invalid numeric input."""
    return {
        "pass": False,
        "required_usd": None,
        "available_usd": None,
        "shortfall_usd": None,
        "reason": f"INPUTS_UNAVAILABLE: {parameter}",
    }


def _wrapped_input_unavailable_result(parameter: str) -> dict:
    """Return the wrapped/native invariant result for invalid input."""
    return {
        "pass": False,
        "native_usable": False,
        "wrapped_usable": False,
        "note": _WETH_GAS_NOTE,
        "reason": f"INPUTS_UNAVAILABLE: {parameter}",
    }


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Coerce int/float/str/Decimal to Decimal; None/bool/bad input -> None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    try:
        return Decimal(str(value))
    except Exception:
        return None


def exit_gas_requirement_usd(
    *,
    gas_price_wei: Any,
    native_price_usd: Any,
    multiplier: Any = RESERVE_MULTIPLIER,
) -> Optional[Decimal]:
    """USD needed to pay ONE close (v3_burn_collect) gas, x multiplier.

    Only the close is counted -- at open time the funds are still in hand, so
    the open (v3_mint) cost is deliberately excluded.  Returns None (never 0)
    when any input is missing, non-finite, or non-positive.
    """
    gas_price = _to_decimal(gas_price_wei)
    native_price = _to_decimal(native_price_usd)
    mult = _to_decimal(multiplier)
    if (
        gas_price is None
        or not gas_price.is_finite()
        or gas_price <= 0
        or native_price is None
        or not native_price.is_finite()
        or native_price <= 0
        or mult is None
        or not mult.is_finite()
        or mult <= 0
    ):
        return None

    try:
        single = estimate_gas_usd(
            gas_price_wei=gas_price,
            native_price_usd=native_price,
            gas_units=GAS_UNITS["v3_burn_collect"],
        )
        if single is None or not single.is_finite():
            return None
        result = single * mult
    except Exception:
        return None

    return result if result.is_finite() else None


def native_reserve_gate(
    *,
    native_balance_wei: Any,
    gas_price_wei: Any,
    native_price_usd: Any,
    multiplier: Any = RESERVE_MULTIPLIER,
) -> dict:
    """Decide whether the native balance can fund the close-gas reserve.

    Returns {"pass", "required_usd", "available_usd", "shortfall_usd",
    "reason"}.  An unknown balance fails (never treated as sufficient);
    unknown gas inputs fail; non-finite and sign-invalid numeric inputs fail
    with INPUTS_UNAVAILABLE.  ``shortfall_usd`` is a positive Decimal when
    insufficient and ``Decimal(0)`` when sufficient (0 is distinct from
    None/unknown).
    """
    balance = _to_decimal(native_balance_wei)
    if balance is None:
        return {
            "pass": False,
            "required_usd": None,
            "available_usd": None,
            "shortfall_usd": None,
            "reason": "NATIVE_BALANCE_UNKNOWN",
        }
    if not balance.is_finite() or balance < 0:
        return _input_unavailable_result("native_balance_wei")

    gas_price = _to_decimal(gas_price_wei)
    if gas_price is None:
        return {
            "pass": False,
            "required_usd": None,
            "available_usd": None,
            "shortfall_usd": None,
            "reason": "GAS_ESTIMATE_UNAVAILABLE",
        }
    if not gas_price.is_finite() or gas_price <= 0:
        return _input_unavailable_result("gas_price_wei")

    price = _to_decimal(native_price_usd)
    if price is None:
        return {
            "pass": False,
            "required_usd": None,
            "available_usd": None,
            "shortfall_usd": None,
            "reason": "GAS_ESTIMATE_UNAVAILABLE",
        }
    if not price.is_finite() or price <= 0:
        return _input_unavailable_result("native_price_usd")

    mult = _to_decimal(multiplier)
    if mult is None:
        return {
            "pass": False,
            "required_usd": None,
            "available_usd": None,
            "shortfall_usd": None,
            "reason": "GAS_ESTIMATE_UNAVAILABLE",
        }
    if not mult.is_finite() or mult <= 0:
        return _input_unavailable_result("multiplier")

    required = exit_gas_requirement_usd(
        gas_price_wei=gas_price,
        native_price_usd=price,
        multiplier=mult,
    )
    if required is None:
        return {
            "pass": False,
            "required_usd": None,
            "available_usd": None,
            "shortfall_usd": None,
            "reason": "GAS_ESTIMATE_UNAVAILABLE",
        }
    if not required.is_finite():
        return _input_unavailable_result("gas_price_wei")

    try:
        available = balance / _E18 * price
    except Exception:
        return _input_unavailable_result("native_balance_wei")

    if not available.is_finite():
        return _input_unavailable_result("native_balance_wei")

    if available < required:
        try:
            shortfall = required - available
        except Exception:
            return _input_unavailable_result("native_balance_wei")

        if not shortfall.is_finite():
            return _input_unavailable_result("native_balance_wei")

        return {
            "pass": False,
            "required_usd": required,
            "available_usd": available,
            "shortfall_usd": shortfall,
            "reason": "NATIVE_GAS_RESERVE_INSUFFICIENT",
        }

    return {
        "pass": True,
        "required_usd": required,
        "available_usd": available,
        "shortfall_usd": Decimal(0),
        "reason": "OK",
    }


def wrapped_does_not_count(*, weth_balance_wei: Any, native_balance_wei: Any) -> dict:
    """WETH cannot pay gas -- the core T29 semantic, made checkable.

    Gas on EVM chains is paid in the native coin only.  WETH is an ERC-20
    token; however large ``weth_balance_wei`` is, it contributes nothing to
    the gas reserve.  This function states that invariant explicitly and
    NEVER folds WETH into any usable balance: ``wrapped_usable`` is always
    False, and ``native_usable`` records that the native coin is the only
    gas-paying asset class.
    """
    weth_balance = _to_decimal(weth_balance_wei)
    if (
        weth_balance is None
        or not weth_balance.is_finite()
        or weth_balance < 0
    ):
        return _wrapped_input_unavailable_result("weth_balance_wei")

    native_balance = _to_decimal(native_balance_wei)
    if (
        native_balance is None
        or not native_balance.is_finite()
        or native_balance < 0
    ):
        return _wrapped_input_unavailable_result("native_balance_wei")

    return {
        "native_usable": True,
        "wrapped_usable": False,
        "note": _WETH_GAS_NOTE,
    }


def _json_safe(value: Any) -> Any:
    """Decimal -> str to preserve precision; recurse into containers."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Native ETH gas-reserve gate (offline, read-only)."
    )
    parser.add_argument("--native-balance-wei", required=True, type=int)
    parser.add_argument("--gas-price-wei", required=True, type=int)
    parser.add_argument("--native-price-usd", required=True)
    parser.add_argument("--out", help="output path; defaults to stdout")
    args = parser.parse_args(argv)
    result = native_reserve_gate(
        native_balance_wei=args.native_balance_wei,
        gas_price_wei=args.gas_price_wei,
        native_price_usd=args.native_price_usd,
    )
    payload = json.dumps(_json_safe(result), indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(payload + "\n")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

