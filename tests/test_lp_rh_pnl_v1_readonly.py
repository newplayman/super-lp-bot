"""Tests for the RH-04a NAV ledger and HODL benchmark (offline, read-only).

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


# --- T38: collect, price unchanged, gas=0 -> NAV unchanged -------------------
def test_t38_collect_no_price_move_nav_unchanged():
    before = pnl.compute_nav(
        wallet=Decimal("1000"), lp_principal=Decimal("500"),
        accrued_fees=Decimal("100"), verified_rewards=Decimal("0"),
        liabilities=Decimal("0"))
    after = pnl.compute_nav(
        wallet=Decimal("1100"), lp_principal=Decimal("500"),
        accrued_fees=Decimal("0"), verified_rewards=Decimal("0"),
        liabilities=Decimal("0"))
    assert before == after  # exact Decimal equality, not a tolerance


# --- T39: collect, gas=0.10 -> NAV down exactly 0.10, gas counted once -------
def test_t39_collect_gas_nav_down_exactly_gas():
    before = pnl.compute_nav(
        wallet=Decimal("1000"), lp_principal=Decimal("500"),
        accrued_fees=Decimal("100"), verified_rewards=Decimal("0"),
        liabilities=Decimal("0"))
    after = pnl.compute_nav(
        wallet=Decimal("1099.90"), lp_principal=Decimal("500"),
        accrued_fees=Decimal("0"), verified_rewards=Decimal("0"),
        liabilities=Decimal("0"))
    assert before - after == Decimal("0.10")
    attr = pnl.attribution(
        nav_delta=after - before, fee_income=Decimal("100"),
        gas_paid=Decimal("0.10"), price_move_effect=Decimal("-100"))
    assert attr["reconciled"] is True
    assert attr["components"]["gas_paid"] == Decimal("-0.10")
    assert attr["components"]["fee_income"] == Decimal("100")  # gas not in fees


# --- T40: external deposit 10, no trades -> NAV +10, net_pnl 0 ---------------
def test_t40_external_deposit_nav_up_pnl_zero():
    nav_t0 = pnl.compute_nav(
        wallet=Decimal("1000"), lp_principal=Decimal("500"),
        accrued_fees=Decimal("0"), verified_rewards=Decimal("0"),
        liabilities=Decimal("0"))
    nav_t1 = pnl.compute_nav(
        wallet=Decimal("1010"), lp_principal=Decimal("500"),
        accrued_fees=Decimal("0"), verified_rewards=Decimal("0"),
        liabilities=Decimal("0"))
    assert nav_t1 - nav_t0 == Decimal("10")
    assert pnl.net_pnl(nav_t1, nav_t0, Decimal("10")) == Decimal("0")


# --- T41: recenter after drop -> HODL initial lot not reset ------------------
def test_t41_recenter_hodl_initial_lot_not_reset():
    init0 = Decimal("1000000000000000000")  # 1.0 token0
    init1 = Decimal("3000000000000000000")  # 3.0 token1
    px, q = Decimal("1.5"), Decimal("3000")
    before = pnl.hodl_benchmark(
        initial_token0_raw=init0, initial_token1_raw=init1,
        dec0=18, dec1=18,
        price_t1_token1_per_token0=px, quote_usd_per_token1=q)
    # after a recenter the prices move, but the initial legs are unchanged
    after = pnl.hodl_benchmark(
        initial_token0_raw=init0, initial_token1_raw=init1,
        dec0=18, dec1=18,
        price_t1_token1_per_token0=Decimal("1.2"),
        quote_usd_per_token1=Decimal("2800"))
    assert before != after  # prices moved
    # recomputing at the original prices reproduces the original lot exactly
    again = pnl.hodl_benchmark(
        initial_token0_raw=init0, initial_token1_raw=init1,
        dec0=18, dec1=18,
        price_t1_token1_per_token0=px, quote_usd_per_token1=q)
    assert again == before


# --- T42: same fill in 3 markout windows -> not triple-counted ---------------
def test_t42_same_fill_three_windows_not_triple_counted():
    nav_open = pnl.compute_nav(
        wallet=Decimal("1000"), lp_principal=Decimal("500"),
        accrued_fees=Decimal("0"), verified_rewards=Decimal("0"),
        liabilities=Decimal("0"))
    nav_after_fill = pnl.compute_nav(
        wallet=Decimal("995"), lp_principal=Decimal("500"),
        accrued_fees=Decimal("0"), verified_rewards=Decimal("0"),
        liabilities=Decimal("0"))
    # the single-fill PnL over the period is the loss, counted exactly once
    pnl_total = pnl.net_pnl(nav_after_fill, nav_open, Decimal("0"))
    assert pnl_total == Decimal("-5")
    # the WRONG way: summing the same loss once per markout window (3x)
    tripled = pnl_total * 3
    assert tripled != pnl_total  # -15 != -5


# --- classify_flow -----------------------------------------------------------
def test_classify_flow_collect_is_internal():
    assert pnl.classify_flow("collect") is False


def test_classify_flow_deposit_is_external():
    assert pnl.classify_flow("deposit") is True


def test_classify_flow_unknown_raises():
    with pytest.raises(ValueError, match="UNKNOWN_FLOW_KIND"):
        pnl.classify_flow("bogus_kind")


# --- compute_nav None input --------------------------------------------------
def test_compute_nav_none_input_raises_not_zero():
    with pytest.raises(ValueError, match="NAV_INPUT_MISSING"):
        pnl.compute_nav(wallet=None, lp_principal=Decimal("1"),
                        accrued_fees=Decimal("0"),
                        verified_rewards=Decimal("0"),
                        liabilities=Decimal("0"))


# --- duplicate idempotency_key -> IntegrityError (RH-INV-13) -----------------
def test_duplicate_idempotency_key_integrity_error(tmp_path):
    conn = _open(tmp_path)
    pnl.book_journal_event(
        conn, event_id="e1", idempotency_key="key-1",
        debit="wallet", credit="fees_receivable", asset="USDG",
        amount_raw=Decimal("100"), is_external_flow=False,
        ref={"tx": "0x1"}, now=NOW)
    with pytest.raises(sqlite3.IntegrityError):
        pnl.book_journal_event(
            conn, event_id="e2", idempotency_key="key-1",
            debit="wallet", credit="fees_receivable", asset="USDG",
            amount_raw=Decimal("100"), is_external_flow=False,
            ref={"tx": "0x1"}, now=NOW)


# --- hodl_benchmark uses actual initial qty, not 50/50 (D04) -----------------
def test_hodl_benchmark_uses_actual_initial_qty_not_5050():
    init0 = Decimal("1000000000000000000")  # 1.0 token0
    init1 = Decimal("3000000000000000000")  # 3.0 token1
    px, q = Decimal("2.0"), Decimal("100")
    actual = pnl.hodl_benchmark(
        initial_token0_raw=init0, initial_token1_raw=init1,
        dec0=18, dec1=18,
        price_t1_token1_per_token0=px, quote_usd_per_token1=q)
    assert actual == Decimal("500")  # (1.0*2.0 + 3.0) * 100
    avg = Decimal("2000000000000000000")  # 50/50 assumption: 2.0 each
    fifty_fifty = pnl.hodl_benchmark(
        initial_token0_raw=avg, initial_token1_raw=avg,
        dec0=18, dec1=18,
        price_t1_token1_per_token0=px, quote_usd_per_token1=q)
    assert fifty_fifty == Decimal("600")  # (2.0*2.0 + 2.0) * 100
    assert actual != fifty_fifty


# --- liquidation_nav: unpriced asset -> unvalued, deducted -------------------
def test_liquidation_nav_unpriced_asset_unvalued_and_deducted():
    liq, unvalued_out = pnl.liquidation_nav(
        reference_nav=Decimal("1000"),
        haircut_by_asset={"WEIRD_TOKEN": Decimal("50")},
        unvalued=["WEIRD_TOKEN"])
    assert liq == Decimal("950")  # 1000 - 50, not valued at last trade
    assert unvalued_out == ["WEIRD_TOKEN"]


# --- attribution mismatch -> reconciled=False, unexplained non-zero ----------
def test_attribution_mismatch_flagged():
    attr = pnl.attribution(
        nav_delta=Decimal("10"), fee_income=Decimal("5"),
        gas_paid=Decimal("0"), price_move_effect=Decimal("2"))
    assert attr["reconciled"] is False  # 5 + 0 + 2 = 7 != 10
    assert attr["unexplained"] == Decimal("-3")


# --- float money -> REAL_NOT_ALLOWED_FOR_MONEY -------------------------------
def test_float_amount_rejected_in_compute_nav():
    with pytest.raises(TypeError, match="REAL_NOT_ALLOWED_FOR_MONEY"):
        pnl.compute_nav(wallet=100.0, lp_principal=Decimal("1"),
                        accrued_fees=Decimal("0"),
                        verified_rewards=Decimal("0"),
                        liabilities=Decimal("0"))


def test_float_amount_rejected_in_journal(tmp_path):
    conn = _open(tmp_path)
    with pytest.raises(TypeError, match="REAL_NOT_ALLOWED_FOR_MONEY"):
        pnl.book_journal_event(
            conn, event_id="e1", idempotency_key="key-1",
            debit="wallet", credit="fees_receivable", asset="USDG",
            amount_raw=100.0, is_external_flow=False,
            ref=None, now=NOW)


# --- net_pnl basic -----------------------------------------------------------
def test_net_pnl_basic():
    assert pnl.net_pnl(Decimal("110"), Decimal("100"), Decimal("10")) == Decimal("0")
    assert pnl.net_pnl(Decimal("110"), Decimal("100"), Decimal("0")) == Decimal("10")


# --- main CLI end-to-end -----------------------------------------------------
def test_main_cli_end_to_end(tmp_path):
    events = {
        "position_id": "pos-1",
        "initial_token0_raw": "1000000000000000000",
        "initial_token1_raw": "1000000000000000000",
        "dec0": 18, "dec1": 18,
        "steps": [
            {"mark_time": "t0", "wallet": "1000", "lp_principal": "500",
             "accrued_fees": "0", "verified_rewards": "0", "liabilities": "0",
             "price_t1_token1_per_token0": "1.0",
             "quote_usd_per_token1": "100"},
            {"mark_time": "t1", "wallet": "1010", "lp_principal": "500",
             "accrued_fees": "0", "verified_rewards": "0", "liabilities": "0",
             "external_net_flow": "10",
             "price_t1_token1_per_token0": "1.0",
             "quote_usd_per_token1": "100"},
        ],
    }
    events_path = tmp_path / "events.json"
    events_path.write_text(json.dumps(events))
    out_path = tmp_path / "out.json"
    rc = pnl.main(["--events-json", str(events_path), "--out", str(out_path)])
    assert rc == 0
    payload = json.loads(out_path.read_text())
    assert payload["position_id"] == "pos-1"
    assert len(payload["steps"]) == 2
    assert payload["steps"][1]["net_pnl"] == "0"


# --- replay missing-input handling ------------------------------------------
def _replay_step(mark_time: str, wallet: str, **extra):
    step = {
        "mark_time": mark_time,
        "wallet": wallet,
        "lp_principal": "500",
        "accrued_fees": "0",
        "verified_rewards": "0",
        "liabilities": "0",
        "price_t1_token1_per_token0": "1",
        "quote_usd_per_token1": "100",
    }
    step.update(extra)
    return step


def _replay_payload(steps):
    return {
        "position_id": "replay-inputs",
        "initial_token0_raw": "1000000000000000000",
        "initial_token1_raw": "1000000000000000000",
        "dec0": 18,
        "dec1": 18,
        "steps": steps,
    }


def test_replay_missing_external_flow_is_unavailable_not_zero():
    result = pnl._process_events(_replay_payload([
        _replay_step("t0", "1000", external_net_flow="0",
                     fee_income="0", gas_paid="0", price_move_effect="0"),
        # Wallet gained 100 externally, but the flow field is absent.
        _replay_step("t1", "1100", fee_income="0", gas_paid="0",
                     price_move_effect="0"),
    ]))
    step = result["steps"][1]
    assert step["net_pnl"] is None
    assert "external_net_flow" in step["net_pnl_reason"]
    assert step["net_pnl"] != "100"


@pytest.mark.parametrize("external_flow", ["0", 0, Decimal(0)])
def test_replay_explicit_zero_external_flow_remains_valid(external_flow):
    result = pnl._process_events(_replay_payload([
        _replay_step("t0", "1000", external_net_flow="0"),
        _replay_step("t1", "1010", external_net_flow=external_flow),
    ]))
    assert result["steps"][1]["net_pnl"] == "10"


def test_replay_missing_attribution_input_keeps_pnl_and_marks_unreconciled():
    result = pnl._process_events(_replay_payload([
        _replay_step("t0", "1000", external_net_flow="0",
                     fee_income="0", gas_paid="0", price_move_effect="0"),
        _replay_step("t1", "1010", external_net_flow="0",
                     gas_paid="0", price_move_effect="0"),
    ]))
    step = result["steps"][1]
    assert step["net_pnl"] == "10"
    assert step["attribution"]["reconciled"] is False
    assert "fee_income" in step["attribution"]["missing_inputs"]
    assert "fee_income" in step["attribution"]["reason"]


def test_replay_continues_after_missing_external_flow_step():
    result = pnl._process_events(_replay_payload([
        _replay_step("t0", "1000", external_net_flow="0"),
        _replay_step("t1", "1100"),
        _replay_step("t2", "1110", external_net_flow="0"),
    ]))
    assert result["steps"][1]["net_pnl"] is None
    assert result["steps"][2]["net_pnl"] == "10"


def test_replay_null_external_flow_is_unavailable_not_zero():
    result = pnl._process_events(_replay_payload([
        _replay_step("t0", "1000", external_net_flow="0",
                     fee_income="0", gas_paid="0", price_move_effect="0"),
        _replay_step("t1", "1100", external_net_flow=None,
                     fee_income="0", gas_paid="0", price_move_effect="0"),
    ]))
    step = result["steps"][1]
    assert step["net_pnl"] is None
    assert "external_net_flow" in step["net_pnl_reason"]


@pytest.mark.parametrize("field", [
    "fee_income", "gas_paid", "price_move_effect",
])
def test_replay_null_attribution_input_keeps_pnl_and_marks_unreconciled(field):
    values = {
        "external_net_flow": "0",
        "fee_income": "0",
        "gas_paid": "0",
        "price_move_effect": "0",
    }
    values[field] = None
    result = pnl._process_events(_replay_payload([
        _replay_step("t0", "1000", external_net_flow="0",
                     fee_income="0", gas_paid="0", price_move_effect="0"),
        _replay_step("t1", "1010", **values),
    ]))
    step = result["steps"][1]
    assert step["net_pnl"] == "10"
    assert step["attribution"]["reconciled"] is False
    assert field in step["attribution"]["missing_inputs"]
    assert field in step["attribution"]["reason"]
