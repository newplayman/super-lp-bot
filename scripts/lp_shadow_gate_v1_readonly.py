#!/usr/bin/env python3
"""Persist and report PRD v2.1 section 12.0 paper-shadow evidence.

The module only writes local SQLite evidence.  It performs no network, wallet,
signing, simulation, or transaction work.  Existing scanner tables are never
altered: three additive tables share ``scanner.db`` so the operational gate can
be queried without joining report directories.

Fee prediction error is cumulative and capital weighted at each runner tick::

    abs(sum(actual_fee_usd) - sum(predicted_fee_usd))
    / sum(predicted_fee_usd) * 100

Every active position must expose a finite, strictly-positive cumulative fee
prediction.  Missing/zero/invalid prediction evidence yields UNKNOWN; it is
never interpreted as zero error.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "reports/lp_scanner/scanner.db"
SECONDS_PER_DAY = 86_400.0

GATE_THRESHOLDS = {
    "minimum_shadow_days": 14.0,
    "minimum_simulated_positions": 50,
    "maximum_fee_prediction_error_pct": 20.0,
    "minimum_shadow_net_pnl_usd_exclusive": 0.0,
    "maximum_simulated_drawdown_pct": 8.0,
    "maximum_unresolved_rpc_severe_incidents": 0,
}

_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS shadow_gate_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of TEXT NOT NULL,
    source_run TEXT NOT NULL,
    tick INTEGER NOT NULL,
    current_position_count INTEGER NOT NULL,
    portfolio_nav_usd REAL,
    predicted_fee_usd REAL,
    actual_fee_usd REAL,
    fee_prediction_error_pct REAL,
    fee_prediction_status TEXT NOT NULL CHECK (
        fee_prediction_status IN ('COMPLETE', 'UNKNOWN')
    ),
    shadow_net_pnl_usd REAL,
    simulated_drawdown_pct REAL,
    rpc_health TEXT NOT NULL,
    evidence_status TEXT NOT NULL CHECK (
        evidence_status IN ('COMPLETE', 'INCOMPLETE')
    ),
    evidence_json TEXT NOT NULL,
    UNIQUE(source_run, tick)
);
CREATE INDEX IF NOT EXISTS idx_shadow_gate_observations_as_of
    ON shadow_gate_observations(as_of);

CREATE TABLE IF NOT EXISTS shadow_positions (
    source_run TEXT NOT NULL,
    position_identity TEXT NOT NULL,
    first_seen_as_of TEXT NOT NULL,
    last_seen_as_of TEXT NOT NULL,
    PRIMARY KEY(source_run, position_identity)
);

CREATE TABLE IF NOT EXISTS rpc_severe_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    resolved_at TEXT,
    opening_health TEXT NOT NULL,
    resolution_health TEXT,
    evidence_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rpc_severe_one_open_per_source
    ON rpc_severe_incidents(source) WHERE resolved_at IS NULL;
"""


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_of(value: Any = None) -> str:
    if value is None:
        dt = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return dt.astimezone(timezone.utc).isoformat()


def _position_identity(pool: Mapping[str, Any], index: int) -> str:
    explicit = pool.get("position_id")
    address = pool.get("pool")
    if explicit:
        return str(explicit)
    if address:
        # A fixed runner allocation has one paper position per pool.  source_run
        # is part of the primary key, so restarts/runs do not collapse entries.
        return str(address).lower()
    symbol = pool.get("symbol")
    if symbol:
        return f"symbol:{symbol}:{index}"
    raise ValueError("paper position lacks position_id, pool, and symbol")


class GateStore:
    """Additive scanner.db evidence writer with idempotent runner ticks."""

    def __init__(self, path: str | Path = DEFAULT_DB_PATH):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def initialize_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def record_heartbeat(
        self, source_run: str, tick: int, heartbeat: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Persist one ledger-v2 heartbeat; duplicate run/tick is idempotent."""
        self.initialize_schema()
        stamp = _as_of(heartbeat.get("ts_utc"))
        pools = heartbeat.get("by_pool")
        if not isinstance(pools, list):
            raise ValueError("heartbeat by_pool must be a list")

        predictions: list[float] = []
        actuals: list[float] = []
        pnls: list[float] = []
        identities: list[str] = []
        prediction_complete = True
        pnl_complete = True
        for index, raw in enumerate(pools):
            if not isinstance(raw, Mapping):
                raise ValueError("heartbeat pool entry must be an object")
            identities.append(_position_identity(raw, index))
            predicted = _finite(raw.get("fee_prediction_usd"))
            actual = _finite(raw.get("swap_fee_income", raw.get("fees")))
            pnl = _finite(raw.get("pnl_vs_usdc"))
            if predicted is None or predicted <= 0.0 or actual is None:
                prediction_complete = False
            else:
                predictions.append(predicted)
                actuals.append(actual)
            if pnl is None:
                pnl_complete = False
            else:
                pnls.append(pnl)

        predicted_total = sum(predictions) if prediction_complete and pools else None
        actual_total = sum(actuals) if prediction_complete and pools else None
        fee_error = None
        if predicted_total is not None and predicted_total > 0.0 and actual_total is not None:
            fee_error = abs(actual_total - predicted_total) / predicted_total * 100.0
        fee_status = "COMPLETE" if fee_error is not None else "UNKNOWN"

        shadow_pnl = sum(pnls) if pnl_complete else None
        nav = _finite(heartbeat.get("portfolio_nav_usd"))
        if nav is None and shadow_pnl is not None:
            capital_values = [_finite(row.get("entry_capital_usd")) for row in pools]
            if all(value is not None for value in capital_values):
                nav = sum(value for value in capital_values if value is not None) + shadow_pnl
        rpc_health = str(heartbeat.get("rpc_health") or "UNKNOWN").upper()

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM shadow_gate_observations WHERE source_run=? AND tick=?",
                (str(source_run), int(tick)),
            ).fetchone()
            if existing is not None:
                return dict(existing)

            peak_row = connection.execute(
                "SELECT max(portfolio_nav_usd) FROM shadow_gate_observations WHERE source_run=?",
                (str(source_run),),
            ).fetchone()
            prior_peak = _finite(peak_row[0]) if peak_row else None
            running_peak = nav if prior_peak is None else (max(prior_peak, nav) if nav is not None else prior_peak)
            drawdown = None
            if nav is not None and running_peak is not None and running_peak > 0.0:
                drawdown = max(0.0, (running_peak - nav) / running_peak * 100.0)

            evidence_status = (
                "COMPLETE"
                if fee_status == "COMPLETE" and shadow_pnl is not None and nav is not None
                else "INCOMPLETE"
            )
            evidence = {
                "ledger_schema_version": heartbeat.get("ledger_schema_version"),
                "fee_prediction_formula": (
                    "abs(sum(actual_fee_usd)-sum(predicted_fee_usd))"
                    "/sum(predicted_fee_usd)*100"
                ),
                "position_identities": identities,
                "input_rpc_health": rpc_health,
            }
            connection.execute("BEGIN IMMEDIATE")
            for identity in identities:
                connection.execute(
                    """
                    INSERT INTO shadow_positions(
                        source_run, position_identity, first_seen_as_of, last_seen_as_of
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(source_run, position_identity) DO UPDATE
                    SET last_seen_as_of=excluded.last_seen_as_of
                    """,
                    (str(source_run), identity, stamp, stamp),
                )
            connection.execute(
                """
                INSERT INTO shadow_gate_observations(
                    as_of, source_run, tick, current_position_count,
                    portfolio_nav_usd, predicted_fee_usd, actual_fee_usd,
                    fee_prediction_error_pct, fee_prediction_status,
                    shadow_net_pnl_usd, simulated_drawdown_pct, rpc_health,
                    evidence_status, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stamp, str(source_run), int(tick), len(identities), nav,
                    predicted_total, actual_total, fee_error, fee_status,
                    shadow_pnl, drawdown, rpc_health, evidence_status,
                    json.dumps(evidence, sort_keys=True, separators=(",", ":")),
                ),
            )
            row = connection.execute(
                "SELECT * FROM shadow_gate_observations WHERE source_run=? AND tick=?",
                (str(source_run), int(tick)),
            ).fetchone()
        assert row is not None
        return dict(row)

    def record_rpc_health(
        self, health: str, *, as_of: Any = None, source: str = "scanner"
    ) -> None:
        self.initialize_schema()
        state = str(health).upper()
        stamp = _as_of(as_of)
        with self._connect() as connection:
            if state == "EXIT_ONLY":
                connection.execute(
                    """
                    INSERT OR IGNORE INTO rpc_severe_incidents(
                        source, opened_at, opening_health, evidence_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (source, stamp, state, json.dumps({"health": state}, sort_keys=True)),
                )
            elif state == "NORMAL":
                connection.execute(
                    """
                    UPDATE rpc_severe_incidents
                    SET resolved_at=?, resolution_health=?
                    WHERE source=? AND resolved_at IS NULL
                    """,
                    (stamp, state, source),
                )

    def unresolved_rpc_severe_count(self) -> int:
        self.initialize_schema()
        with self._connect() as connection:
            return int(
                connection.execute(
                    "SELECT count(*) FROM rpc_severe_incidents WHERE resolved_at IS NULL"
                ).fetchone()[0]
            )


def _status(value: Any, predicate, *, unknown_when_none: bool = True) -> str:
    if value is None and unknown_when_none:
        return "UNKNOWN"
    return "PASS" if predicate(value) else "FAIL"


def evaluate_shadow_gate(path: str | Path, *, as_of: Any = None) -> dict[str, Any]:
    """Evaluate exact section 12.0 thresholds from persisted evidence."""
    store = GateStore(path)
    store.initialize_schema()
    generated = _as_of(as_of)
    with store._connect() as connection:
        bounds = connection.execute(
            "SELECT min(as_of), max(as_of) FROM shadow_gate_observations"
        ).fetchone()
        position_count = int(connection.execute("SELECT count(*) FROM shadow_positions").fetchone()[0])
        latest = connection.execute(
            """
            SELECT observation.* FROM shadow_gate_observations observation
            JOIN (
                SELECT source_run, max(tick) AS tick
                FROM shadow_gate_observations GROUP BY source_run
            ) tail USING(source_run, tick)
            """
        ).fetchall()
        max_dd_row = connection.execute(
            "SELECT max(simulated_drawdown_pct) FROM shadow_gate_observations"
        ).fetchone()
        unresolved = int(connection.execute(
            "SELECT count(*) FROM rpc_severe_incidents WHERE resolved_at IS NULL"
        ).fetchone()[0])

    first_as_of = bounds[0] if bounds else None
    last_as_of = bounds[1] if bounds else None
    duration = None
    if first_as_of and last_as_of:
        duration = (
            datetime.fromisoformat(str(last_as_of)) - datetime.fromisoformat(str(first_as_of))
        ).total_seconds() / SECONDS_PER_DAY

    fee_error = None
    net_pnl = None
    if latest:
        predicted = [_finite(row["predicted_fee_usd"]) for row in latest]
        actual = [_finite(row["actual_fee_usd"]) for row in latest]
        pnls = [_finite(row["shadow_net_pnl_usd"]) for row in latest]
        statuses = [row["fee_prediction_status"] for row in latest]
        if all(status == "COMPLETE" for status in statuses) and all(v is not None for v in predicted + actual):
            predicted_total = sum(v for v in predicted if v is not None)
            actual_total = sum(v for v in actual if v is not None)
            if predicted_total > 0.0:
                fee_error = abs(actual_total - predicted_total) / predicted_total * 100.0
        if all(v is not None for v in pnls):
            net_pnl = sum(v for v in pnls if v is not None)
    max_dd = _finite(max_dd_row[0]) if max_dd_row else None

    checks = {
        "shadow_duration_days": {
            "value": duration,
            "threshold": ">= 14",
            "status": _status(duration, lambda v: v >= GATE_THRESHOLDS["minimum_shadow_days"]),
        },
        "simulated_positions": {
            "value": position_count,
            "threshold": ">= 50 unique (source_run, position_identity)",
            "status": _status(position_count if latest else None, lambda v: v >= 50),
        },
        "fee_prediction_error_pct": {
            "value": fee_error,
            "threshold": "< 20%",
            "status": _status(fee_error, lambda v: v < GATE_THRESHOLDS["maximum_fee_prediction_error_pct"]),
        },
        "shadow_net_pnl_usd": {
            "value": net_pnl,
            "threshold": "> 0",
            "status": _status(net_pnl, lambda v: v > 0.0),
        },
        "simulated_drawdown_pct": {
            "value": max_dd,
            "threshold": "< 8%",
            "status": _status(max_dd, lambda v: v < GATE_THRESHOLDS["maximum_simulated_drawdown_pct"]),
        },
        "rpc_severe_unresolved": {
            "value": unresolved,
            "threshold": "= 0",
            "status": _status(unresolved, lambda v: v == 0, unknown_when_none=False),
        },
    }
    statuses = {item["status"] for item in checks.values()}
    overall = "FAIL" if "FAIL" in statuses else ("INSUFFICIENT_EVIDENCE" if "UNKNOWN" in statuses else "PASS")
    return {
        "gate_schema_version": 1,
        "generated_at": generated,
        "source_db": str(Path(path)),
        "evidence_window": {"first_as_of": first_as_of, "last_as_of": last_as_of},
        "thresholds": dict(GATE_THRESHOLDS),
        "checks": checks,
        "overall_status": overall,
        "authorization": "evidence_only_not_M1_authorization",
    }


def build_gate_report_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# M0 Shadow §12.0 Gate Report",
        "",
        f"_generated {report.get('generated_at')} · evidence-only · read-only/paper-only_",
        "",
        f"Overall: **{report.get('overall_status')}**",
        "",
        "Fee formula: `fee_prediction_error_pct = abs(actual - predicted) / predicted * 100`。",
        "缺失、非有限、零或负预测值均记为 `UNKNOWN`，绝不记作 0% 误差。",
        "模拟仓按唯一 `(source_run, position_identity)` 计数，重复 tick 不增加仓数。",
        "",
        "| Check | Value | Threshold | Status |",
        "|---|---:|---:|---|",
    ]
    for name, item in report.get("checks", {}).items():
        value = item.get("value")
        rendered = "—" if value is None else f"{value:.6g}" if isinstance(value, float) else str(value)
        lines.append(f"| {name} | {rendered} | {item.get('threshold')} | {item.get('status')} |")
    lines.extend([
        "",
        "此报告只汇总 M0 shadow 证据，不授权 M1、签名、广播或任何真实交易。",
        "",
    ])
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate PRD v2.1 section 12.0 gate report")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--out", default=None)
    parser.add_argument("--json-out", default=None)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    report = evaluate_shadow_gate(args.db)
    out = Path(args.out) if args.out else REPO_ROOT / "reports/lp_shadow_gate/latest/gate_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_gate_report_markdown(report), encoding="utf-8")
    if args.json_out:
        json_path = Path(args.json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{report['overall_status']} {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
