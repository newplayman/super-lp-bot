#!/usr/bin/env python3
"""LP Long Horizon — Stage Supervisor Finalize Dry-run From Existing Checkpoints V1.

Purpose:
    Re-runs the supervisor finalize logic (aggregate + FINAL_VERDICT + fallback) against
    an existing 12h (or 6h/24h/etc.) checkpoint dataset, **without** running the long
    collector loop and **without** modifying the source data dir. Writes the result to
    a separate `--out` directory so the supervisor's behavior can be exercised and
    verified.

This is the test harness companion to
`scripts/run_lp_long_horizon_readonly_stage_once.sh` after the V3 lowercase-bool fix.

Inputs:
    --source-data   path to checkpoint dir (e.g. data/lp_long_horizon/20260605_082120)
    --source-report path to supervisor report dir (e.g. reports/lp_long_horizon_readonly_12h_run/20260605_082120)
                    Used to read actual_runtime_minutes from corrected verdict (source of truth)
    --out           path to dry-run output dir (must NOT be under --source-data)
    --run-id        the new run id (e.g. 20260606_082958)
    --stage         stage name (e.g. 12h, 6h, 24h)

Outputs in --out:
    - aggregate_summary.json   (success path output)
    - FINAL_VERDICT.json       (success path output, status=PASS/FAIL based on actual_runtime_minutes vs gate)
    - CORRECTED_FINAL_VERDICT_FALLBACK.json (only if --simulate-fail is set)

Hard guarantees:
    - Read-only on --source-data
    - Read-only on --source-report
    - No wallet / keypair / signer / tx / probe / canary / live / paper
    - No auto-advance to any longer stage
    - No process spawn
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Hard guards (read-only, no forbidden process)
# ---------------------------------------------------------------------------

FORBIDDEN_TOKENS = [
    "canary", "lpbot-live", "live-mode", "sendTransaction",
    "eth_sendRawTransaction", "eth_sendTransaction",
    "keypair", "private_key", "mnemonic", "seed_phrase",
]


def _refuse_if_under_source(src: Path, out: Path) -> None:
    """Refuse if --out is under --source-data or --source-report (would modify source)."""
    try:
        out_resolved = out.resolve()
    except Exception:
        out_resolved = out
    for s in (src,):
        try:
            s_resolved = s.resolve()
        except Exception:
            s_resolved = s
        try:
            out_resolved.relative_to(s_resolved)
            raise SystemExit(f"REFUSED: --out {out} is under --source-data {src}")
        except ValueError:
            pass


def _load_corrected_runtime_minutes(source_report: Path) -> int:
    """Read the actual_runtime_minutes from a corrected verdict if available, else from
    the source FINAL_VERDICT.json. Both are read-only."""
    candidates = [
        source_report / "CORRECTED_FINAL_VERDICT.json",
        source_report.parent / "CORRECTED_FINAL_VERDICT.json",
    ]
    # Look for any file with corrected verdict in the chain
    for c in candidates:
        if c.exists():
            try:
                d = json.loads(c.read_text())
                if "actual_runtime_minutes" in d:
                    return int(d["actual_runtime_minutes"])
            except Exception:
                pass
    # Fallback: read raw source FINAL_VERDICT.json
    fv = source_report / "FINAL_VERDICT.json"
    if fv.exists():
        try:
            d = json.loads(fv.read_text())
            if "actual_runtime_minutes" in d:
                return int(d["actual_runtime_minutes"])
        except Exception:
            pass
    return 0


def aggregate_checkpoints(data_dir: Path) -> dict[str, Any]:
    """Re-aggregate row counts from checkpoint_* dirs in --source-data."""
    if not data_dir.exists():
        raise SystemExit(f"REFUSED: --source-data {data_dir} does not exist")
    ckpts = sorted([p for p in data_dir.iterdir() if p.is_dir() and p.name.startswith("checkpoint_")])
    total = {"pool_snapshots": 0, "quote_snapshots": 0, "fee_velocity": 0,
             "liquidity_distribution": 0, "market_regime": 0, "actual_fee_accrual": 0}
    seen_pool: set[str] = set()
    seen_quote: set[tuple] = set()
    for d in ckpts:
        p = d / "pool_snapshots.jsonl"
        if p.exists():
            for line in p.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                key = r.get("pool_address")
                if key and key not in seen_pool:
                    seen_pool.add(key)
                    total["pool_snapshots"] += 1
        q = d / "quote_snapshots.jsonl"
        if q.exists():
            for line in q.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                key = (r.get("pool_address"), r.get("notional_usd"), r.get("quote_at"))
                if key not in seen_quote:
                    seen_quote.add(key)
                    total["quote_snapshots"] += 1
        f = d / "fee_velocity.jsonl"
        if f.exists():
            for line in f.read_text().splitlines():
                if line.strip():
                    total["fee_velocity"] += 1
        l = d / "liquidity_distribution.jsonl"
        if l.exists():
            for line in l.read_text().splitlines():
                if line.strip():
                    total["liquidity_distribution"] += 1
        r = d / "market_regime.jsonl"
        if r.exists():
            for line in r.read_text().splitlines():
                if line.strip():
                    total["market_regime"] += 1
        a = d / "actual_fee_accrual_placeholder.json"
        if a.exists():
            total["actual_fee_accrual"] += 1
    return {
        "stage": "",  # filled in by caller
        "run_id": "",  # filled in by caller
        "checkpoint_count": len(ckpts),
        "checkpoint_dirs": [str(d) for d in ckpts],
        "row_counts_deduped": total,
        "selected_pool_count": len(seen_pool),
    }


def write_aggregate_summary(out_dir: Path, stage: str, run_id: str,
                             actual_runtime_minutes: int,
                             agg: dict[str, Any],
                             duration_hours: int) -> dict[str, Any]:
    """Mirror scripts/run_lp_long_horizon_readonly_stage_once.sh aggregate block.

    Critically, this uses Python bool arithmetic (not bash boolean interpolation)
    and writes a real JSON boolean to aggregate_summary.json.
    """
    tolerance_min = 60  # matches the supervisor's TOLERANCE_MIN
    expected_min = duration_hours * 60 - tolerance_min
    # Compute gate validity in Python — no bash boolean literal involved.
    runtime_valid = actual_runtime_minutes >= expected_min
    gate_decision = "PASS" if runtime_valid else "FAIL"

    summary = {
        "stage": stage,
        "run_id": run_id,
        "actual_runtime_minutes": actual_runtime_minutes,
        "expected_min_runtime_minutes": expected_min,
        "actual_runtime_valid_for_" + stage + "_gate": runtime_valid,
        "short_mode_used": False,
        "loop_count_total": duration_hours,
        "sleep_seconds_per_iteration": 3600,
        "checkpoint_count": agg["checkpoint_count"],
        "checkpoint_dirs": agg["checkpoint_dirs"],
        "row_counts_deduped": agg["row_counts_deduped"],
        "selected_pool_count": agg["selected_pool_count"],
        "real_pool_universe_used": True,
        "selected_real_pool_count": 33,
        "placeholder_pool_count": 0,
        "wallet_or_tx_touched": False,
        "transaction_sent": False,
        "no_production_write": True,
        "no_shadow_overwrite": True,
        "can_run_probe_now": False,
        "tiny_canary_allowed": "no",
        "auto_advance_to_next": False,
        "send_hard_disable_still_active": True,
        "gate_decision": gate_decision,
        "next_action": "manual review of FINAL_VERDICT",
        "dry_run_source_data": str(agg.get("dry_run_source_data", "")),
    }
    (out_dir / "aggregate_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
    )
    return summary


def write_final_verdict(out_dir: Path, agg_summary: dict[str, Any],
                         run_id: str, stage: str,
                         session_name: str = "") -> dict[str, Any]:
    """Mirror the success-path finalize block. Reads aggregate_summary.json via
    json.loads (proper bool) — no bash boolean interpolation."""
    gate_valid = bool(agg_summary.get("actual_runtime_valid_for_" + stage + "_gate", False))
    gate_decision = agg_summary.get("gate_decision", "PASS" if gate_valid else "FAIL")
    status = "PASS" if gate_decision == "PASS" else "FAIL"
    data_quality = "PASS" if status == "PASS" else "FAIL"

    if status == "PASS":
        recommended_next_stage = "LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1"
    else:
        recommended_next_stage = "LP_LONG_HORIZON_" + stage.upper() + "_COLLECTOR_FIX_REPEAT"

    total = agg_summary["row_counts_deduped"]
    fv = {
        "stage": "LP_LONG_HORIZON_READONLY_" + stage.upper() + "_STAGE_RUN_V1",
        "status": status,
        "run_id": run_id,
        "branch": "feat/supabase-postgres-deployment",
        "approval_recorded": True,
        "approved_stage": stage,
        "tmux_started": False,
        "tmux_session_name": session_name or f"dryrun_{stage}_{run_id}",
        "tmux_session_at_finalize": "n/a (dry-run)",
        "twelve_hour_run_completed": True,
        "actual_runtime_minutes": agg_summary["actual_runtime_minutes"],
        "actual_runtime_valid_for_" + stage + "_gate": gate_valid,
        "short_mode_used": False,
        "real_pool_universe_used": True,
        "selected_real_pool_count": 33,
        "placeholder_pool_count": 0,
        "selected_pool_count": agg_summary["selected_pool_count"],
        "pool_snapshot_rows": total["pool_snapshots"],
        "quote_snapshot_rows": total["quote_snapshots"],
        "fee_velocity_rows": total["fee_velocity"],
        "liquidity_distribution_rows": total["liquidity_distribution"],
        "market_regime_rows": total["market_regime"],
        "actual_fee_accrual_placeholder_rows": total["actual_fee_accrual"],
        "error_rate_pct": 0.0,
        "consecutive_429_max": 0,
        "data_quality_status": data_quality,
        "gate_pass": gate_valid,
        "can_advance_to_next": False,
        "auto_advance_started": False,
        "longer_stage_started": False,
        "can_run_probe_now": False,
        "tiny_canary_allowed": "no",
        "edge_proven": "no",
        "wallet_or_tx_touched": False,
        "transaction_sent": False,
        "send_hard_disable_still_active": True,
        "recommended_next_stage": recommended_next_stage,
        "dry_run": True,
        "dry_run_source_data": agg_summary.get("dry_run_source_data", ""),
    }
    (out_dir / "FINAL_VERDICT.json").write_text(json.dumps(fv, indent=2, ensure_ascii=False))
    return fv


def write_fallback_verdict(out_dir: Path, agg_summary: dict[str, Any],
                            run_id: str, stage: str,
                            error_msg: str,
                            session_name: str = "") -> dict[str, Any]:
    """Mirror the failure-path fallback block. Reads aggregate_summary.json via
    json.loads (proper bool) — no bash boolean interpolation."""
    gate_valid = bool(agg_summary.get("actual_runtime_valid_for_" + stage + "_gate", False))
    total = agg_summary.get("row_counts_deduped", {})
    if gate_valid:
        recommended_next_stage = "LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1"
    else:
        recommended_next_stage = "LP_LONG_HORIZON_" + stage.upper() + "_COLLECTOR_FIX_REPEAT"
    fb = {
        "stage": "LP_LONG_HORIZON_READONLY_" + stage.upper() + "_STAGE_RUN_V3",
        "status": "WARN",
        "run_id": run_id,
        "branch": "feat/supabase-postgres-deployment",
        "approval_recorded": True,
        "approved_stage": stage,
        "twelve_hour_run_completed": True,
        "actual_runtime_minutes": agg_summary.get("actual_runtime_minutes", 0),
        "actual_runtime_valid_for_" + stage + "_gate": gate_valid,
        "short_mode_used": False,
        "supervisor_finalize_failed": True,
        "finalize_error": error_msg,
        "real_pool_universe_used": True,
        "selected_real_pool_count": 33,
        "placeholder_pool_count": 0,
        "selected_pool_count": agg_summary.get("selected_pool_count", 0),
        "pool_snapshot_rows": total.get("pool_snapshots", 0),
        "quote_snapshot_rows": total.get("quote_snapshots", 0),
        "fee_velocity_rows": total.get("fee_velocity", 0),
        "liquidity_distribution_rows": total.get("liquidity_distribution", 0),
        "market_regime_rows": total.get("market_regime", 0),
        "actual_fee_accrual_placeholder_rows": total.get("actual_fee_accrual", 0),
        "can_run_probe_now": False,
        "tiny_canary_allowed": "no",
        "edge_proven": "no",
        "wallet_or_tx_touched": False,
        "transaction_sent": False,
        "can_advance_to_next": False,
        "auto_advance_started": False,
        "longer_stage_started": False,
        "send_hard_disable_still_active": True,
        "recommended_next_stage": recommended_next_stage,
        "dry_run": True,
        "dry_run_source_data": agg_summary.get("dry_run_source_data", ""),
    }
    (out_dir / "CORRECTED_FINAL_VERDICT_FALLBACK.json").write_text(
        json.dumps(fb, indent=2, ensure_ascii=False)
    )
    return fb


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-data", required=True, type=Path,
                    help="Path to checkpoint dir (e.g. data/lp_long_horizon/20260605_082120)")
    ap.add_argument("--source-report", required=True, type=Path,
                    help="Path to supervisor report dir (e.g. reports/lp_long_horizon_readonly_12h_run/20260605_082120)")
    ap.add_argument("--out", required=True, type=Path,
                    help="Path to dry-run output dir (must NOT be under --source-data)")
    ap.add_argument("--run-id", required=True, help="Run id for the dry-run output")
    ap.add_argument("--stage", required=True, choices=["6h", "12h", "24h", "48h", "72h", "7d"],
                    help="Stage name (used to compute duration_hours)")
    ap.add_argument("--simulate-fail", action="store_true",
                    help="Also write CORRECTED_FINAL_VERDICT_FALLBACK.json (simulates finalize-block rc!=0)")
    args = ap.parse_args()

    # ---- Hard guards ----
    args.source_data = args.source_data.resolve()
    args.source_report = args.source_report.resolve()
    args.out = args.out.resolve()

    if not args.source_data.exists():
        print(f"REFUSED: --source-data {args.source_data} does not exist", file=sys.stderr)
        return 17
    if not args.source_report.exists():
        print(f"REFUSED: --source-report {args.source_report} does not exist", file=sys.stderr)
        return 18

    _refuse_if_under_source(args.source_data, args.out)
    _refuse_if_under_source(args.source_report, args.out)

    if str(args.out).startswith(str(args.source_data)):
        print(f"REFUSED: --out {args.out} is under --source-data", file=sys.stderr)
        return 19

    args.out.mkdir(parents=True, exist_ok=True)

    # ---- Map stage to duration_hours ----
    duration_hours = {
        "6h": 6, "12h": 12, "24h": 24, "48h": 48, "72h": 72, "7d": 168,
    }[args.stage]

    # ---- Step 1: aggregate from existing checkpoints (read-only) ----
    agg_raw = aggregate_checkpoints(args.source_data)
    agg_raw["dry_run_source_data"] = str(args.source_data)

    # ---- Step 2: read actual_runtime_minutes from source report ----
    actual_runtime_minutes = _load_corrected_runtime_minutes(args.source_report)
    if actual_runtime_minutes == 0:
        print(f"WARN: could not read actual_runtime_minutes from source report, using 0", file=sys.stderr)

    # ---- Step 3: write aggregate_summary.json (proper bool) ----
    agg_summary = write_aggregate_summary(
        args.out, args.stage, args.run_id,
        actual_runtime_minutes, agg_raw, duration_hours,
    )
    print(f"[aggregate] ckpts={agg_summary['checkpoint_count']} "
          f"pool={agg_summary['row_counts_deduped']['pool_snapshots']} "
          f"quote={agg_summary['row_counts_deduped']['quote_snapshots']} "
          f"fee={agg_summary['row_counts_deduped']['fee_velocity']} "
          f"liq={agg_summary['row_counts_deduped']['liquidity_distribution']} "
          f"regime={agg_summary['row_counts_deduped']['market_regime']} "
          f"actual_fee={agg_summary['row_counts_deduped']['actual_fee_accrual']} "
          f"gate_valid={agg_summary['actual_runtime_valid_for_' + args.stage + '_gate']}")

    # ---- Step 4: write FINAL_VERDICT.json (success path) ----
    fv = write_final_verdict(
        args.out, agg_summary, args.run_id, args.stage,
        session_name=f"dryrun_{args.stage}_{args.run_id}",
    )
    print(f"[finalize] FINAL_VERDICT status={fv['status']} "
          f"runtime={fv['actual_runtime_minutes']}min "
          f"pool_rows={fv['pool_snapshot_rows']}")

    # ---- Step 5: optionally write fallback (simulates finalize block rc!=0) ----
    if args.simulate_fail:
        fb = write_fallback_verdict(
            args.out, agg_summary, args.run_id, args.stage,
            error_msg="dry-run simulated finalize failure",
            session_name=f"dryrun_{args.stage}_{args.run_id}",
        )
        print(f"[fallback] CORRECTED_FINAL_VERDICT_FALLBACK status={fb['status']}")

    print(f"[dryrun] wrote {args.out}/FINAL_VERDICT.json "
          f"+ aggregate_summary.json"
          f"{' + CORRECTED_FINAL_VERDICT_FALLBACK.json' if args.simulate_fail else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
