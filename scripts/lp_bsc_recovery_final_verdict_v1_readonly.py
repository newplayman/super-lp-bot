#!/usr/bin/env python3
"""Compose FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX for the recovery pipeline (read-only).

Aggregates outputs from earlier phases inside a single report dir:
  - current_run_finalizer.json
  - bsc_rpc_eth_getlogs_capability_matrix.json
  - bsc_fee_velocity_1pool_24h_smoke.json
  - bsc_fee_velocity_short_backfill_results.json
  - bsc_realdata_economics_with_recovered_fee.json
  - bsc_10_20u_probe_preflight_design.json

Outputs:
  $REPORT_DIR/FINAL_VERDICT.json
  $REPORT_DIR/ONEPAGE_CN.md
  $REPORT_DIR/ARTIFACT_INDEX.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


ALLOWED_NEXT = {
    "BSC_RPC_SETUP_REQUIRED",
    "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_SHORT_BACKFILL_REPEAT",
    "LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1",
    "LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1",
    "STOP_LP_RESEARCH_NOW",
}


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return {}


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Compose FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX.")
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)

    rd: Path = args.report_dir
    rd.mkdir(parents=True, exist_ok=True)

    fin = _load(rd / "current_run_finalizer.json")
    matrix = _load(rd / "bsc_rpc_eth_getlogs_capability_matrix.json")
    smoke = _load(rd / "bsc_fee_velocity_1pool_24h_smoke.json")
    backfill = _load(rd / "bsc_fee_velocity_short_backfill_results.json")
    econ = _load(rd / "bsc_realdata_economics_with_recovered_fee.json")
    preflight = _load(rd / "bsc_10_20u_probe_preflight_design.json")

    # ----- compose verdict ---------------------------------------------
    usable_bsc_rpc_count = matrix.get("usable_count", 0) if matrix else 0
    smoke_ran = bool(smoke)
    smoke_pass = bool(smoke.get("smoke_pass")) if smoke else False
    backfill_ran = bool(backfill)
    fee_ready_pool_count = backfill.get("fee_ready_pool_count", 0) if backfill else 0
    decoded_swap_log_count = backfill.get("decoded_swap_log_count", 0) if backfill else 0
    econ_ran = bool(econ)
    pos_realistic = econ.get("positive_proxy_count_realistic", 0) if econ else 0
    near_be = econ.get("near_break_even_count", 0) if econ else 0

    preflight_ready = bool(preflight and preflight.get("preflight_kind") == "candidate_present_design_only")

    # Choose status + next stage
    if not usable_bsc_rpc_count:
        status = "FAIL"
        next_stage = "BSC_RPC_SETUP_REQUIRED"
    elif not backfill_ran:
        status = "WARN"
        next_stage = "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_SHORT_BACKFILL_REPEAT"
    elif fee_ready_pool_count == 0:
        status = "WARN"
        next_stage = "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_SHORT_BACKFILL_REPEAT"
    elif not econ_ran:
        status = "WARN"
        next_stage = "LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1"
    elif preflight_ready:
        status = "PASS"
        next_stage = "LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1"
    elif pos_realistic > 0 or near_be > 0:
        status = "WARN"
        next_stage = "LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1"
    else:
        status = "WARN"
        next_stage = "LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1"

    if next_stage not in ALLOWED_NEXT:
        print(f"ERROR: chosen next_stage {next_stage!r} not in ALLOWED_NEXT", file=sys.stderr)
        return 2

    verdict = {
        "status": status,
        "stage": "LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1",
        "run_id": args.run_id,
        "old_run_finalized": bool(fin),
        "old_runner_stopped_by_this_task": bool(fin.get("runner_stopped_by_this_task")) if fin else False,
        "rpc_capability_matrix_ran": bool(matrix),
        "usable_bsc_rpc_count": usable_bsc_rpc_count,
        "smoke_1pool_24h_ran": smoke_ran,
        "smoke_1pool_24h_pass": smoke_pass,
        "short_backfill_ran": backfill_ran,
        "fee_ready_pool_count": fee_ready_pool_count,
        "decoded_swap_log_count": decoded_swap_log_count,
        "economics_preview_ran": econ_ran,
        "positive_proxy_count_realistic": pos_realistic,
        "near_break_even_count": near_be,
        "best_pool": econ.get("best_pool", "") if econ else "",
        "best_pair": econ.get("best_pair", "") if econ else "",
        "best_fee_tier": econ.get("best_fee_tier", "") if econ else "",
        "best_notional": econ.get("best_notional") if econ else None,
        "best_hold_window": econ.get("best_hold_window", "") if econ else "",
        "best_net_ev_proxy_usd": econ.get("best_net_ev_proxy_usd") if econ else None,
        "probe_preflight_design_ready": preflight_ready,
        "can_run_probe_now": False,
        "manual_approval_required_for_probe": True,
        "edge_proven": "no",
        "actual_fee_ready": False,
        "token_id_available": False,
        "wallet_or_tx_touched": False,
        "tiny_canary_allowed": "no",
        "recommended_next_stage": next_stage,
    }
    (rd / "FINAL_VERDICT.json").write_text(json.dumps(verdict, indent=2) + "\n")

    # ----- ONEPAGE_CN.md -----------------------------------------------
    md = [
        "# 单页总览（recovery pipeline）",
        "",
        "```text",
        f"stage                              = {verdict['stage']}",
        f"run_id                             = {verdict['run_id']}",
        f"status                             = {verdict['status']}",
        "",
        f"old_run_finalized                  = {verdict['old_run_finalized']}",
        f"old_runner_stopped_by_this_task    = {verdict['old_runner_stopped_by_this_task']}",
        "",
        f"rpc_capability_matrix_ran          = {verdict['rpc_capability_matrix_ran']}",
        f"usable_bsc_rpc_count               = {verdict['usable_bsc_rpc_count']}",
        "",
        f"smoke_1pool_24h_ran                = {verdict['smoke_1pool_24h_ran']}",
        f"smoke_1pool_24h_pass               = {verdict['smoke_1pool_24h_pass']}",
        "",
        f"short_backfill_ran                 = {verdict['short_backfill_ran']}",
        f"fee_ready_pool_count               = {verdict['fee_ready_pool_count']}",
        f"decoded_swap_log_count             = {verdict['decoded_swap_log_count']}",
        "",
        f"economics_preview_ran              = {verdict['economics_preview_ran']}",
        f"positive_proxy_count_realistic     = {verdict['positive_proxy_count_realistic']}",
        f"near_break_even_count              = {verdict['near_break_even_count']}",
        f"best_pool                          = {verdict['best_pool'] or '-'}",
        f"best_pair                          = {verdict['best_pair'] or '-'}",
        f"best_fee_tier                      = {verdict['best_fee_tier'] or '-'}",
        f"best_notional                      = {verdict['best_notional'] or '-'}",
        f"best_hold_window                   = {verdict['best_hold_window'] or '-'}",
        f"best_net_ev_proxy_usd              = {verdict['best_net_ev_proxy_usd'] or '-'}",
        "",
        f"probe_preflight_design_ready       = {verdict['probe_preflight_design_ready']}",
        f"can_run_probe_now                  = {verdict['can_run_probe_now']}",
        f"manual_approval_required_for_probe = {verdict['manual_approval_required_for_probe']}",
        f"edge_proven                        = {verdict['edge_proven']}",
        f"actual_fee_ready                   = {verdict['actual_fee_ready']}",
        f"token_id_available                 = {verdict['token_id_available']}",
        f"wallet_or_tx_touched               = {verdict['wallet_or_tx_touched']}",
        f"tiny_canary_allowed                = {verdict['tiny_canary_allowed']}",
        "",
        f"recommended_next_stage             = {verdict['recommended_next_stage']}",
        "```",
        "",
        "## 严格禁区（本轮已遵守）",
        "",
        "```text",
        "不发交易            no tx",
        "不启动 live         no live",
        "不启动 paper        no paper",
        "不运行 canary       no canary",
        "不执行 probe        no probe",
        "不读私钥/wallet     no wallet",
        "不创建 signer       no signer",
        "不调用 swap/mint/burn/collect/approve/increaseLiquidity/decreaseLiquidity",
        "不写 production positions",
        "不覆盖 shadow 表",
        "不重启 lpbot-shadow / lpbot-live",
        "tiny_canary_allowed = no",
        "can_run_probe_now   = false",
        "edge_proven         = no",
        "```",
    ]
    (rd / "ONEPAGE_CN.md").write_text("\n".join(md) + "\n")

    # ----- ARTIFACT_INDEX.md -------------------------------------------
    idx = [
        f"# Artifact Index — `{args.run_id}`",
        "",
        f"Stage: `{verdict['stage']}`",
        f"Status: **`{verdict['status']}`**",
        f"Recommended next stage: `{verdict['recommended_next_stage']}`",
        "",
        "## 报告文件",
        "",
        "| 文件 | 用途 |",
        "|---|---|",
        "| `FINAL_VERDICT.json` | 顶层汇总 verdict |",
        "| `ONEPAGE_CN.md` | 单页总览 |",
        "| `CURRENT_RUN_FINALIZER_CN.md` / `current_run_finalizer.json` | Phase 1 上一轮 overnight 收尾 |",
        "| `STOPPED_STALE_READONLY_RUN_CN.md` | Phase 1 安全停止旧 run 的取证记录 |",
        "| `BSC_RPC_ETH_GETLOGS_CAPABILITY_MATRIX_CN.md` / `*.csv` / `*.json` | Phase 2 BSC RPC eth_getLogs 能力矩阵 |",
        "| `BSC_FEE_VELOCITY_1POOL_24H_SMOKE_CN.md` / `*.csv` / `*.json` | Phase 3 1池 24h smoke |",
        "| `BSC_FEE_VELOCITY_SHORT_BACKFILL_RESULTS_CN.md` / `*.csv` / `*.json` | Phase 4 8池 × 24h/72h/7d 回填 |",
        "| `bsc_swap_logs_decoded_short.csv` | Phase 4 解码 swap 样本 |",
        "| `BSC_REALDATA_ECONOMICS_WITH_RECOVERED_FEE_CN.md` / `*.csv` / `*.json` | Phase 5 economics preview |",
        "| `BSC_10_20U_PROBE_PREFLIGHT_DESIGN_CN.md` / `*.json` | Phase 6 10/20U probe preflight 设计（仅设计，不执行） |",
        "",
        "## 工具脚本（仓库 `scripts/`）",
        "",
        "- `scripts/lp_bsc_rpc_eth_getlogs_capability_matrix_v1_readonly.py`",
        "- `scripts/lp_bsc_fee_velocity_smoke_v1_readonly.py`",
        "- `scripts/lp_bsc_fee_velocity_short_backfill_v2_readonly.py`",
        "- `scripts/lp_bsc_realdata_economics_with_recovered_fee_v1_readonly.py`",
        "- `scripts/lp_bsc_10_20u_probe_preflight_design_v1_readonly.py`",
        "- `scripts/lp_bsc_recovery_final_verdict_v1_readonly.py`（本脚本）",
        "",
        "## 测试（仓库 `tests/`）",
        "",
        "- `tests/test_lp_bsc_fee_velocity_recovery_probe_preflight_v1_readonly.py`",
    ]
    (rd / "ARTIFACT_INDEX.md").write_text("\n".join(idx) + "\n")

    print(json.dumps({
        "status": verdict["status"],
        "recommended_next_stage": verdict["recommended_next_stage"],
        "probe_preflight_design_ready": verdict["probe_preflight_design_ready"],
        "fee_ready_pool_count": verdict["fee_ready_pool_count"],
        "positive_proxy_count_realistic": verdict["positive_proxy_count_realistic"],
        "near_break_even_count": verdict["near_break_even_count"],
        "best_pool": verdict["best_pool"],
        "best_net_ev_proxy_usd": verdict["best_net_ev_proxy_usd"],
    }, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
