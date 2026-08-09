#!/usr/bin/env python3
"""Dependency-free, read-only dashboard for the LP M0 shadow evidence.

This process only reads operator-configured evidence paths.  Request paths and
query parameters can never select a filesystem object.  It has no wallet,
signing, transaction, subprocess, configuration-write, or daemon-control path.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import csv
import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence
from urllib.parse import parse_qs, urlsplit

if __package__:
    from scripts.lp_rejection_reason_v1_readonly import explain_rejection
    from scripts.lp_shadow_gate_v1_readonly import MIN_UNIQUE_ROOT_POOLS, _REENTRY_SUFFIX
else:  # Preserve direct ``python scripts/lp_panel_server_v1_readonly.py`` operation.
    from lp_rejection_reason_v1_readonly import explain_rejection
    from lp_shadow_gate_v1_readonly import MIN_UNIQUE_ROOT_POOLS, _REENTRY_SUFFIX


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "reports/lp_scanner/scanner.db"
DEFAULT_HEARTBEAT = REPO_ROOT / "reports/lp_portfolio_paper_runner/latest/heartbeat.jsonl"
DEFAULT_PORTFOLIO_CSV = REPO_ROOT / "reports/lp_portfolio_paper_runner/latest/portfolio_state_hourly.csv"
DEFAULT_RWA_DIR = REPO_ROOT / "reports/lp_scanner/rwa_sessions"
DEFAULT_PROBE_DIR = REPO_ROOT / "reports/lp_rpc_pool_probe"
DEFAULT_ACCESS_LOG = REPO_ROOT / "reports/lp_panel/access.log"
TOKEN_ENV = "LPBOT_PANEL_TOKEN"
MIN_TOKEN_LENGTH = 32
MAX_REQUEST_BODY_BYTES = 8192
DEFAULT_RATE_LIMIT = 60
DEFAULT_REQUEST_TIMEOUT_SECS = 10.0
DEFAULT_REQUEST_QUEUE_SIZE = 16
DEFAULT_MAX_THREADS = 16
ALLOWED_PATHS = frozenset({"/", "/api/state.json"})

_SENSITIVE_KEY = re.compile(
    r"(?:^|[_-])(token|secret|password|passwd|api[_-]?key|private[_-]?key|credential|authorization|cookie)(?:$|[_-])",
    re.IGNORECASE,
)
_SENSITIVE_VALUE = re.compile(
    r"(?:\bBearer\s+[A-Za-z0-9._~+/=-]{12,}|\b\d{8,12}:[A-Za-z0-9_-]{30,}|"
    r"\bsk-[A-Za-z0-9_-]{20,}|\bAKIA[A-Z0-9]{16}\b|"
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b|"
    r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----)",
    re.IGNORECASE,
)
USD_NEAR_ZERO_TOLERANCE = 1e-9


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_timestamp(path: Path) -> Optional[str]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        return None


def open_sqlite_readonly(path: str | Path) -> sqlite3.Connection:
    """Open an existing SQLite database with OS- and SQLite-level writes denied."""
    resolved = Path(path).expanduser().resolve(strict=True)
    uri = resolved.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=1.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def scrub_payload(value: Any) -> Any:
    """Remove secret-bearing fields and redact recognizable secret values."""
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if _SENSITIVE_KEY.search(name):
                continue
            clean[name] = scrub_payload(item)
        return clean
    if isinstance(value, (list, tuple)):
        return [scrub_payload(item) for item in value]
    if isinstance(value, str):
        return _SENSITIVE_VALUE.sub("[REDACTED]", value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if table not in _table_names(connection):
        return set()
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _safe_json(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, str):
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _status(value: Any, predicate: Callable[[float], bool]) -> str:
    if value is None:
        return "UNKNOWN"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "UNKNOWN"
    return "PASS" if predicate(number) else "FAIL"


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _root_identity(identity: str) -> str:
    return _REENTRY_SUFFIX.sub("", identity)


def read_gate(connection: sqlite3.Connection) -> dict[str, Any]:
    tables = _table_names(connection)
    observations = "shadow_gate_observations" in tables
    positions = "shadow_positions" in tables
    incidents = "rpc_severe_incidents" in tables
    bounds = (None, None)
    latest: list[sqlite3.Row] = []
    max_dd = None
    if observations:
        bounds = connection.execute(
            "SELECT min(as_of), max(as_of) FROM shadow_gate_observations"
        ).fetchone()
        latest = connection.execute(
            """SELECT o.* FROM shadow_gate_observations o JOIN
               (SELECT source_run, max(tick) tick FROM shadow_gate_observations GROUP BY source_run) t
               USING(source_run,tick)"""
        ).fetchall()
        row = connection.execute(
            "SELECT max(simulated_drawdown_pct) FROM shadow_gate_observations"
        ).fetchone()
        max_dd = _finite(row[0]) if row else None
    duration = None
    if bounds and bounds[0] and bounds[1]:
        try:
            duration = (
                datetime.fromisoformat(str(bounds[1]).replace("Z", "+00:00"))
                - datetime.fromisoformat(str(bounds[0]).replace("Z", "+00:00"))
            ).total_seconds() / 86400.0
        except (TypeError, ValueError):
            pass
    identities: list[str] = []
    if positions:
        identities = [str(row[0]) for row in connection.execute(
            "SELECT position_identity FROM shadow_positions"
        )]
    unique_positions = len(identities)
    unique_pools = len({_root_identity(item) for item in identities})
    fee_error = None
    net_pnl = None
    net_pnl_raw = None
    rpc_health = "UNKNOWN"
    if latest:
        statuses = [str(row["fee_prediction_status"]) for row in latest]
        predicted = [_finite(row["predicted_fee_usd"]) for row in latest]
        actual = [_finite(row["actual_fee_usd"]) for row in latest]
        if all(item == "COMPLETE" for item in statuses) and all(
            item is not None for item in predicted + actual
        ):
            predicted_total = sum(float(item) for item in predicted)
            if predicted_total > 0:
                fee_error = abs(sum(float(item) for item in actual) - predicted_total) / predicted_total * 100
        pnls = [_finite(row["shadow_net_pnl_usd"]) for row in latest]
        if all(item is not None for item in pnls):
            net_pnl_raw = sum(float(item) for item in pnls)
            net_pnl = 0.0 if abs(net_pnl_raw) <= USD_NEAR_ZERO_TOLERANCE else net_pnl_raw
        health_values = [str(row["rpc_health"] or "UNKNOWN").upper() for row in latest]
        severity = {"UNKNOWN": 0, "NORMAL": 1, "DEGRADED": 2, "EXIT_ONLY": 3, "KILLED": 4}
        rpc_health = max(health_values, key=lambda item: severity.get(item, 0))
    unresolved = 0
    if incidents:
        unresolved = int(connection.execute(
            "SELECT count(*) FROM rpc_severe_incidents WHERE resolved_at IS NULL"
        ).fetchone()[0])
    position_status = "UNKNOWN" if not latest else (
        "PASS" if unique_positions >= 50 and unique_pools >= MIN_UNIQUE_ROOT_POOLS else "FAIL"
    )
    checks = {
        "shadow_duration_days": {"value": duration, "threshold": ">= 14", "status": _status(duration, lambda v: v >= 14)},
        "simulated_positions": {
            "value": unique_positions,
            "unique_position_identities": unique_positions,
            "unique_root_pools": unique_pools,
            "threshold": f">= 50 unique identities AND >= {MIN_UNIQUE_ROOT_POOLS} unique root pools",
            "status": position_status,
        },
        "fee_prediction_error_pct": {"value": fee_error, "threshold": "< 20%", "status": _status(fee_error, lambda v: v < 20)},
        "shadow_net_pnl_usd": {"value": net_pnl, "raw_value": net_pnl_raw, "threshold": "> 0", "status": _status(net_pnl, lambda v: v > 0)},
        "simulated_drawdown_pct": {"value": max_dd, "threshold": "< 8%", "status": _status(max_dd, lambda v: v < 8)},
        "rpc_severe_unresolved": {"value": unresolved, "threshold": "= 0", "status": _status(unresolved, lambda v: v == 0)},
    }
    statuses = {item["status"] for item in checks.values()}
    overall = "FAIL" if "FAIL" in statuses else ("INSUFFICIENT_EVIDENCE" if "UNKNOWN" in statuses else "PASS")
    return {
        "status": overall,
        "checks": checks,
        "unique_position_identity": unique_positions,
        "unique_root_pool": unique_pools,
        "rpc_health": rpc_health,
        "evidence_window": {"first": bounds[0] if bounds else None, "last": bounds[1] if bounds else None},
    }


def read_funnel(connection: sqlite3.Connection) -> dict[str, Any]:
    tables = _table_names(connection)
    result: dict[str, Any] = {
        "cycle_as_of": None, "screened": 0, "top": 0, "resolved": 0,
        "scored": 0, "accepted": 0, "gate_rejections": {}, "rejection_reasons": {},
    }
    if "opportunity_scores" not in tables:
        return result
    row = connection.execute("SELECT max(as_of) FROM opportunity_scores").fetchone()
    cycle = row[0] if row else None
    result["cycle_as_of"] = cycle
    if cycle is None:
        return result
    rows = connection.execute(
        "SELECT accepted,rejection_reason,score_json FROM opportunity_scores WHERE as_of=?", (cycle,)
    ).fetchall()
    result["scored"] = len(rows)
    result["top"] = len(rows)
    result["accepted"] = sum(int(row["accepted"]) for row in rows)
    reasons: collections.Counter[str] = collections.Counter()
    gate_rejections: collections.Counter[str] = collections.Counter()
    resolved = 0
    for row in rows:
        score = _safe_json(row["score_json"])
        gates = score.get("gates")
        if isinstance(gates, Mapping):
            for gate_name, passed in gates.items():
                if passed is False:
                    gate_rejections[str(gate_name)] += 1
        if str(score.get("resolve_status", "")).upper() == "OK" or score.get("resolved_pool"):
            resolved += 1
        if not int(row["accepted"]):
            reason_record = dict(score)
            # The DB column is the persisted terminal explanation.  Preserve it
            # as evidence, but let permanent/entry veto fields in score_json
            # outrank stale upstream success sentinels such as ``ok``/``PASS``.
            reason_record["persisted_rejection_reason"] = row["rejection_reason"]
            reason = explain_rejection(reason_record, accepted=False)
            assert reason is not None
            reasons[reason] += 1
    result["resolved"] = resolved
    result["gate_rejections"] = dict(sorted(gate_rejections.items()))
    result["rejection_reasons"] = dict(sorted(reasons.items()))
    if "pool_snapshots" in tables:
        snapshot_cycle = connection.execute("SELECT max(as_of) FROM pool_snapshots").fetchone()[0]
        result["screened"] = int(connection.execute(
            "SELECT count(*) FROM pool_snapshots WHERE as_of=?", (snapshot_cycle,)
        ).fetchone()[0]) if snapshot_cycle else 0
    return result


def read_latest_netcover(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    if "opportunity_scores" not in _table_names(connection):
        return {}
    cycle = connection.execute("SELECT max(as_of) FROM opportunity_scores").fetchone()[0]
    if cycle is None:
        return {}
    result: dict[str, dict[str, Any]] = {}
    ratio_column = "netcover_ratio" if "netcover_ratio" in _columns(connection, "opportunity_scores") else "NULL AS netcover_ratio"
    for row in connection.execute(
        f"SELECT pool,{ratio_column},score_json FROM opportunity_scores WHERE as_of=?", (cycle,)
    ):
        score = _safe_json(row["score_json"])
        result[str(row["pool"])] = {
            "netcover_ratio": row["netcover_ratio"] if row["netcover_ratio"] is not None else score.get("netcover_ratio"),
            "netcover_gate_status": score.get("netcover_gate_status"),
        }
    return result


def read_rwa_db(connection: sqlite3.Connection) -> dict[str, Any]:
    if "market_sessions" not in _table_names(connection):
        return {"symbols": [], "as_of": None}
    last = connection.execute("SELECT max(as_of) FROM market_sessions").fetchone()[0]
    if last is None:
        return {"symbols": [], "as_of": None}
    rows = connection.execute(
        "SELECT instrument_id,market_session,source_timestamp,reference_price,basis_bps,redemption_status,source "
        "FROM market_sessions WHERE as_of=? ORDER BY instrument_id,source", (last,)
    ).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        instrument = str(row["instrument_id"])
        raw_symbol = instrument.split(":", 1)[-1]
        symbol = raw_symbol[:-1] + "x" if raw_symbol.upper().endswith("X") else raw_symbol + "x"
        entry = grouped.setdefault(symbol, {"symbol": symbol, "session": row["market_session"], "anchors": []})
        entry["anchors"].append({
            "source": row["source"], "available": row["reference_price"] is not None,
            "price": row["reference_price"], "basis_bps": row["basis_bps"],
            "redemption_status": row["redemption_status"], "source_timestamp": row["source_timestamp"],
            "basis_semantics": "same_issuer_only" if row["basis_bps"] is not None else None,
        })
    return {"symbols": list(grouped.values()), "as_of": last}


def read_latest_json_lines(path: Path, limit: int = 2000) -> tuple[list[dict[str, Any]], int]:
    if not path.is_file():
        return [], 0
    lines: collections.deque[str] = collections.deque(maxlen=limit)
    malformed = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.strip():
                    lines.append(line)
    except OSError:
        return [], 0
    records: list[dict[str, Any]] = []
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if isinstance(item, dict):
            records.append(item)
    return records, malformed


def read_heartbeat(path: Path) -> dict[str, Any]:
    records, malformed = read_latest_json_lines(path, limit=5000)
    series: list[dict[str, Any]] = []
    peak_nav: Optional[float] = None
    for record in records:
        if record.get("portfolio_nav_usd") is None and record.get("portfolio_net_usd") is None:
            continue
        nav = _finite(record.get("portfolio_nav_usd"))
        if nav is not None:
            peak_nav = nav if peak_nav is None else max(peak_nav, nav)
        drawdown = ((peak_nav - nav) / peak_nav * 100.0) if nav is not None and peak_nav and peak_nav > 0 else None
        series.append({
            "as_of": record.get("ts_utc"),
            "portfolio_nav_usd": nav,
            "portfolio_net_usd": _finite(record.get("portfolio_net_usd")),
            "portfolio_drawdown_pct": drawdown,
        })
    last = records[-1] if records else {}
    positions = last.get("by_pool") if isinstance(last.get("by_pool"), list) else []
    return {
        "available": bool(records), "as_of": last.get("ts_utc"), "series": series[-1000:],
        "positions": positions, "malformed_lines": malformed,
    }


def read_portfolio_csv(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"available": False, "rows": [], "as_of": None}
    rows: collections.deque[dict[str, str]] = collections.deque(maxlen=1000)
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                rows.append(dict(row))
    except (OSError, csv.Error):
        return {"available": False, "rows": [], "as_of": None}
    data = list(rows)
    return {"available": True, "rows": data, "as_of": data[-1].get("ts_utc") if data else None}


def read_rwa_leads(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        return {"available": False, "shadow_leads": [], "as_of": None}
    leads: list[dict[str, Any]] = []
    for item in sorted(path.glob("*.jsonl")):
        records, _ = read_latest_json_lines(item, limit=100)
        candidates = [row for row in records if row.get("shadow_only") is True]
        if candidates:
            row = dict(candidates[-1])
            row["semantics"] = "shadow-only cross-issuer lead; excluded from basis"
            leads.append(row)
    as_of_values = [str(row.get("as_of")) for row in leads if row.get("as_of")]
    return {"available": True, "shadow_leads": leads, "as_of": max(as_of_values) if as_of_values else None}


def read_probe_outputs(path: Path, current_health: str) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "chains": [], "current_health": current_health, "as_of": None}
    files = [path] if path.is_file() else sorted(path.glob("**/probe_*.txt"), key=lambda p: p.stat().st_mtime)
    chains: list[dict[str, Any]] = []
    for probe in files[-10:]:
        try:
            lines = probe.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        chain = probe.stem.removeprefix("probe_") or "unknown"
        endpoints = []
        for line in lines:
            match = re.search(r"\b(UP|DOWN|FAIL)\b.*?(https?://\S+)", line)
            if not match:
                continue
            endpoint = urlsplit(match.group(2).rstrip(",;"))
            hostname = endpoint.hostname
            if not hostname:
                continue
            try:
                port = endpoint.port
            except ValueError:
                continue
            safe_host = f"[{hostname}]" if ":" in hostname else hostname
            safe_netloc = f"{safe_host}:{port}" if port is not None else safe_host
            endpoints.append({
                # Probe URLs may carry provider credentials in the userinfo,
                # path or query.  The panel only needs the canonical origin.
                "endpoint": f"{endpoint.scheme.lower()}://{safe_netloc}",
                "status": "UP" if match.group(1) == "UP" else "DOWN",
                "cooldown": "not_persisted",
                "recent_429_count": sum("429" in item for item in lines),
            })
        chains.append({"chain": chain, "endpoints": endpoints, "as_of": file_timestamp(probe)})
    as_of_values = [item["as_of"] for item in chains if item.get("as_of")]
    return {
        "available": bool(chains), "chains": chains, "current_health": current_health,
        "as_of": max(as_of_values) if as_of_values else None,
    }


class StateBuilder:
    def __init__(self, *, db: Path, heartbeat: Path, portfolio_csv: Path, rwa_dir: Path, probe_dir: Path):
        self.db = db
        self.heartbeat = heartbeat
        self.portfolio_csv = portfolio_csv
        self.rwa_dir = rwa_dir
        self.probe_dir = probe_dir

    def build(self) -> dict[str, Any]:
        gate = {"status": "UNKNOWN", "checks": {}, "rpc_health": "UNKNOWN"}
        funnel = {"cycle_as_of": None, "screened": 0, "top": 0, "resolved": 0, "scored": 0, "accepted": 0, "gate_rejections": {}, "rejection_reasons": {}}
        rwa = {"symbols": [], "as_of": None}
        db_error = None
        netcover_by_pool: dict[str, dict[str, Any]] = {}
        try:
            with contextlib.closing(open_sqlite_readonly(self.db)) as connection:
                gate = read_gate(connection)
                funnel = read_funnel(connection)
                rwa = read_rwa_db(connection)
                netcover_by_pool = read_latest_netcover(connection)
        except (OSError, sqlite3.Error, ValueError) as exc:
            db_error = type(exc).__name__
        heartbeat = read_heartbeat(self.heartbeat)
        portfolio_csv = read_portfolio_csv(self.portfolio_csv)
        for position in heartbeat["positions"]:
            if isinstance(position, dict):
                netcover = netcover_by_pool.get(str(position.get("pool", "")), {})
                position.setdefault("netcover_ratio", netcover.get("netcover_ratio"))
                position.setdefault("netcover_gate_status", netcover.get("netcover_gate_status"))
        if not heartbeat["series"] and portfolio_csv["rows"]:
            heartbeat["series"] = [
                {
                    "as_of": row.get("ts_utc"),
                    "portfolio_nav_usd": None,
                    "portfolio_net_usd": _finite(row.get("portfolio_net_usd")),
                }
                for row in portfolio_csv["rows"]
            ]
        leads = read_rwa_leads(self.rwa_dir)
        for symbol in rwa.get("symbols", []):
            symbol["shadow_leads"] = [
                lead for lead in leads["shadow_leads"]
                if str(lead.get("instrument_id", "")).split(":")[-1].upper().startswith(str(symbol["symbol"]).upper().removesuffix("X"))
            ]
        rpc = read_probe_outputs(self.probe_dir, str(gate.get("rpc_health", "UNKNOWN")))
        sources = {
            "scanner_db": {"status": "尚未开始" if db_error else "OK", "last_update": funnel.get("cycle_as_of") or rwa.get("as_of"), "error": db_error},
            "heartbeat": {"status": "OK" if heartbeat["available"] else "尚未开始", "last_update": heartbeat.get("as_of") or file_timestamp(self.heartbeat)},
            "portfolio_csv": {"status": "OK" if portfolio_csv["available"] else "尚未开始", "last_update": portfolio_csv.get("as_of") or file_timestamp(self.portfolio_csv)},
            "rwa_jsonl": {"status": "OK" if leads["available"] else "尚未开始", "last_update": leads.get("as_of")},
            "rpc_probe": {"status": "OK" if rpc["available"] else "尚未开始", "last_update": rpc.get("as_of")},
        }
        return scrub_payload({
            "as_of": utc_now(),
            "mode": "PAPER / READ-ONLY — 无钱包无签名",
            "sources": sources,
            "gate": gate,
            "nav_series": heartbeat["series"],
            "positions": heartbeat["positions"],
            "funnel": funnel,
            "rwa": rwa,
            "rpc": rpc,
        })


class RateLimiter:
    def __init__(self, limit: int = DEFAULT_RATE_LIMIT, window_secs: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self.limit = int(limit)
        self.window_secs = float(window_secs)
        self.clock = clock
        self._requests: dict[str, collections.deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, address: str) -> bool:
        now = self.clock()
        with self._lock:
            bucket = self._requests.setdefault(address, collections.deque())
            while bucket and bucket[0] <= now - self.window_secs:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True


class AccessLogger:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def write(self, ip: str, request_path: str, status: int, note: str = "") -> None:
        safe_path = urlsplit(request_path).path[:256].replace("\n", "_").replace("\r", "_")
        line = f"{utc_now()} ip={ip} path={safe_path} status={int(status)}"
        if note:
            line += f" note={note.replace(chr(10), '_').replace(chr(13), '_')}"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")


class PanelHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], *, state_builder: StateBuilder, token_digest: Optional[bytes], access_logger: AccessLogger, rate_limiter: RateLimiter, request_timeout_secs: float, refresh_secs: int, request_queue_size: int, max_threads: int):
        if request_queue_size < 1 or max_threads < 1:
            raise ValueError("request_queue_size and max_threads must be positive")
        # TCPServer.server_activate reads this instance attribute when calling
        # listen(), so it must be assigned before the superclass constructor.
        self.request_queue_size = request_queue_size
        self.max_threads = max_threads
        self._worker_slots = threading.BoundedSemaphore(max_threads)
        self._worker_count = 0
        self._worker_count_lock = threading.Lock()
        super().__init__(address, PanelHandler)
        self.state_builder = state_builder
        self.token_digest = token_digest
        self.access_logger = access_logger
        self.rate_limiter = rate_limiter
        self.request_timeout_secs = request_timeout_secs
        self.refresh_secs = refresh_secs

    @property
    def active_worker_count(self) -> int:
        with self._worker_count_lock:
            return self._worker_count

    def process_request(self, request: Any, client_address: tuple[str, int]) -> None:
        if not self._worker_slots.acquire(blocking=False):
            self._reject_overloaded(request, client_address)
            return
        with self._worker_count_lock:
            self._worker_count += 1
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._release_worker_slot()
            raise

    def process_request_thread(self, request: Any, client_address: tuple[str, int]) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._release_worker_slot()

    def _release_worker_slot(self) -> None:
        with self._worker_count_lock:
            self._worker_count -= 1
        self._worker_slots.release()

    def _reject_overloaded(self, request: Any, client_address: tuple[str, int]) -> None:
        body = b'{"error":"server overloaded"}'
        response = (
            b"HTTP/1.1 503 Service Unavailable\r\n"
            b"Content-Type: application/json; charset=utf-8\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"Cache-Control: no-store\r\nConnection: close\r\n\r\n"
            + body
        )
        try:
            request.sendall(response)
        except OSError:
            pass
        self.access_logger.write(client_address[0], "/", HTTPStatus.SERVICE_UNAVAILABLE, "MAX_THREADS")
        self.shutdown_request(request)


class PanelHandler(BaseHTTPRequestHandler):
    server: PanelHTTPServer
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(self.server.request_timeout_secs)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)
        self.server.access_logger.write(self.client_address[0], self.path, status)

    def _json_error(self, status: int, message: str) -> None:
        self._send(status, json.dumps({"error": message}, separators=(",", ":")).encode(), "application/json; charset=utf-8")

    def _authorized(self, query: Mapping[str, list[str]]) -> bool:
        expected = self.server.token_digest
        if expected is None:
            return True
        supplied = self.headers.get("X-Panel-Token")
        if supplied is None:
            values = query.get("token", [])
            supplied = values[0] if values else ""
        digest = hashlib.sha256(supplied.encode("utf-8", errors="ignore")).digest()
        return hmac.compare_digest(expected, digest)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path not in ALLOWED_PATHS:
            self._json_error(HTTPStatus.NOT_FOUND, "not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json_error(HTTPStatus.BAD_REQUEST, "invalid content length")
            return
        if length < 0 or length > MAX_REQUEST_BODY_BYTES:
            self.close_connection = True
            self._json_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body too large")
            return
        if length:
            self.close_connection = True
        if not self.server.rate_limiter.allow(self.client_address[0]):
            self._json_error(HTTPStatus.TOO_MANY_REQUESTS, "rate limit exceeded")
            return
        try:
            query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=8)
        except ValueError:
            self._json_error(HTTPStatus.BAD_REQUEST, "invalid query")
            return
        if not self._authorized(query):
            self._json_error(HTTPStatus.UNAUTHORIZED, "authentication required")
            return
        if parsed.path == "/api/state.json":
            payload = scrub_payload(self.server.state_builder.build())
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
            self._send(HTTPStatus.OK, body, "application/json; charset=utf-8")
            return
        body = PANEL_HTML.replace("__REFRESH_SECONDS__", str(self.server.refresh_secs)).encode("utf-8")
        self._send(HTTPStatus.OK, body, "text/html; charset=utf-8")

    def _method_not_allowed(self) -> None:
        self.close_connection = True
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "GET")
        body = b'{"error":"method not allowed"}'
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.server.access_logger.write(self.client_address[0], self.path, HTTPStatus.METHOD_NOT_ALLOWED)

    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_PATCH = _method_not_allowed


PANEL_HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LP Bot M0 Shadow Panel</title><style>
:root{color-scheme:dark;--bg:#0b1020;--card:#151d32;--line:#2b3757;--fg:#e8edf8;--muted:#9ba8c5;--good:#39d98a;--bad:#ff6577;--warn:#f7c948}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif}header{position:sticky;top:0;background:#111a30;padding:14px 3vw;border-bottom:1px solid var(--line);z-index:2}.banner{font-weight:800;color:var(--warn);letter-spacing:.06em}.meta{color:var(--muted);margin-top:6px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px;padding:18px 3vw}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:15px;overflow:auto}.wide{grid-column:1/-1}h2{font-size:16px;margin:0 0 12px}.lights{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:8px}.light{border-left:5px solid var(--warn);background:#10182b;padding:9px}.light.PASS{border-color:var(--good)}.light.FAIL{border-color:var(--bad)}.value{font-size:20px;font-weight:700}.small{color:var(--muted);font-size:12px}table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid var(--line);padding:7px;vertical-align:top}canvas{width:100%;height:260px;background:#10182b}details{margin:5px 0}code{white-space:pre-wrap}.pill{display:inline-block;padding:2px 7px;border-radius:12px;background:#263453;margin:2px}.error{color:var(--bad)}
</style></head><body><header><div class="banner">PAPER / READ-ONLY — 无钱包无签名</div><div class="meta" id="meta">加载中…</div></header><main class="grid">
<section class="card wide"><h2>Gate 六项红绿灯（唯一 identity 与唯一 root pool 分列）</h2><div class="lights" id="gate"></div></section>
<section class="card wide"><h2>净值与回撤曲线（NAV 与 Net 分离）</h2><canvas id="chart" width="1200" height="260"></canvas></section>
<section class="card wide"><h2>当前持仓 · 23 字段归因账本</h2><div id="positions"></div></section>
<section class="card"><h2>漏斗健康与逐闸拒绝</h2><div id="funnel"></div></section>
<section class="card"><h2>RWA 三锚 / session / basis</h2><div id="rwa"></div></section>
<section class="card wide"><h2>RPC 健康 / 冷却 / 429 / 状态机</h2><div id="rpc"></div></section>
</main><script>
const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>typeof x==='number'?x.toLocaleString(undefined,{maximumFractionDigits:4}):esc(x);
function draw(rows){const c=document.querySelector('#chart'),x=c.getContext('2d');x.clearRect(0,0,c.width,c.height);const vals=rows.flatMap(r=>[r.portfolio_nav_usd,r.portfolio_net_usd]).filter(Number.isFinite);if(!vals.length){x.fillStyle='#9ba8c5';x.fillText('尚未开始',20,30);return}const lo=Math.min(...vals),hi=Math.max(...vals),span=hi-lo||1;[['portfolio_nav_usd','#39d98a'],['portfolio_net_usd','#f7c948']].forEach(([k,color])=>{x.strokeStyle=color;x.beginPath();rows.forEach((r,i)=>{const v=r[k];if(!Number.isFinite(v))return;const px=20+i*(c.width-40)/Math.max(1,rows.length-1),py=230-(v-lo)*200/span;i?x.lineTo(px,py):x.moveTo(px,py)});x.stroke()});const dds=rows.map(r=>r.portfolio_drawdown_pct).filter(Number.isFinite),maxdd=Math.max(1,...dds);x.strokeStyle='#60a5fa';x.beginPath();rows.forEach((r,i)=>{const v=r.portfolio_drawdown_pct;if(!Number.isFinite(v))return;const px=20+i*(c.width-40)/Math.max(1,rows.length-1),py=30+v*200/maxdd;i?x.lineTo(px,py):x.moveTo(px,py)});x.stroke();x.fillStyle='#39d98a';x.fillText('portfolio_nav_usd',20,18);x.fillStyle='#f7c948';x.fillText('portfolio_net_usd',170,18);x.fillStyle='#60a5fa';x.fillText(`drawdown_pct (max ${maxdd.toFixed(2)}%)`,320,18)}
function render(s){document.querySelector('#meta').innerHTML=`as_of ${esc(s.as_of)} · `+Object.entries(s.sources).map(([k,v])=>`${esc(k)}: ${esc(v.status)} @ ${esc(v.last_update)}`).join(' · ');document.querySelector('#gate').innerHTML=Object.entries(s.gate.checks||{}).map(([k,v])=>`<div class="light ${esc(v.status)}"><b>${esc(k)}</b><div class="value">${fmt(v.value)}</div>${k==='simulated_positions'?`<div>identity ${fmt(v.unique_position_identities)} ≠ root pool ${fmt(v.unique_root_pools)}</div>`:''}<div class="small">${esc(v.threshold)} · ${esc(v.status)}</div></div>`).join('')||'尚未开始';draw(s.nav_series||[]);
document.querySelector('#positions').innerHTML=(s.positions||[]).map(p=>`<details><summary><b>${esc(p.symbol||p.pool)}</b> · PnL_vs_USDC ${fmt(p.pnl_vs_usdc)} · Alpha_vs_HODL ${fmt(p.alpha_vs_hodl)} · IL_vs_HODL ${fmt(p.il_vs_hodl_usd)} · NetCover ${fmt(p.netcover_ratio)} · range ${esc(p.in_range)} · risk ${esc(p.risk_state)}</summary><code>${esc(JSON.stringify(p,null,2))}</code></details>`).join('')||'尚未开始';
const f=s.funnel||{};document.querySelector('#funnel').innerHTML=`<p>${['screened','top','resolved','scored','accepted'].map(k=>`<span class="pill">${k}: ${fmt(f[k])}</span>`).join('')}</p><h3>逐闸拒绝</h3><table>${Object.entries(f.gate_rejections||{}).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${fmt(v)}</td></tr>`).join('')}</table><h3>最终拒绝原因</h3><table>${Object.entries(f.rejection_reasons||{}).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${fmt(v)}</td></tr>`).join('')}</table>`;
document.querySelector('#rwa').innerHTML=(s.rwa.symbols||[]).map(r=>`<details><summary>${esc(r.symbol)} · ${esc(r.session)}</summary><table>${(r.anchors||[]).map(a=>`<tr><td>${esc(a.source)}</td><td>${a.available?'UP':'UNAVAILABLE'}</td><td>basis ${fmt(a.basis_bps)}</td><td>${esc(a.basis_semantics)}</td></tr>`).join('')}</table><div class="small">shadow-only 跨发行商 lead，不计入 basis：${esc(JSON.stringify(r.shadow_leads||[]))}</div></details>`).join('')||'尚未开始';
document.querySelector('#rpc').innerHTML=`<p>当前健康态：<b>${esc(s.rpc.current_health)}</b></p>`+(s.rpc.chains||[]).map(c=>`<details><summary>${esc(c.chain)} @ ${esc(c.as_of)}</summary><table>${(c.endpoints||[]).map(e=>`<tr><td>${esc(e.endpoint)}</td><td>${esc(e.status)}</td><td>cooldown ${esc(e.cooldown)}</td><td>429 ${fmt(e.recent_429_count)}</td></tr>`).join('')}</table></details>`).join('')||'尚未开始'}
async function poll(){try{const token=new URLSearchParams(location.search).get('token');const u='/api/state.json'+(token?'?token='+encodeURIComponent(token):'');const r=await fetch(u,{cache:'no-store'});if(!r.ok)throw Error(`HTTP ${r.status}`);render(await r.json())}catch(e){document.querySelector('#meta').innerHTML=`<span class="error">${esc(e)}</span>`}}poll();setInterval(poll,__REFRESH_SECONDS__*1000);
</script></body></html>'''


def _token_strength_error(token: str) -> Optional[str]:
    """Return a reason for obviously guessable tokens; never estimate provenance."""
    if len(token) < MIN_TOKEN_LENGTH:
        return f"must contain at least {MIN_TOKEN_LENGTH} characters"
    if len(set(token)) < 10:
        return "has too few distinct characters"
    lowered = token.lower()
    if any(word in lowered for word in ("password", "changeme", "paneltoken", "secretsecret")):
        return "contains a common placeholder pattern"
    # Reject exact repetition of a short seed (for example ``abcd`` * 8).
    for period in range(1, min(16, len(token) // 2) + 1):
        if len(token) % period == 0 and token == token[:period] * (len(token) // period):
            return f"repeats a {period}-character pattern"
    frequencies = collections.Counter(token)
    entropy_bits_per_character = -sum(
        (count / len(token)) * math.log2(count / len(token))
        for count in frequencies.values()
    )
    if entropy_bits_per_character < 3.0:
        return "has insufficient character diversity"
    return None


def build_server(args: argparse.Namespace) -> PanelHTTPServer:
    token_digest: Optional[bytes] = None
    logger = AccessLogger(Path(args.access_log))
    if args.no_auth:
        warning = "WARNING: LP panel authentication DISABLED; bind is externally visible"
        print(warning, file=sys.stderr, flush=True)
        logger.write("startup", "/", 0, "NO_AUTH_ENABLED")
    else:
        token = os.environ.get(TOKEN_ENV, "")
        strength_error = _token_strength_error(token)
        if strength_error:
            raise SystemExit(
                f"{TOKEN_ENV} {strength_error}; generate a strong token with: openssl rand -hex 32"
            )
        token_digest = hashlib.sha256(token.encode("utf-8")).digest()
    builder = StateBuilder(
        db=Path(args.db), heartbeat=Path(args.heartbeat), portfolio_csv=Path(args.portfolio_csv),
        rwa_dir=Path(args.rwa_jsonl_dir), probe_dir=Path(args.probe_dir),
    )
    return PanelHTTPServer(
        (args.host, args.port), state_builder=builder, token_digest=token_digest,
        access_logger=logger, rate_limiter=RateLimiter(args.rate_limit),
        request_timeout_secs=args.request_timeout_secs, refresh_secs=args.refresh_secs,
        request_queue_size=args.request_queue_size, max_threads=args.max_threads,
    )


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="LP M0 paper/read-only evidence panel")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--heartbeat", default=str(DEFAULT_HEARTBEAT))
    ap.add_argument("--portfolio-csv", default=str(DEFAULT_PORTFOLIO_CSV))
    ap.add_argument("--rwa-jsonl-dir", default=str(DEFAULT_RWA_DIR))
    ap.add_argument("--probe-dir", default=str(DEFAULT_PROBE_DIR))
    ap.add_argument("--access-log", default=str(DEFAULT_ACCESS_LOG))
    ap.add_argument("--refresh-secs", type=int, default=10)
    ap.add_argument("--rate-limit", type=int, default=DEFAULT_RATE_LIMIT)
    ap.add_argument("--request-timeout-secs", type=float, default=DEFAULT_REQUEST_TIMEOUT_SECS)
    ap.add_argument("--request-queue-size", type=int, default=DEFAULT_REQUEST_QUEUE_SIZE)
    ap.add_argument("--max-threads", type=int, default=DEFAULT_MAX_THREADS)
    ap.add_argument("--no-auth", action="store_true")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be in 1..65535")
    if (
        args.refresh_secs < 1
        or args.rate_limit < 1
        or args.request_timeout_secs <= 0
        or args.request_queue_size < 1
        or args.max_threads < 1
    ):
        raise SystemExit("refresh/rate-limit/timeout/queue/thread values must be positive")
    server = build_server(args)
    print(f"LP panel PAPER/READ-ONLY listening on {args.host}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
