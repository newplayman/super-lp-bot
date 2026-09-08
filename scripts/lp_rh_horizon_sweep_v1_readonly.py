#!/usr/bin/env python3
"""RH-04d: holding-period sweep and conversion-cost audit (read-only, offline).

Quantifies the B1 §9.5 claim ("fixed cost ≈ 2× pool fee tier, nearly
position-invariant; holding period is the dominant lever") against the RH-04b
first closed-loop finding.  Pure and offline: it only CALLS the three existing
read-only modules (assemble_rh_clmm_inputs, apply_netcover_gate,
clmm_token0_value_fraction) and never touches wallets, chain state, or the
network.  Money amounts are carried as Decimal; missing inputs stay None and
are never filled with 0.
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

from scripts.lp_netcover_engine_v1_readonly import apply_netcover_gate
from scripts.lp_rh_netcover_inputs_v1_readonly import assemble_rh_clmm_inputs
from scripts.lp_swap_cost_model_v1_readonly import (
    clmm_token0_value_fraction,
    exit_conversion_cost_usd,
)

# PRD §10.1 finite holding-period scenarios.
HORIZONS_HOURS = (24, 168, 720, 1220)


def _dec(value: Any) -> Optional[Decimal]:
    """Decimal(str(value)) for a finite number, else None. Never 0 for missing."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _pool_params(evidence: Mapping[str, Any]):
    """Extract (price, fee_tier, dec0, dec1, liquidity_raw) or None if incomplete.

    price = (sqrt_price_x96 / 2**96) ** 2; fee_tier = fee / 1e6.  Returns None
    when any field is missing/invalid so callers can emit None (not 0).
    """
    vals = (evidence.get("sqrt_price_x96"), evidence.get("fee"),
            evidence.get("dec0"), evidence.get("dec1"), evidence.get("liquidity_raw"))
    if any(v is None for v in vals):
        return None
    try:
        price = (float(vals[0]) / 2.0 ** 96) ** 2
        fee_tier = float(vals[1]) / 1e6
        dec0, dec1 = int(vals[2]), int(vals[3])
        liq = float(vals[4])
    except (TypeError, ValueError):
        return None
    if price <= 0 or fee_tier <= 0 or liq <= 0:
        return None
    return price, fee_tier, dec0, dec1, liq


def _netcover_at(evidence: Mapping[str, Any], *, fee_apr_pct: float,
                 position_usd: Decimal, horizon_hours: float) -> Optional[float]:
    """NetCover at a given fee APR (pct); None when the gate fails closed."""
    ev = dict(evidence)
    ev["fee_apr_pct"] = fee_apr_pct
    record = assemble_rh_clmm_inputs(ev, position_usd=position_usd,
                                     horizon_hours=horizon_hours)
    gated = apply_netcover_gate([record])
    return gated[0].get("netcover") if gated else None


def _bisect_required_fee_apr(evidence: Mapping[str, Any], *, position_usd: Decimal,
                             horizon_hours: float, tol: float = 0.01,
                             max_iter: int = 200) -> Optional[float]:
    """Back-solve the fee APR (pct) that makes NetCover = 1.0.

    fee_ev is linear in fee APR in this model, but we bisect on NetCover
    directly so the result stays self-consistent even if the income/cost model
    changes.  Returns None when NetCover is not computable (any required input
    missing) or when no finite APR reaches the gate.
    """
    base = _netcover_at(evidence, fee_apr_pct=evidence.get("fee_apr_pct"),
                        position_usd=position_usd, horizon_hours=horizon_hours)
    if base is None:
        return None
    if _netcover_at(evidence, fee_apr_pct=0.0, position_usd=position_usd,
                    horizon_hours=horizon_hours) >= 1.0:
        return 0.0
    hi = 1.0
    while _netcover_at(evidence, fee_apr_pct=hi, position_usd=position_usd,
                       horizon_hours=horizon_hours) < 1.0:
        hi *= 2.0
        if hi > 1e9:
            return None
    lo = 0.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        if _netcover_at(evidence, fee_apr_pct=mid, position_usd=position_usd,
                        horizon_hours=horizon_hours) < 1.0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2.0


def sweep_horizons(evidence: Mapping[str, Any], *, position_usd: Decimal,
                   horizons: Sequence[float] = HORIZONS_HOURS) -> list[dict]:
    """Run assemble+gate at each holding period; report fee EV, fixed cost, NetCover.

    fixed_cost_usd = entry + exit + gas, the horizon-invariant part.  Any missing
    input leaves the affected item None (never 0), and required_fee_apr_pct is
    None whenever NetCover itself is not computable.
    """
    results = []
    for h in horizons:
        record = assemble_rh_clmm_inputs(evidence, position_usd=position_usd,
                                         horizon_hours=h)
        gated = apply_netcover_gate([record])
        g = gated[0] if gated else {}
        netcover = g.get("netcover")
        entry, exit_, gas = (record.get("entry_cost_usd"),
                             record.get("exit_cost_usd"), record.get("gas_usd"))
        if entry is not None and exit_ is not None and gas is not None:
            fixed_cost = _dec(entry) + _dec(exit_) + _dec(gas)
        else:
            fixed_cost = None
        required = (_bisect_required_fee_apr(evidence, position_usd=position_usd,
                                             horizon_hours=h)
                    if netcover is not None else None)
        results.append({
            "horizon_hours": h,
            "fee_ev_usd": _dec(record.get("fee_ev_usd")),
            "fixed_cost_usd": fixed_cost,
            "netcover": netcover,
            "netcover_pass": g.get("netcover_pass"),
            "required_fee_apr_pct": required,
        })
    return results


def fixed_cost_share(evidence: Mapping[str, Any], *,
                     position_usds: Sequence[float] = (50, 500, 5000)) -> list[dict]:
    """Fixed cost (entry+exit+gas) across position sizes; tests B1 §9.5 constancy.

    Fixed cost is horizon-invariant, so a single horizon (24h) suffices.  If the
    cost model treats the full principal as the leg-swap amount (forbidden by
    PRD §11.3), the USD cost grows with position size instead of staying ~constant.
    """
    results = []
    for pos in position_usds:
        record = assemble_rh_clmm_inputs(evidence, position_usd=Decimal(str(pos)),
                                         horizon_hours=HORIZONS_HOURS[0])
        entry, exit_, gas = (record.get("entry_cost_usd"),
                             record.get("exit_cost_usd"), record.get("gas_usd"))
        if entry is not None and exit_ is not None and gas is not None:
            fixed_cost = _dec(entry) + _dec(exit_) + _dec(gas)
            pct = fixed_cost / Decimal(str(pos)) * Decimal(100)
        else:
            fixed_cost = None
            pct = None
        results.append({
            "position_usd": pos,
            "fixed_cost_usd": fixed_cost,
            "fixed_cost_pct_of_position": pct,
        })
    return results


def conversion_cost_audit(evidence: Mapping[str, Any], *, position_usd: Decimal,
                          range_pcts: Sequence[float] = (1, 5, 10, 20, 50)) -> list[dict]:
    """Diagnose whether the $4.70 leg-swap cost is overestimated.

    For each range width, a freshly-minted CL position only needs to swap
    ``token0_value_fraction`` of its value to token0 (not the whole position).
    Wider ranges -> more balanced legs -> smaller swap share.  Diagnostic only;
    no conclusion is drawn here.
    """
    params = _pool_params(evidence)
    results = []
    for r in range_pcts:
        if params is None:
            results.append({"range_pct": r, "token0_value_fraction": None,
                            "implied_swap_notional_usd": None, "entry_cost_usd": None})
            continue
        price, fee_tier, dec0, dec1, liq = params
        try:
            frac = clmm_token0_value_fraction(price, r)
        except ValueError:
            frac = None
        if frac is None:
            results.append({"range_pct": r, "token0_value_fraction": None,
                            "implied_swap_notional_usd": None, "entry_cost_usd": None})
            continue
        notional = float(position_usd) * frac
        entry_cost = exit_conversion_cost_usd(notional, liq, price, fee_tier, dec0, dec1,
                                              side="buy_base")
        results.append({
            "range_pct": r,
            "token0_value_fraction": frac,
            "implied_swap_notional_usd": notional,
            "entry_cost_usd": entry_cost,
        })
    return results


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI: --evidence-json --position-usd --out.  Offline; no network, no writes."""
    parser = argparse.ArgumentParser(
        description="RH-04d horizon sweep + conversion-cost audit (read-only).")
    parser.add_argument("--evidence-json", required=True)
    parser.add_argument("--position-usd", type=str, default="50")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with open(args.evidence_json, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, Mapping):
        evidence_list = list(payload.get("records") or [])
    else:
        evidence_list = list(payload)
    if not evidence_list:
        print("No evidence records found.", file=sys.stderr)
        return 1
    evidence = evidence_list[0]
    position_usd = Decimal(args.position_usd)
    out = {
        "generated_by": "lp_rh_horizon_sweep_v1_readonly",
        "position_usd": str(position_usd),
        "sweep_horizons": sweep_horizons(evidence, position_usd=position_usd),
        "fixed_cost_share": fixed_cost_share(evidence),
        "conversion_cost_audit": conversion_cost_audit(evidence,
                                                      position_usd=position_usd),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=str)
        fh.write("\n")
    print(f"Wrote horizon sweep to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
