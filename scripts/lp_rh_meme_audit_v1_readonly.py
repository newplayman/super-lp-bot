#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path("/opt/lpbot/lp-bot-v3-origin-check")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_store_v1_readonly import assert_decimal_text  # noqa: E402
MAX_LP_CONCENTRATION_BPS = Decimal("5000")
MAX_LP_CONCENTRATION_PCT = Decimal("50")
MAX_LP_CONCENTRATION_RATIO = Decimal("0.50")


def _lookup(facts: Mapping[str, Any], keys: Sequence[str]) -> tuple[bool, Any]:
    sections = [facts]
    for name in ("security", "permissions", "exit", "liquidity", "holders", "evidence"):
        value = facts.get(name)
        if isinstance(value, Mapping):
            sections.append(value)
    for section in sections:
        for key in keys:
            if key in section:
                return True, section[key]
    return False, None
def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"REAL_NOT_ALLOWED_FOR_MONEY: {field}")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"INVALID_DECIMAL_TEXT: {field}") from exc
    raise TypeError(f"REAL_NOT_ALLOWED_FOR_MONEY: {field}")
def _unknown_or_bool(
    facts: Mapping[str, Any], keys: Sequence[str], unknown_name: str,
) -> tuple[bool | None, str | None]:
    found, value = _lookup(facts, keys)
    if not found or value is None:
        return None, f"UNKNOWN_{unknown_name}"
    if not isinstance(value, bool):
        return None, f"UNKNOWN_{unknown_name}"
    return value, None
def _concentration_result(facts: Mapping[str, Any]) -> tuple[bool | None, str | None]:
    found, value = _lookup(facts, (
        "lp_concentration_over_threshold", "lp_concentration_over_limit",
        "lp_concentration_exceeded", "lp_concentration_risk",
    ))
    if found:
        if value is None or not isinstance(value, bool):
            return None, "UNKNOWN_LP_CONCENTRATION"
        return not value, None

    found, value = _lookup(facts, (
        "lp_concentration_ok", "lp_concentration_within_limit",
        "lp_concentration_pass",
    ))
    if found:
        if value is None or not isinstance(value, bool):
            return None, "UNKNOWN_LP_CONCENTRATION"
        return value, None

    found, value = _lookup(facts, (
        "lp_concentration_bps", "lp_concentration_pct", "lp_concentration_ratio",
    ))
    if not found or value is None:
        return None, "UNKNOWN_LP_CONCENTRATION"
    try:
        amount = _decimal(value, "lp_concentration")
    except (TypeError, ValueError):
        return None, "UNKNOWN_LP_CONCENTRATION"
    if "lp_concentration_bps" in facts:
        return amount <= _decimal(facts.get("lp_concentration_threshold_bps", MAX_LP_CONCENTRATION_BPS), "lp_concentration_threshold_bps"), None
    if "lp_concentration_pct" in facts:
        return amount <= _decimal(facts.get("lp_concentration_threshold_pct", MAX_LP_CONCENTRATION_PCT), "lp_concentration_threshold_pct"), None
    return amount <= MAX_LP_CONCENTRATION_RATIO, None
def _liquidity_result(facts: Mapping[str, Any]) -> tuple[bool | None, str | None]:
    found, value = _lookup(facts, (
        "liquidity_sudden_drop", "liquidity_drop", "liquidity_drop_over_threshold",
    ))
    if found:
        if value is None or not isinstance(value, bool):
            return None, "UNKNOWN_LIQUIDITY_DROP"
        return not value, None
    found, value = _lookup(facts, ("liquidity_ok", "liquidity_stable"))
    if found:
        if value is None or not isinstance(value, bool):
            return None, "UNKNOWN_LIQUIDITY_DROP"
        return value, None
    found, value = _lookup(facts, ("liquidity_drop_bps", "liquidity_drop_pct"))
    if not found or value is None:
        return None, "UNKNOWN_LIQUIDITY_DROP"
    try:
        amount = _decimal(value, "liquidity_drop")
        key = "liquidity_drop_bps" if "liquidity_drop_bps" in facts else "liquidity_drop_pct"
        default = "3000" if key.endswith("bps") else "30"
        threshold = _decimal(facts.get("liquidity_drop_threshold_bps" if key.endswith("bps") else "liquidity_drop_threshold_pct", default), "liquidity_drop_threshold")
    except (TypeError, ValueError):
        return None, "UNKNOWN_LIQUIDITY_DROP"
    return amount < threshold, None
def _holder_evidence_result(facts: Mapping[str, Any]) -> tuple[bool | None, str | None]:
    found, value = _lookup(facts, (
        "holder_concentration_evidence", "holder_concentration_evidence_available",
        "holder_concentration_verified", "holder_concentration_ok", "holders_concentration_evidence",
    ))
    if found:
        if value is None:
            return None, "UNKNOWN_HOLDER_CONCENTRATION_EVIDENCE"
        if isinstance(value, bool):
            return value, None
        if isinstance(value, Mapping):
            if "available" in value:
                available = value["available"]
            elif "verified" in value:
                available = value["verified"]
            else:
                return None, "UNKNOWN_HOLDER_CONCENTRATION_EVIDENCE"
            if not isinstance(available, bool):
                return None, "UNKNOWN_HOLDER_CONCENTRATION_EVIDENCE"
            return available, None
        return None, "UNKNOWN_HOLDER_CONCENTRATION_EVIDENCE"
    found, value = _lookup(facts, ("holder_concentration_pct", "top_holder_pct"))
    if not found or value is None:
        return None, "UNKNOWN_HOLDER_CONCENTRATION_EVIDENCE"
    try:
        _decimal(value, "holder_concentration_pct")
    except (TypeError, ValueError):
        return None, "UNKNOWN_HOLDER_CONCENTRATION_EVIDENCE"
    return True, None
def admission_check(token_facts: Mapping[str, Any]) -> tuple[bool, list[str]]:
    if not isinstance(token_facts, Mapping):
        raise TypeError("token_facts must be a Mapping")
    reasons: list[str] = []

    can_sell, reason = _unknown_or_bool(
        token_facts, ("can_sell", "can_sell_token", "sell_ok", "sellable", "sell_simulation_ok", "sell_simulation_pass"), "CAN_SELL")
    can_reduce, reduce_reason = _unknown_or_bool(
        token_facts, ("can_reduce", "can_reduce_position", "can_decrease", "can_remove", "reducible", "remove_possible", "decrease_liquidity_ok", "remove_liquidity_ok"), "CAN_REDUCE")
    if can_sell is None:
        reasons.append(reason or "UNKNOWN_CAN_SELL")
    if can_reduce is None:
        reasons.append(reduce_reason or "UNKNOWN_CAN_REDUCE")
    if can_sell is False or can_reduce is False:
        reasons.append("CANNOT_SELL_OR_REDUCE_POSITION")

    found, tax = _lookup(token_facts, ("transfer_tax_bps", "transfer_tax"))
    if not found or tax is None:
        reasons.append("UNKNOWN_TRANSFER_TAX_BPS")
    else:
        try:
            if _decimal(tax, "transfer_tax_bps") != 0:
                reasons.append("TRANSFER_TAX_BPS_NONZERO")
        except (TypeError, ValueError):
            reasons.append("UNKNOWN_TRANSFER_TAX_BPS")

    gates = (
        (("owner_can_mint", "owner_can_mint_arbitrarily", "owner_can_arbitrary_mint", "arbitrary_mint", "owner_mint"), "OWNER_CAN_MINT_ARBITRARILY", "OWNER_CAN_MINT_ARBITRARILY"),
        (("can_blacklist", "owner_can_blacklist", "can_blocklist", "blacklist_enabled", "blacklist"), "BLACKLIST_ENABLED", "BLACKLIST_ENABLED"),
        (("can_change_tax", "tax_changeable", "owner_can_change_tax", "owner_can_set_tax", "tax_mutable"), "TAX_CHANGEABLE", "TAX_CHANGEABLE"),
        (("proxy_can_change_implementation", "proxy_implementation_can_change", "proxy_upgradeable", "implementation_changeable", "proxy_can_upgrade"), "PROXY_IMPLEMENTATION_CHANGEABLE", "PROXY_IMPLEMENTATION_CHANGEABLE"),
    )
    for keys, bad_reason, unknown_name in gates:
        value, unknown = _unknown_or_bool(token_facts, keys, unknown_name)
        if value is None:
            reasons.append(unknown or f"UNKNOWN_{unknown_name}")
        elif value:
            reasons.append(bad_reason)

    concentration, concentration_reason = _concentration_result(token_facts)
    if concentration is None:
        reasons.append(concentration_reason or "UNKNOWN_LP_CONCENTRATION")
    elif not concentration:
        reasons.append("LP_CONCENTRATION_OVER_THRESHOLD")

    liquidity, liquidity_reason = _liquidity_result(token_facts)
    if liquidity is None:
        reasons.append(liquidity_reason or "UNKNOWN_LIQUIDITY_DROP")
    elif not liquidity:
        reasons.append("LIQUIDITY_SUDDEN_DROP")

    holder, holder_reason = _holder_evidence_result(token_facts)
    if holder is None:
        reasons.append(holder_reason or "UNKNOWN_HOLDER_CONCENTRATION_EVIDENCE")
    elif not holder:
        reasons.append("HOLDER_CONCENTRATION_EVIDENCE_MISSING")
    return not reasons, reasons
def downtrend_recenter_guard(*, price_now: Any, range_lower: Any,
                             trend_slope: Any, volume_trend: Any) -> tuple[str, str]:
    if price_now < range_lower and trend_slope < 0:
        return "REMOVE_EVAL", "NO_DOWNTREND_RECENTER"
    if price_now < range_lower or trend_slope < 0 or volume_trend < 0:
        return "HOLD", "WAIT_FOR_TREND_AND_VOLUME_RECOVERY"
    return "NORMAL", "RANGE_MAINTAINED"
def exit_state_machine(*, remove_ok: bool, swap_ok: bool | None,
                       atomic: bool) -> tuple[str, dict]:
    if atomic and swap_ok is False:
        return "ATOMIC_EXIT_REVERTED", {"remove_effective": False}
    if remove_ok and swap_ok is True:
        return "CLOSED_RECONCILED", {
            "cash_closed": True, "asset_cap_released": True, "residual_risk": False,
        }
    if remove_ok and swap_ok is False:
        return "REMOVED_RISKY_INVENTORY", {
            "cash_closed": False, "asset_cap_released": False, "residual_risk": True,
        }
    if swap_ok is None:
        return "EXIT_UNKNOWN_RECONCILE_REQUIRED", {"asset_cap_released": False}
    return "EXIT_INCOMPLETE", {"remove_effective": bool(remove_ok), "asset_cap_released": False}
def exit_direction_check(*, from_asset: str, to_asset: str,
                         current_exposure: Mapping[str, Decimal],
                         caps: Mapping[str, Decimal]) -> tuple[bool, str]:
    if to_asset not in caps or caps[to_asset] is None:
        return False, f"UNKNOWN_EXPOSURE_CAP:{to_asset}"
    if to_asset not in current_exposure or current_exposure[to_asset] is None:
        return False, f"UNKNOWN_EXPOSURE:{to_asset}"
    try:
        exposure = _decimal(current_exposure[to_asset], f"exposure:{to_asset}")
        cap = _decimal(caps[to_asset], f"cap:{to_asset}")
    except (TypeError, ValueError):
        return False, f"UNKNOWN_EXPOSURE:{to_asset}"
    if exposure >= cap:
        return False, f"EXIT_INCREASES_CAPPED_EXPOSURE:{to_asset}"
    return True, "OK"
def residual_inventory_accounting(*args: Any, **kwargs: Any) -> dict[str, Any]:
    names = ["asset", "quantity", "mark_price", "cost_basis", "liquidation_price"]
    values = dict(zip(names, args))
    values.update(kwargs)
    asset = values.get("asset", values.get("token", ""))
    quantity = values.get("quantity", values.get("amount", values.get("residual_amount")))
    mark_price = values.get("mark_price", values.get("price"))
    liquidation_price = values.get("liquidation_price", values.get("liquidation_mark"))
    cost_basis = values.get("cost_basis", values.get("acquisition_value", values.get("basis")))
    if quantity is None:
        raise ValueError("RESIDUAL_INVENTORY_AMOUNT_MISSING")
    quantity_dec = _decimal(quantity, "residual_amount")
    direct_value = values.get("liquidation_value")
    price_value = liquidation_price if liquidation_price is not None else mark_price
    liquidation_value = (_decimal(direct_value, "liquidation_value") if direct_value is not None
                         else None if price_value is None
                         else quantity_dec * _decimal(price_value, "liquidation_price"))
    basis_value = None if cost_basis is None else _decimal(cost_basis, "cost_basis")
    reference_nav = values.get("reference_nav")
    liquidation_nav = values.get("liquidation_nav")
    nav_value = None if liquidation_nav is None else _decimal(liquidation_nav, "liquidation_nav")
    if nav_value is None and reference_nav is not None and liquidation_value is not None:
        nav_value = _decimal(reference_nav, "reference_nav")
    row = {
        "asset": str(asset),
        "amount": quantity_dec,
        "residual_amount": quantity_dec,
        "residual_inventory": True,
        "asset_cap_released": False,
        "counts_toward_asset_cap": True,
        "counts_toward_drawdown": True,
        "counts_toward_liquidation_nav": True,
        "liquidation_value": liquidation_value,
        "cost_basis": basis_value,
        "liquidation_nav": nav_value,
        "cash_closed": False,
        "rh_journal": {
            "account_debit": "residual_risk_inventory",
            "account_credit": "lp_position",
            "asset": str(asset),
            "amount_raw": assert_decimal_text(format(quantity_dec, "f"), "amount_raw"),
            "is_external_flow": False,
        },
    }
    row.update(row["rh_journal"])
    if liquidation_value is not None and basis_value is not None:
        row["unrealized_pnl"] = liquidation_value - basis_value
    return row
def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"not JSON serializable: {type(value).__name__}")
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline MEME admission audit")
    parser.add_argument("--facts-json", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with Path(args.facts_json).open(encoding="utf-8") as handle:
        payload = json.load(handle, parse_float=Decimal)
    facts = payload.get("token_facts", payload) if isinstance(payload, Mapping) else payload
    allowed, reasons = admission_check(facts)
    result = {"allowed": allowed, "reasons": reasons}
    Path(args.out).write_text(json.dumps(result, default=_json_default, indent=2) + "\n", encoding="utf-8")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
