#!/usr/bin/env python3
"""RH-05a: stock-token reference price + corporate-action guard (offline).

Pure, offline computation.  Implements the PRD §9.2 unified model for
stock tokens (all 18-decimal, SESSION_NESTED) and the §9.5 corporate-action
and oracle-pause guards.  No network, no collection, no writes to
``reports/lp_rh/``.  All money is ``Decimal``; no ``float``.

The reference price is a *reference*, not a guaranteed fill (PRD §9.3):
the dataclass is named ``ReferenceValue`` and must never be renamed to a
"guaranteed fair price" type.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_market_session_v1_readonly import stale_reason  # noqa: E402

# --- PRD §9.2 unified model -------------------------------------------------
def token_quantity(raw_balance: int, token_decimals: int) -> Decimal:
    """raw_balance / 10**token_decimals."""
    return Decimal(raw_balance) / Decimal(10) ** token_decimals


def multiplier_from_raw(onchain_ui_multiplier_raw: int) -> Decimal:
    """onchain_uiMultiplier_raw / 10**18."""
    return Decimal(onchain_ui_multiplier_raw) / Decimal(10) ** 18


def multiplier_from_api(api_current_multiplier: str) -> Decimal:
    """Decimal(api.currentMultiplier)."""
    return Decimal(api_current_multiplier)


def underlying_share_equivalent(token_quantity: Decimal,
                                multiplier_human: Decimal) -> Decimal:
    """token_quantity * multiplier_human."""
    return token_quantity * multiplier_human


def token_equivalent_price(*, underlying_price_usd: Decimal,
                           multiplier_human: Decimal,
                           source_is_already_token_equivalent: bool) -> Decimal:
    """reference_token_price_usd, with the T18 no-double-apply guard.

    When the source feed is already token-equivalent, return it as-is and
    never multiply by the multiplier again (PRD §9.2 / T18).
    """
    if source_is_already_token_equivalent:
        return underlying_price_usd
    return underlying_price_usd * multiplier_human


def usdg_normalized_price(token_price_usd: Decimal,
                          usdg_price_usd: Decimal) -> Decimal:
    """reference_stock_per_usdg = token_price_usd / usdg_price_usd (T19)."""
    if usdg_price_usd <= 0:
        raise ValueError("USDG_PRICE_INVALID")
    return token_price_usd / usdg_price_usd


def split_preserves_reference(*, before_underlying: Decimal,
                              before_multiplier: Decimal,
                              after_underlying: Decimal,
                              after_multiplier: Decimal) -> bool:
    """T20: a split keeps the per-token reference price unchanged."""
    return (before_underlying * before_multiplier
            == after_underlying * after_multiplier)


# --- PRD §9.3 reference value (not a guaranteed fill) -----------------------
@dataclass
class ReferenceValue:
    reference_bid: Optional[Decimal]
    reference_ask: Optional[Decimal]
    reference_mid: Optional[Decimal]
    executable_exit_bid_for_position_size: Optional[Decimal]
    reference_age_secs: Optional[int]
    quote_age_secs: Optional[int]
    source_quality: str
    redeem_access: str = "NOT_PROVEN"


# --- PRD §9.5 corporate-action + oracle-pause guard -------------------------
def corp_action_guard(*, current_multiplier: Optional[str],
                      pending_multiplier: Optional[str],
                      effective_at: Optional[datetime],
                      now: datetime,
                      oracle_paused: Optional[bool]) -> tuple[str, list[str]]:
    """Return (state, reasons).  Read failures are UNKNOWN, never False (T21)."""
    if oracle_paused is True:
        return "ORACLE_PAUSED", ["oracle feed paused"]
    if current_multiplier is None or oracle_paused is None:
        reasons = []
        if current_multiplier is None:
            reasons.append("current_multiplier read failed")
        if oracle_paused is None:
            reasons.append("oracle_paused read failed")
        return "UNKNOWN", reasons
    if pending_multiplier and effective_at is not None and effective_at > now:
        return "CORP_ACTION_GUARD", [
            "pending multiplier change effective in the future"]
    return "NORMAL", []


def allows_new_or_recenter(state: str) -> bool:
    """Only NORMAL permits new positions or recentering (T21)."""
    return state == "NORMAL"


def stale_classification(*, session: str, oracle_age_secs: float,
                         heartbeat_secs: int) -> str:
    """T23: reuse lp_rh_market_session.stale_reason (import, not rewrite)."""
    return stale_reason(session, oracle_age_secs, heartbeat_secs)


def exit_quote_required(reference: ReferenceValue) -> tuple[bool, str]:
    """T24: a readable reference without a full exit quote is not risk-free."""
    if reference.executable_exit_bid_for_position_size is None:
        return False, "INPUTS_UNAVAILABLE: EXIT_QUOTE"
    return True, "EXIT_QUOTE_AVAILABLE"


# --- snapshot ----------------------------------------------------------------
def load_assets_snapshot(path: "str | Path") -> dict[str, dict]:
    """Index RH_ASSETS_SNAPSHOT.json assets by tokenSymbol."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {a["tokenSymbol"]: a for a in data["assets"]}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RH-05a stock-token reference price (offline)")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--underlying-usd", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    assets = load_assets_snapshot(args.snapshot)
    asset = assets[args.symbol]
    multiplier = multiplier_from_api(asset["currentMultiplier"])
    underlying = Decimal(args.underlying_usd)
    price = token_equivalent_price(
        underlying_price_usd=underlying, multiplier_human=multiplier,
        source_is_already_token_equivalent=False)
    result = {
        "symbol": args.symbol,
        "currentMultiplier": asset["currentMultiplier"],
        "token_equivalent_price_usd": str(price),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
