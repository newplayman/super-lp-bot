"""
RH V3 Calldata Fixtures — pure-Python ABI encoder for Uniswap V3 on RH chain (4663).

No network access. No RPC calls. Produces 0x-prefixed hex calldata strings.

Selector reference (verified against Uniswap V3 peripheral ABI):
  mint       = 0x88316456
  burn       = 0x42966c68
  collect    = 0xfc6f7865
  multicall  = 0xac9650d8
  increaseLiquidity = 0x219f5d17
  decreaseLiquidity = 0x0c49ccbe

mint() ABI:
  (address token0, address token1, uint24 fee,
   int24 tickLower, int24 tickUpper,
   uint256 amount0Desired, uint256 amount1Desired,
   uint256 amount0Min, uint256 amount1Min,
   address recipient, uint256 deadline)

collect() ABI:
  (uint256 tokenId, address recipient, uint128 amount0Max, uint128 amount1Max)

multicall() ABI:
  (bytes[] calls)  — each call is raw encoded subcall bytes
"""

from __future__ import annotations

import hashlib
import struct
import time

# ─── Selectors ─────────────────────────────────────────────────────────────────
SEL_MINT: str = "0x88316456"
SEL_BURN: str = "0x42966c68"
SEL_COLLECT: str = "0xfc6f7865"
SEL_MULTICALL: str = "0xac9650d8"
SEL_INC_LIQ: str = "0x219f5d17"
SEL_DEC_LIQ: str = "0x0c49ccbe"

# ─── Sentinel addresses (match lp_rh_chain_manifest_v1_readonly) ───────────────
NPM_RH_SENTINEL: str = "0x" + "0" * 40
FACTORY_RH_SENTINEL: str = "0x" + "0" * 40

# ─── Deadline helper ────────────────────────────────────────────────────────────
def _future_deadline(secs: int = 3600) -> int:
    """Return a deadline unix timestamp `secs` seconds in the future."""
    return int(time.time()) + secs


# ─── Low-level ABI encoding primitives ─────────────────────────────────────────
def _pad32(data: bytes) -> bytes:
    """Right-pad with zeros to a 32-byte word boundary."""
    remainder = len(data) % 32
    if remainder:
        data = data + b"\x00" * (32 - remainder)
    return data


def _encode_uint256(value: int) -> bytes:
    """ABI-encode a uint256 (big-endian 32 bytes)."""
    if value < 0:
        raise ValueError("negative uint256")
    return value.to_bytes(32, "big")


def _encode_address(addr: str) -> bytes:
    """ABI-encode an address (20 bytes, right-padded to 32)."""
    addr = addr.lower().replace("0x", "")
    if len(addr) != 40:
        raise ValueError(f"bad address length: {addr}")
    return bytes.fromhex(addr).rjust(32, b"\x00")


def _encode_int24(value: int) -> bytes:
    """ABI-encode an int24 (signed 24-bit, big-endian 4 bytes right-padded)."""
    if not (-8388608 <= value <= 8388607):
        raise ValueError(f"int24 overflow: {value}")
    return struct.pack(">i", value).rjust(32, b"\x00")


def _encode_uint24(value: int) -> bytes:
    """ABI-encode a uint24 (big-endian 3 bytes right-padded)."""
    if not (0 <= value <= 0xFFFFFF):
        raise ValueError(f"uint24 overflow: {value}")
    return value.to_bytes(32, "big")


def _encode_uint128(value: int) -> bytes:
    """ABI-encode a uint128 (big-endian 16 bytes right-padded)."""
    if value < 0:
        raise ValueError("negative uint128")
    return value.to_bytes(32, "big")


# ─── Selector ─────────────────────────────────────────────────────────────────
def _selector_hex(sel: str) -> str:
    s = sel.lower().replace("0x", "")
    if len(s) != 8:
        raise ValueError(f"bad selector length: {sel}")
    return s


# ─── mint ─────────────────────────────────────────────────────────────────────
def build_mint_calldata(
    token0: str,
    token1: str,
    fee: int,
    tick_lower: int,
    tick_upper: int,
    amount0_desired: int,
    amount1_desired: int,
    amount0_min: int,
    amount1_min: int,
    recipient: str,
    deadline: int,
) -> str:
    """
    Build a Uniswap V3 `mint` calldata bytes (0x-prefixed hex string).

    Selector: 0x88316456
    ABI: mint(token0, token1, fee, tickLower, tickUpper,
               amount0Desired, amount1Desired, amount0Min, amount1Min,
               recipient, deadline)
    """
    sel = _selector_hex(SEL_MINT)
    parts = (
        _encode_address(token0)
        + _encode_address(token1)
        + _encode_uint24(fee)
        + _encode_int24(tick_lower)
        + _encode_int24(tick_upper)
        + _encode_uint256(amount0_desired)
        + _encode_uint256(amount1_desired)
        + _encode_uint256(amount0_min)
        + _encode_uint256(amount1_min)
        + _encode_address(recipient)
        + _encode_uint256(deadline)
    )
    return "0x" + sel + parts.hex()


def build_collect_calldata(
    token_id: int,
    recipient: str,
    amount0_max: int,
    amount1_max: int,
) -> str:
    """
    Build a Uniswap V3 `collect` calldata bytes (0x-prefixed hex string).

    Selector: 0xfc6f7865
    ABI: collect(tokenId, recipient, amount0Max, amount1Max)
    """
    sel = _selector_hex(SEL_COLLECT)
    parts = (
        _encode_uint256(token_id)
        + _encode_address(recipient)
        + _encode_uint128(amount0_max)
        + _encode_uint128(amount1_max)
    )
    return "0x" + sel + parts.hex()


def build_multicall_calldata(subcalls: list[str]) -> str:
    """
    Build a Uniswap V3 `multicall` calldata containing arbitrary subcall hex strings.

    Selector: 0xac9650d8
    ABI: multicall(bytes[] calls) where each element is raw encoded subcall bytes.

    Layout after selector:
      [offset_0(32)] ... [offset_N-1(32)] [count(32)] [len_0(32)] [data_0_padded] ...

    Decoder (_decode_bytes_array) interpretation:
      top = body[0:32]  (as big-endian uint256) = byte position of count word
      count = body[top:top+32]
      For element i:
        offset_i = body[top+32+i*32:top+32+(i+1)*32]  (as big-endian uint256)
        start_i  = top + 32 + offset_i   (byte position of len_i word)
        length_i = body[start_i:start_i+32]  (as big-endian uint256)
        data_i   = body[start_i+32:start_i+32+length_i]

    For element 0 with 1 call: top=32, offset_0=0, len_0 at body[64], data_0 at body[96].
    For multiple elements, offset_i must account for padded sizes of elem_0..elem_{i-1}.
    """
    sel = _selector_hex(SEL_MULTICALL)
    num_calls = len(subcalls)

    # top = byte offset to count word = num_calls * 32
    top_bytes = _encode_uint256(num_calls * 32)

    # Build data section: count + (len_i + padded_data_i) for each element
    # Data section layout: count(32) + [len_i(32) + data_i_padded] * N
    # offset_i = i*32 + sum(padded_len_0..elem_{i-1})  (relative to data section start)
    # After elem i: cumsum += padded_len_i
    data_parts = [_encode_uint256(num_calls)]  # count
    offsets = []
    cumsum = 0
    for i, sc in enumerate(subcalls):
        offsets.append(_encode_uint256(i * 32 + cumsum))
        raw = bytes.fromhex(sc.lower().replace("0x", ""))
        padded = _pad32(raw)
        data_parts.append(_encode_uint256(len(raw)))
        data_parts.append(padded)
        cumsum += len(padded)

    offset_array = b"".join(offsets)
    data_section = b"".join(data_parts)

    return "0x" + sel + top_bytes.hex() + offset_array.hex() + data_section.hex()


# ─── Calldata hash (SHA-256, lowercased) ─────────────────────────────────────
def calldata_hash(calldata_hex: str) -> str:
    """Return the SHA-256 hash of raw calldata bytes (0x-prefixed hex in, 0x-hex out)."""
    text = calldata_hex[2:] if calldata_hex.lower().startswith("0x") else calldata_hex
    raw = bytes.fromhex(text)
    return "0x" + hashlib.sha256(raw).hexdigest()


# ─── Common test fixtures ─────────────────────────────────────────────────────
DUMMY_TOKEN0: str = "0x" + "a1" * 20  # 0xa1a1a1...
DUMMY_TOKEN1: str = "0x" + "b2" * 20  # 0xb2b2b2...
DUMMY_RECIPIENT: str = "0x" + "c3" * 20  # 0xc3c3c3...
DUMMY_WALLET: str = "0x" + "w1" * 20  # 0xw1w1w1...
FUTURE_DEADLINE: int = _future_deadline(3600)
PAST_DEADLINE: int = _future_deadline(-100)

# Legal mint: full-range, standard slippage protection
LEGAL_MINT_CALDATA: str = build_mint_calldata(
    token0=DUMMY_TOKEN0,
    token1=DUMMY_TOKEN1,
    fee=3000,
    tick_lower=-887220,
    tick_upper=887220,
    amount0_desired=1_000_000_000_000_000_000,
    amount1_desired=1_000_000_000_000_000_000,
    amount0_min=1,
    amount1_min=1,
    recipient=DUMMY_RECIPIENT,
    deadline=FUTURE_DEADLINE,
)

LEGAL_MINT_SEL: str = SEL_MINT
LEGAL_MINT_TARGET: str = NPM_RH_SENTINEL
LEGAL_MINT_HASH: str = calldata_hash(LEGAL_MINT_CALDATA)
LEGAL_MINT_VALUE: int = 0

# Legal collect
LEGAL_COLLECT_CALDATA: str = build_collect_calldata(
    token_id=1,
    recipient=DUMMY_RECIPIENT,
    amount0_max=1_000_000_000_000_000_000,
    amount1_max=1_000_000_000_000_000_000,
)
LEGAL_COLLECT_SEL: str = SEL_COLLECT
LEGAL_COLLECT_HASH: str = calldata_hash(LEGAL_COLLECT_CALDATA)

# Legal multicall with one mint inner call
LEGAL_MULTICALL_CALDATA: str = build_multicall_calldata([LEGAL_MINT_CALDATA])
LEGAL_MULTICALL_SEL: str = SEL_MULTICALL
LEGAL_MULTICALL_HASH: str = calldata_hash(LEGAL_MULTICALL_CALDATA)

# ─── Intent claim dicts (all required _INTENT_FIELDS) ─────────────────────────
_NOW: int = int(time.time())

LEGAL_MINT_INTENT: dict = dict(
    chain_id=4663,
    target_address=NPM_RH_SENTINEL,
    selector=SEL_MINT,
    recipient_address=DUMMY_RECIPIENT,
    wallet_address=DUMMY_WALLET,
    deadline=FUTURE_DEADLINE,
    value_wei=0,
    calldata_bytes=LEGAL_MINT_CALDATA,
    calldata_hash=LEGAL_MINT_HASH,
    expected_value_wei=0,
    role="gate",  # default: no bypass; tests override to "test" when needed
    expected_intent=dict(
        chain_id=4663,
        wallet_id="wallet-001",
        position_id="pos-001",
        request_id="req-001",
        decision_id="dec-001",
        idempotency_key="idem-mint-001",
        policy_hash="0x" + "ab" * 32,
        code_version="v3.0.0",
        snapshot_hash="0x" + "cd" * 32,
        calldata_hash=LEGAL_MINT_HASH,
        expires_at=_NOW + 3600,
    ),
)

LEGAL_COLLECT_INTENT: dict = dict(
    chain_id=4663,
    target_address=NPM_RH_SENTINEL,
    selector=SEL_COLLECT,
    recipient_address=DUMMY_RECIPIENT,
    wallet_address=DUMMY_WALLET,
    deadline=FUTURE_DEADLINE,
    value_wei=0,
    calldata_bytes=LEGAL_COLLECT_CALDATA,
    calldata_hash=LEGAL_COLLECT_HASH,
    expected_value_wei=0,
    role="gate",
    expected_intent=dict(
        chain_id=4663,
        wallet_id="wallet-001",
        position_id="pos-001",
        request_id="req-002",
        decision_id="dec-001",
        idempotency_key="idem-collect-001",
        policy_hash="0x" + "ab" * 32,
        code_version="v3.0.0",
        snapshot_hash="0x" + "cd" * 32,
        calldata_hash=LEGAL_COLLECT_HASH,
        expires_at=_NOW + 3600,
    ),
)

LEGAL_MULTICALL_INTENT: dict = dict(
    chain_id=4663,
    target_address=NPM_RH_SENTINEL,
    selector=SEL_MULTICALL,
    recipient_address=DUMMY_RECIPIENT,
    wallet_address=DUMMY_WALLET,
    deadline=FUTURE_DEADLINE,
    value_wei=0,
    calldata_bytes=LEGAL_MULTICALL_CALDATA,
    calldata_hash=LEGAL_MULTICALL_HASH,
    expected_value_wei=0,
    role="gate",
    expected_intent=dict(
        chain_id=4663,
        wallet_id="wallet-001",
        position_id="pos-001",
        request_id="req-003",
        decision_id="dec-001",
        idempotency_key="idem-multicall-001",
        policy_hash="0x" + "ab" * 32,
        code_version="v3.0.0",
        snapshot_hash="0x" + "cd" * 32,
        calldata_hash=LEGAL_MULTICALL_HASH,
        expires_at=_NOW + 3600,
    ),
)


if __name__ == "__main__":
    print(f"LEGAL_MINT_CALDATA:    {LEGAL_MINT_CALDATA[:42]}...")
    print(f"LEGAL_MINT_HASH:        {LEGAL_MINT_HASH}")
    print(f"LEGAL_COLLECT_CALDATA: {LEGAL_COLLECT_CALDATA[:42]}...")
    print(f"LEGAL_MULTICALL_CALD:  {LEGAL_MULTICALL_CALDATA[:42]}...")
    print(f"FUTURE_DEADLINE:        {FUTURE_DEADLINE}  (now={_NOW})")
    assert LEGAL_MINT_CALDATA.startswith(SEL_MINT), "mint selector mismatch"
    assert LEGAL_COLLECT_CALDATA.startswith(SEL_COLLECT), "collect selector mismatch"
    assert LEGAL_MULTICALL_CALDATA.startswith(SEL_MULTICALL), "multicall selector mismatch"
    print("[self-test] ALL PASS")
