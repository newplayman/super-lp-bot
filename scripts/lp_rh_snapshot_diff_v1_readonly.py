#!/usr/bin/env python3
"""RH-08d: frozen-snapshot gate diff (read-only, offline).

Proves a gate-logic change has NOT silently changed verdicts on a fixed
historical snapshot (PRD: 旧 Base 固定快照可复现).  freeze_snapshot backs up a
live DB read-only; replay_gates runs the RH Shadow loop over it; diff_replays
compares two replays step-by-step, gate-by-gate.  A baseline records which git
revision and frozen moment produced it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.lp_rh_shadow_runner_v1_readonly import (
    DEFAULT_POOL, load_samples_from_db, run_episode,
)
from scripts.lp_rh_store_v1_readonly import migrate, open_store

# Fixed clock so a replay is reproducible: market_and_chain_risk_pass reads the
# session and health, both of which depend on the clock.
REPLAY_NOW = "2026-01-01T00:00:00Z"
REPLAY_EPISODE = "rh-snapshot-diff"
REPLAY_TARGET_MODE = "SHADOW_SCENARIO"

# Per-step scalar fields diff_replays compares; terminal_bits is compared
# gate-by-gate, so its keys are flattened in separately.
_SCALAR_FIELDS = ("step_index", "sample_time", "primary_status",
                  "dominant_blocker")


def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head() -> str:
    """Current git HEAD, or 'unknown' when git is unavailable (offline test)."""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=10)
        head = out.stdout.strip()
        return head if head else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _table_row_counts(conn: sqlite3.Connection) -> dict:
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in tables}


def freeze_snapshot(src_db, dst_path) -> dict:
    """Consistent SQLite backup of a live DB to dst_path.  Source is read-only.

    Uses the online backup API (reads pages, never VACUUMs, never writes the
    source).  Returns per-table row counts, the snapshot sha256, and the
    freeze timestamp.
    """
    src_db = Path(src_db)
    dst_path = Path(dst_path)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{src_db}?mode=ro", uri=True)
    dest = sqlite3.connect(dst_path)
    try:
        source.backup(dest)
        dest.commit()
    finally:
        source.close()
        dest.close()
    ro = sqlite3.connect(f"file:{dst_path}?mode=ro", uri=True)
    try:
        rows = _table_row_counts(ro)
    finally:
        ro.close()
    sha = hashlib.sha256(dst_path.read_bytes()).hexdigest()
    return {"rows": rows, "sha256": sha, "frozen_at": _utc_now_rfc3339()}


def replay_gates(snapshot_db, *, pool, samples, position_usd, capital_usd,
                 horizon_hours, pool_meta=None) -> list:
    """Replay the RH Shadow closed loop over a frozen snapshot.

    The snapshot is opened read-only; every Shadow write goes to a throwaway
    store in a temp dir, so the snapshot file is never modified.  Returns one
    dict per step (index, sample time, status, blocker, terminal bits).  A
    fixed clock (REPLAY_NOW) keeps the replay reproducible.
    """
    position_usd = (position_usd if isinstance(position_usd, Decimal)
                    else Decimal(str(position_usd)))
    capital_usd = (capital_usd if isinstance(capital_usd, Decimal)
                   else Decimal(str(capital_usd)))
    snap = open_store(Path(snapshot_db), read_only=True)
    try:
        loaded, _skipped = load_samples_from_db(snap, pool=pool, limit=samples)
    finally:
        snap.close()
    if not loaded:
        return []
    with tempfile.TemporaryDirectory() as tmpdir:
        scratch = open_store(Path(tmpdir) / "scratch.db", read_only=False)
        migrate(scratch)
        try:
            steps = run_episode(
                scratch, strategy_episode=REPLAY_EPISODE, samples=loaded,
                position_usd=position_usd, horizon_hours=horizon_hours,
                capital_usd=capital_usd, target_mode=REPLAY_TARGET_MODE,
                now_fn=lambda: REPLAY_NOW, pool_meta=pool_meta)
            scratch.commit()
            bits_rows = scratch.execute(
                "SELECT terminal_bits_json FROM rh_gate_decisions "
                "ORDER BY rowid").fetchall()
        finally:
            scratch.close()
    out: list = []
    for step, (bits_json,) in zip(steps, bits_rows):
        out.append({
            "step_index": step.step_index,
            "sample_time": step.sample_time,
            "primary_status": step.primary_status,
            "dominant_blocker": step.dominant_blocker,
            "terminal_bits": json.loads(bits_json) if bits_json else {},
        })
    return out


def diff_replays(baseline, current) -> dict:
    """Step-by-step, gate-by-gate comparison of two replays.

    A step-count mismatch is reported, never force-aligned (padding or
    truncating would hide the drift this diff exists to catch).  Each differing
    field (scalar or terminal-gate bit) is one entry in changed_steps.
    """
    if len(baseline) != len(current):
        return {"error": "STEP_COUNT_MISMATCH",
                "baseline_steps": len(baseline),
                "current_steps": len(current)}
    n_steps = len(baseline)
    changed_steps: list = []
    status_transitions: dict = {}
    for i in range(n_steps):
        b, c = baseline[i], current[i]
        for field in _SCALAR_FIELDS:
            if b.get(field) != c.get(field):
                changed_steps.append({"step_index": i, "field": field,
                                      "from": b.get(field),
                                      "to": c.get(field)})
        bb = b.get("terminal_bits") or {}
        cb = c.get("terminal_bits") or {}
        for gate in sorted(set(bb) | set(cb)):
            if bb.get(gate) != cb.get(gate):
                changed_steps.append({"step_index": i, "field": gate,
                                      "from": bb.get(gate),
                                      "to": cb.get(gate)})
        bs, cs = b.get("primary_status"), c.get("primary_status")
        if bs != cs:
            key = f"{bs}->{cs}"
            status_transitions[key] = status_transitions.get(key, 0) + 1
    return {
        "n_steps": n_steps,
        "identical": not changed_steps,
        "changed_steps": changed_steps,
        "changed_count": len(changed_steps),
        "status_transitions": status_transitions,
    }


def save_baseline(replay, path, *, git_head: Optional[str] = None,
                  frozen_at: Optional[str] = None) -> dict:
    """Write a replay as a baseline JSON, recording its provenance.

    git_head and frozen_at are stored so a reader knows which revision and
    frozen moment produced the baseline (computed when omitted).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "git_head": git_head if git_head is not None else _git_head(),
        "frozen_at": frozen_at if frozen_at is not None else _utc_now_rfc3339(),
        "steps": replay,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
        fh.write("\n")
    return payload


def load_baseline(path) -> dict:
    """Read a baseline JSON written by save_baseline."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="RH-08d frozen-snapshot gate diff (read-only).")
    p.add_argument("--snapshot", required=True, help="frozen snapshot db")
    p.add_argument("--baseline", required=True, help="baseline JSON path")
    p.add_argument("--out", default=None, help="where to write the diff JSON")
    p.add_argument("--save-baseline", action="store_true",
                   help="save the current replay as the baseline and exit")
    p.add_argument("--pool", default=DEFAULT_POOL)
    p.add_argument("--samples", type=int, default=20)
    p.add_argument("--position-usd", default="1000")
    p.add_argument("--capital-usd", default="10000")
    p.add_argument("--horizon-hours", type=float, default=24.0)
    p.add_argument("--pool-meta-json", default=None)
    a = p.parse_args(argv)

    pool_meta = None
    if a.pool_meta_json:
        with open(a.pool_meta_json, "r", encoding="utf-8") as fh:
            pool_meta = json.load(fh)

    def _replay() -> list:
        return replay_gates(a.snapshot, pool=a.pool, samples=a.samples,
                            position_usd=Decimal(a.position_usd),
                            capital_usd=Decimal(a.capital_usd),
                            horizon_hours=a.horizon_hours,
                            pool_meta=pool_meta)

    if a.save_baseline:
        replay = _replay()
        saved = save_baseline(replay, a.baseline)
        payload = {"status": "SAVED", "baseline": a.baseline,
                   "n_steps": len(replay), "git_head": saved["git_head"],
                   "frozen_at": saved["frozen_at"]}
    elif not Path(a.baseline).exists():
        payload = {"status": "NO_BASELINE",
                   "hint": f"no baseline at {a.baseline}; run with "
                           f"--save-baseline to create it"}
    else:
        baseline = load_baseline(a.baseline).get("steps", [])
        payload = diff_replays(baseline, _replay())

    out_text = json.dumps(payload, indent=2, default=str)
    if a.out:
        Path(a.out).write_text(out_text + "\n")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
