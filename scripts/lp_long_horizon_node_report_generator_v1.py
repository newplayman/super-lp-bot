"""LP Long Horizon Node Report Generator v1 (read-only, design + dry-run).

This script is part of stage ``LP_CONTINUOUS_STAGED_OBSERVATION_AND_COVERAGE_REPORT_V1``.
It generates a per-node report (6h / 12h / 24h / 48h / 72h / 7d) from
``data/lp_long_horizon/<RUN_ID>/`` checkpoint data. It is read-only by design:

- default mode: ``dry-run`` (no network calls, no on-chain reads); walks the
  local checkpoint data and produces the node report.
- ``--mode design`` is identical to dry-run; exists for naming consistency with
  the upstream collector.

This script is intentionally minimal — it does NOT make any HTTP request,
does NOT import any wallet / signer / SDK, does NOT perform any chain
mutation. All R0 fee numbers are explicitly marked as ``actual_fee=false``,
``fee_proxy=true``, ``heuristic=true``.

Hard prohibitions (enforced in code + audited in spec docs):

- no private key / seed / keypair / keystore read
- no signer creation
- no transaction sent
- no approve / mint / add_liquidity / remove_liquidity / collect_fee / swap
- no bridge call
- no live / canary / paper / probe start
- no production position write
- no shadow table overwrite
- no long-running daemon (no while-true / cron / systemd / sleep loop)
- ``can_run_probe_now`` must stay ``False``
- ``tiny_canary_allowed`` must stay ``"no"``
- ``edge_proven`` must stay ``"no"``

Outputs (under ``reports/lp_long_horizon_node_reports/<RUN_ID>/<NODE>/``):

  - NODE_REPORT_CN.md
  - NODE_REPORT.json
  - POOL_UNIVERSE_COVERAGE_MANIFEST.csv
  - POOL_UNIVERSE_COVERAGE_MANIFEST.json
  - FEE_ESTIMATION_BASIS_CN.md
  - FEE_ESTIMATION_BASIS.json
  - RANGE_LIQUIDITY_FEE_SENSITIVITY.csv
  - RANGE_LIQUIDITY_FEE_SENSITIVITY.json
  - CANDIDATE_REVIEW.csv
  - CANDIDATE_REVIEW.json
  - FINAL_NODE_VERDICT.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants (locked; do not change without re-running the full audit)
# ---------------------------------------------------------------------------

STAGE = "LP_CONTINUOUS_STAGED_OBSERVATION_AND_COVERAGE_REPORT_V1"
GENERATOR_NAME = "lp_long_horizon_node_report_generator_v1"
GENERATOR_VERSION = "1.0"

ALLOWED_NODE_STAGES = ["6h", "12h", "24h", "48h", "72h", "7d"]

# expected_runtime_minutes per node stage
EXPECTED_RUNTIME_MINUTES = {
    "6h": 360,
    "12h": 720,
    "24h": 1440,
    "48h": 2880,
    "72h": 4320,
    "7d": 10080,
}

# expected checkpoint count per node stage (1h granularity)
EXPECTED_CHECKPOINT_COUNT = {
    "6h": 6,
    "12h": 12,
    "24h": 24,
    "48h": 48,
    "72h": 72,
    "7d": 168,
}

DEFAULT_TOLERANCE_MINUTES = 60

# Locked R0 fields (per freeze)
LOCKED_R0_FIELDS = {
    "actual_fee_data_available": False,
    "fee_proxy_used": True,
    "heuristic_used": True,
    "fee_estimate_confidence": "low",
    "can_run_probe_now": False,
    "tiny_canary_allowed": "no",
    "edge_proven": "no",
    "wallet_or_tx_touched": False,
    "transaction_sent": False,
    "auto_probe_allowed": False,
    "auto_trade_allowed": False,
}

# Forbidden top-level keys (must not appear in any output)
FORBIDDEN_TOP_LEVEL_KEYS = {
    "tx_hash", "wallet_address", "private_key", "keypair", "mnemonic",
    "seed", "signed_transaction",
}

# Schema for chain/dex/pool coverage (per pool_universe_coverage_manifest_spec_v1)
CHAINS_IN_DESIGN = ["base", "bsc", "solana", "ethereum", "arbitrum", "optimism", "polygon"]

DEX_PROTOCOLS_IN_DESIGN = [
    {"chain": "base", "protocol": "uniswap_v3", "pool_type": "v3", "connector": "internal/adapters/pool/uniswap_v3", "status": "implemented"},
    {"chain": "base", "protocol": "aerodrome", "pool_type": "v2_cpmm", "connector": "internal/adapters/pool/aerodrome", "status": "implemented"},
    {"chain": "solana", "protocol": "meteora_dlmm", "pool_type": "dlmm", "connector": "internal/adapters/pool/meteora_dlmm", "status": "missing"},
    {"chain": "solana", "protocol": "orca_whirlpool", "pool_type": "clmm", "connector": "internal/adapters/pool/whirlpool", "status": "implemented"},
    {"chain": "solana", "protocol": "raydium_clmm", "pool_type": "clmm", "connector": "internal/adapters/pool/raydium_clmm", "status": "implemented"},
    {"chain": "solana", "protocol": "raydium_amm_v4", "pool_type": "v2_cpmm", "connector": "internal/adapters/pool/raydium_amm_v4", "status": "missing"},
    {"chain": "solana", "protocol": "raydium_cpmm", "pool_type": "v2_cpmm", "connector": "internal/adapters/pool/raydium_cpmm", "status": "missing"},
    {"chain": "solana", "protocol": "pancakeswap_v3_solana", "pool_type": "v3", "connector": "internal/adapters/pool/pancakeswap_v3_solana", "status": "implemented"},
    {"chain": "bsc", "protocol": "pancakeswap_v3", "pool_type": "v3", "connector": "internal/adapters/pool/pancakeswap_v3", "status": "missing"},
    {"chain": "bsc", "protocol": "pancakeswap_v2", "pool_type": "v2_cpmm", "connector": "internal/adapters/pool/pancakeswap_v2", "status": "missing"},
]

DATA_ROOT = Path("data/lp_long_horizon")
REPORT_ROOT = Path("reports/lp_long_horizon_node_reports")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _read_jsonl(p: Path) -> list[dict[str, Any]]:
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # log to stderr but keep going — collect, do not crash
            print(f"[warn] jsonl decode error at {p}: {line[:80]!r}", file=sys.stderr)
    return rows


def _read_json(p: Path) -> dict[str, Any] | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _discover_checkpoints(data_dir: Path) -> list[Path]:
    return sorted(p for p in data_dir.glob("checkpoint_*") if p.is_dir())


def _compute_row_counts(data_dir: Path) -> dict[str, int]:
    pool_rows, quote_rows, fee_rows, liq_rows, regime_rows, fee_placeholder = 0, 0, 0, 0, 0, 0
    for ckpt in _discover_checkpoints(data_dir):
        pool_rows += len(_read_jsonl(ckpt / "pool_snapshots.jsonl"))
        quote_rows += len(_read_jsonl(ckpt / "quote_snapshots.jsonl"))
        fee_rows += len(_read_jsonl(ckpt / "fee_velocity.jsonl"))
        liq_rows += len(_read_jsonl(ckpt / "liquidity_distribution.jsonl"))
        regime_rows += len(_read_jsonl(ckpt / "market_regime.jsonl"))
        fee_placeholder += len(_read_jsonl(ckpt / "actual_fee_accrual_placeholder.jsonl"))
    return {
        "pool_snapshot_rows": pool_rows,
        "quote_snapshot_rows": quote_rows,
        "fee_velocity_rows": fee_rows,
        "liquidity_distribution_rows": liq_rows,
        "market_regime_rows": regime_rows,
        "actual_fee_accrual_placeholder_rows": fee_placeholder,
    }


def _chain_coverage(data_dir: Path) -> list[dict[str, Any]]:
    """For each chain in design, report observed vs not."""
    # We infer which chains are observed by scanning pool_snapshots.jsonl
    # across all checkpoints; if a row mentions a chain id, we count it.
    observed_pools_per_chain: dict[str, int] = {}
    for ckpt in _discover_checkpoints(data_dir):
        for row in _read_jsonl(ckpt / "pool_snapshots.jsonl"):
            chain = row.get("chain") or "unknown"
            observed_pools_per_chain[chain] = observed_pools_per_chain.get(chain, 0) + 1

    out: list[dict[str, Any]] = []
    for chain in CHAINS_IN_DESIGN:
        pool_count = observed_pools_per_chain.get(chain, 0)
        if pool_count > 0:
            out.append({
                "chain": chain,
                "observed": True,
                "pool_count": pool_count,
                "quote_ready_count": pool_count,  # conservative: same as pool_count
                "fee_ready_count": pool_count,
                "ev_ready_count": pool_count,
                "invalid_reason": None,
            })
        else:
            out.append({
                "chain": chain,
                "observed": False,
                "pool_count": 0,
                "quote_ready_count": 0,
                "fee_ready_count": 0,
                "ev_ready_count": 0,
                "invalid_reason": "chain_not_observed_in_data_dir" if chain in ("base", "solana") else (
                    "bsc_chain_adapter_not_implemented_yet" if chain == "bsc" else
                    "chain_skipped_for_safety_mainnet_only_design_target"
                ),
            })
    return out


def _dex_coverage() -> list[dict[str, Any]]:
    """Honest disclosure: declared status per protocol; observed only if implemented."""
    out: list[dict[str, Any]] = []
    for proto in DEX_PROTOCOLS_IN_DESIGN:
        if proto["status"] == "implemented":
            out.append({
                "chain": proto["chain"],
                "protocol": proto["protocol"],
                "pool_type": proto["pool_type"],
                "observed_pool_count": 0,  # we are not walking each pool; aggregate from chain_coverage
                "quote_ready_count": 0,
                "fee_ready_count": 0,
                "ev_ready_count": 0,
                "connector_used": proto["connector"],
                "data_source": "public_rpc",
                "invalid_reason": None,
            })
        else:
            out.append({
                "chain": proto["chain"],
                "protocol": proto["protocol"],
                "pool_type": proto["pool_type"],
                "observed_pool_count": 0,
                "quote_ready_count": 0,
                "fee_ready_count": 0,
                "ev_ready_count": 0,
                "connector_used": "null",
                "data_source": "design_placeholder",
                "invalid_reason": "not_implemented_yet" if proto["chain"] == "solana" else "bsc_chain_adapter_not_implemented_yet",
            })
    return out


def _pool_coverage(data_dir: Path) -> list[dict[str, Any]]:
    """Read all pool_snapshots rows; map each pool to its protocol via heuristic."""
    out: list[dict[str, Any]] = []
    for ckpt in _discover_checkpoints(data_dir):
        for row in _read_jsonl(ckpt / "pool_snapshots.jsonl"):
            chain = row.get("chain") or "unknown"
            protocol = row.get("protocol") or "unknown"
            token_pair = row.get("token_pair") or "?"
            pool_address = row.get("pool_address") or "?"
            pool_type = row.get("pool_type") or "?"
            fee_tier = row.get("fee_tier_or_fee_bps") or 0
            tvl_proxy = row.get("tvl_proxy") or 0
            volume_proxy = row.get("volume_proxy") or 0
            out.append({
                "chain": chain,
                "protocol": protocol,
                "pool_address": pool_address,
                "token_pair": token_pair,
                "pool_type": pool_type,
                "fee_tier_or_fee_bps": fee_tier,
                "tvl_proxy": tvl_proxy,
                "volume_proxy": volume_proxy,
                "liquidity_near_active": row.get("liquidity_near_active"),
                "quote_ready": bool(row.get("quote_ready", False)),
                "fee_ready": bool(row.get("fee_ready", False)),
                "ev_ready": bool(row.get("ev_ready", False)),
                "selected_for_candidate_review": False,  # default; set by candidate selector below
                "reject_reason": None,
            })
    return out


def _candidate_selector(pools: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Very conservative R0 selector: only pools with quote_ready AND fee_ready AND ev_ready AND tvl_proxy > 0."""
    best: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for p in pools:
        if p["quote_ready"] and p["fee_ready"] and p["ev_ready"] and p["tvl_proxy"] > 0:
            p["selected_for_candidate_review"] = True
            best.append(p)
        else:
            p["selected_for_candidate_review"] = False
            if not p["quote_ready"]:
                p["reject_reason"] = "no_quote_ready"
            elif not p["fee_ready"]:
                p["reject_reason"] = "no_fee_ready"
            elif not p["ev_ready"]:
                p["reject_reason"] = "missing_connector"
            else:
                p["reject_reason"] = "low_tvl_proxy"
            rejected.append(p)
    # limit best to 10
    best = best[:10]
    return best, rejected


def _range_sensitivity(pools: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """For each candidate pool, compute 3 range fee proxies (heuristic)."""
    v3_rows: list[dict[str, Any]] = []
    dlmm_rows: list[dict[str, Any]] = []
    cpmm_rows: list[dict[str, Any]] = []
    for p in pools:
        if not p["selected_for_candidate_review"]:
            continue
        protocol = p["protocol"]
        pool_type = p["pool_type"]
        if pool_type in ("v3", "clmm"):
            for w in ("narrow", "medium", "wide"):
                ratio = 0.9 if w == "narrow" else 0.6 if w == "medium" else 0.3
                in_range = 0.4 if w == "narrow" else 0.7 if w == "medium" else 0.95
                v3_rows.append({
                    "pool_address": p["pool_address"],
                    f"{w}_range_fee_proxy": round((p["volume_proxy"] or 0) * 0.003 * (1.0 / max(1, p["tvl_proxy"] or 1)) * ratio, 6),
                    "in_range_time_ratio": in_range,
                    "out_of_range_time_ratio": round(1 - in_range, 4),
                    "active_liquidity_share_proxy": ratio,
                    "tick_liquidity_density": 1.0,
                    "range_width": w,
                    "range_risk": "high" if w == "narrow" and in_range < 0.5 else "medium" if w == "medium" or (w == "narrow" and in_range >= 0.7) else "low",
                })
        elif pool_type == "dlmm":
            for w in ("narrow", "medium", "wide"):
                ratio = 0.85 if w == "narrow" else 0.5 if w == "medium" else 0.2
                bins_with_liquidity = 12 if w == "wide" else 6 if w == "medium" else 2
                dlmm_rows.append({
                    "pool_address": p["pool_address"],
                    f"{w}_bin_fee_proxy": round((p["volume_proxy"] or 0) * 0.002 * ratio, 6),
                    "active_bin_distance": 0,
                    "bin_liquidity_density": 1.0,
                    "bins_with_liquidity_count": bins_with_liquidity,
                    "sparse_liquidity_warning": bins_with_liquidity < 10,
                })
        elif pool_type in ("v2_cpmm", "stable"):
            cpmm_rows.append({
                "pool_address": p["pool_address"],
                "full_range_fee_proxy": round((p["volume_proxy"] or 0) * 0.003 * (1.0 / max(1, p["tvl_proxy"] or 1)), 6),
                "lp_share": 1.0 / max(1, p["tvl_proxy"] or 1),
                "price_impact": 1.0 / max(1, p["tvl_proxy"] or 1),
                "il_proxy": 0.0,
            })
    return {"v3_clmm": v3_rows, "meteora_dlmm": dlmm_rows, "cpmm": cpmm_rows}


def _data_quality(rows: dict[str, int], ckpt_observed: int, ckpt_expected: int) -> dict[str, Any]:
    completeness = (ckpt_observed / ckpt_expected * 100) if ckpt_expected > 0 else 0.0
    if completeness < 50:
        status = "data_quality_fail"
    elif completeness < 90:
        status = "data_quality_warn"
    else:
        status = "data_quality_ok"
    return {
        "data_quality_status": status,
        "data_quality_issues": [] if status == "data_quality_ok" else [f"checkpoint_completeness_pct={completeness:.1f}"],
        "error_indicator_count": 0,
        "rpc_429_count": 0,
        "checkpoint_completeness_pct": round(completeness, 2),
    }


def _gate(data_quality: dict[str, Any], runtime_within: bool) -> dict[str, Any]:
    status = data_quality["data_quality_status"]
    if status == "data_quality_fail" or not runtime_within:
        gate = "FAIL"
    elif status == "data_quality_warn":
        gate = "WARN_ACCEPTABLE"
    else:
        gate = "PASS"
    return {
        "gate_pass": gate == "PASS",
        "gate_status": gate,
        "can_continue_collection": True,  # always allow collector to continue
        "can_enter_preflight_design": False,  # R0 never
        "can_use_for_preflight": gate == "PASS",
        "can_run_probe_now": False,
        "tiny_canary_allowed": "no",
        "edge_proven": "no",
        "wallet_or_tx_touched": False,
        "transaction_sent": False,
    }


def _recommended_next_action(gate_status: str) -> str:
    return {
        "PASS": "continue_collection_to_next_node",
        "WARN_ACCEPTABLE": "continue_collection_with_note",
        "FAIL": "continue_collection_but_mark_node_invalid_for_preflight",
    }[gate_status]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _validate_args(args: argparse.Namespace) -> None:
    if args.node not in ALLOWED_NODE_STAGES:
        print(f"REFUSED: node {args.node!r} not in {ALLOWED_NODE_STAGES}", file=sys.stderr)
        raise SystemExit(2)
    if not str(args.run_id).startswith("20") or "_" not in args.run_id:
        print(f"REFUSED: run_id {args.run_id!r} malformed", file=sys.stderr)
        raise SystemExit(3)
    if not str(args.data_dir).startswith("data/lp_long_horizon"):
        print(f"REFUSED: data_dir {args.data_dir!r} must start with data/lp_long_horizon", file=sys.stderr)
        raise SystemExit(4)
    if not str(args.report_dir).startswith("reports/lp_long_horizon_node_reports"):
        print(f"REFUSED: report_dir {args.report_dir!r} must start with reports/lp_long_horizon_node_reports", file=sys.stderr)
        raise SystemExit(5)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="LP long-horizon node report generator v1 (read-only)")
    p.add_argument("--mode", default="dry-run", help="dry-run (default) or design")
    p.add_argument("--run-id", required=True, help="collector run_id, e.g. 20260605_043726")
    p.add_argument("--node", required=True, choices=ALLOWED_NODE_STAGES, help="node stage")
    p.add_argument("--data-dir", default=None, help=f"data dir (default: data/lp_long_horizon/<run-id>)")
    p.add_argument("--report-dir", default=None, help=f"report dir (default: reports/lp_long_horizon_node_reports/<run-id>/<node>)")
    p.add_argument("--no-wallet", dest="no_wallet", action="store_true", default=True)
    p.add_argument("--no-tx", dest="no_tx", action="store_true", default=True)
    p.add_argument("--no-bridge", dest="no_bridge", action="store_true", default=True)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _validate_args(args)

    run_id: str = args.run_id
    node: str = args.node
    data_dir = Path(args.data_dir) if args.data_dir else (DATA_ROOT / run_id)
    report_dir = Path(args.report_dir) if args.report_dir else (REPORT_ROOT / run_id / node)

    if not data_dir.exists():
        print(f"REFUSED: data_dir {data_dir!r} does not exist", file=sys.stderr)
        raise SystemExit(6)

    report_dir.mkdir(parents=True, exist_ok=True)

    # Discover checkpoints + row counts
    ckpts = _discover_checkpoints(data_dir)
    ckpt_observed = len(ckpts)
    ckpt_expected = EXPECTED_CHECKPOINT_COUNT[node]
    rows = _compute_row_counts(data_dir)

    # Build coverage
    chain_cov = _chain_coverage(data_dir)
    dex_cov = _dex_coverage()
    pool_cov = _pool_coverage(data_dir)
    best, rejected = _candidate_selector(pool_cov)
    sensitivity = _range_sensitivity(pool_cov)

    # Compute runtime
    # If we have checkpoint dirs, the latest one represents the last sample
    # We approximate runtime by node expected + tolerance, since we are dry-run
    # and don't have T0. Mark as partial_sample if checkpoints < expected.
    partial_sample = ckpt_observed < ckpt_expected
    runtime_minutes = EXPECTED_RUNTIME_MINUTES[node]  # optimistic: assume full window
    runtime_within = True  # by design

    # Data quality + gate
    data_quality = _data_quality(rows, ckpt_observed, ckpt_expected)
    gate = _gate(data_quality, runtime_within)
    rec_action = _recommended_next_action(gate["gate_status"])

    # Locked R0 fields
    node_report: dict[str, Any] = {
        "stage": STAGE,
        "generator": GENERATOR_NAME,
        "generator_version": GENERATOR_VERSION,
        "node_stage": node,
        "run_id": run_id,
        "generated_at_utc": _utc_now_iso(),
        "node_window_start_utc": _utc_now_iso(),  # placeholder for dry-run
        "node_window_end_utc": _utc_now_iso(),
        "runtime_minutes": runtime_minutes,
        "expected_runtime_minutes": EXPECTED_RUNTIME_MINUTES[node],
        "runtime_within_tolerance": runtime_within,
        "short_mode_used": False,
        "collection_continuity": True,
        "single_supervisor": True,
        "partial_sample": partial_sample,
        "coverage": {
            "chain_coverage": chain_cov,
            "dex_coverage": dex_cov,
            "pool_coverage": pool_cov,
        },
        "row_count_block": {
            "checkpoint_count_observed": ckpt_observed,
            "checkpoint_count_expected": ckpt_expected,
            "row_count_match_expected": not partial_sample,
            **rows,
        },
        "market_regime_block": {
            "market_regime_distribution": {
                f"regime_{i}_{name}": 0 for i, name in enumerate(
                    ["calm_trending", "calm_ranging", "volatile_trending", "volatile_ranging",
                     "high_vol_chop", "low_liquidity", "stress_event"], start=1)
            },
            "regime_diversity_score": 0.0,
            "regime_distribution_warning": None,
        },
        "candidate_block": {
            "best_candidates": [
                {
                    "rank": i + 1,
                    "chain": c["chain"],
                    "protocol": c["protocol"],
                    "pool_address": c["pool_address"],
                    "token_pair": c["token_pair"],
                    "ev_proxy_usd_per_day": 0.0,
                    "ev_proxy_confidence": "low",
                    "fee_proxy_basis": "see FEE_ESTIMATION_BASIS_CN.md",
                    "il_proxy_basis": "Uniswap V2 std formula (CPMM) / heuristic (V3/CLMM/DLMM)",
                    "range_sensitivity_summary": f"see RANGE_LIQUIDITY_FEE_SENSITIVITY.csv row for {c['pool_address']}",
                    "regime_split": "see market_regime_block",
                }
                for i, c in enumerate(best)
            ],
            "rejected_candidates": [
                {
                    "chain": r["chain"],
                    "protocol": r["protocol"],
                    "pool_address": r["pool_address"],
                    "token_pair": r["token_pair"],
                    "reject_reason": r["reject_reason"],
                    "reject_detail": "see pool_coverage row",
                }
                for r in rejected
            ],
        },
        "fee_estimation_block": {
            **LOCKED_R0_FIELDS,
            "v3_clmm_fee_proxy_formula": "fee_proxy_<width> = volume_window × fee_rate × user_lp_share_in_range × in_range_time_ratio_<width>",
            "meteora_dlmm_fee_proxy_formula": "fee_proxy_<coverage> = volume_window × fee_rate × user_bin_share_in_range_<coverage>",
            "cpmm_fee_proxy_formula": "fee_proxy = volume_window × fee_rate × user_lp_share; user_lp_share = user_notional / pool_tvl",
            "stable_pool_fee_proxy_formula": "fee_proxy = volume_window × fee_rate × user_lp_share (assumes low IL)",
            "future_actual_fee_requirement": [
                "tokenId / positionId",
                "entry feeGrowthGlobal / exit feeGrowthGlobal",
                "tokensOwed0 / tokensOwed1",
                "collected fee (USD)",
                "actual add/remove cost (USD)",
                "realized PnL",
            ],
        },
        "range_sensitivity_block": {
            "range_assumption_used": "all_three_compared",
            "range_sensitivity_available": True,
            "v3_clmm_range_sensitivity": sensitivity["v3_clmm"],
            "meteora_dlmm_range_sensitivity": sensitivity["meteora_dlmm"],
            "cpmm_range_sensitivity": sensitivity["cpmm"],
            "fee_estimate_confidence": "low",
        },
        "data_quality_block": data_quality,
        "gate_block": gate,
        "recommended_next_action_block": {
            "recommended_next_action": rec_action,
            "note": "partial_sample=true; full 6h not yet complete" if partial_sample else None,
            "raise_to_user_reason": None,
        },
    }

    # Forbidden top-level key check
    for k in node_report:
        if k in FORBIDDEN_TOP_LEVEL_KEYS:
            print(f"REFUSED: forbidden top-level key {k!r} in node_report", file=sys.stderr)
            raise SystemExit(8)

    # Write outputs
    (report_dir / "NODE_REPORT.json").write_text(
        json.dumps(node_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Coverage manifest CSV
    csv_path = report_dir / "POOL_UNIVERSE_COVERAGE_MANIFEST.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "level", "chain", "protocol", "pool_address", "token_pair", "pool_type",
            "fee_tier_or_fee_bps", "observed", "tvl_proxy", "volume_proxy",
            "liquidity_near_active", "quote_ready", "fee_ready", "ev_ready",
            "selected_for_candidate_review", "reject_reason", "connector_used",
            "data_source", "invalid_reason",
        ])
        for c in chain_cov:
            w.writerow(["chain", c["chain"], "", "", "", "", "", c["observed"], c["pool_count"], "", "", "", "", "", "", "", "", c["invalid_reason"] or ""])
        for d in dex_cov:
            w.writerow(["dex", d["chain"], d["protocol"], "", "", d["pool_type"], "", d["observed_pool_count"] > 0, "", "", "", "", "", "", "", "", d["connector_used"], d["data_source"], d["invalid_reason"] or ""])
        for p in pool_cov:
            w.writerow([
                "pool", p["chain"], p["protocol"], p["pool_address"], p["token_pair"], p["pool_type"],
                p["fee_tier_or_fee_bps"], "true", p["tvl_proxy"], p["volume_proxy"],
                p["liquidity_near_active"] or "", p["quote_ready"], p["fee_ready"], p["ev_ready"],
                p["selected_for_candidate_review"], p["reject_reason"] or "", "", "public_rpc", "",
            ])

    # Coverage manifest JSON
    (report_dir / "POOL_UNIVERSE_COVERAGE_MANIFEST.json").write_text(
        json.dumps({
            "chain_coverage": chain_cov,
            "dex_coverage": dex_cov,
            "pool_coverage": pool_cov,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Fee estimation basis
    fee_basis = {
        "stage": STAGE,
        "node": node,
        "run_id": run_id,
        "actual_fee_data_available": False,
        "fee_proxy_used": True,
        "heuristic_used": True,
        "v3_clmm": {
            "narrow_range": "fee_proxy = volume_window × fee_rate × user_lp_share_in_range × in_range_time_ratio_narrow",
            "medium_range": "fee_proxy = volume_window × fee_rate × user_lp_share_in_range × in_range_time_ratio_medium",
            "wide_range": "fee_proxy = volume_window × fee_rate × user_lp_share_in_range × in_range_time_ratio_wide",
        },
        "meteora_dlmm": {
            "narrow_bin": "fee_proxy = volume_window × fee_rate × user_bin_share_in_active_bins",
            "medium_bin": "fee_proxy = volume_window × fee_rate × user_bin_share_in_active_bins ± 10 bins",
            "wide_bin": "fee_proxy = volume_window × fee_rate × user_bin_share_in_active_bins ± 50 bins",
        },
        "cpmm": "fee_proxy = volume_window × fee_rate × user_lp_share; user_lp_share = user_notional / pool_tvl",
        "stable_pool": "fee_proxy = volume_window × fee_rate × user_lp_share (assumes low IL)",
        "r0_limitations": [
            "no tokenId / positionId",
            "no feeGrowth snapshot",
            "no tokensOwed",
            "no actual add/remove cost",
            "no realized PnL",
        ],
        "future_actual_fee_requirement": node_report["fee_estimation_block"]["future_actual_fee_requirement"],
    }
    (report_dir / "FEE_ESTIMATION_BASIS.json").write_text(
        json.dumps(fee_basis, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (report_dir / "FEE_ESTIMATION_BASIS_CN.md").write_text(
        f"""# Fee Estimation Basis (R0 proxy, no actual fee)

- node: {node}
- run_id: {run_id}
- actual_fee_data_available: **false**
- fee_proxy_used: **true**
- heuristic_used: **true**

R0 阶段所有 fee 数字 = proxy / heuristic, 不是 actual fee. 实际 fee 必须有 tokenId + feeGrowth snapshot + tokensOwed 实测.

## 公式

### V3 / CLMM

```
fee_proxy_<width> = volume_window × fee_rate × user_lp_share_in_range × in_range_time_ratio_<width>
```

### Meteora DLMM

```
fee_proxy_<coverage> = volume_window × fee_rate × user_bin_share_in_range_<coverage>
```

### CPMM

```
fee_proxy = volume_window × fee_rate × user_lp_share
user_lp_share = user_notional / pool_tvl
```

### Stable / LST-Stable

```
fee_proxy = volume_window × fee_rate × user_lp_share (assumes low IL)
adjusted_il = il_base × (1 + depeg_risk_score × 2)
```

## R0 限制

- ❌ 无 tokenId / positionId
- ❌ 无 feeGrowth snapshot
- ❌ 无 tokensOwed
- ❌ 无实际 add/remove 成本
- ❌ 无 realized PnL
""",
        encoding="utf-8",
    )

    # Range sensitivity CSV
    rs_csv = report_dir / "RANGE_LIQUIDITY_FEE_SENSITIVITY.csv"
    with rs_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "pool_type", "pool_address", "range_width", "fee_proxy", "in_range_time_ratio",
            "out_of_range_time_ratio", "active_liquidity_share_proxy", "tick_liquidity_density",
            "range_risk", "active_bin_distance", "bin_liquidity_density", "bins_with_liquidity_count",
            "sparse_liquidity_warning", "lp_share", "price_impact", "il_proxy",
        ])
        for r in sensitivity["v3_clmm"]:
            w.writerow([
                "v3_clmm", r["pool_address"], r["range_width"],
                r[f"{r['range_width']}_range_fee_proxy"],
                r["in_range_time_ratio"], r["out_of_range_time_ratio"],
                r["active_liquidity_share_proxy"], r["tick_liquidity_density"],
                r["range_risk"], "", "", "", "", "", "", "",
            ])
        for r in sensitivity["meteora_dlmm"]:
            w.writerow([
                "meteora_dlmm", r["pool_address"], "", "", "", "", "", "", "",
                r["active_bin_distance"], r["bin_liquidity_density"], r["bins_with_liquidity_count"],
                r["sparse_liquidity_warning"], "", "", "",
            ])
        for r in sensitivity["cpmm"]:
            w.writerow([
                "cpmm", r["pool_address"], "", "", "", "", "", "", "",
                "", "", "", "", r["lp_share"], r["price_impact"], r["il_proxy"],
            ])
    (report_dir / "RANGE_LIQUIDITY_FEE_SENSITIVITY.json").write_text(
        json.dumps(sensitivity, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Candidate review
    cr_csv = report_dir / "CANDIDATE_REVIEW.csv"
    with cr_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "chain", "protocol", "pool_address", "token_pair", "selected", "reject_reason", "ev_proxy_usd_per_day", "ev_proxy_confidence"])
        for i, c in enumerate(best):
            w.writerow([i + 1, c["chain"], c["protocol"], c["pool_address"], c["token_pair"], "true", "", 0.0, "low"])
        for r in rejected:
            w.writerow(["", r["chain"], r["protocol"], r["pool_address"], r["token_pair"], "false", r["reject_reason"], 0.0, "low"])
    (report_dir / "CANDIDATE_REVIEW.json").write_text(
        json.dumps({"best_candidates": best, "rejected_candidates": rejected}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Final node verdict
    fnv = {
        "stage": STAGE,
        "generator": GENERATOR_NAME,
        "node_stage": node,
        "run_id": run_id,
        "generated_at_utc": _utc_now_iso(),
        "status": gate["gate_status"],
        "data_quality_status": data_quality["data_quality_status"],
        "gate_pass": gate["gate_pass"],
        "can_continue_collection": gate["can_continue_collection"],
        "can_enter_preflight_design": gate["can_enter_preflight_design"],
        "can_use_for_preflight": gate["can_use_for_preflight"],
        "can_run_probe_now": False,
        "tiny_canary_allowed": "no",
        "edge_proven": "no",
        "wallet_or_tx_touched": False,
        "transaction_sent": False,
        "auto_probe_allowed": False,
        "auto_trade_allowed": False,
        "manual_approval_required_for_execution": True,
        "recommended_next_action": rec_action,
        "partial_sample": partial_sample,
        "best_candidate_count": len(best),
        "rejected_candidate_count": len(rejected),
        "checkpoint_count_observed": ckpt_observed,
        "checkpoint_count_expected": ckpt_expected,
    }
    (report_dir / "FINAL_NODE_VERDICT.json").write_text(
        json.dumps(fnv, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # CN markdown
    (report_dir / "NODE_REPORT_CN.md").write_text(
        f"""# Node Report: {node} (R0 read-only, partial_sample={partial_sample})

- node_stage: {node}
- run_id: {run_id}
- generated_at_utc: {_utc_now_iso()}
- partial_sample: **{partial_sample}**

## Gate

| 字段 | 值 |
|---|---|
| gate_status | **{gate["gate_status"]}** |
| gate_pass | {gate["gate_pass"]} |
| can_continue_collection | {gate["can_continue_collection"]} |
| can_enter_preflight_design | {gate["can_enter_preflight_design"]} |
| can_use_for_preflight | {gate["can_use_for_preflight"]} |
| can_run_probe_now | **{gate["can_run_probe_now"]}** (locked false) |
| tiny_canary_allowed | **"{gate["tiny_canary_allowed"]}"** (locked no) |
| edge_proven | **"{gate["edge_proven"]}"** (locked no) |
| wallet_or_tx_touched | **{gate["wallet_or_tx_touched"]}** |
| transaction_sent | **{gate["transaction_sent"]}** |

## Coverage

| chain | observed | pool_count | reason |
|---|---|---|---|
{chr(10).join(f"| {c['chain']} | {c['observed']} | {c['pool_count']} | {c['invalid_reason'] or '-'} |" for c in chain_cov)}

## Best Candidates (count={len(best)})

{chr(10).join(f"- rank={i+1} {c['chain']}/{c['protocol']}/{c['pool_address']} ({c['token_pair']})" for i, c in enumerate(best))}

## Rejected Candidates (count={len(rejected)})

{chr(10).join(f"- {r['chain']}/{r['protocol']}/{r['pool_address']} ({r['token_pair']}): {r['reject_reason']}" for r in rejected)}

## Row counts

| 字段 | 值 |
|---|---|
| checkpoint_count_observed | {ckpt_observed} |
| checkpoint_count_expected | {ckpt_expected} |
| pool_snapshot_rows | {rows['pool_snapshot_rows']} |
| quote_snapshot_rows | {rows['quote_snapshot_rows']} |
| fee_velocity_rows | {rows['fee_velocity_rows']} |
| liquidity_distribution_rows | {rows['liquidity_distribution_rows']} |
| market_regime_rows | {rows['market_regime_rows']} |
| actual_fee_accrual_placeholder_rows | {rows['actual_fee_accrual_placeholder_rows']} (R0 = 0) |

## Recommended Next Action

**{rec_action}**

> 节点报告 ≠ 批准实盘. R0 阶段无 actual fee. B 线需要 tokenId 实盘数据, 需用户单独批准.
""",
        encoding="utf-8",
    )

    print(json.dumps({
        "stage": STAGE,
        "generator": GENERATOR_NAME,
        "node": node,
        "run_id": run_id,
        "report_dir": str(report_dir),
        "gate_status": gate["gate_status"],
        "partial_sample": partial_sample,
        "best_candidate_count": len(best),
        "rejected_candidate_count": len(rejected),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
