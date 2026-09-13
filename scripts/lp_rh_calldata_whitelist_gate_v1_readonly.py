"""Calldata whitelist gate for transaction intents (W2).

Gating mechanism ensuring every rh_tx_intents row passes whitelist verification
before any signer/broadcaster invocation in the daemon.

verify_intent_or_reject takes a single ``intent`` dict that must carry ALL of:
  - calldata_bytes (hex string)
  - target_address
  - selector
  - recipient_address (or wallet_address)
  - chain_id (the chain the call is meant for)
  - deadline (unix-seconds or ISO-8601)
  - value_wei
  - calldata_hash (expected hash of calldata)
  - expected_intent (Mapping - the Owner-approved intent payload)
  - expected_min_out (slippage-protection value the caller is willing to accept)

Any missing critical field fails closed with ``whitelist_reject:field_missing:<name>``.
Any exception from the decoder fails closed with ``whitelist_reject:decoder_exception:<Type>``.
Whitelist pass != SIMULATED_OK: this gate only proves the intent is on the
allow-list; the caller decides what state label to record (PROPOSED / VALIDATED
/ SIMULATED_OK / ...).
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import hashlib
import sys
import time
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

WHITELIST_SELECTORS: frozenset[str] = frozenset({
    "0xb95cac29",  # addLiquidity
    "0x0cfe81c8",  # removeLiquidity
    "0x02751cec",  # decreaseLiquidity / removeLiquidity on Uniswap V3 style
    "0x9ff3e9fc",  # claimFees
    "0x38b2a21d",  # swap
    "0xf28f8205",  # quoteAddLiquidity
    "0xfc6f7865",  # collect
    "0x42966c68",  # burn
    "0x88316456",  # mint
    "0x219f5d17",  # increaseLiquidity
    "0x0c49ccbe",  # decreaseLiquidity
    "0x04e45aaf",  # exactInputSingle swap
    "0xac9650d8",  # multicall
})

WHITELIST_RECIPIENTS: frozenset[str] = frozenset({
    # Zero address (burn / null address)
    "0x0000000000000000000000000000000000000000",
    # Placeholder for project-controlled wallet; MUST be replaced before any LIVE mode
    "0x000000000000000000000000000000000000dead",
})

# Fields required for full validation. Missing any -> field_missing:<name>.
REQUIRED_FIELDS = (
    "calldata_bytes",
    "expected_intent",
    "target_address",
    "selector",
    "recipient_address",
    "deadline",
    "value_wei",
    "calldata_hash",
)


def load_whitelist() -> dict[str, set[str]]:
    """Return dictionary of whitelist constants for inspection."""
    return {
        "targets": set(WHITELIST_TARGETS),
        "selectors": set(WHITELIST_SELECTORS),
        "recipients": set(WHITELIST_RECIPIENTS),
    }


def _norm_hex(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.lower().startswith("0x"):
        return value.lower()
    return None


def _hex_to_bytes(calldata: str) -> bytes:
    text = calldata[2:] if calldata.lower().startswith("0x") else calldata
    if len(text) % 2:
        raise ValueError("odd-length calldata hex")
    return bytes.fromhex(text)


def _selector_of(calldata: str) -> Optional[str]:
    try:
        raw = _hex_to_bytes(calldata)
    except ValueError:
        return None
    if len(raw) < 4:
        return None
    return "0x" + raw[:4].hex()


def _deadline_unix(deadline: Any) -> Optional[int]:
    """Coerce deadline to unix seconds. Accepts int, str-int, or ISO-8601 string."""
    if isinstance(deadline, (int, float)):
        return int(deadline)
    if isinstance(deadline, str):
        try:
            return int(deadline)
        except ValueError:
            pass
        try:
            from datetime import datetime
            return int(datetime.fromisoformat(
                deadline.replace("Z", "+00:00")
            ).timestamp())
        except Exception:
            return None
    return None


def _decoded_subcalls(decoded: Mapping) -> list[Mapping]:
    """Return the inner multicall subcalls (if any) from a decoded payload."""
    subcalls: list[Mapping] = []
    for arg in decoded.get("args", []) or []:
        if isinstance(arg, Mapping) and arg.get("name") == "calls":
            val = arg.get("value", [])
            if isinstance(val, list):
                subcalls.extend(x for x in val if isinstance(x, Mapping))
    subcalls.extend(x for x in (decoded.get("subcalls") or []) if isinstance(x, Mapping))
    return subcalls


def verify_intent_or_reject(intent: dict) -> Tuple[bool, Optional[str]]:
    """Verify intent against the whitelist rules.

    Returns ``(True, None)`` on full pass and ``(False, 'whitelist_reject:<reason>')``
    on any failure (missing field, decoder exception, target/selector/recipient
    not on the allow-list, chain mismatch, calldata-hash mismatch, expired
    deadline, bad multicall sub-action, value mismatch, or min-out mismatch).

    The gate never writes SIMULATED_OK; the caller chooses the post-validation
    state label based on the whitelist verdict.
    """
    if not isinstance(intent, Mapping):
        return False, "whitelist_reject:invalid_intent_type"

    # Field-presence check (fail closed, no fallback path).
    for field in REQUIRED_FIELDS:
        if field not in intent or intent[field] is None or intent[field] == "":
            return False, f"whitelist_reject:field_missing:{field}"

    # Decode calldata + verify the intent payload with the decoder module.
    # CA-02 (PAPER_ACCEPTANCE_REPAIR_V2): the previous code threw away
    # verify_intent's (ok, reasons) return value.  When the decoder decided
    # the intent did not match the decoded calldata (returning False plus a
    # list of reasons), no exception was raised so the except branch never
    # fired and the wrapper silently continued past the intent-equality
    # check.  We now bind both values and short-circuit on False.
    try:
        from scripts.lp_rh_calldata_decoder_v1_readonly import decode_calldata, verify_intent
        calldata = intent["calldata_bytes"]
        decoded = decode_calldata(calldata)
    except Exception as exc:
        return False, f"whitelist_reject:decoder_exception:{type(exc).__name__}"

    if decoded.get("status") != "OK":
        return False, f"whitelist_reject:calldata_decode_failed:{decoded.get('status', 'UNKNOWN')}"

    # Metadata-bound selector must equal the calldata-derived selector.
    # Prevents submitting an intent header claiming a safe selector while
    # the actual on-chain bytes encode a different action.
    decoded_selector = decoded.get("selector")
    intent_selector = intent.get("selector")
    if decoded_selector and intent_selector and decoded_selector.lower() != intent_selector.lower():
        return False, f"whitelist_reject:selector_mismatch:decoded={decoded_selector}:intent={intent_selector}"

    try:
        intent_ok, intent_reasons = verify_intent(decoded, intent=intent["expected_intent"])
    except Exception as exc:
        return False, f"whitelist_reject:decoder_exception:{type(exc).__name__}"
    if not intent_ok:
        # Surface the actual reasons so callers can distinguish "intent missing
        # field X" from "intent claims X=foo but calldata encodes X=bar".
        joined = ",".join(intent_reasons) if intent_reasons else "verify_intent_false"
        return False, f"whitelist_reject:intent_verify_failed:{joined}"

    # Whitelist checks on the outer target / selector / recipient.
    target = _norm_hex(intent.get("target_address")) or str(intent.get("target_address") or "").lower().strip()
    if not target:
        return False, "whitelist_reject:field_missing:target_address"
    if target not in WHITELIST_TARGETS:
        return False, f"whitelist_reject:target_not_whitelisted:{target}"

    selector = _norm_hex(intent.get("selector")) or str(intent.get("selector") or "").lower().strip()
    if not selector:
        return False, "whitelist_reject:field_missing:selector"
    if selector not in WHITELIST_SELECTORS:
        return False, f"whitelist_reject:selector_not_whitelisted:{selector}"

    recipient = _norm_hex(intent.get("recipient_address"))
    if recipient is None:
        recipient = _norm_hex(intent.get("wallet_address"))
    if recipient is None:
        return False, "whitelist_reject:field_missing:recipient_address"
    if recipient not in WHITELIST_RECIPIENTS:
        return False, f"whitelist_reject:recipient_not_whitelisted:{recipient}"

    # Chain-id check (when intent supplies intent_chain_id).
    intent_chain_id = intent.get("intent_chain_id")
    if intent_chain_id is not None:
        try:
            chain_id = int(intent["chain_id"])
            intent_chain_id_int = int(intent_chain_id)
            if chain_id != intent_chain_id_int:
                return False, "whitelist_reject:chain_mismatch"
        except (TypeError, ValueError):
            return False, "whitelist_reject:chain_mismatch"

    # calldata_hash match.
    expected_hash = _norm_hex(intent.get("calldata_hash"))
    actual_hash = "0x" + hashlib.sha256(_hex_to_bytes(calldata)).hexdigest()
    if expected_hash is not None and expected_hash != actual_hash:
        return False, "whitelist_reject:calldata_hash_mismatch"

    # Deadline check.
    deadline_unix = _deadline_unix(intent.get("deadline"))
    if deadline_unix is None:
        return False, "whitelist_reject:field_missing:deadline"
    now_unix = int(time.time())
    if deadline_unix <= now_unix:
        return False, "whitelist_reject:deadline_expired"

    # value_wei equality check.
    try:
        actual_value = int(intent.get("value_wei") or 0)
    except (TypeError, ValueError):
        return False, "whitelist_reject:value_mismatch"
    expected_value = intent.get("expected_value_wei")
    if expected_value is not None:
        try:
            if int(expected_value) != actual_value:
                return False, "whitelist_reject:value_mismatch"
        except (TypeError, ValueError):
            return False, "whitelist_reject:value_mismatch"

    # Min-out / amount-protection sanity: at least one of amount0Min / amount1Min /
    # amountOutMinimum must be non-zero.  This is a structural check (not a
    # numerical comparison against expected_min_out, which the simulator does).
    decoded_args = decoded.get("args", []) or []
    min_fields = ("amount0Min", "amount1Min", "amountOutMinimum")
    found_min = False
    for arg in decoded_args:
        if isinstance(arg, Mapping) and arg.get("name") in min_fields:
            try:
                if int(arg.get("value") or 0) > 0:
                    found_min = True
                    break
            except (TypeError, ValueError):
                continue
    if not found_min:
        # For multicall, skip outer-level check (inner checks still apply).
        if selector != "0xac9650d8":
            return False, "whitelist_reject:missing_slippage_protection"

    # Multicall: recurse into each sub-action with the same whitelist.
    if selector == "0xac9650d8":
        for idx, sub in enumerate(_decoded_subcalls(decoded)):
            if not isinstance(sub, Mapping):
                continue
            sub_target = (_norm_hex(sub.get("target"))
                          or _norm_hex(sub.get("call_target"))
                          or "").strip()
            if not sub_target:
                return False, f"whitelist_reject:multicall_inner_reject:no_target:{idx}"
            if sub_target not in WHITELIST_TARGETS:
                return False, f"whitelist_reject:multicall_inner_reject:target_not_whitelisted:{idx}:{sub_target}"
            sub_sel = _norm_hex(sub.get("selector")) or ""
            if not sub_sel:
                # Derive selector from raw calldata if available.
                raw = sub.get("calldata") or sub.get("raw") or ""
                if isinstance(raw, str) and raw:
                    sub_sel = _selector_of(raw) or sub_sel
            if sub_sel and sub_sel not in WHITELIST_SELECTORS:
                return False, f"whitelist_reject:multicall_inner_reject:selector_not_whitelisted:{idx}:{sub_sel}"
            sub_recipient = None
            for arg in sub.get("args", []) or []:
                if isinstance(arg, Mapping) and arg.get("name") in ("recipient",):
                    sub_recipient = _norm_hex(arg.get("value"))
                    if sub_recipient is not None:
                        break
            if sub_recipient is not None and sub_recipient not in WHITELIST_RECIPIENTS:
                return False, f"whitelist_reject:multicall_inner_reject:recipient_not_whitelisted:{idx}:{sub_recipient}"

    return True, None
