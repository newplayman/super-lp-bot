"""Tests for LP_CONTINUOUS_STAGED_OBSERVATION_AND_COVERAGE_REPORT_V1.

These tests verify the deliverables of Stage A→J of the continuous staged
observation design:
  - A: V2 in-flight protection (read-only audit, no V2 modification)
  - B: input evidence audit
  - C: continuous_staged_observation_design
  - D: node_report_schema
  - E: pool_universe_coverage_manifest_spec
  - F: fee_estimation_without_probe
  - G: range_liquidity_fee_sensitivity_spec
  - H: node_report_generator_v1 (read-only, dry-run)
  - I: continuous_observation_next_stage_decision
  - J: FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX

All tests are read-only; they do NOT touch V2 supervisor / collector / data.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports" / "lp_continuous_staged_observation" / "20260605_082058"
V2_REPORT_DIR = ROOT / "reports" / "lp_long_horizon_readonly_collector_6h_run" / "20260605_043726"
V2_DATA_DIR = ROOT / "data" / "lp_long_horizon" / "20260605_043726"
SAMPLE_NODE_REPORT_DIR = ROOT / "reports" / "lp_long_horizon_node_reports" / "20260605_043726" / "6h"
GENERATOR = ROOT / "scripts" / "lp_long_horizon_node_report_generator_v1.py"

# ---------------------------------------------------------------------------
# A: V2 in-flight protection
# ---------------------------------------------------------------------------

def test_a_v2_inflight_protection_audit_exists() -> None:
    """Stage A: V2 protection audit files must exist."""
    assert (REPORT_DIR / "CURRENT_V2_PROTECTION_AUDIT_CN.md").exists()
    assert (REPORT_DIR / "current_v2_protection_audit.json").exists()


def test_a_v2_inflight_protection_audit_locked_fields() -> None:
    """Stage A: must explicitly set current_v2_not_touched=true, no_restart=true, etc."""
    audit = json.loads((REPORT_DIR / "current_v2_protection_audit.json").read_text())
    assert audit["current_v2_not_touched"] is True
    assert audit["no_restart"] is True
    assert audit["no_parallel_collector"] is True
    assert audit["no_kill"] is True
    assert audit["can_run_probe_now"] is False
    assert audit["tiny_canary_allowed"] == "no"
    assert audit["edge_proven"] == "no"


def test_a_v2_supervisor_pid_still_alive() -> None:
    """Stage A: V2 supervisor PID 3872268 must still be alive."""
    rc = subprocess.run(
        ["ps", "-p", "3872268", "-o", "pid="],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0
    assert "3872268" in rc.stdout


# ---------------------------------------------------------------------------
# B: input evidence audit
# ---------------------------------------------------------------------------

def test_b_input_evidence_audit_files_exist() -> None:
    assert (REPORT_DIR / "INPUT_EVIDENCE_AUDIT_CN.md").exists()
    assert (REPORT_DIR / "input_evidence_audit.json").exists()


def test_b_input_evidence_audit_key_assertions() -> None:
    audit = json.loads((REPORT_DIR / "input_evidence_audit.json").read_text())
    assert audit["key_assertions"]["one_shot_7d_replaced"] is True
    assert audit["key_assertions"]["stages"] == ["6h", "12h", "24h", "48h", "72h", "7d"]
    assert audit["key_assertions"]["auto_advance_allowed_originally"] is False
    assert audit["key_assertions"]["this_turn_only_designs_reporting_does_not_start_new_run"] is True
    assert audit["key_assertions"]["current_v2_6h_run_in_flight"] is True


# ---------------------------------------------------------------------------
# C: continuous_staged_observation_design
# ---------------------------------------------------------------------------

def test_c_continuous_staged_observation_design_files() -> None:
    assert (REPORT_DIR / "CONTINUOUS_STAGED_OBSERVATION_DESIGN_CN.md").exists()
    assert (REPORT_DIR / "continuous_staged_observation_design.json").exists()


def test_c_design_collector_continuity() -> None:
    d = json.loads((REPORT_DIR / "continuous_staged_observation_design.json").read_text())
    assert d["collector_continuity"] is True
    assert d["node_reports"] == ["6h", "12h", "24h", "48h", "72h", "7d"]
    assert d["data_collection_can_continue_between_nodes"] is True
    assert d["auto_probe_allowed"] is False
    assert d["auto_trade_allowed"] is False
    assert d["auto_advance_to_execution_allowed"] is False
    assert d["manual_approval_required_for_execution"] is True


def test_c_design_constraints_locked() -> None:
    d = json.loads((REPORT_DIR / "continuous_staged_observation_design.json").read_text())
    c = d["design_constraints"]
    assert c["C1_no_probe_canary_live_paper"] is True
    assert c["C2_no_wallet_keypair_signer"] is True
    assert c["C3_no_tx_send_approve_mint"] is True
    assert c["C9_can_run_probe_now_lock_false"] is True
    assert c["C10_tiny_canary_allowed_lock_no"] is True
    assert c["C11_edge_proven_lock_no"] is True


# ---------------------------------------------------------------------------
# D: node_report_schema
# ---------------------------------------------------------------------------

def test_d_node_report_schema_files() -> None:
    assert (REPORT_DIR / "NODE_REPORT_SCHEMA_CN.md").exists()
    assert (REPORT_DIR / "node_report_schema.json").exists()


def test_d_schema_required_fields_count() -> None:
    s = json.loads((REPORT_DIR / "node_report_schema.json").read_text())
    assert len(s["schema_validation"]["required_fields"]) >= 18


def test_d_schema_forbidden_keys() -> None:
    s = json.loads((REPORT_DIR / "node_report_schema.json").read_text())
    forbidden = set(s["schema_validation"]["forbidden_top_level_keys"])
    assert "tx_hash" in forbidden
    assert "wallet_address" in forbidden
    assert "private_key" in forbidden
    assert "keypair" in forbidden
    assert "mnemonic" in forbidden
    assert "seed" in forbidden
    assert "signed_transaction" in forbidden


def test_d_schema_node_stages_enum() -> None:
    s = json.loads((REPORT_DIR / "node_report_schema.json").read_text())
    assert s["node_report_top_level_fields"]["node_stage"]["enum"] == ["6h", "12h", "24h", "48h", "72h", "7d"]


def test_d_schema_gate_states() -> None:
    s = json.loads((REPORT_DIR / "node_report_schema.json").read_text())
    assert s["gate_block"]["gate_status"]["enum"] == ["PASS", "WARN_ACCEPTABLE", "FAIL"]


# ---------------------------------------------------------------------------
# E: pool_universe_coverage_manifest_spec
# ---------------------------------------------------------------------------

def test_e_coverage_manifest_spec_files() -> None:
    assert (REPORT_DIR / "POOL_UNIVERSE_COVERAGE_MANIFEST_SPEC_CN.md").exists()
    assert (REPORT_DIR / "pool_universe_coverage_manifest_spec.json").exists()


def test_e_spec_chains_count() -> None:
    s = json.loads((REPORT_DIR / "pool_universe_coverage_manifest_spec.json").read_text())
    chains = s["manifest_structure"]["manifest_level_1_chain_coverage"]["chains_in_design"]
    assert len(chains) == 7
    assert "base" in chains
    assert "bsc" in chains
    assert "solana" in chains


def test_e_spec_protocols_count() -> None:
    s = json.loads((REPORT_DIR / "pool_universe_coverage_manifest_spec.json").read_text())
    protos = s["manifest_structure"]["manifest_level_2_dex_protocol_coverage"]["dex_protocols_in_design"]
    assert len(protos) == 10


def test_e_spec_observed_false_protocols_listed() -> None:
    s = json.loads((REPORT_DIR / "pool_universe_coverage_manifest_spec.json").read_text())
    protos = s["manifest_structure"]["manifest_level_2_dex_protocol_coverage"]["dex_protocols_in_design"]
    missing = [p for p in protos if p["current_status"] == "missing"]
    assert len(missing) >= 5  # meteora_dlmm, raydium_cpmm, raydium_amm_v4, pancakeswap_v3, pancakeswap_v2


# ---------------------------------------------------------------------------
# F: fee_estimation_without_probe
# ---------------------------------------------------------------------------

def test_f_fee_estimation_files() -> None:
    assert (REPORT_DIR / "FEE_ESTIMATION_WITHOUT_PROBE_CN.md").exists()
    assert (REPORT_DIR / "fee_estimation_without_probe.json").exists()


def test_f_fee_estimation_locked_r0_fields() -> None:
    s = json.loads((REPORT_DIR / "fee_estimation_without_probe.json").read_text())
    locked = s["r0_state_locked_fields"]
    assert locked["actual_fee"] is False
    assert locked["fee_proxy"] is True
    assert locked["heuristic"] is True
    assert locked["actual_fee_accrual_rows_in_data_dir"] == 0
    assert locked["wallet_or_tx_touched"] is False
    assert locked["transaction_sent"] is False
    assert locked["can_run_probe_now"] is False
    assert locked["tiny_canary_allowed"] == "no"


def test_f_fee_estimation_pool_types() -> None:
    s = json.loads((REPORT_DIR / "fee_estimation_without_probe.json").read_text())
    types = s["fee_proxy_per_pool_type"]
    assert "V3_CLMM" in types
    assert "Meteora_DLMM" in types
    assert "CPMM_v2_cpmm" in types
    assert "Stable_LST_Stable" in types


def test_f_fee_estimation_r1_upgrade_requirements() -> None:
    s = json.loads((REPORT_DIR / "fee_estimation_without_probe.json").read_text())
    req = s["future_actual_fee_requirement"]["required_data_points"]
    # Substring match (spec uses verbose strings like "tokenId / positionId (V3/CLMM...)")
    req_str = " | ".join(req)
    assert "tokenId" in req_str
    assert "positionId" in req_str
    assert "feeGrowth" in req_str
    assert "tokensOwed" in req_str
    assert "collected fee" in req_str
    assert "add/remove cost" in req_str
    assert "realized PnL" in req_str
    assert len(req) >= 6


# ---------------------------------------------------------------------------
# G: range_liquidity_fee_sensitivity_spec
# ---------------------------------------------------------------------------

def test_g_range_sensitivity_files() -> None:
    assert (REPORT_DIR / "RANGE_LIQUIDITY_FEE_SENSITIVITY_SPEC_CN.md").exists()
    assert (REPORT_DIR / "range_liquidity_fee_sensitivity_spec.json").exists()


def test_g_v3_clmm_three_ranges() -> None:
    s = json.loads((REPORT_DIR / "range_liquidity_fee_sensitivity_spec.json").read_text())
    widths = s["v3_clmm_range_sensitivity"]["range_width_definition"]
    assert set(widths.keys()) == {"narrow", "medium", "wide"}


def test_g_dlmm_three_bin_coverages() -> None:
    s = json.loads((REPORT_DIR / "range_liquidity_fee_sensitivity_spec.json").read_text())
    coverages = s["meteora_dlmm_range_sensitivity"]["bin_coverage_definition"]
    assert set(coverages.keys()) == {"narrow", "medium", "wide"}


def test_g_cpmm_full_range() -> None:
    s = json.loads((REPORT_DIR / "range_liquidity_fee_sensitivity_spec.json").read_text())
    assert s["cpmm_range_sensitivity"]["note"].startswith("CPMM 池本身就是 full range")


# ---------------------------------------------------------------------------
# H: node_report_generator_v1
# ---------------------------------------------------------------------------

def test_h_generator_script_exists() -> None:
    assert GENERATOR.exists()
    assert GENERATOR.is_file()


def test_h_generator_syntax() -> None:
    """Verify the generator compiles without errors."""
    import py_compile
    try:
        py_compile.compile(str(GENERATOR), doraise=True)
    except py_compile.PyCompileError as e:
        pytest.fail(f"compile error: {e}")


def test_h_generator_sample_output_exists() -> None:
    """Sample 6h node report must exist (from dry-run on V2 in-flight data)."""
    assert SAMPLE_NODE_REPORT_DIR.exists()
    assert (SAMPLE_NODE_REPORT_DIR / "NODE_REPORT.json").exists()
    assert (SAMPLE_NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").exists()
    assert (SAMPLE_NODE_REPORT_DIR / "POOL_UNIVERSE_COVERAGE_MANIFEST.csv").exists()
    assert (SAMPLE_NODE_REPORT_DIR / "FEE_ESTIMATION_BASIS_CN.md").exists()
    assert (SAMPLE_NODE_REPORT_DIR / "RANGE_LIQUIDITY_FEE_SENSITIVITY.csv").exists()
    assert (SAMPLE_NODE_REPORT_DIR / "CANDIDATE_REVIEW.csv").exists()


def test_h_generator_sample_locked_fields() -> None:
    sample = json.loads((SAMPLE_NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert sample["can_run_probe_now"] is False
    assert sample["tiny_canary_allowed"] == "no"
    assert sample["edge_proven"] == "no"
    assert sample["wallet_or_tx_touched"] is False
    assert sample["transaction_sent"] is False
    assert sample["auto_probe_allowed"] is False
    assert sample["auto_trade_allowed"] is False
    assert sample["manual_approval_required_for_execution"] is True


def test_h_generator_sample_no_forbidden_keys() -> None:
    """Sample output must not contain any forbidden top-level keys."""
    sample = json.loads((SAMPLE_NODE_REPORT_DIR / "NODE_REPORT.json").read_text())
    forbidden = {"tx_hash", "wallet_address", "private_key", "keypair", "mnemonic", "seed", "signed_transaction"}
    for k in sample:
        assert k not in forbidden, f"forbidden top-level key {k!r} in sample"


def test_h_generator_sample_partial_sample_true() -> None:
    """V2 in-flight at 4/6 ckpts: sample should be partial_sample=true."""
    sample = json.loads((SAMPLE_NODE_REPORT_DIR / "FINAL_NODE_VERDICT.json").read_text())
    assert sample["partial_sample"] is True
    assert sample["checkpoint_count_observed"] == 4
    assert sample["checkpoint_count_expected"] == 6


# ---------------------------------------------------------------------------
# I: continuous_observation_next_stage_decision
# ---------------------------------------------------------------------------

def test_i_decision_files_exist() -> None:
    assert (REPORT_DIR / "CONTINUOUS_OBSERVATION_NEXT_STAGE_DECISION_CN.md").exists()
    assert (REPORT_DIR / "continuous_observation_next_stage_decision.json").exists()


def test_i_decision_selected_stage() -> None:
    d = json.loads((REPORT_DIR / "continuous_observation_next_stage_decision.json").read_text())
    assert d["selected_next_stage"] == "LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1"


# ---------------------------------------------------------------------------
# J: FINAL_VERDICT
# ---------------------------------------------------------------------------

def test_j_final_verdict_files() -> None:
    assert (REPORT_DIR / "FINAL_VERDICT.json").exists()
    assert (REPORT_DIR / "ONEPAGE_CN.md").exists()
    assert (REPORT_DIR / "ARTIFACT_INDEX.md").exists()


def test_j_final_verdict_required_fields() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["current_v2_touched"] is False
    assert fv["continuous_observation_design_ready"] is True
    assert fv["node_report_schema_ready"] is True
    assert fv["coverage_manifest_spec_ready"] is True
    assert fv["fee_estimation_explained"] is True
    assert fv["range_liquidity_fee_sensitivity_spec_ready"] is True
    assert fv["node_report_generator_built"] is True
    assert fv["sample_node_report_generated"] is True
    assert fv["collection_can_continue_between_nodes"] is True
    assert fv["auto_probe_allowed"] is False
    assert fv["auto_trade_allowed"] is False
    assert fv["manual_approval_required_for_execution"] is True
    assert fv["can_run_probe_now"] is False
    assert fv["tiny_canary_allowed"] == "no"
    assert fv["edge_proven"] == "no"
    assert fv["wallet_or_tx_touched"] is False
    assert fv["transaction_sent"] is False
    assert fv["recommended_next_stage"] in fv["allowed_next_stages_locked"]


def test_j_final_verdict_recommended_next_stage() -> None:
    fv = json.loads((REPORT_DIR / "FINAL_VERDICT.json").read_text())
    assert fv["recommended_next_stage"] == "LP_LONG_HORIZON_CONTINUOUS_OBSERVATION_NODE_REPORTS_V1"


# ---------------------------------------------------------------------------
# Cross-cutting safety tests
# ---------------------------------------------------------------------------

def test_no_collector_restart_since_audit() -> None:
    """No V2 supervisor restart since Stage A audit (~5 min ago)."""
    rc = subprocess.run(
        ["ps", "-p", "3872268", "-o", "etime="],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0
    # ELAPSED should be > 3:00:00 (no fresh restart)
    elapsed = rc.stdout.strip()
    h, m, s = (int(x) for x in elapsed.split(":"))
    assert h * 3600 + m * 60 + s > 3 * 3600


def test_no_new_tmux_session_for_observation() -> None:
    """No new tmux session for the observation stage."""
    rc = subprocess.run(
        ["tmux", "ls"],
        capture_output=True, text=True,
    )
    assert "staged_observation" not in rc.stdout


def test_v2_data_dir_unchanged() -> None:
    """V2 data dir must still have exactly 28 files (4 ckpts × 7)."""
    files = list(V2_DATA_DIR.rglob("*"))
    files = [f for f in files if f.is_file()]
    assert len(files) == 28


def test_v2_report_dir_unchanged() -> None:
    """V2 report dir must NOT have any new top-level files added by this stage.

    V2 supervisor is still running and writes new heartbeat files in
    logs/heartbeat/ during the 6h run. We assert the top-level files (not
    under logs/) are unchanged from the original 7.
    """
    top_level = [p for p in V2_REPORT_DIR.iterdir() if p.is_file()]
    # 7 startup files (pre-finalize): 4 *.json + 3 *.md + supervisor.pid
    assert len(top_level) == 7, f"expected 7 top-level V2 files, got {len(top_level)}: {[p.name for p in top_level]}"
    expected_names = {
        "MANUAL_APPROVAL_RECORDED.json", "MANUAL_APPROVAL_RECORDED_CN.md",
        "PRE_RUN_SAFETY_CHECK_CN.md", "pre_run_safety_check.json",
        "TMUX_START_HEALTHCHECK_CN.md", "tmux_start_healthcheck.json",
        "supervisor.pid",
    }
    actual_names = {p.name for p in top_level}
    assert expected_names == actual_names, f"V2 top-level mismatch: extra={actual_names-expected_names}, missing={expected_names-actual_names}"


def test_no_forbidden_process_running() -> None:
    """No canary / live / paper / sendTransaction / keypair / wallet process must be running."""
    rc = subprocess.run(
        ["ps", "aux"],
        capture_output=True, text=True,
    )
    forbidden_patterns = ["canary", "lpbot-live", "sendTransaction", "eth_sendRawTransaction", "eth_sendTransaction", "keypair", "private_key", "mnemonic"]
    for pat in forbidden_patterns:
        # word-boundary-ish: must not appear as a process arg
        for line in rc.stdout.splitlines():
            if "grep" in line:
                continue
            if re.search(rf"\b{re.escape(pat)}\b", line):
                pytest.fail(f"forbidden process {pat!r} found: {line}")


def test_no_secret_leak_in_generated_reports() -> None:
    """No private_key / mnemonic / seed / wallet secret VALUE in this stage's reports.

    Documentation references to these tokens (as forbidden-key list) are allowed.
    """
    # Look for actual secret *values* — not field names.
    # Patterns: "private_key": "0xabc...", mnemonic phrase, hex key string, base64 secret
    value_patterns = [
        re.compile(r'"private_key"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"mnemonic"\s*:\s*"([^"]{8,})"'),
        re.compile(r'"seed"\s*:\s*"([^"]{8,})"'),
        re.compile(r'0x[0-9a-fA-F]{64}'),  # 32-byte private key
        re.compile(r'[0-9a-fA-F]{64,}'),  # any long hex
    ]
    for p in REPORT_DIR.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".md", ".csv"}:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pat in value_patterns:
                m = pat.search(text)
                if m:
                    pytest.fail(f"potential secret value matched {pat.pattern!r} in {p}: {m.group(0)[:80]}")


# ---------------------------------------------------------------------------
# Generator CLI: regression test
# ---------------------------------------------------------------------------

def test_generator_rejects_bad_node() -> None:
    """The generator must refuse unknown node stage (argparse)."""
    rc = subprocess.run(
        [sys.executable, str(GENERATOR), "--run-id", "20260605_043726", "--node", "99h"],
        capture_output=True, text=True,
    )
    assert rc.returncode != 0
    # argparse emits "invalid choice" + "choose from"
    assert ("invalid choice" in rc.stderr) or ("REFUSED" in rc.stderr)


def test_generator_rejects_bad_data_dir() -> None:
    """The generator must refuse data_dir not under data/lp_long_horizon."""
    rc = subprocess.run(
        [sys.executable, str(GENERATOR), "--run-id", "20260605_043726", "--node", "6h",
         "--data-dir", "tmp/bad", "--report-dir", "reports/bad"],
        capture_output=True, text=True,
    )
    assert rc.returncode != 0
    assert "REFUSED" in rc.stderr


def test_generator_runs_on_v2_data() -> None:
    """The generator must run end-to-end on V2 in-flight data."""
    rc = subprocess.run(
        [sys.executable, str(GENERATOR),
         "--run-id", "20260605_043726",
         "--node", "6h",
         "--data-dir", "data/lp_long_horizon/20260605_043726",
         "--report-dir", "reports/lp_long_horizon_node_reports/20260605_043726/6h_regression_test"],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0, f"generator failed: {rc.stderr}"
    # Check that the run produced the expected output structure
    out = json.loads(rc.stdout)
    assert out["gate_status"] in ("PASS", "WARN_ACCEPTABLE", "FAIL")
    assert out["partial_sample"] is True  # V2 still in-flight
    # Cleanup: remove the regression test output to keep repo clean
    import shutil
    shutil.rmtree(ROOT / "reports" / "lp_long_horizon_node_reports" / "20260605_043726" / "6h_regression_test", ignore_errors=True)
