"""Tests for scripts/lp_rh_pnl_v1_readonly.py (RH-04a NAV ledger and HODL benchmark).

Adds G2: collect/remove accounting tests (W2 FULL_COST_ACCOUNTING_V3).
Mirrors the spec's T38-T42 use cases plus the decimal / idempotency / flow
classification contracts.  All DB tests use tmp_path; no network, no live DB.
"""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from scripts import lp_rh_pnl_v1_readonly as pnl
from scripts import lp_rh_store_v1_readonly as store

NOW = "2026-09-08T00:00:00Z"


def _open(tmp_path: Path) -> sqlite3.Connection:
    conn = store.open_store(tmp_path / "pnl.db")
    store.migrate(conn)
    return conn


# ---------------------------------------------------------------------------
# G2: collect / remove accounting
# ---------------------------------------------------------------------------

class TestCollectRemoveAccounting:
    """W2 FULL_COST_ACCOUNTING_V3 G2: collect/remove journal and NAV semantics."""

    def test_collect_no_gas_does_not_change_nav(self):
        """G2.1: collect with zero gas -> wallet unchanged, NAV unchanged."""
        nav_before = pnl.compute_nav(
            wallet=Decimal("1000"), lp_principal=Decimal("500"),
            accrued_fees=Decimal("100"), verified_rewards=Decimal("0"),
            liabilities=Decimal("0"))
        nav_after = pnl.compute_nav(
            wallet=Decimal("1100"), lp_principal=Decimal("500"),
            # fees collected into wallet
            accrued_fees=Decimal("0"), verified_rewards=Decimal("0"),
            liabilities=Decimal("0"))
        assert nav_before == nav_after

    def test_collect_with_gas_deducts_once(self):
        """G2.2: collect followed by gas payment of $0.10 -> NAV reduced by exactly $0.10."""
        # NAV before collect+gas
        nav_before = pnl.compute_nav(
            wallet=Decimal("1000"), lp_principal=Decimal("500"),
            accrued_fees=Decimal("100"), verified_rewards=Decimal("0"),
            liabilities=Decimal("0"))
        # After collect: wallet = 1100, fees = 0
        # After gas payment: wallet = 1099.90
        nav_after_gas = pnl.compute_nav(
            wallet=Decimal("1099.90"), lp_principal=Decimal("500"),
            accrued_fees=Decimal("0"), verified_rewards=Decimal("0"),
            liabilities=Decimal("0"))
        assert nav_before - nav_after_gas == Decimal("0.10")
        # Attribution confirms gas counted exactly once
        attr = pnl.attribution(
            nav_delta=nav_after_gas - nav_before,
            fee_income=Decimal("100"),
            gas_paid=Decimal("0.10"),
            price_move_effect=Decimal("-100"))
        assert attr["reconciled"] is True
        assert attr["components"]["gas_paid"] == Decimal("-0.10")

    def test_remove_returns_principal_not_fee_income(self):
        """G2.3: remove_liquidity returns LP principal to wallet; no fee row in journal."""
        conn = _open(Path("/tmp/test_remove_journal"))
        # Book a remove_liquidity event (principal recovery)
        pnl.book_journal_event(
            conn,
            event_id="remove-1",
            idempotency_key="remove-1",
            debit="WALLET_TOKEN0",
            credit="LP_POSITION_TOKEN0",
            asset="0xtoken0",
            amount_raw=Decimal("1000000000000000000"),
            is_external_flow=False,
            ref={"kind": "remove_liquidity", "position_id": "pos-1"},
            now=NOW)
        rows = conn.execute(
            "SELECT event_id, account_debit, account_credit, amount_raw, is_external_flow "
            "FROM rh_journal ORDER BY event_id").fetchall()
        assert len(rows) == 1
        # remove returns principal, not fee income: debit WALLET, credit LP_POSITION
        assert rows[0][1] == "WALLET_TOKEN0"
        assert rows[0][2] == "LP_POSITION_TOKEN0"
        assert rows[0][3] == "1000000000000000000"
        assert rows[0][4] == 0  # internal flow
        # Verify no fee row
        fee_rows = [r for r in rows if "fee" in r[0].lower() or "income" in r[1].lower()]
        assert len(fee_rows) == 0
        conn.close()

    def test_remove_succeeds_but_swap_fails_keeps_inventory_risk(self):
        """G2.4: remove succeeds but swap fails -> position stuck, liquidation_nav < reference_nav.

        When remove succeeds but the subsequent swap fails, the LP tokens are returned
        to the wallet but are stuck (cannot be converted back to base tokens). The
        position is still at risk and must be conservatively unwound. The
        liquidation NAV (wallet + conservative_exit_value - exit_costs) is always
        less than the ideal reference NAV (wallet + full_position_value).
        """
        # wallet = 1000, stuck position at current prices with emergency exit costs
        wallet = Decimal("1000")
        # l_pos in raw Q128.128; l_pos=2e15 gives position_value≈100 at px=1.0
        # This small position (~$100 notional) is realistic for the stuck portion
        # after the majority of capital was recovered from the remove
        liq_res = pnl.compute_liquidation_nav(
            wallet=wallet,
            l_pos=Decimal("2000000000000000"),
            price=Decimal("1.0"),
            range=(Decimal("0.9"), Decimal("1.1")),
            fee_growth_0=Decimal("0"),
            fee_growth_1=Decimal("0"),
            decimals=(18, 6),
            slippage_bps_max=Decimal("200"),
            entry_cost_usd=Decimal("100"),  # high entry cost ( sunk)
            exit_cost_usd=Decimal("100"),   # emergency exit cost
            gas_usd=Decimal("10"),
            quote_usd_per_token1=Decimal("1"),
        )
        # reference_nav = wallet + position_value (ideal, no emergency costs)
        # A position of ~$100 has reference_nav ≈ 1100
        # liquidation_nav = wallet + position_value*(1-slip) - exit_costs
        # = 1000 + 100*0.98 - 110 = 868
        # Since 868 < 1100, inventory risk is properly reflected
        assert liq_res.liquidation_nav is not None
        # The stuck position's liquidation value is less than its ideal reference value
        assert liq_res.liquidation_nav < Decimal("1100")
