#!/usr/bin/env python3
"""Funnel vetting step: merge bridge + multi-window artifacts -> vetted menu.

The screener funnel is 3 stages run as separate scripts:
  1. lp_universe_screener        (Stage 1, 0 RPC, DefiLlama)  -> stage2_candidates.json
  2. lp_pool_resolve_and_rank    (Stage 2, on-chain validate) -> resolve_and_rank.json
  3. lp_multiwindow_stability    (on-chain, N rolling windows) -> stability.json

This script is the final, previously-ad-hoc merge: it joins the bridge
records with the multi-window stability records by resolved pool address and
applies the legacy gates plus the WP-04 full-cost NetCover gate:

  gate_quality   : tier_quality in {A, B}        (blue-chip / one-major-leg)
  gate_yield     : on-chain yield_cover >= yc_min (fees+reward beat IL)
  gate_stable    : multi-window stable             (not a single-window fluke)
  gate_netcover  : full-cost NetCover >= 1.0       (when WP-04 input supplied)
  (status_ok     : resolved OK and not wash-flagged)

A record is `vetted` only if all gates pass. This is read-only: it consumes
artifacts, makes NO network calls. Run the three stages first, then this.

FROZEN-project rules: read-only. No wallet/sign/broadcast/chain writes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ---------------------------------------------------------------------------
# Pure core (unit-tested, no I/O)
# ---------------------------------------------------------------------------

def _yc_value(yc):
    """Coerce a yield_cover field (may be 'inf', number, or None) to a float."""
    if yc in ("inf", "Infinity", float("inf")):
        return float("inf")
    try:
        return float(yc)
    except (TypeError, ValueError):
        return 0.0


def _pool_key(rec):
    """Resolved on-chain pool address, lowercased (the bridge sets resolved_pool)."""
    return str(rec.get("resolved_pool") or rec.get("pool") or "").lower()


def index_stability(stability_records):
    """Map resolved-pool-address -> stability summary dict ({stable, enter_frac, ...})."""
    out = {}
    for s in stability_records:
        addr = str(s.get("pool") or s.get("resolved_pool") or "").lower()
        if not addr:
            continue
        out[addr] = s.get("fee_cover_stability") or s.get("stability") or {}
    return out


def index_netcover(netcover_records):
    """Map pool address to an explicit full-cost NetCover value."""
    out = {}
    for item in netcover_records:
        addr = _pool_key(item)
        if not addr:
            continue
        value = item.get("netcover", item.get("netcover_ratio"))
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = None
        out[addr] = value
    return out


def vet_record(bridge_rec, stab_summary, *, yc_min=1.0,
               netcover_value=None, require_netcover=True):
    """Annotate one bridge record and apply every requested gate.

    Missing NetCover fails closed by default.  ``require_netcover=False`` is an
    explicitly named intermediate/research-only compatibility path.
    """
    rec = dict(bridge_rec)
    sub = stab_summary or {}
    rec["stable"] = bool(sub.get("stable", False))
    rec["enter_frac"] = sub.get("enter_frac")

    q = rec.get("tier_quality")
    yc = _yc_value(rec.get("yield_cover"))
    status = rec.get("status")
    resolve = rec.get("resolve_status")

    gate_quality = q in ("A", "B")
    gate_yield = yc >= yc_min
    gate_stable = rec["stable"]
    status_ok = (
        status in (None, "OK")
        and resolve in (None, "OK", "resolved")
        and not rec.get("wash_flag", False)
    )
    rec["gates"] = {
        "quality": gate_quality,
        "yield_cover": gate_yield,
        "stable": gate_stable,
        "status_ok": status_ok,
    }
    gate_netcover = True
    if require_netcover:
        rec["netcover"] = netcover_value
        gate_netcover = netcover_value is not None and netcover_value >= 1.0
        rec["gates"]["netcover_shadow"] = gate_netcover
        rec["netcover_gate_status"] = (
            "PASS" if gate_netcover
            else "MISSING_FAIL_CLOSED" if netcover_value is None
            else "BELOW_SHADOW"
        )
    else:
        rec["netcover_gate_status"] = "LEGACY_NOT_APPLIED"
    rec["vetted"] = (
        gate_quality and gate_yield and gate_stable and status_ok and gate_netcover
    )
    return rec


def funnel_vet(bridge_records, stability_records, *, yc_min=1.0,
               netcover_records=None, allow_legacy_without_netcover=False):
    """Merge artifacts; fifth-gate bypass requires an explicit legacy opt-in."""
    stab = index_stability(stability_records)
    strict = not allow_legacy_without_netcover
    cover = index_netcover(netcover_records or [])
    return [
        vet_record(
            r, stab.get(_pool_key(r), {}), yc_min=yc_min,
            netcover_value=cover.get(_pool_key(r)), require_netcover=strict,
        )
        for r in bridge_records
    ]


def vetted_menu(records):
    """The pass-list: records where all gates passed, sorted by yield_cover desc."""
    passed = [r for r in records if r.get("vetted")]
    return sorted(passed, key=lambda r: _yc_value(r.get("yield_cover")), reverse=True)


# ---------------------------------------------------------------------------
# I/O + CLI
# ---------------------------------------------------------------------------

def _load(path):
    with open(path) as f:
        return json.load(f)


def _as_list(obj):
    if isinstance(obj, list):
        return obj
    for k in ("pools", "records", "results"):
        if isinstance(obj.get(k), list):
            return obj[k]
    return [obj]


def _render_md(records, yc_min):
    lines = [
        "# Funnel vetting — merged menu",
        "",
        f"Entry gates: quality · on-chain yield_cover ≥ {yc_min} · multi-window stable · resolved/not-wash · full-cost NetCover ≥ 1.0 (strict when supplied).",
        "",
        "| symbol | tier_q | pool | yc | stable | enter_frac | VETTED |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in sorted(records, key=lambda x: (not x.get("vetted"), -_yc_value(x.get("yield_cover")))):
        yc = _yc_value(r.get("yield_cover"))
        ef = r.get("enter_frac")
        lines.append(
            f"| {r.get('symbol')} | {r.get('tier_quality')} | "
            f"{_pool_key(r)[:14]} | {yc:.2f} | {r.get('stable')} | "
            f"{ef if ef is not None else '-'} | {'✅' if r.get('vetted') else '—'} |"
        )
    return "\n".join(lines) + "\n"


def run_self_test():
    bridge = [
        {"symbol": "GOOD", "tier_quality": "B", "yield_cover": 8.2, "status": "OK",
         "resolve_status": "OK", "wash_flag": False, "resolved_pool": "0xAAA"},
        {"symbol": "UNSTABLE", "tier_quality": "B", "yield_cover": 14.0, "status": "OK",
         "resolve_status": "OK", "wash_flag": False, "resolved_pool": "0xBBB"},
        {"symbol": "LOWYC", "tier_quality": "A", "yield_cover": 0.4, "status": "OK",
         "resolve_status": "OK", "wash_flag": False, "resolved_pool": "0xCCC"},
        {"symbol": "JUNKQ", "tier_quality": "C", "yield_cover": 99, "status": "OK",
         "resolve_status": "OK", "wash_flag": False, "resolved_pool": "0xDDD"},
        {"symbol": "WASH", "tier_quality": "B", "yield_cover": 50, "status": "OK",
         "resolve_status": "OK", "wash_flag": True, "resolved_pool": "0xEEE"},
    ]
    stab = [
        {"pool": "0xaaa", "fee_cover_stability": {"stable": True, "enter_frac": 0.83}},
        {"pool": "0xbbb", "fee_cover_stability": {"stable": False, "enter_frac": 0.33}},
        {"pool": "0xccc", "fee_cover_stability": {"stable": True, "enter_frac": 1.0}},
        {"pool": "0xddd", "fee_cover_stability": {"stable": True, "enter_frac": 1.0}},
        {"pool": "0xeee", "fee_cover_stability": {"stable": True, "enter_frac": 1.0}},
    ]
    vetted = vetted_menu(funnel_vet(
        bridge, stab, allow_legacy_without_netcover=True,
    ))
    syms = [r["symbol"] for r in vetted]
    assert syms == ["GOOD"], f"only GOOD passes all 3 gates, got {syms}"
    print("self-test OK: GOOD passes; UNSTABLE(stability), LOWYC(yc), "
          "JUNKQ(quality C), WASH(wash) all correctly rejected.")


def main():
    ap = argparse.ArgumentParser(description="Merge bridge + stability artifacts into a vetted menu (read-only)")
    ap.add_argument("--bridge", help="resolve_and_rank.json from the Stage-2 bridge")
    ap.add_argument("--stability", help="stability.json from multi-window stability")
    ap.add_argument("--netcover", help="WP-04 full-cost NetCover records (enables strict fifth gate)")
    ap.add_argument("--legacy-allow-missing-netcover", action="store_true",
                    help="research/intermediate only: bypass strict fifth gate")
    ap.add_argument("--yc-min", type=float, default=1.0)
    ap.add_argument("--out", default=None, help="dir to write vetted_menu.json / .md")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        run_self_test()
        return
    if not (args.bridge and args.stability):
        ap.error("--bridge and --stability are required (or use --self-test)")

    bridge = _as_list(_load(args.bridge))
    stab = _as_list(_load(args.stability))
    cover = _as_list(_load(args.netcover)) if args.netcover else None
    merged = funnel_vet(
        bridge, stab, yc_min=args.yc_min, netcover_records=cover,
        allow_legacy_without_netcover=args.legacy_allow_missing_netcover,
    )
    menu = vetted_menu(merged)

    print(f"vetted {len(menu)}/{len(merged)} pools (yc_min={args.yc_min}):")
    for r in menu:
        print(f"  ✅ {r.get('symbol'):16s} tier_q={r.get('tier_quality')} "
              f"yc={_yc_value(r.get('yield_cover')):.2f} enter_frac={r.get('enter_frac')}")

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "vetted_menu.json"), "w") as f:
            json.dump({"yc_min": args.yc_min, "merged": merged, "vetted": menu}, f, indent=2)
        with open(os.path.join(args.out, "vetted_menu.md"), "w") as f:
            f.write(_render_md(merged, args.yc_min))
        print(f"wrote {args.out}/vetted_menu.json, vetted_menu.md")


if __name__ == "__main__":
    main()
