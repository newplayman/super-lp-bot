from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path("/Users/bendu/lp-bot/v3/scripts/lp_bsc_pancakeswap_v3_precise_quote_v2_readonly.py")
spec = importlib.util.spec_from_file_location("lp_bsc_pancakeswap_v3_precise_quote_v2_readonly", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_readonly_constants_and_stage() -> None:
    assert module.TESTED_NOTIONALS == [20, 100, 500, 1000, 2000]
    assert module.CHAIN_ID_EXPECTED == 56
    assert "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_FIX_REPEAT" in module.ALLOWED_NEXT
    assert "LP_BSC_PANCAKESWAP_V3_DATA_FIX_REPEAT" not in module.ALLOWED_NEXT


def test_no_wallet_or_tx_symbols_in_script() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    banned = [
        "eth_sendrawtransaction",
        "eth_sendtransaction",
        "sendtransaction(",
        "signtransaction(",
        "private_key",
        "mnemonic",
        "--canary-mint",
    ]
    for token in banned:
        assert token not in text


def test_abi_variants_and_helpers_exist() -> None:
    assert [v.variant_name for v in module.QUOTE_VARIANTS] == [
        "pancakeswap_v3_struct",
        "uniswap_v3_struct_alt",
        "legacy_quoter",
    ]
    for variant in module.QUOTE_VARIANTS:
        assert "quoteExactInputSingle" in variant.function_signature
        assert variant.param_types == ["address", "address", "uint24", "uint256", "uint160"] or variant.param_types == ["address", "address", "uint24", "uint160", "uint256"]
    for helper in [
        "build_decimal_audit",
        "build_compatibility_matrix",
        "quote_exact_input_single_with_variant",
        "classify_staticcall_error",
    ]:
        assert hasattr(module, helper)


def test_required_artifact_names_are_present() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    required = [
        "BSC_QUOTER_STATICCALL_FAILURE_DIAGNOSIS_CN.md",
        "BSC_QUOTER_ABI_COMPATIBILITY_MATRIX_CN.md",
        "BSC_AMOUNT_DECIMAL_AUDIT_CN.md",
        "BSC_PRECISE_QUOTE_V2_IMPLEMENTATION_CN.md",
        "BSC_PRECISE_QUOTE_V2_RESULTS_CN.md",
        "BSC_PRECISE_QUOTE_V1_V2_COMPARISON_CN.md",
        "BSC_PRECISE_QUOTE_V2_SAFETY_AUDIT_CN.md",
        "LP_BSC_PRECISE_QUOTE_FIX_NEXT_STAGE_DECISION_CN.md",
        "FINAL_VERDICT.json",
        "ARTIFACT_INDEX.md",
    ]
    for marker in required:
        assert marker in text


def test_final_verdict_is_fix_repeat_stage() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert '"stage": "LP_BSC_PANCAKESWAP_V3_PRECISE_QUOTE_FIX_REPEAT_V1"' in text
    assert '"tiny_canary_allowed": "no"' in text
    assert '"quoter_v2_staticcall_fixed": bool(agg["quoter_staticcall_success_count"] > 0)' in text
