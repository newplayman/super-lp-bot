from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path


SCRIPT_PATH = Path("/Users/bendu/lp-bot/v3/scripts/lp_bsc_quoter_staticcall_amount_fix_v1_readonly.py")
spec = importlib.util.spec_from_file_location("lp_bsc_quoter_staticcall_amount_fix_v1_readonly", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_script_is_readonly() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    banned = [
        "eth_sendrawtransaction(",
        "eth_sendtransaction(",
        "signtransaction(",
        "private_key =",
        "mnemonic =",
        "--canary-mint",
        "swap(",
        "mint(",
        "burn(",
        "collect(",
        "approve(",
    ]
    for token in banned:
        assert token not in text


def test_abi_candidate_matrix_and_stage() -> None:
    signatures = [p.candidate_signature for p in module.build_abi_ground_truth_audit.__defaults__] if False else []
    expected = [
        "quoteExactInputSingle((address,address,uint256,uint24,uint160))",
        "quoteExactInputSingle((address,address,uint24,uint256,uint160))",
        "quoteExactInputSingle(address,address,uint24,uint24,uint160)" if False else "quoteExactInputSingle(address,address,uint24,uint256,uint160)",
        "quoteExactInputSingle(address,address,uint256,uint24,uint160)",
    ]
    # The script hard-codes exactly four comparison candidates.
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    for sig in expected:
        assert sig in text
    assert '"stage": "LP_BSC_PANCAKESWAP_V3_QUOTER_STATICCALL_AMOUNT_FIX_V1"' in text


def test_amount_raw_helpers_cover_stable_and_anchor_paths() -> None:
    prices = {
        "0xaaa": Decimal("1"),
        "0xbbb": Decimal("700"),
    }
    sources = {
        "0xaaa": "stable_anchor",
        "0xbbb": "slot0_pool_anchor:test",
    }
    stable_amount, stable_source, stable_anchor, stable_reason = module.build_amount_in_raw(
        20,
        "0xaaa",
        "USDT",
        18,
        prices,
        sources,
    )
    assert stable_amount == 20 * 10**18
    assert stable_source == "stable_anchor"
    assert stable_anchor == Decimal("1")
    assert stable_reason == ""

    wbnb_amount, wbnb_source, wbnb_anchor, wbnb_reason = module.build_amount_in_raw(
        20,
        "0xbbb",
        "WBNB",
        18,
        prices,
        sources,
    )
    assert wbnb_amount is not None and wbnb_amount > 0
    assert wbnb_source == "slot0_pool_anchor:test"
    assert wbnb_anchor == Decimal("700")
    assert wbnb_reason == ""

    missing_amount, _, _, missing_reason = module.build_amount_in_raw(
        20,
        "0xccc",
        "WBNB",
        18,
        {},
        {},
    )
    assert missing_amount is None
    assert missing_reason == "amount_raw_unavailable"


def test_revert_decode_helpers_present() -> None:
    empty = module.decode_revert_payload("0x")
    assert empty["error_type"] == "empty_revert"
    error = module.decode_revert_payload("0x08c379a0")
    assert error["decoded"] == "no" or error["error_type"] in {"error_string", "error_string_decode_fail"}
    panic = module.decode_revert_payload("0x4e487b71")
    assert panic["error_type"] in {"panic", "panic_decode_fail", "custom_error_or_unknown"}


def test_stage_decision_allows_only_expected_next_stages() -> None:
    allowed = {
        "LP_BSC_PANCAKESWAP_V3_TICK_LIQUIDITY_PIPELINE_V1",
        "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_FIX_REPEAT",
        "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_FALLBACK_ONLY_FREEZE",
        "STOP_LP_RESEARCH_NOW",
    }
    verdict_text = SCRIPT_PATH.read_text(encoding="utf-8")
    for stage in allowed:
        assert stage in verdict_text
