#!/usr/bin/env python3
"""Offline MEME single-asset cross-pool / cross-wallet aggregation gate (RH-06b / T26).

Adds an aggregation layer on top of the per-position MEME audit. The audit's
``exit_direction_check`` takes a *flat* ``current_exposure`` map and does not
aggregate across pools or wallets, so the same asset split across several pools
or wallets evades the single-asset cap. This module computes, per asset, both
the *current* exposure and the *worst-case* exposure (price out-of-range turns
the whole position into the risk leg) and enforces the PRD caps on the
aggregated totals.

Read-only: no chain access, no wallet, no state writes.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

# PRD §260: 同一 MEME 聚合 ≤2%。单资产的「当前暴露」与「最坏情况暴露」都受此约束。
MAX_SINGLE_ASSET_PCT = Decimal("2")
# PRD §260: MEME LP 总部署 ≤8%（所有 MEME 资产当前暴露之和）。
MAX_MEME_TOTAL_PCT = Decimal("8")
# PRD §76 D10: 单池仅总资金 0.5–2%（上限取 2%）。
MAX_SINGLE_POOL_PCT = Decimal("2")


def _decimal(value: Any, field: str) -> Decimal | None:
    """Coerce a money value to Decimal; None passes through, floats/bools are rejected."""
    if value is None:
        return None
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


def _pct(amount: Decimal, capital: Decimal) -> Decimal:
    """amount as a percentage of capital, as a Decimal."""
    return amount / capital * Decimal(100)


def _sum_or_none(values: Sequence[Decimal | None]) -> Decimal | None:
    """Sum Decimals; return None if any value is None (missing is not zero)."""
    total = Decimal("0")
    for value in values:
        if value is None:
            return None
        total += value
    return total


def position_exposure(position: Mapping[str, Any]) -> dict[str, Any]:
    """Current and worst-case exposure for one LP position.

    worst_case is asset + paired regardless of ``in_range``, and that is not an
    oversight.  While in range, price crossing out turns the whole position into
    one leg, so the sum is the worst case.  Once out of range the paired leg is
    already drained, so the sum equals current.  The formula needs no branch, and
    ``in_range`` is accepted only so callers can carry it through.  Do not add a
    branch on it: doing so would understate the worst case for in-range positions,
    which is the direction that admits risk.

    A missing amount yields None for the affected figure, never 0.
    """
    if not isinstance(position, Mapping):
        raise TypeError("position must be a Mapping")
    asset = position.get("asset")
    asset_amount = _decimal(position.get("asset_amount_usd"), "asset_amount_usd")
    paired_amount = _decimal(position.get("paired_amount_usd"), "paired_amount_usd")
    current_usd = asset_amount
    worst_case_usd = (
        None if (asset_amount is None or paired_amount is None)
        else asset_amount + paired_amount
    )
    return {"asset": asset, "current_usd": current_usd, "worst_case_usd": worst_case_usd}


def aggregate_by_asset(positions: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate exposure per asset across every pool and wallet.

    Returns ``{asset: {"current_usd", "worst_case_usd", "pool_count",
    "wallet_count", "positions"}}``. If any position for an asset has a missing
    amount, that asset's corresponding total is None (missing is not summed as
    0); the caller surfaces those via ``incomplete_assets``.
    """
    by_asset: dict[str, dict[str, Any]] = {}
    for position in positions:
        exposure = position_exposure(position)
        asset = exposure["asset"]
        entry = by_asset.get(asset)
        if entry is None:
            entry = {
                "_current_sum": Decimal("0"), "_current_ok": True,
                "_worst_sum": Decimal("0"), "_worst_ok": True,
                "_pools": set(), "_wallets": set(), "positions": [],
            }
            by_asset[asset] = entry
        entry["positions"].append(position)
        entry["_pools"].add(position.get("pool"))
        entry["_wallets"].add(position.get("wallet"))
        if exposure["current_usd"] is None:
            entry["_current_ok"] = False
        else:
            entry["_current_sum"] += exposure["current_usd"]
        if exposure["worst_case_usd"] is None:
            entry["_worst_ok"] = False
        else:
            entry["_worst_sum"] += exposure["worst_case_usd"]
    result: dict[str, dict[str, Any]] = {}
    for asset, entry in by_asset.items():
        result[asset] = {
            "current_usd": entry["_current_sum"] if entry["_current_ok"] else None,
            "worst_case_usd": entry["_worst_sum"] if entry["_worst_ok"] else None,
            "pool_count": len(entry["_pools"]),
            "wallet_count": len(entry["_wallets"]),
            "positions": entry["positions"],
        }
    return result


def _aggregate_by_pool(positions: Sequence[Mapping[str, Any]]) -> dict[Any, Decimal | None]:
    """Total capital (asset + paired) per pool; None if any position is missing."""
    by_pool: dict[Any, dict[str, Any]] = {}
    for position in positions:
        pool = position.get("pool")
        asset_amount = _decimal(position.get("asset_amount_usd"), "asset_amount_usd")
        paired_amount = _decimal(position.get("paired_amount_usd"), "paired_amount_usd")
        total = (
            None if (asset_amount is None or paired_amount is None)
            else asset_amount + paired_amount
        )
        entry = by_pool.get(pool)
        if entry is None:
            entry = {"_sum": Decimal("0"), "_ok": True}
            by_pool[pool] = entry
        if total is None:
            entry["_ok"] = False
        else:
            entry["_sum"] += total
    return {pool: (entry["_sum"] if entry["_ok"] else None) for pool, entry in by_pool.items()}


def aggregation_gate(positions: Sequence[Mapping[str, Any]], *, capital_usd: Any) -> dict[str, Any]:
    """Enforce the PRD MEME caps on aggregated exposure.

    ``pass`` is False when capital is unknown, any asset's exposure is
    incomplete (cannot be computed), or any cap is exceeded. Every violated cap
    is listed in ``violations`` (not just the first).
    """
    by_asset = aggregate_by_asset(positions)
    incomplete_assets = sorted(
        (asset for asset, entry in by_asset.items()
         if entry["current_usd"] is None or entry["worst_case_usd"] is None),
        key=lambda a: str(a),
    )
    total_current = _sum_or_none([e["current_usd"] for e in by_asset.values()])
    total_worst = _sum_or_none([e["worst_case_usd"] for e in by_asset.values()])
    violations: list[dict[str, Any]] = []
    capital = _decimal(capital_usd, "capital_usd")
    capital_ok = capital is not None and capital > 0
    if not capital_ok:
        violations.append({"kind": "CAPITAL_UNKNOWN", "asset": None, "pool": None,
                           "pct": None, "cap": None})
    else:
        for asset, entry in by_asset.items():
            current = entry["current_usd"]
            worst = entry["worst_case_usd"]
            if current is not None and _pct(current, capital) > MAX_SINGLE_ASSET_PCT:
                violations.append({"kind": "SINGLE_ASSET_CURRENT", "asset": asset, "pool": None,
                                   "pct": _pct(current, capital), "cap": MAX_SINGLE_ASSET_PCT})
            if worst is not None and _pct(worst, capital) > MAX_SINGLE_ASSET_PCT:
                violations.append({"kind": "SINGLE_ASSET_WORST_CASE", "asset": asset, "pool": None,
                                   "pct": _pct(worst, capital), "cap": MAX_SINGLE_ASSET_PCT})
        if total_current is not None and _pct(total_current, capital) > MAX_MEME_TOTAL_PCT:
            violations.append({"kind": "MEME_TOTAL", "asset": None, "pool": None,
                               "pct": _pct(total_current, capital), "cap": MAX_MEME_TOTAL_PCT})
        for pool, total in _aggregate_by_pool(positions).items():
            if total is not None and _pct(total, capital) > MAX_SINGLE_POOL_PCT:
                violations.append({"kind": "SINGLE_POOL", "asset": None, "pool": pool,
                                   "pct": _pct(total, capital), "cap": MAX_SINGLE_POOL_PCT})
        if incomplete_assets:
            violations.append({"kind": "EXPOSURE_INCOMPLETE", "asset": None, "pool": None,
                               "pct": None, "cap": None, "assets": incomplete_assets})
    passed = capital_ok and not incomplete_assets and not violations
    totals: dict[str, Any] = {
        "capital_usd": capital,
        "meme_total_current_usd": total_current,
        "meme_total_worst_case_usd": total_worst,
    }
    if total_current is not None and capital_ok:
        totals["meme_total_current_pct"] = _pct(total_current, capital)
    if total_worst is not None and capital_ok:
        totals["meme_total_worst_case_pct"] = _pct(total_worst, capital)
    return {
        "pass": passed,
        "violations": violations,
        "by_asset": by_asset,
        "totals": totals,
        "incomplete_assets": incomplete_assets,
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline MEME cross-pool / cross-wallet aggregation gate")
    parser.add_argument("--positions-json", required=True)
    parser.add_argument("--capital-usd", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with Path(args.positions_json).open(encoding="utf-8") as handle:
        payload = json.load(handle, parse_float=Decimal)
    positions = payload.get("positions", payload) if isinstance(payload, Mapping) else payload
    result = aggregation_gate(positions, capital_usd=args.capital_usd)
    Path(args.out).write_text(
        json.dumps(result, default=_json_default, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
