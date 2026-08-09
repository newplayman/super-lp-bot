"""Base M1 single-position executor (C4, no live transaction performed here).

The module owns the narrow transaction boundary for Uniswap v3 and Aerodrome
Slipstream NonfungiblePositionManager contracts on Base.  Transaction building
is pure.  Signing is delegated to Foundry ``cast mktx`` with an encrypted
keystore; broadcasting remains fail-closed unless two independent live gates
are open at process start.

No private key or mnemonic environment variable is supported.
"""
from __future__ import annotations

import json
import http.client
import os
import stat
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


BASE_CHAIN_ID = 8453
UINT128_MAX = (1 << 128) - 1
UINT256_MAX = (1 << 256) - 1
LIVE_CONFIRMATION = "CONFIRM_BASE_M1_LIVE_BROADCAST"
MAX_SLIPPAGE_BPS = 75

UNISWAP_V3_NPM = "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1"
AERODROME_SLIPSTREAM_NPMS = frozenset(
    {
        # Initial, gauge-caps, and Gauges-v3 deployments from the official repo.
        "0x827922686190790b37229fd06084350E74485b72",
        "0xa990C6a764b73BF43cee5Bb40339c3322FB9D55F",
        "0xe1f8cd9AC4e4A65F54f38a5CdAfCA44f6dD68b53",
    }
)


class LiveTradingLocked(RuntimeError):
    """Raised whenever a caller reaches broadcast without both live gates."""


class PolicyRejected(RuntimeError):
    """Raised when an intent or its evidence violates the execution contract."""


class ReceiptFailed(RuntimeError):
    """Raised for reverted or reorg-invalidated transactions."""


def decode_revert_data(data: str | None) -> str:
    """Decode Solidity Error(string)/Panic(uint256), retaining unknown payloads."""
    if not data or not isinstance(data, str) or not data.startswith("0x"):
        return "reason unavailable"
    raw = data[2:]
    if raw.startswith("08c379a0") and len(raw) >= 8 + 64 * 3:
        try:
            length = int(raw[8 + 64 : 8 + 128], 16)
            message = bytes.fromhex(raw[8 + 128 : 8 + 128 + length * 2]).decode("utf-8", "replace")
            return f"Error({message})"
        except (ValueError, UnicodeDecodeError):
            pass
    if raw.startswith("4e487b71") and len(raw) >= 8 + 64:
        return f"Panic(0x{int(raw[8:8 + 64], 16):x})"
    return f"unknown revert data {data[:74]}"


class Protocol(str, Enum):
    UNISWAP_V3 = "uniswap_v3"
    AERODROME_SLIPSTREAM = "aerodrome_slipstream"


class Action(str, Enum):
    APPROVE_EXACT = "approve_exact"
    MINT = "mint"
    DECREASE_LIQUIDITY = "decrease_liquidity"
    COLLECT = "collect"
    BURN = "burn"
    REVOKE = "revoke"


class ExecutionState(str, Enum):
    NORMAL = "NORMAL"
    EXIT_ONLY = "EXIT_ONLY"


RISK_REDUCING_ACTIONS = frozenset(
    {Action.DECREASE_LIQUIDITY, Action.COLLECT, Action.BURN, Action.REVOKE}
)
ACTION_ALLOWLIST = frozenset(Action)


def _norm_address(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("0x") or len(value) != 42:
        raise PolicyRejected(f"invalid EVM address: {value!r}")
    try:
        int(value[2:], 16)
    except ValueError as exc:
        raise PolicyRejected(f"invalid EVM address: {value!r}") from exc
    return value.lower()


def _word(value: int) -> str:
    if not 0 <= value <= UINT256_MAX:
        raise PolicyRejected(f"uint256 out of range: {value}")
    return f"{value:064x}"


def _signed_word(value: int, bits: int = 24) -> str:
    lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    if not lo <= value <= hi:
        raise PolicyRejected(f"int{bits} out of range: {value}")
    return f"{value % (1 << 256):064x}"


def _address_word(value: str) -> str:
    return _norm_address(value)[2:].rjust(64, "0")


def encode_approve(spender: str, amount: int) -> str:
    if amount == UINT256_MAX:
        raise PolicyRejected("ApproveMax is forbidden")
    return "0x095ea7b3" + _address_word(spender) + _word(amount)


def encode_burn(token_id: int) -> str:
    return "0x42966c68" + _word(token_id)


def encode_collect(token_id: int, recipient: str, amount0_max: int, amount1_max: int) -> str:
    if amount0_max > UINT128_MAX or amount1_max > UINT128_MAX:
        raise PolicyRejected("collect maxima must fit uint128")
    return (
        "0xfc6f7865"
        + _word(token_id)
        + _address_word(recipient)
        + _word(amount0_max)
        + _word(amount1_max)
    )


def encode_decrease(
    token_id: int, liquidity: int, amount0_min: int, amount1_min: int, deadline: int
) -> str:
    if not 0 < liquidity <= UINT128_MAX:
        raise PolicyRejected("decrease liquidity must be in uint128 and non-zero")
    return (
        "0x0c49ccbe"
        + _word(token_id)
        + _word(liquidity)
        + _word(amount0_min)
        + _word(amount1_min)
        + _word(deadline)
    )


def encode_uniswap_mint(
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
    if not 0 <= fee < 1 << 24:
        raise PolicyRejected("fee must fit uint24")
    # MintParams is a fully static tuple; ABI encoding does not contain an offset.
    return "0x88316456" + "".join(
        (
            _address_word(token0),
            _address_word(token1),
            _word(fee),
            _signed_word(tick_lower),
            _signed_word(tick_upper),
            _word(amount0_desired),
            _word(amount1_desired),
            _word(amount0_min),
            _word(amount1_min),
            _address_word(recipient),
            _word(deadline),
        )
    )


def encode_slipstream_mint(
    token0: str,
    token1: str,
    tick_spacing: int,
    tick_lower: int,
    tick_upper: int,
    amount0_desired: int,
    amount1_desired: int,
    amount0_min: int,
    amount1_min: int,
    recipient: str,
    deadline: int,
    sqrt_price_x96: int = 0,
) -> str:
    if not 0 <= sqrt_price_x96 < 1 << 160:
        raise PolicyRejected("sqrtPriceX96 must fit uint160")
    return "0xb5007d1f" + "".join(
        (
            _address_word(token0),
            _address_word(token1),
            _signed_word(tick_spacing),
            _signed_word(tick_lower),
            _signed_word(tick_upper),
            _word(amount0_desired),
            _word(amount1_desired),
            _word(amount0_min),
            _word(amount1_min),
            _address_word(recipient),
            _word(deadline),
            _word(sqrt_price_x96),
        )
    )


@dataclass(frozen=True)
class Intent:
    protocol: Protocol
    npm: str
    action: Action
    wallet: str
    strategy_decision_id: str
    risk_verdict_id: str
    idempotency_key: str
    notional_usd: float
    slippage_bps: int
    deadline: int
    pool: str | None = None
    token: str | None = None
    spender: str | None = None
    amount: int = 0
    token0: str | None = None
    token1: str | None = None
    fee: int | None = None
    tick_spacing: int | None = None
    tick_lower: int | None = None
    tick_upper: int | None = None
    amount0_desired: int = 0
    amount1_desired: int = 0
    amount0_min: int = 0
    amount1_min: int = 0
    token_id: int | None = None
    liquidity: int = 0
    sqrt_price_x96: int = 0


@dataclass(frozen=True)
class Preflight:
    simulate_ok: bool
    quote_ok: bool
    basis_ok: bool
    rpc_health_ok: bool
    wallet_balance_ok: bool
    simulation: Mapping[str, Any]
    quote: Mapping[str, Any]
    basis: Mapping[str, Any]
    rpc_health: Mapping[str, Any]
    wallet_balance: Mapping[str, Any]

    def require_all(self) -> None:
        failed = [
            name
            for name in (
                "simulate_ok",
                "quote_ok",
                "basis_ok",
                "rpc_health_ok",
                "wallet_balance_ok",
            )
            if not getattr(self, name)
        ]
        if failed:
            raise PolicyRejected("preflight failed: " + ",".join(failed))


@dataclass(frozen=True)
class Transaction:
    action: Action
    from_address: str
    to: str
    data: str
    value_wei: int
    notional_usd: float
    strategy_decision_id: str
    risk_verdict_id: str
    idempotency_key: str
    deadline: int


@dataclass(frozen=True)
class ExecutionPolicy:
    single_tx_cap_usd: float = 60.0
    daily_cap_usd: float = 60.0
    max_slippage_bps: int = MAX_SLIPPAGE_BPS
    allowed_pools: frozenset[str] = frozenset()
    allowed_tokens: frozenset[str] = frozenset(
        {
            "0x4200000000000000000000000000000000000006",  # WETH
            "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",  # native USDC
        }
    )

    def npm_allowed(self, protocol: Protocol, npm: str) -> bool:
        address = _norm_address(npm)
        if protocol is Protocol.UNISWAP_V3:
            return address == UNISWAP_V3_NPM.lower()
        return address in {item.lower() for item in AERODROME_SLIPSTREAM_NPMS}

    def pool_allowed(self, pool: str | None) -> bool:
        return bool(pool) and _norm_address(pool) in {item.lower() for item in self.allowed_pools}

    def token_allowed(self, token: str | None) -> bool:
        return bool(token) and _norm_address(token) in {item.lower() for item in self.allowed_tokens}


class Ledger:
    """Append-only JSONL result ledger with idempotency and daily cap queries."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def contains(self, key: str) -> bool:
        return any(row.get("idempotency_key") == key for row in self._rows())

    def daily_notional(self, day: str) -> float:
        return sum(
            float(row.get("notional_usd", 0))
            for row in self._rows()
            if row.get("utc_day") == day and row.get("status") == "confirmed"
        )

    def append(self, row: Mapping[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(dict(row), sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())


class IntentValidator:
    def __init__(self, policy: ExecutionPolicy, ledger: Ledger, now: Callable[[], float] = time.time):
        self.policy = policy
        self.ledger = ledger
        self.now = now

    def validate(self, intent: Intent, state: ExecutionState) -> None:
        if intent.action not in ACTION_ALLOWLIST:
            raise PolicyRejected("action not allowlisted")
        if state is ExecutionState.EXIT_ONLY and intent.action not in RISK_REDUCING_ACTIONS:
            raise PolicyRejected("EXIT_ONLY permits risk-reducing actions only")
        if not self.policy.npm_allowed(intent.protocol, intent.npm):
            raise PolicyRejected("protocol/NPM pair not allowlisted")
        if not self.policy.pool_allowed(intent.pool):
            raise PolicyRejected("pool not allowlisted")
        referenced_tokens = [item for item in (intent.token, intent.token0, intent.token1) if item]
        if not referenced_tokens or any(not self.policy.token_allowed(item) for item in referenced_tokens):
            raise PolicyRejected("token not allowlisted")
        _norm_address(intent.wallet)
        if not all((intent.strategy_decision_id, intent.risk_verdict_id, intent.idempotency_key)):
            raise PolicyRejected("decision, verdict, and idempotency identifiers are required")
        if self.ledger.contains(intent.idempotency_key):
            raise PolicyRejected("duplicate idempotency key")
        if not 0 <= intent.notional_usd <= self.policy.single_tx_cap_usd:
            raise PolicyRejected("single transaction notional cap exceeded")
        if not 0 <= intent.slippage_bps <= self.policy.max_slippage_bps:
            raise PolicyRejected("slippage hard limit exceeded")
        if intent.deadline <= int(self.now()) or intent.deadline > int(self.now()) + 3600:
            raise PolicyRejected("deadline must be in the next hour")
        day = datetime.fromtimestamp(self.now(), tz=timezone.utc).date().isoformat()
        if self.ledger.daily_notional(day) + intent.notional_usd > self.policy.daily_cap_usd:
            raise PolicyRejected("daily notional cap exceeded")


def build_transaction(intent: Intent) -> Transaction:
    npm = _norm_address(intent.npm)
    wallet = _norm_address(intent.wallet)
    if intent.action in {Action.APPROVE_EXACT, Action.REVOKE}:
        if not intent.token or _norm_address(intent.spender or "") != npm:
            raise PolicyRejected("approval token and exact NPM spender are required")
        if intent.action is Action.APPROVE_EXACT and not 0 < intent.amount < UINT256_MAX:
            raise PolicyRejected("ApproveExact must be positive and never uint256 max")
        amount = 0 if intent.action is Action.REVOKE else intent.amount
        to, data = _norm_address(intent.token), encode_approve(npm, amount)
    elif intent.action is Action.MINT:
        if not all((intent.token0, intent.token1, intent.tick_lower is not None, intent.tick_upper is not None)):
            raise PolicyRejected("mint token and tick fields are required")
        if intent.tick_lower >= intent.tick_upper:
            raise PolicyRejected("tickLower must be below tickUpper")
        if intent.amount0_min > intent.amount0_desired or intent.amount1_min > intent.amount1_desired:
            raise PolicyRejected("minimum token amount exceeds desired amount")
        if intent.protocol is Protocol.UNISWAP_V3:
            if intent.fee is None:
                raise PolicyRejected("Uniswap fee is required")
            data = encode_uniswap_mint(
                intent.token0, intent.token1, intent.fee, intent.tick_lower, intent.tick_upper,
                intent.amount0_desired, intent.amount1_desired, intent.amount0_min,
                intent.amount1_min, wallet, intent.deadline,
            )
        else:
            if intent.tick_spacing is None:
                raise PolicyRejected("Slipstream tickSpacing is required")
            data = encode_slipstream_mint(
                intent.token0, intent.token1, intent.tick_spacing, intent.tick_lower,
                intent.tick_upper, intent.amount0_desired, intent.amount1_desired,
                intent.amount0_min, intent.amount1_min, wallet, intent.deadline,
                intent.sqrt_price_x96,
            )
        to = npm
    elif intent.action is Action.DECREASE_LIQUIDITY:
        if intent.token_id is None:
            raise PolicyRejected("token id required")
        to, data = npm, encode_decrease(
            intent.token_id, intent.liquidity, intent.amount0_min, intent.amount1_min, intent.deadline
        )
    elif intent.action is Action.COLLECT:
        if intent.token_id is None:
            raise PolicyRejected("token id required")
        to, data = npm, encode_collect(intent.token_id, wallet, UINT128_MAX, UINT128_MAX)
    elif intent.action is Action.BURN:
        if intent.token_id is None:
            raise PolicyRejected("token id required")
        to, data = npm, encode_burn(intent.token_id)
    else:
        raise PolicyRejected("unsupported action")
    return Transaction(
        action=intent.action,
        from_address=wallet,
        to=to,
        data=data,
        value_wei=0,
        notional_usd=intent.notional_usd,
        strategy_decision_id=intent.strategy_decision_id,
        risk_verdict_id=intent.risk_verdict_id,
        idempotency_key=intent.idempotency_key,
        deadline=intent.deadline,
    )


class JsonRpc:
    def __init__(self, url: str, timeout_seconds: float = 15, retries: int = 3):
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self._request_id = 0

    def call(self, method: str, params: Sequence[Any]) -> Any:
        last: Exception | None = None
        for attempt in range(self.retries):
            self._request_id += 1
            body = json.dumps(
                {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": list(params)}
            ).encode()
            try:
                request = urllib.request.Request(
                    self.url,
                    data=body,
                    headers={"Content-Type": "application/json", "User-Agent": "lpbot-base-m1-executor/1.0"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = json.loads(response.read())
                if "error" in payload:
                    raise RuntimeError(json.dumps(payload["error"], sort_keys=True))
                return payload["result"]
            except (urllib.error.URLError, TimeoutError, RuntimeError, ConnectionError, http.client.RemoteDisconnected) as exc:
                last = exc
                if attempt + 1 < self.retries:
                    time.sleep(0.25 * (2**attempt))
        raise RuntimeError(f"RPC {method} failed after {self.retries} attempts: {last}")

    def estimate_gas(self, tx: Transaction) -> int:
        return int(self.call("eth_estimateGas", [_rpc_tx(tx)]), 16)

    def simulate(self, tx: Transaction) -> str:
        return self.call("eth_call", [_rpc_tx(tx), "latest"])

    def eip1559_fees(self) -> tuple[int, int]:
        history = self.call("eth_feeHistory", ["0x5", "latest", [50]])
        base_fee = int(history["baseFeePerGas"][-1], 16)
        rewards = [int(row[0], 16) for row in history.get("reward", []) if row]
        priority = max(rewards[-1] if rewards else 1_000_000, 1_000_000)
        return base_fee * 2 + priority, priority

    def pending_nonce(self, wallet: str) -> int:
        return int(self.call("eth_getTransactionCount", [_norm_address(wallet), "pending"]), 16)

    def broadcast_raw(self, raw_tx: str) -> str:
        return self.call("eth_sendRawTransaction", [raw_tx])

    def receipt(self, tx_hash: str) -> Mapping[str, Any] | None:
        return self.call("eth_getTransactionReceipt", [tx_hash])

    def block_number(self) -> int:
        return int(self.call("eth_blockNumber", []), 16)


def _rpc_tx(tx: Transaction) -> dict[str, str]:
    return {"from": tx.from_address, "to": tx.to, "data": tx.data, "value": hex(tx.value_wei)}


class NonceManager:
    def __init__(self, rpc: JsonRpc, wallet: str):
        self.rpc = rpc
        self.wallet = wallet
        self._next: int | None = None
        self._lock = threading.Lock()

    def reserve(self) -> int:
        with self._lock:
            if self._next is None:
                self._next = self.rpc.pending_nonce(self.wallet)
            nonce = self._next
            self._next += 1
            return nonce

    def refresh(self) -> None:
        with self._lock:
            self._next = None


def verify_keystore_permissions(path: Path, expected_uid: int | None = None) -> None:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise PermissionError("keystore must be a regular file")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise PermissionError("keystore must not grant group/other permissions")
    if expected_uid is not None and info.st_uid != expected_uid:
        raise PermissionError("keystore owner does not match executor uid")


class CastKeystoreSigner:
    """Signs EIP-1559 transactions without exposing secret key material."""

    def __init__(
        self,
        keystore: Path,
        password_file: Path,
        rpc_url: str,
        expected_uid: int | None = None,
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ):
        verify_keystore_permissions(keystore, expected_uid)
        verify_keystore_permissions(password_file, expected_uid)
        self.keystore = keystore
        self.password_file = password_file
        self.rpc_url = rpc_url
        self.run = run

    def sign(
        self, tx: Transaction, nonce: int, gas_limit: int, max_fee_per_gas: int, priority_fee: int
    ) -> str:
        command = [
            "cast", "mktx", tx.to, tx.data, "--value", str(tx.value_wei),
            "--nonce", str(nonce), "--gas-limit", str(gas_limit), "--gas-price",
            str(max_fee_per_gas), "--priority-gas-price", str(priority_fee), "--chain",
            str(BASE_CHAIN_ID), "--rpc-url", self.rpc_url, "--keystore", str(self.keystore),
            "--password-file", str(self.password_file),
        ]
        result = self.run(command, text=True, capture_output=True, check=True, env={"PATH": os.environ["PATH"]})
        raw = result.stdout.strip().splitlines()[-1]
        if not raw.startswith("0x"):
            raise RuntimeError("cast did not return a raw signed transaction")
        return raw


@dataclass(frozen=True)
class LiveUnlock:
    environment_enabled: bool
    startup_confirmed: bool

    @classmethod
    def from_process_start(cls, startup_confirmation: str, env: Mapping[str, str] | None = None) -> "LiveUnlock":
        source = os.environ if env is None else env
        return cls(
            environment_enabled=source.get("LIVE_TRADING", "false").lower() == "true",
            startup_confirmed=startup_confirmation == LIVE_CONFIRMATION,
        )

    @property
    def unlocked(self) -> bool:
        return self.environment_enabled and self.startup_confirmed


class Broadcaster:
    def __init__(self, rpc: JsonRpc, unlock: LiveUnlock):
        self.rpc = rpc
        self.unlock = unlock
        self.broadcast_count = 0

    def broadcast(self, raw_tx: str) -> str:
        self.require_unlocked()
        tx_hash = self.rpc.broadcast_raw(raw_tx)
        self.broadcast_count += 1
        return tx_hash

    def require_unlocked(self) -> None:
        if not self.unlock.unlocked:
            raise LiveTradingLocked("LIVE_TRADING plus startup confirmation are both required")


def wait_for_final_receipt(
    rpc: JsonRpc,
    tx_hash: str,
    confirmations: int = 3,
    timeout_seconds: float = 120,
    poll_seconds: float = 1,
) -> Mapping[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    first_hash: str | None = None
    while time.monotonic() < deadline:
        receipt = rpc.receipt(tx_hash)
        if receipt:
            if int(receipt.get("status", "0x0"), 16) != 1:
                reason = receipt.get("revertReason") or receipt.get("revertData")
                if isinstance(reason, str) and reason.startswith("0x"):
                    reason = decode_revert_data(reason)
                raise ReceiptFailed(f"transaction reverted: {reason or 'reason unavailable'}")
            block_hash = receipt.get("blockHash")
            if first_hash is None:
                first_hash = block_hash
            elif block_hash != first_hash:
                raise ReceiptFailed("receipt block changed during confirmation window (reorg)")
            included = int(receipt["blockNumber"], 16)
            if rpc.block_number() >= included + confirmations - 1:
                stable = rpc.receipt(tx_hash)
                if not stable or stable.get("blockHash") != first_hash:
                    raise ReceiptFailed("receipt disappeared or moved after confirmations")
                return stable
        time.sleep(poll_seconds)
    raise TimeoutError("receipt confirmation timed out")


class BaseM1Executor:
    def __init__(
        self,
        rpc: JsonRpc,
        signer: CastKeystoreSigner,
        broadcaster: Broadcaster,
        policy: ExecutionPolicy,
        ledger: Ledger,
        wallet: str,
    ):
        self.rpc = rpc
        self.signer = signer
        self.broadcaster = broadcaster
        self.policy = policy
        self.ledger = ledger
        self.wallet = _norm_address(wallet)
        self.validator = IntentValidator(policy, ledger)
        self.nonces = NonceManager(rpc, wallet)
        self.state = ExecutionState.NORMAL

    def trigger_kill_switch(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("kill-switch reason required")
        self.state = ExecutionState.EXIT_ONLY
        self.ledger.append(
            {"event": "kill_switch", "state": self.state.value, "reason": reason,
             "timestamp": datetime.now(timezone.utc).isoformat()}
        )

    def execute(self, intent: Intent, preflight: Preflight) -> Mapping[str, Any]:
        self.validator.validate(intent, self.state)
        preflight.require_all()
        tx = build_transaction(intent)
        if tx.from_address != self.wallet:
            raise PolicyRejected("intent wallet does not match signer wallet")
        # Estimate/simulate before signing; no send method is reached before both succeed.
        self.rpc.simulate(tx)
        gas_limit = (self.rpc.estimate_gas(tx) * 120 + 99) // 100
        max_fee, priority = self.rpc.eip1559_fees()
        # Do not even create a signed payload while the broadcast boundary is locked.
        self.broadcaster.require_unlocked()
        nonce = self.nonces.reserve()
        attempt_time = datetime.now(timezone.utc)
        # Reserve the idempotency key durably before signing.  Any ambiguous
        # failure thereafter is fail-closed and requires ledger reconciliation;
        # it can never silently create a second on-chain attempt.
        self.ledger.append(
            {
                "event": "execution_attempt",
                "status": "prepared",
                "utc_day": attempt_time.date().isoformat(),
                "timestamp": attempt_time.isoformat(),
                "action": intent.action.value,
                "notional_usd": intent.notional_usd,
                "strategy_decision_id": intent.strategy_decision_id,
                "risk_verdict_id": intent.risk_verdict_id,
                "idempotency_key": intent.idempotency_key,
                "nonce": nonce,
            }
        )
        tx_hash: str | None = None
        try:
            raw = self.signer.sign(tx, nonce, gas_limit, max_fee, priority)
            tx_hash = self.broadcaster.broadcast(raw)
            self.ledger.append(
                {
                    "event": "execution_attempt",
                    "status": "submitted",
                    "utc_day": attempt_time.date().isoformat(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "idempotency_key": intent.idempotency_key,
                    "nonce": nonce,
                    "tx_hash": tx_hash,
                    "notional_usd": intent.notional_usd,
                }
            )
            receipt = wait_for_final_receipt(self.rpc, tx_hash)
        except Exception as exc:
            self.nonces.refresh()
            self.ledger.append(
                {
                    "event": "execution_attempt",
                    "status": "failed_ambiguous" if tx_hash else "failed_before_submit",
                    "utc_day": attempt_time.date().isoformat(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "idempotency_key": intent.idempotency_key,
                    "nonce": nonce,
                    "tx_hash": tx_hash,
                    "error_type": type(exc).__name__,
                }
            )
            raise
        now = datetime.now(timezone.utc)
        row = {
            "event": "execution_result", "status": "confirmed", "tx_hash": tx_hash,
            "utc_day": now.date().isoformat(), "timestamp": now.isoformat(),
            "notional_usd": intent.notional_usd, "action": intent.action.value,
            "strategy_decision_id": intent.strategy_decision_id,
            "risk_verdict_id": intent.risk_verdict_id,
            "idempotency_key": intent.idempotency_key, "nonce": nonce,
            "gas_limit": gas_limit, "max_fee_per_gas": max_fee,
            "max_priority_fee_per_gas": priority, "receipt": dict(receipt),
        }
        self.ledger.append(row)
        return row


def dry_run(
    intent: Intent,
    preflight: Preflight,
    rpc: JsonRpc,
    policy: ExecutionPolicy,
    ledger: Ledger,
    state: ExecutionState = ExecutionState.NORMAL,
) -> Mapping[str, Any]:
    """Build, simulate, and price an intent, stopping before signing/broadcast."""
    IntentValidator(policy, ledger).validate(intent, state)
    preflight.require_all()
    tx = build_transaction(intent)
    simulation = rpc.simulate(tx)
    gas_limit = rpc.estimate_gas(tx)
    max_fee, priority = rpc.eip1559_fees()
    return {
        "intent": _jsonable_intent(intent), "transaction": asdict(tx),
        "simulation_result": simulation, "gas_estimate": gas_limit,
        "max_fee_per_gas": max_fee, "max_priority_fee_per_gas": priority,
        "estimated_max_gas_cost_wei": gas_limit * max_fee,
        "broadcast_count": 0, "signed": False, "raw_transaction": None,
    }


def _jsonable_intent(intent: Intent) -> dict[str, Any]:
    data = asdict(intent)
    data["protocol"] = intent.protocol.value
    data["action"] = intent.action.value
    return data
