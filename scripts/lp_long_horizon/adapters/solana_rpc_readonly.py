"""Solana RPC read-only adapter.

Sends JSON-RPC ``getMultipleAccountsInfo`` requests to a Solana public RPC.
This is a **read-only** call: it never signs, never sends a transaction, and
never mutates chain state. If the network is blocked, returns an empty list
and records the error on the AbortController; the runner decides whether to
abort.

Safety:
- Read-only (HTTP POST with JSON-RPC body, no signing, no keypair).
- No wallet / signer / tx / mutation.
- Caller must explicitly opt in (--use-solana-rpc=1) for the runner to call
  this adapter; default is off.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..utils.retry import retry_with_backoff, classify_429, with_timeout, TimeoutError_


# Public Solana RPC endpoints. The runner picks one and may rotate on failure.
DEFAULT_RPC_ENDPOINTS = [
    "https://api.mainnet-beta.solana.com",
    "https://solana.publicnode.com",
    "https://api.mainnet.solana.com",
]


@dataclass
class AccountInfo:
    address: str
    data_len: int
    owner: str
    lamports: int
    executable: bool = False
    rent_epoch: int = 0
    real_data: bool = True
    data_source: str = "solana_rpc_public"

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "data_len": self.data_len,
            "owner": self.owner,
            "lamports": self.lamports,
            "executable": self.executable,
            "rent_epoch": self.rent_epoch,
            "real_data": self.real_data,
            "data_source": self.data_source,
        }


class SolanaRpcReadOnlyAdapter:
    """Read-only Solana JSON-RPC adapter for getMultipleAccountsInfo.

    Methods return ``[]`` (and record error) on any failure. They never raise.
    """

    def __init__(self, *, abort_controller=None, timeout_s: float = 5.0,
                 endpoint: str | None = None):
        self.abort_controller = abort_controller
        self.timeout_s = timeout_s
        self.endpoint = endpoint or DEFAULT_RPC_ENDPOINTS[0]

    def fetch_accounts(self, addresses: list[str]) -> list[AccountInfo]:
        """Fetch account info for ``addresses``. Read-only, no signing."""
        if not addresses:
            return []
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getMultipleAccountsInfo",
            "params": [addresses, {"encoding": "base64"}],
        }).encode("utf-8")
        try:
            def _do():
                req = urllib.request.Request(
                    self.endpoint, data=body, method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    raw = resp.read().decode("utf-8")
                return json.loads(raw)
            data = retry_with_backoff(
                _do,
                max_retries=2,
                base_delay_s=0.5,
                is_retryable=lambda e: classify_429(e) or isinstance(e, (TimeoutError_, urllib.error.URLError)),
            )
        except Exception as exc:  # noqa: BLE001
            if self.abort_controller is not None:
                if classify_429(exc):
                    self.abort_controller.record_429()
                else:
                    self.abort_controller.record_error()
            return []

        result = data.get("result") or []
        out: list[AccountInfo] = []
        for addr, info in zip(addresses, result):
            if not info:
                continue
            try:
                data_field = info.get("data") or ["", "base64"]
                data_b64 = data_field[0] if isinstance(data_field, list) else ""
                out.append(AccountInfo(
                    address=addr,
                    data_len=len(data_b64),
                    owner=str(info.get("owner", "")),
                    lamports=int(info.get("lamports", 0)),
                    executable=bool(info.get("executable", False)),
                    rent_epoch=int(info.get("rentEpoch", 0)),
                ))
            except (TypeError, ValueError):
                continue
        if self.abort_controller is not None:
            self.abort_controller.record_ok()
        return out


# Static self-check: same pattern as public_api_coingecko.
_BANNED_TOKENS_HERE = (
    "private_key", "mnemonic", "seed_phrase", "keypair.from_secret_key",
    "fromSecretKey", "SecretKey", "keystore.json", "encrypted_json",
    "new Signer(", "new Wallet(",
    "sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction",
    "signTransaction(", "signAndSendTransaction(",
    "add_liquidity(", "remove_liquidity(", "collect_fee(", "collect(",
    "mint(", "approve(", "burn(", "transfer(",
    "wormhole.core", "wormhole.bridge", "mayan.forward", "portal.bridge",
)


def _self_check() -> None:
    import ast
    import io as _io
    import tokenize
    from pathlib import Path
    src = Path(__file__).read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        raise SystemExit(f"solana_rpc_readonly parse error: {exc}")
    target = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "_BANNED_TOKENS_HERE":
                    target = node
                    break
            if target is not None:
                break
    if target is None:
        raise SystemExit("BANNED_TOKENS_HERE assignment missing")
    lines = src.splitlines(keepends=True)
    s_l, s_c = target.lineno - 1, target.col_offset
    e_l, e_c = target.end_lineno - 1, target.end_col_offset
    if e_l >= len(lines):
        e_l = len(lines) - 1
        e_c = len(lines[e_l])
    pre = "".join(lines[:s_l]) + lines[s_l][:s_c]
    post = lines[e_l][e_c:] + "".join(lines[e_l + 1:])
    blanked = " " * (len(src) - len(pre) - len(post))
    text_minus_tuple = pre + blanked + post
    lines2 = text_minus_tuple.splitlines(keepends=True)
    try:
        tokens = list(tokenize.generate_tokens(_io.StringIO(text_minus_tuple).readline))
    except tokenize.TokenizeError as exc:
        raise SystemExit(f"solana_rpc_readonly tokenize error: {exc}")
    for tok in tokens:
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            s_r, s_c2 = tok.start
            e_r, e_c2 = tok.end
            if s_r - 1 >= len(lines2):
                continue
            if e_r - 1 >= len(lines2):
                e_r = len(lines2)
            if s_r == e_r:
                line = lines2[s_r - 1]
                lines2[s_r - 1] = line[:s_c2] + " " * (e_c2 - s_c2) + line[e_c2:]
            else:
                first = lines2[s_r - 1]
                lines2[s_r - 1] = first[:s_c2]
                for mid in range(s_r, e_r - 1):
                    lines2[mid] = " " * len(lines2[mid])
                last = lines2[e_r - 1]
                lines2[e_r - 1] = " " * e_c2 + last[e_c2:]
    text_scannable = "".join(lines2)
    for token in _BANNED_TOKENS_HERE:
        if token in text_scannable:
            raise SystemExit(f"solana_rpc_readonly banned token: {token!r}")


_self_check()
