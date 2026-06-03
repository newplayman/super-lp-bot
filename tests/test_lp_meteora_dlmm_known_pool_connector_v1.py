"""Tests for LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1 stage.

Properties asserted:
  * no keypair / no private key / no seed phrase anywhere
  * no signer / no sendTransaction / no wallet adapter
  * no swap tx builder call
  * repo root node_modules NOT created
  * known pool feed required (full addresses from V3 artifact)
  * connector script: only --mode snapshot/quote-smoke/all
  * pool_snapshot_success_count == 2
  * fee_snapshot_success_count == 2
  * bin_liquidity_snapshot_success_count == 0 (blocked on public RPC)
  * quote_snapshot_success_count == 0 (blocked on public RPC)
  * quote blocked does NOT fake success
  * final verdict allowed next stages only contains the 5 specific stages
  * can_run_probe_now / tiny_canary_allowed locked safe
  * v2 line count 992 unchanged
  * SDK install in /tmp isolated
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260603_134202"
REPORT_DIR = REPO_ROOT / "reports" / "lp_meteora_dlmm_known_pool_connector" / RUN_ID

V2 = REPO_ROOT / "scripts" / "lp_base_10u_probe_executor_v2.py"
CONNECTOR_SCRIPT = REPO_ROOT / "scripts" / "lp_meteora_dlmm_known_pool_connector_v1_readonly.js"

ALLOWED_NEXT_STAGES = {
    "LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT",
    "LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1",
    "LP_SOLANA_PAID_RPC_SETUP_REQUIRED",
    "LP_METEORA_DLMM_KNOWN_POOL_CONNECTOR_FIX_REPEAT",
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
    assert fv["stage"] == "LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1"
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


def test_final_verdict_connector_built_and_pools_decoded() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["known_pool_connector_built"] is True
    assert fv["known_pool_count"] == 2
    assert fv["pool_snapshot_success_count"] == 2
    assert fv["fee_snapshot_success_count"] == 2


def test_final_verdict_blocked_documented_honestly() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["bin_liquidity_snapshot_success_count"] == 0
    assert fv["quote_snapshot_success_count"] == 0
    assert fv["needs_paid_rpc"] is True


def test_final_verdict_judgments() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["connector_readonly_ready"] is True
    assert fv["quote_ready"] is False
    assert fv["survival_ev_ready"] is False
    assert fv["needs_known_pool_feed_expansion"] is False


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
    "METEORA_KNOWN_POOL_UNIVERSE_CN.md",
    "meteora_known_pool_universe.csv",
    "meteora_known_pool_universe.json",
    "METEORA_POOL_SNAPSHOT_CN.md",
    "meteora_pool_snapshot.csv",
    "meteora_pool_snapshot.json",
    "METEORA_FEE_SNAPSHOT_CN.md",
    "meteora_fee_snapshot.csv",
    "meteora_fee_snapshot.json",
    "METEORA_BIN_LIQUIDITY_SNAPSHOT_CN.md",
    "meteora_bin_liquidity_snapshot.csv",
    "meteora_bin_liquidity_snapshot.json",
    "METEORA_QUOTE_SNAPSHOT_CN.md",
    "meteora_quote_snapshot.csv",
    "meteora_quote_snapshot.json",
    "METEORA_CONNECTOR_READINESS_MATRIX_CN.md",
    "meteora_connector_readiness_matrix.json",
    "METEORA_KNOWN_POOL_CONNECTOR_NEXT_STAGE_DECISION_CN.md",
    "meteora_known_pool_connector_next_stage_decision.json",
    "FINAL_VERDICT.json", "ONEPAGE_CN.md", "ARTIFACT_INDEX.md",
])
def test_artifact_present(name: str) -> None:
    p = REPORT_DIR / name
    assert p.is_file(), f"missing: {p}"
    assert p.stat().st_size > 0


# --- Stage C: connector script exists + safety --------------------

def test_connector_script_exists() -> None:
    assert CONNECTOR_SCRIPT.is_file()


def test_connector_script_no_signer_no_tx() -> None:
    """Static check: the connector JS script must not call signer/tx/position methods."""
    src = CONNECTOR_SCRIPT.read_text()
    bad = [
        "Keypair.from_secret_key(", "Keypair.generate(", "Keypair.from_seed(",
        "new Keypair()",  # no ephemeral random keypair
        "sendTransaction(", "sendRawTransaction(",
        # SDK tx-builder methods (construct Transaction, not just quote)
        "dlmmPool.swapExactIn(",
        "dlmmPool.swapExactOut(",
        "initializePositionAndAddLiquidityByStrategy",
        "addLiquidityByStrategy",
        "removeLiquidity",
        "closePosition", "claimFee", "claimReward",
        "wallet add", "wallet import",
        "@solana/wallet-adapter",
    ]
    for b in bad:
        assert b not in src, f"connector script contains suspicious token: {b!r}"


def test_connector_script_uses_swapquote_not_swap_tx() -> None:
    """The connector must only call swapQuote (read-only quote) for quote, not tx builder."""
    src = CONNECTOR_SCRIPT.read_text()
    # swapQuote is allowed (returns a quote object; no tx)
    assert "swapQuote" in src
    # swap (tx builder) is NOT called
    assert "dlmmPool.swap(" not in src, "script calls tx builder dlmmPool.swap("


def test_connector_script_supports_modes() -> None:
    """The connector must support snapshot / quote-smoke / all modes."""
    src = CONNECTOR_SCRIPT.read_text()
    for mode in ["snapshot", "quote-smoke", "all"]:
        assert f'"{mode}"' in src or f"'{mode}'" in src, f"mode {mode!r} not supported"


def test_connector_script_isolated_sdk_dir() -> None:
    """The connector must use /tmp isolated install, not repo root."""
    src = CONNECTOR_SCRIPT.read_text()
    assert "/tmp" in src


# --- Stage D: known pool universe --------------------------------

def test_known_pool_universe_has_2_selected_1_skipped() -> None:
    j = _read_json("meteora_known_pool_universe.json")
    selected = [p for p in j["pools"] if p["selected_for_snapshot"]]
    skipped = [p for p in j["pools"] if not p["selected_for_snapshot"]]
    assert len(selected) == 2
    assert len(skipped) == 1
    for p in selected:
        assert p["source"] == "official_sdk_example"
        assert p["expected_owner_program"] == "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"


def test_known_pool_universe_full_addresses_from_v3_artifact() -> None:
    """Pool addresses must be the full strings from V3 artifact (not truncated)."""
    j = _read_json("meteora_known_pool_universe.json")
    selected = [p["pool_address"] for p in j["pools"] if p["selected_for_snapshot"]]
    # V3 full addresses from artifact
    expected_1 = "5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF"
    expected_2 = "9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad"
    assert expected_1 in selected
    assert expected_2 in selected
    # None should be truncated with ...
    for addr in selected:
        assert "..." not in addr, f"pool address truncated: {addr!r}"


# --- Stage E: pool snapshot --------------------------------------

def test_pool_snapshot_2_of_2_full_decode() -> None:
    j = _read_json("meteora_pool_snapshot.json")
    assert len(j) == 2
    for r in j:
        assert r["sdk_decode_success"] is True
        assert r["pool_owner"] == "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
        assert r["bin_step"] is not None
        assert r["token_x_mint"] is not None
        assert r["token_y_mint"] is not None
        assert r["active_bin_id"] is not None
        assert r["active_price"] is not None
        assert r["reserve_x_raw"] is not None
        assert r["reserve_y_raw"] is not None


def test_pool_snapshot_no_signer_call() -> None:
    j = _read_json("meteora_pool_snapshot.json")
    s = json.dumps(j)
    bad = ["Keypair.from_secret_key(", "Keypair.generate(", "Account.from_key(",
           "sendTransaction(", "sendRawTransaction(",
           "new Keypair()", "from_secret_key(", "from_seed(", "from_mnemonic(",
           "initializePositionAndAddLiquidityByStrategy",
           "addLiquidityByStrategy",
           "removeLiquidity",
           "closePosition", "claimFee", "claimReward"]
    for b in bad:
        assert b not in s, f"pool snapshot contains suspicious token: {b!r}"


# --- Stage F: fee snapshot ---------------------------------------

def test_fee_snapshot_2_of_2_with_base_and_max() -> None:
    j = _read_json("meteora_fee_snapshot.json")
    assert len(j) == 2
    for r in j:
        assert r["fee_info_available"] is True
        assert r["base_fee_bps"] is not None
        assert r["max_fee_bps"] is not None
        assert r["source_method"] == "dlmmPool.getFeeInfo()"


# --- Stage G: bin liquidity attempt ------------------------------

def test_bin_liquidity_0_of_2_blocked_honestly() -> None:
    j = _read_json("meteora_bin_liquidity_snapshot.json")
    assert len(j) == 2
    for r in j:
        assert r["bin_array_attempted"] is True
        assert r["bin_array_success"] is False
        assert r["bin_count"] == 0
        assert r["total_x_amount"] is None
        assert r["total_y_amount"] is None
        assert r["blocker"] is not None
        # 403 or 410 — public RPC restriction
        assert "403" in r["blocker"] or "410" in r["blocker"]


# --- Stage H: quote snapshot attempt -----------------------------

def test_quote_0_of_4_blocked_honestly() -> None:
    j = _read_json("meteora_quote_snapshot.json")
    assert len(j) == 4
    for r in j:
        assert r["quote_attempted"] is True
        assert r["quote_success"] is False
        assert r["amount_out_raw"] is None
        assert r["blocker"] is not None


def test_quote_blocked_does_not_fake_success() -> None:
    """V4 must not claim quote success when blocker present."""
    j = _read_json("meteora_quote_snapshot.json")
    for r in j:
        if r["quote_success"] is True:
            assert r["blocker"] is None, f"quote marked success but blocker present: {r}"
        if r["quote_success"] is False:
            assert r["blocker"] is not None, f"quote marked failed but no blocker: {r}"


def test_quote_swap_transaction_not_built() -> None:
    """V4 quote script must NOT call swap tx builder."""
    j = _read_json("meteora_quote_snapshot.json")
    s = json.dumps(j)
    bad = [
        "Keypair.from_secret_key(", "Keypair.generate(", "new Keypair()",
        "sendTransaction(", "sendRawTransaction(",
        "dlmmPool.swap(",
        "createTransaction",
        "signTransaction",
    ]
    for b in bad:
        assert b not in s


# --- Stage I: readiness matrix -----------------------------------

def test_readiness_matrix_6_tables() -> None:
    j = _read_json("meteora_connector_readiness_matrix.json")
    assert len(j["tables"]) == 6


def test_readiness_matrix_3_ready_2_blocked_1_blocked_missing() -> None:
    j = _read_json("meteora_connector_readiness_matrix.json")
    s = j["summary"]
    assert s["tables_ready"] == 3
    assert s["tables_blocked_public_rpc"] == 2
    assert s["tables_blocked_missing_quote"] == 1


def test_readiness_matrix_judgments_consistent() -> None:
    j = _read_json("meteora_connector_readiness_matrix.json")
    jd = j["judgments"]
    assert jd["connector_readonly_ready"] is True
    assert jd["quote_ready"] is False
    assert jd["survival_ev_ready"] is False
    assert jd["needs_paid_rpc"] is True
    assert jd["needs_known_pool_feed_expansion"] is False


# --- Stage J: next-stage decision ---------------------------------

def test_next_stage_decision_in_allowed() -> None:
    j = _read_json("meteora_known_pool_connector_next_stage_decision.json")
    assert j["recommended_next_stage"] in ALLOWED_NEXT_STAGES


def test_next_stage_decision_is_quote_binarray_fix_repeat() -> None:
    fv = _read_json("FINAL_VERDICT.json")
    j = _read_json("meteora_known_pool_connector_next_stage_decision.json")
    assert j["recommended_next_stage"] == "LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT"
    assert fv["recommended_next_stage"] == "LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT"


def test_next_stage_decision_must_not_list() -> None:
    j = _read_json("meteora_known_pool_connector_next_stage_decision.json")
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
    pj = REPO_ROOT / "package.json"
    if pj.is_file():
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


# --- SDK install isolation ---------------------

def test_sdk_install_dir_is_isolated_tmp() -> None:
    """SDK install must be in /tmp, not repo root."""
    fv = _read_json("FINAL_VERDICT.json")
    assert fv["sdk_install_in_isolated_tmp"] is True
    assert fv["sdk_install_dir"].startswith("/tmp")
    assert fv["repo_node_modules_created"] is False
    assert fv["repo_root_touched_for_sdk"] is False
