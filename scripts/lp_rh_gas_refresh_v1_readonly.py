#!/usr/bin/env python3
"""RH gas refresh: recompute pool_meta's gas_usd_estimate from live chain state.

RH-03d.  RH-03c built the estimator (``lp_rh_gas_estimator_v1_readonly``) but
nothing wrote its result back into ``reports/lp_rh/pool_meta.json``, whose
``gas_usd_estimate`` was still the hand-filled ``0.02`` -- the value T34
forensics proved understated ~23x (true ~$0.4614) and which inverted a
capital-policy verdict.  This package closes that gap.

No gas constant is hard-coded here (not even 0.4614, which is only a snapshot
at one gas price): the new value is computed from *injected* chain state via
the RH-03c estimator.  The module itself performs no network I/O -- chain data
arrives through an injected ``rpc_fn(method, params)`` and ``native_price_usd``
is supplied by the caller.  When any input is missing or non-positive the
refresh is ``UNAVAILABLE`` and ``apply_to_pool_meta`` writes nothing.

Family convention: ``rpc_fn`` returns the JSON-RPC envelope; ``_call`` splits
it into (value, error).  All money is ``Decimal``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_gas_estimator_v1_readonly import (  # noqa: E402
    GAS_UNITS,
    gas_estimate_sanity,
    observed_gas_units,
    round_trip_gas_usd,
)
from scripts.lp_rh_capabilities_v1_readonly import (  # noqa: E402
    _call,
    _default_rpc,
    _hex_to_int,
)

RPC_URL = "https://rpc.mainnet.chain.robinhood.com"

# Open + close a position: v3_mint + v3_burn_collect (from the RH-03c table).
_ROUND_TRIP_UNITS = GAS_UNITS["v3_mint"] + GAS_UNITS["v3_burn_collect"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    """Make a result JSON-serialisable (Decimal -> str to preserve precision)."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def collect_gas_inputs(rpc_fn: Callable, *, receipt_sample: int = 8) -> dict:
    """Fetch gas price + latest-block receipts through rpc_fn (no I/O here).

    Returns {"gas_price_wei", "block_number", "observed", "errors"}.  Any step
    that fails is recorded in ``errors`` and its value left ``None`` -- never
    raised, never filled with 0.
    """
    errors: list = []
    gas_price_wei: Optional[int] = None
    block_number: Optional[int] = None
    observed: Optional[dict] = None

    gp_raw, gp_err = _call(rpc_fn, "eth_gasPrice", [])
    if gp_err is not None:
        errors.append("eth_gasPrice: %s" % gp_err)
    else:
        gas_price_wei = _hex_to_int(gp_raw)
        if gas_price_wei is None:
            errors.append("eth_gasPrice: unparseable result %r" % (gp_raw,))

    block, block_err = _call(rpc_fn, "eth_getBlockByNumber", ["latest", True])
    if block_err is not None:
        errors.append("eth_getBlockByNumber: %s" % block_err)
    elif not isinstance(block, dict):
        errors.append("eth_getBlockByNumber: non-object result %r" % (block,))
    else:
        block_number = _hex_to_int(block.get("number"))
        txs = block.get("transactions")
        if not isinstance(txs, list):
            txs = []
        receipts = []
        for tx in txs[:receipt_sample]:
            if isinstance(tx, dict):
                receipts.append({
                    "gasUsed": tx.get("gasUsed"),
                    "effectiveGasPrice": tx.get("effectiveGasPrice"),
                })
        observed = observed_gas_units(receipts)

    return {
        "gas_price_wei": gas_price_wei,
        "block_number": block_number,
        "observed": observed,
        "errors": errors,
    }


def compute_refresh(inputs: dict, *, native_price_usd: Any,
                    current_estimate: Any) -> dict:
    """Compute the new gas estimate and sanity-check it against the old value.

    Returns {"new_gas_usd", "sanity", "provenance", "verdict"}.  ``verdict`` is
    ``REFRESHED`` only when ``new_gas_usd`` is a positive Decimal; otherwise
    ``UNAVAILABLE`` (new_gas_usd is None).  ``sanity`` compares the old
    ``current_estimate`` against the newly computed value.
    """
    gas_price_wei = inputs.get("gas_price_wei")
    block_number = inputs.get("block_number")
    observed = inputs.get("observed")

    new_gas_usd = round_trip_gas_usd(
        gas_price_wei=gas_price_wei,
        native_price_usd=native_price_usd,
    )
    sanity = gas_estimate_sanity(current_estimate, new_gas_usd)
    receipt_n = observed.get("n") if isinstance(observed, dict) else None
    provenance = {
        "gas_price_wei": gas_price_wei,
        "native_price_usd": native_price_usd,
        "block_number": block_number,
        "receipt_n": receipt_n,
        "gas_units_total": _ROUND_TRIP_UNITS,
        "computed_at": _utc_now_iso(),
    }
    verdict = "REFRESHED" if new_gas_usd is not None else "UNAVAILABLE"
    return {
        "new_gas_usd": new_gas_usd,
        "sanity": sanity,
        "provenance": provenance,
        "verdict": verdict,
    }


def apply_to_pool_meta(path, refresh: dict, *, backup: bool = True) -> dict:
    """Atomically write the refreshed gas_usd_estimate into pool_meta.

    Writes nothing (returns {"written": False, ...}) unless ``verdict`` is
    ``REFRESHED`` and ``new_gas_usd`` is not None.  The write is atomic: a temp
    file in the same directory is filled then ``os.replace``d over the target,
    so a concurrent reader never sees a half-written file.  Only the
    ``gas_usd_estimate`` key changes and a ``gas_provenance`` dict is added;
    every other key is preserved verbatim.  ``backup=True`` first copies the
    original to ``<path>.bak-<UTC timestamp>``.
    """
    path = Path(path)
    verdict = refresh.get("verdict")
    new_gas_usd = refresh.get("new_gas_usd")
    if verdict != "REFRESHED" or new_gas_usd is None:
        return {
            "written": False,
            "reason": "verdict=%r new_gas_usd=%r" % (verdict, new_gas_usd),
        }

    meta = json.loads(path.read_text())

    backup_path = None
    if backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        backup_path = path.with_name("%s.bak-%s" % (path.name, ts))
        shutil.copy2(path, backup_path)

    meta["gas_usd_estimate"] = float(new_gas_usd)
    meta["gas_provenance"] = refresh.get("provenance") or {}

    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".pool_meta.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(meta, fh, indent=1)
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
        "gas_usd_estimate": float(new_gas_usd),
    }


def main(argv=None, *, rpc_fn: Optional[Callable] = None) -> int:
    """CLI.  Read-only by default: without ``--apply`` it only prints the
    refresh it would write.  ``rpc_fn`` is injectable for offline tests; the
    default is the family urllib JSON-RPC client."""
    ap = argparse.ArgumentParser(
        description="Refresh pool_meta gas_usd_estimate from live chain state "
                    "(read-only unless --apply).")
    ap.add_argument("--pool-meta", required=True)
    ap.add_argument("--native-price-usd", required=True)
    ap.add_argument("--receipt-sample", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    if rpc_fn is None:
        rpc_fn = _default_rpc(RPC_URL)

    try:
        meta = json.loads(Path(args.pool_meta).read_text())
        current_estimate = meta.get("gas_usd_estimate") if isinstance(meta, dict) else None
    except Exception:
        current_estimate = None

    inputs = collect_gas_inputs(rpc_fn, receipt_sample=args.receipt_sample)
    refresh = compute_refresh(
        inputs,
        native_price_usd=args.native_price_usd,
        current_estimate=current_estimate,
    )

    if args.apply:
        result = apply_to_pool_meta(args.pool_meta, refresh)
        print(json.dumps(_json_safe(result), indent=2, sort_keys=True))
    else:
        # Read-only (default and --dry-run): print what would be written.
        print(json.dumps(_json_safe(refresh), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
