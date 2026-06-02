#!/usr/bin/env python3
"""Generate 10/20U probe preflight design (read-only).

Consumes Phase 5 (bsc_realdata_economics_with_recovered_fee.json) and emits a
strict preflight design document. This script does NOT execute a probe,
does NOT load a wallet, does NOT create a signer, does NOT submit any
transaction. The output is for manual review and approval.

Gates required for can_run_probe_now = false (current pipeline never flips this):
  1. precise quote ready          (input: lp_bsc_pancakeswap_v3_precise_quote)
  2. tick-liquidity ready         (input: lp_v3_tick_liquidity)
  3. real cost ready              (input: lp_real_cost_model)
  4. fee velocity ready           (Phase 4 fee_ready_pool_count > 0)
  5. realistic-scenario candidate (Phase 5 positive_proxy_count_realistic > 0 OR near_break_even_count > 0)
  6. manual approval required
  7. dry-run transaction builder only after approval
  8. no auto-submit

Outputs:
  $REPORT_DIR/bsc_10_20u_probe_preflight_design.json
  $REPORT_DIR/BSC_10_20U_PROBE_PREFLIGHT_DESIGN_CN.md
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional


ALLOWED_NEXT = {
    "LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1",
    "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_FIX_REPEAT",
    "LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1",
    "STOP_LP_RESEARCH_NOW",
}


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="10/20U probe preflight DESIGN (no execution).")
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--econ-json", type=Path,
                        help="Defaults to <report-dir>/bsc_realdata_economics_with_recovered_fee.json")
    args = parser.parse_args(argv)

    econ_json = args.econ_json or (args.report_dir / "bsc_realdata_economics_with_recovered_fee.json")
    if not econ_json.is_file():
        # No economics preview yet — emit a "no candidate / waiting" preflight stub.
        design = {
            "stage": "LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1",
            "phase": "6_probe_preflight_design",
            "run_id": args.run_id,
            "preflight_kind": "no_candidate_blocked_on_economics_preview",
            "can_run_probe_now": False,
            "manual_approval_required_for_probe": True,
            "edge_proven": "no",
            "tiny_canary_allowed": "no",
            "wallet_or_tx_touched": False,
            "actual_fee_ready": False,
            "token_id_available": False,
            "blockers": ["bsc_realdata_economics_with_recovered_fee.json missing"],
            "recommended_next_stage": "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_FIX_REPEAT",
        }
    else:
        econ = json.loads(econ_json.read_text())

        has_realistic = (econ.get("positive_proxy_count_realistic", 0) or 0) > 0
        has_near_be = (econ.get("near_break_even_count", 0) or 0) > 0
        best_net_ev = econ.get("best_net_ev_proxy_usd")
        try:
            best_net_ev_dec = Decimal(str(best_net_ev)) if best_net_ev not in (None, "") else None
        except Exception:  # noqa: BLE001
            best_net_ev_dec = None
        soft_candidate = (best_net_ev_dec is not None and best_net_ev_dec > Decimal("-0.02"))

        if not (has_realistic or has_near_be or soft_candidate):
            design = {
                "stage": "LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1",
                "phase": "6_probe_preflight_design",
                "run_id": args.run_id,
                "preflight_kind": "no_probe_candidate",
                "can_run_probe_now": False,
                "manual_approval_required_for_probe": True,
                "edge_proven": "no",
                "tiny_canary_allowed": "no",
                "wallet_or_tx_touched": False,
                "actual_fee_ready": False,
                "token_id_available": False,
                "best_net_ev_proxy_usd": best_net_ev,
                "best_pool": econ.get("best_pool"),
                "best_pair": econ.get("best_pair"),
                "blockers": [
                    "positive_proxy_count_realistic == 0",
                    "near_break_even_count == 0",
                    "best_net_ev_proxy_usd not better than -$0.02",
                ],
                "recommended_next_stage": "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_FIX_REPEAT",
            }
        else:
            design = {
                "stage": "LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1",
                "phase": "6_probe_preflight_design",
                "run_id": args.run_id,
                "preflight_kind": "candidate_present_design_only",
                "preflight_target": {
                    "pool": econ.get("best_pool"),
                    "pair": econ.get("best_pair"),
                    "fee_tier_raw": econ.get("best_fee_tier"),
                    "hold_window": econ.get("best_hold_window"),
                    "notional_usd_min": 10,
                    "notional_usd_max": 20,
                    "single_pool_only": True,
                    "low_risk_path_only": True,
                },
                "gates_required_before_probe": {
                    "precise_quote_ready": True,
                    "tick_liquidity_ready": True,
                    "real_cost_ready": True,
                    "fee_velocity_ready": True,
                    "realistic_or_near_be_positive_candidate_present": True,
                    "manual_approval_required": True,
                    "dry_run_tx_builder_only_after_approval": True,
                    "no_auto_submit": True,
                },
                "must_record": [
                    "tokenId",
                    "mint_tx_hash",
                    "feeGrowthInside (entry & exit)",
                    "tokensOwed (entry & exit)",
                    "exit_quote",
                    "actual_PnL_in_USD",
                    "actual_fee_accrual_in_USD",
                ],
                "execution_constraints": {
                    "max_funds_usd": 20,
                    "wallet_load_allowed_in_this_phase": False,
                    "signer_create_allowed_in_this_phase": False,
                    "eth_sendTransaction_allowed_in_this_phase": False,
                    "eth_sendRawTransaction_allowed_in_this_phase": False,
                    "increaseLiquidity_allowed_in_this_phase": False,
                    "decreaseLiquidity_allowed_in_this_phase": False,
                    "collect_allowed_in_this_phase": False,
                    "approve_allowed_in_this_phase": False,
                },
                "best_net_ev_proxy_usd": best_net_ev,
                "best_net_ev_proxy_pct": econ.get("best_net_ev_proxy_pct"),
                "fee_velocity_window_used": None,
                "can_run_probe_now": False,
                "manual_approval_required_for_probe": True,
                "edge_proven": "no",
                "tiny_canary_allowed": "no",
                "wallet_or_tx_touched": False,
                "actual_fee_ready": False,
                "token_id_available": False,
                "recommended_next_stage": "LP_BSC_10_20U_PROBE_PREFLIGHT_REVIEW_V1",
            }

    if design.get("recommended_next_stage") not in ALLOWED_NEXT:
        print(f"ERROR: recommended_next_stage {design['recommended_next_stage']!r} not allowed", file=sys.stderr)
        return 2

    (args.report_dir / "bsc_10_20u_probe_preflight_design.json").write_text(json.dumps(design, indent=2) + "\n")

    md = [
        "# BSC 10/20U probe preflight DESIGN（仅设计，不执行）",
        "",
        f"- stage: `LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1`",
        f"- run_id: `{args.run_id}`",
        f"- preflight_kind: `{design['preflight_kind']}`",
        f"- can_run_probe_now: **`False`**",
        f"- manual_approval_required_for_probe: **`True`**",
        "",
    ]
    if design["preflight_kind"] == "candidate_present_design_only":
        t = design["preflight_target"]
        md += [
            "## 候选目标（仅设计）",
            "",
            f"- pool: `{t['pool']}`",
            f"- pair: `{t['pair']}`",
            f"- fee_tier_raw: `{t['fee_tier_raw']}`",
            f"- hold_window: `{t['hold_window']}`",
            f"- notional_usd: `{t['notional_usd_min']}–{t['notional_usd_max']}`",
            f"- single_pool_only: `{t['single_pool_only']}`",
            f"- low_risk_path_only: `{t['low_risk_path_only']}`",
            "",
            "## 进入 probe 前必须满足的 gate（本脚本不放行）",
            "",
            "1. precise quote ready",
            "2. tick-liquidity ready",
            "3. real cost ready",
            "4. fee velocity ready",
            "5. realistic or near-break-even positive candidate present",
            "6. manual approval required",
            "7. dry-run transaction builder only after approval",
            "8. no auto-submit",
            "",
            "## 一旦人工放行（仍需独立审计后实施），必须记录",
            "",
            *[f"- {item}" for item in design["must_record"]],
            "",
            "## 严格执行边界（preflight 阶段一律禁止）",
            "",
            "```text",
            "max_funds_usd                                  = 20",
            "wallet_load_allowed_in_this_phase              = False",
            "signer_create_allowed_in_this_phase            = False",
            "eth_sendTransaction_allowed_in_this_phase      = False",
            "eth_sendRawTransaction_allowed_in_this_phase   = False",
            "increaseLiquidity_allowed_in_this_phase        = False",
            "decreaseLiquidity_allowed_in_this_phase        = False",
            "collect_allowed_in_this_phase                  = False",
            "approve_allowed_in_this_phase                  = False",
            "```",
            "",
            f"- best_net_ev_proxy_usd: `{design['best_net_ev_proxy_usd']}`",
            f"- best_net_ev_proxy_pct: `{design['best_net_ev_proxy_pct']}`",
        ]
    else:
        md += [
            "## 目前无候选",
            "",
            f"- best_net_ev_proxy_usd: `{design.get('best_net_ev_proxy_usd')}`",
            f"- best_pool: `{design.get('best_pool')}`",
            f"- best_pair: `{design.get('best_pair')}`",
            "",
            "blockers:",
            "",
            *[f"- {b}" for b in design["blockers"]],
            "",
            "recommended_next_stage: `LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_FIX_REPEAT`",
        ]
    md += [
        "",
        "## 全局安全",
        "",
        "```text",
        "edge_proven                = no",
        "tiny_canary_allowed        = no",
        "can_run_probe_now          = no",
        "wallet_or_tx_touched       = false",
        "actual_fee_ready           = false",
        "token_id_available         = false",
        "```",
    ]
    (args.report_dir / "BSC_10_20U_PROBE_PREFLIGHT_DESIGN_CN.md").write_text("\n".join(md) + "\n")

    print(json.dumps({
        "preflight_kind": design["preflight_kind"],
        "can_run_probe_now": False,
        "recommended_next_stage": design["recommended_next_stage"],
    }, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
