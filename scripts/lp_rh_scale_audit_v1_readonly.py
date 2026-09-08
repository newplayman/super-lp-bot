"""RH-09a: cross-scale consistency audit for precision-class silent errors.

Read-only. No network, no live-DB writes. Companion to
reports/rh_pivot/20260907T124500Z/COST_MODEL_PRICE_SCALE_BUG.md.

The lesson encoded here: any value handed across a precision boundary must be
checked across multiple position scales. A single-point check cannot catch a
constant ratio error (the raw-ratio-as-price bug looked perfectly plausible at
one size and only broke when compared across three scales).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
from collections.abc import Sequence
from decimal import Decimal

# A line that computes the raw sqrtPriceX96^2 ratio. The 2**96 exponent is the
# signature; the decimals-normalised price multiplies this by 10**dec0/10**dec1.
_RAW_RATIO_EXP = re.compile(r"\*\*\s*96\b")
# A precision scaling by 10 to a decimal-count power (10 ** d0, Decimal(10) ** dec0, ...).
_PRECISION_SCALE = re.compile(r"(?:10|Decimal\(\s*10\s*\))\s*\*\*\s*(?:d\d+|\w*dec\w*)")


def _is_raw_ratio_line(line: str) -> bool:
    return "sqrt_price_x96" in line and _RAW_RATIO_EXP.search(line) is not None


def _has_precision_scaling(text: str) -> bool:
    return _PRECISION_SCALE.search(text) is not None


def _relative_deviation(values: Sequence[Decimal]) -> Decimal:
    """Max relative deviation of values from their mean (0 if all zero)."""
    if not values:
        return Decimal(0)
    mean = sum(values) / len(values)
    if mean == 0:
        return Decimal(0) if all(v == 0 for v in values) else Decimal("Infinity")
    return max(abs(v - mean) / abs(mean) for v in values)


def scale_invariance_check(fn, *, base_kwargs, scale_key: str, scales: Sequence[Decimal], expected: str) -> dict:
    """Evaluate fn across scales and check the value-vs-scale shape.

    expected: "LINEAR" (value/scale constant), "CONSTANT" (value constant),
    "SUBLINEAR" (value/scale non-decreasing but bounded <5x).
    Any None value -> verdict INPUTS_UNAVAILABLE (never treated as 0).
    """
    scales = list(scales)
    values = []
    for scale in scales:
        kwargs = dict(base_kwargs)
        kwargs[scale_key] = scale
        values.append(fn(**kwargs))

    result = {
        "scales": scales,
        "values": values,
        "ratios": [],
        "expected": expected,
        "verdict": "OK",
        "detail": "",
    }

    if any(v is None for v in values):
        result["verdict"] = "INPUTS_UNAVAILABLE"
        result["detail"] = "one or more scale points returned None; not comparable"
        return result

    dec_values = [Decimal(v) for v in values]
    dec_scales = [Decimal(s) for s in scales]
    ratios = [dv / ds for dv, ds in zip(dec_values, dec_scales)]
    result["ratios"] = ratios

    if expected == "LINEAR":
        dev = _relative_deviation(ratios)
        ok = dev < Decimal("0.05")
        result["verdict"] = "OK" if ok else "VIOLATION"
        result["detail"] = f"value/scale relative deviation {dev} ({'<' if ok else '>='} 5%)"
    elif expected == "CONSTANT":
        dev = _relative_deviation(dec_values)
        ok = dev < Decimal("0.05")
        result["verdict"] = "OK" if ok else "VIOLATION"
        result["detail"] = f"value relative deviation {dev} ({'<' if ok else '>='} 5%)"
    elif expected == "SUBLINEAR":
        tol = Decimal("1e-9")
        non_decreasing = all(ratios[i + 1] >= ratios[i] - tol for i in range(len(ratios) - 1))
        if min(ratios) <= 0:
            bounded = False
            spread = Decimal("Infinity")
        else:
            spread = max(ratios) / min(ratios)
            bounded = spread < 5
        ok = non_decreasing and bounded
        result["verdict"] = "OK" if ok else "VIOLATION"
        result["detail"] = f"value/scale non_decreasing={non_decreasing}, max/min={spread}"
    else:
        result["verdict"] = "VIOLATION"
        result["detail"] = f"unknown expected kind {expected!r}"
    return result


def decimals_roundtrip_check(*, sqrt_price_x96: int, dec0: int, dec1: int) -> dict:
    """Recover the decimals-normalised price from the raw ratio (exact Decimal).

    ratio == 10**(dec0-dec1) when the scaling is applied; ratio == 1 means the
    raw ratio was used as the price (the COST_MODEL_PRICE_SCALE_BUG failure mode).
    """
    two = Decimal(2)
    sqrt_price = Decimal(sqrt_price_x96) / (two ** 96)
    raw = sqrt_price * sqrt_price
    human = raw * (Decimal(10) ** dec0) / (Decimal(10) ** dec1)
    ratio = human / raw
    expected_ratio = Decimal(10) ** (dec0 - dec1)
    return {
        "raw": raw,
        "human": human,
        "ratio": ratio,
        "expected_ratio": expected_ratio,
        "ok": ratio == expected_ratio,
    }


def audit_module_prices(module_name: str, source: str) -> list[dict]:
    """Heuristic scan: raw-ratio lines with no nearby decimals scaling.

    May false-positive; every finding is tagged heuristic=True.
    """
    lines = source.splitlines()
    findings = []
    for i, line in enumerate(lines):
        if not _is_raw_ratio_line(line):
            continue
        lo = max(0, i - 5)
        hi = min(len(lines), i + 6)
        window = "\n".join(lines[lo:hi])
        if not _has_precision_scaling(window):
            findings.append({
                "module": module_name,
                "line": i + 1,
                "snippet": line.strip(),
                "risk": "RAW_RATIO_USED_AS_PRICE",
                "heuristic": True,
            })
    return findings


def audit_all(scripts_dir) -> dict:
    """Run audit_module_prices over every scripts/lp_rh_*.py and summarise."""
    paths = sorted(glob.glob(os.path.join(scripts_dir, "lp_rh_*.py")))
    findings_by_module = {}
    for path in paths:
        module_name = os.path.basename(path)
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        findings = audit_module_prices(module_name, source)
        if findings:
            findings_by_module[module_name] = findings
    return {
        "scripts_dir": scripts_dir,
        "modules_scanned": len(paths),
        "modules_with_findings": len(findings_by_module),
        "findings": findings_by_module,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="RH-09a cross-scale consistency audit (read-only).")
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    result = audit_all(args.scripts_dir)
    text = json.dumps(result, indent=2, default=str)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
