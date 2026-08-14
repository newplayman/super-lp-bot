#!/usr/bin/env python3
"""Replay NetCover gates from a SQLite snapshot without touching its source DB."""
from __future__ import annotations

import argparse
import importlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def replay(*, db_path: Path, code_root: Path) -> dict[str, Any]:
    # Select the exact checked-out code root before importing the two gate
    # modules.  This lets TP-J compare pre/post source on one copied snapshot.
    sys.path.insert(0, str(code_root.resolve()))
    inputs = importlib.import_module("scripts.lp_netcover_inputs_v1_readonly")
    engine = importlib.import_module("scripts.lp_netcover_engine_v1_readonly")
    connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    try:
        source_rows = connection.execute(
            "select id, as_of, pool, score_json from opportunity_scores order by id"
        ).fetchall()
    finally:
        connection.close()
    rows: list[dict[str, Any]] = []
    for ident, as_of, pool, encoded in source_rows:
        source = json.loads(encoded)
        # The persisted historical row predates FIX-F1's explicit dispatch
        # field.  Reproduce the production boundary's audited Base mapping,
        # rather than comparing two meaningless protocol-type failures.
        if source.get("protocol_type") is None and str(source.get("project", "")).lower() in {
            "aerodrome-slipstream", "uniswap-v3",
        }:
            source["protocol_type"] = "clmm"
        position = source.get("capital_usd") or source.get("position_requested_usd") or 50.0
        try:
            assembled = inputs.assemble_netcover_inputs(
                source, position_usd=float(position),
                scanner_measured_evidence=source.get("scanner_measured_cross_pool_evidence"),
            )
            gated = engine.apply_netcover_gate([assembled])[0]
            row = {
                "id": ident, "as_of": as_of, "pool": pool,
                "netcover_ratio": gated.get("netcover_ratio"),
                "netcover_pass": gated.get("netcover_pass"),
                "netcover_reason": gated.get("rejection_reason"),
                "position_cap_pass": assembled.get("position_cap_pass"),
                "position_cap_reason": assembled.get("position_cap_reason"),
                "entry_cost_usd": assembled.get("entry_cost_usd"),
                "exit_cost_usd": assembled.get("exit_cost_usd"),
                "slippage_usd": assembled.get("slippage_usd"),
            }
        except Exception as exc:  # preserve a fail-closed replay error as evidence
            row = {"id": ident, "as_of": as_of, "pool": pool, "replay_error": repr(exc)}
        rows.append(row)
    return {
        "db": str(db_path), "code_root": str(code_root), "row_count": len(rows),
        "netcover_pass_counts": dict(Counter(str(row.get("netcover_pass")) for row in rows)),
        "position_cap_counts": dict(Counter(str(row.get("position_cap_pass")) for row in rows)),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only fixed-snapshot NetCover replay")
    parser.add_argument("--db", required=True)
    parser.add_argument("--code-root", default=".")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = replay(db_path=Path(args.db), code_root=Path(args.code_root))
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
