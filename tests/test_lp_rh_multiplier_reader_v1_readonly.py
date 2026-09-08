from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from scripts import lp_rh_multiplier_reader_v1_readonly as mr

NOW = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
IMPL = "0xb35490d6f9163de4f80d88dc75c3516eb64c5ae2"
OTHER = "0x1111111111111111111111111111111111111111"
SRC = (Path(__file__).resolve().parents[1]
       / "scripts/lp_rh_multiplier_reader_v1_readonly.py").read_text()


def make_rpc(calls):
    def rpc_fn(to, data, block="latest"):
        if data not in calls:
            raise RuntimeError(f"revert: no fixture for {data}")
        return calls[data]
    return rpc_fn


def crwd_calls():
    return {
        mr.SEL_MULTIPLIER: "0x3782dace9d900000",
        mr.SEL_MULT_EFFECTIVE: "0x6a4667d8",
        mr.SEL_PAUSED: "0x0",
        mr.SEL_DECIMALS: "0x12",
        mr.SEL_TOTAL_SUPPLY: "0x2dd9aa98d2b816000",
    }


def mk_om(mult, eff, errors=None):
    return mr.OnChainMultiplier(
        token="T", multiplier_human=mult, effective_at_unix=eff,
        read_errors=errors or [])


def beacon_info(matches, impl=IMPL):
    return {"proxy_kind": "BEACON",
            "beacon": mr.KNOWN_BEACON if matches else OTHER,
            "implementation": impl, "matches_known_beacon": matches}


# --- read_multiplier ---------------------------------------------------------
def test_crwd_multiplier_and_effective():
    res = mr.read_multiplier("CRWD", rpc_fn=make_rpc(crwd_calls()), block=123)
    assert res.multiplier_human == Decimal("4")
    assert res.effective_at_unix == 1782999000
    assert res.paused is False
    assert res.decimals == 18
    assert res.total_supply_raw == 52861750000000000000
    assert res.read_errors == []
    assert res.block_number == 123


def test_effective_zero_is_none_not_error():
    calls = crwd_calls()
    calls[mr.SEL_MULT_EFFECTIVE] = "0x0"
    res = mr.read_multiplier("T", rpc_fn=make_rpc(calls))
    assert res.effective_at_unix is None
    assert res.read_errors == []


def test_multiplier_read_fail_is_none_not_zero():
    calls = crwd_calls()
    del calls[mr.SEL_MULTIPLIER]
    res = mr.read_multiplier("T", rpc_fn=make_rpc(calls))
    assert res.multiplier_human is None
    assert res.multiplier_human != 0
    assert len(res.read_errors) == 1


def test_paused_read_fail_is_none_not_false():
    calls = crwd_calls()
    del calls[mr.SEL_PAUSED]
    res = mr.read_multiplier("T", rpc_fn=make_rpc(calls))
    assert res.paused is None
    assert len(res.read_errors) == 1


# --- resolve_beacon ----------------------------------------------------------
def test_resolve_beacon_known():
    calls = {mr.EIP1967_BEACON_SLOT: mr.KNOWN_BEACON,
             mr.SEL_BEACON_IMPL: IMPL}
    info = mr.resolve_beacon("CRWD", rpc_fn=make_rpc(calls))
    assert info["proxy_kind"] == "BEACON"
    assert info["matches_known_beacon"] is True
    assert info["implementation"] == IMPL


def test_resolve_beacon_other_address():
    calls = {mr.EIP1967_BEACON_SLOT: OTHER, mr.SEL_BEACON_IMPL: IMPL}
    info = mr.resolve_beacon("T", rpc_fn=make_rpc(calls))
    assert info["proxy_kind"] == "BEACON"
    assert info["matches_known_beacon"] is False


def test_resolve_beacon_direct():
    calls = {mr.EIP1967_IMPL_SLOT: IMPL}
    info = mr.resolve_beacon("T", rpc_fn=make_rpc(calls))
    assert info["proxy_kind"] == "DIRECT"
    assert info["implementation"] == IMPL


# --- detect_multiplier_change ------------------------------------------------
def test_detect_change_effective_at_changed():
    changed, why = mr.detect_multiplier_change(
        mk_om(Decimal("4"), 100), mk_om(Decimal("4"), 200))
    assert changed is True
    assert why == "MULTIPLIER_EFFECTIVE_AT_CHANGED"


def test_detect_change_value_without_timestamp():
    changed, why = mr.detect_multiplier_change(
        mk_om(Decimal("4"), 100), mk_om(Decimal("5"), 100))
    assert changed is True
    assert why == "MULTIPLIER_VALUE_CHANGED_WITHOUT_TIMESTAMP"


def test_detect_change_stable():
    changed, why = mr.detect_multiplier_change(
        mk_om(Decimal("4"), 100), mk_om(Decimal("4"), 100))
    assert changed is False
    assert why == "STABLE"


def test_detect_change_unknown_cannot_compare():
    changed, why = mr.detect_multiplier_change(
        mk_om(None, 100), mk_om(Decimal("4"), 100))
    assert changed is True
    assert why == "UNKNOWN_CANNOT_COMPARE"


# --- cross_check_api ---------------------------------------------------------
def test_cross_check_agree():
    status, detail = mr.cross_check_api(mk_om(Decimal("4"), 100),
                                        "4.000000000000000000")
    assert status == "AGREE"
    assert detail == ""


def test_cross_check_disagreement():
    status, detail = mr.cross_check_api(mk_om(Decimal("4"), 100), "4.5")
    assert status == "SOURCE_DISAGREEMENT"
    assert "4" in detail and "4.5" in detail


def test_cross_check_unknown():
    status, detail = mr.cross_check_api(mk_om(None, 100), "4.0")
    assert status == "UNKNOWN"
    assert "onchain" in detail


# --- attestation_record ------------------------------------------------------
def test_attestation_mismatch_status():
    rec = mr.attestation_record(
        "CRWD", mk_om(Decimal("4"), 100), beacon_info(matches=False), now=NOW)
    assert rec["attestation_status"] == "DISCOVERED_NOT_ATTESTED"


def test_attestation_read_errors_status():
    rec = mr.attestation_record(
        "CRWD", mk_om(Decimal("4"), 100, errors=["SEL: revert"]),
        beacon_info(matches=True), now=NOW)
    assert rec["attestation_status"] == "DISCOVERED_NOT_ATTESTED"


def test_attestation_normal():
    rec = mr.attestation_record(
        "CRWD", mk_om(Decimal("4"), 100), beacon_info(matches=True), now=NOW)
    assert rec["attestation_status"] == "ATTESTED_SAME_BLOCK"
    assert rec["chain_id"] == mr.RH_CHAIN_ID
    assert rec["policy_version"] == "rh-05b-v1"
    assert rec["created_at"] == "2026-09-08T15:00:00Z"
    assert rec["expires_at"] == "2026-09-09T15:00:00Z"


# --- source invariants -------------------------------------------------------
def test_unverified_selectors_registered_once():
    assert SRC.count("0xdc767007") == 1
    assert SRC.count("0x9bea6429") == 1


def test_no_prd_assumed_method_names():
    for name in ("uiMultiplier", "oraclePaused", "newUIMultiplier",
                 "effectiveAt"):
        assert name not in SRC
