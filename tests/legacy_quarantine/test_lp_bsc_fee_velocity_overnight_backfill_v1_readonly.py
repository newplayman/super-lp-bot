from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path("/Users/bendu/lp-bot/v3/scripts/lp_bsc_fee_velocity_overnight_backfill_v1_readonly.py")
spec = importlib.util.spec_from_file_location("lp_bsc_fee_velocity_overnight_backfill_v1_readonly", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_script_is_readonly_bsc_only_and_has_required_controls() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    banned = [
        "eth_sendrawtransaction(",
        "eth_sendtransaction(",
        "signtransaction(",
        "--canary-mint",
        "private_key =",
        "mnemonic =",
        "wallet.load",
        "createsigner",
        "swap(",
        "mint(",
        "burn(",
        "collect(",
        "approve(",
    ]
    for token in banned:
        assert token not in text

    assert "lp_bsc_pancakeswap_v3_fee_velocity_overnight_backfill_v1" in text
    assert "--max-hours" in text
    assert "--checkpoint-minutes" in text
    assert "eth_getlogs" in text
    assert "checkpoint/state.json" in text
    assert "tiny_canary_allowed" in text
    assert module.ALLOWED_NEXT == {
        "LP_BSC_PANCAKESWAP_V3_REALDATA_REVIEW_V1",
        "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_FIX_REPEAT",
        "LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_REPEAT",
        "STOP_LP_RESEARCH_NOW",
    }


def test_checkpoint_state_schema_and_safety_audit() -> None:
    rpc_ready = {"rpc_env_key": "public_fallback", "latest_block": "123456"}
    state = module.build_checkpoint_state(
        run_id="20260602_235959",
        started_at=1710000000,
        windows=["24h", "72h"],
        pool_contexts=[{"pool_id": "0x1"}, {"pool_id": "0x2"}],
        selected_rows=[{"pool_address": "0x1"}, {"pool_address": "0x2"}],
        rpc_ready=rpc_ready,
        resume=False,
    )

    for field in [
        "run_id",
        "started_at",
        "current_time",
        "windows",
        "completed_targets",
        "completed_window_targets",
        "pool_count",
        "selected_pool_count",
        "next_pool_index",
        "next_window_index",
        "last_checkpoint_at",
        "resume",
        "rpc_env_key",
        "latest_block",
    ]:
        assert field in state
    assert state["pool_count"] == 2
    assert state["selected_pool_count"] == 2
    assert state["rpc_env_key"] == "public_fallback"
    assert state["latest_block"] == 123456

    audit = module.safety_audit()
    assert audit["private_key_loaded"] is False
    assert audit["wallet_loaded"] is False
    assert audit["signer_created"] is False
    assert audit["transaction_sent"] is False
    assert audit["eth_sendTransaction_called"] is False
    assert audit["eth_sendRawTransaction_called"] is False
    assert audit["swap_called"] is False
    assert audit["mint_called"] is False
    assert audit["burn_called"] is False
    assert audit["collect_called"] is False
    assert audit["approve_called"] is False
    assert audit["eth_getLogs_bounded"] is True
    assert audit["read_only_eth_call_only"] is True
    assert audit["event_logs_read_only"] is True
    assert audit["wallet_or_tx_touched"] is False
    assert audit["can_run_probe_now"] is False
    assert audit["tiny_canary_allowed"] == "no"


def test_final_verdict_schema_and_stage_decision_are_restricted() -> None:
    fee_blockers_summary = {
        "pool_count": 2,
        "fee_ready_pool_count": 0,
        "nonzero_pool_count": 1,
    }
    summary_rows = [
        {
            "log_count": 3,
            "volume_usd_proxy": 12.5,
            "pool_fee_usd_proxy": 0.0125,
        }
    ]
    econ_agg = {
        "positive_proxy_count_total": 0,
        "positive_proxy_count_realistic": 0,
        "best_pool": "0x1",
        "best_pair": "WBNB/USDT",
        "best_fee_tier": "100",
        "best_notional": 20,
        "best_hold_window": "15m",
        "best_net_ev_proxy_usd": -0.01,
        "best_fee_window_used": "24h",
    }
    verdict = module.build_final_verdict(
        run_id="20260602_235959",
        selected_rows=[{"pool_address": "0x1"}, {"pool_address": "0x2"}],
        fee_blockers_summary=fee_blockers_summary,
        fee_rows=[],
        summary_rows=summary_rows,
        econ_agg=econ_agg,
        windows_completed=["24h"],
        pool_code_rows=[{"eth_getCode_ok": "yes"}, {"eth_getCode_ok": "no"}],
    )

    for field in [
        "status",
        "stage",
        "run_id",
        "selected_pool_count",
        "windows_completed",
        "swap_log_pool_count",
        "fee_ready_pool_count",
        "swap_log_count",
        "volume_usd_total",
        "pool_fee_usd_proxy_total",
        "economics_preview_ran",
        "positive_proxy_count_total",
        "positive_proxy_count_realistic",
        "best_pool",
        "best_pair",
        "best_fee_tier",
        "best_notional",
        "best_hold_window",
        "best_net_ev_proxy_usd",
        "actual_fee_ready",
        "token_id_available",
        "can_run_probe_now",
        "can_run_virtual_economics_now",
        "edge_proven",
        "tiny_canary_candidate",
        "tiny_canary_allowed",
        "wallet_or_tx_touched",
        "recommended_next_stage",
        "window_count",
        "selected_pool_rows_with_code",
    ]:
        assert field in verdict

    assert verdict["edge_proven"] == "no"
    assert verdict["actual_fee_ready"] is False
    assert verdict["token_id_available"] is False
    assert verdict["can_run_probe_now"] is False
    assert verdict["tiny_canary_candidate"] == "no"
    assert verdict["tiny_canary_allowed"] == "no"
    assert verdict["wallet_or_tx_touched"] is False
    assert verdict["recommended_next_stage"] in module.ALLOWED_NEXT
    assert verdict["selected_pool_rows_with_code"] == 1
    assert verdict["best_pool"] == "0x1"
    assert verdict["best_pair"] == "WBNB/USDT"
    assert verdict["best_hold_window"] == "15m"

