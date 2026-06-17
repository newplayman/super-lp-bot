"""Pure unit tests for helper decoders in lp_tier_c_sample_builder_v1_readonly.py.

No network calls are made; all helpers under test are pure functions.
"""

import sys
import os

# Ensure the repo root is on the path so 'scripts' is importable as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.lp_tier_c_sample_builder_v1_readonly import (  # noqa: E402
    WETH,
    USDC,
    decode_pool_created,
    fresh_token_for_major_pair,
    decode_decimals_from_word,
)


def _pad_word(value_hex: str) -> str:
    """Left-pad a hex string (without 0x) to 64 chars."""
    return value_hex.lstrip("0x").rjust(64, "0")


def test_decode_pool_created_basic():
    """Decode a synthetic PoolCreated log and assert all fields."""
    fake_token0 = "0x1111111111111111111111111111111111111111"
    fake_pool   = "0x2222222222222222222222222222222222222222"
    fee         = 10000   # 0x2710
    tick_sp     = 200     # 0xc8

    # Build the 128-char hex data section (2 words):
    #   word0 [0:64]  = tickSpacing (int24)
    #   word1 [64:128] = pool address right-aligned in 32 bytes
    tick_word = _pad_word(hex(tick_sp)[2:])
    pool_word = _pad_word(fake_pool[2:])   # 40 hex = last 40 chars, padded left with zeros

    log = {
        "topics": [
            "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118",
            "0x000000000000000000000000" + fake_token0[2:],
            "0x000000000000000000000000" + WETH[2:],
            "0x" + _pad_word(hex(fee)[2:]),
        ],
        "data": "0x" + tick_word + pool_word,
        "blockNumber": "0x3c2f",  # 15407 decimal
    }

    decoded = decode_pool_created(log)

    assert decoded["token0"].lower() == fake_token0.lower()
    assert decoded["token1"].lower() == WETH.lower()
    assert decoded["fee"] == fee
    assert decoded["tickSpacing"] == tick_sp
    assert decoded["pool"].lower() == fake_pool.lower()
    assert decoded["creation_block"] == 0x3C2F


def test_fresh_token_filter_weth_paired():
    """Returns (fresh, WETH) when token1 is WETH."""
    fake = "0x1111111111111111111111111111111111111111"
    result = fresh_token_for_major_pair(fake, WETH)
    assert result is not None
    fresh, major = result
    assert fresh.lower() == fake.lower()
    assert major.lower() == WETH.lower()


def test_fresh_token_filter_usdc_paired():
    """Returns (fresh, USDC) when token0 is USDC."""
    fake = "0x3333333333333333333333333333333333333333"
    result = fresh_token_for_major_pair(USDC, fake)
    assert result is not None
    fresh, major = result
    assert fresh.lower() == fake.lower()
    assert major.lower() == USDC.lower()


def test_fresh_token_filter_major_major_returns_none():
    """Both WETH and USDC -> None (major/major pair)."""
    assert fresh_token_for_major_pair(WETH, USDC) is None


def test_fresh_token_filter_non_major_pair_returns_none():
    """Two non-major tokens -> None."""
    a = "0x1111111111111111111111111111111111111111"
    b = "0x3333333333333333333333333333333333333333"
    assert fresh_token_for_major_pair(a, b) is None


def test_decode_decimals_18():
    """18 decimals = 0x12."""
    word = "0x" + _pad_word("12")
    assert decode_decimals_from_word(word) == 18


def test_decode_decimals_6():
    """6 decimals = 0x06 (USDC)."""
    word = "0x" + _pad_word("06")
    assert decode_decimals_from_word(word) == 6


def test_decode_decimals_zero():
    word = "0x" + _pad_word("00")
    assert decode_decimals_from_word(word) == 0


def test_decode_decimals_255():
    word = "0x" + _pad_word("ff")
    assert decode_decimals_from_word(word) == 255
