"""Test Suite D: Liquidation NAV Matrix & Zero Threshold-Branch AST Inspection.

Validates compute_liquidation_nav across a wide parameter matrix of principal,
token decimal pairs, and range percentages against analytic reference inventory.
Performs static AST inspection on scripts/lp_rh_pnl_v1_readonly.py to verify
zero numeric threshold branches on liquidity (R3 Package E compliance).
"""

import ast
from decimal import Decimal
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_pnl_v1_readonly import compute_liquidation_nav
from scripts.lp_rh_v3_inventory_v1_readonly import inventory_for_position

PRINCIPALS = [Decimal("1"), Decimal("10"), Decimal("50"), Decimal("1000")]
DECIMALS = [(18, 6), (6, 18), (18, 18)]
RANGES = [Decimal("5"), Decimal("10"), Decimal("50"), Decimal("90")]
PRICE = Decimal("2000.0")


@pytest.mark.parametrize("principal", PRINCIPALS)
@pytest.mark.parametrize("dec0,dec1", DECIMALS)
@pytest.mark.parametrize("range_pct", RANGES)
def test_paper_d_liquidation_nav_matrix(principal, dec0, dec1, range_pct):
    """Verify compute_liquidation_nav equals analytic reference with relative error <= 1e-10."""
    inv = inventory_for_position(
        position_usd=principal,
        entry_price=PRICE,
        range_pct=range_pct,
        dec0=dec0,
        dec1=dec1,
        quote_usd_per_token1=Decimal("1.0"),
    )
    res = compute_liquidation_nav(
        wallet=Decimal("0"),
        l_pos=inv.liquidity_raw,
        price=PRICE,
        range=range_pct,
        fee_growth_0=Decimal("0"),
        fee_growth_1=Decimal("0"),
        decimals=(dec0, dec1),
        slippage_bps_max=Decimal("0"),
        entry_cost_usd=Decimal("0"),
        exit_cost_usd=Decimal("0"),
        gas_usd=Decimal("0"),
        quote_usd_per_token1=Decimal("1.0"),
    )
    assert res.nav is not None, f"Liquidation NAV calculation failed: {res.reason}"
    rel_err = abs(res.nav - principal) / principal
    assert rel_err <= Decimal("1e-10"), (
        f"Relative error {rel_err} exceeds 1e-10 for "
        f"principal={principal}, dec0={dec0}, dec1={dec1}, range_pct={range_pct}"
    )


def test_paper_d_ast_zero_numeric_threshold_branch():
    """Verify static AST of compute_liquidation_nav has no numeric threshold branch on liquidity.

    R3 Package E removed arbitrary threshold branches (e.g. l >= scale_factor),
    replacing them with fail-close exact math.
    """
    pnl_path = REPO_ROOT / "scripts" / "lp_rh_pnl_v1_readonly.py"
    tree = ast.parse(pnl_path.read_text(encoding="utf-8"), filename=str(pnl_path))

    target_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "compute_liquidation_nav":
            target_fn = node
            break

    assert target_fn is not None, "compute_liquidation_nav not found in AST"

    # Traverse AST and assert no If condition references scale_factor
    for node in ast.walk(target_fn):
        if isinstance(node, ast.If):
            test_dump = ast.dump(node.test)
            assert "scale_factor" not in test_dump, (
                f"Found scale_factor in If condition: {test_dump}"
            )
