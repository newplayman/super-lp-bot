#!/usr/bin/env python3
"""RH-04a: NAV ledger and HODL benchmark (offline, read-only).

The single ledger of record is NAV (PRD v1.1 §12), not a Fee-IL-AS formula:
NetPnL(t0,t1) = NAV(t1) - NAV(t0) - net external flow; gas/slippage already in
balance changes are not deducted again (RH-INV-12).  §12.4 stores reference_nav
and liquidation_nav; D04: the HODL benchmark uses the actual initial legs,
never a 50/50 assumption.  Money is decimal.Decimal; the store rejects floats.
No network, no live DB writes.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_store_v1_readonly import (  # noqa: E402
    assert_decimal_text, insert_row, migrate, open_store,
)

# --- flow classification (RH-INV-13) ----------------------------------------
EXTERNAL_FLOW_KINDS = frozenset({"deposit", "withdrawal", "external_gas_sponsor"})
INTERNAL_FLOW_KINDS = frozenset(
    {"collect", "remove_liquidity", "add_liquidity", "bucket_transfer", "swap"})


def classify_flow(kind: str) -> bool:
    """Return is_external_flow for a journal event kind; unknown kinds error."""
    if kind in EXTERNAL_FLOW_KINDS:
        return True
    if kind in INTERNAL_FLOW_KINDS:
        return False
    raise ValueError("UNKNOWN_FLOW_KIND")


def _as_decimal(field_name: str, value: Any) -> Decimal:
    """Coerce a money/price input to Decimal; None and floats are errors."""
    if value is None:
        raise ValueError(f"NAV_INPUT_MISSING: {field_name}")
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"REAL_NOT_ALLOWED_FOR_MONEY: {field_name}")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, Decimal):
        return value
    raise TypeError(f"REAL_NOT_ALLOWED_FOR_MONEY: {field_name}")


def _as_decimals_places(field_name: str, value: Any) -> int:
    """Validate a token-decimals input (non-negative int)."""
    if value is None:
        raise ValueError(f"NAV_INPUT_MISSING: {field_name}")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"INVALID_DECIMALS: {field_name}")
    return value


def _decimal_to_text(value: Any, field_name: str = "amount_raw") -> str:
    """Normalize a Decimal to a validated plain decimal string for storage."""
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"REAL_NOT_ALLOWED_FOR_MONEY: {field_name}")
    if not isinstance(value, Decimal):
        raise TypeError(f"REAL_NOT_ALLOWED_FOR_MONEY: {field_name}")
    return assert_decimal_text(format(value, "f"), field_name)


def open_pnl_store(path: Any) -> sqlite3.Connection:
    """Open and migrate a store for NAV ledger work (tests / offline runs)."""
    conn = open_store(path)
    migrate(conn)
    return conn


# --- NAV (PRD §12.1) ---------------------------------------------------------
@dataclass
class NavSnapshot:
    position_id: str
    mark_time: str
    wallet_value: Decimal
    lp_principal_value: Decimal
    accrued_fees: Decimal
    verified_rewards: Decimal
    liabilities: Decimal
    reference_nav: Decimal
    liquidation_nav: Decimal
    unvalued_assets: list[str] = field(default_factory=list)


def compute_nav(*, wallet, lp_principal, accrued_fees, verified_rewards,
                liabilities) -> Decimal:
    """NAV = wallet + lp_principal + accrued_fees + verified_rewards - liabilities.

    A missing input is an error, never a silent zero (PRD §12.1)."""
    w = _as_decimal("wallet", wallet)
    p = _as_decimal("lp_principal", lp_principal)
    f = _as_decimal("accrued_fees", accrued_fees)
    r = _as_decimal("verified_rewards", verified_rewards)
    l = _as_decimal("liabilities", liabilities)
    return w + p + f + r - l


class LiquidationNavResult(tuple):
    """Result of compute_liquidation_nav supporting tuple unpacking, dict and attribute access."""

    def __new__(cls, nav: Optional[Decimal], reason: Optional[str] = None):
        return super().__new__(cls, (nav, reason))

    @property
    def liquidation_nav(self) -> Optional[Decimal]:
        return self[0]

    @property
    def nav(self) -> Optional[Decimal]:
        return self[0]

    @property
    def reason(self) -> Optional[str]:
        return self[1]

    def get(self, key: str, default=None):
        if key in ("liquidation_nav", "nav"):
            return self[0]
        if key == "reason":
            return self[1]
        return default

    def __getitem__(self, item):
        if isinstance(item, str):
            return self.get(item)
        return super().__getitem__(item)


def compute_full_cost_nav(
    *,
    wallet,
    lp_principal,
    accrued_fees,
    entry_cost_usd,
    exit_cost_usd,
    gas_usd,
    slippage_usd,
    verified_rewards=Decimal(0),
    liabilities=Decimal(0),
) -> Decimal:
    """Compute full-cost NAV: wallet + lp_principal - entry_cost - exit_cost - gas - slippage + accrued_fees + rewards - liabilities.

    Fail-close: all numeric parameters are validated via _as_decimal.
    """
    w = _as_decimal("wallet", wallet)
    p = _as_decimal("lp_principal", lp_principal)
    f = _as_decimal("accrued_fees", accrued_fees)
    ec = _as_decimal("entry_cost_usd", entry_cost_usd)
    xc = _as_decimal("exit_cost_usd", exit_cost_usd)
    g = _as_decimal("gas_usd", gas_usd)
    s = _as_decimal("slippage_usd", slippage_usd)
    r = _as_decimal("verified_rewards", verified_rewards)
    l = _as_decimal("liabilities", liabilities)
    return w + p - ec - xc - g - s + f + r - l


def compute_liquidation_nav(
    *,
    l_pos=None,
    price=None,
    range=None,
    fee_growth_0=None,
    fee_growth_1=None,
    decimals=None,
    slippage_bps_max=Decimal("200"),
    entry_cost_usd=Decimal(0),
    exit_cost_usd=Decimal(0),
    gas_usd=Decimal(0),
    quote_usd_per_token1=Decimal(1),
    **kwargs,
) -> LiquidationNavResult:
    """Conservative maximum extractable cash on exit given fee growth + slippage cap.

    Strictly fail-close: if any required input (l_pos, price, range, fee_growth_0,
    fee_growth_1, decimals) is missing, returns LiquidationNavResult(None, "LIQUIDATION_NAV_INPUT_MISSING").
    """
    if (l_pos is None or price is None or range is None or
            fee_growth_0 is None or fee_growth_1 is None or decimals is None):
        return LiquidationNavResult(None, "LIQUIDATION_NAV_INPUT_MISSING")

    try:
        l = Decimal(str(l_pos))
        px = Decimal(str(price))
        fg0 = Decimal(str(fee_growth_0))
        fg1 = Decimal(str(fee_growth_1))
        slip_bps = Decimal(str(slippage_bps_max))
        ec = Decimal(str(entry_cost_usd)) if entry_cost_usd is not None else Decimal(0)
        xc = Decimal(str(exit_cost_usd)) if exit_cost_usd is not None else Decimal(0)
        g = Decimal(str(gas_usd)) if gas_usd is not None else Decimal(0)
        q = Decimal(str(quote_usd_per_token1)) if quote_usd_per_token1 is not None else Decimal(1)

        if isinstance(decimals, (tuple, list)):
            dec0, dec1 = int(decimals[0]), int(decimals[1])
        else:
            dec0 = dec1 = int(decimals)

        if l <= 0 or px <= 0:
            return LiquidationNavResult(Decimal(0), None)

        if isinstance(range, (tuple, list)):
            lower_p, upper_p = Decimal(str(range[0])), Decimal(str(range[1]))
        elif isinstance(range, (int, float, Decimal, str)):
            rpct = Decimal(str(range))
            lower_p = px * (Decimal(1) - rpct / Decimal(100))
            upper_p = px * (Decimal(1) + rpct / Decimal(100))
        else:
            return LiquidationNavResult(None, "LIQUIDATION_NAV_INPUT_MISSING")

        sqrt_pa = lower_p.sqrt()
        sqrt_pb = upper_p.sqrt()
        sqrt_p = px.sqrt()

        if px <= lower_p:
            amt0 = l * (sqrt_pb - sqrt_pa) / (sqrt_pa * sqrt_pb)
            amt1 = Decimal(0)
        elif px >= upper_p:
            amt0 = Decimal(0)
            amt1 = l * (sqrt_pb - sqrt_pa)
        else:
            amt0 = l * (sqrt_pb - sqrt_p) / (sqrt_p * sqrt_pb)
            amt1 = l * (sqrt_p - sqrt_pa)

        pos_val_usd = (amt0 * px + amt1) * q
        fee_scale = Decimal(2) ** Decimal(128)
        tok0_fees = l * fg0 / fee_scale / (Decimal(10) ** dec0)
        tok1_fees = l * fg1 / fee_scale / (Decimal(10) ** dec1)
        fee_val_usd = (tok0_fees * px + tok1_fees) * q

        slippage_factor = slip_bps / Decimal(10000)
        conservative_exit_val = (pos_val_usd + fee_val_usd) * (Decimal(1) - slippage_factor)
        net_liq_nav = conservative_exit_val - ec - xc - g
        return LiquidationNavResult(max(Decimal(0), net_liq_nav), None)
    except Exception:
        return LiquidationNavResult(None, "LIQUIDATION_NAV_COMPUTATION_ERROR")



def net_pnl(nav_t1: Decimal, nav_t0: Decimal,
            external_net_flow: Decimal) -> Decimal:
    """NetPnL(t0,t1) = NAV(t1) - NAV(t0) - net external flow (PRD §12.1)."""
    return (_as_decimal("nav_t1", nav_t1) - _as_decimal("nav_t0", nav_t0)
            - _as_decimal("external_net_flow", external_net_flow))


def hodl_benchmark(*, initial_token0_raw, initial_token1_raw, dec0, dec1,
                   price_t1_token1_per_token0, quote_usd_per_token1) -> Decimal:
    """Value the actual initial two-leg lot at t1 prices (D04: no 50/50).

    token0 leg -> token1 at the t1 price, then combined token1 -> USD at the
    t1 quote.  Initial leg quantities are fixed at open, never reset."""
    t0 = _as_decimal("initial_token0_raw", initial_token0_raw)
    t1 = _as_decimal("initial_token1_raw", initial_token1_raw)
    d0 = _as_decimals_places("dec0", dec0)
    d1 = _as_decimals_places("dec1", dec1)
    px = _as_decimal("price_t1_token1_per_token0", price_t1_token1_per_token0)
    q = _as_decimal("quote_usd_per_token1", quote_usd_per_token1)
    token0_human = t0 / (Decimal(10) ** d0)
    token1_human = t1 / (Decimal(10) ** d1)
    token1_equiv = token0_human * px + token1_human
    return token1_equiv * q


def book_journal_event(conn: sqlite3.Connection, *, event_id: str,
                       idempotency_key: str, debit: str, credit: str,
                       asset: str, amount_raw: Decimal, is_external_flow: bool,
                       ref: Optional[Mapping[str, Any]], now: str) -> None:
    """Book one double-entry journal row; a duplicate idempotency_key raises
    sqlite3.IntegrityError (RH-INV-13: no double-booking of any flow)."""
    row = {
        "event_id": event_id,
        "idempotency_key": idempotency_key,
        "account_debit": debit,
        "account_credit": credit,
        "asset": asset,
        "amount_raw": _decimal_to_text(amount_raw),
        "is_external_flow": 1 if is_external_flow else 0,
        "ref_json": json.dumps(ref, sort_keys=True) if ref is not None else None,
        "booked_at": now,
    }
    insert_row(conn, "rh_journal", row)


def attribution(*, nav_delta, fee_income, gas_paid, price_move_effect,
                tolerance: Decimal = Decimal("0.000000001"),
                missing_inputs: Sequence[str] = ()) -> dict:
    """Explanatory view only (PRD §12.2/§12.5); never alters the ledger.

    fee_income (+), gas_paid (deducted exactly once), price_move_effect (signed);
    reconciles against nav_delta, flagging a mismatch rather than adjusting.
    Missing replay inputs are represented as zero for continuity, but force the
    result to be unreconciled and are reported explicitly."""
    nd = _as_decimal("nav_delta", nav_delta)
    fi = _as_decimal("fee_income", fee_income)
    gp = _as_decimal("gas_paid", gas_paid)
    pm = _as_decimal("price_move_effect", price_move_effect)
    components = {"fee_income": fi, "gas_paid": -gp, "price_move_effect": pm}
    total = sum(components.values())
    unexplained = total - nd
    missing = list(dict.fromkeys(missing_inputs))
    result = {
        "nav_delta": nd,
        "components": components,
        "sum_components": total,
        "unexplained": unexplained,
        "reconciled": not missing and abs(unexplained) <= tolerance,
    }
    if missing:
        result["missing_inputs"] = missing
        result["reason"] = "NAV_INPUT_MISSING: " + ", ".join(missing)
    return result


def liquidation_nav(*, reference_nav, haircut_by_asset: Mapping[str, Decimal],
                    unvalued: list[str]) -> Tuple[Decimal, list]:
    """Conservative liquidation NAV (PRD §12.4).

    Unpriced assets are not valued at last trade: they stay in unvalued and
    their conservative haircut is deducted from the reference NAV."""
    rn = _as_decimal("reference_nav", reference_nav)
    deduction = Decimal(0)
    for asset, haircut in haircut_by_asset.items():
        deduction += _as_decimal("haircut:" + asset, haircut)
    return rn - deduction, list(unvalued)


def _process_events(payload: Mapping[str, Any]) -> dict:
    """Compute NAV, PnL, HODL delta and attribution per step (offline)."""
    init0 = Decimal(payload["initial_token0_raw"])
    init1 = Decimal(payload["initial_token1_raw"])
    dec0 = int(payload["dec0"])
    dec1 = int(payload["dec1"])
    steps_out: list[dict] = []
    prev_nav: Optional[Decimal] = None
    for step in payload["steps"]:
        nav = compute_nav(
            wallet=Decimal(step["wallet"]),
            lp_principal=Decimal(step["lp_principal"]),
            accrued_fees=Decimal(step["accrued_fees"]),
            verified_rewards=Decimal(step["verified_rewards"]),
            liabilities=Decimal(step["liabilities"]),
        )
        hodl = hodl_benchmark(
            initial_token0_raw=init0, initial_token1_raw=init1,
            dec0=dec0, dec1=dec1,
            price_t1_token1_per_token0=Decimal(step["price_t1_token1_per_token0"]),
            quote_usd_per_token1=Decimal(step["quote_usd_per_token1"]),
        )
        external_value = step.get("external_net_flow")
        external_missing = external_value is None
        external = (Decimal(0) if external_missing
                    else Decimal(external_value))
        nav_delta = Decimal(0) if prev_nav is None else nav - prev_nav - external
        pnl_delta = (None if prev_nav is None or external_missing
                     else net_pnl(nav, prev_nav, external))
        attribution_fields = ("fee_income", "gas_paid", "price_move_effect")
        missing_inputs = [name for name in attribution_fields
                          if step.get(name) is None]
        if external_missing:
            missing_inputs.insert(0, "external_net_flow")
        attr = attribution(
            nav_delta=nav_delta,
            fee_income=(Decimal(0) if step.get("fee_income") is None
                        else Decimal(step["fee_income"])),
            gas_paid=(Decimal(0) if step.get("gas_paid") is None
                      else Decimal(step["gas_paid"])),
            price_move_effect=(Decimal(0) if step.get("price_move_effect") is None
                               else Decimal(step["price_move_effect"])),
            missing_inputs=missing_inputs,
        )
        step_out = {
            "mark_time": step["mark_time"],
            "nav": str(nav),
            "net_pnl": None if pnl_delta is None else str(pnl_delta),
            "hodl_benchmark": str(hodl),
            "hodl_delta": str(nav - hodl),
            "attribution": {
                "reconciled": attr["reconciled"],
                "unexplained": str(attr["unexplained"]),
                "components": {k: str(v) for k, v in attr["components"].items()},
            },
        }
        if external_missing:
            step_out["net_pnl_reason"] = "NAV_INPUT_MISSING: external_net_flow"
        if attr.get("missing_inputs"):
            step_out["attribution"]["missing_inputs"] = attr["missing_inputs"]
            step_out["attribution"]["reason"] = attr["reason"]
        steps_out.append(step_out)
        prev_nav = nav
    return {"position_id": payload.get("position_id", ""), "steps": steps_out}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RH-04a NAV ledger + HODL benchmark (offline, read-only)")
    parser.add_argument("--events-json", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    result = _process_events(json.loads(Path(args.events_json).read_text()))
    Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
