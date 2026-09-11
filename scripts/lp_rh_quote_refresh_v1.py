#!/usr/bin/env python3
"""RH quote refresh: observe USDG/USD exchange rate and refresh pool_meta quote_usd_per_token1.

Fail-close design: the module performs no network I/O; rates arrive through an
injected fetch_fn. When inputs are missing, invalid, non-positive, or outside
the sanity range (0.1, 10.0), status is UNAVAILABLE:<reason> and apply_to_pool_meta
writes nothing. All financial arithmetic uses Decimal.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=global-dollar&vs_currencies=usd"
COINGECKO_ID = "global-dollar"
COINGECKO_VS = "usd"
SOURCE_DESC = "coingecko:global-dollar/usd (simple/price, free tier, no key)"
TTL_SECS = 86400
ABSURD_MIN = Decimal("0.1")
ABSURD_MAX = Decimal("10.0")
DEFAULT_TIMEOUT_SECS = 10.0
DEFAULT_USER_AGENT = "curl/8.5.0"


def _utc_now_rfc3339(now: Optional[datetime] = None) -> str:
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_quote_refresh(raw_payload: Any, *, now: Optional[datetime] = None) -> dict:
    """Pure function: parse CoinGecko simple/price payload and compute quote refresh.

    Returns {"status": "OK"|"UNAVAILABLE:<reason>", "quote": dict|None, ...}.
    Fail-close: returns UNAVAILABLE without quote on any invalid input or absurd value.
    """
    if raw_payload is None:
        return {"status": "UNAVAILABLE:missing_payload", "quote": None, "value": None, "depeg_pct": None, "raw_fragment": None}

    if isinstance(raw_payload, (str, bytes)):
        try:
            data = json.loads(raw_payload)
        except Exception:
            return {"status": "UNAVAILABLE:invalid_json", "quote": None, "value": None, "depeg_pct": None, "raw_fragment": None}
    elif isinstance(raw_payload, dict):
        data = raw_payload
    else:
        return {"status": "UNAVAILABLE:invalid_payload", "quote": None, "value": None, "depeg_pct": None, "raw_fragment": None}

    if not isinstance(data, dict):
        return {"status": "UNAVAILABLE:invalid_payload", "quote": None, "value": None, "depeg_pct": None, "raw_fragment": None}

    gd = data.get(COINGECKO_ID)
    if not isinstance(gd, dict) or COINGECKO_VS not in gd:
        return {"status": "UNAVAILABLE:missing_target_field", "quote": None, "value": None, "depeg_pct": None, "raw_fragment": gd if isinstance(gd, dict) else None}

    raw_val = gd[COINGECKO_VS]
    raw_fragment = {COINGECKO_ID: {COINGECKO_VS: raw_val}}

    if raw_val is None:
        return {"status": "UNAVAILABLE:unparseable_value", "quote": None, "value": None, "depeg_pct": None, "raw_fragment": raw_fragment}

    try:
        val = Decimal(str(raw_val))
    except (InvalidOperation, TypeError, ValueError):
        return {"status": "UNAVAILABLE:unparseable_value", "quote": None, "value": None, "depeg_pct": None, "raw_fragment": raw_fragment}

    if not val.is_finite() or val <= Decimal(0):
        return {"status": "UNAVAILABLE:non_positive_value", "quote": None, "value": None, "depeg_pct": None, "raw_fragment": raw_fragment}

    if not (ABSURD_MIN < val < ABSURD_MAX):
        return {"status": "UNAVAILABLE:absurd_value", "quote": None, "value": None, "depeg_pct": None, "raw_fragment": raw_fragment}

    depeg = (val - Decimal("1")) * Decimal("100")
    depeg_str = str(depeg)
    observed_at = _utc_now_rfc3339(now)

    quote = {
        "value": str(val),
        "source": SOURCE_DESC,
        "observed_at": observed_at,
        "ttl_secs": TTL_SECS,
        "note": f"USDG = Global Dollar. Observed depeg {depeg:.4f}%. TTL 24h; on expiry the runner reports QUOTE_EVIDENCE_EXPIRED and produces no NAV rather than reusing a stale rate.",
        "depeg_pct": depeg_str,
        "raw_fragment": raw_fragment,
    }

    return {
        "status": "OK",
        "quote": quote,
        "value": str(val),
        "depeg_pct": depeg_str,
        "raw_fragment": raw_fragment,
    }


def apply_to_pool_meta(path, refresh: dict, *, backup: bool = True) -> dict:
    """Atomically write the refreshed quote_usd_per_token1 into pool_meta.

    Writes nothing unless status is 'OK' and quote is a dict. The write is atomic:
    a temp file in the same directory is written and replaced. All other fields
    are preserved byte-for-byte in formatting.
    """
    path = Path(path)
    status = refresh.get("status")
    quote = refresh.get("quote")
    if status != "OK" or not isinstance(quote, dict):
        return {
            "written": False,
            "reason": f"status={status!r} quote={'present' if isinstance(quote, dict) else None}",
        }

    orig_text = path.read_text()
    has_trailing_newline = orig_text.endswith("\n")
    meta = json.loads(orig_text)

    backup_path = None
    if backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = path.with_name(f"{path.name}.bak-{ts}")
        shutil.copy2(path, backup_path)

    meta["quote_usd_per_token1"] = quote

    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".pool_meta.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(meta, fh, indent=2)
            if has_trailing_newline:
                fh.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    return {
        "written": True,
        "path": str(path),
        "backup": str(backup_path) if backup_path else None,
        "quote": quote,
    }


def _default_fetch(url: str, timeout: float = DEFAULT_TIMEOUT_SECS, user_agent: str = DEFAULT_USER_AGENT) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP status {resp.status}")
        return json.loads(resp.read().decode("utf-8"))


def _invoke_fetch(fn: Callable, url: str, timeout: float) -> tuple[Any, Optional[str]]:
    try:
        try:
            return fn(url, timeout=timeout), None
        except TypeError:
            try:
                return fn(url), None
            except TypeError:
                return fn(), None
    except Exception as exc:
        return None, str(exc)


def main(argv=None, *, fetch_fn: Optional[Callable] = None, now: Optional[datetime] = None) -> int:
    ap = argparse.ArgumentParser(description="Refresh pool_meta quote_usd_per_token1 from CoinGecko (dry-run unless --apply).")
    ap.add_argument("--pool-meta", default="reports/lp_rh/pool_meta.json")
    ap.add_argument("--apply", action="store_true", default=False)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--timeout-secs", type=float, default=DEFAULT_TIMEOUT_SECS)
    args = ap.parse_args(argv)

    if fetch_fn is None:
        fetch_fn = lambda: _default_fetch(COINGECKO_URL, timeout=args.timeout_secs)

    raw_payload, fetch_err = _invoke_fetch(fetch_fn, COINGECKO_URL, args.timeout_secs)
    if fetch_err is not None:
        refresh = {
            "status": f"UNAVAILABLE:request_failed: {fetch_err}",
            "quote": None,
            "value": None,
            "depeg_pct": None,
            "raw_fragment": None,
        }
    else:
        refresh = build_quote_refresh(raw_payload, now=now)

    if args.apply:
        result = apply_to_pool_meta(args.pool_meta, refresh)
        print(json.dumps(result, indent=2))
        return 0 if result.get("written") else 1

    print(json.dumps(refresh, indent=2))
    return 0 if refresh.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
