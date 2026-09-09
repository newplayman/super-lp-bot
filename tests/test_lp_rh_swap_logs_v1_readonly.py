import sys
sys.path.insert(0, '/opt/lpbot/lp-bot-v3-origin-check')

from decimal import Decimal

import pytest

from scripts.lp_rh_swap_logs_v1_readonly import (
    SWAP_TOPIC0,
    decode_int256,
    decode_swap_log,
    split_range,
    fetch_swaps,
    to_organic_events,
)

MINT_TOPIC = "0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde"

SENDER = "aa" * 20
RECIPIENT = "bb" * 20


def _enc_int256(v: int) -> str:
    if v < 0:
        v += 2 ** 256
    return format(v, "064x")


def _enc_uint(v: int) -> str:
    return format(v, "064x")


def make_swap_log(
    amount0=1000,
    amount1=-2000,
    sqrt_price_x96=1,
    liquidity=2,
    tick=-5,
    sender=SENDER,
    recipient=RECIPIENT,
    block=30,
    tx_hash="0xabc",
    log_index=0,
    topic0=SWAP_TOPIC0,
):
    data = (
        "0x"
        + _enc_int256(amount0)
        + _enc_int256(amount1)
        + _enc_uint(sqrt_price_x96)
        + _enc_uint(liquidity)
        + _enc_int256(tick)
    )
    return {
        "address": "0xpool",
        "topics": [topic0, "0x" + "00" * 12 + sender, "0x" + "00" * 12 + recipient],
        "data": data,
        "blockNumber": hex(block),
        "transactionHash": tx_hash,
        "logIndex": hex(log_index),
    }


def _span(params):
    return int(params["toBlock"], 16) - int(params["fromBlock"], 16)


def test_decode_int256_positive_one():
    assert decode_int256("0x" + "00" * 31 + "01") == 1


def test_decode_int256_minus_one():
    assert decode_int256("0x" + "ff" * 32) == -1


def test_decode_int256_min_negative():
    assert decode_int256("0x" + "80" + "00" * 31) == -(2 ** 255)


def test_decode_int256_zero():
    assert decode_int256("0x" + "00" * 32) == 0


def test_decode_int256_max_positive():
    assert decode_int256("0x" + "7f" + "ff" * 31) == 2 ** 255 - 1


def test_decode_swap_log_real_shape_signs():
    ev = decode_swap_log(make_swap_log(amount0=1000, amount1=-2000))
    assert ev is not None
    assert ev["amount0"] == 1000
    assert ev["amount1"] == -2000
    assert ev["amount0"] > 0
    assert ev["amount1"] < 0


def test_decode_swap_log_mint_topic_returns_none():
    assert decode_swap_log(make_swap_log(topic0=MINT_TOPIC)) is None


def test_decode_swap_log_too_few_topics():
    log = make_swap_log()
    log["topics"] = [SWAP_TOPIC0]
    assert decode_swap_log(log) is None


def test_decode_swap_log_too_little_data():
    log = make_swap_log()
    log["data"] = "0x" + "00" * 64 * 2
    assert decode_swap_log(log) is None


def test_decode_swap_log_address_lowercase():
    upper = "AA" * 20
    ev = decode_swap_log(make_swap_log(sender=upper))
    assert ev is not None
    assert ev["sender"] == "0x" + upper.lower()
    assert ev["sender"] == ev["sender"].lower()


def test_decode_swap_log_block_hex():
    log = make_swap_log(block=30)
    assert log["blockNumber"] == "0x1e"
    assert decode_swap_log(log)["block"] == 30


def test_decode_swap_log_negative_tick():
    ev = decode_swap_log(make_swap_log(tick=-5))
    assert ev["tick"] == -5
    assert ev["tick"] < 0


def test_decode_swap_log_all_fields():
    log = make_swap_log(
        amount0=7, amount1=-9, sqrt_price_x96=123, liquidity=456,
        tick=11, block=30, tx_hash="0xdead", log_index=3,
    )
    assert decode_swap_log(log) == {
        "block": 30,
        "tx_hash": "0xdead",
        "log_index": 3,
        "sender": "0x" + SENDER,
        "recipient": "0x" + RECIPIENT,
        "amount0": 7,
        "amount1": -9,
        "sqrt_price_x96": 123,
        "liquidity": 456,
        "tick": 11,
    }


def test_split_range_basic():
    assert split_range(100, 105, 2) == [(100, 101), (102, 103), (104, 105)]


def test_split_range_single():
    assert split_range(100, 100, 2) == [(100, 100)]


def test_split_range_reversed():
    assert split_range(105, 100, 2) == []


def test_split_range_zero_span_raises():
    with pytest.raises(ValueError):
        split_range(100, 105, 0)


def test_fetch_swaps_auto_split_complete():
    def call_fn(params):
        if _span(params) > 1000:
            raise RuntimeError("query returned more than 10000 results")
        fb = int(params["fromBlock"], 16)
        tb = int(params["toBlock"], 16)
        return [make_swap_log(block=b, tx_hash="0xtx" + format(b, "x")) for b in range(fb, tb + 1)]

    result = fetch_swaps("0xpool", 0, 3000, call_fn)
    assert result["status"] == "COMPLETE"
    assert len(result["events"]) == 3001
    assert result["failed_ranges"] == []
    assert result["coverage_frac"] == Decimal(1)


def test_fetch_swaps_partial_failure():
    def call_fn(params):
        fb = int(params["fromBlock"], 16)
        tb = int(params["toBlock"], 16)
        if fb <= 199 and tb >= 100:
            raise RuntimeError("query returned more than 10000 results")
        return [make_swap_log(block=b, tx_hash="0xtx" + format(b, "x")) for b in range(fb, tb + 1)]

    result = fetch_swaps("0xpool", 0, 300, call_fn)
    assert result["status"] == "PARTIAL"
    assert result["failed_ranges"]
    assert result["events"]
    assert result["coverage_frac"] is not None
    assert result["coverage_frac"] < 1


def test_fetch_swaps_all_failed_inputs_unavailable():
    def call_fn(params):
        raise RuntimeError("query returned more than 10000 results")

    result = fetch_swaps("0xpool", 0, 10, call_fn)
    assert result["status"] == "INPUTS_UNAVAILABLE"
    assert result["coverage_frac"] is None
    assert result["events"] == []
    assert result["failed_ranges"]


def test_fetch_swaps_dedup():
    def call_fn(params):
        log = make_swap_log(block=5, tx_hash="0xdup", log_index=0)
        return [log, log]

    result = fetch_swaps("0xpool", 5, 5, call_fn)
    assert len(result["events"]) == 1
    assert result["status"] == "COMPLETE"


def test_to_organic_events_decimal_fields():
    decoded = [decode_swap_log(make_swap_log(amount0=1000, amount1=-2000))]
    out = to_organic_events(decoded)
    assert isinstance(out[0]["amount0"], Decimal)
    assert isinstance(out[0]["amount1"], Decimal)
    assert out[0]["amount0"] == Decimal(1000)
    assert out[0]["amount1"] == Decimal(-2000)


def test_to_organic_events_field_names_match_rh05f():
    out = to_organic_events([decode_swap_log(make_swap_log())])
    required = {"block", "tx_hash", "log_index", "sender", "recipient", "amount0", "amount1"}
    assert required.issubset(out[0].keys())
    assert isinstance(out[0]["block"], int)
    assert isinstance(out[0]["sender"], str)


def test_call_timeout_is_explicit_and_defaults_high_enough():
    """The hardcoded 30s timeout is why eight organic windows were lost.

    The identical request that returned nothing at 30s returned 22,281 events at
    90s, so the value decides whether data arrives at all and must be visible.
    """
    import scripts.lp_rh_swap_logs_v1_readonly as mod
    assert mod.DEFAULT_CALL_TIMEOUT_SECS >= 60
    import inspect
    sig = inspect.signature(mod.make_urllib_call_fn)
    assert "timeout_secs" in sig.parameters
    assert sig.parameters["timeout_secs"].default == mod.DEFAULT_CALL_TIMEOUT_SECS


def test_overload_errors_trigger_splitting_not_a_hard_failure():
    """-32005 "network is busy" never matched the range-error keys.

    It is an overload signal rather than a range complaint, so fetch_swaps treated
    it as fatal and skipped the window.  On this chain it fires reliably at 8,800
    blocks and never at 2,000, so asking for less is the correct response.
    """
    import scripts.lp_rh_swap_logs_v1_readonly as mod
    assert mod._is_range_error(RuntimeError("the network is busy, please try again"))
    assert mod._is_range_error(RuntimeError("{'code': -32005, 'message': 'busy'}"))
    assert mod._is_range_error(RuntimeError("logs matched by query exceeds limit of 10000"))
    assert not mod._is_range_error(ValueError("bad params"))
