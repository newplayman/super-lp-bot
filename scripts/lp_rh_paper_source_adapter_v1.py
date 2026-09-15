"""
Paper source adapter — read real read-only market data instead of synthetic fixtures.

Owner directive (NEXT_AGENT_TASK_CN.md §1):
  - Move synthetic fallback out of production path
  - Normal CLI source must come from config-specified read-only DB
  - Bind chain_id, pool_address, source schema, source event time, data validity policy, cursor
  - Source missing/structured wrong/identity unknown → BLOCKED_DATA
  - Source normal but no new events since cursor → NO_NEW_DATA
  - Don't quietly run fixture, don't fake current time, don't treat old as new

This module is pure read-only — opens the source DB with mode=ro.  No writes
to scanner.db; only writes go to the local ledger DB's `rh_paper_cursor` table
(created by the daemon entry, NOT here).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

# Allowed exit codes / status strings
EXIT_BLOCKED_DATA = 2  # source unusable; do not retry without intervention
EXIT_NO_NEW_DATA = 0   # source OK but no new events since cursor; not an error

REQUIRED_SOURCE_KEYS = (
    "db_path",
    "events_table",
    "chain_id",
    "pool_address",
    "expected_interval_secs",
    "lookback_hours",
)

REQUIRED_EVENT_COLUMNS = (
    "asset_address",
    "sample_time",
    "chain_id",
    "reference_mid",
    "fee_growth_global_0",
    "fee_growth_global_1",
)


class SourceConfigError(Exception):
    """Source section missing/structured wrong."""


class SourceSchemaError(Exception):
    """Source DB missing table or required columns."""


class SourceIdentityError(Exception):
    """Source events have wrong chain_id or asset_address."""


class SourceFreshnessError(Exception):
    """Source events all older than lookback or in the future."""


@dataclass
class PaperSourceAdapter:
    """Reads real market events from a configured read-only DB.

    All access is via a fresh sqlite3 connection in mode=ro.  This module
    performs no writes to the source DB; cursor state is held by the caller
    (the daemon entry writes to its own ledger DB).
    """
    db_path: str
    events_table: str
    chain_id: int
    pool_address: str
    expected_interval_secs: int
    lookback_hours: int
    profile_horizon_hours: int = 24  # frozen profile horizon
    min_event_interval_secs: int = 60

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "PaperSourceAdapter":
        src = cfg.get("source")
        if not isinstance(src, dict):
            raise SourceConfigError("config missing [source] section")
        missing_keys = [k for k in REQUIRED_SOURCE_KEYS if k not in src]
        if missing_keys:
            raise SourceConfigError(
                f"source section missing keys: {missing_keys}"
            )
        profile = cfg.get("profile") or {}
        horizon = int(profile.get("horizon_hours", 24))
        if horizon <= 0 or horizon > 168:
            raise SourceConfigError(
                f"profile.horizon_hours must be in (0, 168]; got {horizon}"
            )
        min_evt = int(profile.get("min_event_interval_secs", 60))
        if min_evt <= 0:
            raise SourceConfigError(
                f"profile.min_event_interval_secs must be > 0; got {min_evt}"
            )
        return cls(
            db_path=str(src["db_path"]),
            events_table=str(src["events_table"]),
            chain_id=int(src["chain_id"]),
            pool_address=str(src["pool_address"]),
            expected_interval_secs=int(src["expected_interval_secs"]),
            lookback_hours=int(src["lookback_hours"]),
            profile_horizon_hours=horizon,
            min_event_interval_secs=min_evt,
        )

    def _open(self) -> sqlite3.Connection:
        if not Path(self.db_path).is_file():
            raise SourceConfigError(f"source db not found: {self.db_path}")
        try:
            return sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise SourceConfigError(f"cannot open source db read-only: {exc}")

    def _validate_schema(self, conn: sqlite3.Connection) -> None:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (self.events_table,),
        )
        if cur.fetchone() is None:
            raise SourceSchemaError(
                f"source table missing: {self.events_table}"
            )
        cols = {
            r[1]
            for r in conn.execute(f"PRAGMA table_info({self.events_table})").fetchall()
        }
        missing_cols = [c for c in REQUIRED_EVENT_COLUMNS if c not in cols]
        if missing_cols:
            raise SourceSchemaError(
                f"source table {self.events_table} missing columns: {missing_cols}"
            )

    def validate(self) -> dict[str, Any]:
        """Open + schema check.  Returns evidence dict."""
        conn = self._open()
        try:
            self._validate_schema(conn)
            row = conn.execute(
                f"SELECT COUNT(*), MIN(sample_time), MAX(sample_time) "
                f"FROM {self.events_table} "
                f"WHERE chain_id=? AND asset_address=?",
                (self.chain_id, self.pool_address),
            ).fetchone()
            n_events = int(row[0]) if row and row[0] is not None else 0
            first = str(row[1]) if row and row[1] is not None else None
            last = str(row[2]) if row and row[2] is not None else None
            if n_events == 0:
                raise SourceIdentityError(
                    f"no events for chain_id={self.chain_id} "
                    f"asset_address={self.pool_address} in {self.db_path}"
                )
            return {
                "ok": True,
                "db_path": self.db_path,
                "events_table": self.events_table,
                "n_events": n_events,
                "first_sample_time": first,
                "last_sample_time": last,
            }
        finally:
            conn.close()

    def read_new_events(
        self,
        since_event_time: str | None,
        *,
        now_iso: str | None = None,
        max_events: int = 1024,
    ) -> list[dict[str, Any]]:
        """Return events strictly newer than since_event_time (exclusive).

        If since_event_time is None, start from now-lookback_hours.
        Events are ordered by sample_time ASC.  Identity (chain_id, asset_address)
        and key fields (reference_mid, fee_growth_global_0/1) are filtered.

        `now_iso` is passed in (NOT utcnow()) so the caller controls clock — no
        fake 'now' in the adapter.  Future-dated events are dropped.
        """
        if now_iso is None:
            now_iso = datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            )
        now_dt = _to_dt(now_iso)
        if now_dt is None:
            raise SourceConfigError(f"invalid now_iso: {now_iso!r}")

        if since_event_time is None:
            since_dt = now_dt.timestamp() - self.lookback_hours * 3600
            since_iso = _from_ts(since_dt)
        else:
            since_iso = since_event_time

        conn = self._open()
        try:
            self._validate_schema(conn)
            sql = (
                f"SELECT sample_time, reference_mid, session, "
                f"fee_growth_global_0, fee_growth_global_1, "
                f"reference_bid, reference_ask, source_event_time "
                f"FROM {self.events_table} "
                f"WHERE chain_id=? AND asset_address=? "
                f"AND sample_time > ? AND sample_time <= ? "
                f"AND reference_mid IS NOT NULL "
                f"AND fee_growth_global_0 IS NOT NULL "
                f"AND fee_growth_global_1 IS NOT NULL "
                f"ORDER BY sample_time ASC LIMIT ?"
            )
            rows = conn.execute(
                sql,
                (
                    self.chain_id,
                    self.pool_address,
                    since_iso,
                    now_iso,
                    int(max_events),
                ),
            ).fetchall()
        finally:
            conn.close()

        out: list[dict[str, Any]] = []
        for r in rows:
            sample_time = str(r[0])
            evt_dt = _to_dt(sample_time)
            if evt_dt is None or evt_dt > now_dt:
                continue  # malformed or future-dated, drop
            out.append(
                {
                    "sample_time": sample_time,
                    "reference_mid": str(r[1]),
                    "session": str(r[2] or ""),
                    "fee_growth_global_0": str(r[3]),
                    "fee_growth_global_1": str(r[4]),
                    "reference_bid": str(r[5]) if r[5] is not None else "",
                    "reference_ask": str(r[6]) if r[6] is not None else "",
                    "source_event_time": str(r[7]) if r[7] is not None else sample_time,
                }
            )
        return out

    def read_source_health(self) -> dict[str, Any]:
        """Read-only health snapshot for the source.

        Returns counts and null-ratios for the configured (chain_id, asset_address)
        window.  Used by status() and isolated diagnostics — does NOT change
        source DB state.
        """
        conn = self._open()
        try:
            self._validate_schema(conn)
            base = (
                f"FROM {self.events_table} "
                f"WHERE chain_id=? AND asset_address=?"
            )
            row = conn.execute(
                f"SELECT COUNT(*), MIN(sample_time), MAX(sample_time) {base}",
                (self.chain_id, self.pool_address),
            ).fetchone()
            n = int(row[0]) if row and row[0] is not None else 0
            first = str(row[1]) if row and row[1] is not None else None
            last = str(row[2]) if row and row[2] is not None else None
            nulls = {}
            for col in REQUIRED_EVENT_COLUMNS:
                if col in ("asset_address", "sample_time", "chain_id"):
                    continue
                cnt = conn.execute(
                    f"SELECT COUNT(*) {base} AND {col} IS NULL",
                    (self.chain_id, self.pool_address),
                ).fetchone()[0]
                nulls[col] = int(cnt)
            return {
                "db_path": self.db_path,
                "events_table": self.events_table,
                "chain_id": self.chain_id,
                "pool_address": self.pool_address,
                "n_events": n,
                "first_sample_time": first,
                "last_sample_time": last,
                "nulls_per_col": nulls,
                "expected_interval_secs": self.expected_interval_secs,
                "lookback_hours": self.lookback_hours,
            }
        finally:
            conn.close()


def _to_dt(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _from_ts(ts: float) -> str:
    return (
        datetime.fromtimestamp(ts, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )