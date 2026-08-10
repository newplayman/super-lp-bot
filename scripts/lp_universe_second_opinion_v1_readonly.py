#!/usr/bin/env python3
"""Zero-RPC second opinion over the DefiLlama Stage-1 universe.

This tool is deliberately independent of the on-chain scanner orchestration.
It reuses (rather than reimplements) the audited M0F ``proxy_netcover`` model,
uses only free DefiLlama fields, and treats proxy results as leads rather than
entry decisions.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lp_capital_tiers_v1_readonly import coarse_tvl_min_usd  # noqa: E402
from scripts.lp_funnel_rerank_v1_readonly import proxy_netcover  # noqa: E402
from scripts.lp_universe_screener_v1_readonly import (  # noqa: E402
    DEFAULTS,
    assess,
    fetch_pools,
    strip_untrusted_reward_evidence,
)


DEFAULT_PROJECTS = ("aerodrome-slipstream", "uniswap-v3")
TOP_N = 50


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def il_tolerance_apr(proxy: Mapping[str, Any]) -> float | None:
    """Maximum IL APR that preserves proxy NetCover >=1 at fixed other costs."""
    income = _finite(proxy.get("proxy_income_apr_pct"))
    fixed = _finite(proxy.get("proxy_fixed_drag_apr_pct"))
    lvr = _finite(proxy.get("proxy_lvr_coefficient"))
    if income is None or fixed is None or lvr is None or lvr < 0.0:
        return None
    return (income - fixed) / (1.0 + lvr)


def analyze(
    raw_pools: Sequence[Mapping[str, Any]],
    *,
    chain: str = "Base",
    projects: Sequence[str] = DEFAULT_PROJECTS,
    capital_tier: str = "M1",
    min_tvl: float | None = None,
    min_vol1d: float = 50_000.0,
    top_n: int = TOP_N,
) -> dict[str, Any]:
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    project_set = {str(project) for project in projects}
    gates = {
        "min_tvl": coarse_tvl_min_usd(capital_tier, min_tvl),
        "min_vol1d": float(min_vol1d),
        "suspect_reward_apr": DEFAULTS["suspect_reward_apr"],
        "suspect_vol_tvl": DEFAULTS["suspect_vol_tvl"],
    }
    scoped = [
        strip_untrusted_reward_evidence(pool)
        for pool in raw_pools
        if pool.get("chain") == chain and pool.get("project") in project_set
    ]
    rows = []
    for pool in scoped:
        screened = assess(pool, gates)
        proxy = proxy_netcover(screened)
        rows.append({
            **screened,
            **proxy,
            "proxy_il_tolerance_apr_pct": il_tolerance_apr(proxy),
            "second_opinion_semantics": "zero_rpc_lead_only_not_entry_gate",
        })
    ranked = sorted(
        rows,
        key=lambda row: (
            row.get("proxy_netcover") is None,
            -float(row.get("proxy_netcover") or 0.0),
            -float(row.get("score") or 0.0),
            str(row.get("llama_pool_id") or ""),
        ),
    )
    calculable = [row for row in rows if row.get("proxy_netcover") is not None]
    proxy_pass = [row for row in calculable if float(row["proxy_netcover"]) >= 1.0]
    coarse_proxy_pass = [row for row in proxy_pass if row.get("gate_ok") is True]
    return {
        "schema": "lp_universe_second_opinion_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "chain": chain,
            "projects": list(projects),
            "raw_universe": len(raw_pools),
            "scoped_pools": len(scoped),
            "capital_tier": capital_tier,
            "coarse_gates": gates,
            "network": "DefiLlama free keyless HTTP only; zero RPC",
        },
        "summary": {
            "coarse_pass": sum(row.get("gate_ok") is True for row in rows),
            "entry_eligible_from_stage1_surrogate": sum(row.get("entry_eligible") is True for row in rows),
            "proxy_calculable": len(calculable),
            "proxy_netcover_ge_1_all_scoped": len(proxy_pass),
            "proxy_netcover_ge_1_and_coarse_pass": len(coarse_proxy_pass),
            "proxy_netcover_ge_1_coarse_and_entry_eligible": sum(
                row.get("entry_eligible") is True for row in coarse_proxy_pass
            ),
        },
        "model": {
            "implementation": "scripts.lp_funnel_rerank_v1_readonly.proxy_netcover",
            "position_usd": 50.0,
            "horizon_hours": 720.0,
            "proxy_is_entry_gate": False,
            "il_tolerance_formula": "(proxy_income_apr_pct - proxy_fixed_drag_apr_pct) / (1 + proxy_lvr_coefficient)",
        },
        "top_50": [
            {
                "rank": index,
                "llama_pool_id": row.get("llama_pool_id"),
                "symbol": row.get("symbol"),
                "project": row.get("project"),
                "tier_quality": row.get("tier_quality"),
                "tvl_usd": row.get("tvlUsd"),
                "volume_usd_1d": row.get("volumeUsd1d"),
                "fee_tier": row.get("fee_tier"),
                "apy_base": row.get("apyBase"),
                "apy_reward": row.get("apyReward"),
                "stage1_gate_ok": row.get("gate_ok") is True,
                "stage1_gate_reason": row.get("gate_reason"),
                "entry_eligible": row.get("entry_eligible") is True,
                "reward_persistence_status": row.get("reward_persistence_status"),
                "proxy_status": row.get("proxy_status"),
                "proxy_reason": row.get("proxy_reason"),
                "proxy_netcover": row.get("proxy_netcover"),
                "proxy_income_apr_pct": row.get("proxy_income_apr_pct"),
                "proxy_cost_apr_pct": row.get("proxy_cost_apr_pct"),
                "proxy_il_tolerance_apr_pct": row.get("proxy_il_tolerance_apr_pct"),
            }
            for index, row in enumerate(ranked[:top_n], 1)
        ],
        "proxy_unavailable_reasons": {
            reason: sum(row.get("proxy_reason") == reason for row in rows)
            for reason in sorted({str(row.get("proxy_reason")) for row in rows if row.get("proxy_reason")})
        },
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    scope, summary = report["scope"], report["summary"]
    lines = [
        "# LP universe second opinion v1（0 RPC）",
        "",
        f"范围：{scope['chain']} / {', '.join(scope['projects'])}；全网快照 {scope['raw_universe']} 条，范围内 {scope['scoped_pools']} 条。",
        f"proxy 可计算 {summary['proxy_calculable']}；proxy NetCover≥1 为 {summary['proxy_netcover_ge_1_all_scoped']}，同时过 Stage-1 粗筛为 {summary['proxy_netcover_ge_1_and_coarse_pass']}，再同时 entry_eligible 为 {summary['proxy_netcover_ge_1_coarse_and_entry_eligible']}。",
        "proxy 只用于第二意见与排序，不是入场闸；终端全成本 NetCover 与完整合取仍是唯一结论来源。",
        "",
        "| # | 池 | quality | coarse | entry | proxy NC | IL 容忍 APR | coarse 原因 |",
        "|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["top_50"]:
        nc = "—" if row["proxy_netcover"] is None else f"{float(row['proxy_netcover']):.4f}"
        tolerance = "—" if row["proxy_il_tolerance_apr_pct"] is None else f"{float(row['proxy_il_tolerance_apr_pct']):.3f}%"
        lines.append(
            f"| {row['rank']} | {row['symbol']} | {row['tier_quality']} | "
            f"{row['stage1_gate_ok']} | {row['entry_eligible']} | {nc} | {tolerance} | {row['stage1_gate_reason']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _load_raw(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping) and isinstance(payload.get("data"), list):
        return payload["data"]
    raise ValueError("input must be a DefiLlama list or {data:[...]}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Free Stage-1 LP universe second opinion")
    parser.add_argument("--input", type=Path, help="saved DefiLlama raw JSON; skips HTTP")
    parser.add_argument("--chain", default="Base")
    parser.add_argument("--projects", nargs="+", default=list(DEFAULT_PROJECTS))
    parser.add_argument("--capital-tier", default="M1")
    parser.add_argument("--min-tvl", type=float)
    parser.add_argument("--min-vol1d", type=float, default=50_000.0)
    parser.add_argument("--top", type=int, default=TOP_N)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    raw = _load_raw(args.input) if args.input else fetch_pools()
    report = analyze(
        raw, chain=args.chain, projects=args.projects, capital_tier=args.capital_tier,
        min_tvl=args.min_tvl, min_vol1d=args.min_vol1d, top_n=args.top,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "second_opinion.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    (args.out / "second_opinion.md").write_text(render_markdown(report), encoding="utf-8")
    print(
        f"second opinion scoped={report['scope']['scoped_pools']} "
        f"calculable={report['summary']['proxy_calculable']} "
        f"proxy_ge_1={report['summary']['proxy_netcover_ge_1_all_scoped']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
