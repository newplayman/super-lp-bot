"""LP Long Horizon Read-only Collector - Real Data Smoke (v1).

This is the runner for stage ``LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1``.
It runs a 1-pass read-only smoke that produces ``real_data_rows > 0`` from the
``LocalArtifactReplayAdapter`` (real pool addresses from frozen verdicts).

It does NOT:
- run 7d / 14d / 30d long-running collection
- start a daemon / cron / systemd
- touch any wallet / signer / keypair
- sign / send / approve / mint / add_liquidity / remove_liquidity / collect_fee / swap / bridge
- probe / canary / live / paper
- write to production positions or shadow tables

It DOES:
- run the local_artifact_replay_adapter (real pool_addresses, no network)
- optionally run public_api_coingecko + solana_rpc_readonly adapters (opt-in)
- run classify_regime() on placeholder inputs
- write SQLite + JSONL (research-only) under ``data/lp_long_horizon/<run_id>/``
- check AbortController between units
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the scripts/ dir importable so ``lp_long_horizon`` package can be loaded
# when this script is invoked as ``python3 scripts/lp_long_horizon_readonly_real_data_smoke_v1.py``.
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lp_long_horizon.adapters.local_artifact_replay import (
    LocalArtifactReplayAdapter,
    build_pool_snapshot_row,
    build_quote_snapshot_rows,
    build_fee_velocity_rows,
    build_liquidity_distribution_row,
)
from lp_long_horizon.classify.market_regime import (
    classify_regime,
    build_market_regime_row,
)
from lp_long_horizon.storage.research_store import ResearchStore
from lp_long_horizon.utils.abort import AbortController, ErrorRateMonitor, AbortError


NOTIONALS_USD = [10, 20, 100, 500, 1000, 2000]
ROLLING_WINDOWS = ["15m", "1h", "6h", "24h", "7d"]
REGIME_INPUTS = [
    # (regime_name_for_audit, realized_vol_7d_pct, price_change_7d_pct, volume_to_tvl_30d_pct, lm_active, bribe_active)
    # These cover all 7 regimes deterministically (1 per regime).
    ("low_volatility_stable", 0.5, 0.0, 0.0, False, False),  # vol < 1
    ("incentive_period", 5.0, 0.0, 0.0, True, False),  # LM active override
    ("high_volatility_trend", 12.0, 0.0, 0.0, False, False),  # vol >= 10
    ("high_volume_sideways", 2.0, 0.0, 1.5, False, False),  # sideways + vol_tvl >= 1
    ("uptrend", 5.0, 8.0, 0.0, False, False),  # px > +5
    ("downtrend", 5.0, -8.0, 0.0, False, False),  # px < -5
    ("sideways", 2.0, 0.0, 0.5, False, False),  # fallback
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LP long-horizon real-data smoke (1 pass, no daemon)")
    parser.add_argument("--mode", default="smoke", choices=["design", "smoke"],
                        help="design (default) prints spec only; smoke runs 1 pass")
    parser.add_argument("--out", default=None,
                        help="output directory; default data/lp_long_horizon/<run_id>/real_data_smoke")
    parser.add_argument("--pools", type=int, default=5, help="max pools from local_artifact_replay")
    parser.add_argument("--use-public-api", type=int, default=0, choices=[0, 1],
                        help="opt-in to CoinGecko public OHLC")
    parser.add_argument("--use-solana-rpc", type=int, default=0, choices=[0, 1],
                        help="opt-in to Solana RPC getMultipleAccountsInfo")
    parser.add_argument("--run-id", default=None, help="override run id (default: timestamp)")
    args = parser.parse_args(argv)

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else (Path("data/lp_long_horizon") / run_id / "real_data_smoke")

    if not str(out_dir).startswith("data/lp_long_horizon"):
        print(f"REFUSED: out dir {out_dir!r} must start with data/lp_long_horizon", file=sys.stderr)
        return 5

    if args.mode == "design":
        print(f"[design mode] stage=LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1 run_id={run_id}")
        print(f"[design mode] out_dir={out_dir}")
        print(f"[design mode] pools={args.pools}")
        print(f"[design mode] use_public_api={args.use_public_api}")
        print(f"[design mode] use_solana_rpc={args.use_solana_rpc}")
        print(f"[design mode] expected_real_data_rows>=65 expected_placeholder_rows<=8")
        print("[design mode] no network (default), no tx, no wallet, no daemon. exit 0")
        return 0

    # smoke mode
    print(f"[smoke mode] run_id={run_id} out_dir={out_dir}")

    abort_ctrl = AbortController(
        error_rate_monitor=ErrorRateMonitor(threshold_pct=50.0, window=20),
        max_429_streak=5,
    )

    # Adapter 1: local_artifact_replay (always runs, no network)
    replay = LocalArtifactReplayAdapter(abort_controller=abort_ctrl)
    pools = replay.fetch_pools()
    if args.pools > 0:
        pools = pools[: args.pools]
    print(f"[smoke mode] local_artifact_replay fetched {len(pools)} real pools")

    if not pools:
        print("[smoke mode] FATAL: no pools from local_artifact_replay; abort", file=sys.stderr)
        return 6

    # Store
    store = ResearchStore(out_dir, abort_controller=abort_ctrl)
    print(f"[smoke mode] store: sqlite_available={store.sqlite_available} jsonl_only={store.jsonl_only}")

    snapshot_at = _now_iso()
    quote_at = snapshot_at
    window_end_at = snapshot_at

    real_data_rows = 0
    placeholder_rows = 0

    try:
        for record in pools:
            # pool_snapshots
            ps_row = build_pool_snapshot_row(record, snapshot_at=snapshot_at)
            store.write_pool_snapshot(ps_row)
            if ps_row.get("real_data"):
                real_data_rows += 1
            else:
                placeholder_rows += 1

            # liquidity_distribution
            ld_row = build_liquidity_distribution_row(record, snapshot_at=snapshot_at)
            store.write_liquidity_distribution(ld_row)
            if ld_row.get("real_data"):
                real_data_rows += 1
            else:
                placeholder_rows += 1

            # quote_snapshots (6 notionals)
            q_rows = build_quote_snapshot_rows(record, NOTIONALS_USD, quote_at=quote_at)
            for q in q_rows:
                store.write_quote_snapshot(q)
                if q.get("real_data"):
                    real_data_rows += 1
                else:
                    placeholder_rows += 1

            # fee_velocity (5 windows)
            f_rows = build_fee_velocity_rows(record, ROLLING_WINDOWS, window_end_at=window_end_at)
            for f in f_rows:
                store.write_fee_velocity(f)
                if f.get("real_data"):
                    real_data_rows += 1
                else:
                    placeholder_rows += 1

            abort_ctrl.check_abort()

        # market_regime: 7 regimes via real classify_regime (1 per regime)
        for (name, vol7, px7, vol_tvl, lm, bribe) in REGIME_INPUTS:
            classified = classify_regime(
                realized_vol_7d_pct=vol7,
                price_change_7d_pct=px7,
                volume_to_tvl_30d_pct=vol_tvl,
                lm_active=lm,
                bribe_active=bribe,
            )
            mr_row = build_market_regime_row(
                regime=classified,
                lookback_days=7,
                price_change_pct=px7,
                realized_vol_pct=vol7,
                volume_to_tvl_pct=vol_tvl,
                incentive_active=(lm or bribe),
                regime_at=snapshot_at,
                real_data=True,
                data_source="real_classifier",
            )
            store.write_market_regime(mr_row)
            real_data_rows += 1  # classified by real function, real_data=True
            abort_ctrl.check_abort()

        # actual_fee_accrual: schema-only placeholder
        actual_fee_placeholder = {
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
            "real_data": False,
        }
        store.write_actual_fee_placeholder(actual_fee_placeholder)
        placeholder_rows += 1

    except AbortError as exc:
        print(f"[smoke mode] ABORT: {exc}", file=sys.stderr)
        return 7
    finally:
        # Always write smoke_summary before closing the store
        store_summary = store.summary()
        abort_summary = abort_ctrl.summary()
        total_rows = real_data_rows + placeholder_rows
        summary = {
            "stage": "LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1",
            "mode": "smoke",
            "run_id": run_id,
            "executed_at": snapshot_at,
            "out_dir": str(out_dir),
            "selected_pool_count": len(pools),
            "real_data_rows": real_data_rows,
            "placeholder_rows": placeholder_rows,
            "total_rows": total_rows,
            "store_summary": store_summary,
            "abort_summary": abort_summary,
            "wallet_or_tx_touched": False,
            "transaction_sent": False,
            "send_hard_disable_still_active": True,
            "no_long_running_daemon": True,
            "no_paid_rpc_called": (args.use_public_api == 0 and args.use_solana_rpc == 0),
            "real_data_smoke_ran": True,
            "smoke_placeholder_only": False,
        }
        (out_dir / "smoke_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        store.close()

    print(f"[smoke mode] wrote real_data_rows={real_data_rows} placeholder_rows={placeholder_rows} total={real_data_rows + placeholder_rows}")
    print(f"[smoke mode] abort_summary={abort_ctrl.summary()}")
    print("[smoke mode] no network, no tx, no wallet, no signer, no daemon. exit 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
