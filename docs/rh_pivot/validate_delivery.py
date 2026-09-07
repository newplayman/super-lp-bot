#!/usr/bin/env python3
"""Check this documentation package, NOT the user's bot or a blockchain.

Requires Python 3.11+. No network, signing, keys, subprocesses or repo writes.
Exit 0 means only package consistency and synthetic arithmetic passed.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

try:
    import tomllib
except ImportError:
    raise SystemExit("Python 3.11+ is required for the built-in TOML parser.")

ROOT = Path(__file__).resolve().parent
D = Decimal


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    cfg = tomllib.loads((ROOT / "config.rh.shadow.example.toml").read_text(encoding="utf-8"))
    prd = (ROOT / "PRD_RH_LP_Bot_v1.1_CN.md").read_text(encoding="utf-8")
    fixture = json.loads((ROOT / "ACCEPTANCE_FIXTURES_SYNTHETIC.json").read_text(encoding="utf-8"))

    require(cfg["mode"] == "READONLY", "Default mode must remain READONLY.")
    for flag in ("live_enabled", "wallet_access_enabled", "signing_enabled", "broadcast_enabled",
                 "paid_services_allowed", "production_key_generation_allowed"):
        require(cfg[flag] is False, f"Unsafe default: {flag}")
    policy = cfg["proposed_policy"]
    require(policy["approved_for_live"] is False, "Proposed policy must not authorize live trading.")
    require(policy["cross_bucket_borrowing"] is False, "No automatic bucket borrowing.")
    require(cfg["meme"]["live_enabled"] is False and cfg["meme"]["max_live_positions"] == 0,
            "MEME live must remain disabled.")
    expected_constants = {
        "stable_min_frac": "0.7", "netcover_shadow": "1.0", "netcover_tiny_live": "1.5",
        "position_tvl_share": "0.0005", "hard_position_tvl_share": "0.001",
        "lvr_coefficient_model": "0.50",
    }
    require(cfg["protected_constants"] == expected_constants, "Protected constants differ.")
    weights = [D(policy[b]["weight"]) for b in ("core", "stock", "meme")]
    require(sum(weights) == D("1"), "Budget weights must sum to 1.")
    cap_fractions = {b: D(policy[b]["weight"]) * D(policy[b]["max_active_fraction_of_bucket"])
                     for b in ("core", "stock", "meme")}
    require(sum(cap_fractions.values()) == D("0.715"), "Active caps must sum to 71.5%.")
    capital = D(cfg["legacy_policy"]["capital_usd"])
    core_cap = capital * cap_fractions["core"]
    require(core_cap == D("42.5"), "Expected proposed 100U CORE cap of 42.5U.")
    require(core_cap < D(cfg["legacy_policy"]["position_min_usd"]),
            "Expected explicit conflict with legacy 50U minimum.")

    require(fixture["data_kind"] == "SYNTHETIC_NOT_CHAIN_DATA", "Fixtures must be labelled synthetic.")
    f = fixture["stock_units"]
    qty = D(f["raw_balance"]) / (D(10) ** int(f["token_decimals"]))
    multiplier = D(f["multiplier_raw"]) / (D(10) ** 18)
    price = D(f["underlying_usd"]) * multiplier
    require(qty == D(f["expected_tokens"]), "Token quantity mismatch.")
    require(qty * multiplier == D(f["expected_share_equivalent"]), "Share equivalent mismatch.")
    require(price == D(f["expected_token_usd"]), "Token price mismatch.")
    require(qty * price == D(f["expected_nav_usd"]), "NAV mismatch.")
    require(abs(price / D(f["usdg_usd"]) - D(f["expected_token_usdg_approx"])) < D("0.00000001"),
            "USDG normalization mismatch.")
    split = fixture["split"]
    require(D(split["before_underlying"]) * D(split["before_multiplier"]) ==
            D(split["after_underlying"]) * D(split["after_multiplier"]),
            "Synthetic split must preserve per-token reference value.")
    collect = fixture["collect"]
    before = D(collect["wallet_before"]) + D(collect["lp_principal"]) + D(collect["uncollected_fee"])
    after = (D(collect["wallet_before"]) + D(collect["uncollected_fee"]) - D(collect["gas"]) +
             D(collect["lp_principal"]))
    require(after - before == -D(collect["gas"]), "Collect must only lose gas in this fixture.")
    flow = fixture["external_flow"]
    require(D(flow["nav_after"]) - D(flow["nav_before"]) - D(flow["external_net_injection"]) == D("0"),
            "Deposit must not create PnL.")

    cases = re.findall(r"^\| (T\d{2}) \|", prd, re.MULTILINE)
    require(cases == [f"T{i:02}" for i in range(1, 61)], "Must contain ordered unique T01–T60 matrix.")
    headers = re.findall(r"^## (\d+)\.", prd, re.MULTILINE)
    require(headers == [str(i) for i in range(29)], "Expected PRD sections 0–28.")
    require(prd.count("```") % 2 == 0, "Unbalanced Markdown code fences.")
    cited = {int(x) for x in re.findall(r"\[R(\d{2})", prd)}
    defined = {int(x) for x in re.findall(r"\*\*R(\d{2}) —", prd)}
    require(cited <= defined, f"Undefined references: {cited - defined}")
    require(defined == set(range(1, 26)), "Expected source registry R01–R25.")

    manifest_path = ROOT / "INPUT_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["inputs"]:
        path = ROOT / item["relative_path"]
        require(path.is_file(), f"Missing input: {item['relative_path']}")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"],
                f"Input checksum mismatch: {item['relative_path']}")

    result = {
        "verdict": "PASS",
        "scope": "DOCUMENT_PACKAGE_AND_SYNTHETIC_ARITHMETIC_ONLY",
        "config_toml_valid": True,
        "unsafe_defaults_enabled": False,
        "protected_constants_preserved_in_example": True,
        "proposed_active_cap_fraction": str(sum(cap_fractions.values())),
        "proposed_100_usd_core_cap": str(core_cap),
        "legacy_capital_policy_conflict_detected": True,
        "acceptance_matrix_cases": len(cases),
        "prd_sections": len(headers),
        "source_registry_entries": len(defined),
        "input_checksums_verified": True,
        "existing_repository_tested": False,
        "blockchain_rpc_verified": False,
        "live_authorized": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
        print(json.dumps({"verdict": "FAIL", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
