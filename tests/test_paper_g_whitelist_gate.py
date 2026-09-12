"""Unit tests for calldata whitelist gate (W2 / Paper G)."""
import pytest
from scripts.lp_rh_calldata_whitelist_gate_v1_readonly import (
    load_whitelist,
    verify_intent_or_reject,
)

ROUTER_ADDRESS = "0xF87912FeFD79b1dEe6561C3d38e9EB4F3F77D7e2"
ADD_LIQUIDITY_SELECTOR = "0xb95cac29"


def test_legal_target_passes():
    """Legal router address (lowercase) and addLiquidity selector pass."""
    intent = {
        "target_address": ROUTER_ADDRESS.lower(),
        "selector": ADD_LIQUIDITY_SELECTOR,
        "recipient_address": "0x0000000000000000000000000000000000000000",
    }
    ok, reason = verify_intent_or_reject(intent)
    assert ok is True
    assert reason is None


def test_evil_target_rejected():
    """Evil target address is rejected with reason starting with whitelist_reject: or whitelist_gate_exception:."""
    intent = {
        "target_address": "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "selector": ADD_LIQUIDITY_SELECTOR,
        "recipient_address": "0x0000000000000000000000000000000000000000",
    }
    ok, reason = verify_intent_or_reject(intent)
    assert ok is False
    assert reason is not None
    assert reason.startswith("whitelist_reject:") or reason.startswith("whitelist_gate_exception:")


def test_evil_selector_rejected():
    """Legal target with evil selector is rejected."""
    intent = {
        "target_address": ROUTER_ADDRESS.lower(),
        "selector": "0xdeadbeef",
        "recipient_address": "0x0000000000000000000000000000000000000000",
    }
    ok, reason = verify_intent_or_reject(intent)
    assert ok is False
    assert reason is not None
    assert reason.startswith("whitelist_reject:") or reason.startswith("whitelist_gate_exception:")


def test_case_insensitive_target():
    """Uppercase target still passes after lowercasing."""
    intent = {
        "target_address": ROUTER_ADDRESS.upper(),
        "selector": ADD_LIQUIDITY_SELECTOR,
        "recipient_address": "0x0000000000000000000000000000000000000000",
    }
    ok, reason = verify_intent_or_reject(intent)
    assert ok is True
    assert reason is None


def test_whitelist_constant_non_empty():
    """load_whitelist()['targets'] length must be greater than 3."""
    wl = load_whitelist()
    assert "targets" in wl
    assert len(wl["targets"]) > 3
