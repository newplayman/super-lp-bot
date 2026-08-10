#!/usr/bin/env python3
"""Instrumented TP-D full funnel once-run (READ-ONLY).

This runner uses the production ``DefaultStages`` and ``RpcPool`` while
recording physical JSON-RPC attempts, logical stage timings, Multicall3
validation evidence, and final RPC health.  It exists so D1/D2/D4 acceptance
numbers are reproducible without adding observability behavior to the daemon.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import lp_rpc_pool_v1_readonly as rpc_module
from scripts.lp_scanner_daemon_v1_readonly import (
    DefaultStages,
    FunnelOrchestrator,
    ScannerStore,
    export_latest_vetted_menu,
)


def conservative_rpc_budget(top_n: int) -> dict[str, Any]:
    """Compare old 92x6 serial upper bound with TP-D's 10-window path.

    Both sides count logical JSON-RPC requests before provider retries and use
    the repository's inclusive 2,001-block log chunks (44 per resolve day and
    22 per stability day).  The post-D1 contract bound assumes the worst case
    where all six ordered Slipstream factory probes per candidate return
    distinct nonzero pools, so it is intentionally stricter than observed.
    """
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    old = {
        "batch_tip_calls": 2,
        "resolve_factory_lookup_calls": 92 * 6,
        "resolve_candidate_validation_calls": 92 * 18,
        "resolve_window_log_calls": 92 * 44,
        "stability_window_log_calls": 92 * 6 * 22,
        "terminal_live_state_calls": 92 * 2,
        "cross_route_fixed_batch_calls": 89,
    }
    batch = 60
    ceil_div = lambda value: (value + batch - 1) // batch
    max_factory_results = top_n * 6
    new = {
        "batch_tip_calls": 2,
        "multicall3_runtime_validation_calls": 1,
        "resolve_factory_aggregate_calls": ceil_div(top_n * 6),
        "resolve_pool_identity_aggregate_calls": ceil_div(max_factory_results * 3),
        "resolve_token_decimals_aggregate_calls": ceil_div(max_factory_results * 2),
        "resolve_pool_code_calls": max_factory_results,
        "resolve_window_log_calls": top_n * 44,
        "stability_window_log_calls": top_n * 10 * 22,
        "terminal_live_state_aggregate_calls": ceil_div(top_n * 2),
        "cross_route_fixed_batch_calls": 89,
    }
    old_total, new_total = sum(old.values()), sum(new.values())
    return {
        "semantics": "logical requests before provider retries; conservative upper bound",
        "old": {"top_n": 92, "n_windows": 6, "components": old, "total": old_total},
        "new": {"top_n": top_n, "n_windows": 10, "components": new, "total": new_total},
        "delta": new_total - old_total,
        "within_old_budget": new_total <= old_total,
    }


class PhysicalRequestCounter:
    def __init__(self) -> None:
        self.attempts: Counter[str] = Counter()
        self.successes: Counter[str] = Counter()
        self.failures: Counter[str] = Counter()
        self.endpoints: Counter[str] = Counter()

    def post(self, url: str, method: str, params: Any, timeout: int = 20) -> Any:
        self.attempts[method] += 1
        self.endpoints[url] += 1
        try:
            response = rpc_module._default_post(url, method, params, timeout=timeout)
        except Exception:
            self.failures[method] += 1
            raise
        if isinstance(response, dict) and "result" in response:
            self.successes[method] += 1
        else:
            self.failures[method] += 1
        return response

    def evidence(self) -> dict[str, Any]:
        return {
            "physical_attempts_by_method": dict(sorted(self.attempts.items())),
            "physical_attempts_total": sum(self.attempts.values()),
            "successes_by_method": dict(sorted(self.successes.items())),
            "failures_by_method": dict(sorted(self.failures.items())),
            "attempts_by_endpoint": dict(sorted(self.endpoints.items())),
        }


class TimedStages(DefaultStages):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.stage_seconds: dict[str, float] = {}

    def _timed(self, name: str, function: Any, *args: Any) -> Any:
        print(f"[tp-d] {name} start", flush=True)
        started = time.monotonic()
        result = function(*args)
        elapsed = time.monotonic() - started
        self.stage_seconds[name] = elapsed
        size = len(result) if hasattr(result, "__len__") else "-"
        print(f"[tp-d] {name} done seconds={elapsed:.3f} rows={size}", flush=True)
        return result

    def screen(self):
        return self._timed("screen", super().screen)

    def resolve(self, candidates):
        return self._timed("resolve", super().resolve, candidates)

    def multiwindow(self, resolved):
        return self._timed("multiwindow", super().multiwindow, resolved)

    def funnel(self, resolved, stability):
        return self._timed("funnel", super().funnel, resolved, stability)

    def netcover(self, records):
        return self._timed("netcover", super().netcover, records)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--top", type=int, required=True)
    parser.add_argument("--n-windows", type=int, default=10)
    parser.add_argument("--pace-secs", type=float, default=0.2)
    parser.add_argument(
        "--endpoint-url",
        action="append",
        default=[],
        help="restrict RpcPool to a prequalified configured free endpoint (repeatable)",
    )
    args = parser.parse_args()
    if args.top <= 0 or args.n_windows <= 0 or args.pace_secs < 0:
        parser.error("top/windows must be positive and pace non-negative")

    args.out.mkdir(parents=True, exist_ok=True)
    counter = PhysicalRequestCounter()
    rpc_pool = rpc_module.RpcPool(
        "base", post=counter.post, pace_secs=args.pace_secs
    )
    if args.endpoint_url:
        configured = {item["url"]: item for item in rpc_pool._endpoints}
        unknown = sorted(set(args.endpoint_url) - set(configured))
        if unknown:
            parser.error(f"endpoint URL is not in the Base registry: {unknown}")
        selected = [configured[url] for url in args.endpoint_url]
        if not all(item.get("getlogs") is True for item in selected):
            parser.error("TP-D full run endpoint subset must be getLogs-capable")
        rpc_pool._endpoints = selected
    stages = TimedStages(
        chain="Base",
        projects=("aerodrome-slipstream", "uniswap-v3"),
        top=args.top,
        n_windows=args.n_windows,
        rpc_pool=rpc_pool,
    )
    db_path = args.out / "scanner.db"
    store = ScannerStore(db_path)
    orchestrator = FunnelOrchestrator(stages, store)
    started = time.monotonic()
    result = orchestrator.run_once(
        refresh_coarse=True,
        as_of=datetime.now(timezone.utc),
    )
    cycle_seconds = time.monotonic() - started
    screen_batch = orchestrator._screen_batch
    if screen_batch is not None:
        (args.out / "stage1_screen.json").write_text(
            json.dumps(screen_batch.all_records, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (args.out / "stage2_candidates.json").write_text(
            json.dumps(screen_batch.candidates, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    menu = export_latest_vetted_menu(db_path, args.out / "vetted_menu.json")
    evidence = {
        "schema": "lp_tp_d_full_once_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "signed": False,
        "broadcast_count": 0,
        "config": {
            "top": args.top,
            "n_windows": args.n_windows,
            "stable_min_frac": 0.7,
            "rpc_pace_secs": args.pace_secs,
            "fetch_pace_secs": float(os.environ.get("FETCH_PACE_SECS", "0.12")),
            "qualified_endpoint_urls": list(args.endpoint_url),
        },
        "conservative_rpc_budget": conservative_rpc_budget(args.top),
        "cycle": vars(result),
        "cycle_seconds": cycle_seconds,
        "stage_seconds": stages.stage_seconds,
        "rpc": counter.evidence(),
        "rpc_health": rpc_pool.health_snapshot(),
        "multicall3": {
            "evidence": stages._multicall3.evidence,
            "request_counts": stages._multicall3.request_counts(),
            "cache_hits": stages._batched_rpc.cache_hits,
            "failed_primes": stages._batched_rpc.failed_primes,
        },
        "vetted_menu_export": menu,
    }
    (args.out / "once_evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "cycle_seconds": round(cycle_seconds, 3),
        "physical_rpc_attempts": evidence["rpc"]["physical_attempts_total"],
        "rpc_health": evidence["rpc_health"]["state"],
        "accepted": result.accepted,
        "evidence": str(args.out / "once_evidence.json"),
    }, sort_keys=True), flush=True)
    return 0 if evidence["rpc_health"]["state"] == "NORMAL" else 4


if __name__ == "__main__":
    raise SystemExit(main())
