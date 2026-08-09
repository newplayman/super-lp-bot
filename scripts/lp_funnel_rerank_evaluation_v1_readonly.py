#!/usr/bin/env python3
"""Run the M0F R2 proxy cohort through the unchanged read-only terminal funnel.

This is an evidence runner, not a production-ranking switch.  It selects a
research-only proxy top-N, measures true NetCover for that exact batch, writes
Spearman/top-K evidence, and recommends either proxy ranking or the mandatory
APR fallback.  No entry threshold or fail-closed rule is modified.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.lp_funnel_rerank_v1_readonly import (
    build_rpc_budget,
    correlate_proxy_with_netcover,
    enrich_with_proxy,
    rank_stage1,
)
from scripts.lp_rpc_pool_v1_readonly import RpcPool
from scripts.lp_scanner_daemon_v1_readonly import (
    DefaultStages,
    FunnelOrchestrator,
    ScannerStore,
    ScreenBatch,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_SYMBOLS = (
    "USDC-AVAIL",
    "CADC-USDC",
    "MSUSD-USDC",
    "XSGD-USDC",
    "VCHF-USDC",
    "WETH-USDC",
    "WETH-CBBTC",
    "USDC-CBBTC",
)
TARGET_CHAIN = "Base"
TARGET_PROJECT = "aerodrome-slipstream"


def _is_exact_target_row(record: Mapping[str, Any]) -> bool:
    return (
        str(record.get("chain") or "") == TARGET_CHAIN
        and str(record.get("project") or "").lower() == TARGET_PROJECT
        and str(record.get("symbol") or "").upper() in TARGET_SYMBOLS
    )


def terminal_accepted(record: Mapping[str, Any]) -> bool:
    """Use exactly ScannerStore/_score_row's accepted derivation."""
    return bool(record.get("vetted", False)) and bool(record.get("netcover_pass", False))


def _target_only(record: Mapping[str, Any]) -> bool:
    sources = set(record.get("research_selection_sources") or ())
    return "ADD2_TARGET_RESEARCH" in sources and "PROXY_TOP_N" not in sources


def terminal_outcome(record: Mapping[str, Any]) -> str:
    """Return a deterministic terminal outcome; never emit UNKNOWN or gate 'ok'."""
    permanent = record.get("permanent_fail_closed_reason")
    if permanent:
        return f"PERMANENT_FAIL_CLOSED:{permanent}"
    if _target_only(record):
        detail = str(record.get("gate_reason") or "target_expansion_only")
        if detail.strip().lower() == "ok":
            detail = "target_expansion_only"
        if record.get("netcover_pass") is True:
            gate_result = "NETCOVER_GATE_PASS"
        else:
            status = str(record.get("netcover_gate_status") or "NO_NETCOVER_PASS_EVIDENCE")
            gate_result = f"NETCOVER_GATE_{status}"
        return f"RESEARCH_ONLY_NOT_PROXY_TOP_N:{detail};{gate_result}"
    if record.get("gate_ok") is False:
        detail = str(record.get("gate_reason") or "coarse_gate_failed")
        if detail.strip().lower() == "ok":
            detail = "coarse_gate_failed"
        return f"COARSE_GATE_REJECTED:{detail}"
    if record.get("entry_eligible") is False:
        reasons = record.get("entry_block_reasons") or ()
        detail = ",".join(str(reason) for reason in reasons) or "entry_ineligible"
        return f"ENTRY_INELIGIBLE:{detail}"
    if terminal_accepted(record):
        return "ACCEPTED"
    reason = str(record.get("rejection_reason") or "").strip()
    if reason and reason.lower() not in {"ok", "unknown"}:
        return f"NETCOVER_REJECTED:{reason}"
    status = str(record.get("netcover_gate_status") or "").strip()
    if status and status.lower() not in {"ok", "unknown"}:
        return f"NETCOVER_REJECTED:{status}"
    return "NETCOVER_REJECTED:NO_ACCEPTANCE_EVIDENCE"


def enforce_research_only_nonproduction(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Retain target-only economics while preventing research sampling acceptance."""
    output: list[dict[str, Any]] = []
    for source in records:
        record = dict(source)
        if _target_only(record):
            record["research_netcover_ratio"] = record.get("netcover_ratio")
            record["research_netcover_pass_before_boundary"] = bool(
                record.get("netcover_pass", False)
            )
            record["research_vetted_before_boundary"] = bool(record.get("vetted", False))
            record["research_only_forced_nonproduction"] = True
            detail = str(record.get("gate_reason") or "target_expansion_only")
            if detail.strip().lower() == "ok":
                detail = "target_expansion_only"
            record["vetted"] = False
            record["rejection_reason"] = f"RESEARCH_ONLY_NOT_PROXY_TOP_N:{detail}"
        record["accepted"] = terminal_accepted(record)
        record["terminal_outcome"] = terminal_outcome(record)
        output.append(record)
    return output


class CountingRpcPool:
    """Count logical reads while delegating rotation/backoff unchanged."""

    def __init__(self, delegate: RpcPool):
        self.delegate = delegate
        self.calls: Counter[str] = Counter()

    def call(self, method: str, params: Any, timeout: int = 20) -> Any:
        self.calls[method] += 1
        return self.delegate.call(method, params, timeout=timeout)

    def health_snapshot(self) -> dict[str, Any]:
        return self.delegate.health_snapshot()


class ProxyEvidenceStages(DefaultStages):
    """Use proxy order for this validation batch only, never as gate evidence."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.screened_with_proxy: list[dict[str, Any]] = []
        self.passed_proxy_order: list[dict[str, Any]] = []
        self.research_candidates: list[dict[str, Any]] = []
        self.terminal_rows: list[dict[str, Any]] = []

    def screen(self) -> ScreenBatch:
        from scripts import lp_universe_screener_v1_readonly as screener

        pools = screener.fetch_pools()
        selected = [
            pool
            for pool in pools
            if pool.get("chain") == self.chain and pool.get("project") in self.projects
        ]
        gates = {
            "min_tvl": self.min_tvl,
            "min_vol1d": self.min_vol1d,
            "suspect_reward_apr": screener.DEFAULTS["suspect_reward_apr"],
            "suspect_vol_tvl": screener.DEFAULTS["suspect_vol_tvl"],
        }
        assessed = [dict(screener.assess(pool, gates), chain=self.chain) for pool in selected]
        enriched = enrich_with_proxy(assessed)
        passed = [record for record in enriched if record.get("gate_ok")]
        # Evidence collection is necessarily proxy-selected; this does not
        # assert that correlation is valid and cannot bypass the fifth gate.
        # Reuse rank annotation but order by its proxy comparison rank solely
        # for evidence collection. No fake/bootstrapped validity claim is fed
        # into the production switch.
        compared = rank_stage1(passed, correlation_evidence=None)
        ranked = sorted(compared, key=lambda record: int(record["proxy_rank"]))
        for record in ranked:
            record["stage1_ranking_method"] = "PROXY_RESEARCH_VALIDATION_ONLY"
        proxy_top = ranked[: self.top]
        # ADD-2 requires terminal evidence for every live matching target even
        # if the unproven proxy fails to put it in top-N. This union is research
        # sampling only; target identity never affects production ordering or a
        # terminal gate decision.
        target_matches = [
            record for record in enriched
            if _is_exact_target_row(record)
        ]
        candidates_by_id: dict[str, dict[str, Any]] = {}
        for source, records in (
            ("PROXY_TOP_N", proxy_top),
            ("ADD2_TARGET_RESEARCH", target_matches),
        ):
            for index, record in enumerate(records):
                identity = str(record.get("llama_pool_id") or record.get("pool") or f"{source}:{index}")
                candidate = candidates_by_id.setdefault(identity, dict(record))
                selection = list(candidate.get("research_selection_sources") or ())
                if source not in selection:
                    selection.append(source)
                candidate["research_selection_sources"] = selection
                candidate["target_research_only_never_allowlist"] = (
                    "ADD2_TARGET_RESEARCH" in selection
                )
        self.screened_with_proxy = enriched
        self.passed_proxy_order = ranked
        self.research_candidates = list(candidates_by_id.values())
        return ScreenBatch(all_records=enriched, candidates=self.research_candidates)

    def netcover(self, records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        # Keep the full in-memory cohort. ScannerStore's operational schema is
        # uniquely keyed by resolved on-chain pool and may intentionally
        # collapse duplicate DefiLlama leads via INSERT OR REPLACE; correlation
        # must instead retain every selected lead from this same batch.
        self.terminal_rows = enforce_research_only_nonproduction(
            list(super().netcover(records))
        )
        return self.terminal_rows


def load_latest_score_rows(db_path: Path) -> tuple[str | None, list[dict[str, Any]]]:
    uri = f"file:{db_path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
        latest_row = connection.execute("SELECT max(as_of) FROM opportunity_scores").fetchone()
        latest = latest_row[0] if latest_row else None
        rows = [] if latest is None else connection.execute(
            "SELECT pool, netcover_ratio, accepted, rejection_reason, score_json "
            "FROM opportunity_scores WHERE as_of=? ORDER BY id",
            (latest,),
        ).fetchall()
    output: list[dict[str, Any]] = []
    for pool, netcover, accepted, reason, raw in rows:
        record = json.loads(raw)
        record["pool"] = record.get("pool") or pool
        record["netcover_ratio"] = netcover
        record["accepted"] = bool(accepted)
        record["rejection_reason"] = reason or record.get("rejection_reason")
        output.append(record)
    return latest, output


def target_evidence(
    live_universe: Sequence[Mapping[str, Any]],
    universe_proxy_order: Sequence[Mapping[str, Any]],
    actual_rows: Sequence[Mapping[str, Any]],
    top_n: int,
) -> list[dict[str, Any]]:
    positions: dict[str, list[tuple[int, Mapping[str, Any]]]] = {symbol: [] for symbol in TARGET_SYMBOLS}
    for rank, row in enumerate(universe_proxy_order, 1):
        symbol = str(row.get("symbol") or "").upper()
        if symbol in positions and _is_exact_target_row(row):
            positions[symbol].append((rank, row))
    live_counts = Counter(
        str(row.get("symbol") or "").upper()
        for row in live_universe
        if _is_exact_target_row(row)
    )
    actual_by_symbol: dict[str, list[Mapping[str, Any]]] = {symbol: [] for symbol in TARGET_SYMBOLS}
    for row in actual_rows:
        symbol = str(row.get("symbol") or "").upper()
        if (
            symbol in actual_by_symbol
            and _is_exact_target_row(row)
            and "ADD2_TARGET_RESEARCH" in (row.get("research_selection_sources") or ())
        ):
            actual_by_symbol[symbol].append(row)
    result = []
    for symbol in TARGET_SYMBOLS:
        matches = positions[symbol]
        best = matches[0] if matches else None
        actual = actual_by_symbol[symbol]
        result.append({
            "symbol": symbol,
            "live_universe_matches": live_counts[symbol],
            "coarse_gate_passed_matches": len(matches),
            "best_proxy_rank": best[0] if best else None,
            "best_proxy_netcover": best[1].get("proxy_netcover") if best else None,
            "in_proxy_top_n": bool(best and best[0] <= top_n),
            "stage2_terminal_rows": len(actual),
            "fully_calculable_rows": sum(row.get("netcover_ratio") is not None for row in actual),
            "best_true_netcover": max(
                (float(row["netcover_ratio"]) for row in actual if row.get("netcover_ratio") is not None),
                default=None,
            ),
            "accepted_rows": sum(terminal_accepted(row) for row in actual),
            "terminal_outcomes": sorted({terminal_outcome(row) for row in actual}),
            "live_status": (
                "NOT_IN_LIVE_UNIVERSE"
                if live_counts[symbol] == 0
                else "LIVE_BUT_NOT_COARSE_GATE_ELIGIBLE"
                if not matches
                else "LIVE"
            ),
            "target_semantics": "validation_target_only_never_allowlist_or_gate_bypass",
        })
    return result


def _fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(payload: Mapping[str, Any]) -> str:
    corr = payload["correlation"]
    budget = payload["rpc_budget"]
    validity = "VALID" if corr["proxy_valid"] else "INVALID"
    lines = [
        "# M0F FIX-R2 — Stage-1 proxy correlation",
        "",
        "## Result",
        "",
        f"Proxy evidence is **{validity}**. Production recommendation: "
        f"`{corr['production_ranking']}`.",
        "",
        f"- same research batch: `{corr['same_batch_records']}` rows",
        f"- fully calculable proxy/true pairs: `{corr['fully_calculable_pairs']}` "
        "(only these participate in correlation)",
        f"- Spearman: `{_fmt(corr['spearman'])}`; validity requires "
        f"`>= {corr['validity_threshold']}` and at least "
        f"`{corr['minimum_correlation_pairs']}` calculable pairs",
        f"- top-K hit: `{corr['top_k_hits']}/{corr['top_k_denominator']}` = "
        f"`{_fmt(corr['top_k_hit_rate'])}`",
        f"- top-K definition: {corr['top_k_definition']}",
        "- correlation retains the full in-memory selected-lead cohort; SQLite's operational "
        "unique resolved-pool key is not allowed to collapse duplicate DefiLlama leads first",
        "",
        "## Proxy formula (zero RPC)",
        "",
        "`income_apr = apyBase×0.65 + apyReward×REWARD_HAIRCUTS[known category]`",
        "",
        "`cost_apr = IL(sigma, stable/same-anchor, pair quality)×(1+LVR 0.5) "
        "+ annualized(2×fee_tier×50U + Base gas 0.0795U)/50U`",
        "",
        "`proxy_netcover = income_apr / cost_apr`",
        "",
        "Low fee tier, stable/same-anchor identity, and emission-dominant blue-chip identity "
        "are structured income/cost inputs. Only reward-dominant double-major pairs retain the "
        "full existing category haircut; other known rewards receive an extra conservative "
        "reliability discount. They are not post-hoc bonuses. The position is "
        "fixed at M1 50U and is not a ranking factor. Missing sigma/fee tier or unknown reward "
        "category makes the proxy unavailable and therefore cannot activate proxy ordering.",
        "DefiLlama's generic sigma is a Stage-1 proxy assumption, not the terminal gate's "
        "on-chain measured pair-price sigma; weak observed correlation therefore automatically "
        "selects the original APR fallback.",
        "",
        "## ADD-2 validation targets",
        "",
        "**Identity limitation:** the audit target table supplies chain/project/symbol but no "
        "DefiLlama pool id. To avoid guessing identity from stale APR, each symbol label expands "
        "to every live row with the exact `Base / aerodrome-slipstream / symbol` identity. "
        "The per-symbol expansion counts are shown below.",
        "",
        "| symbol | live status | live matches | coarse-pass | best proxy rank | in top-N | terminal rows | calculable | best true NetCover | accepted | outcomes |",
        "| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["targets"]:
        lines.append(
            f"| {row['symbol']} | {row['live_status']} | {row['live_universe_matches']} | "
            f"{row['coarse_gate_passed_matches']} | {_fmt(row['best_proxy_rank'])} | "
            f"{row['in_proxy_top_n']} | {row['stage2_terminal_rows']} | {row['fully_calculable_rows']} | "
            f"{_fmt(row['best_true_netcover'])} | {row['accepted_rows']} | "
            f"{', '.join(row['terminal_outcomes']) or '—'} |"
        )
    lines.extend([
        "",
        "The terminal research cohort is `proxy top-N ∪ every live target-symbol row`, de-duplicated "
        "by DefiLlama pool id. Correlation uses only the same proxy-top-N subcohort so target "
        "oversampling cannot improve it. Target rows are forced into research evaluation only; no "
        "target is whitelisted, production-ranked, or directly accepted. Missing symbols are "
        "reported as NOT_IN_LIVE_UNIVERSE and never fabricated.",
        "",
        "## RPC budget",
        "",
        f"Measured logical RPC calls: `{budget['measured_total_calls']}`. Conservative upper "
        f"bound before provider retries: `{budget['upper_total_calls']}`.",
        "",
        "| measured method | calls |",
        "| --- | ---: |",
    ])
    for method, count in sorted(budget["measured_calls_by_method"].items()):
        lines.append(f"| {method} | {count} |")
    lines.extend(["", "| upper-bound component | calls |", "| --- | ---: |"])
    for component, count in budget["upper_components"].items():
        lines.append(f"| {component} | {count} |")
    lines.extend([
        "",
        f"Budget semantics: {budget['upper_bound_semantics']}.",
        "",
        "## Safety",
        "",
        "This run used public read-only RPC calls only. It did not sign, broadcast, access a "
        "wallet, change NetCover thresholds, or start a daemon.",
        "",
    ])
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stamp", default=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--out-root", default=str(REPO_ROOT / "reports" / "lp_funnel_rerank"))
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--window-blocks", type=int, default=86_400)
    parser.add_argument("--window-days", type=float, default=1.0)
    parser.add_argument("--n-windows", type=int, default=6)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    invoked_args = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(argv)
    if min(args.top, args.top_k, args.window_blocks, args.n_windows) <= 0 or args.window_days <= 0:
        raise SystemExit("top/window arguments must be positive")
    out_dir = Path(args.out_root) / args.stamp
    out_dir.mkdir(parents=True, exist_ok=False)
    db_path = out_dir / "scanner.db"
    counter = CountingRpcPool(RpcPool("base"))
    stages = ProxyEvidenceStages(
        chain="Base",
        projects=("aerodrome-slipstream", "uniswap-v3"),
        top=args.top,
        window_blocks=args.window_blocks,
        window_days=args.window_days,
        n_windows=args.n_windows,
        rpc_pool=counter,
    )
    cycle = FunnelOrchestrator(stages, ScannerStore(db_path)).run_once(
        refresh_coarse=True, as_of=datetime.now(timezone.utc)
    )
    latest, persisted_rows = load_latest_score_rows(db_path)
    actual_rows = stages.terminal_rows
    correlation_rows = [
        row for row in actual_rows
        if "PROXY_TOP_N" in (row.get("research_selection_sources") or ())
    ]
    correlation = correlate_proxy_with_netcover(correlation_rows, top_k=args.top_k)
    targets = target_evidence(
        stages.screened_with_proxy,
        stages.passed_proxy_order,
        actual_rows,
        args.top,
    )
    # 2-second Base block time; count full chunks rather than pretending log
    # retrieval is one RPC call per multi-day window.
    resolve_chunks = math.ceil(args.window_blocks / 2_000)
    stability_blocks = math.ceil(args.window_days * 86_400 / 2.0)
    stability_chunks = math.ceil(stability_blocks / 2_000)
    budget = build_rpc_budget(
        top_n=len(stages.research_candidates),
        n_windows=args.n_windows,
        resolve_log_chunks=resolve_chunks,
        stability_log_chunks_per_window=stability_chunks,
        measured_calls=dict(counter.calls),
    )
    payload = {
        "schema_version": "lp_funnel_rerank_r2_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scanner_as_of": latest,
        "command": " ".join(["python3", os.path.relpath(__file__, REPO_ROOT), *invoked_args]),
        "cycle": cycle.__dict__,
        "stage1": {
            "free_universe_records": len(stages.screened_with_proxy),
            "passed_coarse_gates": len(stages.passed_proxy_order),
            "proxy_calculable": sum(
                row.get("proxy_status") == "CALCULABLE" for row in stages.passed_proxy_order
            ),
            "research_top_n": args.top,
            "evaluated_union_records": len(stages.research_candidates),
            "terminal_in_memory_records": len(actual_rows),
            "sqlite_persisted_unique_pool_rows": len(persisted_rows),
            "sqlite_deduplication_note": (
                "operational scanner schema is unique by resolved pool; correlation uses the "
                "full in-memory selected-lead cohort before any INSERT OR REPLACE collapse"
            ),
            "correlation_cohort": "PROXY_TOP_N_ONLY",
            "production_ranking_was_not_changed_by_this_runner": True,
        },
        "correlation": correlation,
        "targets": targets,
        "target_identity_limitation": (
            "audit table has no pool ids; exact chain/project/symbol labels expand to all live "
            "matching rows; stale income APR is never used to guess identity"
        ),
        "rpc_budget": budget,
        "redlines": {
            "wallet_or_signing": False,
            "broadcast": False,
            "paid_data": False,
            "threshold_change": False,
            "long_running_process_started": False,
        },
    }
    (out_dir / "correlation.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    (out_dir / "correlation.md").write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({
        "out": str(out_dir),
        "same_batch": correlation["same_batch_records"],
        "fully_calculable": correlation["fully_calculable_pairs"],
        "spearman": correlation["spearman"],
        "top_k_hit_rate": correlation["top_k_hit_rate"],
        "proxy_valid": correlation["proxy_valid"],
        "production_ranking": correlation["production_ranking"],
        "measured_rpc_calls": budget["measured_total_calls"],
    }, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
