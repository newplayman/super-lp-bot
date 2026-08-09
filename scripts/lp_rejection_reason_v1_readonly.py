#!/usr/bin/env python3
"""Deterministic fail-closed rejection explanations for scanner evidence."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Optional


_NON_REJECTION_TOKENS = frozenset(
    {"", "ok", "pass", "passed", "true", "accepted", "none", "null", "n/a", "na"}
)


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _is_meaningful(value: Any) -> bool:
    return _text(value).casefold() not in _NON_REJECTION_TOKENS


def _permanent_reason(record: Mapping[str, Any]) -> Optional[str]:
    permanent = _text(record.get("permanent_fail_closed_reason"))
    if permanent:
        if permanent.upper().startswith("PERMANENT_FAIL_CLOSED"):
            return permanent
        return f"PERMANENT_FAIL_CLOSED:{permanent}"
    for key in (
        "persisted_rejection_reason",
        "rejection_reason",
        "gate_reason",
        "error",
        "netcover_gate_status",
    ):
        candidate = _text(record.get(key))
        if candidate.upper().startswith("PERMANENT_FAIL_CLOSED"):
            return candidate
    return None


def _entry_block_reasons(record: Mapping[str, Any]) -> list[str]:
    raw = record.get("entry_block_reasons")
    if raw is None:
        return []
    values: Sequence[Any] = (raw,) if isinstance(raw, (str, bytes)) else raw
    try:
        return [_text(value) for value in values if _is_meaningful(value)]
    except TypeError:
        return [_text(raw)] if _is_meaningful(raw) else []


def explain_rejection(record: Mapping[str, Any], accepted: bool) -> Optional[str]:
    """Explain a terminal rejection without treating success sentinels as failures.

    This function is explanatory only: it never derives or changes acceptance.
    Permanent fail-closed evidence and entry vetoes outrank stale upstream text.
    """
    if accepted:
        return None

    permanent = _permanent_reason(record)
    if permanent:
        return permanent

    entry_blocks = _entry_block_reasons(record)
    if entry_blocks:
        return "ENTRY_INELIGIBLE:" + ",".join(entry_blocks)
    if record.get("entry_eligible") is False:
        return "ENTRY_INELIGIBLE:UNSPECIFIED_FAIL_CLOSED"

    for key in ("persisted_rejection_reason", "rejection_reason"):
        explicit = record.get(key)
        if _is_meaningful(explicit):
            return _text(explicit)

    gate_reason = record.get("gate_reason")
    if record.get("gate_ok") is False and _is_meaningful(gate_reason):
        return "COARSE_GATE_REJECTED:" + _text(gate_reason)

    gates = record.get("gates")
    if isinstance(gates, Mapping):
        failed = sorted(str(key) for key, passed in gates.items() if passed is False)
        if failed:
            return "FAILED_GATES:" + ",".join(failed)

    netcover_status = record.get("netcover_gate_status")
    if _is_meaningful(netcover_status):
        return "NETCOVER_REJECTED:" + _text(netcover_status)

    error = record.get("error")
    if _is_meaningful(error):
        return "ERROR_FAIL_CLOSED:" + _text(error)
    if not bool(record.get("vetted", False)):
        return "FUNNEL_REJECTED:UNSPECIFIED_FAIL_CLOSED"
    if not bool(record.get("netcover_pass", False)):
        return "NETCOVER_REJECTED:UNSPECIFIED_FAIL_CLOSED"
    return "REJECTION_REASON_UNKNOWN_FAIL_CLOSED"
