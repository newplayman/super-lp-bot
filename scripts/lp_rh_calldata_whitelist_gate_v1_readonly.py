"""Calldata whitelist gate for transaction intents (W2).

Gating mechanism ensuring every rh_tx_intents row passes whitelist verification
before any signer/broadcaster invocation in the daemon.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import sys
from typing import Any, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Constants derived from internal/adapters/pool/aerodrome/adapter.go
# Line 21: RouterV2Address = "0xF87912FeFD79b1dEe6561C3d38e9EB4F3F77D7e2"
# Line 22: FactoryV2Address = "0x420DD7b1D89364d57d6EEA33300755E7d0fF6794"
# NPM addresses derived from execution/base_m1_executor_v1.py:37-45
WHITELIST_TARGETS: frozenset[str] = frozenset({
    # Aerodrome V2 Router (internal/adapters/pool/aerodrome/adapter.go:21)
    "0xf87912fefd79b1dee6561c3d38e9eb4f3f77d7e2",
    # Aerodrome V2 Factory (internal/adapters/pool/aerodrome/adapter.go:22)
    "0x420dd7b1d89364d57d6eea33300755e7d0ff6794",
    # Aerodrome Slipstream NPM initial (execution/base_m1_executor_v1.py:41)
    "0x827922686190790b37229fd06084350e74485b72",
    # Aerodrome Slipstream NPM gauge-caps (execution/base_m1_executor_v1.py:42)
    "0xa990c6a764b73bf43cee5bb40339c3322fb9d55f",
    # Aerodrome Slipstream NPM Gauges-v3 (execution/base_m1_executor_v1.py:43)
    "0xe1f8cd9ac4e4a65f54f38a5cdafca44f6dd68b53",
    # Uniswap V3 NPM (execution/base_m1_executor_v1.py:37)
    "0x03a520b32c04bf3beef7beb72e919cf822ed34f1",
})

# Function selectors derived from:
# - internal/adapters/pool/aerodrome/adapter.go:27-31
# - scripts/lp_rh_calldata_decoder_v1_readonly.py:9-27
WHITELIST_SELECTORS: frozenset[str] = frozenset({
    # addLiquidity (aerodrome/adapter.go:27, buildAddLiquidityCalldata:195)
    "0xb95cac29",
    # removeLiquidity (aerodrome/adapter.go:28, buildRemoveLiquidityCalldata:212)
    "0x0cfe81c8",
    # decreaseLiquidity / removeLiquidity on Uniswap V3 style (spec W2)
    "0x02751cec",
    # claimFees (aerodrome/adapter.go:29, buildClaimFeesCalldata:226)
    "0x9ff3e9fc",
    # swap (aerodrome/adapter.go:30, buildSwapCalldata:234)
    "0x38b2a21d",
    # quoteAddLiquidity (aerodrome/adapter.go:31)
    "0xf28f8205",
    # collect (scripts/lp_rh_calldata_decoder_v1_readonly.py:24)
    "0xfc6f7865",
    # burn (scripts/lp_rh_calldata_decoder_v1_readonly.py:25)
    "0x42966c68",
    # mint (scripts/lp_rh_calldata_decoder_v1_readonly.py:15)
    "0x88316456",
    # increaseLiquidity (scripts/lp_rh_calldata_decoder_v1_readonly.py:18)
    "0x219f5d17",
    # decreaseLiquidity (scripts/lp_rh_calldata_decoder_v1_readonly.py:21)
    "0x0c49ccbe",
    # exactInputSingle swap (scripts/lp_rh_calldata_decoder_v1_readonly.py:12)
    "0x04e45aaf",
    # multicall (scripts/lp_rh_calldata_decoder_v1_readonly.py:26)
    "0xac9650d8",
})

WHITELIST_RECIPIENTS: frozenset[str] = frozenset({
    # Zero address (burn / null address)
    "0x0000000000000000000000000000000000000000",
    # Placeholder for project-controlled wallet; MUST be replaced before any LIVE mode
    "0x000000000000000000000000000000000000dead",
})


def load_whitelist() -> dict[str, set[str]]:
    """Return dictionary of whitelist constants for inspection."""
    return {
        "targets": set(WHITELIST_TARGETS),
        "selectors": set(WHITELIST_SELECTORS),
        "recipients": set(WHITELIST_RECIPIENTS),
    }


def verify_intent_or_reject(intent: dict) -> Tuple[bool, Optional[str]]:
    """Verify intent against whitelist rules.

    Calls verify_intent if available. If missing or raises, falls back to
    in-process whitelist check (target + selector only).
    Returns (True, None) on pass, (False, 'whitelist_reject:<reason>') on fail.
    """
    if not isinstance(intent, Mapping):
        return False, "whitelist_reject:invalid_intent_type"

    # Lowercase all hex addresses/values before comparison
    norm_intent: dict[str, Any] = {}
    for k, v in intent.items():
        if isinstance(v, str) and v.lower().startswith("0x"):
            norm_intent[k] = v.lower()
        else:
            norm_intent[k] = v

    # Call verify_intent if available
    try:
        from scripts.lp_rh_calldata_decoder_v1_readonly import verify_intent
        try:
            res = verify_intent(norm_intent)
            if isinstance(res, tuple) and len(res) == 2:
                ok, reasons = res
                if not ok:
                    reason_msg = reasons[0] if reasons else "intent_verification_failed"
                    return False, f"whitelist_reject:{reason_msg}"
                return True, None
        except TypeError:
            pass
    except ImportError:
        pass
    except Exception:
        pass

    # Fall back to in-process whitelist check (target + selector only)
    raw_target = norm_intent.get("target_address")
    if raw_target is None:
        raw_target = norm_intent.get("target")
    if raw_target is None or not str(raw_target).strip():
        return False, "whitelist_reject:target_missing"
    target = str(raw_target).lower().strip()
    if target not in WHITELIST_TARGETS:
        return False, f"whitelist_reject:target_not_whitelisted:{target}"

    raw_selector = norm_intent.get("selector")
    if raw_selector is None or not str(raw_selector).strip():
        return False, "whitelist_reject:selector_missing"
    selector = str(raw_selector).lower().strip()
    if selector not in WHITELIST_SELECTORS:
        return False, f"whitelist_reject:selector_not_whitelisted:{selector}"

    return True, None
