"""Public API CoinGecko adapter (read-only HTTP, opt-in).

Fetches OHLC bars from CoinGecko's free /coins/{id}/ohlc endpoint. If the
network is blocked, returns an empty list and increments the error counter
on the AbortController; the runner decides whether to abort based on
ErrorRateMonitor.

Safety:
- Read-only (HTTP GET, no auth header required for public endpoint).
- No wallet / signer / tx / mutation.
- Caller must explicitly opt in (--use-public-api=1) for the runner to call
  this adapter; default is off.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..utils.retry import retry_with_backoff, classify_429, with_timeout, TimeoutError_


COINGECKO_BASE = "https://api.coingecko.com/api/v3"


@dataclass
class OhlcBar:
    ts: int  # unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    real_data: bool = True
    data_source: str = "coingecko_public"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "real_data": self.real_data,
            "data_source": self.data_source,
        }


class PublicApiCoinGeckoAdapter:
    """Read-only CoinGecko OHLC adapter.

    Methods return ``[]`` (and record error) on any failure. They never raise.
    """

    def __init__(self, *, abort_controller=None, timeout_s: float = 5.0):
        self.abort_controller = abort_controller
        self.timeout_s = timeout_s

    def fetch_ohlc(self, coin_id: str, vs_currency: str = "usd", days: int = 7) -> list[OhlcBar]:
        """Fetch OHLC bars for ``coin_id`` in ``vs_currency`` for the last ``days`` days.

        Returns empty list on any failure (network error, 4xx, 5xx, timeout).
        """
        if not coin_id:
            return []
        url = f"{COINGECKO_BASE}/coins/{coin_id}/ohlc?vs_currency={vs_currency}&days={days}"
        try:
            def _do():
                req = urllib.request.Request(url, method="GET")
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

        # CoinGecko returns a list of [ts_ms, o, h, l, c]
        bars: list[OhlcBar] = []
        for row in data:
            if not isinstance(row, list) or len(row) < 5:
                continue
            ts_ms, o, h, l, c = row[:5]
            try:
                bars.append(OhlcBar(
                    ts=int(ts_ms) // 1000,
                    open=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c),
                ))
            except (TypeError, ValueError):
                continue
        if self.abort_controller is not None:
            self.abort_controller.record_ok()
        return bars


def build_ohlc_rows(coin_id: str, bars: list[OhlcBar]) -> list[dict[str, Any]]:
    """Wrap OhlcBar list as a list of dicts for storage."""
    return [bar.to_dict() for bar in bars]


# Static check: ensure no banned token / wallet / signer / tx in this file.
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
        raise SystemExit(f"public_api_coingecko parse error: {exc}")
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
        raise SystemExit(f"public_api_coingecko tokenize error: {exc}")
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
            raise SystemExit(f"public_api_coingecko banned token: {token!r}")


_self_check()
