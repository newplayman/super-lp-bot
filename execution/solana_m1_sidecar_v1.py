"""Fail-closed Solana M1 single-position execution sidecar (TP-E / FIX-E3).

The module deliberately separates unsigned transaction construction and RPC
simulation from the encrypted-keystore signer and broadcast boundary.  A dry
run never instantiates a signer and the RPC method used by :func:`dry_run` is
``simulateTransaction`` only.  No raw private-key or mnemonic environment
variable is supported.
"""
from __future__ import annotations

import base64
import json
import math
import os
import stat
import threading
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol as TypingProtocol, Sequence


SOLANA_MAINNET_GENESIS_HASH = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
LIVE_CONFIRMATION = "CONFIRM_SOLANA_M1_LIVE_BROADCAST"

RAYDIUM_AMM_V4_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
RAYDIUM_CLMM_PROGRAM = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
ORCA_WHIRLPOOL_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
DEX_PROGRAMS = frozenset(
    {RAYDIUM_AMM_V4_PROGRAM, RAYDIUM_CLMM_PROGRAM, ORCA_WHIRLPOOL_PROGRAM}
)

SYSTEM_PROGRAM = "11111111111111111111111111111111"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
ASSOCIATED_TOKEN_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
COMPUTE_BUDGET_PROGRAM = "ComputeBudget111111111111111111111111111111"
SUPPORT_PROGRAMS = frozenset(
    {SYSTEM_PROGRAM, TOKEN_PROGRAM, TOKEN_2022_PROGRAM, ASSOCIATED_TOKEN_PROGRAM, COMPUTE_BUDGET_PROGRAM}
)

BPF_LOADERS = frozenset(
    {
        "NativeLoader1111111111111111111111111111111",
        "BPFLoader1111111111111111111111111111111111",
        "BPFLoader2111111111111111111111111111111111",
        "BPFLoaderUpgradeab1e11111111111111111111111",
        "LoaderV411111111111111111111111111111111111",
    }
)

FORBIDDEN_SECRET_ENV_KEYS = frozenset(
    {
        "PRIVATE_KEY",
        "SOLANA_PRIVATE_KEY",
        "SOLANA_SECRET_KEY",
        "SECRET_KEY",
        "MNEMONIC",
        "SEED_PHRASE",
    }
)

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {char: index for index, char in enumerate(_B58_ALPHABET)}


class LiveTradingLocked(RuntimeError):
    """Signing/broadcast was reached without both process-start gates."""


class PolicyRejected(RuntimeError):
    """Intent, program, token, or evidence failed the execution contract."""


class Action(str, Enum):
    OPEN = "open"
    INCREASE = "increase"
    DECREASE = "decrease"
    COLLECT = "collect"
    CLOSE = "close"
    SWAP = "swap"


class Protocol(str, Enum):
    RAYDIUM_AMM = "raydium_amm"
    RAYDIUM_CLMM = "raydium_clmm"
    ORCA_WHIRLPOOL = "orca_whirlpool"


class ExecutionState(str, Enum):
    NORMAL = "NORMAL"
    EXIT_ONLY = "EXIT_ONLY"


PROTOCOL_PROGRAM = {
    Protocol.RAYDIUM_AMM: RAYDIUM_AMM_V4_PROGRAM,
    Protocol.RAYDIUM_CLMM: RAYDIUM_CLMM_PROGRAM,
    Protocol.ORCA_WHIRLPOOL: ORCA_WHIRLPOOL_PROGRAM,
}
RISK_REDUCING_ACTIONS = frozenset({Action.DECREASE, Action.COLLECT, Action.CLOSE})


def reject_secret_environment(env: Mapping[str, str] | None = None) -> None:
    source = os.environ if env is None else env
    found = sorted(key for key in FORBIDDEN_SECRET_ENV_KEYS if source.get(key))
    if found:
        raise PolicyRejected("raw secret environment variables are forbidden: " + ",".join(found))


def _b58decode(value: str, expected_length: int = 32) -> bytes:
    if not isinstance(value, str) or not value:
        raise PolicyRejected("Solana public key/base58 value is required")
    number = 0
    try:
        for char in value:
            number = number * 58 + _B58_INDEX[char]
    except KeyError as exc:
        raise PolicyRejected(f"invalid base58 character in {value!r}") from exc
    raw = b"" if number == 0 else number.to_bytes((number.bit_length() + 7) // 8, "big")
    raw = b"\0" * (len(value) - len(value.lstrip("1"))) + raw
    if len(raw) != expected_length:
        raise PolicyRejected(f"base58 value must decode to {expected_length} bytes")
    return raw


def _shortvec(value: int) -> bytes:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PolicyRejected("shortvec value must be a non-negative integer")
    result = bytearray()
    while True:
        elem = value & 0x7F
        value >>= 7
        if value:
            elem |= 0x80
        result.append(elem)
        if not value:
            return bytes(result)


@dataclass(frozen=True)
class AccountMeta:
    pubkey: str
    is_signer: bool = False
    is_writable: bool = False

    def __post_init__(self) -> None:
        _b58decode(self.pubkey)


@dataclass(frozen=True)
class Instruction:
    program_id: str
    accounts: tuple[AccountMeta, ...]
    data: bytes
    semantic_action: Action | None = None

    def __post_init__(self) -> None:
        _b58decode(self.program_id)
        if not isinstance(self.data, bytes):
            raise PolicyRejected("instruction data must be bytes")


@dataclass(frozen=True)
class Intent:
    protocol: Protocol
    action: Action
    wallet: str
    pool: str
    token_mints: tuple[str, ...]
    strategy_decision_id: str
    risk_verdict_id: str
    idempotency_key: str
    notional_usd: float
    slippage_bps: int
    deadline_unix: int
    reduces_risk: bool = False
    # The stock-token leg currently held by the strategy.  This is a risk
    # verdict input, not a claim about the instruction: EXIT_ONLY verifies it
    # against the mints actually read from the swap's token accounts.
    position_mint: str | None = None

    def __post_init__(self) -> None:
        _b58decode(self.wallet)
        _b58decode(self.pool)
        for mint in self.token_mints:
            _b58decode(mint)
        if self.position_mint is not None:
            _b58decode(self.position_mint)
            if self.position_mint not in self.token_mints:
                raise PolicyRejected("position mint must be an allowlisted intent mint")


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
            field
            for field in (
                "simulate_ok",
                "quote_ok",
                "basis_ok",
                "rpc_health_ok",
                "wallet_balance_ok",
            )
            if not getattr(self, field)
        ]
        if failed:
            raise PolicyRejected("preflight failed: " + ",".join(failed))


@dataclass(frozen=True)
class ExecutionPolicy:
    single_tx_cap_usd: float = 50.0
    daily_cap_usd: float = 100.0
    max_slippage_bps: int = 200
    max_deadline_seconds: int = 300
    max_blockhash_horizon_blocks: int = 150
    allowed_pools: frozenset[str] = frozenset()
    allowed_mints: frozenset[str] = frozenset()
    allowed_support_programs: frozenset[str] = SUPPORT_PROGRAMS

    @property
    def allowed_programs(self) -> frozenset[str]:
        return DEX_PROGRAMS | self.allowed_support_programs


@dataclass(frozen=True)
class BuiltTransaction:
    transaction_base64: str
    message_base64: str
    program_ids: tuple[str, ...]
    recent_blockhash: str
    last_valid_block_height: int
    required_signatures: int


def _merge_account(
    table: dict[str, tuple[bool, bool]], pubkey: str, is_signer: bool, is_writable: bool
) -> None:
    old_signer, old_writable = table.get(pubkey, (False, False))
    table[pubkey] = (old_signer or is_signer, old_writable or is_writable)


def build_unsigned_legacy_transaction(
    *,
    fee_payer: str,
    recent_blockhash: str,
    last_valid_block_height: int,
    instructions: Sequence[Instruction],
) -> BuiltTransaction:
    """Compile a legacy transaction with zero signature placeholders.

    No private material is accepted.  The resulting payload is suitable for
    ``simulateTransaction`` with ``sigVerify=false`` and must never be treated
    as a signed transaction.
    """
    _b58decode(fee_payer)
    blockhash = _b58decode(recent_blockhash)
    if not instructions:
        raise PolicyRejected("at least one instruction is required")
    accounts: dict[str, tuple[bool, bool]] = {fee_payer: (True, True)}
    for instruction in instructions:
        _merge_account(accounts, instruction.program_id, False, False)
        for meta in instruction.accounts:
            _merge_account(accounts, meta.pubkey, meta.is_signer, meta.is_writable)

    def group(item: tuple[str, tuple[bool, bool]]) -> tuple[int, str]:
        pubkey, (signer, writable) = item
        if pubkey == fee_payer:
            return (-1, pubkey)
        return ((0 if signer and writable else 1 if signer else 2 if writable else 3), pubkey)

    ordered = [pubkey for pubkey, _flags in sorted(accounts.items(), key=group)]
    index = {pubkey: position for position, pubkey in enumerate(ordered)}
    if len(ordered) > 256:
        raise PolicyRejected("legacy transaction account index overflow")
    required = sum(accounts[key][0] for key in ordered)
    readonly_signed = sum(signer and not writable for signer, writable in accounts.values())
    readonly_unsigned = sum(not signer and not writable for signer, writable in accounts.values())
    message = bytearray((required, readonly_signed, readonly_unsigned))
    message += _shortvec(len(ordered))
    message += b"".join(_b58decode(key) for key in ordered)
    message += blockhash
    message += _shortvec(len(instructions))
    for instruction in instructions:
        account_indexes = bytes(index[meta.pubkey] for meta in instruction.accounts)
        message += bytes((index[instruction.program_id],))
        message += _shortvec(len(account_indexes)) + account_indexes
        message += _shortvec(len(instruction.data)) + instruction.data
    transaction = _shortvec(required) + (b"\0" * (64 * required)) + bytes(message)
    return BuiltTransaction(
        transaction_base64=base64.b64encode(transaction).decode("ascii"),
        message_base64=base64.b64encode(message).decode("ascii"),
        program_ids=tuple(dict.fromkeys(item.program_id for item in instructions)),
        recent_blockhash=recent_blockhash,
        last_valid_block_height=int(last_valid_block_height),
        required_signatures=required,
    )


class SolanaRpc:
    """Small JSON-RPC client; dry-run calls have no send path."""

    def __init__(self, url: str, timeout_seconds: float = 15.0):
        self.url = url
        self.timeout_seconds = timeout_seconds
        self._request_id = 0

    def call(self, method: str, params: Sequence[Any]) -> Any:
        self._request_id += 1
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": list(params)}
        ).encode()
        request = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "lpbot-solana-m1-sidecar/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read())
        if body.get("error") is not None:
            raise RuntimeError(json.dumps(body["error"], sort_keys=True))
        if "result" not in body:
            raise RuntimeError("Solana RPC response is missing result")
        return body["result"]

    def account_info(self, address: str) -> Mapping[str, Any]:
        return self.call("getAccountInfo", [address, {"encoding": "jsonParsed", "commitment": "confirmed"}])

    def simulate(self, tx: BuiltTransaction) -> Mapping[str, Any]:
        return self.call(
            "simulateTransaction",
            [
                tx.transaction_base64,
                {
                    "encoding": "base64",
                    "sigVerify": False,
                    "replaceRecentBlockhash": False,
                    "commitment": "confirmed",
                },
            ],
        )

    def send_transaction(self, signed_transaction_base64: str) -> str:
        result = self.call(
            "sendTransaction",
            [
                signed_transaction_base64,
                {"encoding": "base64", "skipPreflight": False, "preflightCommitment": "confirmed"},
            ],
        )
        if not isinstance(result, str) or not result:
            raise RuntimeError("sendTransaction returned no signature")
        return result

    def signature_status(self, signature: str) -> Mapping[str, Any] | None:
        result = self.call(
            "getSignatureStatuses", [[signature], {"searchTransactionHistory": True}]
        )
        values = result.get("value") if isinstance(result, Mapping) else None
        if not isinstance(values, list) or len(values) != 1:
            raise RuntimeError("getSignatureStatuses returned malformed result")
        value = values[0]
        return value if isinstance(value, Mapping) else None


@dataclass(frozen=True)
class ProgramEvidence:
    program_id: str
    executable: bool
    owner: str
    slot: int


def verify_program_on_chain(rpc: Any, program_id: str, allowed: frozenset[str]) -> ProgramEvidence:
    if program_id not in allowed:
        raise PolicyRejected(f"program id is not allowlisted: {program_id}")
    response = rpc.account_info(program_id)
    value = response.get("value") if isinstance(response, Mapping) else None
    if not isinstance(value, Mapping):
        raise PolicyRejected(f"program account is missing: {program_id}")
    owner = value.get("owner")
    if value.get("executable") is not True or owner not in BPF_LOADERS:
        raise PolicyRejected(f"program is not an executable loader-owned account: {program_id}")
    context = response.get("context") or {}
    slot = context.get("slot")
    if not isinstance(slot, int) or isinstance(slot, bool) or slot <= 0:
        raise PolicyRejected("program verification slot is missing")
    return ProgramEvidence(program_id, True, owner, slot)


def verify_transaction_programs(
    rpc: Any, intent: Intent, instructions: Sequence[Instruction], policy: ExecutionPolicy
) -> list[ProgramEvidence]:
    expected = PROTOCOL_PROGRAM[intent.protocol]
    dex_instructions = [item for item in instructions if item.program_id in DEX_PROGRAMS]
    if not dex_instructions or any(item.program_id != expected for item in dex_instructions):
        raise PolicyRejected("protocol transaction must invoke exactly its official DEX program")
    if any(item.semantic_action is not intent.action for item in dex_instructions):
        raise PolicyRejected("DEX instruction action does not match the intent")
    programs = tuple(dict.fromkeys(item.program_id for item in instructions))
    return [verify_program_on_chain(rpc, program_id, policy.allowed_programs) for program_id in programs]


def _token_account_mint(rpc: Any, address: str) -> str:
    """Read a token-account mint from chain, never from plan metadata."""
    response = rpc.account_info(address)
    value = response.get("value") if isinstance(response, Mapping) else None
    data = value.get("data") if isinstance(value, Mapping) else None
    parsed = data.get("parsed") if isinstance(data, Mapping) else None
    info = parsed.get("info") if isinstance(parsed, Mapping) else None
    mint = info.get("mint") if isinstance(info, Mapping) and parsed.get("type") == "account" else None
    if not isinstance(mint, str):
        raise PolicyRejected("swap token account mint is unavailable from chain")
    _b58decode(mint)
    return mint


def parse_swap_token_direction(
    rpc: Any, intent: Intent, instructions: Sequence[Instruction]
) -> tuple[str, str]:
    """Parse the actual input/output mint direction for an EXIT_ONLY swap.

    Raydium AMM v4's public swap layout places user source and destination
    token accounts at indexes 15 and 16.  CLMM/Whirlpool layouts are not
    accepted here until their instruction discriminators/layouts are decoded;
    guessing a direction would weaken EXIT_ONLY, so those swaps fail closed.
    """
    swaps = [item for item in instructions if item.program_id in DEX_PROGRAMS and item.semantic_action is Action.SWAP]
    if len(swaps) != 1:
        raise PolicyRejected("EXIT_ONLY requires exactly one parsable swap instruction")
    swap = swaps[0]
    if swap.program_id != RAYDIUM_AMM_V4_PROGRAM or len(swap.accounts) < 17:
        raise PolicyRejected("EXIT_ONLY swap direction is unsupported and fail-closed")
    return _token_account_mint(rpc, swap.accounts[15].pubkey), _token_account_mint(rpc, swap.accounts[16].pubkey)


def verify_exit_only_swap_direction(
    rpc: Any, intent: Intent, instructions: Sequence[Instruction], state: ExecutionState
) -> None:
    if state is not ExecutionState.EXIT_ONLY or intent.action is not Action.SWAP:
        return
    if intent.position_mint is None:
        raise PolicyRejected("EXIT_ONLY swap requires a position mint for direction verification")
    token_in, token_out = parse_swap_token_direction(rpc, intent, instructions)
    if token_in != intent.position_mint or token_out == intent.position_mint:
        raise PolicyRejected("EXIT_ONLY swap direction increases or does not reduce position exposure")


@dataclass(frozen=True)
class MintSemantics:
    mint: str
    token_program: str
    decimals: int
    scaled_ui_multiplier: Decimal
    multiplier_effective_at: int | None
    extensions: tuple[str, ...]

    def accounting_amount(self, raw_amount: int) -> Decimal:
        if not isinstance(raw_amount, int) or isinstance(raw_amount, bool) or raw_amount < 0:
            raise PolicyRejected("raw token amount must be a non-negative integer")
        return Decimal(raw_amount) / (Decimal(10) ** self.decimals)

    def ui_amount(self, raw_amount: int) -> Decimal:
        return self.accounting_amount(raw_amount) * self.scaled_ui_multiplier

    def raw_from_ui_exact(self, ui_amount: Decimal | str) -> int:
        try:
            raw = Decimal(str(ui_amount)) * (Decimal(10) ** self.decimals) / self.scaled_ui_multiplier
        except (InvalidOperation, ZeroDivisionError) as exc:
            raise PolicyRejected("invalid UI token amount") from exc
        integral = raw.to_integral_value()
        if raw != integral or integral < 0:
            raise PolicyRejected("UI amount cannot be represented exactly in raw units")
        return int(integral)

    def notional(self, raw_amount: int, price: Decimal | str, price_semantics: str) -> Decimal:
        price_value = Decimal(str(price))
        if not price_value.is_finite() or price_value <= 0:
            raise PolicyRejected("token price must be finite and positive")
        if price_semantics == "per_ui_unit":
            return self.ui_amount(raw_amount) * price_value
        if price_semantics == "per_accounting_unit":
            return self.accounting_amount(raw_amount) * price_value
        raise PolicyRejected("price semantics must state per_ui_unit or per_accounting_unit")


def _positive_decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PolicyRejected(f"invalid {label}") from exc
    if not result.is_finite() or result <= 0:
        raise PolicyRejected(f"invalid {label}")
    return result


def read_mint_semantics(rpc: Any, mint: str, now_unix: int | None = None) -> MintSemantics:
    _b58decode(mint)
    response = rpc.account_info(mint)
    value = response.get("value") if isinstance(response, Mapping) else None
    if not isinstance(value, Mapping):
        raise PolicyRejected("mint account is missing")
    token_program = value.get("owner")
    if token_program not in {TOKEN_PROGRAM, TOKEN_2022_PROGRAM}:
        raise PolicyRejected("mint owner is not SPL Token or Token-2022")
    data = value.get("data")
    parsed = data.get("parsed") if isinstance(data, Mapping) else None
    info = parsed.get("info") if isinstance(parsed, Mapping) else None
    if not isinstance(info, Mapping) or parsed.get("type") != "mint":
        raise PolicyRejected("mint jsonParsed payload is missing")
    decimals = info.get("decimals")
    if not isinstance(decimals, int) or isinstance(decimals, bool) or not 0 <= decimals <= 18:
        raise PolicyRejected("mint decimals are invalid")
    extensions_value = info.get("extensions") or []
    if not isinstance(extensions_value, list):
        raise PolicyRejected("Token-2022 extensions must be a list")
    names: list[str] = []
    multiplier = Decimal(1)
    effective: int | None = None
    now_value = int(time.time()) if now_unix is None else int(now_unix)
    for extension in extensions_value:
        if not isinstance(extension, Mapping):
            raise PolicyRejected("malformed Token-2022 extension")
        name = extension.get("extension") or extension.get("extensionType")
        if not isinstance(name, str) or not name:
            raise PolicyRejected("Token-2022 extension name is missing")
        names.append(name)
        if name in {"scaledUiAmountConfig", "scaledUiAmount"}:
            state = extension.get("state") if isinstance(extension.get("state"), Mapping) else extension
            multiplier = _positive_decimal(
                state.get("multiplier", state.get("currentMultiplier")), "scaled UI multiplier"
            )
            future = state.get("newMultiplier")
            activation = state.get("newMultiplierEffectiveTimestamp", state.get("newMultiplierEffectiveTime"))
            if future is not None or activation is not None:
                if future is None or activation is None:
                    raise PolicyRejected("scaled UI future multiplier activation is incomplete")
                try:
                    activation_int = int(activation)
                except (TypeError, ValueError) as exc:
                    raise PolicyRejected("scaled UI multiplier activation is invalid") from exc
                if activation_int <= now_value:
                    multiplier = _positive_decimal(future, "activated scaled UI multiplier")
                    effective = activation_int
    if token_program == TOKEN_PROGRAM and names:
        raise PolicyRejected("legacy SPL Token mint unexpectedly contains extensions")
    return MintSemantics(mint, token_program, decimals, multiplier, effective, tuple(names))


class Ledger:
    """Append-only JSONL ledger with atomic idempotency/daily-cap reservation."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _rows_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def _append_unlocked(self, row: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(row), sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def append(self, row: Mapping[str, Any]) -> None:
        with self._lock:
            self._append_unlocked(row)

    def contains(self, key: str) -> bool:
        with self._lock:
            return any(row.get("idempotency_key") == key for row in self._rows_unlocked())

    def reserve(self, intent: Intent, daily_cap_usd: float, now_unix: float) -> None:
        day = datetime.fromtimestamp(now_unix, tz=timezone.utc).date().isoformat()
        with self._lock:
            rows = self._rows_unlocked()
            if any(row.get("idempotency_key") == intent.idempotency_key for row in rows):
                raise PolicyRejected("duplicate idempotency key")
            # One execution is represented by multiple append-only lifecycle
            # rows.  Count only the latest state per key so prepared ->
            # submitted -> confirmed is never charged three times.
            latest_by_key: dict[str, Mapping[str, Any]] = {}
            for row in rows:
                key = row.get("idempotency_key")
                if key and row.get("utc_day") == day and row.get("status"):
                    latest_by_key[str(key)] = row
            committed = sum(
                float(row.get("notional_usd", 0))
                for row in latest_by_key.values()
                if row.get("status") in {"prepared", "submitted", "confirmed", "failed_ambiguous"}
            )
            if committed + intent.notional_usd > daily_cap_usd:
                raise PolicyRejected("daily notional cap exceeded")
            self._append_unlocked(
                {
                    "event": "execution_attempt",
                    "status": "prepared",
                    "utc_day": day,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": intent.action.value,
                    "notional_usd": intent.notional_usd,
                    "strategy_decision_id": intent.strategy_decision_id,
                    "risk_verdict_id": intent.risk_verdict_id,
                    "idempotency_key": intent.idempotency_key,
                }
            )


class IntentValidator:
    def __init__(self, policy: ExecutionPolicy, ledger: Ledger, now: Callable[[], float] = time.time):
        self.policy = policy
        self.ledger = ledger
        self.now = now

    def validate(self, intent: Intent, state: ExecutionState, current_block_height: int, last_valid: int) -> None:
        if state is ExecutionState.EXIT_ONLY:
            reducing = intent.action in RISK_REDUCING_ACTIONS or (
                intent.action is Action.SWAP and intent.reduces_risk
            )
            if not reducing:
                raise PolicyRejected("EXIT_ONLY permits risk-reducing actions only")
        if intent.action is Action.SWAP and intent.reduces_risk is False and state is ExecutionState.EXIT_ONLY:
            raise PolicyRejected("EXIT_ONLY swap must explicitly reduce risk")
        if PROTOCOL_PROGRAM[intent.protocol] not in DEX_PROGRAMS:
            raise PolicyRejected("protocol program is not allowlisted")
        if intent.pool not in self.policy.allowed_pools:
            raise PolicyRejected("pool is not allowlisted")
        if not intent.token_mints or any(mint not in self.policy.allowed_mints for mint in intent.token_mints):
            raise PolicyRejected("token mint is not allowlisted")
        if not all((intent.strategy_decision_id, intent.risk_verdict_id, intent.idempotency_key)):
            raise PolicyRejected("decision, verdict, and idempotency identifiers are required")
        if self.ledger.contains(intent.idempotency_key):
            raise PolicyRejected("duplicate idempotency key")
        if not math.isfinite(intent.notional_usd) or not 0 <= intent.notional_usd <= self.policy.single_tx_cap_usd:
            raise PolicyRejected("single transaction notional cap exceeded")
        if not 0 <= intent.slippage_bps <= self.policy.max_slippage_bps:
            raise PolicyRejected("slippage hard limit exceeded")
        now = int(self.now())
        if intent.deadline_unix <= now or intent.deadline_unix > now + self.policy.max_deadline_seconds:
            raise PolicyRejected("deadline is expired or too far in the future")
        remaining = last_valid - current_block_height
        if remaining <= 0 or remaining > self.policy.max_blockhash_horizon_blocks:
            raise PolicyRejected("blockhash validity window is expired or unbounded")


@dataclass(frozen=True)
class LiveUnlock:
    environment_enabled: bool
    startup_confirmed: bool

    @classmethod
    def from_process_start(
        cls, startup_confirmation: str, env: Mapping[str, str] | None = None
    ) -> "LiveUnlock":
        source = os.environ if env is None else env
        reject_secret_environment(source)
        return cls(
            source.get("LIVE_TRADING", "false").lower() == "true",
            startup_confirmation == LIVE_CONFIRMATION,
        )

    @property
    def unlocked(self) -> bool:
        return self.environment_enabled and self.startup_confirmed


class BroadcastTransport(TypingProtocol):
    def send_transaction(self, signed_transaction_base64: str) -> str: ...


class Broadcaster:
    def __init__(self, transport: BroadcastTransport, unlock: LiveUnlock):
        self.transport = transport
        self.unlock = unlock
        self.broadcast_count = 0

    def require_unlocked(self) -> None:
        if not self.unlock.unlocked:
            raise LiveTradingLocked("LIVE_TRADING plus startup confirmation are both required")

    def broadcast(self, signed_transaction_base64: str) -> str:
        self.require_unlocked()
        signature = self.transport.send_transaction(signed_transaction_base64)
        self.broadcast_count += 1
        return signature


def wait_for_final_signature(
    rpc: Any,
    signature: str,
    *,
    timeout_seconds: float = 120.0,
    poll_seconds: float = 1.0,
) -> Mapping[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = rpc.signature_status(signature)
        if status is not None:
            if status.get("err") is not None:
                raise RuntimeError("Solana transaction failed: " + json.dumps(status["err"], sort_keys=True))
            if status.get("confirmationStatus") == "finalized":
                return status
        time.sleep(poll_seconds)
    raise TimeoutError("Solana transaction finalization timed out")


def verify_keystore_permissions(path: Path, expected_uid: int) -> None:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise PermissionError(f"secret path is not a regular file: {path}")
    if info.st_uid != expected_uid:
        raise PermissionError(f"secret path owner mismatch: {path}")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise PermissionError(f"secret path must be mode 0600: {path}")


class EncryptedKeystoreSigner:
    """External signer boundary; the sidecar never decrypts secret bytes itself."""

    def __init__(
        self,
        keystore: Path,
        password_file: Path,
        expected_uid: int,
        run: Callable[..., Any],
        signer_command: str = "lpbot-solana-keystore-sign",
    ):
        verify_keystore_permissions(keystore, expected_uid)
        verify_keystore_permissions(password_file, expected_uid)
        envelope = json.loads(keystore.read_text(encoding="utf-8"))
        if envelope.get("version") != 1 or not isinstance(envelope.get("crypto"), Mapping):
            raise PolicyRejected("encrypted keystore envelope is invalid")
        crypto = envelope["crypto"]
        if not all(crypto.get(field) for field in ("cipher", "ciphertext", "kdf", "mac")):
            raise PolicyRejected("encrypted keystore envelope is incomplete")
        self.keystore = keystore
        self.password_file = password_file
        self.run = run
        self.signer_command = signer_command

    def sign(self, unsigned_transaction_base64: str) -> str:
        result = self.run(
            [
                self.signer_command,
                "--keystore",
                str(self.keystore),
                "--password-file",
                str(self.password_file),
            ],
            input=unsigned_transaction_base64,
            text=True,
            capture_output=True,
            check=True,
            env={"PATH": os.environ.get("PATH", "")},
        )
        signed = result.stdout.strip()
        if not signed:
            raise RuntimeError("external signer returned no signed transaction")
        return signed


def _jsonable_intent(intent: Intent) -> dict[str, Any]:
    result = asdict(intent)
    result["protocol"] = intent.protocol.value
    result["action"] = intent.action.value
    return result


def dry_run(
    *,
    intent: Intent,
    preflight: Preflight,
    instructions: Sequence[Instruction],
    recent_blockhash: str,
    last_valid_block_height: int,
    current_block_height: int,
    rpc: Any,
    policy: ExecutionPolicy,
    ledger: Ledger,
    state: ExecutionState = ExecutionState.NORMAL,
    now: Callable[[], float] = time.time,
) -> Mapping[str, Any]:
    """Validate, build, verify and simulate without loading a key or broadcasting."""
    validator = IntentValidator(policy, ledger, now=now)
    validator.validate(intent, state, current_block_height, last_valid_block_height)
    preflight.require_all()
    program_evidence = verify_transaction_programs(rpc, intent, instructions, policy)
    verify_exit_only_swap_direction(rpc, intent, instructions, state)
    built = build_unsigned_legacy_transaction(
        fee_payer=intent.wallet,
        recent_blockhash=recent_blockhash,
        last_valid_block_height=last_valid_block_height,
        instructions=instructions,
    )
    simulation = rpc.simulate(built)
    value = simulation.get("value") if isinstance(simulation, Mapping) else None
    if not isinstance(value, Mapping) or value.get("err") is not None:
        raise PolicyRejected("simulateTransaction rejected the unsigned transaction")
    return {
        "stage": "E3_SOLANA_DRY_RUN",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "network": "solana_mainnet",
        "intent": _jsonable_intent(intent),
        "transaction": {
            "encoding": "base64",
            "unsigned": True,
            "required_signature_placeholders": built.required_signatures,
            "message_base64": built.message_base64,
            "recent_blockhash": built.recent_blockhash,
            "last_valid_block_height": built.last_valid_block_height,
            "program_ids": list(built.program_ids),
        },
        "program_verification": [asdict(item) for item in program_evidence],
        "preflight": {
            "simulate": preflight.simulate_ok,
            "quote": preflight.quote_ok,
            "basis": preflight.basis_ok,
            "rpc_health": preflight.rpc_health_ok,
            "wallet_balance": preflight.wallet_balance_ok,
        },
        "preflight_all_pass": True,
        "simulation_result": simulation,
        "broadcast_count": 0,
        "signed": False,
        "raw_transaction": None,
        "transaction_signatures": [],
        "keystore_loaded": False,
    }


class SolanaM1Sidecar:
    """Live-capable boundary, still locked unless the commander opens both gates."""

    def __init__(
        self,
        *,
        rpc: Any,
        signer: EncryptedKeystoreSigner,
        broadcaster: Broadcaster,
        policy: ExecutionPolicy,
        ledger: Ledger,
        now: Callable[[], float] = time.time,
    ):
        reject_secret_environment()
        self.rpc = rpc
        self.signer = signer
        self.broadcaster = broadcaster
        self.policy = policy
        self.ledger = ledger
        self.now = now
        self.state = ExecutionState.NORMAL

    def trigger_kill_switch(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("kill-switch reason is required")
        self.state = ExecutionState.EXIT_ONLY
        self.ledger.append(
            {
                "event": "kill_switch",
                "state": self.state.value,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def execute(
        self,
        *,
        intent: Intent,
        preflight: Preflight,
        instructions: Sequence[Instruction],
        recent_blockhash: str,
        last_valid_block_height: int,
        current_block_height: int,
    ) -> Mapping[str, Any]:
        validator = IntentValidator(self.policy, self.ledger, now=self.now)
        validator.validate(intent, self.state, current_block_height, last_valid_block_height)
        preflight.require_all()
        verify_transaction_programs(self.rpc, intent, instructions, self.policy)
        verify_exit_only_swap_direction(self.rpc, intent, instructions, self.state)
        built = build_unsigned_legacy_transaction(
            fee_payer=intent.wallet,
            recent_blockhash=recent_blockhash,
            last_valid_block_height=last_valid_block_height,
            instructions=instructions,
        )
        simulation = self.rpc.simulate(built)
        value = simulation.get("value") if isinstance(simulation, Mapping) else None
        if not isinstance(value, Mapping) or value.get("err") is not None:
            raise PolicyRejected("simulateTransaction failed before signing")
        # The commander gate is checked before ledger reservation and, crucially,
        # before the external signer is invoked.
        self.broadcaster.require_unlocked()
        self.ledger.reserve(intent, self.policy.daily_cap_usd, self.now())
        signature: str | None = None
        try:
            signed = self.signer.sign(built.transaction_base64)
            signature = self.broadcaster.broadcast(signed)
            self.ledger.append(
                {
                    "event": "execution_attempt",
                    "status": "submitted",
                    "utc_day": datetime.now(timezone.utc).date().isoformat(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "notional_usd": intent.notional_usd,
                    "idempotency_key": intent.idempotency_key,
                    "signature": signature,
                }
            )
            confirmation = wait_for_final_signature(self.rpc, signature)
            row = {
                "event": "execution_result",
                "status": "confirmed",
                "utc_day": datetime.now(timezone.utc).date().isoformat(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": intent.action.value,
                "notional_usd": intent.notional_usd,
                "strategy_decision_id": intent.strategy_decision_id,
                "risk_verdict_id": intent.risk_verdict_id,
                "idempotency_key": intent.idempotency_key,
                "signature": signature,
                "confirmation": dict(confirmation),
            }
            self.ledger.append(row)
            return row
        except Exception as exc:
            self.ledger.append(
                {
                    "event": "execution_result",
                    "status": "failed_ambiguous" if signature else "failed_before_submit",
                    "utc_day": datetime.now(timezone.utc).date().isoformat(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "idempotency_key": intent.idempotency_key,
                    "signature": signature,
                    "notional_usd": intent.notional_usd,
                    "error_type": type(exc).__name__,
                }
            )
            raise
