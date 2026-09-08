"""RH-01e: provider availability recorder (turns point-in-time snapshots into a series).

Read-only. All network I/O is injected via ``call_fn``; tests never open a
socket. Reuses the RH-01d pool module for per-method verification,
disagreement detection, usability, and the live gate -- this module only adds
the periodic sampling loop and the two SQLite tables.

Design notes
------------
* Consensus comparison happens ONLY on a pinned block (``head - 60``). The
  head block number (``eth_blockNumber``) is deliberately NOT a consensus
  method: every provider reports its own chain head, so comparing it would
  misreport normal sync lag as ``SOURCE_DISAGREEMENT`` and needlessly ban the
  warehouse.
* ``chain_id`` is validated against ``EXPECTED_CHAIN_ID`` (4663): an endpoint
  serving a different chain (e.g. Base, 8453) is not ok even when the call
  succeeds. Its raw value is still digested, so cross-provider disagreement
  detection sees a wrong-chain answer too.
* ``usable_count`` is fail-closed over ALL capabilities: missing even one
  capability makes a provider unusable.
* ``latency_ms`` is NULL on failure rows (never 0).
* One provider's timeout/exception never aborts the round; it is recorded on
  that row's ``error`` and the loop continues to the next provider.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_provider_pool_v1_readonly import (  # noqa: E402
    _digest,
    detect_disagreement,
    live_readiness,
    usable_providers,
    verify_provider_methods,
)

__all__ = [
    "CAPABILITIES",
    "CONSENSUS_METHODS",
    "EXPECTED_CHAIN_ID",
    "PROVIDERS",
    "JsonRpcError",
    "run_round",
    "main",
]

# The 8 capabilities required by PRD §8.3, in fixed order (one row each).
CAPABILITIES = [
    "chain_id",
    "block_hash_consistency",
    "historical_read",
    "log_range_1k",
    "log_range_10k",
    "eth_call",
    "gas_estimate",
    "error_structure",
]

# Consensus comparison is on pinned-block methods plus chain_id.
# eth_blockNumber is the one deliberately excluded method: every provider
# reports its own chain head, so comparing it would misreport normal sync lag
# as SOURCE_DISAGREEMENT. chain_id is a constant (EXPECTED_CHAIN_ID) and MUST
# be compared: a wrong-chain endpoint must show up in disagreements.
CONSENSUS_METHODS = ["chain_id", "block_hash_consistency", "eth_call"]

# chainId 4663 endpoints from the ethereum-lists registry.
PROVIDERS = [
    {"name": "robinhood", "url": "https://rpc.mainnet.chain.robinhood.com"},
    {"name": "publicnode", "url": "https://robinhood-rpc.publicnode.com"},
    {"name": "ordofi", "url": "https://rpc.ordofi.network"},
    {"name": "arrowrpc", "url": "https://rpc.arrowrpc.com"},
]

# CORE seed pool + selectors (PRD §8.3).
CORE_POOL = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
SLOT0_SELECTOR = "0x3850c7bd"
SWAP_TOPIC0 = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"

# The chain this recorder serves (PRD §8.3 identity gate).
EXPECTED_CHAIN_ID = 4663

# probe name -> JSON-RPC method. "head" is the separate head-block fetch.
PROBE_TO_RPC = {
    "head": "eth_blockNumber",
    "chain_id": "eth_chainId",
    "block_hash_consistency": "eth_getBlock",
    "historical_read": "eth_call",
    "log_range_1k": "eth_getLogs",
    "log_range_10k": "eth_getLogs",
    "eth_call": "eth_call",
    "gas_estimate": "eth_estimateGas",
    "error_structure": "lp_nonexistent_method",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS rh_provider_capability (
    sample_time TEXT NOT NULL,
    provider TEXT NOT NULL,
    capability TEXT NOT NULL,
    ok INTEGER NOT NULL,
    latency_ms REAL,
    error TEXT,
    result_digest TEXT,
    PRIMARY KEY (sample_time, provider, capability));
CREATE TABLE IF NOT EXISTS rh_provider_rollup (
    sample_time TEXT NOT NULL,
    usable_count INTEGER NOT NULL,
    usable_providers_json TEXT,
    disagreements_json TEXT,
    live_gate_status TEXT,
    live_gate_reason TEXT,
    head_block INTEGER,
    pinned_block INTEGER,
    PRIMARY KEY (sample_time));
"""


class JsonRpcError(Exception):
    """A structured JSON-RPC error object (the endpoint is alive and well-behaved).

    Distinct from transport/HTTP-layer errors (HTTPError, URLError, timeout),
    which mean the endpoint is not usable. ``error_structure`` is ok only when
    this is raised; an HTTP-layer error is not ok.
    """

    def __init__(self, code, message, data=None):
        super().__init__("JSON-RPC error %s: %s" % (code, message))
        self.code = code
        self.message = message
        self.data = data


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_probes(head: int, pinned_block: int) -> List[dict]:
    """The 7 normal capability probes; eth_call + block hash hit the pinned block."""
    pinned_hex = hex(pinned_block)
    hist_hex = hex(head - 100000)
    slot0 = {"to": CORE_POOL, "data": SLOT0_SELECTOR}

    def logs(from_hex):
        return [{"fromBlock": from_hex, "toBlock": pinned_hex,
                 "address": CORE_POOL, "topics": [SWAP_TOPIC0]}]

    return [
        {"method": "chain_id", "params": []},
        {"method": "block_hash_consistency", "params": [pinned_hex, False]},
        {"method": "historical_read", "params": [slot0, hist_hex]},
        {"method": "log_range_1k", "params": logs(hex(pinned_block - 1000))},
        {"method": "log_range_10k", "params": logs(hex(pinned_block - 10000))},
        {"method": "eth_call", "params": [slot0, pinned_hex]},
        {"method": "gas_estimate", "params": [slot0]},
    ]


def _fetch_head(providers, call_fn) -> Optional[int]:
    """Head block from the first provider that answers; None if all fail."""
    for prov in providers:
        try:
            return int(call_fn(prov["url"], "head", []), 16)
        except Exception:  # noqa: BLE001 - try the next provider
            continue
    return None


def _probe_error_structure(url, call_fn) -> dict:
    """error_structure: ok only on a structured JSON-RPC error, not on HTTP."""
    t0 = time.perf_counter()
    try:
        call_fn(url, "error_structure", [])
    except JsonRpcError as exc:
        return {
            "ok": True,
            "latency_ms": (time.perf_counter() - t0) * 1000.0,
            "error": None,
            "result_digest": _digest({"code": exc.code, "message": exc.message}),
        }
    except Exception as exc:  # noqa: BLE001 - HTTP/transport-layer error
        return {
            "ok": False,
            "latency_ms": None,
            "error": "%s: %s" % (type(exc).__name__, exc),
            "result_digest": None,
        }
    # A result came back for a non-existent method: not the structured error
    # we asked for, so not ok.
    return {
        "ok": False,
        "latency_ms": None,
        "error": "expected JSON-RPC error but got a result",
        "result_digest": None,
    }


def _parse_chain_id(result):
    """eth_chainId result -> int, or None when not parseable."""
    if isinstance(result, int):
        return result
    if isinstance(result, str):
        s = result.strip()
        try:
            return int(s, 16) if s.lower().startswith("0x") else int(s, 10)
        except ValueError:
            return None
    return None


def _probe_chain_id(url, call_fn) -> dict:
    """chain_id: ok only when the endpoint reports EXPECTED_CHAIN_ID (4663).

    The raw value is digested even on a wrong-chain answer, so a Base
    endpoint (8453) still shows up in cross-provider disagreements.
    """
    t0 = time.perf_counter()
    try:
        result = call_fn(url, "chain_id", [])
    except Exception as exc:  # noqa: BLE001 - transport/HTTP-layer error
        return {"ok": False, "latency_ms": None,
                "error": "%s: %s" % (type(exc).__name__, exc),
                "result_digest": None}
    digest = _digest(result)
    chain_id = _parse_chain_id(result)
    if chain_id == EXPECTED_CHAIN_ID:
        return {"ok": True,
                "latency_ms": (time.perf_counter() - t0) * 1000.0,
                "error": None, "result_digest": digest}
    if chain_id is None:
        error = "chain_id result not parseable: %r" % (result,)
    else:
        error = "chain_id %d != expected %d" % (chain_id, EXPECTED_CHAIN_ID)
    return {"ok": False, "latency_ms": None, "error": error,
            "result_digest": digest}


def run_round(conn, providers, call_fn, sample_time) -> dict:
    """Run one sampling round; write capability + rollup rows. Returns a summary.

    A single provider's timeout/exception never aborts the round: it is
    recorded on that row's ``error`` and the loop continues.
    """
    head = _fetch_head(providers, call_fn)
    pinned_block = (head - 60) if head is not None else None

    if head is not None:
        probes = _build_probes(head, pinned_block)
        # chain_id is probed by _probe_chain_id: it must validate the value
        # against EXPECTED_CHAIN_ID, which verify_provider_methods cannot do.
        matrix = verify_provider_methods(
            providers,
            [p for p in probes if p["method"] != "chain_id"], call_fn)
        for prov in providers:
            matrix[prov["name"]]["chain_id"] = _probe_chain_id(
                prov["url"], call_fn)
    else:
        # No head available: every pinned-block capability fails, but we still
        # write all 8 rows per provider (never fewer).
        probes = _build_probes(0, 0)
        matrix = {
            prov["name"]: {
                p["method"]: {"ok": False, "latency_ms": None,
                              "error": "no head block available",
                              "result_digest": None}
                for p in probes
            }
            for prov in providers
        }

    # error_structure has inverted semantics, so it is probed separately.
    for prov in providers:
        matrix[prov["name"]]["error_structure"] = _probe_error_structure(
            prov["url"], call_fn)

    usable = usable_providers(matrix, CAPABILITIES)
    methods = [{"method": c} for c in CAPABILITIES]
    disagreements = detect_disagreement(
        matrix, methods, consensus_methods=CONSENSUS_METHODS)
    readiness = live_readiness(len(usable))

    _write_capability_rows(conn, sample_time, providers, matrix)
    _write_rollup_row(conn, sample_time, usable, disagreements, readiness,
                      head, pinned_block)
    conn.commit()

    return {
        "usable_count": len(usable),
        "live_gate_status": readiness["status"],
        "live_gate_reason": readiness["reason"],
        "head_block": head,
        "pinned_block": pinned_block,
    }


def _write_capability_rows(conn, sample_time, providers, matrix) -> None:
    for prov in providers:
        name = prov["name"]
        meths = matrix.get(name, {})
        for cap in CAPABILITIES:
            rec = meths.get(cap, {})
            ok = 1 if rec.get("ok") is True else 0
            latency = rec.get("latency_ms")
            if ok == 0:
                latency = None  # failure rows: NULL, never 0
            conn.execute(
                "INSERT OR REPLACE INTO rh_provider_capability "
                "(sample_time, provider, capability, ok, latency_ms, error, "
                "result_digest) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sample_time, name, cap, ok, latency,
                 rec.get("error"), rec.get("result_digest")),
            )


def _write_rollup_row(conn, sample_time, usable, disagreements, readiness,
                      head, pinned_block) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO rh_provider_rollup "
        "(sample_time, usable_count, usable_providers_json, "
        "disagreements_json, live_gate_status, live_gate_reason, head_block, "
        "pinned_block) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (sample_time, len(usable), json.dumps(usable, sort_keys=True),
         json.dumps(disagreements, sort_keys=True),
         readiness["status"], readiness["reason"], head, pinned_block),
    )


_USER_AGENT = "lp-rh-provider-health/1.0 (readonly)"


def _default_call_fn(url, probe, params):
    """urllib JSON-RPC POST. Raises JsonRpcError on a structured error and lets
    transport/HTTP errors (HTTPError, URLError, timeout) propagate."""
    rpc_method = PROBE_TO_RPC[probe]
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": rpc_method, "params": params}
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        raise JsonRpcError(err.get("code"), err.get("message"), err.get("data"))
    return data.get("result") if isinstance(data, dict) else data


_STOP = {"flag": False}


def _on_signal(signum, frame):
    _STOP["flag"] = True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="RH-01e provider health recorder (read-only)")
    ap.add_argument("--db", default="reports/lp_rh/provider_health.db")
    ap.add_argument("--period-secs", type=float, default=900.0)
    ap.add_argument("--pid-file", default=None)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args(argv)
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    if args.pid_file:
        Path(args.pid_file).write_text(str(os.getpid()))
    conn = sqlite3.connect(args.db, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)

    while not _STOP["flag"]:
        started = time.monotonic()  # deadline from round START, not end
        sample_time = _now()
        try:
            summary = run_round(conn, PROVIDERS, _default_call_fn, sample_time)
            print("%s usable=%d gate=%s head=%s pinned=%s" % (
                sample_time, summary["usable_count"],
                summary["live_gate_status"], summary["head_block"],
                summary["pinned_block"]), flush=True)
        except Exception as exc:  # noqa: BLE001 - one bad round never kills the loop
            print("%s round failed: %s" % (sample_time, exc),
                  file=sys.stderr, flush=True)
        if args.once:
            break
        deadline = started + args.period_secs
        while not _STOP["flag"]:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            time.sleep(min(1.0, left))
    conn.close()
    if args.pid_file:
        try:
            os.unlink(args.pid_file)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
