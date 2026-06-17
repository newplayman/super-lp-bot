from __future__ import annotations

import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_pool_resolve_and_rank_v1_readonly import (
    SELECTOR_GET_POOL_AERODROME,
    SELECTOR_GET_POOL_UNISWAP,
    build_aerodrome_get_pool_calldata,
    build_uniswap_get_pool_calldata,
    composite_score,
    encode_address_word,
    encode_int_word,
    reward_adjusted_cover,
)


def test_abi_encode_helpers_address_and_int24() -> None:
    address = "0x1234567890abcdef1234567890ABCDEF12345678"
    encoded_address = encode_address_word(address)
    assert encoded_address == "0x" + "0" * 24 + "1234567890abcdef1234567890abcdef12345678"

    encoded_positive = encode_int_word(60, bits=24)
    assert encoded_positive.startswith("0x")
    assert len(encoded_positive) == 66
    assert encoded_positive.endswith("3c".rjust(64, "0"))

    encoded_negative = encode_int_word(-1, bits=24)
    assert encoded_negative == "0x" + "f" * 58 + "ffffff"


def test_get_pool_calldata_builders_prefix_and_length() -> None:
    token_a = "0x00000000000000000000000000000000000000aa"
    token_b = "0x00000000000000000000000000000000000000bb"

    uni = build_uniswap_get_pool_calldata(token_a, token_b, 500)
    aero = build_aerodrome_get_pool_calldata(token_a, token_b, 60)

    assert uni.startswith(SELECTOR_GET_POOL_UNISWAP)
    assert aero.startswith(SELECTOR_GET_POOL_AERODROME)
    assert len(uni) == 2 + 8 + 64 * 3
    assert len(aero) == 2 + 8 + 64 * 3
    assert uni[10:] != ""
    assert aero[10:] != ""


def test_reward_adjusted_cover_math_and_zero_il() -> None:
    cover = reward_adjusted_cover(
        fees_quote=0.01,
        il_quote=-0.02,
        apy_reward=12.0,
        window_days=2.0,
    )
    assert cover["fee_apr"] > 0
    assert cover["reward_apr"] == 12.0
    assert cover["total_income_apr"] > cover["reward_apr"]
    assert cover["il_apr"] > 0
    assert cover["yield_cover"] > 0

    zero_il = reward_adjusted_cover(
        fees_quote=0.01,
        il_quote=0.0,
        apy_reward=0.0,
        window_days=1.0,
    )
    assert math.isinf(zero_il["yield_cover"])


def test_composite_score_penalties_and_clamp() -> None:
    clean = {
        "status": "OK",
        "resolve_status": "OK",
        "tier": "A",
        "suspect": [],
        "wash_flag": False,
        "total_income_apr": 90.0,
        "il_apr": 10.0,
        "yield_cover": 9.0,
    }
    suspect = dict(clean, suspect=["odd-metadata"])
    wash = dict(clean, wash_flag=True)
    weak_cover = dict(clean, total_income_apr=40.0, il_apr=80.0, yield_cover=0.5)
    extreme = dict(clean, total_income_apr=150000.0, il_apr=10.0, yield_cover=500.0)

    clean_score = composite_score(clean)
    suspect_score = composite_score(suspect)
    wash_score = composite_score(wash)
    weak_cover_score = composite_score(weak_cover)
    extreme_score = composite_score(extreme)

    assert clean_score > suspect_score
    assert wash_score == 0.0
    assert clean_score > weak_cover_score
    assert extreme_score <= clean_score
