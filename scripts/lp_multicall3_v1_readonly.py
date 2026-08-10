#!/usr/bin/env python3
"""Base Multicall3 ``aggregate3`` reader (READ-ONLY).

This module batches contract ``eth_call`` reads only.  It cannot batch
``eth_getLogs``: in the current funnel it reduces the resolver/live-state half
of the RPC workload, not the multi-window log half.

The configured Multicall3 address is never trusted merely because it is
well-known.  The first batch validates non-empty bytecode through the supplied
``RpcPool`` and records the bytecode Keccak-256.  A missing/unreadable contract
causes an explicit, measured fallback to individual ``eth_call`` requests.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from Crypto.Hash import keccak


MULTICALL3_ADDRESS = "0xca11bde05977b3631167028862be2a173976ca11"
AGGREGATE3_SELECTOR = "0x82ad56cb"
DEFAULT_BATCH_SIZE = 60
_EMPTY_CODES = frozenset({"0x", "0x0", "0x00", ""})


def _word(value: int) -> bytes:
    if value < 0 or value >= 1 << 256:
        raise ValueError("ABI uint256 out of range")
    return value.to_bytes(32, "big")


def _hex_bytes(value: str, *, field: str) -> bytes:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise ValueError(f"{field} must be 0x-prefixed hex")
    text = value[2:]
    if len(text) % 2:
        raise ValueError(f"{field} must contain whole bytes")
    try:
        return bytes.fromhex(text)
    except ValueError as exc:
        raise ValueError(f"{field} contains non-hex data") from exc


def _address_bytes(value: str) -> bytes:
    raw = _hex_bytes(value, field="target")
    if len(raw) != 20:
        raise ValueError("target must be a 20-byte address")
    return raw


def _dynamic_bytes(raw: bytes) -> bytes:
    padding = (-len(raw)) % 32
    return _word(len(raw)) + raw + (b"\x00" * padding)


@dataclass(frozen=True)
class Call3:
    target: str
    call_data: str
    allow_failure: bool = True


@dataclass(frozen=True)
class Call3Result:
    success: bool
    return_data: str
    source: str
    error: str | None = None


def encode_aggregate3(calls: Sequence[Call3]) -> str:
    """ABI-encode ``aggregate3((address,bool,bytes)[])`` calldata."""
    encoded_items: list[bytes] = []
    for call in calls:
        if call.allow_failure is not True:
            raise ValueError("D1 requires allowFailure=true for every Call3")
        payload = _hex_bytes(call.call_data, field="call_data")
        encoded_items.append(
            (b"\x00" * 12)
            + _address_bytes(call.target)
            + _word(1)
            + _word(96)
            + _dynamic_bytes(payload)
        )

    # Dynamic-array element offsets are relative to the element-head region,
    # i.e. immediately after the array length word.
    offset = 32 * len(encoded_items)
    offsets = []
    for item in encoded_items:
        offsets.append(_word(offset))
        offset += len(item)
    array_body = _word(len(encoded_items)) + b"".join(offsets) + b"".join(encoded_items)
    return AGGREGATE3_SELECTOR + (_word(32) + array_body).hex()


def _read_word(raw: bytes, offset: int) -> int:
    if offset < 0 or offset + 32 > len(raw):
        raise ValueError("aggregate3 ABI result is truncated")
    return int.from_bytes(raw[offset : offset + 32], "big")


def decode_aggregate3_result(value: str) -> list[tuple[bool, str]]:
    """Decode the ABI output ``(bool success, bytes returnData)[]``."""
    raw = _hex_bytes(value, field="aggregate3 result")
    array_base = _read_word(raw, 0)
    count = _read_word(raw, array_base)
    if count > 100_000:
        raise ValueError("aggregate3 result count is implausibly large")
    heads_base = array_base + 32
    if heads_base + count * 32 > len(raw):
        raise ValueError("aggregate3 result array head is truncated")

    decoded: list[tuple[bool, str]] = []
    for index in range(count):
        item_base = heads_base + _read_word(raw, heads_base + index * 32)
        success_word = _read_word(raw, item_base)
        if success_word not in (0, 1):
            raise ValueError("aggregate3 success flag is not boolean")
        data_base = item_base + _read_word(raw, item_base + 32)
        data_length = _read_word(raw, data_base)
        start = data_base + 32
        end = start + data_length
        if end > len(raw):
            raise ValueError("aggregate3 returnData is truncated")
        decoded.append((bool(success_word), "0x" + raw[start:end].hex()))
    return decoded


def bytecode_keccak256(code: str) -> str:
    digest = keccak.new(digest_bits=256)
    digest.update(_hex_bytes(code, field="bytecode"))
    return "0x" + digest.hexdigest()


class Multicall3Reader:
    """Health-aware batch reader backed exclusively by a shared ``RpcPool``."""

    def __init__(
        self,
        rpc_pool: Any,
        *,
        address: str = MULTICALL3_ADDRESS,
        batch_size: int | None = None,
    ) -> None:
        if not callable(getattr(rpc_pool, "call", None)):
            raise TypeError("rpc_pool must expose RpcPool.call")
        configured = (
            int(os.environ.get("LP_MULTICALL3_BATCH_SIZE", str(DEFAULT_BATCH_SIZE)))
            if batch_size is None
            else int(batch_size)
        )
        if configured <= 0:
            raise ValueError("batch_size must be positive")
        self.rpc_pool = rpc_pool
        self.address = "0x" + _address_bytes(address).hex()
        self.batch_size = configured
        self._validated = False
        self._usable = False
        self.evidence: dict[str, Any] = {
            "address": self.address,
            "validation_status": "NOT_RUN",
            "bytecode_bytes": 0,
            "bytecode_keccak256": None,
            "validation_error": None,
        }
        self._counts = {
            "logical_calls": 0,
            "eth_getCode_requests": 0,
            "aggregate3_requests": 0,
            "serial_fallback_requests": 0,
            "per_call_failures": 0,
        }

    def request_counts(self) -> dict[str, int]:
        return dict(self._counts)

    def validate_contract(self) -> bool:
        if self._validated:
            return self._usable
        self._validated = True
        self._counts["eth_getCode_requests"] += 1
        try:
            code = self.rpc_pool.call("eth_getCode", [self.address, "latest"])
            if not isinstance(code, str) or code.lower() in _EMPTY_CODES:
                raise ValueError("multicall3 bytecode is empty")
            code_bytes = _hex_bytes(code, field="bytecode")
            if not code_bytes:
                raise ValueError("multicall3 bytecode is empty")
            self.evidence.update({
                "validation_status": "VALIDATED",
                "bytecode_bytes": len(code_bytes),
                "bytecode_keccak256": bytecode_keccak256(code),
                "validation_error": None,
            })
            self._usable = True
        except Exception as exc:  # explicit serial fallback, retained as evidence
            self.evidence.update({
                "validation_status": "FALLBACK_SERIAL",
                "validation_error": f"{type(exc).__name__}: {exc}",
            })
            self._usable = False
        return self._usable

    def _serial(self, calls: Sequence[Call3], block_tag: str, reason: str) -> list[Call3Result]:
        results: list[Call3Result] = []
        for call in calls:
            self._counts["serial_fallback_requests"] += 1
            try:
                value = self.rpc_pool.call(
                    "eth_call",
                    [{"to": call.target, "data": call.call_data}, block_tag],
                )
                if not isinstance(value, str) or not value.startswith("0x"):
                    raise ValueError(f"unexpected eth_call result {value!r}")
                results.append(Call3Result(True, value, "serial_fallback", reason))
            except Exception as exc:
                self._counts["per_call_failures"] += 1
                results.append(Call3Result(
                    False,
                    "0x",
                    "serial_fallback",
                    f"{reason}; {type(exc).__name__}: {exc}",
                ))
        return results

    def execute(self, calls: Iterable[Call3], *, block_tag: str = "latest") -> list[Call3Result]:
        items = list(calls)
        self._counts["logical_calls"] += len(items)
        if not items:
            return []
        if not self.validate_contract():
            return self._serial(items, block_tag, "multicall3_contract_validation_failed")

        output: list[Call3Result] = []
        for start in range(0, len(items), self.batch_size):
            batch = items[start : start + self.batch_size]
            try:
                self._counts["aggregate3_requests"] += 1
                raw = self.rpc_pool.call(
                    "eth_call",
                    [{"to": self.address, "data": encode_aggregate3(batch)}, block_tag],
                )
                decoded = decode_aggregate3_result(raw)
                if len(decoded) != len(batch):
                    raise ValueError(
                        f"aggregate3 result cardinality {len(decoded)} != {len(batch)}"
                    )
                for success, return_data in decoded:
                    if not success:
                        self._counts["per_call_failures"] += 1
                    output.append(Call3Result(
                        success,
                        return_data,
                        "multicall3",
                        None if success else "aggregate3_subcall_failed",
                    ))
            except Exception as exc:
                reason = f"aggregate3_batch_failed:{type(exc).__name__}: {exc}"
                output.extend(self._serial(batch, block_tag, reason))
        return output


def _call_key(target: str, data: str, block_tag: str) -> tuple[str, str, str]:
    return ("0x" + _address_bytes(target).hex(), data.lower(), str(block_tag).lower())


class BatchedRpcReader:
    """RpcPool-compatible read proxy with an explicitly primed eth_call cache.

    Failed Multicall3 subcalls are deliberately not cached.  When production
    code later consumes that logical call it receives an individual RpcPool
    retry, so one bad target neither swallows the batch nor fabricates a value.
    """

    def __init__(self, rpc_pool: Any, multicall: Multicall3Reader | None = None) -> None:
        if not callable(getattr(rpc_pool, "call", None)):
            raise TypeError("rpc_pool must expose RpcPool.call")
        self.rpc_pool = rpc_pool
        self.multicall = multicall or Multicall3Reader(rpc_pool)
        self._cache: dict[tuple[str, str, str], str] = {}
        self.cache_hits = 0
        self.failed_primes = 0

    def prime(self, calls: Iterable[Call3], *, block_tag: str = "latest") -> list[Call3Result]:
        items = list(calls)
        # ``latest`` is cycle-local evidence.  Never let a failed refresh expose
        # a successful value cached by an older scanner cycle.
        for call in items:
            self._cache.pop(_call_key(call.target, call.call_data, block_tag), None)
        results = self.multicall.execute(items, block_tag=block_tag)
        for call, result in zip(items, results):
            if result.success:
                self._cache[_call_key(call.target, call.call_data, block_tag)] = result.return_data
            else:
                self.failed_primes += 1
        return results

    def cached(self, target: str, data: str, block_tag: str = "latest") -> str | None:
        return self._cache.get(_call_key(target, data, block_tag))

    def call(self, method: str, params: Sequence[Any], timeout: int = 20) -> Any:
        if method == "eth_call" and len(params) >= 2 and isinstance(params[0], Mapping):
            tx = params[0]
            target = tx.get("to")
            data = tx.get("data")
            if isinstance(target, str) and isinstance(data, str):
                key = _call_key(target, data, str(params[1]))
                if key in self._cache:
                    self.cache_hits += 1
                    return self._cache[key]
        return self.rpc_pool.call(method, params, timeout=timeout)
