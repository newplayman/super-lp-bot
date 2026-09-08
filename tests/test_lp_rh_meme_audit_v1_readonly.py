import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

import json
from decimal import Decimal

from scripts.lp_rh_meme_audit_v1_readonly import (
    admission_check,
    downtrend_recenter_guard,
    exit_direction_check,
    exit_state_machine,
    main,
    residual_inventory_accounting,
)


def _facts(**changes):
    facts = {
        "can_sell": True,
        "can_reduce": True,
        "transfer_tax_bps": 0,
        "owner_can_mint": False,
        "can_blacklist": False,
        "can_change_tax": False,
        "proxy_can_change_implementation": False,
        "lp_concentration_ok": True,
        "liquidity_sudden_drop": False,
        "holder_concentration_evidence": True,
    }
    facts.update(changes)
    return facts


def test_compliant_facts_pass():
    assert admission_check(_facts()) == (True, [])


def test_transfer_tax_five_percent_is_rejected():
    allowed, reasons = admission_check(_facts(transfer_tax_bps=500))
    assert not allowed
    assert "TRANSFER_TAX_BPS_NONZERO" in reasons


def test_unknown_transfer_tax_is_not_zero():
    allowed, reasons = admission_check(_facts(transfer_tax_bps=None))
    assert not allowed
    assert "UNKNOWN_TRANSFER_TAX_BPS" in reasons


def test_any_unknown_fact_has_unknown_reason():
    for key in _facts():
        allowed, reasons = admission_check(_facts(**{key: None}))
        assert not allowed
        assert any(reason.startswith("UNKNOWN_") for reason in reasons)


def test_cannot_sell_is_hard_reject():
    allowed, reasons = admission_check(_facts(can_sell=False))
    assert not allowed
    assert "CANNOT_SELL_OR_REDUCE_POSITION" in reasons


def test_cannot_reduce_is_hard_reject():
    allowed, reasons = admission_check(_facts(can_reduce=False))
    assert not allowed
    assert "CANNOT_SELL_OR_REDUCE_POSITION" in reasons


def test_owner_arbitrary_mint_is_rejected():
    allowed, reasons = admission_check(_facts(owner_can_mint=True))
    assert not allowed
    assert "OWNER_CAN_MINT_ARBITRARILY" in reasons


def test_blacklist_is_rejected():
    allowed, reasons = admission_check(_facts(can_blacklist=True))
    assert not allowed
    assert "BLACKLIST_ENABLED" in reasons


def test_tax_change_is_rejected():
    allowed, reasons = admission_check(_facts(can_change_tax=True))
    assert not allowed
    assert "TAX_CHANGEABLE" in reasons


def test_proxy_upgrade_is_rejected():
    allowed, reasons = admission_check(_facts(proxy_can_change_implementation=True))
    assert not allowed
    assert "PROXY_IMPLEMENTATION_CHANGEABLE" in reasons


def test_lp_concentration_is_rejected():
    allowed, reasons = admission_check(_facts(lp_concentration_ok=False))
    assert not allowed
    assert "LP_CONCENTRATION_OVER_THRESHOLD" in reasons


def test_liquidity_drop_is_rejected():
    allowed, reasons = admission_check(_facts(liquidity_sudden_drop=True))
    assert not allowed
    assert "LIQUIDITY_SUDDEN_DROP" in reasons


def test_holder_evidence_missing_is_rejected():
    allowed, reasons = admission_check(_facts(holder_concentration_evidence=False))
    assert not allowed
    assert "HOLDER_CONCENTRATION_EVIDENCE_MISSING" in reasons


def test_t43_downtrend_cannot_recenter_lower():
    status, reason = downtrend_recenter_guard(
        price_now=Decimal("9"), range_lower=Decimal("10"),
        trend_slope=Decimal("-1"), volume_trend=Decimal("-2"))
    assert (status, reason) == ("REMOVE_EVAL", "NO_DOWNTREND_RECENTER")
    assert status in {"REMOVE_EVAL", "HOLD", "NORMAL"}
    assert "RECENTER_LOWER" not in status.upper()


def test_downtrend_inside_range_holds():
    assert downtrend_recenter_guard(
        price_now=Decimal("10.5"), range_lower=Decimal("10"),
        trend_slope=Decimal("-1"), volume_trend=Decimal("-1"))[0] == "HOLD"


def test_normal_trend_is_normal():
    assert downtrend_recenter_guard(
        price_now=Decimal("11"), range_lower=Decimal("10"),
        trend_slope=Decimal("1"), volume_trend=Decimal("1")) == (
            "NORMAL", "RANGE_MAINTAINED")


def test_t44_remove_without_swap_keeps_risk():
    state, details = exit_state_machine(remove_ok=True, swap_ok=False, atomic=False)
    assert state == "REMOVED_RISKY_INVENTORY"
    assert details["cash_closed"] is False
    assert details["asset_cap_released"] is False
    assert details["residual_risk"] is True


def test_t45_atomic_swap_failure_reverts_remove():
    state, details = exit_state_machine(remove_ok=True, swap_ok=False, atomic=True)
    assert state == "ATOMIC_EXIT_REVERTED"
    assert details["remove_effective"] is False


def test_unknown_swap_does_not_release_cap():
    state, details = exit_state_machine(remove_ok=True, swap_ok=None, atomic=False)
    assert state == "EXIT_UNKNOWN_RECONCILE_REQUIRED"
    assert details["asset_cap_released"] is False


def test_clean_exit_reconciles():
    state, details = exit_state_machine(remove_ok=True, swap_ok=True, atomic=True)
    assert state == "CLOSED_RECONCILED"
    assert details["cash_closed"] is True
    assert details["asset_cap_released"] is True


def test_t46_exit_to_full_usdg_is_blocked():
    result = exit_direction_check(
        from_asset="MEME", to_asset="USDG",
        current_exposure={"USDG": Decimal("100")},
        caps={"USDG": Decimal("100")},
    )
    assert result == (False, "EXIT_INCREASES_CAPPED_EXPOSURE:USDG")


def test_exit_direction_allows_uncapped_target():
    assert exit_direction_check(
        from_asset="MEME", to_asset="USDG",
        current_exposure={"USDG": Decimal("99")},
        caps={"USDG": Decimal("100")},
    ) == (True, "OK")


def test_residual_inventory_keeps_cap_and_nav_flags():
    row = residual_inventory_accounting(
        asset="MEME", quantity=Decimal("5"), mark_price=Decimal("2"),
        cost_basis=Decimal("20"), reference_nav=Decimal("100"))
    assert row["asset_cap_released"] is False
    assert row["counts_toward_asset_cap"] is True
    assert row["counts_toward_drawdown"] is True
    assert row["counts_toward_liquidation_nav"] is True
    assert row["liquidation_value"] == Decimal("10")
    assert row["unrealized_pnl"] == Decimal("-10")
    assert row["rh_journal"]["amount_raw"] == "5"


def test_residual_amount_alias_is_supported():
    row = residual_inventory_accounting(token="MEME", amount=Decimal("3"), price=Decimal("4"))
    assert row["asset"] == "MEME"
    assert row["residual_amount"] == Decimal("3")
    assert row["liquidation_value"] == Decimal("12")


def test_main_cli_is_offline_and_writes_audit(tmp_path):
    facts_path = tmp_path / "facts.json"
    out_path = tmp_path / "audit.json"
    facts_path.write_text(json.dumps(_facts(transfer_tax_bps=500)), encoding="utf-8")
    assert main(["--facts-json", str(facts_path), "--out", str(out_path)]) == 0
    result = json.loads(out_path.read_text(encoding="utf-8"))
    assert result["allowed"] is False
    assert "TRANSFER_TAX_BPS_NONZERO" in result["reasons"]
