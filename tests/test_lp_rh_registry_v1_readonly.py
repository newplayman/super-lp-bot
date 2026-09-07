from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import lp_rh_registry_v1_readonly as reg

FIXTURES = Path(__file__).parent / "fixtures" / "rh" / "synthetic"
WETH = "0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73"
USDG = "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168"
T, N, C = "TRADING_STATUS_TRADABLE", "TRADING_STATUS_NOT_TRADABLE", "TRADING_STATUS_CLOSING_ONLY"


def _sess(whole, frac):
    return {"whole": whole, "fractional": frac}


def _nested(market, extended, overnight):
    def norm(v):
        return v if isinstance(v, dict) else _sess(v, v)
    return {"market": norm(market), "extended": norm(extended), "overnight": norm(overnight)}


def _legacy(fractional, all_day, extended_hours):
    return {
        "fractionalTradability": fractional,
        "allDayTradability": all_day,
        "extendedHoursFractionalTradability": extended_hours,
    }


def _asset(tc, address=WETH, symbol="WETH", decimals=18):
    return {"tokenAddress": address, "symbol": symbol, "tokenDecimals": decimals,
            "tradingCapabilities": tc}


def _ident(address, symbol="WETH", uid=None, decimals=18, chain=4663):
    return reg.AssetIdentity(chain_id=chain, address=address.lower(), symbol_display=symbol,
                             uid=uid, decimals=decimals, metadata_version="v1", source="src")


# --- schema detection -------------------------------------------------------
def test_detect_schema_legacy_only():
    assert reg.detect_schema(_asset(_legacy(True, True, False))) == "LEGACY_FIELDS"


def test_detect_schema_nested_only():
    assert reg.detect_schema(_asset(_nested(T, N, C))) == "SESSION_NESTED"


def test_detect_schema_neither_is_unknown():
    assert reg.detect_schema(_asset({"unrelated": 1})) == "UNKNOWN"


def test_detect_schema_both_consistent_is_nested_with_flag():
    tc = dict(_legacy(True, True, True), **_nested(T, T, T))
    cap = reg.normalize_capability(_asset(tc))
    assert cap.schema_kind == "SESSION_NESTED"
    assert cap.raw_flags["both_present"] is True


def test_detect_schema_both_conflict():
    tc = dict(_legacy(True, True, True), **_nested(N, N, N))
    assert reg.detect_schema(_asset(tc)) == "SCHEMA_SEMANTIC_CONFLICT"
    cap = reg.normalize_capability(_asset(tc))
    assert (cap.market, cap.extended, cap.overnight) == ("UNKNOWN", "UNKNOWN", "UNKNOWN")


# --- T03 / legacy mapping ---------------------------------------------------
def test_legacy_mapping_true_false_null_empty():
    cap = reg.normalize_capability(_asset(_legacy(True, False, None)))
    assert cap.market == "TRADABLE"
    assert cap.extended == "UNKNOWN"
    assert cap.overnight == "NOT_TRADABLE"
    cap2 = reg.normalize_capability(_asset(_legacy(None, "", False)))
    assert cap2.market == "UNKNOWN"
    assert cap2.extended == "NOT_TRADABLE"
    assert cap2.overnight == "UNKNOWN"


# --- T04 / nested sessions --------------------------------------------------
def test_nested_market_extended_overnight_distinguished():
    cap = reg.normalize_capability(_asset(_nested(T, N, C)))
    assert cap.market == "TRADABLE"
    assert cap.extended == "NOT_TRADABLE"
    assert cap.overnight == "NOT_TRADABLE"


# --- T05 / unknown enum + conflict ------------------------------------------
def test_nested_unknown_enum_is_unknown_and_blocked():
    cap = reg.normalize_capability(_asset(_nested(
        _sess("TRADING_STATUS_MAYBE", T), _sess(None, T), _sess("", ""))))
    assert (cap.market, cap.extended, cap.overnight) == ("UNKNOWN", "UNKNOWN", "UNKNOWN")
    assert reg.is_new_position_allowed(cap, "market") is False
    assert reg.is_new_position_allowed(cap, "overnight") is False


# --- closing-only -----------------------------------------------------------
def test_closing_only_maps_not_tradable_and_preserves_raw():
    cap = reg.normalize_capability(_asset(_nested(C, T, T)))
    assert cap.market == "NOT_TRADABLE"
    raw = cap.raw_flags["raw_trading_capabilities"]["market"]["whole"]
    assert raw == "TRADING_STATUS_CLOSING_ONLY"


# --- whole/fractional conservative ------------------------------------------
def test_whole_fractional_disagreement_takes_conservative():
    cap = reg.normalize_capability(_asset(_nested(
        _sess(T, N), _sess(T, "TRADING_STATUS_MAYBE"), T)))
    assert cap.market == "NOT_TRADABLE"
    assert cap.extended == "UNKNOWN"
    assert cap.overnight == "TRADABLE"


# --- address / decimals -----------------------------------------------------
def test_address_invalid_raises():
    with pytest.raises(ValueError, match="ASSET_ADDRESS_INVALID"):
        reg.asset_from_json(4663, _asset(_legacy(True, True, True), address="0x1234"), "v1", "src")
    with pytest.raises(ValueError, match="ASSET_ADDRESS_INVALID"):
        reg.asset_from_json(4663, {"symbol": "WETH"}, "v1", "src")


def test_decimals_missing_is_none():
    ident = reg.asset_from_json(4663, {"tokenAddress": WETH, "symbol": "WETH"}, "v1", "src")
    assert ident.decimals is None
    assert ident.address == WETH.lower()


# --- verify_identity --------------------------------------------------------
def test_verify_identity_ok():
    registry = {WETH.lower(): _ident(WETH)}
    assert reg.verify_identity(_ident(WETH), registry) == "ASSET_IDENTITY_OK"


def test_verify_identity_symbol_mismatch():
    registry = {WETH.lower(): _ident(WETH, symbol="WETH")}
    assert reg.verify_identity(_ident(WETH, symbol="ETH"), registry) == "ASSET_IDENTITY_MISMATCH"


def test_verify_identity_same_symbol_different_address():
    registry = {WETH.lower(): _ident(WETH, symbol="WETH")}
    cand = _ident(USDG, symbol="WETH")
    assert reg.verify_identity(cand, registry) == "ASSET_IDENTITY_MISMATCH"


def test_verify_identity_uid_or_decimals_mismatch():
    registry = {WETH.lower(): _ident(WETH, uid="u1", decimals=18)}
    assert reg.verify_identity(_ident(WETH, uid="u2"), registry) == "ASSET_IDENTITY_MISMATCH"
    assert reg.verify_identity(_ident(WETH, decimals=6), registry) == "ASSET_IDENTITY_MISMATCH"


def test_verify_identity_testnet_asset_not_in_mainnet_registry():
    mainnet_registry = {WETH.lower(): _ident(WETH, chain=4663)}
    testnet_addr = "0x" + "ab" * 20
    cand = _ident(testnet_addr, symbol="WETH", chain=46630)
    assert reg.verify_identity(cand, mainnet_registry) == "ASSET_IDENTITY_MISMATCH"


# --- is_new_position_allowed ------------------------------------------------
def test_is_new_position_allowed_only_tradable():
    cap = reg.normalize_capability(_asset(_nested(T, N, "TRADING_STATUS_MAYBE")))
    assert reg.is_new_position_allowed(cap, "market") is True
    assert reg.is_new_position_allowed(cap, "extended") is False
    assert reg.is_new_position_allowed(cap, "overnight") is False
    assert reg.is_new_position_allowed(cap, "bogus") is False


# --- load_assets / main -----------------------------------------------------
def test_load_assets_reads_local_file():
    assets = reg.load_assets(str(FIXTURES / "assets_legacy.json"))
    assert len(assets) == 2
    assert assets[0]["symbol"] == "WETH"
    assert assets[1]["symbol"] == "USDG"


def test_main_writes_discovered_not_attested(tmp_path):
    out = tmp_path / "reg.json"
    rc = reg.main(["--assets-json", str(FIXTURES / "assets_session_nested.json"),
                   "--registry-out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["count"] == 1
    entry = data["attestations"][0]
    assert entry["attested"] is False
    assert entry["attestation_status"] == "DISCOVERED_NOT_ATTESTED"
    assert entry["schema_kind"] == "SESSION_NESTED"
    assert entry["capability"]["overnight"] == "NOT_TRADABLE"
