#!/usr/bin/env python3
"""Read-only reconciliation of the portfolio paper runner and NetCover.

TP-J deliberately uses the runner as a positive control.  This module reads
only the runner's published book/heartbeat and immutable SQLite snapshots; it
never opens a wallet, signs, broadcasts, or contacts an RPC endpoint.

The comparison is intentionally *not* a retrospective trading backtest.  The
paper runner's realised fee/reward/IL observations are put into NetCover's
existing full-cost calculation at the real position size and elapsed holding
time.  Costs absent from the runner's output are labelled ``UNMODELED`` rather
than silently converted to zero.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.lp_cost_sensitivity_v1_readonly import _swap_components
from scripts.lp_netcover_engine_v1_readonly import REWARD_HAIRCUTS, evaluate_netcover
from scripts.lp_swap_cost_model_v1_readonly import clmm_token0_value_fraction


HISTORICAL_BASE_GAS_USD = 0.0795
EXIT_LATENCY_LOSS_APR_PCT_MODEL = 0.50
HOURS_PER_YEAR = 365.0 * 24.0

# These are immutable, already-recorded scanner observations.  They are used
# only for depth/price/decimal state and reward-route cost scaling; the income
# and IL inputs below come from the paper runner itself.
SNAPSHOT_SOURCES = {
    "0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1": (
        "reports/lp_funnel_autopsy/20260810_043427/scanner.db",
        "2026-08-10T04:34:39.491608+00:00",
    ),
    "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59": (
        "reports/lp_tp_d/20260810_d4_top68_w10_normal/scanner.db",
        "2026-08-10T13:24:29.678852+00:00",
    ),
    "0x0b1c2dcbbfa744ebd3fc17ff1a96a1e1eb4b2d69": (
        "reports/lp_scanner/scanner.db",
        "2026-08-13T08:52:53.521676+00:00",
    ),
    "0x4e829f8a5213c42535ab84aa40bd4adcce9cba02": (
        "reports/lp_tp_d/20260810_d4_top68_w10_normal/scanner.db",
        "2026-08-10T13:24:29.678852+00:00",
    ),
    "0x80cc08712aa61ce9dc7604f9ce7560a25094b862": (
        "reports/lp_funnel_autopsy/20260810_043427/scanner.db",
        "2026-08-10T04:34:39.491608+00:00",
    ),
    "0x529d2863a1521d0b57db028168fde2e97120017c": (
        "reports/lp_scanner/scanner.db",
        "2026-08-13T18:06:05.743131+00:00",
    ),
}


def _finite(value: Any, name: str, *, positive: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result) or result < 0 or (positive and result <= 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'non-negative'}")
    return result


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _last_jsonl(path: Path) -> dict[str, Any]:
    last: dict[str, Any] | None = None
    with path.open() as handle:
        for line in handle:
            if line.strip():
                last = json.loads(line)
    if last is None:
        raise ValueError(f"empty JSONL file: {path}")
    return last


def _snapshot_record(repo_root: Path, pool: str) -> tuple[dict[str, Any], dict[str, str]]:
    try:
        relative_path, as_of = SNAPSHOT_SOURCES[pool.lower()]
    except KeyError as exc:
        raise ValueError(f"no pinned scanner snapshot for {pool}") from exc
    path = repo_root / relative_path
    # mode=ro prevents the calibration from changing a scanner DB.  This is
    # deliberately a stored snapshot, not a request to the currently-running
    # scanner process.
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "select score_json from opportunity_scores "
            "where lower(pool) = ? and as_of = ? order by id desc limit 1",
            (pool.lower(), as_of),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ValueError(f"pinned snapshot row missing for {pool} at {as_of}")
    return json.loads(row[0]), {"path": relative_path, "as_of": as_of}


def _position_leg_swap_components(
    *, capital_usd: float, fee_tier: float, range_pct: float, snapshot: Mapping[str, Any],
    legacy_full_position_legs: bool,
) -> dict[str, float]:
    """Price two CLMM conversion legs under an explicit J1/J3 convention."""
    quote_usd = _finite(snapshot.get("measured_token1_usd", 1.0), "measured_token1_usd", positive=True)
    pool = SimpleNamespace(
        l_active_raw_historical=_finite(snapshot.get("last_swap_liquidity_raw"), "last_swap_liquidity_raw", positive=True),
        price_usd=_finite(snapshot.get("last_swap_price_token1_per_token0"), "last_swap_price", positive=True),
        fee_tier=_finite(fee_tier, "fee_tier"),
        dec0=int(_finite(snapshot.get("dec0"), "dec0")),
        dec1=int(_finite(snapshot.get("dec1"), "dec1")),
    )
    fraction = 1.0 if legacy_full_position_legs else clmm_token0_value_fraction(
        pool.price_usd, _finite(range_pct, "range_pct", positive=True)
    )
    quote_components = _swap_components(
        capital_usd / quote_usd, pool, conversion_fraction=fraction,
    )
    return {key: float(value) * quote_usd for key, value in quote_components.items()}


def _scaled_reward_conversion_cost(
    *, reward_ev_usd: float, snapshot: Mapping[str, Any]
) -> float:
    """Scale the pinned route quote from its observed reward notional.

    The selected route is a fee-plus-local-slippage quote.  Scaling is exact
    for its fee component and an explicitly disclosed local approximation for
    the tiny reward-conversion notional; it is preferable to pretending the
    runner had no conversion cost at all.
    """
    if reward_ev_usd == 0.0:
        return 0.0
    observed_reward = _finite(snapshot.get("reward_ev_usd"), "snapshot reward_ev_usd", positive=True)
    observed_cost = _finite(snapshot.get("reward_conversion_cost_usd"), "snapshot reward_conversion_cost_usd")
    return observed_cost / observed_reward * reward_ev_usd


def calibrate(
    *, book: Sequence[Mapping[str, Any]], heartbeat: Mapping[str, Any], repo_root: Path,
    legacy_full_position_legs: bool = True,
) -> dict[str, Any]:
    """Return one reproducible reconciliation record for every paper position."""
    by_pool = {str(item.get("pool", "")).lower(): item for item in heartbeat.get("by_pool", [])}
    observed_at = _parse_timestamp(str(heartbeat["ts_utc"]))
    rows: list[dict[str, Any]] = []
    for allocation in book:
        pool = str(allocation["pool"]).lower()
        runner = by_pool.get(pool)
        if runner is None:
            raise ValueError(f"heartbeat has no row for book pool {pool}")
        snapshot, snapshot_source = _snapshot_record(repo_root, pool)
        capital = _finite(allocation["capital"], "capital", positive=True)
        fee_tier = _finite(allocation["fee_tier"], "fee_tier")
        started_at = _parse_timestamp(str(heartbeat.get("started_at") or "2026-06-24T11:54:26.450337+00:00"))
        # Legacy heartbeats lack started_at; book runner launch is the only
        # source of truth for this fixed run and is recorded in the report.
        holding_hours = (observed_at - started_at).total_seconds() / 3600.0
        if holding_hours <= 0:
            raise ValueError("paper holding duration must be positive")
        swaps = _position_leg_swap_components(
            capital_usd=capital, fee_tier=fee_tier,
            range_pct=float(allocation["range_pct"]), snapshot=snapshot,
            legacy_full_position_legs=legacy_full_position_legs,
        )
        fee_ev = _finite(runner.get("fees"), "paper fee", positive=False)
        reward_ev = _finite(runner.get("reward"), "paper reward", positive=False)
        # Paper runner emits IL as a signed alpha-vs-HODL diagnostic. NetCover
        # consumes a non-negative loss budget, so the comparison uses magnitude.
        il_ev = abs(float(runner.get("il", 0.0)))
        reward_conversion = _scaled_reward_conversion_cost(
            reward_ev_usd=reward_ev, snapshot=snapshot
        )
        exit_latency = capital * EXIT_LATENCY_LOSS_APR_PCT_MODEL / 100.0 * holding_hours / HOURS_PER_YEAR
        estimate = evaluate_netcover(
            fee_ev=fee_ev,
            reward_ev=reward_ev,
            reward_haircut=REWARD_HAIRCUTS["protocol"],
            expected_il=il_ev,
            lvr_coefficient=0.5,
            entry_cost=swaps["entry_cost_usd"],
            exit_cost=swaps["exit_cost_usd"],
            gas=HISTORICAL_BASE_GAS_USD,
            slippage=swaps["slippage_usd"],
            reward_conversion_cost=reward_conversion,
            exit_latency_loss=exit_latency,
        )
        paper = {
            "net_pnl_usd": float(runner.get("net_usd", 0.0)),
            "fee_ev_usd": fee_ev,
            "reward_ev_usd": reward_ev,
            "il_ev_usd": il_ev,
            "gas_usd": "UNMODELED",
            "entry_cost_usd": "UNMODELED",
            "exit_cost_usd": "UNMODELED",
            "slippage_usd": "UNMODELED",
            "reward_conversion_cost_usd": "UNMODELED",
            "exit_latency_loss_usd": "UNMODELED",
        }
        netcover = {
            "fee_ev_usd": fee_ev,
            "reward_ev_usd": reward_ev,
            "reward_haircut_deduction_usd": reward_ev - estimate.haircut_reward_ev,
            "il_ev_usd": il_ev,
            "lvr_ev_usd": estimate.expected_lvr_model,
            "gas_usd": estimate.gas,
            "entry_cost_usd": estimate.entry_cost,
            "exit_cost_usd": estimate.exit_cost,
            "slippage_usd": estimate.slippage,
            "reward_conversion_cost_usd": estimate.reward_conversion_cost,
            "exit_latency_loss_usd": estimate.exit_latency_loss_model,
        }
        deltas = []
        for component, value in netcover.items():
            paper_value = paper.get(component, 0.0 if component == "reward_haircut_deduction_usd" else "UNMODELED")
            if isinstance(paper_value, str):
                factor: float | str = "N/A (paper UNMODELED)"
                difference = float(value)
            elif paper_value == 0.0:
                factor = "N/A (paper zero)"
                difference = float(value)
            else:
                factor = float(value) / float(paper_value)
                difference = float(value) - float(paper_value)
            deltas.append({
                "component": component, "paper_runner": paper_value,
                "netcover": float(value), "difference_usd": difference,
                "netcover_over_paper_factor": factor,
            })
        deltas.sort(key=lambda item: abs(float(item["difference_usd"])), reverse=True)
        rows.append({
            "pool": pool, "symbol": allocation["symbol"], "project": allocation["project"],
            "capital_usd": capital, "holding_hours": holding_hours,
            "paper_runner": paper, "netcover": netcover,
            "netcover_ratio": estimate.netcover, "netcover_pass": estimate.shadow_candidate,
            "netcover_risk_usd": estimate.expected_risk_cost,
            "netcover_adjusted_income_usd": estimate.adjusted_income_ev,
            "snapshot_source": snapshot_source, "differences_descending": deltas,
            "legacy_full_position_legs": legacy_full_position_legs,
        })
    largest = max(
        (item for row in rows for item in row["differences_descending"]),
        key=lambda item: abs(float(item["difference_usd"])),
    )
    return {
        "method": "TP-J J1 realised-paper-income/full-cost-NetCover reconciliation",
        "runner_book_source": "reports/lp_portfolio_paper_runner/launch_20260624_115413_freerpc/book_init.json",
        "runner_heartbeat_source": "reports/lp_portfolio_paper_runner/launch_20260624_115413_freerpc/heartbeat.jsonl",
        "paper_observed_at": observed_at.isoformat(),
        "paper_started_at": started_at.isoformat(),
        "cost_leg_convention": "legacy_full_position_notional_per_leg" if legacy_full_position_legs else "corrected_position_leg_notional",
        "rows": rows,
        "largest_difference": largest,
    }


def _netcover_at_capital(
    *, allocation: Mapping[str, Any], runner: Mapping[str, Any], snapshot: Mapping[str, Any],
    holding_hours: float, capital_usd: float,
) -> float:
    """Scale observed per-dollar outcome terms, then price actual CLMM legs."""
    original_capital = _finite(allocation["capital"], "original capital", positive=True)
    target = _finite(capital_usd, "capital_usd", positive=True)
    scale = target / original_capital
    swaps = _position_leg_swap_components(
        capital_usd=target, fee_tier=_finite(allocation["fee_tier"], "fee_tier"),
        range_pct=float(allocation["range_pct"]), snapshot=snapshot,
        legacy_full_position_legs=False,
    )
    reward = _finite(runner.get("reward"), "paper reward") * scale
    estimate = evaluate_netcover(
        fee_ev=_finite(runner.get("fees"), "paper fee") * scale,
        reward_ev=reward,
        reward_haircut=REWARD_HAIRCUTS["protocol"],
        expected_il=abs(float(runner.get("il", 0.0))) * scale,
        lvr_coefficient=0.5,
        entry_cost=swaps["entry_cost_usd"], exit_cost=swaps["exit_cost_usd"],
        gas=HISTORICAL_BASE_GAS_USD, slippage=swaps["slippage_usd"],
        reward_conversion_cost=_scaled_reward_conversion_cost(
            reward_ev_usd=reward, snapshot=snapshot,
        ),
        exit_latency_loss=(
            target * EXIT_LATENCY_LOSS_APR_PCT_MODEL / 100.0
            * holding_hours / HOURS_PER_YEAR
        ),
    )
    return estimate.netcover


def backsolve_minimum_capital(
    *, book: Sequence[Mapping[str, Any]], heartbeat: Mapping[str, Any], repo_root: Path,
) -> dict[str, Any]:
    """Find the smallest capital at which each realised-input curve reaches 1.0.

    This is a scale diagnostic, not an allocator instruction: it holds each
    position's observed fee/reward/IL per dollar and its recorded horizon fixed.
    A curve with no finite solution has variable risk larger than its adjusted
    income, so no amount can amortise the one-off gas cost into viability.
    """
    observed_at = _parse_timestamp(str(heartbeat["ts_utc"]))
    started_at = _parse_timestamp(str(heartbeat.get("started_at") or "2026-06-24T11:54:26.450337+00:00"))
    holding_hours = (observed_at - started_at).total_seconds() / 3600.0
    by_pool = {str(item.get("pool", "")).lower(): item for item in heartbeat.get("by_pool", [])}
    rows = []
    for allocation in book:
        pool = str(allocation["pool"]).lower()
        runner = by_pool[pool]
        snapshot, source = _snapshot_record(repo_root, pool)
        original = _finite(allocation["capital"], "capital", positive=True)
        evaluate = lambda capital: _netcover_at_capital(
            allocation=allocation, runner=runner, snapshot=snapshot,
            holding_hours=holding_hours, capital_usd=capital,
        )
        low, high = 1e-9, original
        while evaluate(high) < 1.0 and high < 1e9:
            high *= 2.0
        minimum = None
        if evaluate(high) >= 1.0:
            for _ in range(100):
                midpoint = (low + high) / 2.0
                if evaluate(midpoint) >= 1.0:
                    high = midpoint
                else:
                    low = midpoint
            minimum = high
        rows.append({
            "symbol": allocation["symbol"], "pool": pool,
            "netcover_at_original_capital": evaluate(original),
            "netcover_at_50_usd": evaluate(50.0),
            "netcover_at_60_usd": evaluate(60.0),
            "original_capital_usd": original,
            "minimum_capital_usd_for_netcover_1": minimum,
            "no_finite_solution": minimum is None,
            "snapshot_source": source,
        })
    return {
        "method": "observed per-dollar paper outcome + corrected CLMM leg costs; fixed holding horizon",
        "holding_hours": holding_hours, "rows": rows,
    }


def render_backsolve_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# TP-J FIX-J4 — M1 尺度反解", "",
        "该反解固定每池的 J1 真实持有期与观测到的每美元 fee/reward/IL，使用 J3 的真实 CLMM 两腿成本；它不改任何阈值，也不是交易建议。", "",
        "|池|NetCover（50/60U）|原仓位($)|NetCover（原仓位）|达到 ≥1.0 的最小仓位($)|结论|", "|---|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        minimum = row["minimum_capital_usd_for_netcover_1"]
        lines.append(
            f"|{row['symbol']}|{row['netcover_at_50_usd']:.6f}/{row['netcover_at_60_usd']:.6f}|{row['original_capital_usd']:.2f}|{row['netcover_at_original_capital']:.6f}|"
            f"{'无有限解' if minimum is None else f'{minimum:.2f}'}|"
            f"{'变量风险超过调整后收入' if minimum is None else '可由规模摊薄固定成本'}|"
        )
    return "\n".join(lines) + "\n"


def _money(value: Any) -> str:
    return value if isinstance(value, str) else f"${float(value):,.4f}"


def _factor(value: Any) -> str:
    return value if isinstance(value, str) else f"{float(value):.4f}×"


def render_markdown(report: Mapping[str, Any]) -> str:
    rows = report["rows"]
    corrected = report["cost_leg_convention"] == "corrected_position_leg_notional"
    lines = [
        "# TP-J FIX-J3 — 更正 CLMM 换腿成本后的逐项对账" if corrected
        else "# TP-J FIX-J1 — paper runner 与 NetCover 逐项对账",
        "",
        "本报告只读 paper runner 输出和已存 scanner SQLite 快照；不调用 RPC、不触碰 runner 或保护进程。",
        "NetCover 收益/IL输入使用 runner 的真实累计观测；未被 runner 记账的成本明确标为 `UNMODELED`，绝不按 $0 处理。",
        "",
        "## 6 仓总览",
        "",
        "|池|资金|持有 h|paper 净 PnL|NetCover 收入|NetCover 风险|NetCover|≥1.0|快照来源|",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        source = row["snapshot_source"]
        lines.append(
            f"|{row['symbol']} ({row['project']})|${row['capital_usd']:.2f}|{row['holding_hours']:.2f}|"
            f"${row['paper_runner']['net_pnl_usd']:.4f}|${row['netcover_adjusted_income_usd']:.4f}|${row['netcover_risk_usd']:.4f}|"
            f"{row['netcover_ratio']:.6f}|{'是' if row['netcover_pass'] else '否'}|{source['path']} @ {source['as_of']}|"
        )
    lines.extend(["", "## 逐项口径（每池按绝对差异降序）", ""])
    for row in rows:
        lines.extend([
            f"### {row['symbol']} — {row['pool']}", "",
            "|项|paper runner|NetCover|差异（NetCover−paper）|倍数（NetCover/paper）|",
            "|---|---:|---:|---:|---:|",
        ])
        for item in row["differences_descending"]:
            lines.append(
                f"|{item['component']}|{_money(item['paper_runner'])}|{_money(item['netcover'])}|"
                f"${item['difference_usd']:,.4f}|{_factor(item['netcover_over_paper_factor'])}|"
            )
        lines.append("")
    biggest = report["largest_difference"]
    lines.extend([
        "## 裁定（J1 基线）", "",
        f"两个仪器分歧的最大来源是 `{biggest['component']}`，差异 ${biggest['difference_usd']:,.4f}；"
        f"NetCover/paper 为 {_factor(biggest['netcover_over_paper_factor'])}。",
        "这里的 `UNMODELED` 不是零成本：它表示 paper runner 输出没有该项可对账成本，"
        "故不能以 paper PnL 直接证明小仓真实可执行。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only TP-J paper/NetCover reconciliation")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--book", default="reports/lp_portfolio_paper_runner/launch_20260624_115413_freerpc/book_init.json")
    parser.add_argument("--heartbeat", default="reports/lp_portfolio_paper_runner/launch_20260624_115413_freerpc/heartbeat.jsonl")
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    parser.add_argument(
        "--corrected-position-legs", action="store_true",
        help="Use V3 range inventory leg value instead of the J1 full-leg baseline",
    )
    parser.add_argument("--backsolve-json-out")
    parser.add_argument("--backsolve-markdown-out")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    report = calibrate(
        book=json.loads((root / args.book).read_text()),
        heartbeat=_last_jsonl(root / args.heartbeat),
        repo_root=root,
        legacy_full_position_legs=not args.corrected_position_legs,
    )
    json_path, markdown_path = root / args.json_out, root / args.markdown_out
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(render_markdown(report))
    if bool(args.backsolve_json_out) != bool(args.backsolve_markdown_out):
        raise SystemExit("backsolve JSON and Markdown outputs must be supplied together")
    if args.backsolve_json_out:
        backsolve = backsolve_minimum_capital(
            book=json.loads((root / args.book).read_text()),
            heartbeat=_last_jsonl(root / args.heartbeat), repo_root=root,
        )
        backsolve_json = root / args.backsolve_json_out
        backsolve_markdown = root / args.backsolve_markdown_out
        backsolve_json.parent.mkdir(parents=True, exist_ok=True)
        backsolve_markdown.parent.mkdir(parents=True, exist_ok=True)
        backsolve_json.write_text(json.dumps(backsolve, indent=2, sort_keys=True) + "\n")
        backsolve_markdown.write_text(render_backsolve_markdown(backsolve))


if __name__ == "__main__":
    main()
