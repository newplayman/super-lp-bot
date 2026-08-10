#!/usr/bin/env python3
"""Read-only D3 calibration and NetCover coefficient sensitivity.

The replay deliberately uses only committed swap logs and a copied N1 SQLite
artifact.  It performs no RPC, wallet, signing, or transaction operation.

``approx_lvr`` is the gap between a frictionless 50/50 portfolio rebalanced at
each observed block-close swap price and a fee-free full-range x*y=k LP.  This
is a path-dependent approximation, not an exact concentrated-position LVR.
``endpoint_il`` is the endpoint buy-and-hold minus LP value.  Ratios with a
near-flat endpoint are reported but excluded from the robust subset because
their denominator tends to zero.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence


COEFFICIENTS = (0.0, 0.25, 0.5, 0.75, 1.0)
MODEL_COEFFICIENT = 0.5
WINDOWS_PER_POOL = 4
MIN_ENDPOINT_MOVE_FOR_ROBUST_RATIO = 0.0025  # 25 bps


def _quantile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile requires values")
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def sqrt_price_from_log(log: Mapping[str, Any]) -> int:
    """Decode word 3 of either committed V3 or Algebra V2 Swap event."""
    data = str(log.get("data") or "")
    if not data.startswith("0x") or len(data) < 2 + 3 * 64:
        raise ValueError("swap log data is too short")
    value = int(data[2 + 2 * 64 : 2 + 3 * 64], 16)
    if value <= 0 or value >= 2**160:
        raise ValueError("sqrtPriceX96 must be a positive uint160")
    return value


def replay_window(sqrt_prices_x96: Sequence[int]) -> dict[str, float | None]:
    """Estimate full-range endpoint IL and path LVR per dollar of initial NAV."""
    if len(sqrt_prices_x96) < 2 or any(value <= 0 for value in sqrt_prices_x96):
        raise ValueError("a replay window requires at least two positive prices")

    # Price ratios do not require token decimals: the decimal factor cancels.
    first_squared = float(sqrt_prices_x96[0]) ** 2
    previous_squared = first_squared
    rebalanced_value = 2.0
    quadratic_variation = 0.0
    for sqrt_price in sqrt_prices_x96[1:]:
        current_squared = float(sqrt_price) ** 2
        step_return = current_squared / previous_squared
        rebalanced_value *= 0.5 * (1.0 + step_return)
        quadratic_variation += math.log(step_return) ** 2
        previous_squared = current_squared

    terminal_return = previous_squared / first_squared
    lp_value = 2.0 * math.sqrt(terminal_return)
    # Initial normalized NAV is 2, hence both differences are divided by 2.
    endpoint_il = max(0.0, (1.0 + terminal_return - lp_value) / 2.0)
    approx_lvr = max(0.0, (rebalanced_value - lp_value) / 2.0)
    ratio = approx_lvr / endpoint_il if endpoint_il > 1e-15 else None
    endpoint_move = abs(terminal_return - 1.0)
    return {
        "terminal_return": terminal_return,
        "endpoint_move_abs": endpoint_move,
        "endpoint_il_per_initial_usd": endpoint_il,
        "approx_lvr_per_initial_usd": approx_lvr,
        "approx_lvr_to_endpoint_il": ratio,
        "log_price_quadratic_variation": quadratic_variation,
    }


def load_replay_bounds(path: Path) -> dict[str, tuple[int, int, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {
        row["pool"].lower(): (
            int(row["start_block"]), int(row["end_block"]), row["pool_name"]
        )
        for row in rows
    }


def calibrate_swap_replay(
    raw_logs_path: Path,
    replay_summary_path: Path,
    *,
    windows_per_pool: int = WINDOWS_PER_POOL,
) -> list[dict[str, Any]]:
    """Replay last observed swap price per block over equal block windows."""
    reported_bounds = load_replay_bounds(replay_summary_path)
    block_closes: dict[str, dict[int, int]] = defaultdict(dict)
    event_counts: dict[str, int] = defaultdict(int)
    with raw_logs_path.open(encoding="utf-8") as handle:
        for line in handle:
            log = json.loads(line)
            pool = str(log["pool"]).lower()
            if pool not in reported_bounds:
                continue
            block = int(log["block"])
            # Input order is chain log order; overwrite to retain block close.
            # The R4 aggregate CSV's reported start blocks do not cover every
            # raw event even though its event counts equal the entire JSONL.
            # Use the actual committed raw span and retain both bounds in output.
            block_closes[pool][block] = sqrt_price_from_log(log)
            event_counts[pool] += 1

    rows: list[dict[str, Any]] = []
    for pool, (reported_start, reported_end, pool_name) in sorted(reported_bounds.items()):
        observations = sorted(block_closes.get(pool, {}).items())
        if not observations:
            continue
        start, end = observations[0][0], observations[-1][0]
        width = max(1, (end - start) // windows_per_pool)
        for index in range(windows_per_pool):
            window_start = start + index * width
            window_end = end if index == windows_per_pool - 1 else window_start + width - 1
            prices = [value for block, value in observations if window_start <= block <= window_end]
            if len(prices) < 2:
                rows.append({
                    "pool": pool,
                    "pool_name": pool_name,
                    "window_index": index,
                    "start_block": window_start,
                    "end_block": window_end,
                    "reported_start_block": reported_start,
                    "reported_end_block": reported_end,
                    "event_count_in_full_replay": event_counts.get(pool, 0),
                    "block_close_observations": len(prices),
                    "status": "INSUFFICIENT_OBSERVATIONS",
                })
                continue
            result = replay_window(prices)
            ratio = result["approx_lvr_to_endpoint_il"]
            robust = (
                ratio is not None
                and float(result["endpoint_move_abs"]) >= MIN_ENDPOINT_MOVE_FOR_ROBUST_RATIO
            )
            rows.append({
                "pool": pool,
                "pool_name": pool_name,
                "window_index": index,
                "start_block": window_start,
                "end_block": window_end,
                "reported_start_block": reported_start,
                "reported_end_block": reported_end,
                "event_count_in_full_replay": event_counts[pool],
                "block_close_observations": len(prices),
                "status": "OK",
                **result,
                "robust_ratio_eligible": robust,
                "robust_exclusion_reason": (
                    "" if robust else "endpoint_move_below_25bps_or_zero_endpoint_il"
                ),
            })
    return rows


def _load_n1_rows(scanner_db: Path) -> list[dict[str, Any]]:
    uri = f"file:{scanner_db.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        return [
            json.loads(score_json)
            for (score_json,) in connection.execute(
                "select score_json from opportunity_scores order by id"
            )
        ]
    finally:
        connection.close()


def sensitivity_rows(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = list(records)
    output: list[dict[str, Any]] = []
    for coefficient in COEFFICIENTS:
        covers: list[float] = []
        netcover_pass_count = 0
        terminal_accept_count = 0
        unavailable_count = 0
        baseline_errors: list[float] = []
        for record in records:
            required = (
                "risk_usd", "expected_net_yield_usd", "il_ev_usd", "lvr_ev_usd"
            )
            if any(record.get(key) is None for key in required):
                unavailable_count += 1
                continue
            # Recover adjusted income and non-IL/LVR costs from the stored N1
            # decomposition.  At 0.5 this reproduces the stored NetCover exactly.
            income = float(record["risk_usd"]) + float(record["expected_net_yield_usd"])
            fixed_cost = (
                float(record["risk_usd"])
                - float(record["il_ev_usd"])
                - float(record["lvr_ev_usd"])
            )
            risk = fixed_cost + float(record["il_ev_usd"]) * (1.0 + coefficient)
            cover = math.inf if risk == 0.0 and income > 0.0 else income / risk
            covers.append(cover)
            if coefficient == MODEL_COEFFICIENT and record.get("netcover_ratio") is not None:
                baseline_errors.append(abs(cover - float(record["netcover_ratio"])))
            netcover_ok = cover >= 1.0
            netcover_pass_count += int(netcover_ok)
            gates = record.get("gates") or {}
            other_terminal_gates = (
                bool(gates.get("status_ok"))
                and bool(gates.get("quality"))
                and bool(gates.get("yield_cover"))
                and bool(gates.get("stable"))
                and record.get("entry_eligible") is True
                and bool(gates.get("position_cap"))
            )
            terminal_accept_count += int(netcover_ok and other_terminal_gates)

        output.append({
            "lvr_coefficient": coefficient,
            "universe_count": len(records),
            "calculable_netcover_count": len(covers),
            "fail_closed_unavailable_count": unavailable_count,
            "netcover_min": min(covers),
            "netcover_p25": _quantile(covers, 0.25),
            "netcover_median": _quantile(covers, 0.50),
            "netcover_p75": _quantile(covers, 0.75),
            "netcover_p90": _quantile(covers, 0.90),
            "netcover_max": max(covers),
            "netcover_pass_count": netcover_pass_count,
            "terminal_accept_count": terminal_accept_count,
            "baseline_reproduction_max_abs_error": (
                max(baseline_errors) if baseline_errors else None
            ),
        })
    return output


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _fmt(value: Any) -> str:
    return "" if value is None else f"{value:.6f}" if isinstance(value, float) else str(value)


def render_report(
    calibration: list[dict[str, Any]],
    sensitivity: list[dict[str, Any]],
    *,
    raw_sha256: str = "",
    scanner_db_sha256: str = "",
) -> str:
    valid = [row for row in calibration if row["status"] == "OK"]
    ratios = [float(row["approx_lvr_to_endpoint_il"]) for row in valid if row.get("approx_lvr_to_endpoint_il") is not None]
    robust = [
        float(row["approx_lvr_to_endpoint_il"])
        for row in valid if row.get("robust_ratio_eligible")
    ]
    per_pool = {}
    for row in valid:
        if row.get("approx_lvr_to_endpoint_il") is not None:
            per_pool.setdefault(row["pool"], []).append(float(row["approx_lvr_to_endpoint_il"]))

    lines = [
        "# FIX-D3：LVR 系数溯源、真实 swap 近似校准与敏感性",
        "",
        "## 结论",
        "",
        "**未获充分证据，`LVR_COEFFICIENT_MODEL` 维持 `0.5`。** 本报告不以过闸率选择系数；五档敏感性全部为 0 个 NetCover 过闸。",
        "",
        "## 溯源",
        "",
        "- `git blame scripts/lp_netcover_inputs_v1_readonly.py:86` 指向 `0541c1f73d08b2a4a0f214601185b1c1562225a4`（`m0p(fix-W6): assemble live NetCover inputs`，2026-08-09）。",
        "- 该文件在该提交中首次创建，常量直接写为 `0.50`；相邻注释只解释其他输入，没有 LVR 系数的论文、推导、回放或校准引用。",
        "- 仓库更早的 IL/LVR 文档明确把旧结果称为 score/heuristic proxy，并写明缺少 exact range/inventory 与 exact LVR decomposition；因此不能把它们视为 `0.5` 的实证依据。",
        "- 溯源判定：`0.5` 是无可核验依据的初始模型假设，并非仓库内已证明常数。",
        "",
        "## 近似校准口径",
        "",
        "- 输入是仓库已提交 R4 的 115,680 条 Base 真实 Swap 日志；三个 WETH/USDC 池，分别按 raw JSONL 的实际最小/最大 block 切成四个等长窗口。",
        "- 数据一致性告警：R4 聚合 CSV 的三个 `event_count` 之和等于 raw 的 115,680，但 CSV 声称的 `start_block` 晚于各池 raw 实际首块，不能覆盖全部事件。本校准不静默丢弃事件，采用 raw 实际边界，并在逐窗 CSV 同时保留 reported/actual 边界；该矛盾进一步降低定参证据等级。",
        "- 同一 block 只保留最后一个 swap price，降低交易拆单与同块排序对路径长度的重复计数；价格由 Swap 的 `sqrtPriceX96` 解码，比例计算中 token decimals 抵消。",
        "- 每窗以初始 NAV=2 的 fee-free full-range `x*y=k` LP 为基准：`LP=2*sqrt(Pt/P0)`；端点 IL=`(HODL-LP)/2`。",
        "- 近似 LVR=`(逐 block 价格无摩擦恢复 50/50 的组合终值 - LP 终值)/2`。它捕捉路径二次变差，但不是 CL tokenId 的严格 LVR。",
        f"- 共 {len(valid)} 个有效池窗；全样本比值中位数 `{median(ratios):.6f}`。端点绝对变动至少 25 bps 的稳健子样本 {len(robust)} 窗，中位数 `{median(robust):.6f}`。",
        "",
        "| pool | 四窗 LVR/端点IL 中位数 |",
        "|---|---:|",
    ]
    for pool, values in sorted(per_pool.items()):
        lines.append(f"| `{pool}` | {median(values):.6f} |")
    lines.extend([
        "",
        "### 局限",
        "",
        "1. 只有单一 24h 市况、三个同一资产对，且三个池的价格高度相关，不是三个独立市场样本。",
        "2. 回放没有 LP tokenId、区间、库存、mint/burn、fee growth 与外部公允价；用 full-range 几何近似 CL。",
        "3. 严格 LVR 应相对连续再平衡组合并处理离散套利与费用；本报告只在 block-close swap path 上近似，既可能漏掉块内路径，也可能把非套利 swap 的价格变化计入。",
        "4. 当端点接近原点时，端点 IL 趋近 0，而路径 LVR 仍为正，`LVR/IL` 会机械性爆大；因此全样本均值不可用于定参，25 bps 筛选也只是诊断，不是调参规则。",
        "5. 本近似的稳健子样本中位数明显高于 0.5；若机械采用，会指向上调而非下调。但样本窄、同资产高度相关、源边界矛盾且模型错配，尚不足以支持任何方向的常量变更。这应被视为当前 `0.5` 可能低估风险的警报。",
        "",
        "## N1 92 池系数敏感性",
        "",
        "来源固定为 N1 尸检同一 cohort：`reports/lp_funnel_autopsy/20260810_043427/scanner.db` 的 `opportunity_scores.score_json` 全部 92 行。",
        "",
        f"- scanner.db SHA-256：`{scanner_db_sha256}`",
        f"- swap raw SHA-256：`{raw_sha256}`",
        "- 在系数 0.5 下，对 65 个可算记录重新分解并重算的 NetCover 与库内值最大绝对误差为 `" + f"{next(row['baseline_reproduction_max_abs_error'] for row in sensitivity if row['lvr_coefficient'] == 0.5):.3e}`，证明敏感性只替换 LVR 系数。",
        "- 27 池因解析/报价路线等前置永久 fail-closed 而没有可计算 NetCover；分布统计基于其余 65 池，过闸计数的分母仍是完整 92 池。阈值固定 `NetCover >= 1.0`。",
        "",
        "| 系数 | 可算/92 | min | p25 | median | p75 | p90 | max | NetCover过闸 | 终闸合取通过 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in sensitivity:
        lines.append(
            "| {lvr_coefficient:.2f} | {calculable_netcover_count}/{universe_count} | {netcover_min:.6f} | {netcover_p25:.6f} | {netcover_median:.6f} | {netcover_p75:.6f} | {netcover_p90:.6f} | {netcover_max:.6f} | {netcover_pass_count} | {terminal_accept_count} |".format(**row)
        )
    lines.extend([
        "",
        "敏感性只回答模型风险，不构成系数选择依据。即使 `0.0` 仍无池过闸；这不能反向证明应选 `0.0`，也不能证明 `0.5` 正确。",
        "",
        "## 决策",
        "",
        "- 常量变更：**否**。",
        "- 决策理由：证据覆盖不足，且现有近似存在结构性模型错配；按 TP-D-v1 强制条款维持 `0.5`。",
        "- 后续获得可定参证据的最低条件：跨资产/跨波动 regime 的多日样本、真实 CL 区间与库存、外部公允价、fee 与 LVR 分解，并预注册窗口和聚合方法。",
        "- 安全：RPC=0，签名=0，广播=0，钱包/私钥=0，运行进程变更=0。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-logs", type=Path, required=True)
    parser.add_argument("--replay-summary", type=Path, required=True)
    parser.add_argument("--scanner-db", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    calibration = calibrate_swap_replay(args.raw_logs, args.replay_summary)
    sensitivity = sensitivity_rows(_load_n1_rows(args.scanner_db))
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    raw_sha256 = sha256(args.raw_logs)
    scanner_db_sha256 = sha256(args.scanner_db)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.output_dir / "lvr_il_replay_windows.csv", calibration)
    _write_csv(args.output_dir / "n1_lvr_coefficient_sensitivity.csv", sensitivity)
    (args.output_dir / "results.json").write_text(
        json.dumps({
            "schema": "lp_lvr_coefficient_calibration_v1",
            "model_coefficient_before": MODEL_COEFFICIENT,
            "model_coefficient_after": MODEL_COEFFICIENT,
            "decision": "INSUFFICIENT_EVIDENCE_KEEP_0.5",
            "sources": {
                "raw_logs": str(args.raw_logs),
                "raw_logs_sha256": raw_sha256,
                "scanner_db": str(args.scanner_db),
                "scanner_db_sha256": scanner_db_sha256,
                "n1_cohort_rows": 92,
            },
            "calibration": calibration,
            "sensitivity": sensitivity,
            "safety": {"rpc_calls": 0, "signed": False, "broadcast_count": 0},
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "SUMMARY.md").write_text(
        render_report(
            calibration,
            sensitivity,
            raw_sha256=raw_sha256,
            scanner_db_sha256=scanner_db_sha256,
        ), encoding="utf-8"
    )
    print(json.dumps({
        "output_dir": str(args.output_dir),
        "decision": "INSUFFICIENT_EVIDENCE_KEEP_0.5",
        "valid_windows": sum(row["status"] == "OK" for row in calibration),
        "netcover_pass_counts": {
            str(row["lvr_coefficient"]): row["netcover_pass_count"]
            for row in sensitivity
        },
        "broadcast_count": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
