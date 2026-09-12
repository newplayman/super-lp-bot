"""Unit tests for calldata whitelist gate (W2 / Paper G).

The gate's new contract requires every critical field to be present on the
intent.  Tests mock the decoder so we can drive each whitelist rule in
isolation; the real decoder is exercised in test_lp_rh_calldata_decoder_* and
in the daemon's E2E tests.
"""
import hashlib
import time
from typing import Any, Mapping
from unittest.mock import patch

import pytest

from scripts.lp_rh_calldata_whitelist_gate_v1_readonly import (
    WHITELIST_RECIPIENTS,
    WHITELIST_SELECTORS,
    WHITELIST_TARGETS,
    load_whitelist,
    verify_intent_or_reject,
)

ROUTER_ADDRESS = "0xF87912FeFD79b1dEe6561C3d38e9EB4F3F77D7e2"
LEGAL_ROUTER = "0xf87912fefd79b1dee6561c3d38e9eb4f3f77d7e2"
ADD_LIQUIDITY_SELECTOR = "0xb95cac29"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# Build a legal-looking mint(NPM, ...) calldata dynamically.  Each word is
# 32 bytes; addresses keep their 12 leading zero bytes, integers are
# big-endian and signed integers are two's-complement encoded.
def _word32(v):
    if isinstance(v, str) and v.startswith("0x"):
        v = int(v, 16) if all(c in "0123456789abcdef" for c in v[2:].lower()) else None
    if isinstance(v, int):
        if v < 0:
            # signed 256-bit two's complement
            v &= (1 << 256) - 1
        return v.to_bytes(32, "big").hex()
    raise TypeError(v)


def _build_calldata(selector_hex, *words):
    return "0x" + selector_hex + "".join(_word32(w) for w in words)


FAKE_CALLDATA_HEX = _build_calldata(
    "88316456",  # mint
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # token0
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # token1
    3000,        # fee
    -887220,     # tickLower (signed)
    887220,      # tickUpper
    1_000_000,   # amount0Desired
    10**18,      # amount1Desired
    900_000,     # amount0Min > 0 (slippage protection passes)
    900_000 * 10**12,  # amount1Min > 0
    0,           # recipient (zero)
    0x6a000000,  # deadline (far future)
)
assert len(FAKE_CALLDATA_HEX) == 2 + 8 + 11 * 64, len(FAKE_CALLDATA_HEX)

FAKE_CALLDATA_HASH = "0x" + hashlib.sha256(bytes.fromhex(FAKE_CALLDATA_HEX[2:])).hexdigest()


def _decode_ok(calldata, *args, **kwargs):
    """Stand-in for decode_calldata: always succeed with the right selector."""
    if not isinstance(calldata, str) or not calldata.startswith("0x"):
        raise ValueError("calldata must be 0x-prefixed hex")
    sel = "0x" + calldata[2:10]
    return {
        "selector": sel,
        "known": True,
        "status": "OK",
        "args": [
            {"name": "amount0Min", "value": 900_000},
            {"name": "amount1Min", "value": 900_000 * 10**12},
        ],
        "raw_words": 11,
    }


def _verify_intent_ok(_decoded=None, *, intent=None):
    return True, []


def _patched(monkeypatch, decode_fn=None, verify_fn=None):
    """Patch the decoder symbols the gate imported into its own namespace.

    ``from scripts.lp_rh_calldata_decoder_v1_readonly import X`` binds X in the
    gate's module, so we have to patch the gate's namespace, not the decoder's.
    """
    import scripts.lp_rh_calldata_whitelist_gate_v1_readonly as gate_mod
    monkeypatch.setattr(gate_mod, "decode_calldata", decode_fn or _decode_ok,
                        raising=False)
    # verify_intent is imported lazily inside the try block, so patch the decoder
    # module's attribute (the local binding is re-resolved on each call).
    monkeypatch.setattr(
        "scripts.lp_rh_calldata_decoder_v1_readonly.verify_intent",
        verify_fn or _verify_intent_ok,
    )
    monkeypatch.setattr(
        "scripts.lp_rh_calldata_decoder_v1_readonly.decode_calldata",
        decode_fn or _decode_ok,
    )


def _legal_intent(**overrides):
    deadline = int(time.time()) + 3600
    intent: dict[str, Any] = {
        "calldata_bytes": FAKE_CALLDATA_HEX,
        "expected_intent": {"any": "value"},
        "target_address": LEGAL_ROUTER,
        "selector": "0x88316456",
        "recipient_address": ZERO_ADDRESS,
        "chain_id": 8453,
        "intent_chain_id": 8453,
        "deadline": deadline,
        "value_wei": "0",
        "calldata_hash": FAKE_CALLDATA_HASH,
        "expected_min_out": 1000,
    }
    intent.update(overrides)
    return intent


# ---------------------------------------------------------------------------
# Backwards-compat smoke tests for the old API surface.
# ---------------------------------------------------------------------------

def test_whitelist_constant_non_empty():
    """load_whitelist()['targets'] length must be greater than 3."""
    wl = load_whitelist()
    assert "targets" in wl
    assert len(wl["targets"]) > 3


def test_legal_target_passes(monkeypatch):
    """Legal router + legal selector + zero recipient -> pass."""
    _patched(monkeypatch)
    intent = _legal_intent(
        target_address=LEGAL_ROUTER,
        selector="0x88316456",
        recipient_address=ZERO_ADDRESS,
    )
    ok, reason = verify_intent_or_reject(intent)
    assert ok is True
    assert reason is None


def test_evil_target_rejected(monkeypatch):
    _patched(monkeypatch)
    intent = _legal_intent(target_address="0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
    ok, reason = verify_intent_or_reject(intent)
    assert ok is False
    assert reason is not None
    assert reason.startswith("whitelist_reject:")


def test_evil_selector_rejected(monkeypatch):
    _patched(monkeypatch)
    intent = _legal_intent(selector="0xdeadbeef")
    ok, reason = verify_intent_or_reject(intent)
    assert ok is False
    assert reason is not None
    assert reason.startswith("whitelist_reject:")


def test_case_insensitive_target(monkeypatch):
    _patched(monkeypatch)
    intent = _legal_intent(target_address=LEGAL_ROUTER.upper())
    ok, reason = verify_intent_or_reject(intent)
    assert ok is True
    assert reason is None


# ---------------------------------------------------------------------------
# New reverse tests for PAPER_ACCEPTANCE_REPAIR_V1 §2.
# ---------------------------------------------------------------------------

def test_required_pass_passes(monkeypatch):
    """All required fields present + decode OK + verify_intent OK -> (True, None)."""
    _patched(monkeypatch)
    ok, reason = verify_intent_or_reject(_legal_intent())
    assert ok is True
    assert reason is None


def test_missing_calldata_rejected(monkeypatch):
    """Missing calldata_bytes -> field_missing:calldata_bytes."""
    _patched(monkeypatch)
    intent = _legal_intent()
    intent.pop("calldata_bytes", None)
    ok, reason = verify_intent_or_reject(intent)
    assert ok is False
    assert reason == "whitelist_reject:field_missing:calldata_bytes"


def test_missing_expected_intent_rejected(monkeypatch):
    """Missing expected_intent -> field_missing:expected_intent."""
    _patched(monkeypatch)
    intent = _legal_intent()
    intent.pop("expected_intent", None)
    ok, reason = verify_intent_or_reject(intent)
    assert ok is False
    assert reason == "whitelist_reject:field_missing:expected_intent"


def test_evil_recipient_rejected(monkeypatch):
    """recipient not in WHITELIST_RECIPIENTS -> recipient_not_whitelisted."""
    _patched(monkeypatch)
    intent = _legal_intent(recipient_address="0xbadbadbadbadbadbadbadbadbadbadbadbad")
    ok, reason = verify_intent_or_reject(intent)
    assert ok is False
    assert reason is not None
    assert "recipient_not_whitelisted" in reason


def test_expired_deadline_rejected(monkeypatch):
    """deadline in the past -> deadline_expired."""
    _patched(monkeypatch)
    intent = _legal_intent(deadline=int(time.time()) - 100)
    ok, reason = verify_intent_or_reject(intent)
    assert ok is False
    assert reason == "whitelist_reject:deadline_expired"


def test_missing_calldata_hash_rejected(monkeypatch):
    """Missing calldata_hash -> field_missing:calldata_hash."""
    _patched(monkeypatch)
    intent = _legal_intent()
    intent.pop("calldata_hash", None)
    ok, reason = verify_intent_or_reject(intent)
    assert ok is False
    assert reason == "whitelist_reject:field_missing:calldata_hash"


def test_multicall_inner_evil_target_rejected(monkeypatch):
    """multicall(0xac9650d8) with inner evil target -> multicall_inner_reject."""
    multicall_calldata = (
        "0xac9650d8"
        + "00" * 31 + "20"  # offset to array
        + "00" * 31 + "01"  # count=1
        + "00" * 31 + "20"  # offset to first item
        + "00" * 31 + "40"  # length=64
        + "b95cac29" + "00" * 28  # inner selector
        + "00" * 32
    )
    multicall_hash = "0x" + hashlib.sha256(bytes.fromhex(multicall_calldata[2:])).hexdigest()

    def decode_multicall(calldata):
        sel = "0x" + calldata[2:10]
        # Inner sub-call: a different selector and an evil target.
        inner = {
            "selector": "0xb95cac29",
            "known": True,
            "status": "OK",
            "args": [
                {"name": "target", "value": "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"},
            ],
            "raw_words": 1,
        }
        return {
            "selector": sel,
            "known": True,
            "status": "OK",
            "args": [{"name": "calls", "value": [inner]}],
            "raw_words": 4,
        }

    _patched(monkeypatch, decode_fn=decode_multicall)
    intent = _legal_intent(
        selector="0xac9650d8",
        calldata_bytes=multicall_calldata,
        calldata_hash=multicall_hash,
    )
    ok, reason = verify_intent_or_reject(intent)
    assert ok is False
    assert "multicall_inner_reject" in (reason or "")


def test_decoder_exception_returns_decoder_exception(monkeypatch):
    """verify_intent raising TypeError -> decoder_exception:TypeError."""
    def boom(*_args, **_kwargs):
        raise TypeError("intentional decoder failure")

    _patched(monkeypatch, verify_fn=boom)
    ok, reason = verify_intent_or_reject(_legal_intent())
    assert ok is False
    assert reason == "whitelist_reject:decoder_exception:TypeError"


def test_calldata_decode_failure_rejected(monkeypatch):
    """decode_calldata returning non-OK status -> calldata_decode_failed."""
    def decode_bad(calldata):
        return {"selector": "0x" + calldata[2:10], "known": True, "status": "MALFORMED_CALLDATA",
                "args": [], "raw_words": 0}

    _patched(monkeypatch, decode_fn=decode_bad)
    ok, reason = verify_intent_or_reject(_legal_intent())
    assert ok is False
    assert "calldata_decode_failed" in (reason or "")


def test_calldata_hash_mismatch_rejected(monkeypatch):
    """calldata_hash != sha256(calldata) -> calldata_hash_mismatch."""
    _patched(monkeypatch)
    intent = _legal_intent(
        calldata_hash="0x" + "ff" * 32,
    )
    ok, reason = verify_intent_or_reject(intent)
    assert ok is False
    assert reason == "whitelist_reject:calldata_hash_mismatch"


def test_chain_mismatch_rejected(monkeypatch):
    """chain_id != intent_chain_id -> chain_mismatch."""
    _patched(monkeypatch)
    intent = _legal_intent(chain_id=8453, intent_chain_id=1)
    ok, reason = verify_intent_or_reject(intent)
    assert ok is False
    assert reason == "whitelist_reject:chain_mismatch"


def test_value_mismatch_rejected(monkeypatch):
    """value_wei != expected_value_wei -> value_mismatch."""
    _patched(monkeypatch)
    intent = _legal_intent(value_wei="100", expected_value_wei="200")
    ok, reason = verify_intent_or_reject(intent)
    assert ok is False
    assert reason == "whitelist_reject:value_mismatch"


def test_no_simulated_ok_in_gate():
    """The gate never returns SIMULATED_OK -- the caller decides the post-validation state."""
    # This is a structural sanity check: load_whitelist never exposes a state label.
    wl = load_whitelist()
    for key in wl:
        assert "SIMULATED_OK" not in wl[key]
        assert "STATE" not in wl[key]


def test_invalid_intent_type_rejected():
    """Non-Mapping intent -> invalid_intent_type."""
    ok, reason = verify_intent_or_reject("not-a-dict")  # type: ignore[arg-type]
    assert ok is False
    assert reason == "whitelist_reject:invalid_intent_type"
