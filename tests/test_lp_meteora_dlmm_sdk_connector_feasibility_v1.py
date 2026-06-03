"""Tests for LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT_V1 stage.

Properties asserted:
  * no keypair / no private key / no seed phrase anywhere
  * no signer / no sendTransaction / no wallet adapter
  * SDK package audit ran and recorded
  * known pool feed ready (2 pools, all from official SDK examples)
  * SDK known-pool smoke succeeded (2/2 pools decoded)
  * quote smoke was attempted; root cause documented for failures
  * 6-table connector schema designed
  * discovery strategy decision is in allowed set
  * SDK JS scripts are read-only (no keypair, no sendTransaction, no swap tx, no wallet adapter)
  * final verdict allowed next stages only contains the 4 specific stages
  * can_run_probe_now / tiny_canary_allowed locked safe
  * v2 line count 992 unchanged
  * repo node_modules NOT created
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260603_130532"
REPORT_DIR = REPO_ROOT / "reports" / "lp_meteora_dlmm_sdk_connector_feasibility" / RUN_ID

V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"
SDK_SMOKE_SCRIPT = REPO_ROOT / "scripts" / "lp_meteora_dlmm_sdk_known_pool_smoke_v1_readonly.js"
SDK_QUOTE_SCRIPT = REPO_ROOT / "scripts" / "lp_meteora_dlmm_sdk_quote_smoke_v1_readonly.js"

ALLOWED_NEXT_STAGES = {
    "LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1",
    "LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT",
    "LP_SOLANA_PAID_RPC_SETUP_REQUIRED",
    "STOP_LP_RESEARCH_NOW",
}
FORBIDDEN_NEXT_STAGES = {
    "EXECUTE_NOW",
    "FIRST_EXECUTION_RUN_V1",
    "MINT_NOW",
    "SEND_NOW",
    "WAIT_FOR_MONITOR_COMPLETION",
    "LP_BASE_10U_PROBE_LIVE",
    "LP_BASE_10U_PROBE_CANARY",
    "LP_BASE_10U_PROBE_PAPER",
    "LP_BASE_10U_PROBE_MARKET_UNSAFE_WAIT_V1",
    "PROBE_NOW",
    "LIVE_TRADE_NOW",
    "OPEN_LP_NOW",
    "CLOSE_LP_NOW",
}


def _read_json(rel: str) -> dict | None:
    p = REPORT_DIR / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text())


# --- FINAL_VERDICT.json -----------------------------------------------

def test_final_verdict_exists() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv is not None
    assert fv["stage"] == "LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT_V1"
    assert fv["status"] in ("PASS", "WARN", "FAIL")


def test_final_verdict_safety_locks_intact() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["can_run_probe_now"] is False
    assert fv["execution_allowed_now"] is False
    assert fv["transaction_sent"] is False
    assert fv["wallet_or_tx_touched"] is False
    assert fv["solana_wallet_or_keypair_touched"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["send_hard_disable_still_active"] is True
    assert fv["v2_modified_by_this_task"] is False
    assert fv["v2_line_count_unchanged"] is True
    assert fv["manual_approval_required"] is True


def test_final_verdict_sdk_audit_ran_and_succeeded() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["sdk_package_audit_ran"] is True
    assert fv["sdk_install_or_pack_success"] is True
    assert fv["sdk_version_resolved"] == "1.9.10"
    assert fv["sdk_repo_root_touched"] is False


def test_final_verdict_known_pool_feed_ready() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["known_pool_feed_ready"] is True
    assert fv["known_pool_feed_size"] == 2
    assert fv["all_pools_from_official_source"] is True


def test_final_verdict_known_pool_smoke_succeeded() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["known_pool_smoke_ran"] is True
    assert fv["known_pool_smoke_success"] is True


def test_final_verdict_quote_smoke_attempted_blocked_documented() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["quote_smoke_ran"] is True
    # V3 quote blocked on public RPC; root cause documented
    assert fv["quote_smoke_success"] is False
    assert fv["quote_smoke_blocker"] is not None
    assert "bin_array" in fv["quote_smoke_blocker"].lower() or "rpc" in fv["quote_smoke_blocker"].lower()


def test_final_verdict_connector_schema_ready() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["connector_schema_ready"] is True
    assert fv["connector_schema_tables_count"] == 6


def test_final_verdict_recommended_near_term_path_known_pool_feed() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_near_term_path"] == "known_pool_feed_sdk_decode"


def test_final_verdict_recommended_next_stage_in_allowed() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_final_verdict_recommended_next_stage_not_in_forbidden() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    rns = fv["recommended_next_stage"]
    assert rns not in FORBIDDEN_NEXT_STAGES
    for sub in ["EXECUTE_NOW", "FIRST_EXECUTION_RUN", "MINT_NOW", "SEND_NOW",
                "LIVE", "CANARY", "PAPER", "MARKET_UNSAFE_WAIT",
                "PROBE_NOW", "OPEN_LP_NOW", "CLOSE_LP_NOW"]:
        assert sub not in rns


# --- All artifacts present -------------------------------------------

@pytest.mark.parametrize("name", [
    "INPUT_EVIDENCE_AUDIT_CN.md", "input_evidence_audit.json",
    "METEORA_DLMM_SDK_PACKAGE_AUDIT_CN.md",
    "meteora_dlmm_sdk_package_audit.json",
    "METEORA_DLMM_KNOWN_POOL_FEED_CN.md",
    "meteora_dlmm_known_pool_feed.csv",
    "meteora_dlmm_known_pool_feed.json",
    "METEORA_DLMM_SDK_KNOWN_POOL_SMOKE_CN.md",
    "meteora_dlmm_sdk_known_pool_smoke.json",
    "METEORA_DLMM_SDK_QUOTE_SMOKE_CN.md",
    "meteora_dlmm_sdk_quote_smoke.json",
    "meteora_dlmm_sdk_quote_smoke.csv",
    "METEORA_DLMM_KNOWN_POOL_CONNECTOR_SCHEMA_CN.md",
    "meteora_dlmm_known_pool_connector_schema.json",
    "METEORA_DLMM_DISCOVERY_STRATEGY_DECISION_CN.md",
    "meteora_dlmm_discovery_strategy_decision.json",
    "METEORA_DLMM_SDK_FEASIBILITY_NEXT_STAGE_DECISION_CN.md",
    "meteora_dlmm_sdk_feasibility_next_stage_decision.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = REPORT_DIR / name
    assert p.is_file(), f"missing: {p}"
    assert p.stat().st_size > 0


# --- Stage C: SDK package audit -------------------------------------

def test_sdk_package_audit_has_required_fields() -> None:
    j = _read_json("meteora_dlmm_sdk_package_audit.json")
    for key in ["package_name", "resolved_version", "install_attempted",
                "install_success", "install_dir", "has_dlmm_create",
                "has_get_active_bin", "has_swap_quote", "has_get_fee_info",
                "has_bin_array_helpers", "wallet_related_imports_present",
                "wallet_related_imports_used", "confidence"]:
        assert key in j, f"missing field: {key}"
    assert j["package_name"] == "@meteora-ag/dlmm"
    assert j["resolved_version"] == "1.9.10"
    assert j["install_attempted"] is True
    assert j["install_success"] is True
    assert j["install_dir"].startswith("/tmp")
    assert j["install_in_isolated_tmp_dir"] is True
    assert j["repo_root_touched"] is False
    assert j["repo_node_modules_created"] is False
    assert j["wallet_related_imports_used"] is False
    assert j["wallet_adapter_imported"] is False
    assert j["keypair_instantiated_by_us"] is False


# --- Stage D: known pool feed ---------------------------------------

def test_known_pool_feed_has_2_selected_1_skipped() -> None:
    j = _read_json("meteora_dlmm_known_pool_feed.json")
    selected = [p for p in j["pools"] if p["selected_for_sdk_smoke"]]
    skipped = [p for p in j["pools"] if not p["selected_for_sdk_smoke"]]
    assert len(selected) == 2
    assert len(skipped) == 1
    for p in selected:
        assert p["mainnet_verified"] is True
        assert p["source"] == "official_sdk_example"
        assert p["expected_owner_program"] == "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"


# --- Stage E: SDK known-pool smoke ---------------------------------

def test_known_pool_smoke_2_of_2_full_decode() -> None:
    j = _read_json("meteora_dlmm_sdk_known_pool_smoke.json")
    assert j["smoke_success"] is True
    results = j["results"]
    assert len(results) == 2
    for r in results:
        assert r["sdk_decode_success"] is True
        assert r["pool_owner"] == "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
        assert r["bin_step"] is not None
        assert r["token_x"] is not None
        assert r["token_y"] is not None
        assert r["active_bin_id"] is not None
        assert r["active_bin_price"] is not None
        assert r["reserve_x_amount"] is not None
        assert r["reserve_y_amount"] is not None
        assert r["fee_info_available"] is True
        assert r["fee_info_base_fee_bps"] is not None


def test_known_pool_smoke_no_signer_call() -> None:
    j = _read_json("meteora_dlmm_sdk_known_pool_smoke.json")
    s = json.dumps(j)
    bad = ["Keypair.from_secret_key(", "Keypair.generate(", "Account.from_key(",
           "sendTransaction(", "sendRawTransaction(",
           "new Keypair()", "from_secret_key(", "from_seed(", "from_mnemonic(",
           "initializePositionAndAddLiquidityByStrategy",
           "addLiquidityByStrategy",
           "removeLiquidity",
           "closePosition", "claimFee", "claimReward"]
    for b in bad:
        assert b not in s, f"smoke result contains suspicious token: {b!r}"


# --- Stage F: SDK quote smoke ---------------------------------------

def test_quote_smoke_attempted_blocked_documented() -> None:
    j = _read_json("meteora_dlmm_sdk_quote_smoke.json")
    assert j["smoke_attempted"] is True
    assert j["quote_success_count"] == 0
    for r in j["results"]:
        assert r["error_stage"] == "getBinArrayForSwap"
        # Root cause must mention 403 or 410
        assert "403" in r["error"] or "410" in r["error"]


def test_quote_smoke_swap_transaction_not_built() -> None:
    j = _read_json("meteora_dlmm_sdk_quote_smoke.json")
    assert j["swap_transaction_built"] is False
    assert j["solana_wallet_or_keypair_touched"] is False
    assert j["transaction_sent"] is False
    assert j["signer_used"] is False
    assert j["wallet_adapter_used"] is False


# --- Stage G: connector schema -------------------------------------

def test_connector_schema_6_tables() -> None:
    j = _read_json("meteora_dlmm_known_pool_connector_schema.json")
    tables = j["tables"]
    assert len(tables) == 6
    table_ids = {t["table_id"] for t in tables}
    expected = {
        "meteora_dlmm_known_pool_universe_v1",
        "meteora_dlmm_pool_snapshot_v1",
        "meteora_dlmm_bin_liquidity_snapshot_v1",
        "meteora_dlmm_quote_snapshot_v1",
        "meteora_dlmm_fee_snapshot_v1",
        "meteora_dlmm_survival_ev_preview_v1",
    }
    assert table_ids == expected


def test_connector_schema_field_coverage() -> None:
    j = _read_json("meteora_dlmm_known_pool_connector_schema.json")
    cov = j["field_coverage_check"]
    for k in ["pool_address", "token_x", "token_y", "bin_step", "active_bin",
              "active_price", "fee_parameters", "reserve_x", "reserve_y",
              "bin_liquidity", "quote_10u", "quote_20u",
              "data_confidence", "invalid_reason"]:
        assert k in cov, f"field coverage missing: {k}"


# --- Stage H: discovery strategy decision --------------------------

def test_discovery_strategy_3_paths_evaluated() -> None:
    j = _read_json("meteora_dlmm_discovery_strategy_decision.json")
    strategies = {s["strategy_id"] for s in j["strategies_evaluated"]}
    assert strategies == {"paid_rpc_gpa", "known_pool_feed_sdk_decode", "official_rest_api"}


def test_discovery_strategy_known_pool_feed_selected() -> None:
    j = _read_json("meteora_dlmm_discovery_strategy_decision.json")
    assert j["selected_strategy"] == "known_pool_feed_sdk_decode"
    assert j["recommended_near_term_path"] == "known_pool_feed_sdk_decode"


# --- Stage I: next-stage decision -----------------------------------

def test_next_stage_decision_in_allowed() -> None:
    j = _read_json("meteora_dlmm_sdk_feasibility_next_stage_decision.json")
    assert j["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_next_stage_decision_is_known_pool_connector_v1() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    j = _read_json("meteora_dlmm_sdk_feasibility_next_stage_decision.json")
    assert j["recommended_next_stage"] == "LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1"
    assert fv["recommended_next_stage"] == "LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1"


def test_next_stage_decision_must_not_list() -> None:
    j = _read_json("meteora_dlmm_sdk_feasibility_next_stage_decision.json")
    must_not = j["next_stage_must_not"]
    must_haves = [
        "execute probe", "send any tx",
        "keypair",
        "bridge", "swap",
        "hard-disable",
        "can_run_probe_now to true",
        "tiny_canary_allowed to yes"
    ]
    for m in must_haves:
        assert any(m in line for line in must_not), f"missing must_not: {m!r}"


# --- v2 line count 992 unchanged ---------------------------------

def test_v2_line_count_unchanged() -> None:
    assert V2.is_file()
    with V2.open() as f:
        n = sum(1 for _ in f)
    assert n == 992, f"v2 line count changed: {n}"


# --- Repo root not polluted ---------------------------------------

def test_repo_node_modules_not_created() -> None:
    nm = REPO_ROOT / "node_modules"
    assert not nm.is_dir(), f"repo node_modules was created: {nm}"


def test_repo_package_json_not_modified() -> None:
    # V3 did NOT add a package.json to repo root
    pj = REPO_ROOT / "package.json"
    if pj.is_file():
        # if it exists (it shouldn't for V3 work), check no meteora dependency
        j = json.loads(pj.read_text())
        deps_str = json.dumps(j.get("dependencies", {})) + json.dumps(j.get("devDependencies", {}))
        assert "meteora-ag" not in deps_str, "package.json mentions meteora-ag"


# --- Sweep: safety invariants stay false everywhere ------------

def test_can_run_probe_now_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "can_run_probe_now" in data:
            assert data["can_run_probe_now"] is False, (
                f"{jf.name} has can_run_probe_now={data['can_run_probe_now']!r}"
            )


def test_solana_wallet_or_keypair_touched_false_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "solana_wallet_or_keypair_touched" in data:
            assert data["solana_wallet_or_keypair_touched"] is False, (
                f"{jf.name} has solana_wallet_or_keypair_touched={data['solana_wallet_or_keypair_touched']!r}"
            )


def test_tiny_canary_allowed_no_everywhere() -> None:
    for jf in REPORT_DIR.glob("*.json"):
        data = json.loads(jf.read_text())
        if "tiny_canary_allowed" in data:
            assert data["tiny_canary_allowed"] == "no", (
                f"{jf.name} has tiny_canary_allowed={data['tiny_canary_allowed']!r}"
            )


# --- No secret-shaped strings in artifacts ---------------------

def test_no_64hex_private_key_shape_in_any_artifact() -> None:
    safe_uint256_fields = {
        "pool_liquidity_raw", "pool_slot0_raw", "gas_price_wei",
        "wallet_eth_wei", "usdc_balance_raw", "weth_balance_raw",
        "usdc_allowance_raw", "weth_allowance_raw", "block_number",
        "lamports",
    }
    pat = re.compile(r'"(0x[0-9a-fA-F]{64})"')
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for m in pat.finditer(txt):
            hex_val = m.group(1)
            start = txt.rfind("\n", 0, m.start()) + 1
            end = txt.find("\n", m.end())
            if end < 0:
                end = len(txt)
            line = txt[start:end]
            if any(fld in line for fld in safe_uint256_fields):
                continue
            assert False, f"{f.name} contains 64-hex NOT in safe field: {line!r}"


def test_no_signer_construction_strings() -> None:
    bad = ["Account.from_key(", "LocalAccount(", "from_mnemonic(",
           "load_keystore(", "HTTPProvider(", "Web3(",
           "send_raw_transaction(", "sign_transaction(",
           "eth.send_transaction(",
           "Keypair.from_secret_key(", "Keypair.generate(",
           "from_secret_key(", "from_seed(", "from_bytes(",
           "sendTransaction(", "sendRawTransaction(",
           "solana-keygen", "wallet add"]
    for f in REPORT_DIR.iterdir():
        if not f.is_file():
            continue
        txt = f.read_text(errors="ignore")
        for b in bad:
            assert b not in txt, f"{f.name} contains suspicious call: {b!r}"


# --- SDK JS scripts static safety check -------------------------

def test_sdk_smoke_script_no_signer_no_tx() -> None:
    """Static check: the SDK smoke JS script must not call signer/tx/position methods."""
    assert SDK_SMOKE_SCRIPT.is_file()
    src = SDK_SMOKE_SCRIPT.read_text()
    bad = [
        "Keypair.from_secret_key(", "Keypair.generate(", "Keypair.from_seed(",
        "new Keypair()",
        "sendTransaction(", "sendRawTransaction(",
        "initializePositionAndAddLiquidityByStrategy",
        "addLiquidityByStrategy",
        "removeLiquidity",
        "closePosition", "claimFee", "claimReward",
        "wallet add", "wallet import",
        "@solana/wallet-adapter",
    ]
    for b in bad:
        assert b not in src, f"SDK smoke script contains suspicious token: {b!r}"


def test_sdk_quote_script_no_signer_no_tx_builder() -> None:
    """Static check: the SDK quote JS script must not call signer/tx-builder/swap methods."""
    assert SDK_QUOTE_SCRIPT.is_file()
    src = SDK_QUOTE_SCRIPT.read_text()
    bad = [
        "Keypair.from_secret_key(", "Keypair.generate(", "Keypair.from_seed(",
        "new Keypair()",  # ephemeral random keypair
        "sendTransaction(", "sendRawTransaction(",
        # SDK tx-builder methods (construct Transaction, not just quote)
        "swapExactIn(",  # tx builder
        "swapExactOut(",  # tx builder
        "initializePositionAndAddLiquidityByStrategy",
        "addLiquidityByStrategy",
        "removeLiquidity",
        "closePosition", "claimFee", "claimReward",
        "wallet add", "wallet import",
        "@solana/wallet-adapter",
    ]
    for b in bad:
        assert b not in src, f"SDK quote script contains suspicious token: {b!r}"


def test_sdk_quote_script_only_uses_swapquote_for_quote() -> None:
    """The quote script must only call swapQuote (read-only) for quote, not swap tx builder."""
    assert SDK_QUOTE_SCRIPT.is_file()
    src = SDK_QUOTE_SCRIPT.read_text()
    # swapQuote is allowed (returns a quote object; no tx)
    assert "swapQuote" in src
    # swap (tx builder) is NOT called
    # the keyword `dlmmPool.swap(` (with paren) would indicate tx builder
    assert "dlmmPool.swap(" not in src, "script calls tx builder dlmmPool.swap("


# --- REST API 404 does not fake success ---------------------

def test_rest_api_404_does_not_fake_success() -> None:
    """The official REST API is documented as 404 (V2 finding). V3 must not claim
    success from it."""
    fv = _read_json("FINAL_VERDICT.json")
    # The decision is known_pool_feed_sdk_decode, NOT official_rest_api
    assert fv["recommended_near_term_path"] == "known_pool_feed_sdk_decode"
    # And the official_rest_api strategy should be marked not_viable
    j = _read_json("meteora_dlmm_discovery_strategy_decision.json")
    rest = next((s for s in j["strategies_evaluated"] if s["strategy_id"] == "official_rest_api"), None)
    assert rest is not None
    # Either not_viable, or v3_status marks it 404 / not_found
    assert "404" in str(rest) or "unknown" in str(rest).lower() or "deprecated" in str(rest).lower()
