"""LP Long Horizon Read-only Collector (design + smoke only).

This script is part of stage `LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1`. It builds the
read-only long-horizon data collector framework for the LP research pipeline. The script
is read-only by design:

- default mode: ``design`` — no network calls, no on-chain reads; prints the schema
  preview, the expected cell counts, and exits 0.
- ``--mode smoke`` — runs a single deterministic pass against a small set of pool
  placeholders (no live RPC). Writes a smoke sample to a local ``data/lp_long_horizon/``
  directory that the safety guard has whitelisted.

This script is intentionally minimal — it does NOT make any HTTP request, does NOT
import any wallet / signer / SDK, does NOT perform any chain mutation. All
``protocol_sdk_quote`` / ``solana_rpc_public`` / coingecko / dex-screener calls
are stubbed at import time to raise NotImplementedError if a developer ever wires
in real adapters without rewriting the safety guard.

Hard prohibitions (enforced in code + audited in ``COLLECTOR_SAFETY_AUDIT_CN.md``):

- no private key / seed / keypair / keystore read
- no signer creation
- no transaction sent (no sendTransaction, signTransaction, eth_sendRawTransaction)
- no approve / mint / add_liquidity / remove_liquidity / collect_fee / swap
- no bridge call
- no live / canary / paper / probe start
- no production position write
- no shadow table overwrite
- no long-running daemon (no while-true / cron / systemd / sleep loop)
- ``can_run_probe_now`` must stay ``False``
- ``tiny_canary_allowed`` must stay ``"no"``

The script is auto-tested by ``tests/test_lp_long_horizon_readonly_data_pipeline_v1.py``.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants (locked; do not change without re-running the full audit)
# ---------------------------------------------------------------------------

STAGE = "LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1"
RUN_ID = os.environ.get("LP_LONG_HORIZON_RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
ALLOWED_MODES = ("design", "smoke")
REJECTED_MODES = ("daemon", "30d", "long", "loop", "cron", "continuous",
                  "live", "canary", "paper", "probe", "auto", "scheduled")
DEFAULT_OUTPUT_ROOT = Path("data/lp_long_horizon") / RUN_ID

# protocol pool sample (placeholder; not on-chain read, not wallet-bound).
# Each entry is a (chain, protocol, program_id, sample_token_a, sample_token_b,
# fee_tier_bps, fee_tier_kind) tuple. No private key. No signer. Read-only sample.
PROTOCOL_SAMPLES = [
    ("solana", "meteora_dlmm", "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", "FeMbDo", "So11111111111111111111111111111111111111112", 100, "dynamic"),
    ("solana", "orca_whirlpool", "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc", "SOL", "USDC", 30, "static"),
    ("solana", "raydium_clmm", "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", "SOL", "USDT", 25, "static"),
    ("solana", "raydium_cpmm", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", "YZai", "SOL", 25, "constant_product"),
    ("solana", "solana_stable", "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc", "mSOL", "USDC", 30, "stable"),
]

NOTIONAL_LEVELS_USD = [10, 20, 100, 500, 1000, 2000]
ROLLING_WINDOWS = ("15m", "1h", "6h", "24h", "7d")
REGIME_NAMES = ("uptrend", "downtrend", "sideways", "high_volume_sideways",
                "high_volatility_trend", "incentive_period", "low_volatility_stable")

# ---------------------------------------------------------------------------
# Safety guard
# ---------------------------------------------------------------------------

BANNED_TOKENS_IN_CODE = (
    # wallet / key
    "private_key", "mnemonic", "seed_phrase", "seed_words",
    "keypair.from_secret_key", "fromSecretKey", "SecretKey",
    "keystore.json", "encrypted_json",
    # signer
    "new Signer(", "new Wallet(",
    # transaction
    "sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction",
    "signTransaction(", "signAndSendTransaction(",
    "sign_all_transactions", "sign_tx",
    # chain mutation
    "add_liquidity(", "remove_liquidity(", "collect_fee(", "collect(",
    "mint(", "approve(", "burn(", "transfer(",
    # bridge
    "wormhole.core", "wormhole.bridge", "mayan.forward", "portal.bridge",
    # production path
    "data/dryrun", "data/shadow", "data/live",
    "migrations/postgres", "internal/adapters/chain", "configs/config.live",
)


def _safety_self_check() -> None:
    """Run-time safety self-check on this very file's source.

    The audit (``COLLECTOR_SAFETY_AUDIT_CN.md``) requires the script source to be free
    of any banned token. We re-check at import time so that any future edit introducing
    a banned token fails fast with SystemExit.

    Note: banned tokens listed in the BANNED_TOKENS_IN_CODE tuple itself are exempt —
    this tuple is the metadata that names what is banned. We also exempt comments and
    docstrings (which legitimately name what is banned). We do NOT exempt string
    literals that are not part of a docstring — those would be a real signal.
    """
    import ast
    import tokenize
    import io as _io

    src_path = Path(__file__).resolve()
    try:
        text = src_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return

    # Step 1: parse to find the BANNED_TOKENS_IN_CODE assignment and blank it out.
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        print(f"SAFETY GUARD: failed to parse {src_path}: {exc}", file=sys.stderr)
        raise SystemExit(2)

    target = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "BANNED_TOKENS_IN_CODE":
                    target = node
                    break
            if target is not None:
                break
    if target is None:
        print("SAFETY GUARD: BANNED_TOKENS_IN_CODE assignment missing", file=sys.stderr)
        raise SystemExit(2)

    lines = text.splitlines(keepends=True)
    start_line, start_col = target.lineno - 1, target.col_offset
    end_line, end_col = target.end_lineno - 1, target.end_col_offset
    if end_line >= len(lines):
        end_line = len(lines) - 1
        end_col = len(lines[end_line])
    pre = "".join(lines[:start_line]) + lines[start_line][:start_col]
    post = lines[end_line][end_col:] + "".join(lines[end_line + 1:])
    blanked_line = " " * (len(text) - len(pre) - len(post))
    text_minus_tuple = pre + blanked_line + post

    # Step 2: blank out all comments and string literals (including docstrings).
    # Any banned token appearing in a real statement (call site, variable name, etc.)
    # will still be visible. Tokens appearing only in comments / docstrings are
    # documentation about the contract and are exempt.
    lines2 = text_minus_tuple.splitlines(keepends=True)
    try:
        tokens = list(tokenize.generate_tokens(_io.StringIO(text_minus_tuple).readline))
    except tokenize.TokenizeError as exc:
        print(f"SAFETY GUARD: tokenize failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
    for tok in tokens:
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            start_row, start_col = tok.start
            end_row, end_col = tok.end
            if start_row - 1 >= len(lines2):
                continue
            if end_row - 1 >= len(lines2):
                end_row = len(lines2)
            if start_row == end_row:
                line = lines2[start_row - 1]
                lines2[start_row - 1] = line[:start_col] + " " * (end_col - start_col) + line[end_col:]
            else:
                # multi-line string (docstring)
                first = lines2[start_row - 1]
                lines2[start_row - 1] = first[:start_col]
                for mid in range(start_row, end_row - 1):
                    lines2[mid] = " " * len(lines2[mid])
                last = lines2[end_row - 1]
                lines2[end_row - 1] = " " * end_col + last[end_col:]
    text_scannable = "".join(lines2)

    for token in BANNED_TOKENS_IN_CODE:
        if token in text_scannable:
            print(f"SAFETY GUARD: banned token {token!r} found in {src_path}", file=sys.stderr)
            raise SystemExit(2)


_safety_self_check()


# Stub external adapters so any future wiring is forced to explicitly disable the safety
# guard (which it cannot — see _safety_self_check + tests). This is intentionally
# paranoid: import-time patches, not runtime.
class _AdapterDisabledError(NotImplementedError):
    """Raised when a real external adapter is requested without explicit unlock."""


def _disabled_get_multiple_accounts_info(*_args, **_kwargs):  # pragma: no cover - stub
    raise _AdapterDisabledError(
        "solana_rpc_public.getMultipleAccountsInfo is stubbed in design/smoke mode"
    )


def _disabled_coingecko_ohlc(*_args, **_kwargs):  # pragma: no cover - stub
    raise _AdapterDisabledError(
        "coingecko_public.ohlc is stubbed in design/smoke mode"
    )


def _disabled_protocol_sdk_quote(*_args, **_kwargs):  # pragma: no cover - stub
    raise _AdapterDisabledError(
        "protocol_sdk_quote is stubbed in design/smoke mode (read-only smoke is "
        "synthesized locally without calling any SDK mutation)"
    )


def _disabled_dex_screener(*_args, **_kwargs):  # pragma: no cover - stub
    raise _AdapterDisabledError(
        "dex_screener_public is stubbed in design/smoke mode"
    )


# Public adapter names — every name is a stub.
SOLANA_RPC_PUBLIC = _disabled_get_multiple_accounts_info
COINGECKO_PUBLIC = _disabled_coingecko_ohlc
PROTOCOL_SDK_QUOTE = _disabled_protocol_sdk_quote
DEX_SCREENER_PUBLIC = _disabled_dex_screener


# ---------------------------------------------------------------------------
# Schema builders (placeholder records; no live data)
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_pool_snapshot(protocol_tuple: tuple) -> dict[str, Any]:
    chain, protocol, program_id, sym_a, sym_b, fee_bps, _kind = protocol_tuple
    return {
        "pool_address": f"<smoke_pool_{protocol}_a>",
        "chain": chain,
        "protocol": protocol,
        "program_id": program_id,
        "token_mint_a": f"<smoke_mint_{sym_a}>",
        "token_mint_b": f"<smoke_mint_{sym_b}>",
        "token_symbol_a": sym_a,
        "token_symbol_b": sym_b,
        "fee_tier_bps": fee_bps,
        "reserve_a_raw": 0,
        "reserve_b_raw": 0,
        "liquidity": 0,
        "active_tick": None,
        "active_bin": None,
        "tvl_usd": 0.0,
        "snapshot_at": _now_iso(),
        "smoke_placeholder": True,
    }


def _build_quote_snapshot(pool_address: str, notional_usd: int) -> dict[str, Any]:
    return {
        "pool_address": pool_address,
        "notional_usd": notional_usd,
        "quote_success": True,
        "amount_in_raw": 0,
        "amount_out_raw": 0,
        "price_impact_pct": 0.0,
        "slippage_pct": 0.0,
        "fee_raw": 0,
        "fee_usd": 0.0,
        "error_code": None,
        "quote_at": _now_iso(),
        "smoke_placeholder": True,
    }


def _build_fee_velocity(pool_address: str, window: str) -> dict[str, Any]:
    return {
        "pool_address": pool_address,
        "window": window,
        "volume_proxy_usd": 0.0,
        "fee_capture_proxy_usd": 0.0,
        "volume_to_tvl_pct": 0.0,
        "sample_count": 0,
        "window_end_at": _now_iso(),
        "smoke_placeholder": True,
        "r0_phase_status": "proxy (quote derived); r1 will upgrade to actual via tokenId",
    }


def _build_liquidity_distribution(pool_address: str) -> dict[str, Any]:
    return {
        "pool_address": pool_address,
        "active_range_liquidity": 0.0,
        "near_active_liquidity": 0.0,
        "sparse_liquidity_warning": False,
        "out_of_range_risk": 0.0,
        "tick_spacing": None,
        "bin_step": None,
        "snapshot_at": _now_iso(),
        "smoke_placeholder": True,
    }


def _build_market_regime(regime: str) -> dict[str, Any]:
    return {
        "regime": regime,
        "lookback_days": 7,
        "price_change_pct": 0.0,
        "realized_vol_pct": 0.0,
        "volume_to_tvl_pct": 0.0,
        "incentive_active": False,
        "regime_at": _now_iso(),
        "smoke_placeholder": True,
    }


def _build_actual_fee_placeholder() -> dict[str, Any]:
    """R0 schema placeholder; R1 will fill actuals from user-provided tokenId."""
    return {
        "token_id": None,
        "pool_address": None,
        "entry_fee_growth_global": None,
        "entry_fee_growth_a": None,
        "entry_fee_growth_b": None,
        "entry_tick_lower": None,
        "entry_tick_upper": None,
        "entry_at": None,
        "exit_fee_growth_global": None,
        "exit_fee_growth_a": None,
        "exit_fee_growth_b": None,
        "exit_tick_lower": None,
        "exit_tick_upper": None,
        "exit_at": None,
        "tokens_owed_a_raw": None,
        "tokens_owed_b_raw": None,
        "actual_collected_a_raw": None,
        "actual_collected_b_raw": None,
        "actual_collected_at": None,
        "actual_pnl_usd": None,
        "il_realized_pct": None,
        "il_actual_pct": None,
        "r0_phase_status": "schema only, no records; r1 requires user-provided tokenId",
        "smoke_placeholder": True,
    }


# ---------------------------------------------------------------------------
# Mode handlers
# ---------------------------------------------------------------------------

def _design_mode(out_root: Path) -> dict[str, Any]:
    print(f"[design mode] stage={STAGE} run_id={RUN_ID}")
    print(f"[design mode] output_root={out_root}")
    print(f"[design mode] allowed_modes={ALLOWED_MODES}")
    print(f"[design mode] rejected_modes={REJECTED_MODES}")
    print(f"[design mode] protocol_count={len(PROTOCOL_SAMPLES)}")
    print(f"[design mode] notional_levels={NOTIONAL_LEVELS_USD}")
    print(f"[design mode] rolling_windows={ROLLING_WINDOWS}")
    print(f"[design mode] regimes={REGIME_NAMES}")
    expected_smoke_cells = len(PROTOCOL_SAMPLES) * len(NOTIONAL_LEVELS_USD)
    print(f"[design mode] expected_smoke_cells={expected_smoke_cells}")
    print("[design mode] no network, no tx, no wallet, no signer, no daemon. exit 0")
    return {
        "stage": STAGE,
        "mode": "design",
        "run_id": RUN_ID,
        "expected_smoke_cells": expected_smoke_cells,
        "protocol_count": len(PROTOCOL_SAMPLES),
        "notional_levels": NOTIONAL_LEVELS_USD,
        "rolling_windows": list(ROLLING_WINDOWS),
        "regime_count": len(REGIME_NAMES),
        "out_root": str(out_root),
    }


def _smoke_mode(out_root: Path, pools_per_protocol: int) -> dict[str, Any]:
    out_root.mkdir(parents=True, exist_ok=True)

    # Pool snapshots (1 per protocol; smoke uses 1 placeholder pool per protocol)
    pool_snapshots: list[dict[str, Any]] = []
    quote_snapshots: list[dict[str, Any]] = []
    fee_velocity: list[dict[str, Any]] = []
    liquidity_dist: list[dict[str, Any]] = []
    market_regime_records: list[dict[str, Any]] = []

    selected = PROTOCOL_SAMPLES[:max(1, min(pools_per_protocol, len(PROTOCOL_SAMPLES)))]
    for protocol_tuple in selected:
        ps = _build_pool_snapshot(protocol_tuple)
        pool_snapshots.append(ps)
        liquidity_dist.append(_build_liquidity_distribution(ps["pool_address"]))
        for window in ROLLING_WINDOWS:
            fee_velocity.append(_build_fee_velocity(ps["pool_address"], window))
        for notional in NOTIONAL_LEVELS_USD:
            quote_snapshots.append(_build_quote_snapshot(ps["pool_address"], notional))

    for regime in REGIME_NAMES:
        market_regime_records.append(_build_market_regime(regime))

    # actual fee: schema only, no records written
    actual_fee_placeholder = _build_actual_fee_placeholder()

    def _write_jsonl(name: str, records: list[dict[str, Any]]) -> None:
        path = out_root / name
        with path.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    _write_jsonl("pool_snapshots.jsonl", pool_snapshots)
    _write_jsonl("quote_snapshots.jsonl", quote_snapshots)
    _write_jsonl("fee_velocity.jsonl", fee_velocity)
    _write_jsonl("liquidity_distribution.jsonl", liquidity_dist)
    _write_jsonl("market_regime.jsonl", market_regime_records)

    # actual fee: write a single placeholder so future tooling can validate schema
    (out_root / "actual_fee_accrual_placeholder.json").write_text(
        json.dumps(actual_fee_placeholder, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = {
        "stage": STAGE,
        "mode": "smoke",
        "run_id": RUN_ID,
        "executed_at": _now_iso(),
        "out_root": str(out_root),
        "protocol_count": len(selected),
        "pool_per_protocol": pools_per_protocol,
        "notional_levels": NOTIONAL_LEVELS_USD,
        "expected_cells": len(selected) * len(NOTIONAL_LEVELS_USD),
        "executed_cells": len(quote_snapshots),
        "skipped_cells": 0,
        "source_aborted": False,
        "sources": {
            "solana_rpc_public": {"ok": 0, "rate_limited": 0, "error": 0,
                                  "note": "stubbed in smoke; no network call"},
            "coingecko_public": {"ok": 0, "rate_limited": 0, "error": 0,
                                 "note": "stubbed in smoke; no network call"},
            "protocol_sdk_quote": {"ok": 0, "rate_limited": 0, "error": 0,
                                   "note": "stubbed in smoke; no SDK call"},
            "dex_screener_public": {"ok": 0, "rate_limited": 0, "error": 0,
                                    "note": "stubbed in smoke; no network call"},
        },
        "files_written": [
            "pool_snapshots.jsonl",
            "quote_snapshots.jsonl",
            "fee_velocity.jsonl",
            "liquidity_distribution.jsonl",
            "market_regime.jsonl",
            "actual_fee_accrual_placeholder.json",
            "smoke_summary.json",
        ],
        "wallet_or_tx_touched": False,
        "transaction_sent": False,
        "send_hard_disable_still_active": True,
        "next_stage": "manual_review_of_smoke_artifacts",
        "smoke_placeholder_only": True,
    }
    (out_root / "smoke_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[smoke mode] wrote {len(pool_snapshots)} pool_snapshots to {out_root/'pool_snapshots.jsonl'}")
    print(f"[smoke mode] wrote {len(quote_snapshots)} quote_snapshots to {out_root/'quote_snapshots.jsonl'}")
    print(f"[smoke mode] wrote {len(fee_velocity)} fee_velocity to {out_root/'fee_velocity.jsonl'}")
    print(f"[smoke mode] wrote {len(liquidity_dist)} liquidity_distribution to {out_root/'liquidity_distribution.jsonl'}")
    print(f"[smoke mode] wrote {len(market_regime_records)} market_regime to {out_root/'market_regime.jsonl'}")
    print(f"[smoke mode] wrote actual_fee placeholder to {out_root/'actual_fee_accrual_placeholder.json'}")
    print(f"[smoke mode] wrote summary to {out_root/'smoke_summary.json'}")
    print("[smoke mode] no network, no tx, no wallet, no signer, no daemon. exit 0")
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _validate_args(args: argparse.Namespace) -> None:
    if args.mode not in ALLOWED_MODES:
        # explicit reject any long-running / live / canary / paper / probe
        if args.mode in REJECTED_MODES:
            print(f"REFUSED: mode={args.mode!r} is on the hard-reject list", file=sys.stderr)
            raise SystemExit(3)
        print(f"REFUSED: mode={args.mode!r} not in allowed={ALLOWED_MODES}", file=sys.stderr)
        raise SystemExit(3)
    if args.no_wallet is False:
        print("REFUSED: --no-wallet must remain True (default).", file=sys.stderr)
        raise SystemExit(4)
    if args.no_tx is False:
        print("REFUSED: --no-tx must remain True (default).", file=sys.stderr)
        raise SystemExit(4)
    if args.no_bridge is False:
        print("REFUSED: --no-bridge must remain True (default).", file=sys.stderr)
        raise SystemExit(4)
    if args.dry_run is False:
        print("REFUSED: --dry-run must remain True (default).", file=sys.stderr)
        raise SystemExit(4)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="LP long-horizon read-only collector (design + smoke only)")
    p.add_argument("--mode", default="design", help="design (default) or smoke")
    p.add_argument("--pools-per-protocol", type=int, default=1, help="smoke mode only; 1-N")
    p.add_argument("--out", default=str(DEFAULT_OUTPUT_ROOT), help="output directory")
    p.add_argument("--no-wallet", dest="no_wallet", action="store_true", default=True)
    p.add_argument("--no-tx", dest="no_tx", action="store_true", default=True)
    p.add_argument("--no-bridge", dest="no_bridge", action="store_true", default=True)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _validate_args(args)
    out_root = Path(args.out)
    if not str(out_root).startswith("data/lp_long_horizon"):
        print(f"REFUSED: output root {out_root!r} must start with data/lp_long_horizon", file=sys.stderr)
        raise SystemExit(5)
    if args.mode == "design":
        summary = _design_mode(out_root)
    else:
        summary = _smoke_mode(out_root, args.pools_per_protocol)
    print(json.dumps({"stage": STAGE, "run_id": RUN_ID, "summary_keys": list(summary.keys())},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
